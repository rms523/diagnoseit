"""Checking the medicines a prescription was read as, against the prescription itself.

Reading a photographed or handwritten prescription goes wrong in ways a lab report's does not: a name in a
script the model half-recognises, a strength that belongs to the line above, a medicine missed at the edge
of the page, one invented out of a heading. This asks the review model to compare what was stored against
the original and say what is wrong.

The original goes as text, and as the page image too when the caller asks for it — which the page offers
as a checkbox, ticked by default for a photo or a scan, since checking OCR text against itself would
confirm its errors rather than catch them. The patient's name, phone numbers, and emails are replaced
first, as everywhere else the model is used.

Nothing here applies anything. A prescription's suggestions are always the user's to accept: a dose changed
without them is a harm no confidence score justifies.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any

from ai_settings.client import chat_json, parse_json_object
from ai_settings.services import DEFAULT_TEMPERATURES, ROLE_REPORT_REVIEW, AIConfig
from utils.prescription_parser import FIELD_LIMITS, MAX_IMAGE_EDGE, MAX_TEXT_CHARS, is_image
from utils.report_redaction import Redactor

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 40
EDITABLE_FIELDS = ('medication_name', 'dosage', 'frequency', 'duration', 'instructions')

SYSTEM_PROMPT = (
    "You check a list of medicines against the prescription it was read from. Reply with a JSON object only."
)

INSTRUCTIONS = """The prescription as read:
{text}

The medicines currently stored, as JSON:
{medications}

Compare them with the prescription and report only what is wrong.
- update: a stored medicine whose name, dosage, frequency, duration, or instructions does not match the
  prescription. Give only the fields that should change, with the value as the prescription prints it.
- add: a medicine on the prescription that is missing from the list.
- remove: a stored row that is not a prescribed medicine — a heading, the doctor, a diagnosis, advice.
- Do not suggest a change you cannot see in the prescription, and never invent or adjust a dose. A
  difference only in capitals, spacing, or punctuation is not worth reporting.
- Reply with an empty list when the stored medicines match.

Reply as {{"verdict": "correct" or "changes", "suggestions": [
  {{"action": "update", "medication_id": 1, "changes": {{"dosage": "500 mg"}}, "reason": "at most 15 words"}},
  {{"action": "add", "medication": {{"medication_name": "...", "dosage": "...", "frequency": "...", "duration": "...", "instructions": "..."}}, "reason": "..."}},
  {{"action": "remove", "medication_id": 2, "reason": "..."}}
]}}"""

IMAGE_NOTE = (
    "The prescription image is attached. The text above was read from it by OCR and may itself be wrong, so "
    "trust the image where they disagree."
)

_IGNORED_CHARS_RE = re.compile(r"[\s,;:()\[\]'\"./-]+")


class PrescriptionReviewError(Exception):
    """The review could not be carried out."""


def _same_text(new: Any, old: Any) -> bool:
    """Whether two values differ only in capitals, spacing, or punctuation."""
    left, right = (_IGNORED_CHARS_RE.sub('', str(value or '').casefold()) for value in (new, old))
    return left == right


def _page_image(file_bytes: bytes, filename: str) -> bytes | None:
    """The prescription as one PNG the model can look at: the photo, or the first page of the PDF."""
    from utils.vlm_pdf_parser import limit_image_size

    try:
        if is_image(filename):
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(file_bytes)) as image:
                buffer = io.BytesIO()
                ImageOps.exif_transpose(image).convert('RGB').save(buffer, format='PNG')
            return limit_image_size(buffer.getvalue(), MAX_IMAGE_EDGE)

        from utils.vlm_pdf_parser import _render_page_to_png

        return limit_image_size(_render_page_to_png(file_bytes, 0), MAX_IMAGE_EDGE)
    except Exception as exc:
        logger.warning('Could not prepare the prescription image for review: %s', exc)
        return None


def _stored_medications(medications) -> list[dict[str, Any]]:
    return [
        {'medication_id': medication.id,
         **{field: getattr(medication, field) or '' for field in EDITABLE_FIELDS}}
        for medication in medications
    ]


def _clean_changes(raw: Any, current: dict[str, Any]) -> dict[str, str]:
    """The fields this suggestion really changes, trimmed to what the database holds."""
    if not isinstance(raw, dict):
        return {}
    changes: dict[str, str] = {}
    for field in EDITABLE_FIELDS:
        if field not in raw:
            continue
        value = str(raw.get(field) or '').strip()[:FIELD_LIMITS[field]]
        # A change to nothing, or one that only moves punctuation about, is noise.
        if field == 'medication_name' and not value:
            continue
        if _same_text(value, current.get(field)):
            continue
        changes[field] = value
    return changes


def _clean_medication(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get('medication_name') or '').strip()[:FIELD_LIMITS['medication_name']]
    if not name:
        return None
    return {
        'medication_name': name,
        **{
            field: str(raw.get(field) or '').strip()[:FIELD_LIMITS[field]]
            for field in EDITABLE_FIELDS if field != 'medication_name'
        },
    }


def clean_suggestions(items: Any, stored: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """The model's suggestions, keeping only those that name a real row and really change something."""
    cleaned: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or len(cleaned) >= MAX_SUGGESTIONS:
            continue
        action = str(item.get('action') or '').strip().lower()
        reason = str(item.get('reason') or '')[:200]

        if action == 'add':
            medication = _clean_medication(item.get('medication'))
            # A medicine already stored under that name is not missing.
            if medication and not any(
                _same_text(medication['medication_name'], row['medication_name']) for row in stored.values()
            ):
                cleaned.append({'action': 'add', 'medication': medication, 'reason': reason})
            continue

        try:
            medication_id = int(item.get('medication_id'))
        except (TypeError, ValueError):
            continue
        current = stored.get(medication_id)
        if current is None:
            continue

        if action == 'remove':
            cleaned.append({'action': 'remove', 'medication_id': medication_id, 'reason': reason})
        elif action == 'update':
            changes = _clean_changes(item.get('changes'), current)
            if changes:
                cleaned.append({
                    'action': 'update', 'medication_id': medication_id, 'changes': changes, 'reason': reason,
                })
    return cleaned


def review_prescription(
    prescription, config: AIConfig, file_bytes: bytes | None = None, *, images: bool = False
) -> dict[str, Any]:
    """Ask the review model what is wrong with this prescription's medicines.

    images sends the original page as a picture alongside the text. The caller decides: for a photo or a
    scan the image is what the text should be checked against, and for a PDF whose text layer is already
    exact it is a cost with little to add.
    """
    if not config.is_configured:
        raise PrescriptionReviewError('Set up the report review model in AI settings to review a prescription.')

    data = prescription.parsed_data if isinstance(prescription.parsed_data, dict) else {}
    redactor = Redactor([prescription.user.first_name, prescription.user.last_name])
    text = '\n'.join(redactor.line(line) for line in str(data.get('text') or '').splitlines() if line.strip())
    medications = list(prescription.medications.all())
    if not text and not medications:
        raise PrescriptionReviewError('There is nothing to review: this prescription has no text and no medicines.')

    stored = {row['medication_id']: row for row in _stored_medications(medications)}
    instructions = INSTRUCTIONS.format(
        text=text[:MAX_TEXT_CHARS] or '(no text was read)',
        medications=json.dumps(list(stored.values()), ensure_ascii=False, indent=1),
    )

    image = _page_image(file_bytes, prescription.file.name) if images and file_bytes else None
    if image:
        content: Any = [
            {'type': 'text', 'text': f'{instructions}\n\n{IMAGE_NOTE}'},
            {'type': 'image_url',
             'image_url': {'url': f'data:image/png;base64,{base64.b64encode(image).decode()}'}},
        ]
    else:
        content = instructions

    try:
        reply = chat_json(
            config,
            [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': content}],
            max_tokens=max(config.max_tokens, 2000),
            temperature=config.temperature_or(DEFAULT_TEMPERATURES[ROLE_REPORT_REVIEW]),
        )
        payload = parse_json_object(reply)
    except ValueError as exc:
        raise PrescriptionReviewError('The review model did not return valid JSON.') from exc
    except Exception as exc:
        raise PrescriptionReviewError(
            f'The review model did not respond ({type(exc).__name__}).'
        ) from exc

    suggestions = clean_suggestions(payload.get('suggestions'), stored)
    return {
        'verdict': 'changes' if suggestions else 'correct',
        'suggestions': suggestions,
        'input_mode': 'text_image' if image else 'text',
        'model': config.model,
    }
