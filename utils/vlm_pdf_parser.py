"""
Vision-language PDF parser for medical lab reports.
Renders each PDF page to an image and asks a VLM to extract structured test results.

Supported backends:
  - openai: OpenAI-compatible API (llama-swap, llama.cpp server) via /v1/chat/completions
  - ollama: Ollama native API via /api/generate

Model modes (auto-detected from VLM_MODEL name, or set VLM_MODE):
  - paddle_ocr: PaddleOCR-VL — table recognition first, OCR fallback for non-tabular pages
  - json_vlm: Qwen/Gemma VL — slower but returns JSON directly

Paddle prompt strategy (VLM_PADDLE_STRATEGY, paddle_ocr mode only):
  - table_first: Table Recognition: then OCR: if the table path finds nothing (default)
  - table: Table Recognition: only
  - ocr: OCR: only (legacy behaviour)
"""
import base64
import contextvars
import io
import json
import logging
import os
import re
from html import unescape as html_unescape
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from pypdfium2 import PdfDocument

from utils.lab_units import (
    PERSON_TITLE_RE,
    CATEGORICAL_LINE_RE,
    DESCRIPTIVE_LINE_RE,
    KNOWN_LAB_UNITS,
    OCR_VALUE_RE,
    QUALITATIVE_LINE_RE,
    TABULAR_LINE_RE,
    is_qualitative_value,
)
from utils.pdf_text_normalize import normalize_pdf_extracted_text

logger = logging.getLogger(__name__)

# Settings loaded once for a batch of pages, so page requests on worker threads never query the database.
_OCR_CONFIG_FOR_PAGES: contextvars.ContextVar = contextvars.ContextVar("ocr_config_for_pages", default=None)


def _ocr_config():
    """OCR connection settings (AI settings page, else VLM_*/OLLAMA_* env), read per call."""
    loaded = _OCR_CONFIG_FOR_PAGES.get()
    if loaded is not None:
        return loaded
    from ai_settings.services import ROLE_OCR, get_ai_config

    return get_ai_config(ROLE_OCR)


def _connect_timeout() -> int:
    return int(os.getenv("VLM_CONNECT_TIMEOUT", os.getenv("OLLAMA_CONNECT_TIMEOUT", "10")))


def _auth_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


PADDLE_OCR_PROMPT = "OCR:"
PADDLE_TABLE_PROMPT = "Table Recognition:"
# For vision models that are not PaddleOCR, when a page's text is wanted as it is printed.
OCR_TRANSCRIBE_PROMPT = (
    "Transcribe all the text on this page exactly as printed, from top to bottom. Put each table row on its own "
    "line with its cells in order, separated by two spaces. Reply with the text only, without commentary."
)
_LINE_BREAK_TAG_RE = re.compile(r"<\s*(?:br\s*/?|/tr|/p|/div|/li|/h\d)\s*>", re.IGNORECASE)
_CELL_END_TAG_RE = re.compile(r"<\s*/t[dh]\s*>", re.IGNORECASE)

TABLE_NAME_HEADER_RE = re.compile(
    r"test|investigation|parameter|analyte|name|description|component",
    re.IGNORECASE,
)
TABLE_VALUE_HEADER_RE = re.compile(r"result|value|reading|observed", re.IGNORECASE)
TABLE_UNIT_HEADER_RE = re.compile(r"unit|uom", re.IGNORECASE)
TABLE_REF_HEADER_RE = re.compile(r"ref|range|interval|normal|reference", re.IGNORECASE)
TABLE_STATUS_HEADER_RE = re.compile(r"status|flag|remark|interpretation", re.IGNORECASE)
MARKDOWN_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
HTML_TAG_RE = re.compile(r"<[^>]+>")

KNOWN_OCR_UNITS = set(KNOWN_LAB_UNITS)
OCR_REF_RE = re.compile(r"^\d|^[<>]|^\d+\.?\d*\s*[-–]\s*\d")
OCR_SKIP_LINE_RE = re.compile(
    r"^(Page\s+\d|Test\s+Name|Results|Units|Bio\.?\s*Ref|Test\s+Report|Dr\s|Regd\.|"
    r"Web:|Name|Lab\s+No|Age|Ref\s+By|Gender|Collected|Reported|A/c|Report\s+Status|"
    r"Processed|National|Sector|DELHI|If\s+Test|Tel:|Note|Interpretation|SWASTHFIT|"
    r".*PANEL.*|Courts/Forum|Consultant|Technical|Senior|NRL\s+-)",
    re.IGNORECASE,
)

USER_PROMPT = (
    "Extract all lab test results from this medical report image "
    "and return them as a JSON array of objects. "
    "Each object must have keys: test_name, value, unit, reference_range, status. "
    "Output ONLY valid JSON, no markdown code blocks, no extra text."
)

SYSTEM_PROMPT = (
    "You are a medical laboratory report parser. "
    "Look at the provided lab report image and extract every test result you can see. "
    "Return ONLY a valid JSON array. No markdown, no explanations. "
    "Each array element must be an object with these exact keys:\n"
    "  test_name  (string)\n"
    "  value      (string or number)\n"
    "  unit       (string)\n"
    "  reference_range (string, e.g. '13.00 - 17.00' or '<14.00')\n"
    "  status     (one of: NORMAL, HIGH, LOW, UNKNOWN)\n\n"
    "Important rules:\n"
    "- If a test appears in a 'URINE' section, prefix its name with 'Urine ' (e.g. 'Urine Creatinine').\n"
    "- If a test appears in a 'Differential Leucocyte Count (DLC)' section, suffix its name with ' (DLC)'.\n"
    "- If a test appears in an 'Absolute Leucocyte Count' section, suffix its name with ' (ALC)'.\n"
    "- Do not invent values that are not visible in the image.\n"
    "- If the reference range is not visible, set it to an empty string ''.\n"
    "- If the status is not visible, set it to 'UNKNOWN'.\n"
)


def _use_vlm_parser() -> bool:
    """OCR runs only when USE_VLM_PARSER allows it (a kill switch) and OCR settings are enabled."""
    if os.getenv("USE_VLM_PARSER", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    return _ocr_config().enabled


def _vlm_extraction_mode() -> str:
    """Return 'paddle_ocr' or 'json_vlm'."""
    config = _ocr_config()
    if config.ocr_mode in ("paddle_ocr", "ocr", "paddle"):
        return "paddle_ocr"
    if config.ocr_mode in ("json_vlm", "json", "vlm"):
        return "json_vlm"
    if "paddleocr" in config.model.lower():
        return "paddle_ocr"
    return "json_vlm"


def _page_render_dpi() -> int:
    page_dpi = int(os.getenv("VLM_PAGE_DPI", "0"))  # 0 = use mode default
    if page_dpi > 0:
        return page_dpi
    return 150 if _vlm_extraction_mode() == "paddle_ocr" else 200


def _paddle_prompt_strategy() -> str:
    """Return 'table_first', 'table', or 'ocr'."""
    strategy = os.getenv("VLM_PADDLE_STRATEGY", "table_first").strip().lower()
    if strategy in ("table_first", "table-then-ocr", "auto"):
        return "table_first"
    if strategy in ("table", "table_only"):
        return "table"
    if strategy in ("ocr", "ocr_only"):
        return "ocr"
    return "table_first"


def _openai_root_url(api_base: str) -> str:
    """Server root URL for llama-swap style /health checks (strip a trailing /v1)."""
    return api_base[:-3].rstrip("/") if api_base.endswith("/v1") else api_base


def _vlm_reachable() -> bool:
    """Quick health check — avoid long per-page timeouts when the VLM server is down."""
    if not _use_vlm_parser():
        logger.info("VLM parser disabled via USE_VLM_PARSER or AI settings")
        return False

    config = _ocr_config()
    base = config.api_base
    if not base:
        logger.warning("OCR server URL is not configured")
        return False
    if config.provider == "ollama":
        checks = [f"{base}/api/tags"]
    else:
        # /models is standard for OpenAI-compatible servers; llama-swap also serves /health.
        checks = [f"{base}/models", f"{_openai_root_url(base)}/health"]
    for url in checks:
        try:
            response = requests.get(url, headers=_auth_headers(config.api_key), timeout=_connect_timeout())
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.warning("OCR server check failed at %s: %s", url, exc)
    return False


def _render_page_to_png(pdf_bytes: bytes, page_index: int = 0, dpi: int | None = None) -> bytes:
    """Render a single PDF page to PNG bytes."""
    if dpi is None:
        dpi = _page_render_dpi()
    pdf = PdfDocument(pdf_bytes)
    page = pdf[page_index]
    bitmap = page.render(scale=dpi / 72.0)
    pil_image = bitmap.to_pil()
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    pdf.close()
    return buffer.getvalue()


def limit_image_size(image_bytes: bytes, max_edge: int) -> bytes:
    """The image with its longest edge no larger than max_edge, as PNG; never enlarged.

    A vision model turns an image into tokens by area, so a phone photo at 4000px costs many times what
    the same page costs at 1600px, in both the encode and everything the model then writes about it.
    Text stays legible well below a photo's native size.
    """
    if max_edge <= 0:
        return image_bytes
    from PIL import Image

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            longest = max(image.size)
            if longest <= max_edge:
                return image_bytes
            scale = max_edge / longest
            resized = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.LANCZOS,
            )
            buffer = io.BytesIO()
            resized.convert("RGB").save(buffer, format="PNG")
            logger.info(
                "Scaled OCR image from %sx%s to %sx%s", image.width, image.height, resized.width, resized.height
            )
            return buffer.getvalue()
    except Exception as exc:
        logger.warning("Could not scale the OCR image, sending it as it is: %s", exc)
        return image_bytes


def _read_pdf_bytes(pdf_file) -> bytes:
    """Read PDF bytes and rewind the file handle when possible."""
    if hasattr(pdf_file, "read"):
        pdf_bytes = pdf_file.read()
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
        return pdf_bytes
    return pdf_file


def _embedded_text_length(pdf_bytes: bytes) -> int:
    """Return total embedded text length via pdfplumber (fast text-native check)."""
    import io

    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            raw = sum(len(page.extract_text() or "") for page in pdf.pages)
            if raw:
                pages_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                return len(normalize_pdf_extracted_text(pages_text))
            return raw
    except Exception as exc:
        logger.debug("Could not measure embedded PDF text: %s", exc)
        return 0


def _estimate_actionable_line_count(text: str) -> int:
    """Heuristic count of lines that look like lab result rows."""
    count = 0
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < 5:
            continue
        if any(
            pat.match(line)
            for pat in (
                TABULAR_LINE_RE,
                QUALITATIVE_LINE_RE,
                DESCRIPTIVE_LINE_RE,
                CATEGORICAL_LINE_RE,
            )
        ):
            count += 1
    return count


def _legacy_is_sufficient(legacy: Dict[str, Any]) -> bool:
    """
    Decide whether legacy parser output is good enough to skip slow VLM/OCR.

    Text-native PDFs (like Dr Lal PathLabs exports) usually parse in seconds with
    high recall; VLM should only run when legacy is weak or absent.
    """
    test_count = len(legacy.get("test_results") or [])
    min_tests = int(os.getenv("MIN_LEGACY_TESTS", "3"))
    min_text_chars = int(os.getenv("MIN_EMBEDDED_TEXT_CHARS", "500"))
    min_recall_ratio = float(os.getenv("MIN_LEGACY_RECALL_RATIO", "0.5"))

    if legacy.get("error"):
        return False
    if test_count >= min_tests:
        text = legacy.get("text") or ""
        actionable = _estimate_actionable_line_count(text)
        if actionable >= 8 and test_count < actionable * min_recall_ratio:
            return False
        return True
    text_len = len(legacy.get("text") or "")
    if text_len >= min_text_chars and test_count >= 1:
        actionable = _estimate_actionable_line_count(legacy.get("text") or "")
        if actionable >= 5 and test_count < max(2, actionable * min_recall_ratio):
            return False
        return True
    return False


def _merge_parse_results(
    legacy: Dict[str, Any],
    vlm: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Union legacy and VLM rows, deduplicating by name + context + value."""
    legacy_rows = list(legacy.get("test_results") or [])
    if not vlm or not vlm.get("test_results"):
        legacy["parser"] = legacy.get("parser") or "legacy"
        return legacy

    from utils.parser_normalize import normalize_parsed_results

    vlm_rows = normalize_parsed_results(list(vlm.get("test_results") or []))
    merged = list(legacy_rows)
    seen = {_result_dedup_key(r) for r in merged}

    added = 0
    for row in vlm_rows:
        key = _result_dedup_key(row)
        if key not in seen:
            seen.add(key)
            merged.append(row)
            added += 1

    base = dict(legacy)
    base["test_results"] = merged
    base["parsed_successfully"] = len(merged) > 0
    base["total_tests_found"] = len(merged)
    if merged:
        base["confidence_score"] = sum(r.get("confidence", 0) for r in merged) / len(merged)
        base["high_confidence_tests"] = len([r for r in merged if r.get("confidence", 0) > 0.7])
    if added > 0 and legacy_rows:
        base["parser"] = "hybrid"
    elif added > 0:
        base["parser"] = vlm.get("parser") or "vlm"
    else:
        base["parser"] = "legacy"

    logger.info(
        "Merged parse results: legacy=%s vlm=%s merged=%s added_from_vlm=%s",
        len(legacy_rows),
        len(vlm_rows),
        len(merged),
        added,
    )
    return base


def _result_dedup_key(row: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("test_name") or row.get("display_name") or "").lower(),
        str(row.get("section_context") or ""),
        str(row.get("value") or ""),
    )


def _pick_better_parse_result(
    legacy: Dict[str, Any],
    vlm: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Prefer the parser that found more tests; tie goes to legacy (faster, more reliable on text PDFs)."""
    legacy_count = len(legacy.get("test_results") or [])
    vlm_count = len(vlm.get("test_results") or []) if vlm else 0

    if vlm and vlm_count > legacy_count:
        logger.info(
            "VLM parser selected (%s tests) over legacy (%s tests)",
            vlm_count,
            legacy_count,
        )
        return vlm

    if legacy_count > 0 or not vlm or not vlm.get("parsed_successfully"):
        if vlm and vlm_count > 0 and vlm_count <= legacy_count:
            logger.info(
                "Legacy parser selected (%s tests) over VLM (%s tests)",
                legacy_count,
                vlm_count,
            )
        legacy["parser"] = "legacy"
        return legacy

    return vlm


def _normalize_ocr_line(line: str) -> str:
    """Normalize LaTeX-style OCR artifacts from PaddleOCR (e.g. \\( >59 \\))."""
    cleaned = line.strip()
    cleaned = cleaned.replace("\\(", "").replace("\\)", "")
    cleaned = cleaned.replace("m^2", "m2").replace("²", "2")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _is_ocr_unit(line: str) -> bool:
    normalized = _normalize_ocr_line(line).replace("²", "2")
    if normalized in KNOWN_OCR_UNITS:
        return True
    if re.match(r"^mL/min/1\.73\s*m2?$", normalized, re.IGNORECASE):
        return True
    if re.match(r"^mL/min/1\.73m2$", normalized, re.IGNORECASE):
        return True
    return line in KNOWN_OCR_UNITS or normalized in KNOWN_OCR_UNITS


def _is_ocr_value(line: str) -> bool:
    normalized = _normalize_ocr_line(line)
    if is_qualitative_value(normalized):
        return True
    return bool(OCR_VALUE_RE.match(normalized)) and not _is_ocr_unit(normalized)


def _is_ocr_reference(line: str) -> bool:
    normalized = _normalize_ocr_line(line)
    return bool(OCR_REF_RE.match(normalized)) and not _is_ocr_unit(normalized)


def _should_skip_ocr_line(line: str) -> bool:
    if line.startswith("(") or PERSON_TITLE_RE.search(line):
        return True
    return bool(OCR_SKIP_LINE_RE.match(line))


def _make_lab_result(
    test_name: str,
    value: str,
    unit: str = "",
    reference_range: str = "",
    status: str = "UNKNOWN",
    source: str = "paddle_ocr",
    confidence: float = 0.9,
) -> Dict[str, Any]:
    name = _normalize_ocr_line(test_name)
    return {
        "test_name": name,
        "display_name": name,
        "value": _normalize_ocr_line(value),
        "unit": _normalize_ocr_line(unit),
        "reference_range": _normalize_ocr_line(reference_range),
        "status": str(status or "UNKNOWN").upper(),
        "confidence": confidence,
        "source": source,
    }


def _strip_html(text: str) -> str:
    cleaned = HTML_TAG_RE.sub(" ", text or "")
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = cleaned.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return _normalize_ocr_line(cleaned)


class _SimpleHTMLTableParser(HTMLParser):
    """Collect rows from the first HTML table in model output."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cell_parts: List[str] = []
        self._current_row: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            if not self.rows:
                self._in_table = True
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in ("td", "th"):
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._in_cell:
            self._current_row.append(_strip_html("".join(self._cell_parts)))
            self._in_cell = False
            self._cell_parts = []
        elif tag == "tr" and self._in_row:
            if any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif tag == "table" and self._in_table:
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


def _parse_html_table(raw_text: str) -> List[List[str]]:
    parser = _SimpleHTMLTableParser()
    try:
        parser.feed(raw_text)
    except Exception as exc:
        logger.debug("HTML table parse failed: %s", exc)
        return []
    return parser.rows


def _parse_markdown_table(raw_text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [_normalize_ocr_line(cell) for cell in stripped.strip("|").split("|")]
        if not cells or all(MARKDOWN_SEPARATOR_CELL_RE.match(cell.replace(" ", "")) for cell in cells if cell):
            continue
        rows.append(cells)
    return rows


def _parse_tsv_table(raw_text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in stripped:
            cells = [_normalize_ocr_line(cell) for cell in stripped.split("\t")]
        elif "|" in stripped:
            cells = [_normalize_ocr_line(cell) for cell in stripped.split("|")]
        else:
            cells = [_normalize_ocr_line(cell) for cell in re.split(r"\s{2,}", stripped)]
        cells = [cell for cell in cells if cell]
        if len(cells) >= 3:
            rows.append(cells)
    return rows


def _looks_like_header_row(cells: List[str]) -> bool:
    joined = " ".join(cells).lower()
    return bool(
        TABLE_NAME_HEADER_RE.search(joined)
        or TABLE_VALUE_HEADER_RE.search(joined)
        or TABLE_REF_HEADER_RE.search(joined)
    )


def _map_table_columns(header: List[str]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header):
        if TABLE_NAME_HEADER_RE.search(cell) and "name" not in mapping:
            mapping["name"] = idx
        elif TABLE_VALUE_HEADER_RE.search(cell) and "value" not in mapping:
            mapping["value"] = idx
        elif TABLE_UNIT_HEADER_RE.search(cell) and "unit" not in mapping:
            mapping["unit"] = idx
        elif TABLE_REF_HEADER_RE.search(cell) and "ref" not in mapping:
            mapping["ref"] = idx
        elif TABLE_STATUS_HEADER_RE.search(cell) and "status" not in mapping:
            mapping["status"] = idx
    return mapping


def _default_table_column_map(num_columns: int) -> Dict[str, int]:
    if num_columns >= 5:
        return {"name": 0, "value": 1, "unit": 2, "ref": 3, "status": 4}
    if num_columns == 4:
        return {"name": 0, "value": 1, "unit": 2, "ref": 3}
    if num_columns == 3:
        return {"name": 0, "value": 1, "ref": 2}
    return {"name": 0, "value": 1}


def _table_cell(row: List[str], index: Optional[int]) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _normalize_table_status(raw_status: str) -> str:
    status = _normalize_ocr_line(raw_status).upper()
    if status in ("NORMAL", "HIGH", "LOW", "UNKNOWN"):
        return status
    if status in ("H", "HIGH", "ABNORMAL HIGH"):
        return "HIGH"
    if status in ("L", "LOW", "ABNORMAL LOW"):
        return "LOW"
    if status in ("N", "NORMAL", "WITHIN RANGE"):
        return "NORMAL"
    return "UNKNOWN"


def _rows_to_lab_results(rows: List[List[str]], source: str = "paddle_table") -> List[Dict[str, Any]]:
    if not rows:
        return []

    col_map = _map_table_columns(rows[0]) if _looks_like_header_row(rows[0]) else {}
    data_start = 1 if col_map else 0
    if not col_map:
        col_map = _default_table_column_map(len(rows[0]))

    results: List[Dict[str, Any]] = []
    for row in rows[data_start:]:
        if len(row) < 2:
            continue

        name = _table_cell(row, col_map.get("name"))
        value = _table_cell(row, col_map.get("value"))
        unit = _table_cell(row, col_map.get("unit"))
        ref = _table_cell(row, col_map.get("ref"))
        status = _normalize_table_status(_table_cell(row, col_map.get("status")))

        if not name or _should_skip_ocr_line(name):
            continue
        if not _is_ocr_value(value):
            continue

        results.append(
            _make_lab_result(
                test_name=name,
                value=value,
                unit=unit,
                reference_range=ref,
                status=status,
                source=source,
                confidence=0.92,
            )
        )

    return results


def _parse_table_ocr_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse PaddleOCR Table Recognition output (HTML, markdown, or TSV-like tables).
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return []

    rows: List[List[str]] = []
    if "<table" in raw_text.lower():
        rows = _parse_html_table(raw_text)
    if not rows and raw_text.count("|") >= 4:
        rows = _parse_markdown_table(raw_text)
    if not rows:
        rows = _parse_tsv_table(raw_text)

    results = _rows_to_lab_results(rows, source="paddle_table")
    if results:
        logger.debug("Table recognition parsed %s lab results", len(results))
    return results


def _pick_better_paddle_results(
    table_results: List[Dict[str, Any]],
    ocr_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Prefer the paddle path that extracted more structured lab rows."""
    if not table_results:
        return ocr_results
    if not ocr_results:
        return table_results
    if len(table_results) >= len(ocr_results):
        return table_results
    return ocr_results


def _extract_paddle_ocr_results(image_png_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extract lab rows using PaddleOCR-VL prompts.

    Default strategy tries Table Recognition first (better for lab tables), then
    falls back to plain OCR for cover pages or sparse output.
    """
    strategy = _paddle_prompt_strategy()

    if strategy == "ocr":
        raw_text = _call_openai_vision(PADDLE_OCR_PROMPT, image_png_bytes)
        logger.debug("PaddleOCR OCR raw response: %s", raw_text[:500])
        return _parse_multiline_ocr_text(raw_text)

    raw_table = _call_openai_vision(PADDLE_TABLE_PROMPT, image_png_bytes)
    logger.debug("PaddleOCR table raw response: %s", raw_table[:500])
    table_results = _parse_table_ocr_text(raw_table)

    if strategy == "table":
        return table_results

    if table_results and len(table_results) >= 2:
        return table_results

    raw_ocr = _call_openai_vision(PADDLE_OCR_PROMPT, image_png_bytes)
    logger.debug("PaddleOCR OCR fallback raw response: %s", raw_ocr[:500])
    ocr_results = _parse_multiline_ocr_text(raw_ocr)
    return _pick_better_paddle_results(table_results, ocr_results)


def _parse_multiline_ocr_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse PaddleOCR multiline output (name / value / unit / ref on separate lines).
    """
    lines = [_normalize_ocr_line(line) for line in raw_text.splitlines() if line.strip()]
    results: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if _should_skip_ocr_line(lines[i]):
            i += 1
            continue

        name = lines[i]
        if i + 1 >= len(lines) or not _is_ocr_value(lines[i + 1]):
            i += 1
            continue

        value = lines[i + 1]
        j = i + 2
        unit = ""
        ref = ""

        if j < len(lines) and _is_ocr_unit(lines[j]):
            unit = lines[j]
            j += 1
        if j < len(lines) and _is_ocr_reference(lines[j]):
            ref = lines[j]
            j += 1
        while j < len(lines) and lines[j].startswith("("):
            j += 1

        results.append(
            _make_lab_result(
                test_name=name,
                value=value,
                unit=unit,
                reference_range=ref,
                source="paddle_ocr",
            )
        )
        i = j

    return results


def _parse_json_array_from_text(raw_text: str) -> List[Dict[str, Any]]:
    """Extract and parse a JSON array from model output."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()

    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        logger.warning("No JSON array found in VLM response: %s", raw_text[:200])
        return []

    json_str = raw_text[start : end + 1]
    try:
        results = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse VLM JSON: %s. Text: %s", exc, json_str[:200])
        return []

    if not isinstance(results, list):
        logger.warning("VLM response JSON is not an array")
        return []

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "test_name": str(item.get("test_name", "unknown")).strip(),
            "display_name": str(item.get("test_name", "unknown")).strip(),
            "value": str(item.get("value", "")),
            "unit": str(item.get("unit", "")),
            "reference_range": str(item.get("reference_range", "")),
            "status": str(item.get("status", "UNKNOWN")).upper(),
            "confidence": 0.95,
            "source": "vlm",
        })
    return normalized


def _post_vlm_request(url: str, payload: Dict[str, Any], backend_label: str) -> requests.Response:
    config = _ocr_config()
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_auth_headers(config.api_key),
            timeout=(_connect_timeout(), config.timeout_seconds),
        )
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        logger.error("%s VLM request timed out", backend_label)
        raise
    except requests.exceptions.ConnectionError:
        logger.error("%s VLM connection failed: %s", backend_label, url)
        raise
    except requests.exceptions.RequestException as exc:
        logger.error("%s VLM request failed: %s", backend_label, exc)
        raise


def _call_openai_vision(
    prompt: str, image_png_bytes: bytes, system_prompt: str | None = None, max_tokens: int | None = None
) -> str:
    """Call OpenAI-compatible vision chat and return raw text content."""
    config = _ocr_config()
    b64_image = base64.b64encode(image_png_bytes).decode("utf-8")
    url = f"{config.api_base}/chat/completions"
    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_image}"},
            },
        ],
    })
    payload = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens or config.max_tokens,
        "temperature": config.temperature_or(0.0 if _vlm_extraction_mode() == "paddle_ocr" else 0.1),
    }
    logger.info("Calling OpenAI VLM at %s with model %s", url, config.model)

    response = _post_vlm_request(url, payload, "OpenAI")
    choices = response.json().get("choices") or []
    if not choices:
        logger.warning("OpenAI VLM returned no choices")
        return ""
    return choices[0].get("message", {}).get("content", "")


def _call_openai_vlm(image_png_bytes: bytes) -> List[Dict[str, Any]]:
    """Send a page image via OpenAI-compatible chat/completions (llama-swap)."""
    if _vlm_extraction_mode() == "paddle_ocr":
        return _extract_paddle_ocr_results(image_png_bytes)

    raw_text = _call_openai_vision(USER_PROMPT, image_png_bytes, SYSTEM_PROMPT)
    logger.debug("OpenAI VLM raw response: %s", raw_text[:500])
    return _parse_json_array_from_text(raw_text)


def _call_ollama_vision(
    prompt: str, image_png_bytes: bytes, system_prompt: str | None = None, max_tokens: int = 2048
) -> str:
    """Send a page image via Ollama /api/generate and return the raw text reply."""
    config = _ocr_config()
    b64_image = base64.b64encode(image_png_bytes).decode("utf-8")
    url = f"{config.api_base}/api/generate"
    payload: Dict[str, Any] = {
        "model": config.model,
        "prompt": prompt,
        "images": [b64_image],
        "stream": False,
        "options": {
            "temperature": config.temperature_or(0.1),
            "num_predict": max_tokens,
        },
    }
    if system_prompt:
        payload["system"] = system_prompt
    logger.info("Calling Ollama VLM at %s with model %s", url, config.model)

    response = _post_vlm_request(url, payload, "Ollama")
    return response.json().get("response", "")


def _call_ollama_vlm(image_png_bytes: bytes) -> List[Dict[str, Any]]:
    """Send a page image via Ollama /api/generate."""
    raw_text = _call_ollama_vision(USER_PROMPT, image_png_bytes, SYSTEM_PROMPT)
    logger.debug("Ollama raw response: %s", raw_text[:500])
    return _parse_json_array_from_text(raw_text)


def transcribe_page(image_png_bytes: bytes, max_tokens: int | None = None) -> str:
    """A page image's text as read by the report OCR model: PaddleOCR's plain OCR, or a vision model told to transcribe.

    max_tokens bounds the reply for a caller that knows how much text a page can hold; without it the OCR
    setting's own limit applies. A vision model that starts repeating itself will otherwise write until it
    reaches that limit, which is minutes of decoding for one page.
    """
    config = _ocr_config()
    prompt = PADDLE_OCR_PROMPT if _vlm_extraction_mode() == "paddle_ocr" else OCR_TRANSCRIBE_PROMPT
    if config.provider == "openai":
        raw_text = _call_openai_vision(prompt, image_png_bytes, max_tokens=max_tokens)
    else:
        raw_text = _call_ollama_vision(prompt, image_png_bytes, max_tokens=max_tokens or config.max_tokens)
    return _markup_to_text(raw_text)


def _markup_to_text(raw_text: str) -> str:
    """Model output as plain lines: HTML rows and breaks become new lines, and table cells are spaced apart."""
    text = _LINE_BREAK_TAG_RE.sub("\n", raw_text or "")
    text = _CELL_END_TAG_RE.sub("  ", text)
    text = HTML_TAG_RE.sub(" ", text)
    return html_unescape(text)


def _call_vlm(image_png_bytes: bytes) -> List[Dict[str, Any]]:
    if _ocr_config().provider == "openai":
        return _call_openai_vlm(image_png_bytes)
    return _call_ollama_vlm(image_png_bytes)


def _attempt(read: Callable[[bytes], Any], image_png_bytes: bytes) -> Tuple[Any, Optional[Exception]]:
    try:
        return read(image_png_bytes), None
    except Exception as exc:
        return None, exc


def read_pages(
    pdf_bytes: bytes, page_count: int, read: Callable[[bytes], Any]
) -> List[Tuple[int, Any, Optional[Exception]]]:
    """Send each page image to the OCR server, as many at once as the OCR settings allow.

    Returns (page index, result, error) in page order. Pages are rendered on this thread, since PDFium
    is not thread-safe, and requests share the settings loaded here. After a batch with a connection error
    or timeout, later pages are not sent; they carry that error.
    """
    config = _ocr_config()
    batch_size = max(1, int(getattr(config, "parallel_requests", 1) or 1))
    token = _OCR_CONFIG_FOR_PAGES.set(config)
    outcomes: List[Tuple[int, Any, Optional[Exception]]] = []
    try:
        for start in range(0, page_count, batch_size):
            indexes = list(range(start, min(start + batch_size, page_count)))
            images: Dict[int, bytes] = {}
            results: Dict[int, Tuple[Any, Optional[Exception]]] = {}
            for index in indexes:
                try:
                    images[index] = _render_page_to_png(pdf_bytes, index)
                except Exception as exc:
                    results[index] = (None, exc)
            pending = [index for index in indexes if index in images]
            if len(pending) == 1:
                results[pending[0]] = _attempt(read, images[pending[0]])
            elif pending:
                with ThreadPoolExecutor(max_workers=len(pending)) as pool:
                    futures = {
                        index: pool.submit(contextvars.copy_context().run, _attempt, read, images[index])
                        for index in pending
                    }
                    results.update({index: future.result() for index, future in futures.items()})
            outcomes.extend((index, *results[index]) for index in indexes)
            connection_error = next(
                (
                    error for _, error in (results[index] for index in indexes)
                    if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))
                ),
                None,
            )
            if connection_error is not None:
                outcomes.extend((index, None, connection_error) for index in range(indexes[-1] + 1, page_count))
                break
    finally:
        _OCR_CONFIG_FOR_PAGES.reset(token)
    return outcomes


def parse_medical_pdf_with_vlm(pdf_file) -> Dict[str, Any]:
    """
    Parse a medical report PDF using a vision-language model.
    Returns a dict compatible with the existing parser interface.
    """
    pdf_bytes = pdf_file.read() if hasattr(pdf_file, "read") else pdf_file
    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)

    try:
        pdf = PdfDocument(pdf_bytes)
        num_pages = len(pdf)
        pdf.close()
    except Exception as exc:
        logger.error("Failed to open PDF with pypdfium2: %s", exc)
        return {"error": "Could not open PDF", "test_results": [], "parsed_successfully": False}

    all_results: List[Dict[str, Any]] = []
    page_errors: List[Dict[str, Any]] = []
    aborted = False
    for page_idx, page_results, error in read_pages(pdf_bytes, num_pages, _call_vlm):
        if error is None:
            for result in page_results:
                result["page_number"] = page_idx + 1
            all_results.extend(page_results)
            logger.info(
                "Page %s: extracted %s results via VLM (%s/%s)",
                page_idx + 1,
                len(page_results),
                _ocr_config().provider,
                _vlm_extraction_mode(),
            )
            continue
        if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            # Pages after a connection failure are never read, so they count as failed too.
            if not aborted:
                logger.error("Error processing page %s with VLM (aborting remaining pages): %s", page_idx + 1, error)
                aborted = True
        else:
            logger.error("Error processing page %s with VLM: %s", page_idx + 1, error)
        page_errors.append({"page": page_idx + 1, "reason": _ocr_failure_reason(error)})

    avg_confidence = (
        sum(r.get("confidence", 0) for r in all_results) / len(all_results)
        if all_results
        else 0
    )

    return {
        "text": "",
        "test_results": all_results,
        "parsed_successfully": len(all_results) > 0,
        "confidence_score": avg_confidence,
        "total_tests_found": len(all_results),
        "high_confidence_tests": len([r for r in all_results if r.get("confidence", 0) > 0.7]),
        "parser": f"vlm-{_ocr_config().provider}-{_vlm_extraction_mode()}",
        "pages": num_pages,
        "page_errors": page_errors,
    }


def _ocr_failure_reason(exc: Exception) -> str:
    """Summarize an OCR failure for users without exposing internal server URLs."""
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timed out"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection failed"
    return type(exc).__name__


def _describe_ocr_run_failure(vlm_result: Dict[str, Any]) -> Optional[str]:
    """Explain why an OCR run produced no rows, or None when every page was read."""
    if vlm_result.get("error"):
        return "OCR could not open it"
    page_errors = vlm_result.get("page_errors") or []
    if not page_errors:
        return None
    reasons = ", ".join(sorted({str(error.get("reason")) for error in page_errors}))
    pages = vlm_result.get("pages") or len(page_errors)
    return f"OCR failed on {len(page_errors)} of {pages} page(s) ({reasons})"


def _has_text_layer(embedded_chars: int) -> bool:
    """Scanned or image-only PDFs embed little or no text; real text reports embed hundreds of chars."""
    return embedded_chars >= int(os.getenv("MIN_TEXT_LAYER_CHARS", "100"))


def parse_medical_pdf_hybrid(pdf_file) -> Dict[str, Any]:
    """
    Parse a medical report PDF using the best available strategy.

    Strategy (legacy-first):
      1. Run the fast legacy text parser (pdfplumber + regex) — ~seconds on text PDFs.
      2. If legacy finds enough results, return immediately (skip slow VLM/OCR).
      3. Otherwise try VLM/OCR for scanned/image-only PDFs.
      4. When both run, keep whichever found more tests (tie → legacy).
    """
    from io import BytesIO

    from utils.enhanced_pdf_parser import parse_medical_pdf_enhanced

    pdf_bytes = _read_pdf_bytes(pdf_file)
    legacy = parse_medical_pdf_enhanced(BytesIO(pdf_bytes))
    legacy_count = len(legacy.get("test_results") or [])
    embedded_chars = _embedded_text_length(pdf_bytes)
    logger.info(
        "Legacy parser: %s tests, %s embedded chars",
        legacy_count,
        embedded_chars,
    )

    if _legacy_is_sufficient(legacy):
        legacy["parser"] = "legacy"
        return legacy

    vlm_result: Dict[str, Any] | None = None
    ocr_failure: Optional[str] = None
    if not _use_vlm_parser():
        logger.info("Skipping VLM parser (disabled via USE_VLM_PARSER)")
        ocr_failure = "OCR is disabled"
    elif not _vlm_reachable():
        logger.info("Skipping VLM parser (server unreachable)")
        ocr_failure = "the OCR server is unreachable"
    else:
        try:
            vlm_result = parse_medical_pdf_with_vlm(BytesIO(pdf_bytes))
            if not vlm_result.get("parsed_successfully"):
                logger.warning(
                    "VLM parser returned no results (%s legacy tests available)",
                    legacy_count,
                )
                ocr_failure = _describe_ocr_run_failure(vlm_result)
        except Exception as exc:
            logger.error("VLM parser failed: %s", exc)
            ocr_failure = f"OCR failed ({_ocr_failure_reason(exc)})"

    if vlm_result and vlm_result.get("test_results"):
        merged = _merge_parse_results(legacy, vlm_result)
        # OCR read the PDF, so the text parser's "Could not extract text" must not fail the parse.
        _supersede_legacy_error(merged)
        return merged

    legacy["parser"] = "legacy"
    legacy.setdefault("test_results", [])
    if legacy_count == 0 and not _has_text_layer(embedded_chars):
        if ocr_failure:
            # parse_report_task retries on this error and then marks the report FAILED
            # with a reason, instead of a generic text-extraction error.
            _supersede_legacy_error(legacy)
            legacy["error"] = f"This PDF has no text layer and {ocr_failure}, so no results could be read."
        elif vlm_result is not None:
            # OCR read every page and found no results, like a blank interim report.
            _supersede_legacy_error(legacy)
    return legacy


def _supersede_legacy_error(result: Dict[str, Any]) -> None:
    """Keep the text parser's error for diagnostics once OCR has decided the outcome."""
    error = result.pop("error", None)
    if error:
        result["legacy_error"] = error
