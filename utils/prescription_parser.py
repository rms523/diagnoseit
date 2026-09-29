"""Reading a prescription: its text first, then the medicines printed on it.

A prescription arrives as a PDF from a clinic portal or as a photograph taken on a phone, so the text is
found two ways: a PDF's own text layer when it has one, and the report OCR model when it does not — which
is every photograph and every scan. The medicines are then read out of that text by the report review
model, because a prescription is prose, not a table: "Tab. Amoxicillin 500mg 1-0-1 x 5 days" is one row
to a reader and several to a regular expression. Where no model is configured the older pattern matching
still runs, so an upload always produces something.
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any

from ai_settings.client import chat_json, parse_json_object
from ai_settings.services import DEFAULT_TEMPERATURES, ROLE_REPORT_REVIEW, get_ai_config

logger = logging.getLogger(__name__)

# A PDF with less text than this is treated as a scan and read by OCR: a page of prose has far more,
# while a scanned page often carries a stray header or a barcode's worth of characters.
MIN_PDF_TEXT_CHARS = 120
# Text sent to the model. A prescription is short; this is a guard against a runaway OCR result.
MAX_TEXT_CHARS = 20_000
MAX_MEDICATIONS = 60
FIELD_LIMITS = {
    'medication_name': 200, 'dosage': 100, 'frequency': 100, 'duration': 100, 'instructions': 2000,
}

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.gif', '.heic', '.heif')

# A vision model charges for an image by its area, so a phone photo at 4000px on its longest edge costs
# several times what the same sheet costs at 1600px, and it reads no better. Rendered PDF pages are capped
# too: at 200 dpi an A4 page is about 2340px tall, taller than a prescription needs to be legible.
MAX_IMAGE_EDGE = int(os.getenv('PRESCRIPTION_OCR_MAX_EDGE', '1600'))
# One prescription's text is a few hundred tokens. Without a bound, a model that starts repeating itself
# writes until it hits the OCR setting's limit, which is minutes of decoding for a single sheet.
OCR_REPLY_TOKENS = int(os.getenv('PRESCRIPTION_OCR_MAX_TOKENS', '1500'))

SYSTEM_PROMPT = (
    "You read the medicines off a prescription. Reply with a JSON object only."
)

INSTRUCTIONS = """The prescription as text:
{text}

List every medicine prescribed, in the order printed.
- Keep the name as printed, without the form prefix ("Tab.", "Cap.", "Syp."). Do not correct spelling and
  do not add a medicine that is not printed.
- dosage is the strength ("500 mg", "10 ml"). frequency is how often ("twice daily", "1-0-1").
  duration is how long ("5 days", "1 month"). instructions is any remaining direction ("after food").
- Use "" for a field the prescription does not give. Never guess a dose.
- Ignore the doctor, the clinic, the patient's details, diagnoses, tests advised, and follow-up dates.

Reply as {{"medications": [{{"medication_name": "...", "dosage": "...", "frequency": "...", "duration": "...", "instructions": "..."}}]}}"""


class PrescriptionReadError(Exception):
    """The prescription's text could not be read at all."""


def is_image(filename: str) -> bool:
    return str(filename or '').lower().endswith(IMAGE_EXTENSIONS)


def _png_bytes(image_bytes: bytes) -> bytes:
    """An uploaded image as PNG, turned upright and scaled down to what the OCR model needs."""
    from PIL import Image, ImageOps
    from utils.vlm_pdf_parser import limit_image_size

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            # A photo carries its rotation as a tag; a mode such as CMYK or P cannot be saved as PNG as-is.
            upright = ImageOps.exif_transpose(image)
            buffer = io.BytesIO()
            upright.convert('RGB').save(buffer, format='PNG')
    except Exception as exc:
        raise PrescriptionReadError('This image could not be opened.') from exc
    return limit_image_size(buffer.getvalue(), MAX_IMAGE_EDGE)


def _pdf_text(pdf_bytes: bytes) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return '\n'.join((page.extract_text() or '') for page in pdf.pages).strip()
    except Exception as exc:
        logger.debug('Could not read the prescription PDF text layer: %s', exc)
        return ''


def _page_count(pdf_bytes: bytes) -> int:
    from pypdfium2 import PdfDocument

    try:
        document = PdfDocument(pdf_bytes)
    except Exception as exc:
        raise PrescriptionReadError(
            'This PDF could not be opened. It may be damaged, or only part of it was uploaded.'
        ) from exc
    try:
        pages = len(document)
    finally:
        document.close()
    if pages == 0:
        raise PrescriptionReadError('This PDF has no pages.')
    return pages


def _ocr_pdf(pdf_bytes: bytes) -> str:
    from utils.vlm_pdf_parser import limit_image_size, read_pages, transcribe_page

    def read(page_png: bytes) -> str:
        return transcribe_page(limit_image_size(page_png, MAX_IMAGE_EDGE), max_tokens=OCR_REPLY_TOKENS)

    pages = []
    for page, text, error in read_pages(pdf_bytes, _page_count(pdf_bytes), read):
        if error is not None:
            raise PrescriptionReadError(
                f'The prescription OCR model could not read page {page + 1} ({type(error).__name__}).'
            ) from error
        pages.append(text or '')
    return '\n'.join(pages).strip()


def read_text(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """The prescription's text and where it came from: 'pdf', 'ocr', or 'photo'."""
    from utils.vlm_pdf_parser import _ocr_config, transcribe_page

    if is_image(filename):
        config = _ocr_config()
        if not config.is_configured:
            raise PrescriptionReadError(
                'Reading a photographed prescription needs the report OCR model. Set it up in AI settings.'
            )
        try:
            text = transcribe_page(_png_bytes(file_bytes), max_tokens=OCR_REPLY_TOKENS).strip()
        except PrescriptionReadError:
            raise
        except Exception as exc:
            # Naming the server and the failure is what lets someone fix a wrong URL or a stopped model.
            raise PrescriptionReadError(
                f'The report OCR model at {config.api_base or config.base_url} could not read this photo '
                f'({type(exc).__name__}). Check the OCR server in AI settings.'
            ) from exc
        if not text:
            raise PrescriptionReadError('The report OCR model read no text in this photo.')
        return text, 'photo'

    text = _pdf_text(file_bytes)
    if len(text) >= MIN_PDF_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS], 'pdf'

    # A scan has no usable text layer, so the pages are read as images.
    if not _ocr_config().is_configured:
        if text:
            return text, 'pdf'
        raise PrescriptionReadError(
            'This PDF has no text to read. Set up the report OCR model in AI settings to read a scan.'
        )
    ocr_text = _ocr_pdf(file_bytes)
    if not ocr_text and not text:
        raise PrescriptionReadError('No text could be read from this prescription.')
    return (ocr_text or text)[:MAX_TEXT_CHARS], 'ocr'


def _clean(medication: Any) -> dict[str, str] | None:
    """One medicine from the model, trimmed to the fields and lengths the database holds."""
    if not isinstance(medication, dict):
        return None
    name = str(medication.get('medication_name') or '').strip()[:FIELD_LIMITS['medication_name']]
    if not name:
        return None
    return {
        'medication_name': name,
        **{
            field: str(medication.get(field) or '').strip()[:limit]
            for field, limit in FIELD_LIMITS.items()
            if field != 'medication_name'
        },
    }


def extract_medications(text: str) -> tuple[list[dict[str, str]], str]:
    """The medicines in this text, and how they were read: 'ai' or 'patterns'."""
    if not text.strip():
        return [], 'patterns'

    config = get_ai_config(ROLE_REPORT_REVIEW)
    if config.is_configured:
        try:
            reply = chat_json(
                config,
                [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': INSTRUCTIONS.format(text=text[:MAX_TEXT_CHARS])},
                ],
                max_tokens=max(config.max_tokens, 2000),
                temperature=config.temperature_or(DEFAULT_TEMPERATURES[ROLE_REPORT_REVIEW]),
            )
            payload = parse_json_object(reply)
            items = payload.get('medications')
            medications = [_clean(item) for item in items] if isinstance(items, list) else []
            found = [item for item in medications if item][:MAX_MEDICATIONS]
            if found:
                return found, 'ai'
            logger.info('The review model read no medicines from this prescription; falling back to patterns.')
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning('The review model did not return usable medicines: %s', exc)
        except Exception as exc:
            logger.warning('Reading medicines with the review model failed: %s', exc)

    # No model, or the model gave nothing usable: the older pattern matching still finds obvious rows.
    from utils.pdf_parser import MedicalPDFParser

    legacy = MedicalPDFParser().extract_prescription_data(text).get('medications') or []
    return [item for item in (_clean(row) for row in legacy) if item][:MAX_MEDICATIONS], 'patterns'


def parse_prescription(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Everything read from one prescription file, for Prescription.parsed_data."""
    text, source = read_text(file_bytes, filename)
    medications, read_by = extract_medications(text)
    return {
        'text': text,
        'text_source': source,
        'medications': medications,
        'read_by': read_by,
        'parsed_successfully': bool(medications),
    }


def max_upload_bytes() -> int:
    try:
        return int(os.getenv('PRESCRIPTION_MAX_UPLOAD_BYTES', str(100 * 1024 * 1024)))
    except ValueError:
        return 100 * 1024 * 1024
