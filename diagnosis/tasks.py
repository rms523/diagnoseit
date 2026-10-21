"""Writing an AI diagnosis in the background, the way a report is reviewed.

The generate request returns at once with a PENDING diagnosis and the page polls it while this runs. A
differential from a local reasoning model can take far longer than the 300 s a web request is allowed, so the
model is called here, streamed, with the timeout setting applied in full.
"""

from __future__ import annotations

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai_settings.client import StreamProgress
from utils.llm_service import LLMError, LLMService

from .models import Diagnosis, DiagnosisHistory

logger = logging.getLogger(__name__)

# Stop a minute before the worker's hard time limit so the failure can still be recorded.
DIAGNOSIS_SOFT_TIME_LIMIT = max(60, getattr(settings, "CELERY_TASK_TIME_LIMIT", 1800) - 60)
# The page polls every few seconds, so progress is saved no more often than this.
PROGRESS_INTERVAL_SECONDS = 2.0
# Shown by app builds that only know a finished diagnosis.
IN_PROGRESS_NAME = 'AI diagnosis in progress'
FAILED_NAME = 'AI diagnosis failed'


class DiagnosisStopped(Exception):
    """The diagnosis was deleted while the model was writing it."""


class ProgressReporter:
    """Saves how far the model's streamed reply has got, and stops the stream once the diagnosis is deleted."""

    def __init__(self, diagnosis_id: int, started_at: str):
        self.diagnosis_id = diagnosis_id
        self.started_at = started_at
        self.phase = 'waiting'
        self.saved_at = 0.0

    def __call__(self, progress: StreamProgress) -> None:
        now = time.monotonic()
        if progress.phase == self.phase and now - self.saved_at < PROGRESS_INTERVAL_SECONDS:
            return
        self.phase, self.saved_at = progress.phase, now
        if not self.save(progress):
            raise DiagnosisStopped

    def save(self, progress: StreamProgress) -> bool:
        return bool(Diagnosis.objects.filter(pk=self.diagnosis_id, status=Diagnosis.PROCESSING).update(
            progress={
                'phase': progress.phase,
                'reasoning_tokens': progress.reasoning_tokens,
                'reply_tokens': progress.reply_tokens,
                'started_at': self.started_at,
                'updated_at': timezone.now().isoformat(),
            },
        ))


def _confidence(value) -> int:
    try:
        return min(5, max(1, round(float(value))))
    except (TypeError, ValueError):
        return 3


def _fail(diagnosis_id: int, message: str) -> None:
    Diagnosis.objects.filter(pk=diagnosis_id).update(
        status=Diagnosis.FAILED, condition_name=FAILED_NAME, description=message, error=message,
    )


def _complete(diagnosis_id: int, reply: dict) -> None:
    with transaction.atomic():
        diagnosis = Diagnosis.objects.select_for_update().filter(pk=diagnosis_id).first()
        if diagnosis is None:
            return
        diagnosis.condition_name = str(reply.get('condition_name') or 'Unknown Condition')[:200]
        diagnosis.description = str(reply.get('description') or '')
        diagnosis.confidence_score = _confidence(reply.get('confidence_score'))
        diagnosis.recommendations = str(reply.get('recommendations') or '')
        diagnosis.follow_up_required = bool(reply.get('follow_up_required'))
        diagnosis.follow_up_notes = str(reply.get('follow_up_notes') or '')
        # The differential, and the red flags the earlier code asked the model for and then threw away.
        diagnosis.analysis = reply.get('analysis') or {}
        diagnosis.status = Diagnosis.COMPLETED
        diagnosis.error = ''
        diagnosis.save()
        DiagnosisHistory.objects.create(
            diagnosis=diagnosis,
            condition_name=diagnosis.condition_name,
            description=diagnosis.description,
            confidence_score=diagnosis.confidence_score,
            recommendations=diagnosis.recommendations,
        )


@shared_task(ignore_result=True, queue='ai_review', soft_time_limit=DIAGNOSIS_SOFT_TIME_LIMIT)
def generate_diagnosis_task(diagnosis_id: int, prompt: str) -> None:
    """Ask the AI diagnosis model about a queued diagnosis and store its answer.

    Runs on the review worker, so it reaches the model server one request at a time with report reviews.
    """
    started_at = timezone.now().isoformat()
    reporter = ProgressReporter(diagnosis_id, started_at)
    started = Diagnosis.objects.filter(pk=diagnosis_id, status=Diagnosis.PENDING).update(
        status=Diagnosis.PROCESSING, progress={'phase': 'waiting', 'started_at': started_at},
    )
    if not started:
        logger.info('Diagnosis %s was deleted before it began', diagnosis_id)
        return

    try:
        reply = LLMService().diagnose(prompt, on_progress=reporter)
    except DiagnosisStopped:
        logger.info('Diagnosis %s was deleted while the model was writing it', diagnosis_id)
        return
    except LLMError as exc:
        _fail(diagnosis_id, str(exc))
        return
    except SoftTimeLimitExceeded:
        _fail(diagnosis_id, 'The AI diagnosis took too long and was stopped.')
        return
    except Exception as exc:
        logger.exception('AI diagnosis %s failed', diagnosis_id)
        _fail(diagnosis_id, f'The AI diagnosis failed unexpectedly ({type(exc).__name__}).')
        return
    _complete(diagnosis_id, reply)


def queue_diagnosis(diagnosis_id: int, prompt: str) -> None:
    """Enqueue a diagnosis once the current transaction commits."""

    def dispatch() -> None:
        try:
            generate_diagnosis_task.delay(diagnosis_id, prompt)
        except Exception as exc:
            logger.exception('Could not enqueue diagnosis %s', diagnosis_id)
            _fail(diagnosis_id, f'Could not queue the AI diagnosis: {str(exc)[:500]}')

    transaction.on_commit(dispatch)
