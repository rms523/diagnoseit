from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from utils import report_formats
from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser
from utils.report_formats import (
    REPLACE, SUPPLEMENT, ReportFormat, ReportRow, apply_report_formats, installed_formats, register,
)

EXAMPLE_REPORT = """DiagnoseIt Example Lab - Test Report
Haemoglobin ............ 13.5 g/dL [13.0 - 17.0]
Total Leucocyte Count ............ 12500 /cumm [4000 - 11000]
Blood Group ............ B Positive
"""


class IsolatedRegistry:
    """Give each test its own format registry, so formats registered in a test do not leak."""

    def setUp(self):
        super().setUp()
        saved = list(report_formats._registered)
        self.addCleanup(self._restore, saved)
        report_formats.reset_formats()

    @staticmethod
    def _restore(saved):
        report_formats._registered[:] = saved
        report_formats.reset_formats()


def _format(name, rows, *, mode=REPLACE, priority=0, matches=True, error=None):
    class Format(ReportFormat):
        def matches(self, text):
            return matches

        def parse(self, text):
            if error:
                raise error
            return [ReportRow(test_name=n, value=v) for n, v in rows]

    Format.name, Format.mode, Format.priority = name, mode, priority
    return Format()


def _row(row, format_name):
    return {"test_name": row.test_name, "value": row.value, "report_format": format_name}


class ApplyReportFormatsTests(IsolatedRegistry, SimpleTestCase):
    generic = [{"test_name": "Glucose", "value": "90"}]

    def test_without_matching_formats_the_generic_rows_stand(self):
        formats = [_format("never", [("Hb", "13")], matches=False)]
        self.assertEqual(apply_report_formats("text", self.generic, _row, formats), (self.generic, []))

    def test_highest_priority_replace_format_supplies_the_rows(self):
        formats = sorted(
            [_format("low", [("Hb", "1")], priority=1), _format("high", [("Hb", "2")], priority=5)],
            key=lambda f: -f.priority,
        )
        rows, used = apply_report_formats("text", self.generic, _row, formats)
        self.assertEqual([r["value"] for r in rows], ["2"])
        self.assertEqual(used, ["high"])

    def test_replace_format_without_rows_falls_through_to_the_next(self):
        formats = [_format("empty", []), _format("second", [("Hb", "13")])]
        rows, used = apply_report_formats("text", self.generic, _row, formats)
        self.assertEqual(used, ["second"])
        self.assertEqual(rows[0]["test_name"], "Hb")

    def test_supplement_formats_add_new_rows_to_the_winning_result(self):
        formats = [
            _format("extra", [("Glucose", "90"), ("HbA1c", "5.4")], mode=SUPPLEMENT),
            _format("more", [("Vitamin D", "30")], mode=SUPPLEMENT),
        ]
        rows, used = apply_report_formats("text", self.generic, _row, formats)
        self.assertEqual([r["test_name"] for r in rows], ["Glucose", "HbA1c", "Vitamin D"])
        self.assertEqual(used, ["extra", "more"])

    def test_a_failing_format_is_skipped(self):
        formats = [_format("broken", [], error=ValueError("bad layout")), _format("ok", [("Hb", "13")])]
        with self.assertLogs("utils.report_formats", "ERROR"):
            rows, used = apply_report_formats("text", self.generic, _row, formats)
        self.assertEqual(used, ["ok"])

    def test_register_rejects_formats_without_a_name_or_with_an_unknown_mode(self):
        class Nameless(ReportFormat):
            pass

        class Odd(ReportFormat):
            name, mode = "odd", "merge"

        with self.assertRaises(ValueError):
            register(Nameless)
        with self.assertRaises(ValueError):
            register(Odd)

    def test_formats_are_loaded_from_the_formats_directory(self):
        with TemporaryDirectory() as directory:
            Path(directory, "acme.py").write_text(
                "from utils.report_formats import ReportFormat, register\n"
                "@register\n"
                "class Acme(ReportFormat):\n"
                "    name = 'acme'\n"
                "    priority = 3\n",
                encoding="utf-8",
            )
            Path(directory, "_draft.py").write_text("raise RuntimeError('skipped')\n", encoding="utf-8")
            Path(directory, "broken.py").write_text("import not_a_module\n", encoding="utf-8")
            with patch.dict("os.environ", {"REPORT_FORMATS_DIR": directory}), self.assertLogs(
                "utils.report_formats", "ERROR"
            ) as logs:
                names = [f.name for f in installed_formats()]
        self.assertIn("acme", names)
        self.assertTrue(any("broken.py" in line for line in logs.output))


class ExampleReportFormatTests(IsolatedRegistry, TestCase):
    """The bundled example format, end to end through the text parser and the lab catalog."""

    @classmethod
    def setUpTestData(cls):
        call_command("populate_lab_tests", stdout=StringIO())

    def _parse(self, text):
        parser = EnhancedMedicalPDFParser()
        return apply_report_formats(text, parser.extract_test_results(text), parser._report_format_row)

    def test_example_lab_report_is_read_by_its_format(self):
        rows, used = self._parse(EXAMPLE_REPORT)

        self.assertEqual(used, ["example-lab"])
        by_name = {row["raw_test_name"]: row for row in rows}
        self.assertEqual(set(by_name), {"Haemoglobin", "Total Leucocyte Count", "Blood Group"})
        hb = by_name["Haemoglobin"]
        self.assertEqual((hb["value"], hb["unit"], hb["reference_range"]), ("13.5", "g/dL", "13.0 - 17.0"))
        self.assertEqual(hb["test_name"], "hemoglobin")
        self.assertEqual(hb["status"], "NORMAL")
        self.assertEqual(by_name["Total Leucocyte Count"]["status"], "HIGH")
        self.assertEqual(by_name["Blood Group"]["value"], "B Positive")
        self.assertIsNone(hb["line_number"])

    def test_other_reports_are_left_to_the_generic_parser(self):
        text = "Hemoglobin 13.5 g/dL 13.0 - 17.0\n"
        parser = EnhancedMedicalPDFParser()
        generic = parser.extract_test_results(text)

        rows, used = self._parse(text)

        self.assertEqual(used, [])
        self.assertEqual(rows, generic)
