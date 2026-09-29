"""The state of a prescription's AI review, and what the user does with its suggestions.

A review is queued, runs on the review worker, and leaves suggestions on the prescription. Nothing is ever
applied on its own: unlike a lab report, where correcting a unit or a reference range is safe, every change
here is to a medicine, and a dose changed without the user is a harm no confidence justifies. Accepting one
records what it replaced, so it can be undone; dismissing one is remembered, so a later review does not
raise it again.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import Medication, Prescription

PENDING = 'pending'
COMPLETED = 'completed'
FAILED = 'failed'

# A review still queued after this never ran: the worker is down, or its task was lost.
QUEUED_TIMEOUT = timedelta(hours=24)
MAX_DISMISSED = 200
FIELDS = ('medication_name', 'dosage', 'frequency', 'duration', 'instructions')


def _stored(prescription: Prescription) -> dict[str, Any]:
    return prescription.ai_review if isinstance(prescription.ai_review, dict) else {}


def _expired(review: dict[str, Any]) -> bool:
    queued = review.get('queued_at')
    if not queued:
        return False
    try:
        return timezone.now() - timezone.datetime.fromisoformat(queued) > QUEUED_TIMEOUT
    except (TypeError, ValueError):
        return False


def review_memory(prescription: Prescription) -> dict[str, Any]:
    """What a prescription keeps from earlier reviews: the suggestions the user dismissed."""
    dismissed = _stored(prescription).get('dismissed')
    return {'dismissed': dismissed} if dismissed else {}


def suggestion_key(item: Any, medications: dict[int, Medication]) -> str | None:
    """A suggestion's identity across reviews, so one dismissed is not raised again."""
    if not isinstance(item, dict):
        return None
    action = item.get('action')
    if action == 'add':
        medication = item.get('medication') or {}
        return json.dumps(['add', str(medication.get('medication_name') or '').strip().casefold()])
    row = medications.get(item.get('medication_id'))
    if row is None or action not in ('update', 'remove'):
        return None
    key: list[Any] = [action, (row.medication_name or '').strip().casefold()]
    if action == 'update':
        key.append(sorted((name, str(value).strip()) for name, value in (item.get('changes') or {}).items()))
    return json.dumps(key)


def default_images(prescription: Prescription) -> bool:
    """Whether to send the page image by default: yes when the text itself came from OCR.

    Checking OCR text against itself confirms its mistakes rather than catching them, so for a photo or a
    scan the image is the only thing worth comparing against.
    """
    data = prescription.parsed_data if isinstance(prescription.parsed_data, dict) else {}
    return data.get('text_source') in ('photo', 'ocr')


def start_review(prescription: Prescription, options: dict[str, bool] | None = None) -> str:
    """Queue a new review, replacing any earlier one; returns its run id, which is also its task id.

    options ({'images': bool}) chooses whether the original page image is sent as well as the text.
    """
    prescription.ai_review = {
        'status': PENDING,
        'run_id': uuid.uuid4().hex,
        'queued_at': timezone.now().isoformat(),
        'options': {'images': bool((options or {}).get('images', default_images(prescription)))},
        **review_memory(prescription),
    }
    prescription.save(update_fields=['ai_review', 'updated_at'])
    return prescription.ai_review['run_id']


def review_options(prescription: Prescription) -> dict[str, bool]:
    """What the current review reads: the text alone, or the page image with it."""
    options = _stored(prescription).get('options')
    options = options if isinstance(options, dict) else {}
    return {'images': options.get('images') is True}


def mark_started(prescription_id: int, run_id: str) -> bool:
    """Record that a queued review is starting; False when it is no longer this prescription's review."""
    with transaction.atomic():
        prescription = Prescription.objects.select_for_update().filter(pk=prescription_id).first()
        review = _stored(prescription) if prescription else {}
        if review.get('run_id') != run_id or review.get('status') != PENDING:
            return False
        prescription.ai_review = {**review, 'started_at': timezone.now().isoformat()}
        prescription.save(update_fields=['ai_review', 'updated_at'])
    return True


def finish(prescription_id: int, run_id: str, outcome: dict[str, Any]) -> bool:
    """Store a finished review's result, unless it was replaced or stopped while it ran."""
    with transaction.atomic():
        prescription = Prescription.objects.select_for_update().filter(pk=prescription_id).first()
        review = _stored(prescription) if prescription else {}
        if review.get('run_id') != run_id or review.get('status') != PENDING:
            return False
        stored = {**review, **outcome, 'reviewed_at': timezone.now().isoformat()}
        if outcome.get('status') == COMPLETED:
            # Suggestions the user dismissed before are not raised again.
            medications = {row.id: row for row in prescription.medications.all()}
            dismissed = set(review.get('dismissed') or [])
            kept = [
                item for item in outcome.get('suggestions') or []
                if suggestion_key(item, medications) not in dismissed
            ]
            stored['suggestions'] = [{**item, 'id': index + 1} for index, item in enumerate(kept)]
            stored['applied'] = []
        prescription.ai_review = stored
        prescription.save(update_fields=['ai_review', 'updated_at'])
    return True


def failed_review(error: str) -> dict[str, Any]:
    return {'status': FAILED, 'error': str(error)[:1000]}


def stop_review(prescription: Prescription) -> str | None:
    """Discard a queued or running review; returns its run id so the task can be revoked."""
    with transaction.atomic():
        locked = Prescription.objects.select_for_update().get(pk=prescription.pk)
        review = _stored(locked)
        if review.get('status') != PENDING:
            return None
        locked.ai_review = review_memory(locked)
        locked.save(update_fields=['ai_review', 'updated_at'])
    prescription.ai_review = locked.ai_review
    return str(review.get('run_id') or '')


def clear_review(prescription: Prescription) -> None:
    """Close the review, keeping which suggestions the user dismissed."""
    prescription.ai_review = review_memory(prescription)
    prescription.save(update_fields=['ai_review', 'updated_at'])


def review_status(prescription: Prescription) -> str:
    review = _stored(prescription)
    status = review.get('status') or ''
    return FAILED if status == PENDING and _expired(review) else status


def _open_suggestions(prescription: Prescription, review: dict[str, Any]) -> list[dict[str, Any]]:
    """Suggestions still worth showing: not applied, and about a medicine that still exists."""
    applied = {item.get('suggestion_id') for item in review.get('applied') or [] if isinstance(item, dict)}
    existing = set(prescription.medications.values_list('id', flat=True))
    open_items = []
    for item in review.get('suggestions') or []:
        if not isinstance(item, dict) or item.get('id') in applied:
            continue
        if item.get('action') != 'add' and item.get('medication_id') not in existing:
            continue
        open_items.append(item)
    return open_items


def visible_review(prescription: Prescription) -> dict[str, Any] | None:
    """The stored review as the prescriptions page should show it now."""
    review = _stored(prescription)
    status = review.get('status')
    if status == PENDING and _expired(review):
        review = {'status': FAILED, 'error': 'The AI review did not finish. Run it again.'}
    elif status == COMPLETED:
        review = {
            **review,
            'suggestions': _open_suggestions(prescription, review),
            'applied': review.get('applied') or [],
        }
    elif status not in (PENDING, FAILED):
        return None
    return {key: value for key, value in review.items() if key not in ('run_id', 'dismissed')}


def dismiss_suggestion(prescription: Prescription, suggestion_id: int) -> None:
    """Drop a suggestion and remember it, so a later review does not raise the same one."""
    with transaction.atomic():
        locked = Prescription.objects.select_for_update().get(pk=prescription.pk)
        review = _stored(locked)
        suggestions = review.get('suggestions') or []
        removed = next(
            (item for item in suggestions if isinstance(item, dict) and item.get('id') == suggestion_id), None
        )
        if removed is None:
            return
        medications = {row.id: row for row in locked.medications.all()}
        key = suggestion_key(removed, medications)
        dismissed = list(review.get('dismissed') or [])
        if key and key not in dismissed:
            dismissed = (dismissed + [key])[-MAX_DISMISSED:]
        locked.ai_review = {
            **review,
            'suggestions': [item for item in suggestions if item is not removed],
            'dismissed': dismissed,
        }
        locked.save(update_fields=['ai_review', 'updated_at'])
    prescription.ai_review = locked.ai_review


def _snapshot(medication: Medication) -> dict[str, str]:
    return {field: getattr(medication, field) or '' for field in FIELDS}


def accept_suggestions(prescription: Prescription, suggestion_ids: list[int]) -> list[int]:
    """Apply these suggestions to the medicines, recording what each one replaced so it can be undone."""
    wanted = set(suggestion_ids)
    if not wanted:
        return []
    with transaction.atomic():
        locked = Prescription.objects.select_for_update().get(pk=prescription.pk)
        review = _stored(locked)
        if review.get('status') != COMPLETED:
            return []
        medications = {row.id: row for row in locked.medications.select_for_update()}
        applied = list(review.get('applied') or [])
        done = {item.get('suggestion_id') for item in applied if isinstance(item, dict)}
        accepted: list[int] = []

        for item in review.get('suggestions') or []:
            if not isinstance(item, dict) or item.get('id') not in wanted or item.get('id') in done:
                continue
            action = item.get('action')
            record: dict[str, Any] = {
                'id': len(applied) + 1,
                'suggestion_id': item['id'],
                'action': action,
                'at': timezone.now().isoformat(),
            }

            if action == 'add':
                medication = Medication.objects.create(prescription=locked, **item['medication'])
                record.update({'medication_id': medication.id, 'after': _snapshot(medication)})
            elif action == 'update':
                medication = medications.get(item.get('medication_id'))
                if medication is None:
                    continue
                record['before'] = _snapshot(medication)
                for field, value in (item.get('changes') or {}).items():
                    if field in FIELDS:
                        setattr(medication, field, value)
                medication.save(update_fields=list(FIELDS))
                record.update({'medication_id': medication.id, 'after': _snapshot(medication)})
            elif action == 'remove':
                medication = medications.get(item.get('medication_id'))
                if medication is None:
                    continue
                record.update({'medication_id': medication.id, 'before': _snapshot(medication)})
                medication.delete()
            else:
                continue

            applied.append(record)
            accepted.append(item['id'])

        if accepted:
            locked.ai_review = {**review, 'applied': applied}
            locked.save(update_fields=['ai_review', 'updated_at'])
    prescription.refresh_from_db()
    return accepted


def undo_applied(prescription: Prescription, applied_id: int) -> None:
    """Put back what an accepted suggestion changed."""
    with transaction.atomic():
        locked = Prescription.objects.select_for_update().get(pk=prescription.pk)
        review = _stored(locked)
        record = next(
            (item for item in review.get('applied') or []
             if isinstance(item, dict) and item.get('id') == applied_id),
            None,
        )
        if record is None:
            return

        action = record.get('action')
        if action == 'add':
            Medication.objects.filter(prescription=locked, pk=record.get('medication_id')).delete()
        elif action == 'update':
            medication = Medication.objects.filter(prescription=locked, pk=record.get('medication_id')).first()
            if medication is not None:
                for field, value in (record.get('before') or {}).items():
                    if field in FIELDS:
                        setattr(medication, field, value)
                medication.save(update_fields=list(FIELDS))
        elif action == 'remove':
            # The row is gone, so it comes back as a new one with the values it had.
            Medication.objects.create(prescription=locked, **{
                field: (record.get('before') or {}).get(field, '') for field in FIELDS
            })

        locked.ai_review = {
            **review,
            'applied': [item for item in review.get('applied') or [] if item is not record],
        }
        locked.save(update_fields=['ai_review', 'updated_at'])
    prescription.refresh_from_db()
