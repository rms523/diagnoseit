"""
Shared lab-report unit and value tokens for legacy and VLM parsers.

Keep both parsers aligned by importing from this module instead of
duplicating unit lists and value-matching regexes.
"""
from __future__ import annotations

import re
from typing import FrozenSet

# Longest-first ordering avoids partial matches (e.g. mg/dL before mg).
KNOWN_LAB_UNITS: tuple[str, ...] = (
    "mL/min/1.73m²",
    "mL/min/1.73m2",
    "mL/min/1.73 m2",
    "mL/min",
    "min(1.73m)",
    "cells/µL",
    "cells/μL",
    "cells/mm3",
    "Million/cu.mm",
    "cells/cu.mm",
    "mill/cumm",
    "mil/µL",
    "mil/μL",
    "thou/µL",
    "thou/μL",
    "/c.mm",
    "cumm",
    "CV%",
    "thou/cu.mm",
    "mill/cu.mm",
    "/cu.mm",
    "thou/mm3",
    "mill/mm3",
    "K/µL",
    "K/μL",
    "µIU/mL",
    "μIU/mL",
    "mIU/mL",
    "IU/mL",
    "AU/mL",
    "kUA/L",
    "ng/mL",
    "ng/dL",
    "pg/mL",
    "nmol/L",
    "µmol/L",
    "μmol/L",
    "mmol/L",
    "µg/dL",
    "μg/dL",
    "µg/L",
    "μg/L",
    "ug/L",
    "mg/dL",
    "gm/dL",
    "g/dL",
    "g/mL",
    "mg/L",
    "g/L",
    "mg/day",
    "U/L",
    "IU/L",
    "mIU/L",
    "mEq/L",
    "meq/L",
    "/µL",
    "/μL",
    "/uL",
    "/hpf",
    "/HPF",
    "mm/hr",
    "ratio",
    "Index",
    "fL",
    "sec",
    "pg",
    "ug/dL",
    "%",
)

QUALITATIVE_VALUES: FrozenSet[str] = frozenset(
    {
        "negative",
        "positive",
        "not detected",
        "detected",
        "absent",
        "present",
        "reactive",
        "non reactive",
        "non-reactive",
        "moderate positive",
        "weak positive",
        "strong positive",
        "nil",
        "trace",
        "equivocal",
        "indeterminate",
        "none seen",
        "semi fluid",
        "semi solid",
        "dark brown",
        "brown",
        "alkaline",
        "acidic",
    }
)

# Multi-word descriptive results common in urinalysis / stool / physical exam rows.
_DESCRIPTIVE_PHRASES: tuple[str, ...] = (
    "None Seen",
    "Not Seen",
    "Semi Fluid",
    "Semi Solid",
    "Dark Brown",
    "Light Brown",
    "Brown",
    "Alkaline",
    "Acidic",
)

_SORTED_UNITS = sorted(KNOWN_LAB_UNITS, key=len, reverse=True)
_UNIT_ALTS = "|".join(re.escape(u) for u in _SORTED_UNITS)

# Numeric lab values: optional comparator, optional thousands separators (11,050),
# optional leading minus (e.g. -4.6).
NUMERIC_VALUE_RE = r"(?:[<>]=?\s*)?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"

# Last numeric+unit pair on a line (avoids "90 minutes" false positives in long names).
_RIGHT_ANCHOR_TABULAR_RE = re.compile(
    rf"(?P<value>{NUMERIC_VALUE_RE})\s+(?P<unit>{_UNIT_ALTS})(?:\s+(?P<ref>.*))?$",
    re.IGNORECASE,
)

# Unitless numeric: Name  Value  RefRange (Immunoglobulin Synthesis Index 0.50 0.30 - 0.70).
UNITLESS_NUMERIC_LINE_RE = re.compile(
    rf"^(?P<name>.+?)\s+"
    rf"(?P<value>{NUMERIC_VALUE_RE})\s+"
    rf"(?P<ref>\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?.*)$",
    re.IGNORECASE,
)

# Short numeric result without unit or ref (pH 11.0).
SIMPLE_NUMERIC_LINE_RE = re.compile(
    rf"^(?P<name>.{{1,40}}?)\s+(?P<value>{NUMERIC_VALUE_RE})$",
    re.IGNORECASE,
)

# Short text pair without unit (Type of Sample Urine).
SIMPLE_TEXT_PAIR_LINE_RE = re.compile(
    r"^(?P<name>.{2,55}?)\s+(?P<value>[A-Za-z][A-Za-z0-9\-]{0,30})$",
    re.IGNORECASE,
)

# Longest-first explicit phrases (spaces flexible for OCR/PDF quirks).
_QUALITATIVE_PHRASES: tuple[str, ...] = (
    "Moderate Positive",
    "Strong Positive",
    "Weak Positive",
    "Not Detected",
    "Non Reactive",
    "Non-Reactive",
    "Indeterminate",
    "Equivocal",
    "Negative",
    "Positive",
    "Reactive",
    "Detected",
    "Absent",
    "Present",
    "Trace",
    "Nil",
)
_QUAL_ALTS = "|".join(
    re.escape(p).replace(r"\ ", r"\s+")
    for p in sorted(_QUALITATIVE_PHRASES, key=len, reverse=True)
)
_DESC_ALTS = "|".join(
    re.escape(p).replace(r"\ ", r"\s+")
    for p in sorted(_DESCRIPTIVE_PHRASES, key=len, reverse=True)
)

# Tabular: TestName  Value  Unit  RefRange
TABULAR_LINE_RE = re.compile(
    rf"^(?P<name>.+?)\s+"
    rf"(?P<value>{NUMERIC_VALUE_RE})\s+"
    rf"(?P<unit>{_UNIT_ALTS})\s*"
    rf"(?P<ref>.*?)$",
    re.IGNORECASE,
)

# Qualitative rows may omit a unit (e.g. serology Negative / Negative).
QUALITATIVE_LINE_RE = re.compile(
    rf"^(?P<name>.+?)\s+"
    rf"(?P<value>{_QUAL_ALTS})\s*"
    rf"(?:(?P<unit>{_UNIT_ALTS})\s+)?"
    rf"(?P<ref>.*?)$",
    re.IGNORECASE,
)

# Physical / stool / urinalysis descriptive rows (no numeric value).
DESCRIPTIVE_LINE_RE = re.compile(
    rf"^(?P<name>.+?)\s+"
    rf"(?P<value>{_DESC_ALTS})\s+"
    rf"(?:(?P<unit>{_UNIT_ALTS})\s+)?"
    rf"(?P<ref>.*?)$",
    re.IGNORECASE,
)

# Blood grouping and similar short categorical results without units.
CATEGORICAL_LINE_RE = re.compile(
    r"^(?P<name>.+?(?:Group|Factor|Typing|Blood Type))\s+"
    r"(?P<value>A|B|AB|O|Positive|Negative|Reactive|Non-Reactive)\s*$",
    re.IGNORECASE,
)

# OCR / VLM value token (numeric or qualitative).
OCR_VALUE_RE = re.compile(
    rf"^(?:{NUMERIC_VALUE_RE}%?|{_QUAL_ALTS})$",
    re.IGNORECASE,
)


def unit_regex_alternation() -> str:
    return _UNIT_ALTS


def is_qualitative_value(value: str | None) -> bool:
    return (value or "").strip().lower() in QUALITATIVE_VALUES


# Values that appear in clinical prose, not as structured lab results.
NON_RESULT_TEXT_VALUES: FrozenSet[str] = frozenset(
    {
        "disease",
        "disorder",
        "disorders",
        "symptoms",
        "syndrome",
        "infection",
        "infections",
        "allergens",
        "allergen",
        "test",
        "collection",
        "centre",
        "center",
        "haematology",
        "hematology",
        "edta",
        "report",
        "lab",
        "calculated",
        "immunology",
        "immunogenetics",
        "serology",
        "microbiology",
        "transplant",
        "category",
        "ratio",
        "index",
        "reactivity",
        "present",
    }
)


def name_embeds_lab_unit(name: str) -> bool:
    """True when extracted text already contains a known unit token in the name."""
    lower = (name or "").lower()
    return any(unit.lower() in lower for unit in KNOWN_LAB_UNITS)


def parse_comparable_number(value_str: str) -> float | None:
    """Extract a float from values like '15.2', '<10', '-4.6', '11,050', or '>200'."""
    cleaned = (value_str or "").strip().replace(",", "")
    m = re.match(r"^[<>]=?\s*(-?\d+(?:\.\d+)?)", cleaned)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# Result  [High|Low|Normal]  low-high  Unit   (unit column last).
_STATUS_FLAG_RE = r"(?:High|Low|Normal|Abnormal)"
_VALUE_RANGE_UNIT_RE = re.compile(
    rf"(?P<value>{NUMERIC_VALUE_RE})\s+"
    rf"(?:{_STATUS_FLAG_RE}\s+)?"
    rf"(?P<ref>{NUMERIC_VALUE_RE}\s*[-–]\s*{NUMERIC_VALUE_RE})\s+"
    rf"(?P<unit>{_UNIT_ALTS})\s*$",
    re.IGNORECASE,
)


def match_value_range_unit(line: str) -> dict[str, str] | None:
    """
    Parse rows where the unit is the last column, after the reference range.

    Common LIS order: TestName  Result  [flag]  RefInterval  Unit
    """
    m = _VALUE_RANGE_UNIT_RE.search(line.strip())
    if not m:
        return None
    name = line[: m.start()].strip()
    if not name:
        return None
    return {
        "name": name,
        "value": m.group("value").strip(),
        "unit": m.group("unit").strip(),
        "ref": (m.group("ref") or "").strip(),
    }


def match_right_anchored_tabular(line: str) -> dict[str, str] | None:
    """
    Parse tabular rows by anchoring on the last numeric+unit pair.

    Handles names containing incidental numbers (e.g. "after 90 minutes").
    """
    m = _RIGHT_ANCHOR_TABULAR_RE.search(line.strip())
    if not m:
        return None
    name = line[: m.start()].strip()
    if not name:
        return None
    return {
        "name": name,
        "value": m.group("value").strip(),
        "unit": m.group("unit").strip(),
        "ref": (m.group("ref") or "").strip(),
    }

# A person's title right before a name ("MR.JOHN DOE", "Mrs. Rao"): patient details, never a test result.
PERSON_TITLE_RE = re.compile(r"\b(?:mr|mrs|ms|miss)\.\s*[a-z]", re.IGNORECASE)
