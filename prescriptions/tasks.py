"""Reading an uploaded prescription in the background, the way a medical report is read.

The upload returns as soon as the file is stored, at PENDING, and the page polls the status endpoint while
this runs. Reading a scan or a photograph means an OCR call per page, which is far too slow to hold a
request open for.
"""

from __future__ import annotations

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.files.storage import default_storage
from django.db import transaction

from utils.prescription_parser import PrescriptionReadError, parse_prescription
from utils.prescription_review import PrescriptionReviewError, review_prescription

from .ai_review import COMPLETED, failed_review, finish, mark_started, review_options
from .models import Medication, Prescription

logger = logging.getLogger(__name__)


def _save_failure(prescription: Prescription, message: str) -> None:
    prescription.status = 'FAILED'
    prescription.parse_error = message[:900]
    prescription.save(update_fields=['status', 'parse_error', 'updated_at'])


@shared_task(bind=True, ignore_result=True)
def parse_prescription_task(self, prescription_id: int) -> None:
    """Read the prescription's text and the medicines on it, replacing whatever was read before."""
    prescription = Prescription.objects.filter(pk=prescription_id).first()
    if prescription is None:
        logger.info('Prescription %s is gone; nothing to parse', prescription_id)
        return

    prescription.status = 'PROCESSING'
    prescription.parse_error = ''
    prescription.save(update_fields=['status', 'parse_error', 'updated_at'])

    try:
        with default_storage.open(prescription.file.name, 'rb') as handle:
            file_bytes = handle.read()
        result = parse_prescription(file_bytes, prescription.file.name)
    except SoftTimeLimitExceeded:
        _save_failure(prescription, 'Reading this prescription took too long.')
        raise
    except PrescriptionReadError as exc:
        # A missing OCR model or an unreadable file: the reason is the user's to act on, so it is kept.
        _save_failure(prescription, str(exc))
        return
    except Exception as exc:
        logger.exception('Could not read prescription %s', prescription_id)
        _save_failure(prescription, f'Could not read this prescription ({type(exc).__name__}).')
        return

    medications = result.get('medications') or []
    with transaction.atomic():
        # Replace the earlier rows so a retry or a re-read never doubles them up.
        Medication.objects.filter(prescription=prescription).delete()
        if medications:
            Medication.objects.bulk_create([
                Medication(prescription=prescription, **medication) for medication in medications
            ])
        prescription.parsed_data = result
        prescription.is_parsed = bool(medications)
        prescription.status = 'COMPLETED'
        prescription.parse_error = ''
        prescription.save(
            update_fields=['parsed_data', 'is_parsed', 'status', 'parse_error', 'updated_at']
        )

    logger.info(
        'Prescription %s read: %s medicines, text from %s, read by %s',
        prescription_id, len(medications), result.get('text_source'), result.get('read_by'),
    )


def queue_parse(prescription: Prescription) -> None:
    """Enqueue the read once the upload's transaction has committed."""
    prescription_id = prescription.id

    def dispatch() -> None:
        try:
            parse_prescription_task.delay(prescription_id)
        except Exception as exc:
            logger.exception('Could not enqueue prescription %s for parsing', prescription_id)
            Prescription.objects.filter(pk=prescription_id).update(
                status='FAILED', parse_error=f'Could not queue this prescription for reading: {str(exc)[:900]}'
            )

    transaction.on_commit(dispatch)


@shared_task(bind=True, ignore_result=True, queue='ai_review')
def review_prescription_task(self, prescription_id: int, run_id: str) -> None:
    """Check a prescription's medicines against the prescription itself, on the review worker.

    Reviews share the one worker so the model server gets them one at a time, as report reviews do.
    """
    from ai_settings.services import ROLE_REPORT_REVIEW, get_ai_config

    if not mark_started(prescription_id, run_id):
        logger.info('Prescription %s review %s was replaced or stopped before it began', prescription_id, run_id)
        return

    prescription = Prescription.objects.filter(pk=prescription_id).first()
    if prescription is None:
        return

    file_bytes = None
    try:
        if prescription.file:
            with default_storage.open(prescription.file.name, 'rb') as handle:
                file_bytes = handle.read()
    except Exception as exc:
        logger.warning('Could not read prescription %s for its review: %s', prescription_id, exc)

    try:
        outcome = review_prescription(
            prescription,
            get_ai_config(ROLE_REPORT_REVIEW),
            file_bytes,
            images=review_options(prescription)['images'],
        )
    except PrescriptionReviewError as exc:
        finish(prescription_id, run_id, failed_review(str(exc)))
        return
    except SoftTimeLimitExceeded:
        finish(prescription_id, run_id, failed_review('The AI review took too long.'))
        raise
    except Exception as exc:
        logger.exception('Reviewing prescription %s failed', prescription_id)
        finish(prescription_id, run_id, failed_review(f'The AI review failed ({type(exc).__name__}).'))
        return

    finish(prescription_id, run_id, {'status': COMPLETED, **outcome})


def queue_review(prescription_id: int, run_id: str) -> None:
    """Enqueue a queued review once the current transaction commits."""

    def dispatch() -> None:
        try:
            # The run id doubles as the task id, so stopping the review can revoke it.
            review_prescription_task.apply_async((prescription_id, run_id), task_id=run_id)
        except Exception as exc:
            logger.exception('Could not enqueue the AI review for prescription %s', prescription_id)
            finish(prescription_id, run_id, failed_review(f'Could not queue the AI review: {exc}'))

    transaction.on_commit(dispatch)


def cancel_review_task(run_id: str) -> None:
    """Revoke a review task: a queued one never runs, a running one is stopped so the worker moves on."""
    if not run_id:
        return
    try:
        from diagnoseit_backend.celery import app

        app.control.revoke(run_id, terminate=True, signal='SIGTERM')
    except Exception as exc:
        logger.warning('Could not revoke the prescription review task %s: %s', run_id, exc)
