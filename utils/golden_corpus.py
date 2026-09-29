"""
Golden pathology corpus scoring.

Compares parser output to manually reviewed expected analytes in
`samples/pathology-reports/golden/golden-index.json`.

Used by:
- Django regression tests (`utils.tests_golden_corpus`)
- `manage.py evaluate_golden_corpus` for full re-scores after parser changes
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Optional

# Repo root = parent of utils/
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN_INDEX = REPO_ROOT / "samples/pathology-reports/golden/golden-index.json"
DEFAULT_BASELINE = REPO_ROOT / "samples/pathology-reports/golden/baseline-summary.json"

# Fast CI smoke set: currently parse well (baseline OK) and are small PDFs.
SMOKE_REPORT_CODES = (
    "B001",
    "B002",
    "H001",
    "H002",
    "H003",
    "sample_blood_test",
)

# Blank interim reports that must stay empty (no false positives).
SMOKE_EMPTY_CODES = (
    "A001",
    "Z024",
    "Z025",
    "Z029",
)

# Units that indicate DLC-style percentage vs ALC absolute counts.
_PERCENT_UNITS = frozenset({"%"})
_ABSOLUTE_UNITS = frozenset(
    {
        "thou/mm3",
        "mill/mm3",
        "k/ul",
        "cells/ul",
        "/ul",
        "/µl",
        "/μl",
        "cells/µl",
        "cells/μl",
        "cells/cu.mm",
        "million/cu.mm",
        "mill/cumm",
        "mil/ul",
        "thou/ul",
        "/c.mm",
        "thou/cu.mm",
        "mill/cu.mm",
        "/cu.mm",
    }
)


@dataclass
class MatchRow:
    expected_name: str
    expected_value: str
    parsed_name: str
    parsed_value: str
    name_score: float
    value_ok: bool


@dataclass
class ReportScore:
    report_code: str
    source_pdf: str
    categories: list[str]
    report_state: str
    expected: int
    parsed: int
    matched: int
    recall_pct: float
    precision_pct: float
    value_acc_pct: float
    flag: str
    missing: list[dict[str, Any]] = field(default_factory=list)
    extras: list[dict[str, Any]] = field(default_factory=list)
    value_mismatches: list[dict[str, str]] = field(default_factory=list)
    parser: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def repo_path(relative: str | Path) -> Path:
    return REPO_ROOT / relative


def load_golden_index(path: Path | None = None) -> dict[str, Any]:
    index_path = path or DEFAULT_GOLDEN_INDEX
    if not index_path.is_file():
        raise FileNotFoundError(f"Golden index not found: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def load_baseline(path: Path | None = None) -> dict[str, Any]:
    baseline_path = path or DEFAULT_BASELINE
    if not baseline_path.is_file():
        raise FileNotFoundError(f"Baseline summary not found: {baseline_path}")
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def norm_name(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9%./<>+\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_value(s: str | None) -> str:
    s = (s or "").strip().lower().replace(",", "")
    return re.sub(r"\s+", "", s)


def norm_unit(s: str | None) -> str:
    u = (s or "").strip().lower()
    u = u.replace("µ", "u").replace("μ", "u")
    u = re.sub(r"\s+", "", u)
    aliases = {
        "ug/dl": "ug/dl",
        "mcg/dl": "ug/dl",
        "gm/dl": "g/dl",
        "cells/ul": "cells/ul",
        "k/ul": "k/ul",
        "/hpf": "/hpf",
    }
    return aliases.get(u, u)


def units_match(expected: str | None, parsed: str | None) -> bool:
    eu, pu = norm_unit(expected), norm_unit(parsed)
    if not eu:
        return True
    if not pu:
        return False
    return eu == pu or eu in pu or pu in eu


def unit_family(unit: str | None) -> str:
    """Classify units for DLC % vs ALC absolute-count disambiguation."""
    u = norm_unit(unit)
    if u in _PERCENT_UNITS:
        return "percent"
    if u in _ABSOLUTE_UNITS or u.endswith("/mm3") or u.endswith("/cu.mm"):
        return "absolute"
    return "other"


def section_context_matches_unit(section_context: str | None, unit: str | None) -> bool:
    """True when parser section context aligns with the expected unit family."""
    fam = unit_family(unit)
    ctx = (section_context or "").strip().lower()
    if fam == "percent" and ctx == "dlc":
        return True
    if fam == "absolute" and ctx == "alc":
        return True
    return False


def candidate_match_score(
    expected: dict[str, Any],
    parsed_row: dict[str, Any],
    name_score: float,
) -> float:
    """
    Rank parser rows for a golden expected analyte.

    Combines fuzzy name match with unit agreement and DLC/ALC context hints.
    """
    score = name_score
    exp_unit = expected.get("unit") or ""
    parsed_unit = parsed_row.get("unit") or ""

    if units_match(exp_unit, parsed_unit):
        score += 0.15
    elif unit_family(exp_unit) != "other":
        parsed_fam = unit_family(parsed_unit)
        if parsed_unit and parsed_fam != "other" and parsed_fam != unit_family(exp_unit):
            score -= 0.35

    if section_context_matches_unit(parsed_row.get("section_context"), exp_unit):
        score += 0.2

    return score


def values_match(expected: str | None, parsed: str | None) -> bool:
    ev, pv = norm_value(expected), norm_value(parsed)
    if not ev and not pv:
        return True
    if ev == pv:
        return True
    if ev and pv and (ev in pv or pv in ev):
        return True
    try:
        e_num = float(re.sub(r"[^0-9.+-]", "", ev))
        p_num = float(re.sub(r"[^0-9.+-]", "", pv))
        return abs(e_num - p_num) < 0.011
    except Exception:
        return False


def best_name_match(
    name: str,
    candidates: Iterable[str],
    threshold: float = 0.55,
) -> tuple[Optional[str], float]:
    nn = norm_name(name)
    best: Optional[str] = None
    best_score = 0.0
    for candidate in candidates:
        cn = norm_name(candidate)
        score = SequenceMatcher(None, nn, cn).ratio()
        if nn and nn in cn:
            score = max(score, 0.9)
        if cn and cn in nn:
            score = max(score, 0.85)
        if score > best_score:
            best_score = score
            best = candidate
    if best is not None and best_score >= threshold:
        return best, best_score
    return None, best_score


def parsed_name_candidates(parsed_row: dict[str, Any]) -> list[str]:
    """Names emitted for one row, including its source label when canonicalized."""
    candidates = [
        parsed_row.get("raw_test_name"),
        parsed_row.get("test_name"),
        parsed_row.get("display_name"),
    ]
    return [str(value) for value in candidates if value]


def classify_score(
    expected_n: int,
    parsed_n: int,
    matched: int,
    recall: float,
    value_acc: float,
) -> str:
    if expected_n == 0 and parsed_n == 0:
        return "OK_EMPTY"
    if expected_n == 0 and parsed_n > 0:
        return "FALSE_POSITIVE"
    if matched == 0 and expected_n > 0:
        return "MISS_ALL"
    if recall >= 80 and value_acc >= 70:
        return "OK"
    if recall >= 40:
        return "PARTIAL"
    return "WEAK"


def score_report(
    golden_report: dict[str, Any],
    parsed_results: list[dict[str, Any]],
    *,
    parser_name: str = "",
) -> ReportScore:
    """Score one golden report against a list of parser result dicts."""
    expected = list(golden_report.get("expected_results") or [])
    parsed = list(parsed_results or [])
    used: set[int] = set()
    matches: list[MatchRow] = []
    missing: list[dict[str, Any]] = []
    extras: list[dict[str, Any]] = []
    value_mismatches: list[dict[str, str]] = []

    for exp in expected:
        exp_name = exp.get("test_name") or ""
        exp_unit = exp.get("unit") or ""

        ranked: list[tuple[int, float, float]] = []
        for i, p in enumerate(parsed):
            if i in used:
                continue
            _, name_score = best_name_match(exp_name, parsed_name_candidates(p))
            if name_score < 0.55:
                continue
            total = candidate_match_score(exp, p, name_score)
            ranked.append((i, total, name_score))
        ranked.sort(key=lambda t: (t[1], t[2]), reverse=True)

        if not ranked:
            missing.append(
                {
                    "test_name": exp.get("test_name"),
                    "value": exp.get("value"),
                    "unit": exp.get("unit"),
                }
            )
            continue

        idx = ranked[0][0]
        used.add(idx)
        p = parsed[idx]
        ok = values_match(exp.get("value"), p.get("value"))
        _, name_score = best_name_match(exp_name, parsed_name_candidates(p))
        matches.append(
            MatchRow(
                expected_name=exp_name,
                expected_value=str(exp.get("value") or ""),
                parsed_name=str(p.get("test_name") or p.get("display_name") or ""),
                parsed_value=str(p.get("value") or ""),
                name_score=round(name_score, 2),
                value_ok=ok,
            )
        )
        if not ok:
            value_mismatches.append(
                {
                    "expected": f"{exp.get('test_name')}={exp.get('value')}",
                    "parsed": f"{p.get('test_name')}={p.get('value')}",
                }
            )

    for i, p in enumerate(parsed):
        if i not in used:
            extras.append(
                {
                    "test_name": p.get("test_name") or p.get("display_name"),
                    "value": p.get("value"),
                }
            )

    exp_n = len(expected)
    got_n = len(parsed)
    hit = len(matches)
    recall = (hit / exp_n * 100.0) if exp_n else (100.0 if got_n == 0 else 0.0)
    precision = (hit / got_n * 100.0) if got_n else (100.0 if exp_n == 0 else 0.0)
    value_ok_n = sum(1 for m in matches if m.value_ok)
    value_acc = (value_ok_n / hit * 100.0) if hit else (100.0 if exp_n == 0 else 0.0)
    flag = classify_score(exp_n, got_n, hit, recall, value_acc)

    return ReportScore(
        report_code=golden_report.get("report_code") or Path(golden_report.get("source_pdf", "")).stem,
        source_pdf=golden_report.get("source_pdf") or "",
        categories=list(golden_report.get("categories") or []),
        report_state=str(golden_report.get("report_state") or ""),
        expected=exp_n,
        parsed=got_n,
        matched=hit,
        recall_pct=round(recall, 1),
        precision_pct=round(precision, 1),
        value_acc_pct=round(value_acc, 1),
        flag=flag,
        missing=missing,
        extras=extras,
        value_mismatches=value_mismatches,
        parser=parser_name,
    )


def parse_pdf_file(pdf_path: Path) -> dict[str, Any]:
    """Run the production hybrid parser on a PDF path."""
    from utils.vlm_pdf_parser import parse_medical_pdf_hybrid

    with pdf_path.open("rb") as fh:
        return parse_medical_pdf_hybrid(fh)


def evaluate_reports(
    reports: list[dict[str, Any]],
    *,
    parse_fn=None,
) -> dict[str, Any]:
    """
    Evaluate a list of golden report entries.

    Returns a comparison-report shaped dict with summary/totals/reports.
    """
    parse = parse_fn or parse_pdf_file
    rows: list[ReportScore] = []
    summary: dict[str, int] = {}

    for golden in reports:
        rel = golden.get("source_pdf") or ""
        pdf_path = repo_path(rel)
        if not pdf_path.is_file():
            score = ReportScore(
                report_code=golden.get("report_code") or pdf_path.stem,
                source_pdf=rel,
                categories=list(golden.get("categories") or []),
                report_state=str(golden.get("report_state") or ""),
                expected=int(golden.get("expected_result_count") or 0),
                parsed=0,
                matched=0,
                recall_pct=0.0,
                precision_pct=0.0,
                value_acc_pct=0.0,
                flag="UPLOAD_MISSING",
                missing=[{"error": f"missing file: {pdf_path}"}],
            )
        else:
            parsed = parse(pdf_path)
            results = list(parsed.get("test_results") or [])
            score = score_report(
                golden,
                results,
                parser_name=str(parsed.get("parser") or ""),
            )
        rows.append(score)
        summary[score.flag] = summary.get(score.flag, 0) + 1

    return {
        "summary": summary,
        "reports": [r.to_dict() for r in rows],
        "totals": {
            "reports": len(rows),
            "expected_results": sum(r.expected for r in rows),
            "parsed_results": sum(r.parsed for r in rows),
            "matched": sum(r.matched for r in rows),
            "value_ok": sum(r.matched - len(r.value_mismatches) for r in rows),
        },
    }


def select_reports(
    index: dict[str, Any],
    codes: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    reports = list(index.get("reports") or [])
    if codes is None:
        return reports
    wanted = set(codes)
    selected = [r for r in reports if r.get("report_code") in wanted]
    missing = wanted - {r.get("report_code") for r in selected}
    if missing:
        raise KeyError(f"Unknown golden report_code(s): {sorted(missing)}")
    return selected


def overall_recall(result: dict[str, Any]) -> float:
    totals = result.get("totals") or {}
    expected = max(int(totals.get("expected_results") or 0), 1)
    matched = int(totals.get("matched") or 0)
    return matched / expected * 100.0


def overall_precision(result: dict[str, Any]) -> float:
    """Matched rows as a share of every parsed row; extra non-result rows lower it."""
    totals = result.get("totals") or {}
    parsed = int(totals.get("parsed_results") or 0)
    if parsed == 0:
        return 100.0
    return int(totals.get("matched") or 0) / parsed * 100.0


def overall_value_accuracy(result: dict[str, Any]) -> float:
    """Matched rows whose parsed value agrees with the golden value."""
    totals = result.get("totals") or {}
    matched = int(totals.get("matched") or 0)
    if matched == 0:
        return 100.0
    return int(totals.get("value_ok") or 0) / matched * 100.0


# (label, scorer, baseline threshold key) for the full-corpus aggregate gates.
AGGREGATE_FLOORS = (
    ("recall", overall_recall, "min_overall_recall_pct"),
    ("precision", overall_precision, "min_overall_precision_pct"),
    ("value accuracy", overall_value_accuracy, "min_overall_value_acc_pct"),
)


def aggregate_floor_violations(
    result: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[str]:
    """Describe each aggregate metric that fell below its baseline floor."""
    violations: list[str] = []
    for label, scorer, key in AGGREGATE_FLOORS:
        floor = float(thresholds[key])
        value = scorer(result)
        if value + 1e-9 < floor:
            violations.append(f"overall {label} {value:.2f}% < {floor}% ({key})")
    return violations


def vendor_breakdown(index: dict[str, Any]) -> dict[str, int]:
    """Count golden reports by source vendor folder (lalpath, other, …)."""
    counts: dict[str, int] = {}
    for report in index.get("reports") or []:
        rel = report.get("source_pdf") or ""
        parts = Path(rel).parts
        vendor = parts[2] if len(parts) >= 3 else "unknown"
        counts[vendor] = counts.get(vendor, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def recall_by_vendor(
    index: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, dict[str, float | int]]:
    """Compute matched/expected recall per vendor folder."""
    code_to_vendor = {}
    for report in index.get("reports") or []:
        rel = report.get("source_pdf") or ""
        parts = Path(rel).parts
        vendor = parts[2] if len(parts) >= 3 else "unknown"
        code = report.get("report_code") or Path(rel).stem
        code_to_vendor[code] = vendor

    stats: dict[str, dict[str, float | int]] = {}
    for row in result.get("reports") or []:
        vendor = code_to_vendor.get(row.get("report_code") or "", "unknown")
        bucket = stats.setdefault(vendor, {"reports": 0, "expected": 0, "matched": 0})
        bucket["reports"] = int(bucket["reports"]) + 1
        bucket["expected"] = int(bucket["expected"]) + int(row.get("expected") or 0)
        bucket["matched"] = int(bucket["matched"]) + int(row.get("matched") or 0)

    for vendor, bucket in stats.items():
        exp = max(int(bucket["expected"]), 1)
        bucket["recall_pct"] = round(int(bucket["matched"]) / exp * 100.0, 1)
    return dict(sorted(stats.items()))


def empty_report_codes(index: dict[str, Any]) -> list[str]:
    """Report codes whose golden oracle expects zero analytes."""
    codes: list[str] = []
    for report in index.get("reports") or []:
        expected = report.get("expected_results") or []
        if len(expected) == 0:
            code = report.get("report_code") or Path(report.get("source_pdf", "")).stem
            codes.append(code)
    return sorted(codes)
