"""AI review of a parsed report: value corrections, missing results, and rows that are not results.

Long reports are reviewed in parts so no request or reply is cut off. Each part sends the rows read
from one stretch of the report with that stretch's text or page images, plus a margin of neighbouring
lines or pages so a result split across the boundary is still readable.

Suggestions are returned for the user to accept or dismiss; nothing is applied here. Each update or
removal records whether the model was shown the text line or page its row was read from (row_seen),
which decides whether it may be applied without the user (medical_reports.ai_review.is_safe_fix).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from ai_settings.client import chat_json, parse_json_object
from ai_settings.services import DEFAULT_TEMPERATURES, ROLE_REPORT_REVIEW, AIConfig
from lab_tests.models import LabTestType
from lab_tests.services import build_test_type_matcher, normalize_test_identifier
from medical_reports.ai_review import COMPLETED, result_identity
from medical_reports.tasks import normalize_test_status
from utils.pdf_text_normalize import normalize_pdf_page_lines
from utils.report_redaction import PreparedText, prepare_report_text, redact_page_image

logger = logging.getLogger(__name__)

PART_TEXT_CHARS = 12_000  # report text reviewed per request, not counting the context margins
CONTEXT_LINES = 15  # neighbouring lines shown before and after a text part
CONTEXT_PAGES = 1  # neighbouring pages sent before and after an image part
OUTPUT_TOKENS_PER_ROW = 30  # reply budget per row, so one part's suggestions fit within max_tokens
MIN_ROWS_PER_PART = 10
MAX_ROWS_PER_PART = 80
MAX_SUGGESTIONS = 100  # per part
FIELD_LIMITS = {'test_name': 200, 'value': 100, 'unit': 50, 'reference_range': 100}
EDITABLE_FIELDS = ('test_name', 'value', 'unit', 'reference_range', 'status')
STATUSES = ('NORMAL', 'HIGH', 'LOW', 'ABNORMAL')

SYSTEM_PROMPT = (
    "You review lab report extractions for accuracy. Compare the extracted rows with the report "
    "and reply with a JSON object only. Most extractions are correct: report only real differences from "
    "what is printed, and never invent values that are not printed in the report."
)

INSTRUCTIONS = """Extracted rows (JSON):
{rows}

Catalog test names:
{catalog}

Personal details in the report are shown as [REDACTED]; ignore them.

Check every row against the report, then reply with:
{{"verdict": "correct" or "needs_changes", "summary": "one sentence", "suggestions": [...]}}

When every row matches the report and no result is missing, reply {{"verdict": "correct", "summary": "...", "suggestions": []}}.
Otherwise use "needs_changes" and list each problem as one of:
- {{"action": "update", "result_id": <id>, "test_name"?, "value"?, "unit"?, "reference_range"?, "status"?, "reason": "..."}}
  when the row's value, unit, or reference range differs from what is printed, the row names a different test than the
  one printed, or the report prints a flag (H, L, High, Low, Abnormal) that differs from the row's status.
  Include only the fields that change.
- {{"action": "add", "test_name": "...", "value": "...", "unit": "...", "reference_range": "...", "status": "...", "reason": "..."}}
  for a result printed in the report but missing from the rows. Use the catalog name when one matches the printed test.
- {{"action": "remove", "result_id": <id>, "reason": "..."}}
  for a row that is not a test result (reference bands, headers, interpretation or method text) or is a duplicate.

Do not suggest:
- another name for the same test: rows may use the catalog name, or other words for the printed name;
- changes only in capitals, spacing, or punctuation;
- a status the report does not print: the app works out status from the reference range;
- a value that is not printed in the report.
status is NORMAL, HIGH, LOW, ABNORMAL, or ""."""

PART_TEXT_NOTE = """This is part {part} of {parts} of a long report. The rows were read from the lines between [REVIEW START] and [REVIEW END].
Lines outside the markers belong to neighbouring parts: use them only to read a result split across the boundary.
Suggest "add" only for results printed between the markers."""

OCR_TEXT_NOTE = (
    "Text read from these pages by OCR. It can contain reading errors: where it disagrees with the images, "
    "trust the images."
)

PART_IMAGES_NOTE = """This is part {part} of {parts} of a long report. The images are pages {first} to {last}.
The rows were read from pages {review_first} to {review_last}; other pages are included only to read a result split across a page break.
Suggest "add" only for results printed on pages {review_first} to {review_last}."""


class ReportReviewError(Exception):
    """A reason the AI review could not complete, safe to show to the user."""


@dataclass(frozen=True)
class RowLocation:
    line: int | None  # index of the normalized text line the row was read from, when known exactly
    page: int | None  # zero-based page index


@dataclass
class ReviewPart:
    start: int  # first line or page whose rows this part reviews
    end: int  # one past the last
    rows: list[dict[str, Any]] = field(default_factory=list)


def review_report(report, config: AIConfig, *, ocr: bool = False, images: bool = False) -> dict[str, Any]:
    """Ask the review model to check a report's extracted rows against the original PDF, one part at a time.

    ocr reads the pages with the report OCR model and reviews against that text instead of the PDF's text
    layer, for PDFs whose embedded text is missing or garbled. images sends the page images whatever the
    review setting says; with ocr as well, each request also carries the OCR text of its pages.
    """
    try:
        with report.file.open('rb') as handle:
            pdf_bytes = handle.read()
    except (OSError, ValueError) as exc:
        raise ReportReviewError('The original report file could not be read.') from exc

    rows = [
        {
            'id': result.id,
            'test_name': result.test_name,
            'value': result.value,
            'unit': result.unit or '',
            'reference_range': result.reference_range or '',
            'status': result.status or '',
        }
        for result in report.test_results.order_by('id')
    ]
    page_lines = _ocr_page_lines(pdf_bytes) if ocr else _extract_page_lines(pdf_bytes)
    lines = [line for page in page_lines for line in page]
    page_of_line = [page for page, page_text in enumerate(page_lines) for _ in page_text]
    page_starts = [0]
    for page_text in page_lines:
        page_starts.append(page_starts[-1] + len(page_text))
    if images:
        input_mode = 'images'
    elif ocr:
        input_mode = 'text'
    else:
        input_mode = _input_mode(config.review_input, '\n'.join(lines))
    locations = locate_rows(rows, report.parsed_data, page_lines)
    # Personal details and boilerplate never reach the model; lines results were read from are always sent.
    prepared = prepare_report_text(
        page_lines,
        _personal_names(report),
        keep={location.line for location in locations.values() if location.line is not None},
    )
    catalog = ', '.join(
        LabTestType.objects.filter(is_active=True).order_by('display_name').values_list('display_name', flat=True)
    )
    row_budget = min(MAX_ROWS_PER_PART, max(MIN_ROWS_PER_PART, config.max_tokens // OUTPUT_TOKENS_PER_ROW))

    if input_mode == 'text':
        if not lines:
            raise ReportReviewError('This PDF has no text layer. Set review input to page images for scanned reports.')
        first_line_of_page: dict[int, int] = {}
        for index, page in enumerate(page_of_line):
            first_line_of_page.setdefault(page, index)
        # A row known only by its page is reviewed with the start of that page.
        planned_lines = {
            row_id: location.line if location.line is not None else first_line_of_page.get(location.page)
            for row_id, location in locations.items()
        }
        parts = plan_parts(
            [len(line) + 1 for line in lines],
            [(row, planned_lines[row['id']]) for row in rows],
            PART_TEXT_CHARS,
            row_budget,
        )

        def build_request(number: int, part: ReviewPart) -> tuple[Any, str | None, int, int, range]:
            window = _window(part, len(parts), len(lines), CONTEXT_LINES)
            content, printed = _text_content(prepared, part, window, number, len(parts), _instructions(part.rows, catalog))
            return content, printed, page_of_line[part.start] + 1, page_of_line[part.end - 1] + 1, window

        def printed_at(row_id: int) -> int | None:
            return locations[row_id].line
    else:
        total_pages = _page_count(pdf_bytes)
        max_images = _max_images_per_request()
        pages_per_part = total_pages if total_pages <= max_images else max(1, max_images - 2 * CONTEXT_PAGES)
        parts = plan_parts(
            [1] * total_pages,
            [(row, locations[row['id']].page) for row in rows],
            pages_per_part,
            row_budget,
        )
        rendered: dict[int, str] = {}

        def build_request(number: int, part: ReviewPart) -> tuple[Any, str | None, int, int, range]:
            window = _window(part, len(parts), total_pages, CONTEXT_PAGES)
            ocr_text = None
            if ocr:
                first, last = (page_starts[min(page, len(page_lines))] for page in (window.start, window.stop))
                ocr_text = '\n'.join(prepared.select(range(first, last))[0])
            content = _image_content(
                pdf_bytes, part, window, number, len(parts), _instructions(part.rows, catalog), rendered,
                prepared.tokens, ocr_text,
            )
            return content, None, part.start + 1, part.end, window

        def printed_at(row_id: int) -> int | None:
            return locations[row_id].page

    catalog_matcher = build_test_type_matcher(report.user_id)
    seen = {result_identity(row['test_name'], row['value'], catalog_matcher) for row in rows}
    summaries: list[str] = []
    suggestions: list[dict[str, Any]] = []
    failed_parts: list[dict[str, Any]] = []
    for number, part in enumerate(parts, start=1):
        content, printed, first_page, last_page, window = build_request(number, part)
        try:
            summary, part_suggestions = _review_part(report, config, content, part.rows, seen, printed)
        except ReportReviewError as exc:
            failed_parts.append({'part': number, 'first_page': first_page, 'last_page': last_page, 'error': str(exc)})
            continue
        for suggestion in part_suggestions:
            if 'result_id' in suggestion:
                printed = printed_at(suggestion['result_id'])
                suggestion['row_seen'] = printed is not None and printed in window
        if summary:
            summaries.append(summary)
        suggestions.extend(part_suggestions)

    if len(failed_parts) == len(parts):
        raise ReportReviewError(failed_parts[0]['error'])
    for index, suggestion in enumerate(suggestions, start=1):
        suggestion['id'] = index

    return {
        'status': COMPLETED,
        'summary': ' '.join(summaries)[:1000],
        'suggestions': suggestions,
        'model': config.model,
        'input_mode': ('images_ocr' if input_mode == 'images' else 'ocr') if ocr else input_mode,
        'parts': len(parts),
        'failed_parts': failed_parts,
        'reviewed_at': timezone.now().isoformat(),
    }


def plan_parts(
    unit_sizes: list[int],
    row_units: list[tuple[dict[str, Any], int | None]],
    unit_budget: int,
    row_budget: int,
) -> list[ReviewPart]:
    """Split lines or pages into consecutive parts within both budgets; every row joins exactly one part.

    A line or page holding more rows than one part may is shared by several parts. Rows whose
    position is unknown fill spare room in the earliest parts.
    """
    rows_at: dict[int, list[dict[str, Any]]] = {}
    unplaced: list[dict[str, Any]] = []
    for row, unit in row_units:
        if unit is not None and 0 <= unit < len(unit_sizes):
            rows_at.setdefault(unit, []).append(row)
        else:
            unplaced.append(row)

    parts: list[ReviewPart] = []
    current = ReviewPart(0, 0)
    size = 0
    for unit, unit_size in enumerate(unit_sizes):
        unit_rows = rows_at.get(unit, [])
        if current.end > current.start and (
            size + unit_size > unit_budget or len(current.rows) + len(unit_rows) > row_budget
        ):
            parts.append(current)
            current = ReviewPart(unit, unit)
            size = 0
        current.end = unit + 1
        size += unit_size
        for row in unit_rows:
            if len(current.rows) >= row_budget:
                parts.append(current)
                current = ReviewPart(unit, unit + 1)
                size = unit_size
            current.rows.append(row)
    parts.append(current)

    for row in unplaced:
        target = next((part for part in parts if len(part.rows) < row_budget), None)
        (target or min(parts, key=lambda part: len(part.rows))).rows.append(row)
    return parts


def locate_rows(
    rows: list[dict[str, Any]], parsed_data: Any, page_lines: list[list[str]]
) -> dict[int, RowLocation]:
    """Find where each row was printed, so it is reviewed alongside the right stretch of the report.

    Uses the line or page the parser recorded for the row, then a parser row with the same name
    and value, then the first text line printing the row's name and value.
    """
    lines = [line for page in page_lines for line in page]
    page_of_line = [page for page, page_text in enumerate(page_lines) for _ in page_text]

    parsed_data = parsed_data if isinstance(parsed_data, dict) else {}
    parsed_rows = [row for row in parsed_data.get('test_results') or [] if isinstance(row, dict)]
    # Parser line numbers count lines of the text it parsed; they only apply if this is that text.
    lines_match = (parsed_data.get('text') or '') == '\n'.join(lines)
    by_result_id = {row['result_id']: row for row in parsed_rows if isinstance(row.get('result_id'), int)}
    by_name_and_value: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in parsed_rows:
        names = {normalize_test_identifier(row.get(key)) for key in ('display_name', 'test_name', 'raw_test_name')}
        for name in names - {''}:
            by_name_and_value.setdefault((name, str(row.get('value', '')).strip()), []).append(row)

    locations: dict[int, RowLocation] = {}
    for row in rows:
        source = by_result_id.get(row['id'])
        if source is None:
            matches = by_name_and_value.get((normalize_test_identifier(row['test_name']), row['value'].strip()), [])
            source = matches[0] if len(matches) == 1 else None

        line = _as_int(source.get('line_number')) if source and lines_match else None
        if line is not None and not 0 <= line < len(lines):
            line = None
        page_number = _as_int(source.get('page_number')) if source else None
        page = page_number - 1 if page_number and page_number > 0 else None

        if line is None:
            line = _find_line(row, lines)
        if page is None and line is not None:
            page = page_of_line[line]
        locations[row['id']] = RowLocation(line, page)
    return locations


def clean_suggestions(
    raw: Any,
    rows: list[dict[str, Any]],
    seen: set[tuple[object, str]] | None = None,
    printed_text: str | None = None,
) -> list[dict[str, Any]]:
    """Keep well-formed suggestions about these rows, trimmed to the model's field limits.

    seen holds results already in the report or suggested by earlier parts; adds matching one are dropped.
    Changes that only differ in capitals, spacing, or punctuation, renames to another name of the same
    catalog test, and cleared statuses are dropped. When printed_text (the report text the model was
    shown) is given, a suggested value it does not contain is dropped with its suggestion.
    """
    if not isinstance(raw, list):
        return []
    rows_by_id = {row['id']: row for row in rows}
    catalog = build_test_type_matcher()
    if seen is None:
        seen = {result_identity(row['test_name'], row['value'], catalog) for row in rows}

    def catalog_name(test_name: str) -> str | None:
        test_type = catalog.match(test_name)
        return test_type.display_name if test_type else None

    cleaned: list[dict[str, Any]] = []
    for item in raw:
        if len(cleaned) >= MAX_SUGGESTIONS:
            break
        if not isinstance(item, dict):
            continue
        action = str(item.get('action') or '').strip().lower()
        reason = _text(item.get('reason'), 300)

        if action in ('update', 'remove'):
            row = rows_by_id.get(_as_int(item.get('result_id')))
            if row is None:
                continue
            if action == 'remove':
                cleaned.append({'action': 'remove', 'result_id': row['id'], 'reason': reason})
                continue
            changes = {}
            for field_name in EDITABLE_FIELDS:
                if field_name not in item:
                    continue
                value = _status(item[field_name]) if field_name == 'status' else _text(item[field_name], FIELD_LIMITS[field_name])
                if field_name == 'test_name' and not value:
                    continue
                if _same_text(value, row[field_name]):
                    continue
                # A status the report does not print is worked out from the reference range, not an error.
                if field_name == 'status' and not value:
                    continue
                if field_name == 'test_name' and _same_test(catalog, value, row[field_name]):
                    continue
                changes[field_name] = value
            if 'value' in changes and printed_text is not None and not _is_printed(changes['value'], printed_text):
                continue
            if changes:
                suggestion = {'action': 'update', 'result_id': row['id'], 'changes': changes, 'reason': reason}
                if 'test_name' in changes:
                    suggestion['catalog_name'] = catalog_name(changes['test_name'])
                cleaned.append(suggestion)

        elif action == 'add':
            test_name = _text(item.get('test_name'), FIELD_LIMITS['test_name'])
            value = _text(item.get('value'), FIELD_LIMITS['value'])
            identity = result_identity(test_name, value, catalog)
            if not test_name or not value or identity in seen:
                continue
            if printed_text is not None and not _is_printed(value, printed_text):
                continue
            seen.add(identity)
            cleaned.append({
                'action': 'add',
                'result': {
                    'test_name': test_name,
                    'value': value,
                    'unit': _text(item.get('unit'), FIELD_LIMITS['unit']),
                    'reference_range': _text(item.get('reference_range'), FIELD_LIMITS['reference_range']),
                    'status': _status(item.get('status')),
                },
                'catalog_name': catalog_name(test_name),
                'reason': reason,
            })
    return cleaned


def _review_part(
    report, config: AIConfig, content: Any, rows: list[dict[str, Any]], seen, printed_text: str | None
) -> tuple[str, list]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]
    temperature = config.temperature_or(DEFAULT_TEMPERATURES[ROLE_REPORT_REVIEW])
    try:
        reply = chat_json(config, messages, max_tokens=config.max_tokens, temperature=temperature)
    except Exception as exc:
        logger.warning("Report review request failed for report %s: %s", report.id, exc)
        raise ReportReviewError(f'The review model did not respond ({type(exc).__name__}).') from exc
    try:
        payload = parse_json_object(reply)
    except ValueError as exc:
        raise ReportReviewError('The review model did not return valid JSON.') from exc
    summary = _text(payload.get('summary'), 500)
    # A "correct" verdict means the model found nothing to change, whatever else the reply lists.
    if str(payload.get('verdict') or '').strip().lower() == 'correct':
        return summary, []
    return summary, clean_suggestions(payload.get('suggestions'), rows, seen, printed_text)


def _instructions(rows: list[dict[str, Any]], catalog: str) -> str:
    return INSTRUCTIONS.format(rows=json.dumps(rows, ensure_ascii=False), catalog=catalog)


def _window(part: ReviewPart, count: int, total: int, margin: int) -> range:
    """The lines or pages sent for a part: all of them for a single part, else the part and its margins."""
    if count == 1:
        return range(total)
    return range(max(0, part.start - margin), min(total, part.end + margin))


def _text_content(
    prepared: PreparedText, part: ReviewPart, window: range, number: int, count: int, instructions: str
) -> tuple[str, str]:
    """The request text for a part, and the report text it shows (to check suggested values against)."""
    if count == 1:
        (shown,) = prepared.select(range(len(prepared.lines)))
        printed = "\n".join(shown)
        return f"Report text:\n{printed}\n\n{instructions}", printed
    before, inside, after = prepared.select(
        range(window.start, part.start), range(part.start, part.end), range(part.end, window.stop)
    )
    excerpt = [*before, '[REVIEW START]', *inside, '[REVIEW END]', *after]
    note = PART_TEXT_NOTE.format(part=number, parts=count)
    printed = "\n".join([*before, *inside, *after])
    return "Report text excerpt:\n" + "\n".join(excerpt) + f"\n\n{instructions}\n\n{note}", printed


def _image_content(
    pdf_bytes: bytes,
    part: ReviewPart,
    window: range,
    number: int,
    count: int,
    instructions: str,
    rendered: dict[int, str],
    redacted_words: set[str],
    ocr_text: str | None = None,
) -> list[dict[str, Any]]:
    text = instructions
    if ocr_text is not None:
        text += f"\n\n{OCR_TEXT_NOTE}\n{ocr_text or '(No text was read from these pages.)'}"
    if count > 1:
        text += "\n\n" + PART_IMAGES_NOTE.format(
            part=number,
            parts=count,
            first=window.start + 1,
            last=window.stop,
            review_first=part.start + 1,
            review_last=part.end,
        )
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for page in window:
        if page not in rendered:
            image = redact_page_image(pdf_bytes, page, _page_image(pdf_bytes, page), redacted_words)
            rendered[page] = base64.b64encode(image).decode('ascii')
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{rendered[page]}"}})
    return content


def _ocr_page_lines(pdf_bytes: bytes) -> list[list[str]]:
    """Each page's lines as read by the report OCR model, normalized like the PDF's own text."""
    from utils.vlm_pdf_parser import _ocr_config, read_pages, transcribe_page

    if not _ocr_config().is_configured:
        raise ReportReviewError('Report OCR is not set up. Set it up in AI settings, or review without OCR.')
    page_texts = []
    for page, text, error in read_pages(pdf_bytes, _page_count(pdf_bytes), transcribe_page):
        if error is not None:
            logger.warning("Report OCR failed on page %s: %s", page + 1, error)
            raise ReportReviewError(f'Report OCR could not read page {page + 1} ({type(error).__name__}).') from error
        page_texts.append(text)
    page_lines = normalize_pdf_page_lines(page_texts)
    if not any(page_lines):
        raise ReportReviewError('Report OCR found no text in this PDF.')
    return page_lines


def _find_line(row: dict[str, Any], lines: list[str]) -> int | None:
    """The first line printing the row's value next to the first word of its name."""
    value = row['value'].strip()
    words = re.findall(r'[a-z]{3,}', row['test_name'].casefold())
    if not value or not words:
        return None
    value_pattern = re.compile(rf'(?<![\w.]){re.escape(value)}(?!\w)', re.IGNORECASE)
    for index, line in enumerate(lines):
        if words[0] in line.casefold() and value_pattern.search(line):
            return index
    return None


def _extract_page_lines(pdf_bytes: bytes) -> list[list[str]]:
    """Normalized text lines per page, counted the same way as the text parser's line numbers."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return normalize_pdf_page_lines([page.extract_text() or "" for page in pdf.pages])
    except Exception as exc:
        logger.debug("Could not extract report text for review: %s", exc)
        return []


def _input_mode(setting: str, text: str) -> str:
    from utils.vlm_pdf_parser import _has_text_layer

    if setting in ('text', 'images'):
        return setting
    return 'text' if _has_text_layer(len(text)) else 'images'


def _max_images_per_request() -> int:
    try:
        return max(1, int(os.getenv('REPORT_REVIEW_MAX_PAGES', '4')))
    except ValueError:
        return 4


def _page_count(pdf_bytes: bytes) -> int:
    from pypdfium2 import PdfDocument

    try:
        document = PdfDocument(pdf_bytes)
        total_pages = len(document)
        document.close()
    except Exception as exc:
        raise ReportReviewError('The report PDF could not be opened.') from exc
    if total_pages == 0:
        raise ReportReviewError('The report PDF has no pages.')
    return total_pages


def _page_image(pdf_bytes: bytes, page_index: int) -> bytes:
    from utils.vlm_pdf_parser import _render_page_to_png

    return _render_page_to_png(pdf_bytes, page_index, dpi=150)


def _personal_names(report) -> list[str]:
    """Names to redact wherever they are printed: the account holder's own."""
    user = report.user
    return [name for name in (user.first_name, user.last_name) if name]


_IGNORED_CHARS_RE = re.compile(r"[\s,;:()\[\]'\"]+")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _same_text(new: Any, old: Any) -> bool:
    """Whether two field values differ only in capitals, spacing, punctuation, or trailing zeros."""
    left, right = (
        _IGNORED_CHARS_RE.sub('', str(value or '').casefold().replace('\u2013', '-').replace('\u2014', '-'))
        for value in (new, old)
    )
    if left == right:
        return True
    try:
        return float(left) == float(right)
    except ValueError:
        return False


def _same_test(catalog, new_name: str, old_name: str) -> bool:
    """Whether a rename only gives another name for the catalog test the row already names."""
    new_type = catalog.match(new_name)
    return new_type is not None and new_type == catalog.match(old_name)


def _is_printed(value: str, text: str) -> bool:
    """Whether a suggested value appears in the report text: every number in it, or its words."""
    value = _THOUSANDS_RE.sub('', value).strip()
    numbers = _NUMBER_RE.findall(value)
    if numbers:
        printed = {float(number) for number in _NUMBER_RE.findall(_THOUSANDS_RE.sub('', text))}
        return all(float(number) in printed for number in numbers)
    words = ' '.join(value.casefold().split())
    return not words or words in ' '.join(text.casefold().split())


def _text(value: Any, limit: int) -> str:
    return '' if value is None else str(value).strip()[:limit]


def _status(value: Any) -> str:
    status = str(value or '').strip().upper()
    return status if status in STATUSES else normalize_test_status(status)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
