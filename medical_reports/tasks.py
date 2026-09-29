import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction

from ai_settings.services import ROLE_REPORT_REVIEW, get_ai_config
from medical_reports.ai_review import (
    auto_review_enabled, failed_review, finish_queued_review, mark_review_started, pending_review, review_memory,
    review_options,
)
from medical_reports.models import MedicalReport, TestResult
from lab_tests.services import build_test_type_matcher, tidy_test_name
from utils.vlm_pdf_parser import parse_medical_pdf_hybrid

logger = logging.getLogger(__name__)

# Stop a review a minute before the worker's hard time limit so its failure can still be recorded.
REVIEW_SOFT_TIME_LIMIT = max(60, getattr(settings, "CELERY_TASK_TIME_LIMIT", 1800) - 60)

# Map parser/validation statuses onto TestResult.status choices.
_STATUS_MAP = {
    "NORMAL": "NORMAL",
    "HIGH": "HIGH",
    "LOW": "LOW",
    "ABNORMAL": "ABNORMAL",
    "CRITICAL_HIGH": "HIGH",
    "CRITICAL_LOW": "LOW",
    "UNKNOWN": "",
    "INVALID": "",
}


def normalize_test_status(raw_status) -> str:
    """Normalize parser status strings to TestResult.status choices."""
    if not raw_status:
        return ""
    return _STATUS_MAP.get(str(raw_status).strip().upper(), "")


def _build_test_results(report: MedicalReport, test_results: list) -> list[tuple[dict, TestResult]]:
    """Convert parser output into TestResult instances paired with their parser rows, skipping low-confidence noise."""
    pairs = []
    matcher = build_test_type_matcher(report.user_id)
    for tr in test_results:
        test_name = tr.get("test_name", "Unknown")
        confidence = tr.get("confidence", 1.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 1.0

        # Skip garbage matches from legacy regex fallback
        if str(test_name).lower() == "unknown" and confidence <= 0.5:
            continue

        display_name = tr.get("display_name") or test_name
        # Parser rows carry the catalog name when identified; OCR and vision rows carry the printed name.
        context = tr.get("section_context") or None
        unit = tr.get("unit") or ""
        value = str(tr.get("value", ""))
        test_type = (
            matcher.match(test_name, context=context, unit=unit, value=value)
            or matcher.match(display_name, context=context, unit=unit, value=value)
        )
        pairs.append((
            tr,
            TestResult(
                report=report,
                test_type=test_type,
                test_name=tidy_test_name(display_name) or "Unknown",
                value=value,
                unit=tr.get("unit") or "",
                reference_range=tr.get("reference_range") or "",
                status=normalize_test_status(tr.get("status", "")),
            ),
        ))
    return pairs


def queue_review(report_id: int, run_id: str) -> None:
    """Enqueue the report's queued AI review once the current transaction commits."""

    def dispatch() -> None:
        try:
            # The run id doubles as the Celery task id, so stopping the review can revoke this task.
            review_report_task.apply_async((report_id, run_id), task_id=run_id)
        except Exception as exc:
            logger.exception("Could not enqueue AI review for report %s", report_id)
            finish_queued_review(report_id, run_id, failed_review(f"Could not queue the AI review: {str(exc)[:900]}"))

    transaction.on_commit(dispatch)


def cancel_review_task(run_id: str) -> None:
    """Revoke a review task: a queued one never runs, and a running one is terminated so the worker moves on."""
    try:
        review_report_task.app.control.revoke(run_id, terminate=True)
    except Exception:
        # The stored review is already discarded, so the task skips itself or its result is ignored.
        logger.exception("Could not revoke AI review task %s", run_id)


@shared_task(bind=True, max_retries=2)
def parse_report_task(self, report_id: int, review: bool | None = None):
    """
    Async Celery task to parse a medical report PDF using the hybrid VLM/legacy parser.

    Idempotent: replaces any existing TestResult rows for the report.
    Atomic: status is marked COMPLETED only after results are written.
    Queues an AI review of the new results when the upload asked for one, or when it made no choice
    (review=None) and automatic review is turned on in AI settings.
    """
    try:
        report = MedicalReport.objects.get(id=report_id)
    except MedicalReport.DoesNotExist:
        logger.error("Report %s not found for parsing", report_id)
        return

    report.status = "PROCESSING"
    report.parse_error = ""
    report.save(update_fields=["status", "parse_error"])

    try:
        with default_storage.open(report.file.name, "rb") as f:
            result = parse_medical_pdf_hybrid(f)

        if result.get("error"):
            raise ValueError(result["error"])

        test_results = result.get("test_results", [])
        pairs = _build_test_results(report, test_results)
        auto_review = auto_review_enabled() if review is None else review

        with transaction.atomic():
            # Replace prior rows so retries/redelivery do not duplicate results
            TestResult.objects.filter(report=report).delete()
            if pairs:
                TestResult.objects.bulk_create([test_result for _, test_result in pairs])
                # Record the saved row each parser row became, so an AI review can find where it was printed.
                for source, test_result in pairs:
                    if test_result.pk is not None:
                        source["result_id"] = test_result.pk

            report.parsed_data = result
            report.is_parsed = len(pairs) > 0
            report.status = "COMPLETED"
            report.parse_error = ""
            # New results make any earlier review obsolete.
            report.ai_review = {**pending_review(), **review_memory(report)} if auto_review else review_memory(report)
            report.save(
                update_fields=["parsed_data", "is_parsed", "status", "parse_error", "ai_review"]
            )

        if auto_review:
            queue_review(report.id, report.ai_review["run_id"])

        logger.info(
            "Report %s parsed successfully: %s tests", report_id, len(pairs)
        )
    except Exception as exc:
        logger.error("Failed to parse report %s: %s", report_id, exc)
        if self.request.retries < self.max_retries:
            report.status = "PROCESSING"
            report.parse_error = f"Parse attempt failed; retrying: {str(exc)[:950]}"
            report.save(update_fields=["status", "parse_error"])
            raise self.retry(exc=exc, countdown=60)

        report.status = "FAILED"
        # Store a concise error for the client; avoid dumping full stack traces.
        report.parse_error = str(exc)[:1000]
        report.save(update_fields=["status", "parse_error"])
        logger.error("Report %s exhausted parse retries", report_id)


@shared_task(soft_time_limit=REVIEW_SOFT_TIME_LIMIT)
def review_report_task(report_id: int, run_id: str):
    """Review a report's results with the AI review model, store its suggestions, and apply safe fixes if turned on."""
    # Imported here because utils.report_review imports this module.
    from utils.report_review import ReportReviewError, review_report

    if not mark_review_started(report_id, run_id):
        return  # deleted, cleared, or replaced by a newer review before this one started
    report = MedicalReport.objects.filter(id=report_id).first()
    if report is None:
        return

    config = get_ai_config(ROLE_REPORT_REVIEW)
    if not config.is_configured:
        outcome = failed_review("AI review is not configured. Set it up in AI settings.")
    else:
        try:
            outcome = review_report(report, config, **review_options(report))
        except ReportReviewError as exc:
            outcome = failed_review(str(exc))
        except SoftTimeLimitExceeded:
            outcome = failed_review("The AI review took too long and was stopped. Run it again from the report page.")
        except Exception:
            logger.exception("AI review failed for report %s", report_id)
            outcome = failed_review("The AI review failed unexpectedly. Run it again from the report page.")
    finish_queued_review(report_id, run_id, outcome, auto_apply=config.is_configured and config.auto_apply)
