from io import BytesIO
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, TestCase
from PIL import Image

from utils.vlm_pdf_parser import (
    _legacy_is_sufficient,
    _merge_parse_results,
    _parse_json_array_from_text,
    _parse_multiline_ocr_text,
    _parse_table_ocr_text,
    _pick_better_paddle_results,
    parse_medical_pdf_hybrid,
)


def _image_only_pdf(pages: int = 1) -> bytes:
    """A blank scanned-style PDF: page images with no embedded text layer."""
    images = [Image.new("RGB", (400, 400), "white") for _ in range(pages)]
    buffer = BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def _http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(
        f"{status_code} Server Error for url: http://10.0.0.5:8080/v1/chat/completions",
        response=response,
    )


class VlmResponseParsingTests(SimpleTestCase):
    def test_parses_json_array_from_markdown_fenced_response(self):
        raw = '```json\n[{"test_name": "Glucose", "value": "90", "unit": "mg/dL", "reference_range": "70-100", "status": "NORMAL"}]\n```'
        results = _parse_json_array_from_text(raw)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["test_name"], "Glucose")
        self.assertEqual(results[0]["status"], "NORMAL")

    def test_parses_multiline_paddle_ocr_text(self):
        text = """Creatinine
1.00
mg/dL
0.70 - 1.30
(Modified Jaffe, Kinetic)
Urea
40.00
mg/dL
13.00 - 43.00"""
        results = _parse_multiline_ocr_text(text)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["test_name"], "Creatinine")
        self.assertEqual(results[0]["value"], "1.00")
        self.assertEqual(results[1]["unit"], "mg/dL")

    def test_parses_qualitative_ocr_value(self):
        text = """HIV I & II
Negative
Negative"""
        results = _parse_multiline_ocr_text(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "Negative")

    def test_parses_latex_style_paddle_ocr_units(self):
        text = """GFR Estimated
99
mL/min/1.73\\( m^2 \\)
\\( >59 \\)"""
        results = _parse_multiline_ocr_text(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], "99")
        self.assertIn("mL/min", results[0]["unit"])
        self.assertIn("59", results[0]["reference_range"])

    def test_parses_markdown_lab_table(self):
        text = """| Test Name | Results | Units | Bio. Ref. Interval |
| --- | --- | --- | --- |
| Creatinine | 1.00 | mg/dL | 0.70 - 1.30 |
| Urea | 40.00 | mg/dL | 13.00 - 43.00 |"""
        results = _parse_table_ocr_text(text)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["test_name"], "Creatinine")
        self.assertEqual(results[0]["value"], "1.00")
        self.assertEqual(results[0]["unit"], "mg/dL")
        self.assertEqual(results[0]["source"], "paddle_table")

    def test_parses_html_lab_table(self):
        text = """
<table>
<tr><th>Test Name</th><th>Results</th><th>Units</th><th>Bio Ref Interval</th></tr>
<tr><td>Hemoglobin</td><td>14.2</td><td>g/dL</td><td>13.0 - 17.0</td></tr>
<tr><td>Glucose</td><td>92</td><td>mg/dL</td><td>70 - 100</td></tr>
</table>
"""
        results = _parse_table_ocr_text(text)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[1]["test_name"], "Glucose")
        self.assertEqual(results[1]["value"], "92")

    def test_pick_better_paddle_results_prefers_richer_table_output(self):
        table_results = [
            {"test_name": "Hb", "value": "14", "unit": "g/dL", "source": "paddle_table"},
            {"test_name": "WBC", "value": "7.2", "unit": "K/uL", "source": "paddle_table"},
        ]
        ocr_results = [{"test_name": "Hb", "value": "14", "unit": "g/dL", "source": "paddle_ocr"}]
        picked = _pick_better_paddle_results(table_results, ocr_results)
        self.assertEqual(len(picked), 2)
        self.assertEqual(picked[0]["source"], "paddle_table")

    def test_pick_better_paddle_results_uses_ocr_when_table_empty(self):
        ocr_results = [{"test_name": "Hb", "value": "14", "unit": "g/dL", "source": "paddle_ocr"}]
        picked = _pick_better_paddle_results([], ocr_results)
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]["source"], "paddle_ocr")


class LegacySufficiencyTests(SimpleTestCase):
    def test_legacy_insufficient_when_many_unparsed_lines(self):
        legacy = {
            "test_results": [{"test_name": "t1"}, {"test_name": "t2"}, {"test_name": "t3"}],
            "text": "\n".join(
                f"Analyte{i} {10 + i}.0 mg/dL 5 - 15" for i in range(20)
            ),
        }
        self.assertFalse(_legacy_is_sufficient(legacy))

    def test_legacy_with_many_tests_is_sufficient(self):
        legacy = {
            "test_results": [{"test_name": f"t{i}"} for i in range(5)],
            "text": "x" * 600,
        }
        self.assertTrue(_legacy_is_sufficient(legacy))

    def test_legacy_with_text_and_one_test_is_sufficient(self):
        legacy = {
            "test_results": [{"test_name": "Glucose"}],
            "text": "x" * 600,
        }
        self.assertTrue(_legacy_is_sufficient(legacy))


class MergeParseResultsTests(SimpleTestCase):
    @patch("utils.parser_normalize.normalize_parsed_results", side_effect=lambda rows: rows)
    def test_merge_keeps_distinct_legacy_and_vlm_rows(self, _normalize):
        legacy = {
            "test_results": [
                {"test_name": "t0", "value": "1"},
                {"test_name": "t1", "value": "2"},
            ],
            "text": "short",
        }
        vlm = {
            "test_results": [{"test_name": "Hb", "value": "14", "unit": "g/dL"}],
            "parser": "vlm-openai-paddle_ocr",
        }
        merged = _merge_parse_results(legacy, vlm)
        self.assertEqual(len(merged["test_results"]), 3)
        self.assertEqual(merged["parser"], "hybrid")


class HybridParserFallbackTests(TestCase):
    @patch("utils.enhanced_pdf_parser.parse_medical_pdf_enhanced")
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=False)
    def test_uses_legacy_when_vlm_unreachable(self, _reachable, mock_legacy):
        mock_legacy.return_value = {
            "test_results": [{"test_name": "Glucose", "value": "90", "unit": "mg/dL"}],
            "parsed_successfully": True,
            "text": "x" * 600,
        }

        result = parse_medical_pdf_hybrid(BytesIO(b"%PDF-1.4"))

        mock_legacy.assert_called_once()
        self.assertEqual(result["parser"], "legacy")

    @patch("utils.enhanced_pdf_parser.parse_medical_pdf_enhanced")
    @patch("utils.vlm_pdf_parser.parse_medical_pdf_with_vlm")
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    def test_skips_vlm_when_legacy_is_sufficient(self, _reachable, mock_vlm, mock_legacy):
        mock_legacy.return_value = {
            "test_results": [{"test_name": f"t{i}"} for i in range(10)],
            "parsed_successfully": True,
            "text": "x" * 1000,
        }

        result = parse_medical_pdf_hybrid(BytesIO(b"%PDF-1.4"))

        mock_vlm.assert_not_called()
        self.assertEqual(result["parser"], "legacy")

    @patch("utils.enhanced_pdf_parser.parse_medical_pdf_enhanced")
    @patch("utils.vlm_pdf_parser.parse_medical_pdf_with_vlm")
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    def test_uses_vlm_when_legacy_finds_nothing(self, _reachable, mock_vlm, mock_legacy):
        mock_legacy.return_value = {
            "test_results": [],
            "parsed_successfully": False,
            "text": "",
        }
        mock_vlm.return_value = {
            "test_results": [{"test_name": "Hb", "value": "14", "unit": "g/dL"}],
            "parsed_successfully": True,
            "parser": "vlm-openai-paddle_ocr",
        }

        result = parse_medical_pdf_hybrid(BytesIO(b"%PDF-1.4"))

        mock_vlm.assert_called_once()
        self.assertEqual(result["parser"], "vlm-openai-paddle_ocr")

    @patch("utils.enhanced_pdf_parser.parse_medical_pdf_enhanced")
    @patch("utils.vlm_pdf_parser.parse_medical_pdf_with_vlm")
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    def test_merges_vlm_rows_when_legacy_is_weak(self, _reachable, mock_vlm, mock_legacy):
        mock_legacy.return_value = {
            "test_results": [{"test_name": f"t{i}"} for i in range(2)],
            "parsed_successfully": True,
            "text": "short",
        }
        mock_vlm.return_value = {
            "test_results": [{"test_name": "Hb", "value": "14", "unit": "g/dL"}],
            "parsed_successfully": True,
            "parser": "vlm-openai-paddle_ocr",
        }

        result = parse_medical_pdf_hybrid(BytesIO(b"%PDF-1.4"))

        mock_vlm.assert_called_once()
        self.assertEqual(result["parser"], "hybrid")
        self.assertEqual(len(result["test_results"]), 3)


class ScannedPdfOcrFailureTests(TestCase):
    """An unreadable scan must surface an error instead of parsing to an empty result."""

    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=False)
    def test_errors_when_ocr_is_disabled(self, _enabled):
        result = parse_medical_pdf_hybrid(BytesIO(_image_only_pdf()))

        self.assertEqual(result["test_results"], [])
        self.assertIn("no text layer", result["error"])
        self.assertIn("OCR is disabled", result["error"])

    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=False)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=True)
    def test_errors_when_ocr_server_is_unreachable(self, _enabled, _reachable):
        result = parse_medical_pdf_hybrid(BytesIO(_image_only_pdf()))

        self.assertIn("the OCR server is unreachable", result["error"])

    @patch("utils.vlm_pdf_parser._call_vlm", side_effect=_http_error(500))
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=True)
    def test_errors_without_internal_urls_when_ocr_fails_every_page(self, _enabled, _reachable, mock_call):
        result = parse_medical_pdf_hybrid(BytesIO(_image_only_pdf(pages=2)))

        self.assertEqual(mock_call.call_count, 2)
        self.assertIn("OCR failed on 2 of 2 page(s) (HTTP 500)", result["error"])
        self.assertNotIn("://", result["error"])
        self.assertNotIn("10.0.0.5", result["error"])

    @patch("utils.vlm_pdf_parser._call_vlm", side_effect=requests.ConnectionError("refused"))
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=True)
    def test_connection_failure_counts_unread_pages_as_failed(self, _enabled, _reachable, mock_call):
        result = parse_medical_pdf_hybrid(BytesIO(_image_only_pdf(pages=3)))

        self.assertEqual(mock_call.call_count, 1)
        self.assertIn("OCR failed on 3 of 3 page(s) (connection failed)", result["error"])

    @patch("utils.vlm_pdf_parser._call_vlm", return_value=[])
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=True)
    def test_blank_scan_read_by_ocr_is_not_an_error(self, _enabled, _reachable, _call):
        result = parse_medical_pdf_hybrid(BytesIO(_image_only_pdf()))

        self.assertEqual(result["test_results"], [])
        self.assertNotIn("error", result)

    @patch("utils.vlm_pdf_parser._call_vlm")
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=True)
    def test_rows_from_readable_pages_are_kept_when_another_page_fails(self, _enabled, _reachable, mock_call):
        mock_call.side_effect = [
            _http_error(500),
            [{"test_name": "Hemoglobin", "value": "14.2", "unit": "g/dL"}],
        ]

        result = parse_medical_pdf_hybrid(BytesIO(_image_only_pdf(pages=2)))

        self.assertNotIn("error", result)
        self.assertEqual(len(result["test_results"]), 1)

    @patch("utils.enhanced_pdf_parser.parse_medical_pdf_enhanced")
    @patch("utils.vlm_pdf_parser._embedded_text_length", return_value=5000)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=False)
    def test_text_pdf_without_rows_is_not_an_error_when_ocr_is_disabled(self, _enabled, _chars, mock_legacy):
        # Blank interim reports carry a text layer and legitimately have no results yet.
        mock_legacy.return_value = {
            "test_results": [],
            "parsed_successfully": False,
            "text": "Result awaited",
        }

        result = parse_medical_pdf_hybrid(BytesIO(b"%PDF-1.4"))

        self.assertEqual(result["test_results"], [])
        self.assertNotIn("error", result)
