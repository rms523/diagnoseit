"""
Normalize text extracted from PDFs with broken or custom font encodings.

Many lab PDFs map ASCII glyphs to the Unicode Private Use Area (U+F000–U+F0FF).
Decoding is applied when a sufficient fraction of non-space characters use that
range — a vendor-agnostic signal, not a corpus-specific rule.
"""
from __future__ import annotations

import re

# Adobe / embedded fonts often place ASCII at code_point = 0xF000 + ascii_code.
_PUA_MIN = 0xF000
_PUA_MAX = 0xF0FF
_PUA_DECODE_THRESHOLD = 0.25

# Collapse runs of whitespace produced by decoded filler glyphs.
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def _pua_ratio(text: str) -> float:
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return 0.0
    pua = sum(1 for c in non_space if _PUA_MIN <= ord(c) <= _PUA_MAX)
    return pua / len(non_space)


def decode_pua_font_text(text: str) -> str:
    """Map U+F0xx private-use glyphs back to Latin-1 / ASCII."""
    if not text:
        return text
    decoded: list[str] = []
    for ch in text:
        code = ord(ch)
        if _PUA_MIN <= code <= _PUA_MAX:
            decoded.append(chr(code - _PUA_MIN))
        else:
            decoded.append(ch)
    return "".join(decoded)


def normalize_pdf_extracted_text(text: str) -> str:
    """
    Return PDF text suitable for regex parsing.

    Applies PUA decoding when the extract looks font-encoded; always trims
    excessive internal spacing from decoded filler characters.
    """
    if not text:
        return text
    return "\n".join(normalize_pdf_page_lines([text])[0])


def normalize_pdf_page_lines(page_texts: list[str]) -> list[list[str]]:
    """
    Normalize each page into its non-blank lines, deciding PUA decoding for the whole document.

    Concatenating the pages' lines gives exactly normalize_pdf_extracted_text of the joined pages,
    so a line number in parsed text can be traced back to its page.
    """
    decode = _pua_ratio("\n".join(page_texts)) >= _PUA_DECODE_THRESHOLD
    pages = []
    for text in page_texts:
        if decode:
            text = decode_pua_font_text(text)
        # Normalise odd spaces (decoded 0xF020 fillers, column gaps).
        lines = (_MULTI_SPACE_RE.sub(" ", raw).strip() for raw in (text or "").splitlines())
        pages.append([line for line in lines if line])
    return pages
