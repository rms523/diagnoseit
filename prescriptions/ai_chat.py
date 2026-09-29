"""Asking the AI about one prescription: what the medicines are for, answered from that prescription alone.

The shared machinery — the rules, the redaction, the stored transcript, the model call — lives in
`utils.ai_chat`; this module supplies what is particular to a prescription: its medicines and its text.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.ai_chat import CLOSING_RULES, chat_view, document_text
from utils.report_redaction import Redactor

from .models import Prescription

SYSTEM_PROMPT = (
    "You help someone understand their own prescription. You are given that one prescription and nothing "
    "else.\n"
    + CLOSING_RULES
    + "\n- Explain in plain language what each medicine is generally for, how the prescription says to take "
    "it, and what the common cautions are. Never suggest a different medicine, a different dose, or "
    "stopping one: only their prescriber can change a prescription."
)


def prescription_context(prescription: Prescription) -> str:
    """The prescription as the model sees it: its medicines and its text, redacted."""
    redactor = Redactor([prescription.user.first_name, prescription.user.last_name])
    lines = ['Prescription']
    if prescription.prescription_date:
        lines.append(f"Date: {prescription.prescription_date.isoformat()}")
    if prescription.hospital_clinic:
        lines.append(f"Clinic: {redactor.line(prescription.hospital_clinic)}")

    medications = list(prescription.medications.all())
    if medications:
        lines.append("")
        lines.append("Medicines, one per line as name | dosage | frequency | duration | instructions:")
        for medication in medications:
            fields = [
                redactor.line(medication.medication_name or ''),
                medication.dosage or '-',
                medication.frequency or '-',
                medication.duration or '-',
                redactor.line(medication.instructions or '') or '-',
            ]
            lines.append(' | '.join(field or '-' for field in fields))
    else:
        lines.append("")
        lines.append("No medicines were read from this prescription.")

    data = prescription.parsed_data if isinstance(prescription.parsed_data, dict) else {}
    text = document_text(data.get('text'), redactor)
    if text:
        lines.append("")
        lines.append("The prescription as printed, for the directions the medicines above do not carry:")
        lines.append(text)
    return '\n'.join(lines)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def prescription_chat(request, prescription_id: int):
    """GET: the conversation so far. POST {question}: ask about it. DELETE: start over."""
    prescription = Prescription.objects.filter(pk=prescription_id, user=request.user).first()
    if prescription is None:
        return Response({'error': 'Prescription not found.'}, status=status.HTTP_404_NOT_FOUND)
    return chat_view(
        request,
        prescription,
        field='ai_chat',
        system_prompt=SYSTEM_PROMPT,
        context=lambda: f"The prescription:\n\n{prescription_context(prescription)}",
        subject='prescription',
    )
