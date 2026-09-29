"""Put one test's results over time into a single unit, so they can share a trend line.

Reports print the same unit many ways ("mg/dl", "mg/dL", "cells/cumm", "/cu.mm"), and some labs report
in another unit altogether (mmol/L instead of mg/dL). The trend uses the unit most results were printed
in; results in another unit are converted with the catalog's conversions for that test, and results that
cannot be converted keep their printed value and are marked, so they are never plotted on the wrong scale.
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .models import LabTestUnit, UnitConversion

SAME = 'same'
CONVERTED = 'converted'
UNCONVERTED = 'unconverted'

_NUMBER = r"-?\d[\d,]*(?:\.\d+)?"
_VALUE_RE = re.compile(rf"^\s*(<=|>=|≤|≥|<|>)?\s*({_NUMBER})\s*$")
_RANGE_RE = re.compile(rf"^\s*({_NUMBER})\s*(?:-|–|—|to)\s*({_NUMBER})\s*[^\d]*$", re.IGNORECASE)
_BOUND_RE = re.compile(rf"^\s*(<=|>=|≤|≥|<|>|up\s+to)\s*({_NUMBER})\s*[^\d]*$", re.IGNORECASE)
_CUBIC_MM_RE = re.compile(r"^(?:cells?)?/?(?:cu\.?mm|c\.mm|cmm|mm3|ul)$")
# A count in thousands, lakhs, or millions per cubic millimetre: "thou/cumm", "10^3/uL", "K/uL", "lakhs/cumm".
_SCALED_COUNT_RE = re.compile(
    r"^(?:(?P<thou>thou|thousands?|k|x?10\^?3|x?10³)|(?P<lakh>lakhs?)|(?P<mill>mill|millions?|x?10\^?6|x?10⁶))"
    r"(?:cells?)?/(?:cu\.?mm|c\.mm|cmm|mm3|ul)$"
)
# Different spellings of one unit: a micro-unit per mL is a milli-unit per L.
_SAME_UNIT = {'uiu/ml': 'miu/l', 'iu/l': 'u/l'}


def normalize_unit(unit: object) -> str:
    """A unit's spelling for comparisons: case, spaces, micro signs, and cubic millimetre spellings ignored."""
    text = re.sub(r"\s+", "", str(unit or '').casefold()).replace('µ', 'u').replace('μ', 'u').replace('mcg', 'ug')
    if _CUBIC_MM_RE.match(text):
        return '/ul'  # a cubic millimetre is a microlitre
    scaled = _SCALED_COUNT_RE.match(text)
    if scaled:
        return f"{scaled.lastgroup}/ul"
    return _SAME_UNIT.get(text, text)


def trend_points(results: Iterable[Any], test_type: Any = None) -> tuple[str, list[dict[str, Any]]]:
    """The trend's unit and one point per result (value, unit, status, reference range, and the printed ones)."""
    results = list(results)
    counts = Counter(normalize_unit(result.unit) for result in results if normalize_unit(result.unit))
    if not counts:
        return '', [_point(result, SAME) for result in results]

    default = _default_unit(test_type)
    target = max(counts, key=lambda unit: (counts[unit], unit == default))
    label = Counter(
        (result.unit or '').strip() for result in results if normalize_unit(result.unit) == target
    ).most_common(1)[0][0]
    factors = _factors(test_type)

    points = []
    for result in results:
        unit = normalize_unit(result.unit)
        if not unit or unit == target:
            points.append(_point(result, SAME))
            continue
        factor = factors.get((unit, target))
        value = _convert_value(result.value, factor) if factor is not None else None
        if value is None:
            points.append(_point(result, UNCONVERTED))
            continue
        points.append({
            **_point(result, CONVERTED),
            'value': value,
            'unit': label,
            'reference_range': _convert_range(result.reference_range, factor),
        })
    return label, points


def _point(result: Any, unit_status: str) -> dict[str, Any]:
    return {
        'value': result.value,
        'unit': result.unit or '',
        'status': result.status,
        'reference_range': result.reference_range or '',
        'original_value': result.value,
        'original_unit': result.unit or '',
        'original_reference_range': result.reference_range or '',
        'unit_status': unit_status,
    }


def _default_unit(test_type: Any) -> str | None:
    if test_type is None or not test_type.default_unit:
        return None
    unit = LabTestUnit.objects.filter(name=test_type.default_unit).first()
    return normalize_unit(unit.symbol or unit.name) if unit else normalize_unit(test_type.default_unit)


def _factors(test_type: Any) -> dict[tuple[str, str], Decimal]:
    """Conversion factors for this test, keyed by (from, to) unit spelling; units are known by symbol or name."""
    if test_type is None:
        return {}
    factors: dict[tuple[str, str], Decimal] = {}
    conversions = UnitConversion.objects.filter(test_type=test_type, is_active=True).select_related('from_unit', 'to_unit')
    for conversion in conversions:
        for source in {normalize_unit(conversion.from_unit.symbol), normalize_unit(conversion.from_unit.name)} - {''}:
            for target in {normalize_unit(conversion.to_unit.symbol), normalize_unit(conversion.to_unit.name)} - {''}:
                factors.setdefault((source, target), conversion.conversion_factor)
    return factors


def _convert_value(value: object, factor: Decimal) -> str | None:
    match = _VALUE_RE.match(str(value or ''))
    if not match:
        return None
    number = _scale(match.group(2), factor)
    return None if number is None else f"{match.group(1) or ''}{number}"


def _convert_range(reference_range: object, factor: Decimal) -> str:
    """The range in the new unit, or blank when it is not a plain "low - high" or "< limit" range."""
    text = str(reference_range or '')
    match = _RANGE_RE.match(text)
    if match:
        low, high = _scale(match.group(1), factor), _scale(match.group(2), factor)
        return f"{low} - {high}" if low is not None and high is not None else ''
    match = _BOUND_RE.match(text)
    if match:
        limit = _scale(match.group(2), factor)
        return f"{match.group(1)} {limit}" if limit is not None else ''
    return ''


def _scale(number: str, factor: Decimal) -> str | None:
    try:
        scaled = Decimal(number.replace(',', '')) * factor
    except InvalidOperation:
        return None
    magnitude = abs(scaled)
    places = 3 if magnitude < 1 else 2 if magnitude < 100 else 1 if magnitude < 1000 else 0
    text = f"{scaled:.{places}f}"
    return text.rstrip('0').rstrip('.') if '.' in text else text
