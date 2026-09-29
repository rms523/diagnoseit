"""A patient's health history as one dated timeline, for AI diagnosis that follows a condition over time.

Lab results, symptoms (when each began, changed, and ended), prescriptions, and earlier AI assessments are
listed oldest first under the date they happened, so the model can relate what changed to when. The
account holder's name, phone numbers, and email addresses are redacted from free text; doctor names and
report file names are left out. When the history is longer than the input budget, the earliest dates are
left out and the timeline says so.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from django.utils import timezone

from medical_reports.models import MedicalReport
from prescriptions.models import Prescription
from symptoms.models import Symptom
from utils.llm_service import PLACEHOLDER_CONDITION
from utils.report_redaction import Redactor

from .models import Diagnosis

PERIOD_DAYS: dict[str, int | None] = {'3m': 91, '6m': 182, '1y': 365, '2y': 730, 'all': None}
DEFAULT_PERIOD = '1y'
MAX_TIMELINE_CHARS = 60_000  # about 15,000 tokens of history

SEVERITY = dict(Symptom.SEVERITY_CHOICES)
DURATION = dict(Symptom.DURATION_CHOICES)


@dataclass
class Timeline:
    text: str
    since: date | None
    until: date
    counts: dict[str, int] = field(default_factory=dict)
    omitted_dates: int = 0


def build_timeline(user, period: str = DEFAULT_PERIOD, today: date | None = None) -> Timeline:
    """The user's history for the period (that many days back from today, or everything) as timeline text."""
    today = today or timezone.localdate()
    days = PERIOD_DAYS[period]
    since = today - timedelta(days=days) if days else None
    clean = _cleaner(user)
    events: dict[date, list[str]] = defaultdict(list)
    counts: Counter = Counter()

    def in_period(day: date) -> bool:
        return since is None or day >= since

    for symptom in Symptom.objects.filter(user=user).prefetch_related('logs').order_by('onset_date', 'id'):
        onset = _day(symptom.onset_date)
        ended = _day(symptom.end_date) if symptom.end_date else None
        if in_period(onset):
            events[onset].append(f"  Symptom began: {_symptom_details(symptom, clean)}")
        elif symptom.is_ongoing or (ended is not None and in_period(ended)):
            # Began before the period and was still going on during it.
            events[since].append(f"  Symptom ongoing since {onset.isoformat()}: {_symptom_details(symptom, clean)}")
        else:
            continue
        counts['symptoms'] += 1
        if ended is not None and in_period(ended):
            events[ended].append(f"  Symptom ended: {clean(symptom.description)}")
        for log in sorted(symptom.logs.all(), key=lambda entry: entry.logged_at):
            logged = _day(log.logged_at)
            if not in_period(logged):
                continue
            severity = str(SEVERITY.get(log.severity, log.severity)).lower()
            notes = f". Notes: {clean(log.notes)}" if log.notes.strip() else ''
            events[logged].append(f"  Symptom update: {clean(symptom.description)} is {severity}{notes}")
            counts['symptom_updates'] += 1

    reports = MedicalReport.objects.filter(user=user).prefetch_related('test_results').order_by('report_date', 'id')
    if since is not None:
        reports = reports.filter(report_date__gte=since)
    for report in reports:
        results = sorted(report.test_results.all(), key=lambda result: result.id)
        if not results or report.report_date is None:
            continue
        source = f" from {clean(report.lab_name)}" if (report.lab_name or '').strip() else ''
        lines = [f"  Lab results{source}:"] + [f"    - {_result_line(result, clean)}" for result in results]
        events[report.report_date].append('\n'.join(lines))
        counts['reports'] += 1
        counts['results'] += len(results)

    prescriptions = Prescription.objects.filter(user=user).prefetch_related('medications').order_by('prescription_date', 'id')
    if since is not None:
        prescriptions = prescriptions.filter(prescription_date__gte=since)
    for prescription in prescriptions:
        medications = list(prescription.medications.all())
        lines = ["  Prescription:"]
        lines += [f"    - {_medication_line(medication, clean)}" for medication in medications] or [
            "    - No medicines were recorded from it"
        ]
        if prescription.notes.strip():
            lines.append(f"    Notes: {clean(prescription.notes)}")
        events[prescription.prescription_date].append('\n'.join(lines))
        counts['prescriptions'] += 1
        counts['medications'] += len(medications)

    for diagnosis in Diagnosis.objects.filter(user=user).exclude(condition_name=PLACEHOLDER_CONDITION).order_by('created_at'):
        day = _day(diagnosis.created_at)
        if in_period(day):
            events[day].append(
                f"  Earlier AI assessment, not a doctor's diagnosis: {clean(diagnosis.condition_name)} "
                f"(confidence {diagnosis.confidence_score}/5)"
            )
            counts['assessments'] += 1

    blocks = [f"{day.isoformat()}\n" + '\n'.join(events[day]) for day in sorted(events)]
    total = sum(len(block) + 2 for block in blocks)
    omitted = 0
    while len(blocks) > 1 and total > MAX_TIMELINE_CHARS:
        total -= len(blocks.pop(0)) + 2
        omitted += 1

    header = f"Health timeline from {since.isoformat() if since else 'the first record'} to {today.isoformat()}, oldest first."
    if omitted:
        header += f" The {omitted} earliest date{'s are' if omitted != 1 else ' is'} left out to fit the model's input limit."
    body = '\n\n'.join(blocks) if blocks else 'Nothing was recorded in this period.'
    return Timeline(text=f"{header}\n\n{body}", since=since, until=today, counts=dict(counts), omitted_dates=omitted)


def _cleaner(user) -> Callable[[object], str]:
    """Free text on one line, with the account holder's name and contact details redacted."""
    redactor = Redactor([user.first_name, user.last_name])
    return lambda text: redactor.line(' '.join(str(text or '').split()))


def _day(moment: datetime) -> date:
    return timezone.localtime(moment).date() if timezone.is_aware(moment) else moment.date()


def _symptom_details(symptom: Symptom, clean) -> str:
    parts = [
        clean(symptom.description),
        str(SEVERITY.get(symptom.severity, symptom.severity)).lower(),
        str(DURATION.get(symptom.duration, symptom.duration)).lower(),
    ]
    if symptom.body_part.strip():
        parts.append(f"body part: {clean(symptom.body_part)}")
    if symptom.is_ongoing and not symptom.end_date:
        parts.append('still ongoing')
    text = ', '.join(parts)
    if symptom.notes.strip():
        text += f". Notes: {clean(symptom.notes)}"
    return text


def _result_line(result, clean) -> str:
    line = f"{clean(result.test_name)}: {clean(result.value)}"
    if result.unit:
        line += f" {result.unit}"
    if result.reference_range:
        line += f" (reference {clean(result.reference_range)})"
    if result.status:
        line += f" {result.status}"
    return line


def _medication_line(medication, clean) -> str:
    parts = [clean(medication.medication_name)]
    parts += [clean(value) for value in (medication.dosage, medication.frequency) if value.strip()]
    if medication.duration.strip():
        parts.append(f"for {clean(medication.duration)}")
    line = ', '.join(parts)
    if medication.instructions.strip():
        line += f". Instructions: {clean(medication.instructions)}"
    return line
