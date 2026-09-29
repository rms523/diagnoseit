"""Keep personal details and boilerplate out of what the AI review sends to the model.

Text: the patient's name (a labelled field such as "Patient Name : ...", a name after a title such as
"Mr." or "Mrs.", or the account holder's own first or last name), phone numbers, and email addresses
become [REDACTED]. Age, gender, dates, and the results stay. Legal and contact boilerplate ("clinically
correlate", "customer care", "Page 1 of 2"), sections under an "Important instructions" or "Disclaimer"
heading, encoded barcode text, and page headers and footers repeated on later pages are left out, but
never a line a result was read from.

Page images: words the text pass redacted are painted over using the PDF's text layer. A scanned page
has no text layer, so its image is sent unchanged.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)

REDACTED = '[REDACTED]'
REPEATED_LINE_MIN_CHARS = 20  # shorter lines ("Absent", "Negative") repeat for real results
# Page headers and footers: a line printed at the same place in these margins of two or more pages, whatever its length.
HEADER_LINES = 12
FOOTER_LINES = 6

# Words that start the next field on a line such as "Name : A B Age : 25", so they end a name.
_LABEL_WORDS = frozenset({
    'age', 'sex', 'gender', 'dob', 'date', 'collected', 'collection', 'received', 'reported', 'registered',
    'registration', 'lab', 'sample', 'specimen', 'ref', 'referred', 'referring', 'doctor', 'consultant', 'patient',
    'uhid', 'mrn', 'id', 'visit', 'bill', 'barcode', 'client', 'location', 'centre', 'center', 'status', 'a/c',
    'mobile', 'phone', 'contact', 'email', 'report', 'accession', 'order', 'episode', 'ward', 'bed', 'type', 'no',
    'name', 'years', 'yrs', 'male', 'female',
})
_TITLES = frozenset({'mr', 'mrs', 'ms', 'miss', 'master', 'smt', 'shri', 'sri', 'kumari', 'baby', 'b/o', 'dr'})
_NAME_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z.'\-]*")
_NAME_FIELD_RE = re.compile(
    r"(?<![A-Za-z])(?:patient'?s?\s*name|name\s+of\s+(?:the\s+)?patient|pt\.?\s*name|patient|name)\s*:\s*",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"(?<![A-Za-z])(?:mr|mrs|ms|miss|master|smt|shri|sri|kumari|baby|b/o)\b\.?\s+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_CUE_RE = re.compile(
    r"\b(?:tel|telephone|phone|mob|mobile|cell|contact|call|helpline|whatsapp|toll\s*free|fax)\b\.?"
    r"(?:\s*(?:no|number)\b\.?)?\s*[:\-]?\s*(\+?\d[\d\s()./-]{6,}\d)",
    re.IGNORECASE,
)
_INTERNATIONAL_PHONE_RE = re.compile(r"(?<![\w+])\+\d{1,3}[\s-]?\d[\d\s-]{6,}\d")
_LONG_NUMBER_RE = re.compile(r"(?<![\d.,/])\d{10,}(?![\d.,/])")
_BOILERPLATE_RE = re.compile(
    r"clinical(?:ly)?\s+correlat|correlate\s+clinically|medico[\s-]*legal|jurisdiction|customer\s+care"
    r"|toll[\s-]*free|helpline|terms\s+(?:and|&)\s+conditions|disclaimer|inconvenience|inter[\s-]*laborator"
    r"|electronically\s+(?:signed|generated|verified|authenticated)|computer[\s-]*generated"
    r"|end\s+of\s+(?:the\s+)?report|www\.|https?://",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^\W*page\s*\d+\s*(?:of|/)\s*\d+\W*$", re.IGNORECASE)
# A heading that starts a block of instructions or legal text, which runs to the end of its page.
_BOILERPLATE_HEADING_RE = re.compile(
    r"^\W*(?:important\s+(?:instructions|notes?)|disclaimers?|terms\s+(?:and|&)\s+conditions|conditions\s+of\s+reporting)\W*$",
    re.IGNORECASE,
)
# Text a barcode or QR font prints: one long run of letters and digits with no spaces.
_ENCODED_RE = re.compile(r"^[A-Za-z0-9+/=]{25,}$")
_NO_WORDS_RE = re.compile(r"^[\W_]*$")


def _token(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text).casefold())


class Redactor:
    """Replaces personal details in report lines, remembering the redacted words for painting page images."""

    def __init__(self, names: Iterable[str] = ()):
        words = {word for name in names for word in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", str(name or ''))}
        self._name_res = [re.compile(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", re.IGNORECASE) for word in sorted(words)]
        self.tokens: set[str] = {_token(word) for word in words}

    def line(self, text: str) -> str:
        spans = self._name_spans(text)
        for pattern in self._name_res:
            spans += [match.span() for match in pattern.finditer(text)]
        spans += [match.span() for match in _EMAIL_RE.finditer(text)]
        for match in _PHONE_CUE_RE.finditer(text):
            if len(re.sub(r"\D", "", match.group(1))) >= 8:
                spans.append(match.span(1))
        for pattern in (_INTERNATIONAL_PHONE_RE, _LONG_NUMBER_RE):
            spans += [match.span() for match in pattern.finditer(text) if len(re.sub(r"\D", "", match.group())) >= 8]
        if not spans:
            return text

        merged: list[list[int]] = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in reversed(merged):
            for piece in text[start:end].split():
                token = _token(piece)
                if len(token) >= (4 if token.isdigit() else 2):
                    self.tokens.add(token)
            text = f"{text[:start]}{REDACTED}{text[end:]}"
        return text

    def _name_spans(self, text: str) -> list[tuple[int, int]]:
        """Names after a name label ("Patient Name :") or a title ("Mrs."), up to the next field on the line."""
        spans = []
        for match in _NAME_FIELD_RE.finditer(text):
            if text[:match.start()].rstrip().casefold().endswith('test'):
                continue  # a "Test Name :" column, not a person
            spans += _name_after(text, match.end(), skip_titles=True)
        for match in _TITLE_RE.finditer(text):
            spans += _name_after(text, match.end(), skip_titles=False)
        return spans


def _name_after(text: str, position: int, skip_titles: bool) -> list[tuple[int, int]]:
    start = end = None
    for count, match in enumerate(re.finditer(r"\S+", text[position:])):
        word = match.group()
        bare = re.sub(r"[^a-z/]", "", word.casefold())
        if count >= 6 or ':' in word or not _NAME_TOKEN_RE.fullmatch(word) or bare in _LABEL_WORDS:
            break
        if skip_titles and start is None and bare in _TITLES:
            continue
        if start is None:
            start = position + match.start()
        end = position + match.end()
    return [(start, end)] if start is not None else []


@dataclass
class PreparedText:
    lines: list[str]  # redacted, at the same positions as the extracted lines
    boilerplate: list[bool]
    repeated: set[str]  # header lines printed on more than one page
    keep: set[int]  # lines results were read from: always sent
    tokens: set[str] = field(default_factory=set)

    def select(self, *ranges: range) -> list[list[str]]:
        """The lines of each range to send, leaving out boilerplate and headers already sent in these ranges."""
        sent: set[str] = set()
        selected = []
        for indexes in ranges:
            shown = []
            for index in indexes:
                text = self.lines[index]
                if index not in self.keep and (self.boilerplate[index] or (text in self.repeated and text in sent)):
                    continue
                sent.add(text)
                shown.append(text)
            selected.append(shown)
        return selected


def prepare_report_text(page_lines: list[list[str]], names: Iterable[str], keep: set[int]) -> PreparedText:
    """Redact every line of the report and mark the lines that need not be sent."""
    redactor = Redactor(names)
    pages_of: dict[str, set[int]] = {}
    margin_pages_of: dict[tuple[str, str, int], set[int]] = {}
    lines: list[str] = []
    boilerplate: list[bool] = []
    for page, page_text in enumerate(page_lines):
        in_boilerplate_block = False
        for position, line in enumerate(page_text):
            if len(line) >= REPEATED_LINE_MIN_CHARS:
                pages_of.setdefault(line, set()).add(page)
            if position < HEADER_LINES:
                margin_pages_of.setdefault((line, 'top', position), set()).add(page)
            if position >= len(page_text) - FOOTER_LINES:
                margin_pages_of.setdefault((line, 'bottom', len(page_text) - position), set()).add(page)
            in_boilerplate_block = in_boilerplate_block or bool(_BOILERPLATE_HEADING_RE.match(line))
            lines.append(line)
            boilerplate.append(in_boilerplate_block or is_boilerplate(line))
    repeated_raw = {line for line, pages in pages_of.items() if len(pages) > 1}
    repeated_raw |= {line for (line, _zone, _offset), pages in margin_pages_of.items() if len(pages) > 1}

    redacted = [redactor.line(line) for line in lines]
    return PreparedText(
        lines=redacted,
        boilerplate=boilerplate,
        repeated={redactor.line(line) for line in repeated_raw},
        keep=keep,
        tokens=redactor.tokens,
    )


def is_boilerplate(line: str) -> bool:
    """Legal, contact, page-number, and barcode lines that never help check a result."""
    return bool(
        _BOILERPLATE_RE.search(line) or _PAGE_NUMBER_RE.match(line) or _NO_WORDS_RE.match(line) or _ENCODED_RE.match(line)
    )


def redact_page_image(pdf_bytes: bytes, page_index: int, png: bytes, tokens: set[str]) -> bytes:
    """Paint over the page's words that were redacted in the text; unchanged for a page without a text layer."""
    if not tokens:
        return png
    import pdfplumber
    from PIL import Image, ImageDraw

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[page_index]
            page_width = float(page.width)
            boxes = [
                (word['x0'], word['top'], word['x1'], word['bottom'])
                for word in page.extract_words()
                if _token(word['text']) in tokens
            ]
        if not boxes:
            return png
        image = Image.open(io.BytesIO(png)).convert('RGB')
    except Exception as exc:
        logger.warning("Could not redact page %s of a review image: %s", page_index + 1, exc)
        return png

    scale = image.width / page_width
    draw = ImageDraw.Draw(image)
    for x0, top, x1, bottom in boxes:
        draw.rectangle([x0 * scale - 1, top * scale - 1, x1 * scale + 1, bottom * scale + 1], fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
