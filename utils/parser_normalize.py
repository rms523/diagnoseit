"""
Post-process parser rows through the legacy test-type registry.

VLM/OCR paths emit raw test names; this normalizes them to canonical
LabTestType names when possible (aliases, DLC/ALC context, disambiguation).
"""
from __future__ import annotations

import re
from typing import Any

from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser
from utils.lab_units import PERSON_TITLE_RE, is_qualitative_value, parse_comparable_number


def _infer_context_from_name(raw_name: str) -> str | None:
    name = (raw_name or "").lower()
    if "(dlc)" in name or "dlc)" in name or name.endswith(" %"):
        return "dlc"
    if "(alc)" in name or "alc)" in name or "absolute" in name:
        return "alc"
    if name.startswith("urine ") or " urine" in name:
        return "urine"
    return None


def normalize_parsed_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map raw parser rows to canonical test names where the DB allows."""
    if not results:
        return []

    parser = EnhancedMedicalPDFParser()
    normalized: list[dict[str, Any]] = []

    for row in results:
        raw_name = str(row.get("test_name") or row.get("display_name") or "").strip()
        # Vision models sometimes return the patient's name as a row.
        if not raw_name or PERSON_TITLE_RE.search(raw_name):
            continue

        context = row.get("section_context") or _infer_context_from_name(raw_name)
        lookup_name = re.sub(r"\s*\((dlc|alc)\)\s*$", "", raw_name, flags=re.IGNORECASE)
        lookup_name = re.sub(r"^urine\s+", "", lookup_name, flags=re.IGNORECASE).strip()

        value = str(row.get("value") or "")
        unit = str(row.get("unit") or "")
        ref = str(row.get("reference_range") or "")
        identified = parser._identify_test_type(lookup_name, context=context, unit=unit, value=value)

        if identified and not is_qualitative_value(value):
            identified = parser._disambiguate_test_type(identified, value, unit, ref)

        out = dict(row)
        if identified:
            out["test_name"] = identified.name
            out["display_name"] = identified.display_name
        else:
            out["test_name"] = raw_name
            out["display_name"] = row.get("display_name") or raw_name

        if context:
            out["section_context"] = context

        if ref and not is_qualitative_value(value):
            num = parse_comparable_number(value)
            if num is not None:
                status = parser._status_from_ref_string(str(num), ref)
                if status != "UNKNOWN":
                    out["status"] = status
                elif identified:
                    out["status"] = parser._status_from_db(str(num), unit, identified)

        normalized.append(out)

    return normalized
