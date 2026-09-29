"""AI review state stored on a report: queued, completed with suggestions, or failed.

Suggestions change results only when the user accepts them, or automatically for safe fixes when
that is turned on in AI settings (see is_safe_fix). Each applied suggestion is kept with the values it replaced
so it can be undone, and dismissed suggestions are removed from the stored review.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ai_settings.services import ROLE_REPORT_REVIEW, get_ai_config
from lab_tests.models import LabTestType
from lab_tests.matching import TestNameMatcher
from lab_tests.services import build_test_type_matcher, normalize_test_identifier

from .models import MedicalReport, TestResult

PENDING = 'pending'
COMPLETED = 'completed'
FAILED = 'failed'

# A review that started this long ago was lost (worker restart or hard time limit), so it is shown as failed.
RUNNING_TIMEOUT = timedelta(hours=1)
# A review still waiting to start after this long was lost from the queue. Waiting alone can take hours,
# because a bulk upload queues one review per report behind the others.
QUEUED_TIMEOUT = timedelta(hours=24)

# Corrections to how a printed result was read that leave its name and value alone.
SAFE_UPDATE_FIELDS = frozenset({'unit', 'reference_range', 'status'})
MAX_DISMISSED = 500  # dismissed suggestions remembered per report
RESULT_FIELDS = ('test_name', 'value', 'unit', 'reference_range', 'status', 'notes')


class ReviewConflict(Exception):
    """A change from the review cannot be undone as asked; the message is safe to show to the user."""


def auto_review_enabled() -> bool:
    """Whether reviewing every report after it is parsed is turned on in AI settings."""
    config = get_ai_config(ROLE_REPORT_REVIEW)
    return config.is_configured and config.auto_review


def result_identity(test_name: str, value: str, catalog: TestNameMatcher) -> tuple[object, str]:
    """Results are the same when their names resolve to one catalog test (or match as typed) and their values match."""
    test_type = catalog.match(test_name)
    return (test_type.pk if test_type else normalize_test_identifier(test_name), str(value or '').strip())


def pending_review(options: dict[str, bool] | None = None) -> dict[str, Any]:
    review: dict[str, Any] = {'status': PENDING, 'run_id': uuid.uuid4().hex, 'queued_at': timezone.now().isoformat()}
    if options:
        review['options'] = options
    return review


def failed_review(error: str) -> dict[str, Any]:
    return {'status': FAILED, 'error': error[:1000], 'reviewed_at': timezone.now().isoformat()}


def review_memory(report: MedicalReport) -> dict[str, Any]:
    """What a report keeps from its earlier reviews: the suggestions the user dismissed, so they are not shown again."""
    dismissed = _stored(report).get('dismissed')
    return {'dismissed': dismissed} if dismissed else {}


def suggestion_key(item: Any, results: dict[int, Any]) -> str | None:
    """A suggestion's identity across reviews: the action and change, and the name and value of the row it is about."""
    if not isinstance(item, dict):
        return None
    action = item.get('action')
    if action == 'add':
        result = item.get('result') or {}
        return json.dumps(['add', normalize_test_identifier(result.get('test_name')), str(result.get('value') or '').strip()])
    row = results.get(item.get('result_id'))
    if row is None or action not in ('update', 'remove'):
        return None
    key: list[Any] = [action, normalize_test_identifier(row.test_name), (row.value or '').strip()]
    if action == 'update':
        key.append(sorted((name, str(value).strip()) for name, value in (item.get('changes') or {}).items()))
    return json.dumps(key)


def clear_review(report: MedicalReport) -> None:
    """Close the report's review, keeping which suggestions the user dismissed."""
    report.ai_review = review_memory(report)
    report.save(update_fields=['ai_review'])


def start_review(report: MedicalReport, options: dict[str, bool] | None = None) -> str:
    """Mark a new review as queued, replacing the report's earlier review; returns the new run id.

    options ({'ocr': bool, 'images': bool}) choose what this review reads; see review_options.
    """
    report.ai_review = {**pending_review(options), **review_memory(report)}
    report.save(update_fields=['ai_review'])
    return report.ai_review['run_id']


def review_options(report: MedicalReport) -> dict[str, bool]:
    """What the report's current review reads: the pages' OCR text, page images, or neither (the AI setting decides)."""
    options = _stored(report).get('options')
    options = options if isinstance(options, dict) else {}
    return {'ocr': options.get('ocr') is True, 'images': options.get('images') is True}


def stop_review(report: MedicalReport) -> str | None:
    """Discard the report's queued or running review so nothing from it is stored or applied.

    Returns the stopped review's run id (its Celery task id), or None when no review was pending.
    """
    with transaction.atomic():
        locked = MedicalReport.objects.select_for_update().get(pk=report.pk)
        review = _stored(locked)
        if review.get('status') != PENDING:
            return None
        locked.ai_review = review_memory(locked)
        locked.save(update_fields=['ai_review'])
    report.ai_review = locked.ai_review
    return str(review.get('run_id') or '')


def mark_review_started(report_id: int, run_id: str) -> bool:
    """Record that a queued review is starting; False when it is no longer the report's current review."""
    with transaction.atomic():
        report = MedicalReport.objects.select_for_update().filter(pk=report_id).first()
        review = _stored(report) if report else {}
        if review.get('run_id') != run_id or review.get('status') != PENDING:
            return False
        report.ai_review = {**review, 'started_at': timezone.now().isoformat()}
        report.save(update_fields=['ai_review'])
    return True


def is_safe_fix(item: Any) -> bool:
    """Whether a suggestion may be applied without the user.

    The model must have been shown the text line or page the row was read from, and the fix may
    only remove the row or correct its unit, reference range, or status. Adds, renames, and value
    changes always wait for the user.
    """
    if not isinstance(item, dict) or item.get('row_seen') is not True:
        return False
    if item.get('action') == 'remove':
        return True
    changes = item.get('changes')
    return (
        item.get('action') == 'update'
        and isinstance(changes, dict)
        and bool(changes)
        and set(changes) <= SAFE_UPDATE_FIELDS
    )


def finish_queued_review(report_id: int, run_id: str, outcome: dict[str, Any], auto_apply: bool = False) -> bool:
    """Store a queued review's outcome if it is still the report's current review, applying safe fixes if asked."""
    with transaction.atomic():
        report = MedicalReport.objects.select_for_update().filter(pk=report_id).first()
        if report is None or _stored(report).get('run_id') != run_id:
            return False
        memory = review_memory(report)
        if memory and outcome.get('status') == COMPLETED:
            results = {result.id: result for result in TestResult.objects.filter(report=report)}
            dismissed = set(memory['dismissed'])
            outcome = {
                **outcome,
                'suggestions': [
                    item for item in outcome.get('suggestions') or [] if suggestion_key(item, results) not in dismissed
                ],
            }
        report.ai_review = {**outcome, 'run_id': run_id, **memory}
        if auto_apply and outcome.get('status') == COMPLETED:
            safe_ids = [item['id'] for item in outcome.get('suggestions') or [] if is_safe_fix(item)]
            _apply(report, safe_ids, automatic=True)
        report.save(update_fields=['ai_review'])
    return True


def apply_suggestions(report: MedicalReport, suggestion_ids: list[int]) -> list[int]:
    """Apply suggestions the user accepted in one transaction; returns the ids that were still open and applied."""
    with transaction.atomic():
        locked = MedicalReport.objects.select_for_update().get(pk=report.pk)
        applied = _apply(locked, suggestion_ids, automatic=False)
        locked.save(update_fields=['ai_review'])
    report.ai_review = locked.ai_review
    return applied


def undo_applied(report: MedicalReport, applied_id: int) -> None:
    """Revert one applied suggestion and drop it from the review.

    Raises ReviewConflict when the result changed after the suggestion was applied, so a later
    edit is never overwritten.
    """
    with transaction.atomic():
        locked = MedicalReport.objects.select_for_update().get(pk=report.pk)
        review = _stored(locked)
        applied = [item for item in review.get('applied') or [] if isinstance(item, dict)]
        record = next((item for item in applied if item.get('id') == applied_id), None)
        if record is None:
            raise ReviewConflict('This change is no longer part of the AI review.')
        row = None
        if record.get('result_id') is not None:
            row = TestResult.objects.select_for_update().filter(report=locked, pk=record['result_id']).first()

        action = record.get('action')
        if action == 'remove':
            values = record.get('result') or {}
            test_type_id = record.get('test_type_id')
            TestResult.objects.create(
                report=locked,
                test_type=LabTestType.objects.filter(pk=test_type_id).first() if test_type_id else None,
                **{name: values.get(name) or '' for name in RESULT_FIELDS},
            )
        elif action == 'update':
            changes = record.get('changes') or {}
            if row is None or any(_value(row, name) != value for name, value in changes.items()):
                raise ReviewConflict('This result was edited or deleted after the fix. Change it directly instead.')
            for name, value in (record.get('before') or {}).items():
                setattr(row, name, value)
            if changes.keys() & {'test_name', 'value'}:
                row.test_type = build_test_type_matcher(locked.user_id).match(row.test_name, value=row.value)
            row.save()
        elif action == 'add' and row is not None:
            if _snapshot(row) != record.get('result'):
                raise ReviewConflict('This result was edited after it was added. Delete it directly instead.')
            row.delete()

        locked.ai_review = {**review, 'applied': [item for item in applied if item is not record]}
        locked.save(update_fields=['ai_review'])
    report.ai_review = locked.ai_review


def review_status(report: MedicalReport) -> str:
    review = _stored(report)
    status = review.get('status') or ''
    return FAILED if status == PENDING and _expired(review) else status


def visible_review(report: MedicalReport) -> dict[str, Any] | None:
    """The stored review as the report page should show it now.

    Leaves out suggestions that are already applied or refer to results that no longer exist.
    """
    review = _stored(report)
    status = review.get('status')
    if status == PENDING and _expired(review):
        review = {'status': FAILED, 'error': 'The AI review did not finish. Run it again.', 'reviewed_at': review.get('queued_at')}
    elif status == COMPLETED:
        suggestions = _open_suggestions(report, review, build_test_type_matcher(report.user_id))
        review = {**review, 'suggestions': suggestions, 'applied': review.get('applied') or []}
    elif status not in (PENDING, FAILED):
        return None
    return {key: value for key, value in review.items() if key not in ('run_id', 'dismissed')}


def review_summary(report: MedicalReport, catalog: TestNameMatcher) -> dict[str, Any]:
    """A review's state for report lists: status, whether a queued review has started, and open suggestions."""
    review = _stored(report)
    status = review_status(report)
    return {
        'status': status,
        'started': status == PENDING and bool(review.get('started_at')),
        'open_suggestions': len(_open_suggestions(report, review, catalog)) if status == COMPLETED else 0,
    }


def dismiss_suggestion(report: MedicalReport, suggestion_id: int) -> None:
    with transaction.atomic():
        locked = MedicalReport.objects.select_for_update().get(pk=report.pk)
        review = _stored(locked)
        suggestions = review.get('suggestions') or []
        kept = [item for item in suggestions if not isinstance(item, dict) or item.get('id') != suggestion_id]
        if len(kept) != len(suggestions):
            removed = next(item for item in suggestions if isinstance(item, dict) and item.get('id') == suggestion_id)
            results = {result.id: result for result in TestResult.objects.filter(report=locked)}
            key = suggestion_key(removed, results)
            dismissed = list(review.get('dismissed') or [])
            if key and key not in dismissed:
                dismissed = (dismissed + [key])[-MAX_DISMISSED:]
            locked.ai_review = {**review, 'suggestions': kept, 'dismissed': dismissed}
            locked.save(update_fields=['ai_review'])


def _apply(report: MedicalReport, suggestion_ids: list[int], automatic: bool) -> list[int]:
    """Apply the open suggestions with these ids to a locked report's results and record them as applied."""
    review = _stored(report)
    wanted = set(suggestion_ids)
    if review.get('status') != COMPLETED or not wanted:
        return []
    results = {result.id: result for result in TestResult.objects.select_for_update().filter(report=report)}
    catalog = build_test_type_matcher(report.user_id)
    existing = {result_identity(result.test_name, result.value, catalog) for result in results.values()}
    applied_at = timezone.now().isoformat()
    kept: list[Any] = []
    applied: list[dict[str, Any]] = list(review.get('applied') or [])
    applied_ids: list[int] = []

    for item in review.get('suggestions') or []:
        wanted_item = isinstance(item, dict) and item.get('id') in wanted
        open_item = _still_open(item, results, existing, catalog) if wanted_item else None
        if open_item is None:
            kept.append(item)
            continue

        record: dict[str, Any] = {
            'id': item['id'],
            'action': item['action'],
            'reason': item.get('reason', ''),
            'automatic': automatic,
            'applied_at': applied_at,
        }
        if item['action'] == 'remove':
            row = results.pop(item['result_id'])
            record.update(result=_snapshot(row), test_type_id=row.test_type_id)
            row.delete()
        elif item['action'] == 'update':
            row = results[item['result_id']]
            changes = open_item['changes']
            record.update(result_id=row.id, changes=changes, before={name: _value(row, name) for name in changes})
            for name, value in changes.items():
                setattr(row, name, value)
            if changes.keys() & {'test_name', 'value'}:
                row.test_type = catalog.match(row.test_name, value=row.value)
            row.save()
            existing.add(result_identity(row.test_name, row.value, catalog))
        else:
            values = open_item['result']
            row = TestResult.objects.create(
                report=report,
                test_type=catalog.match(values.get('test_name'), value=values.get('value')),
                **{name: values.get(name) or '' for name in RESULT_FIELDS if name != 'notes'},
            )
            results[row.id] = row
            existing.add(result_identity(row.test_name, row.value, catalog))
            record.update(result_id=row.id, result=_snapshot(row))
        applied.append(record)
        applied_ids.append(item['id'])

    report.ai_review = {**review, 'suggestions': kept, 'applied': applied}
    return applied_ids


def _stored(report: MedicalReport) -> dict[str, Any]:
    return report.ai_review if isinstance(report.ai_review, dict) else {}


def _expired(review: dict[str, Any]) -> bool:
    """Whether a pending review was lost: running for too long, or never started from the queue."""
    started_at = parse_datetime(str(review.get('started_at') or ''))
    if started_at is not None:
        return timezone.now() - started_at > RUNNING_TIMEOUT
    queued_at = parse_datetime(str(review.get('queued_at') or ''))
    return queued_at is None or timezone.now() - queued_at > QUEUED_TIMEOUT


def _open_suggestions(report: MedicalReport, review: dict[str, Any], catalog: TestNameMatcher) -> list[dict[str, Any]]:
    """Stored suggestions the report's current results do not already match."""
    results = {result.id: result for result in report.test_results.all()}
    existing = {result_identity(result.test_name, result.value, catalog) for result in results.values()}
    open_items = (_still_open(item, results, existing, catalog) for item in review.get('suggestions') or [])
    return [item for item in open_items if item]


def _value(row: TestResult, name: str) -> str:
    return getattr(row, name) or ''


def _snapshot(row: TestResult) -> dict[str, str]:
    return {name: _value(row, name) for name in RESULT_FIELDS}


def _still_open(item: Any, results: dict, existing: set, catalog: TestNameMatcher) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    action = item.get('action')
    if action == 'add':
        result = item.get('result') or {}
        return None if result_identity(result.get('test_name', ''), result.get('value', ''), catalog) in existing else item

    row = results.get(item.get('result_id'))
    if row is None:
        return None
    if action == 'remove':
        return item
    changes = {name: value for name, value in (item.get('changes') or {}).items() if _value(row, name) != value}
    if not changes:
        return None
    still_open = {**item, 'changes': changes}
    if 'test_name' not in changes:
        still_open.pop('catalog_name', None)
    return still_open
