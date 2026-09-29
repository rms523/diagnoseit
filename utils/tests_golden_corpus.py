"""
Golden corpus regression tests.

They need the sample report corpus under samples/, which is kept private and not published, and are
skipped without it. With the corpus: `make test-golden`, `make test-golden-full`, or
`manage.py evaluate_golden_corpus`.
"""

from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pdfplumber
from django.test import SimpleTestCase, TestCase
from django.core.management import call_command

from utils.golden_corpus import (
    AGGREGATE_FLOORS,
    DEFAULT_BASELINE,
    DEFAULT_GOLDEN_INDEX,
    REPO_ROOT,
    SMOKE_EMPTY_CODES,
    SMOKE_REPORT_CODES,
    aggregate_floor_violations,
    empty_report_codes,
    evaluate_reports,
    load_baseline,
    load_golden_index,
    overall_precision,
    overall_recall,
    overall_value_accuracy,
    recall_by_vendor,
    select_reports,
    vendor_breakdown,
)
from utils.scanned_corpus import (
    DEFAULT_SCANNED_INDEX,
    SCAN_VARIANTS,
    load_scanned_index,
    materialize_scanned_reports,
)


def _corpus_available() -> bool:
    """True when the private sample corpus (samples/, not published) and all its PDFs are present."""
    if not DEFAULT_GOLDEN_INDEX.is_file():
        return False
    return all(
        (REPO_ROOT / report["source_pdf"]).is_file()
        for report in load_golden_index()["reports"]
    )


# Hybrid parser reads USE_VLM_PARSER from the process env (not Django settings).
_DISABLE_VLM = patch.dict(os.environ, {"USE_VLM_PARSER": "false"}, clear=False)


class PopulatedLabCatalogTestCase(TestCase):
    """Run parser regressions against the catalog used by real deployments."""

    @classmethod
    def setUpTestData(cls):
        call_command("populate_lab_tests", stdout=StringIO())


class AggregateScoringTests(SimpleTestCase):
    """Aggregate metric and floor checks that do not need the PDF corpus."""

    THRESHOLDS = {
        "min_overall_recall_pct": 94.0,
        "min_overall_precision_pct": 74.0,
        "min_overall_value_acc_pct": 95.0,
    }

    @staticmethod
    def _result(expected, parsed, matched, value_ok):
        return {
            "totals": {
                "expected_results": expected,
                "parsed_results": parsed,
                "matched": matched,
                "value_ok": value_ok,
            }
        }

    def test_frozen_baseline_totals_pass_every_floor(self):
        result = self._result(expected=516, parsed=653, matched=496, value_ok=484)

        self.assertEqual(aggregate_floor_violations(result, self.THRESHOLDS), [])

    def test_extra_rows_fail_precision_even_when_recall_holds(self):
        result = self._result(expected=516, parsed=700, matched=496, value_ok=484)

        violations = aggregate_floor_violations(result, self.THRESHOLDS)

        self.assertGreater(overall_recall(result), self.THRESHOLDS["min_overall_recall_pct"])
        self.assertEqual(len(violations), 1)
        self.assertIn("precision", violations[0])

    def test_wrong_values_fail_value_accuracy(self):
        result = self._result(expected=516, parsed=653, matched=496, value_ok=460)

        violations = aggregate_floor_violations(result, self.THRESHOLDS)

        self.assertEqual(len(violations), 1)
        self.assertIn("value accuracy", violations[0])

    def test_evaluate_reports_totals_value_ok_and_extras(self):
        golden = {
            "report_code": "synthetic",
            # Any existing repo file works: parse_fn replaces PDF parsing below.
            "source_pdf": "utils/golden_corpus.py",
            "expected_results": [
                {"test_name": "Hemoglobin", "value": "13.2", "unit": "g/dL"},
                {"test_name": "Platelet Count", "value": "250", "unit": ""},
            ],
        }
        parsed_rows = [
            {"test_name": "Hemoglobin", "value": "13.2", "unit": "g/dL"},
            {"test_name": "Platelet Count", "value": "999", "unit": ""},
            {"test_name": "Reference interval", "value": "12-16", "unit": ""},
        ]

        result = evaluate_reports([golden], parse_fn=lambda _path: {"test_results": parsed_rows})

        self.assertEqual(
            result["totals"],
            {"reports": 1, "expected_results": 2, "parsed_results": 3, "matched": 2, "value_ok": 1},
        )
        self.assertAlmostEqual(overall_precision(result), 200 / 3)
        self.assertAlmostEqual(overall_value_accuracy(result), 50.0)


@unittest.skipUnless(_corpus_available(), "private sample corpus not present")
@_DISABLE_VLM
class GoldenCorpusSmokeTests(PopulatedLabCatalogTestCase):
    """Fast regression guards for known-good and known-empty reports."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.index = load_golden_index()
        cls.baseline = load_baseline() if DEFAULT_BASELINE.is_file() else None

    def test_smoke_ok_reports_keep_high_recall(self):
        reports = select_reports(self.index, SMOKE_REPORT_CODES)
        result = evaluate_reports(reports)
        by_code = {r["report_code"]: r for r in result["reports"]}

        for code in SMOKE_REPORT_CODES:
            row = by_code[code]
            self.assertIn(
                row["flag"],
                {"OK", "PARTIAL"},
                msg=f"{code} regressed to {row['flag']} (recall={row['recall_pct']}%)",
            )
            self.assertGreaterEqual(
                row["recall_pct"],
                80.0,
                msg=f"{code} recall {row['recall_pct']}% < 80%",
            )
            self.assertGreaterEqual(
                row["value_acc_pct"],
                70.0,
                msg=f"{code} value accuracy {row['value_acc_pct']}% < 70%",
            )

    def test_smoke_precision_not_below_floor(self):
        """Extra non-result rows (reference bands, method notes) must not creep in."""
        if self.baseline is None:
            self.skipTest("baseline-summary.json missing")
        result = evaluate_reports(select_reports(self.index, SMOKE_REPORT_CODES))
        precision = overall_precision(result)
        floor = float(self.baseline["thresholds"]["smoke_min_precision_pct"])
        extras = {r["report_code"]: len(r["extras"]) for r in result["reports"] if r["extras"]}
        self.assertGreaterEqual(
            precision,
            floor,
            msg=f"smoke precision {precision:.2f}% < {floor}% (extra rows by report: {extras})",
        )

    def test_smoke_blank_interim_stay_empty(self):
        reports = select_reports(self.index, SMOKE_EMPTY_CODES)
        result = evaluate_reports(reports)
        for row in result["reports"]:
            self.assertEqual(
                row["flag"],
                "OK_EMPTY",
                msg=(
                    f"{row['report_code']} should stay empty but got "
                    f"flag={row['flag']} parsed={row['parsed']} extras={row['extras'][:3]}"
                ),
            )
            self.assertEqual(
                row["parsed"],
                0,
                msg=f"{row['report_code']} emitted {row['parsed']} false-positive row(s): {row['extras'][:5]}",
            )

    def test_smoke_empty_codes_match_baseline(self):
        if self.baseline is None:
            self.skipTest("baseline-summary.json missing")
        baseline_empty = set(self.baseline.get("ok_empty_report_codes") or [])
        self.assertEqual(set(SMOKE_EMPTY_CODES), baseline_empty)

    def test_baseline_file_matches_committed_totals(self):
        """Sanity-check the frozen baseline metadata used for full-eval comparisons."""
        if self.baseline is None:
            self.skipTest("baseline-summary.json missing")
        self.assertEqual(self.baseline.get("schema_version"), 1)
        index = load_golden_index()
        self.assertEqual(self.baseline["totals"]["reports"], index["report_count"])
        self.assertEqual(self.baseline["totals"]["expected_results"], index["total_expected_results"])
        self.assertIn("OK", self.baseline["summary"])
        self.assertIn("smoke_report_codes", self.baseline)
        self.assertEqual(set(SMOKE_REPORT_CODES), set(self.baseline["smoke_report_codes"]))
        thresholds = self.baseline["thresholds"]
        for _, _, key in AGGREGATE_FLOORS:
            self.assertIn(key, thresholds)
        self.assertIn("smoke_min_precision_pct", thresholds)


@unittest.skipUnless(
    _corpus_available() and DEFAULT_SCANNED_INDEX.is_file(),
    "scanned corpus index not present",
)
@_DISABLE_VLM
class ScannedCorpusDerivationTests(PopulatedLabCatalogTestCase):
    """Scan derivatives carry no text layer, and the text parser invents nothing on them."""

    def test_index_references_golden_reports_and_known_variants(self):
        scanned_index = load_scanned_index()
        codes = [row["report_code"] for row in scanned_index["reports"]]

        self.assertTrue(scanned_index["variants"])
        self.assertLessEqual(set(scanned_index["variants"]), set(SCAN_VARIANTS))
        self.assertEqual(len(select_reports(load_golden_index(), codes)), len(set(codes)))
        for _, _, key in AGGREGATE_FLOORS:
            self.assertIn(key, scanned_index["thresholds"])

    def test_derivatives_are_image_only_and_legacy_parser_emits_no_rows(self):
        scanned_index = load_scanned_index()
        with TemporaryDirectory() as out_dir:
            entries = materialize_scanned_reports(
                load_golden_index(), scanned_index, Path(out_dir)
            )
            self.assertEqual(
                len(entries),
                len(scanned_index["reports"]) * len(scanned_index["variants"]),
            )
            for entry in entries:
                with pdfplumber.open(entry["source_pdf"]) as pdf:
                    chars = sum(len(page.chars) for page in pdf.pages)
                self.assertEqual(chars, 0, msg=f"{entry['report_code']} kept a text layer")

            result = evaluate_reports(entries)

        extras = {r["report_code"]: r["extras"][:3] for r in result["reports"] if r["extras"]}
        self.assertEqual(
            result["totals"]["parsed_results"],
            0,
            msg=f"legacy parser invented rows on image-only scans: {extras}",
        )


@unittest.skipUnless(
    _corpus_available() and os.environ.get("GOLDEN_FULL") == "1",
    "set GOLDEN_FULL=1 to run the full golden evaluation",
)
@_DISABLE_VLM
class GoldenCorpusFullTests(PopulatedLabCatalogTestCase):
    """
    Full corpus gate. Opt-in because it parses dozens of PDFs.

    Parses the corpus once per class, then asserts overall recall, precision, and
    value accuracy stay at or above the frozen baseline floors.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.index = load_golden_index()
            cls.baseline = load_baseline()
            # The class decorator only patches test methods, so pin the parser here too.
            with _DISABLE_VLM:
                cls.result = evaluate_reports(list(cls.index["reports"]))
        except Exception:
            cls.tearDownClass()
            raise

    def test_full_corpus_aggregate_metrics_not_below_baseline(self):
        violations = aggregate_floor_violations(self.result, self.baseline["thresholds"])
        self.assertEqual(
            violations,
            [],
            msg=f"summary={self.result['summary']} totals={self.result['totals']}",
        )

    def test_full_corpus_baseline_ok_reports_not_miss_all(self):
        by_code = {r["report_code"]: r for r in self.result["reports"]}
        for code in sorted(self.baseline.get("ok_report_codes") or []):
            self.assertNotEqual(
                by_code[code]["flag"],
                "MISS_ALL",
                msg=f"baseline OK report {code} became MISS_ALL",
            )

    def test_full_corpus_blank_reports_have_no_false_positives(self):
        empty_codes = set(empty_report_codes(self.index))
        self.assertGreaterEqual(len(empty_codes), 4)
        rows = [r for r in self.result["reports"] if r["report_code"] in empty_codes]
        self.assertEqual(len(rows), len(empty_codes))
        for row in rows:
            self.assertEqual(row["parsed"], 0, msg=f"{row['report_code']} false positives: {row['extras'][:3]}")
            self.assertEqual(row["flag"], "OK_EMPTY")

    def test_full_corpus_vendor_recall_tracked(self):
        by_vendor = recall_by_vendor(self.index, self.result)
        overall_floor = float(self.baseline["thresholds"]["min_overall_recall_pct"])
        vendor_floor = float(
            self.baseline["thresholds"].get("min_vendor_recall_pct") or overall_floor
        )
        min_n = int(self.baseline["thresholds"].get("min_vendor_reports_for_floor") or 5)
        for vendor, bucket in by_vendor.items():
            n = int(bucket["reports"])
            self.assertGreater(n, 0, msg=f"{vendor} missing from eval")
            if n < min_n:
                continue
            self.assertGreaterEqual(
                float(bucket["recall_pct"]),
                vendor_floor,
                msg=(
                    f"{vendor} recall {bucket['recall_pct']}% < {vendor_floor}% "
                    f"across {n} reports (generic n>={min_n} vendor floor)"
                ),
            )


@unittest.skipUnless(
    _corpus_available() and os.environ.get("GOLDEN_FULL") == "1",
    "set GOLDEN_FULL=1 to run vendor coverage checks",
)
@_DISABLE_VLM
class GoldenCorpusVendorCoverageTests(TestCase):
    """
    Track vendor skew in the golden corpus.

    Does not fail on Lal Path dominance — documents it so we expand fixtures later.
    """

    def test_golden_corpus_has_non_lalpath_reports(self):
        index = load_golden_index()
        breakdown = vendor_breakdown(index)
        non_lal = sum(n for vendor, n in breakdown.items() if vendor != "lalpath")
        self.assertGreaterEqual(
            non_lal,
            2,
            msg=f"Need vendor diversity beyond Lal Path; got {breakdown}",
        )

    def test_lalpath_dominance_is_documented(self):
        index = load_golden_index()
        breakdown = vendor_breakdown(index)
        total = sum(breakdown.values())
        lal_pct = breakdown.get("lalpath", 0) / max(total, 1) * 100.0
        # Informational guard: METHODOLOGY.md must document the vendor skew.
        coverage_doc = DEFAULT_GOLDEN_INDEX.parent / "METHODOLOGY.md"
        self.assertTrue(coverage_doc.is_file(), msg="Add golden/METHODOLOGY.md documenting vendor skew")
        text = coverage_doc.read_text(encoding="utf-8")
        self.assertIn("lalpath", text.lower())
        if lal_pct > 90:
            self.assertIn("skew", text.lower())


def _vlm_available_for_golden() -> bool:
    if os.environ.get("GOLDEN_VLM") != "1":
        return False
    if not _corpus_available():
        return False
    os.environ.setdefault("USE_VLM_PARSER", "true")
    from utils.vlm_pdf_parser import _vlm_reachable, _use_vlm_parser

    return _use_vlm_parser() and _vlm_reachable()


@unittest.skipUnless(
    _vlm_available_for_golden(),
    "set GOLDEN_VLM=1 with reachable VLM (USE_VLM_PARSER + Ollama/OpenAI) to run",
)
class GoldenCorpusVlmSmokeTests(TestCase):
    """Opt-in smoke eval with VLM/OCR enabled (production-like hybrid path)."""

    def test_vlm_smoke_recall_not_below_legacy_floor(self):
        index = load_golden_index()
        baseline = load_baseline()
        reports = select_reports(index, SMOKE_REPORT_CODES)
        result = evaluate_reports(reports)
        recall = overall_recall(result)
        floor = float(baseline["thresholds"]["smoke_min_recall_pct"])
        self.assertGreaterEqual(
            recall,
            floor,
            msg=f"VLM smoke recall {recall:.1f}% < {floor}% (summary={result['summary']})",
        )


@unittest.skipUnless(
    DEFAULT_SCANNED_INDEX.is_file() and _vlm_available_for_golden(),
    "set GOLDEN_VLM=1 with reachable VLM (USE_VLM_PARSER + Ollama/OpenAI) to run",
)
class GoldenCorpusScannedVlmTests(PopulatedLabCatalogTestCase):
    """
    Opt-in OCR gate on image-only scan derivatives (about two minutes per page).

    Scores the scanned corpus once per class against `scanned-index.json` thresholds.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.scanned_index = load_scanned_index()
            with TemporaryDirectory() as out_dir:
                entries = materialize_scanned_reports(
                    load_golden_index(), cls.scanned_index, Path(out_dir)
                )
                cls.result = evaluate_reports(entries)
        except Exception:
            cls.tearDownClass()
            raise

    def test_scanned_aggregate_metrics_not_below_floors(self):
        violations = aggregate_floor_violations(self.result, self.scanned_index["thresholds"])
        self.assertEqual(
            violations,
            [],
            msg=f"summary={self.result['summary']} totals={self.result['totals']}",
        )

    def test_every_clean_scan_is_read_by_ocr(self):
        # Phone variants are covered by the aggregate floors only: three currently fail
        # deterministically (OCR server errors or unparsed OCR text).
        clean_rows = [r for r in self.result["reports"] if r["report_code"].endswith("@clean")]
        self.assertTrue(clean_rows)
        for row in clean_rows:
            self.assertNotEqual(
                row["parser"],
                "legacy",
                msg=f"{row['report_code']} fell back to the text parser; OCR did not run",
            )
            self.assertNotEqual(
                row["flag"],
                "MISS_ALL",
                msg=f"{row['report_code']} matched nothing (missing={row['missing'][:3]})",
            )
