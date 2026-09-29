"""Asking the AI about one report: what its results mean, answered from that report alone.

The shared machinery — the rules, the redaction, the stored transcript, the model call — lives in
`utils.ai_chat`; this module supplies what is particular to a lab report: its results table and its text.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.ai_chat import (
    CLOSING_RULES,
    HISTORY_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_STORED_MESSAGES,
    chat_state as _chat_state,
    chat_view,
    document_text,
    build_messages as _build_messages,
    save_turn as _save_turn,
)
from utils.report_redaction import Redactor

from .models import MedicalReport

__all__ = [
    'HISTORY_MESSAGES', 'MAX_QUESTION_CHARS', 'MAX_STORED_MESSAGES',
    'SYSTEM_PROMPT', 'build_messages', 'chat_state', 'report_chat', 'report_context', 'save_turn',
]

SYSTEM_PROMPT = (
    "You help someone understand their own lab report. You are given that one report and nothing else.\n"
    + CLOSING_RULES
    + "\n- Explain in plain language what a test measures and what a result outside its reference range "
    "can mean, and point out which results are outside their range. A lab result is not a diagnosis."
)


def chat_state(report: MedicalReport) -> dict:
    return _chat_state(report.ai_chat)


def report_context(report: MedicalReport) -> str:
    """The report as the model sees it: what it is, its results, and its text, all redacted."""
    redactor = Redactor([report.user.first_name, report.user.last_name])
    lines = [f"Report: {redactor.line(report.title or 'Untitled')}"]
    if report.report_date:
        lines.append(f"Date: {report.report_date.isoformat()}")
    if report.lab_name:
        lines.append(f"Laboratory: {redactor.line(report.lab_name)}")

    results = list(report.test_results.all().order_by('test_name'))
    if results:
        lines.append("")
        lines.append("Results, one per line as name | value | unit | reference range | status:")
        for result in results:
            fields = [
                redactor.line(result.test_name or ''),
                redactor.line(result.value or ''),
                result.unit or '-',
                result.reference_range or '-',
                result.status or '-',
            ]
            lines.append(' | '.join(field or '-' for field in fields))
    else:
        lines.append("")
        lines.append("No results were read from this report.")

    data = report.parsed_data if isinstance(report.parsed_data, dict) else {}
    text = document_text(data.get('text'), redactor)
    if text:
        lines.append("")
        lines.append("The report as printed, for the notes and comments the results do not carry:")
        lines.append(text)
    return '\n'.join(lines)


def build_messages(report: MedicalReport, question: str) -> list[dict[str, str]]:
    return _build_messages(
        SYSTEM_PROMPT, f"The report:\n\n{report_context(report)}", chat_state(report)['messages'], question
    )


def save_turn(report: MedicalReport, question: str, answer: str) -> dict:
    return _save_turn(report, 'ai_chat', question, answer)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def report_chat(request, report_id: int):
    """GET: the conversation so far. POST {question}: ask about this report. DELETE: start over."""
    report = MedicalReport.objects.filter(pk=report_id, user=request.user).first()
    if report is None:
        return Response({'error': 'Report not found.'}, status=status.HTTP_404_NOT_FOUND)
    return chat_view(
        request,
        report,
        field='ai_chat',
        system_prompt=SYSTEM_PROMPT,
        context=lambda: f"The report:\n\n{report_context(report)}",
        subject='report',
    )
