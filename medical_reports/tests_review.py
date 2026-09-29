"""Parsed report editing APIs: adding and deleting results, and AI review suggestions."""

import base64
import json
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ai_settings.models import AIServiceConfig
from lab_tests.models import LabTestType
from medical_reports.ai_review import pending_review
from medical_reports.models import MedicalReport, TestResult
from medical_reports.tasks import cancel_review_task, parse_report_task, review_report_task
from utils.report_review import ReportReviewError, RowLocation, locate_rows, plan_parts

User = get_user_model()

REPORT_PAGES = [[
    "HAEMATOLOGY",
    "Hemoglobin 14.5 g/dL 13.0 - 17.0",
    "Platelet Count 250 10^3/uL 150 - 400",
    "Interpretation: Non-Diabetic <5.7 Pre-Diabetic 5.7 - 6.4 Diabetic 6.5 or more",
    "MCV 90 fL 80 - 100",
]]


def _client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


class TestResultEditingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.other = User.objects.create_user(username="someone-else", password="testpass123")
        self.client = _client_for(self.user)
        self.report = MedicalReport.objects.create(
            user=self.user, title="CBC", report_date=date(2026, 5, 14), file="medical_reports/cbc.pdf"
        )
        LabTestType.objects.create(name="hemoglobin", display_name="Hemoglobin", default_unit="g_dl")

    def test_adding_catalog_result_returns_full_row(self):
        response = self.client.post(
            f"/api/medical-reports/reports/{self.report.id}/test-results/",
            {"test_name": "Hemoglobin", "value": "13.5", "unit": "g/dL", "reference_range": "13.0 - 17.0"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.data["test_name"], response.data["test_type_name"]), ("Hemoglobin", "hemoglobin"))
        self.assertTrue(TestResult.objects.filter(pk=response.data["id"], report=self.report).exists())

    def test_adding_custom_result_is_stored_without_catalog_link(self):
        response = self.client.post(
            f"/api/medical-reports/reports/{self.report.id}/test-results/",
            {"test_name": "Anti-Mullerian Hormone", "value": "2.1", "unit": "ng/mL"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["test_type_name"])
        self.assertIsNone(TestResult.objects.get(pk=response.data["id"]).test_type)

    def test_deleting_result_is_owner_only(self):
        mine = TestResult.objects.create(report=self.report, test_name="Hemoglobin", value="13.5")
        theirs_report = MedicalReport.objects.create(
            user=self.other, title="Theirs", report_date=date(2026, 5, 1), file="medical_reports/theirs.pdf"
        )
        theirs = TestResult.objects.create(report=theirs_report, test_name="Hemoglobin", value="12.0")

        self.assertEqual(
            self.client.delete(f"/api/medical-reports/reports/{self.report.id}/test-results/{mine.id}/").status_code,
            204,
        )
        self.assertEqual(
            self.client.delete(f"/api/medical-reports/reports/{theirs_report.id}/test-results/{theirs.id}/").status_code,
            404,
        )
        self.assertFalse(TestResult.objects.filter(pk=mine.pk).exists())
        self.assertTrue(TestResult.objects.filter(pk=theirs.pk).exists())


class ReportAIReviewTests(TestCase):
    def setUp(self):
        cache.clear()
        media_root = TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        media_override = override_settings(MEDIA_ROOT=media_root.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.user = User.objects.create_user(username="reviewer", password="testpass123")
        self.other = User.objects.create_user(username="stranger", password="testpass123")
        self.client = _client_for(self.user)
        self.report = MedicalReport.objects.create(
            user=self.user,
            title="CBC",
            report_date=date(2026, 5, 14),
            file=SimpleUploadedFile("cbc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        )
        self.hemoglobin = TestResult.objects.create(
            report=self.report, test_name="Hemoglobin", value="13.5", unit="g/dL", reference_range="13.0 - 17.0"
        )
        self.band = TestResult.objects.create(report=self.report, test_name="Non-Diabetic", value="<5.7")
        other_report = MedicalReport.objects.create(
            user=self.other, title="Theirs", report_date=date(2026, 5, 1), file="medical_reports/theirs.pdf"
        )
        self.their_result = TestResult.objects.create(report=other_report, test_name="HbA1c", value="9.1")
        self.other_report = other_report
        LabTestType.objects.create(name="platelet_count", display_name="Platelet Count", default_unit="thou_ul")
        self.url = f"/api/medical-reports/reports/{self.report.id}/ai-review/"
        self.detail_url = f"/api/medical-reports/reports/{self.report.id}/"
        self.status_url = f"/api/medical-reports/reports/{self.report.id}/status/"

    def _configure(self, review_input="text", auto_review=False, auto_apply=False, temperature=None):
        AIServiceConfig.objects.create(
            role="report_review",
            base_url="http://llm.local:8080/v1",
            model="reviewer-model",
            review_input=review_input,
            auto_review=auto_review,
            auto_apply=auto_apply,
            temperature=temperature,
        )

    def _review(self, options=None):
        """Ask for a review, run the queued task inline as the worker would, and return the stored review."""
        with patch(
            "medical_reports.tasks.review_report_task.apply_async",
            side_effect=lambda args, task_id: review_report_task(*args),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, options or {}, format="json")
        self.assertEqual((response.status_code, response.data["status"]), (202, "pending"))
        return self.client.get(self.detail_url).data["ai_review"]

    def _store_review(self, suggestions):
        self.report.ai_review = {"status": "completed", "run_id": "abc", "suggestions": suggestions}
        self.report.save()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": ""})
    def test_requires_configuration(self):
        response = self.client.post(self.url, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.data["error"])

    @patch("medical_reports.tasks.review_report_task.apply_async")
    def test_other_users_report_is_not_reviewed(self, mock_delay):
        self._configure()
        other_url = f"/api/medical-reports/reports/{self.other_report.id}/ai-review/"

        self.assertEqual(self.client.post(other_url, format="json").status_code, 404)
        self.assertEqual(self.client.delete(other_url).status_code, 404)
        self.assertEqual(self.client.post(f"{other_url}accept/", {"ids": [1]}, format="json").status_code, 404)
        self.assertEqual(self.client.post(f"{other_url}applied/1/undo/", format="json").status_code, 404)
        mock_delay.assert_not_called()

    @patch("utils.report_review._extract_page_lines", return_value=REPORT_PAGES)
    @patch("utils.report_review.chat_json")
    def test_review_runs_in_the_background_and_stores_valid_suggestions_without_applying(self, mock_chat, _lines):
        self._configure()
        mock_chat.return_value = json.dumps({
            "summary": "One value differs, one row is a reference band, one result is missing.",
            "suggestions": [
                {"action": "update", "result_id": self.hemoglobin.id, "value": "14.5", "unit": "g/dL", "reason": "Printed 14.5"},
                {"action": "update", "result_id": self.their_result.id, "value": "1.0", "reason": "Not this report"},
                {"action": "remove", "result_id": self.band.id, "reason": "Interpretation band"},
                {"action": "add", "test_name": "Platelet Count", "value": "250", "unit": "10^3/uL", "status": "normal"},
                {"action": "add", "test_name": "hemoglobin", "value": "13.5", "reason": "Duplicate of an existing row"},
                {"action": "rewrite", "result_id": self.hemoglobin.id},
            ],
        })

        review = self._review()

        self.assertEqual(
            (review["status"], review["input_mode"], review["model"], review["parts"], review["failed_parts"]),
            ("completed", "text", "reviewer-model", 1, []),
        )
        self.assertEqual(
            review["suggestions"],
            [
                # The report prints 14.5, not the parsed 13.5, so this row's own line was not found.
                {
                    "id": 1, "action": "update", "result_id": self.hemoglobin.id, "changes": {"value": "14.5"},
                    "reason": "Printed 14.5", "row_seen": False,
                },
                {"id": 2, "action": "remove", "result_id": self.band.id, "reason": "Interpretation band", "row_seen": True},
                {
                    "id": 3,
                    "action": "add",
                    "result": {"test_name": "Platelet Count", "value": "250", "unit": "10^3/uL", "reference_range": "", "status": "NORMAL"},
                    "catalog_name": "Platelet Count",
                    "reason": "",
                },
            ],
        )
        self.assertEqual(review["applied"], [])
        self.assertNotIn("run_id", review)
        prompt = mock_chat.call_args.args[1][1]["content"]
        self.assertIn("Hemoglobin 14.5 g/dL", prompt)
        self.assertNotIn("HbA1c", prompt)
        self.assertNotIn("[REVIEW START]", prompt)
        self.hemoglobin.refresh_from_db()
        self.assertEqual(self.hemoglobin.value, "13.5")
        self.assertEqual(TestResult.objects.filter(report=self.report).count(), 2)

    @patch("utils.report_review._page_image", return_value=b"page")
    @patch("utils.report_review._page_count", return_value=6)
    @patch("utils.report_review._extract_page_lines", return_value=[])
    @patch("utils.report_review.chat_json", return_value='{"suggestions": []}')
    def test_scanned_report_is_reviewed_as_page_images_in_parts(self, mock_chat, _lines, _count, _image):
        self._configure(review_input="auto")

        review = self._review()

        self.assertEqual((review["input_mode"], review["parts"]), ("images", 3))
        requests_sent = [call.args[1][1]["content"] for call in mock_chat.call_args_list]
        # At most four images per request: two pages under review and a neighbouring page on each side.
        self.assertEqual([len(content) - 1 for content in requests_sent], [3, 4, 3])
        self.assertEqual(
            requests_sent[0][1]["image_url"]["url"], f"data:image/png;base64,{base64.b64encode(b'page').decode()}"
        )
        self.assertIn("read from pages 3 to 4", requests_sent[1][0]["text"])
        # Rows with no known page are reviewed once, in the first part.
        self.assertIn('"test_name": "Hemoglobin"', requests_sent[0][0]["text"])
        self.assertNotIn('"test_name": "Hemoglobin"', requests_sent[1][0]["text"])

    @patch("utils.report_review.CONTEXT_LINES", 1)
    @patch("utils.report_review.PART_TEXT_CHARS", 80)
    @patch("utils.report_review.chat_json")
    def test_long_report_is_reviewed_in_parts_with_context_across_page_breaks(self, mock_chat):
        self._configure()
        platelets = TestResult.objects.create(report=self.report, test_name="Platelet Count", value="250")
        leucocytes = TestResult.objects.create(report=self.report, test_name="Total Leucocyte Count", value="6.56")
        pages = [
            ["Hemoglobin 13.5 g/dL 13.0 - 17.0", "Non-Diabetic <5.7"],
            ["Platelet Count 250 10^3/uL 150 - 400 MPV 9.1", "Total Leucocyte Count"],
            ["6.56 thou/mm3 4.00 - 10.00", "End of report"],
        ]
        self.report.parsed_data = {
            "text": "\n".join(line for page in pages for line in page),
            "test_results": [
                {"result_id": result.id, "line_number": line}
                for line, result in enumerate([self.hemoglobin, self.band, platelets, leucocytes])
            ],
        }
        self.report.save()
        mock_chat.side_effect = [
            json.dumps({"summary": "Part one.", "suggestions": [
                {"action": "remove", "result_id": self.band.id, "reason": "Reference band"},
                {"action": "add", "test_name": "platelet count", "value": "250", "reason": "Already a row"},
                {"action": "add", "test_name": "Mean Platelet Volume", "value": "9.1", "unit": "fL"},
                {"action": "remove", "result_id": leucocytes.id, "reason": "Not a row of this part"},
            ]}),
            json.dumps({"summary": "Part two.", "suggestions": [
                {"action": "add", "test_name": "mean platelet volume", "value": "9.1", "reason": "Also in the overlap"},
                {"action": "update", "result_id": leucocytes.id, "unit": "thou/mm3", "reason": "Unit on the next page"},
            ]}),
            "Sorry, the reply was cut off",
        ]

        with patch("utils.report_review._extract_page_lines", return_value=pages):
            review = self._review()

        self.assertEqual((review["parts"], review["summary"]), (3, "Part one. Part two."))
        self.assertEqual(
            [(item["id"], item["action"], item.get("result_id"), item.get("row_seen")) for item in review["suggestions"]],
            [(1, "remove", self.band.id, True), (2, "add", None, None), (3, "update", leucocytes.id, True)],
        )
        self.assertEqual(
            review["failed_parts"],
            [{"part": 3, "first_page": 3, "last_page": 3, "error": "The review model did not return valid JSON."}],
        )
        prompts = [call.args[1][1]["content"] for call in mock_chat.call_args_list]
        self.assertNotIn('"test_name": "Total Leucocyte Count"', prompts[0])
        self.assertIn('"test_name": "Total Leucocyte Count"', prompts[1])
        self.assertIn("part 2 of 3", prompts[1])
        # The value printed at the top of the next page is shown right after the part as context.
        self.assertIn("Total Leucocyte Count\n[REVIEW END]\n6.56 thou/mm3", prompts[1])

    @patch("utils.report_review.chat_json")
    def test_prompt_leaves_out_personal_details_and_boilerplate_but_keeps_result_lines(self, mock_chat):
        self._configure()
        self.user.first_name, self.user.last_name = "Anita", "Rao"
        self.user.save()
        pages = [[
            "Name : ANITA RAO Age : 45 Years Gender : Female",
            "Hemoglobin 13.5 g/dL 13.0 - 17.0",
            "Kindly correlate clinically",
            "Page 1 of 1",
            "Non-Diabetic <5.7 Please correlate clinically",
        ]]
        # A "correct" verdict stores no suggestions, whatever else the reply lists.
        mock_chat.return_value = json.dumps({
            "verdict": "correct",
            "summary": "All rows match.",
            "suggestions": [{"action": "remove", "result_id": self.band.id, "reason": "Contradicts the verdict"}],
        })

        with patch("utils.report_review._extract_page_lines", return_value=pages):
            review = self._review()

        prompt = mock_chat.call_args.args[1][1]["content"]
        self.assertIn("Name : [REDACTED] Age : 45 Years Gender : Female", prompt)
        self.assertNotIn("ANITA", prompt)
        self.assertNotIn("Kindly correlate clinically", prompt)
        self.assertNotIn("Page 1 of 1", prompt)
        self.assertIn("Non-Diabetic <5.7 Please correlate clinically", prompt)
        self.assertEqual(mock_chat.call_args.kwargs["temperature"], 0.1)
        self.assertEqual((review["summary"], review["suggestions"]), ("All rows match.", []))

    @patch("utils.report_review._extract_page_lines", return_value=REPORT_PAGES)
    @patch("utils.report_review.chat_json")
    def test_suggestions_that_change_nothing_or_use_unprinted_values_are_dropped(self, mock_chat, _lines):
        self._configure(temperature=0.7)
        LabTestType.objects.create(name="hemoglobin", display_name="Hemoglobin", default_unit="g_dl", aliases=["haemoglobin"])
        self.hemoglobin.status = "NORMAL"
        self.hemoglobin.save()
        mock_chat.return_value = json.dumps({"verdict": "needs_changes", "suggestions": [
            {"action": "update", "result_id": self.hemoglobin.id, "test_name": "HAEMOGLOBIN", "reason": "Printed spelling"},
            {"action": "update", "result_id": self.hemoglobin.id, "reference_range": "13.0-17.0", "reason": "Spacing"},
            {"action": "update", "result_id": self.hemoglobin.id, "status": "", "reason": "No flag printed"},
            {"action": "update", "result_id": self.hemoglobin.id, "value": "15.2", "reason": "Not printed"},
            {"action": "add", "test_name": "Ferritin", "value": "88", "reason": "Not printed"},
            {"action": "update", "result_id": self.hemoglobin.id, "value": "14.5", "reason": "Printed 14.5"},
        ]})

        review = self._review()

        self.assertEqual(
            [(item["action"], item.get("changes")) for item in review["suggestions"]], [("update", {"value": "14.5"})]
        )
        self.assertEqual(mock_chat.call_args.kwargs["temperature"], 0.7)

    @patch("utils.report_review._extract_page_lines", return_value=REPORT_PAGES)
    @patch("utils.report_review.chat_json")
    def test_dismissed_suggestions_are_not_shown_again_by_later_reviews(self, mock_chat, _lines):
        self._configure()
        mock_chat.return_value = json.dumps({"verdict": "needs_changes", "suggestions": [
            {"action": "remove", "result_id": self.band.id, "reason": "Interpretation band"},
            {"action": "update", "result_id": self.hemoglobin.id, "value": "14.5", "reason": "Printed 14.5"},
        ]})

        first = self._review()
        removal = next(item["id"] for item in first["suggestions"] if item["action"] == "remove")
        self.assertEqual(self.client.delete(f"{self.url}suggestions/{removal}/").status_code, 204)
        # Closing the review keeps what was dismissed.
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        second = self._review()

        self.assertEqual([item["action"] for item in second["suggestions"]], ["update"])
        self.assertNotIn("dismissed", second)

    def _configure_ocr(self, enabled=True):
        AIServiceConfig.objects.create(
            role="ocr", base_url="http://ocr.local:8080/v1", model="PaddleOCR-VL-1.6", enabled=enabled
        )

    @patch("utils.report_review._page_count", return_value=1)
    @patch("utils.vlm_pdf_parser._render_page_to_png", return_value=b"page")
    @patch(
        "utils.vlm_pdf_parser._call_openai_vision",
        return_value="<table><tr><td>Hemoglobin</td><td>14.5</td><td>g/dL</td><td>13.0 - 17.0</td></tr></table>Platelet Count 250",
    )
    @patch("utils.report_review._extract_page_lines")
    @patch("utils.report_review.chat_json", return_value='{"verdict": "correct", "suggestions": []}')
    def test_a_review_can_read_the_pages_with_the_ocr_model_instead_of_the_text_layer(
        self, mock_chat, mock_text_layer, mock_vision, _render, _count
    ):
        self._configure(review_input="text")
        self._configure_ocr()

        review = self._review({"ocr": True})

        self.assertEqual((review["status"], review["input_mode"]), ("completed", "ocr"))
        mock_text_layer.assert_not_called()
        self.assertEqual(mock_vision.call_args.args[0], "OCR:")
        prompt = mock_chat.call_args.args[1][1]["content"]
        self.assertIn("Report text:\nHemoglobin 14.5 g/dL 13.0 - 17.0\nPlatelet Count 250", prompt)

    @patch("utils.report_review._page_count", return_value=5)
    @patch("utils.vlm_pdf_parser._render_page_to_png", side_effect=lambda pdf_bytes, index, dpi=None: f"page{index + 1}".encode())
    @patch(
        "utils.vlm_pdf_parser._call_openai_vision",
        side_effect=lambda prompt, image, system_prompt=None, max_tokens=None: f"Result {image.decode()} 1.{image.decode()[-1]}",
    )
    @patch("utils.report_review.chat_json", return_value='{"verdict": "correct", "suggestions": []}')
    def test_ocr_reads_several_pages_at_once_and_keeps_page_order(self, mock_chat, mock_vision, _render, _count):
        self._configure(review_input="text")
        AIServiceConfig.objects.create(
            role="ocr", base_url="http://ocr.local:8080/v1", model="PaddleOCR-VL-1.6", parallel_requests=3
        )

        # Pages 1-3 and then 4-5 go out together; worker threads reuse the loaded settings instead of the database.
        review = self._review({"ocr": True})

        self.assertEqual((review["status"], mock_vision.call_count), ("completed", 5))
        prompt = mock_chat.call_args.args[1][1]["content"]
        self.assertIn(
            "Report text:\nResult page1 1.1\nResult page2 1.2\nResult page3 1.3\nResult page4 1.4\nResult page5 1.5", prompt
        )

    @patch("utils.report_review._page_image", return_value=b"page")
    @patch("utils.report_review._page_count", return_value=1)
    @patch("utils.vlm_pdf_parser._render_page_to_png", return_value=b"page")
    @patch("utils.vlm_pdf_parser._call_openai_vision", return_value="Hemoglobin 14.5 g/dL 13.0 - 17.0")
    @patch("utils.report_review.chat_json", return_value='{"verdict": "correct", "suggestions": []}')
    def test_page_images_can_be_sent_with_their_ocr_text_whatever_the_setting(self, mock_chat, _vision, _render, _count, _image):
        self._configure(review_input="text")
        self._configure_ocr()

        review = self._review({"ocr": True, "images": True})

        self.assertEqual(review["input_mode"], "images_ocr")
        content = mock_chat.call_args.args[1][1]["content"]
        self.assertEqual([item["type"] for item in content], ["text", "image_url"])
        self.assertIn("Text read from these pages by OCR", content[0]["text"])
        self.assertIn("Hemoglobin 14.5 g/dL 13.0 - 17.0", content[0]["text"])

    @patch("utils.report_review._page_image", return_value=b"page")
    @patch("utils.report_review._page_count", return_value=1)
    @patch("utils.report_review._extract_page_lines", return_value=REPORT_PAGES)
    @patch("utils.report_review.chat_json", return_value='{"verdict": "correct", "suggestions": []}')
    def test_page_images_option_overrides_a_text_setting(self, mock_chat, _lines, _count, _image):
        self._configure(review_input="text")

        review = self._review({"images": True})

        self.assertEqual(review["input_mode"], "images")
        content = mock_chat.call_args.args[1][1]["content"]
        self.assertEqual([item["type"] for item in content], ["text", "image_url"])
        self.assertNotIn("Text read from these pages by OCR", content[0]["text"])

    @patch("medical_reports.tasks.review_report_task.apply_async")
    def test_the_ocr_option_needs_report_ocr_to_be_set_up(self, mock_queue):
        self._configure()
        self._configure_ocr(enabled=False)

        response = self.client.post(self.url, {"ocr": True}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertIn("Report OCR is not set up", response.data["error"])
        mock_queue.assert_not_called()
        self.assertEqual(self.client.get("/api/ai-settings/status/").data["ocr"], {"available": False})

    @patch("utils.report_review._extract_page_lines", return_value=REPORT_PAGES)
    def test_model_failures_are_stored_as_a_readable_error(self, _lines):
        self._configure()
        for side_effect, expected in [
            (RuntimeError("connection refused"), "did not respond (RuntimeError)"),
            (None, "did not return valid JSON"),
        ]:
            with self.subTest(expected=expected), patch("utils.report_review.chat_json") as mock_chat:
                if side_effect:
                    mock_chat.side_effect = side_effect
                else:
                    mock_chat.return_value = "Sorry, I cannot help with that."
                review = self._review()

                self.assertEqual(review["status"], "failed")
                self.assertIn(expected, review["error"])

    @patch("utils.report_review._extract_page_lines", return_value=REPORT_PAGES)
    @patch("utils.report_review.chat_json")
    def test_safe_fixes_apply_automatically_only_for_rows_the_model_was_shown(self, mock_chat, _lines):
        self._configure(auto_apply=True)
        platelets = TestResult.objects.create(report=self.report, test_name="Platelet Count", value="250")
        vitamin_d = TestResult.objects.create(report=self.report, test_name="Vitamin D", value="30", unit="ng/mL")
        mock_chat.return_value = json.dumps({"suggestions": [
            {"action": "remove", "result_id": self.band.id, "reason": "Reference band"},
            {"action": "update", "result_id": platelets.id, "unit": "10^3/uL", "reference_range": "150 - 400"},
            {"action": "update", "result_id": self.hemoglobin.id, "value": "14.5", "reason": "Value changes wait"},
            {"action": "remove", "result_id": vitamin_d.id, "reason": "Not printed in this report"},
            {"action": "update", "result_id": platelets.id, "value": "400", "status": "HIGH", "reason": "Mixed change"},
            {"action": "add", "test_name": "MCV", "value": "90", "unit": "fL"},
        ]})

        review = self._review()

        self.assertEqual([change["id"] for change in review["applied"]], [1, 2])
        self.assertTrue(all(change["automatic"] for change in review["applied"]))
        self.assertEqual([item["id"] for item in review["suggestions"]], [3, 4, 5, 6])
        self.assertFalse(TestResult.objects.filter(pk=self.band.pk).exists())
        platelets.refresh_from_db()
        self.assertEqual((platelets.unit, platelets.reference_range, platelets.value), ("10^3/uL", "150 - 400", "250"))
        self.hemoglobin.refresh_from_db()
        self.assertEqual(self.hemoglobin.value, "13.5")
        self.assertTrue(TestResult.objects.filter(pk=vitamin_d.pk).exists())

        response = self.client.post(f"{self.url}applied/1/undo/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(TestResult.objects.filter(report=self.report, test_name="Non-Diabetic", value="<5.7").exists())
        self.assertEqual([change["id"] for change in response.data["review"]["applied"]], [2])

    @patch("medical_reports.tasks.review_report_task.apply_async")
    def test_accepted_suggestions_apply_together_and_can_be_undone(self, _delay):
        self._store_review([
            {"id": 1, "action": "update", "result_id": self.hemoglobin.id, "changes": {"value": "14.5"}, "reason": "Misread"},
            {"id": 2, "action": "remove", "result_id": self.band.id, "reason": "Reference band"},
            {
                "id": 3,
                "action": "add",
                "result": {"test_name": "Platelet Count", "value": "250", "unit": "10^3/uL", "reference_range": "", "status": "NORMAL"},
                "catalog_name": "Platelet Count",
                "reason": "",
            },
            {"id": 4, "action": "update", "result_id": self.band.id, "changes": {"unit": "%"}, "reason": "Row is removed first"},
        ])

        self.assertEqual(self.client.post(f"{self.url}accept/", {"ids": "1,2"}, format="json").status_code, 400)
        response = self.client.post(f"{self.url}accept/", {"ids": [1, 2, 3, 4, 99]}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["applied"], [1, 2, 3])
        self.assertEqual(
            [(row["test_name"], row["value"], row["test_type_name"]) for row in response.data["test_results"]],
            [("Hemoglobin", "14.5", None), ("Platelet Count", "250", "platelet_count")],
        )
        self.assertEqual(response.data["review"]["suggestions"], [])
        self.assertEqual(
            [(change["id"], change["automatic"]) for change in response.data["review"]["applied"]],
            [(1, False), (2, False), (3, False)],
        )

        self.assertEqual(self.client.post(f"{self.url}applied/2/undo/", format="json").status_code, 200)
        self.assertEqual(self.client.post(f"{self.url}applied/1/undo/", format="json").status_code, 200)
        self.hemoglobin.refresh_from_db()
        self.assertEqual(self.hemoglobin.value, "13.5")
        self.assertTrue(TestResult.objects.filter(report=self.report, test_name="Non-Diabetic").exists())

        # An undo never overwrites an edit made after the change.
        TestResult.objects.filter(report=self.report, test_name="Platelet Count").update(value="260")
        conflict = self.client.post(f"{self.url}applied/3/undo/", format="json")
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("edited after it was added", conflict.data["error"])
        self.assertTrue(TestResult.objects.filter(report=self.report, test_name="Platelet Count").exists())
        self.assertEqual(self.client.post(f"{self.url}applied/1/undo/", format="json").status_code, 409)

    def test_report_shows_only_suggestions_still_open(self):
        add = {"test_name": "hemoglobin", "value": "13.5", "unit": "", "reference_range": "", "status": ""}
        self._store_review([
            {"id": 1, "action": "update", "result_id": self.hemoglobin.id, "changes": {"value": "14.5", "unit": "g/dL"}, "reason": ""},
            {"id": 2, "action": "update", "result_id": self.hemoglobin.id, "changes": {"unit": "g/dL"}, "reason": "Accepted"},
            {"id": 3, "action": "remove", "result_id": 999999, "reason": "Row was deleted"},
            {"id": 4, "action": "add", "result": add, "catalog_name": None, "reason": "Accepted"},
            {"id": 5, "action": "remove", "result_id": self.band.id, "reason": ""},
        ])

        review = self.client.get(self.detail_url).data["ai_review"]

        self.assertEqual([item["id"] for item in review["suggestions"]], [1, 5])
        self.assertEqual(review["suggestions"][0]["changes"], {"value": "14.5"})
        self.assertNotIn("run_id", review)

    @patch("medical_reports.views.cancel_review_task")
    def test_stopping_a_review_discards_it_and_revokes_its_task(self, mock_cancel):
        self._configure()
        self.report.ai_review = pending_review()
        self.report.save()
        run_id = self.report.ai_review["run_id"]
        other_url = f"/api/medical-reports/reports/{self.other_report.id}/ai-review/stop/"

        self.assertEqual(self.client.post(other_url, format="json").status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"{self.url}stop/", format="json")

        self.assertEqual(response.status_code, 204)
        mock_cancel.assert_called_once_with(run_id)
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_review, {})
        self.assertEqual(self.client.post(f"{self.url}stop/", format="json").status_code, 409)
        # A worker that still picks the task up skips it instead of reviewing.
        with patch("utils.report_review.review_report") as mock_review:
            review_report_task(self.report.id, run_id)
        mock_review.assert_not_called()
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_review, {})

    def test_cancelling_a_review_task_terminates_it_if_running(self):
        with patch.object(review_report_task.app.control, "revoke") as mock_revoke:
            cancel_review_task("run-123")
        mock_revoke.assert_called_once_with("run-123", terminate=True)

        with patch.object(review_report_task.app.control, "revoke", side_effect=ConnectionError("broker down")):
            cancel_review_task("run-456")  # logged, not raised

    @patch("medical_reports.tasks.review_report_task.apply_async")
    def test_selected_reports_are_queued_for_review_in_order(self, mock_queue):
        url = "/api/medical-reports/reports/bulk-ai-review/"
        self.assertEqual(self.client.post(url, {"ids": "1,2"}, format="json").status_code, 400)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": ""}):
            self.assertEqual(self.client.post(url, {"ids": [self.report.id]}, format="json").status_code, 503)
        self._configure()

        def report(title, **fields):
            return MedicalReport.objects.create(
                user=self.user, title=title, report_date=date(2026, 5, 1), file=f"medical_reports/{title}.pdf", **fields
            )

        first, second, third = (report(f"parsed-{n}", status="COMPLETED") for n in range(3))
        parsing = report("parsing", status="PROCESSING")
        under_review = report("under-review", status="COMPLETED", ai_review=pending_review())
        ids = [third.id, parsing.id, first.id, self.other_report.id, under_review.id, second.id, first.id]

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"ids": ids}, format="json")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["queued"], [third.id, first.id, second.id])
        self.assertEqual(
            [item["id"] for item in response.data["skipped"]], [parsing.id, self.other_report.id, under_review.id]
        )
        self.assertEqual([call.args[0][0] for call in mock_queue.call_args_list], [third.id, first.id, second.id])
        for queued in (first, second, third):
            queued.refresh_from_db()
            self.assertEqual(queued.ai_review["status"], "pending")

    def test_report_list_summarizes_each_review(self):
        for title in ("queued", "running", "unreviewed"):
            MedicalReport.objects.create(
                user=self.user, title=title, report_date=date(2026, 5, 1), file=f"medical_reports/{title}.pdf"
            )
        MedicalReport.objects.filter(title="queued").update(ai_review=pending_review())
        MedicalReport.objects.filter(title="running").update(
            ai_review={**pending_review(), "started_at": timezone.now().isoformat()}
        )
        self._store_review([
            {"id": 1, "action": "remove", "result_id": self.band.id, "reason": ""},
            {"id": 2, "action": "update", "result_id": self.hemoglobin.id, "changes": {"unit": "g/dL"}, "reason": "Applied"},
        ])

        response = self.client.get("/api/medical-reports/reports/")

        summaries = {row["title"]: row["ai_review_summary"] for row in response.data["results"]}
        self.assertEqual(
            summaries,
            {
                "CBC": {"status": "completed", "started": False, "open_suggestions": 1},
                "queued": {"status": "pending", "started": False, "open_suggestions": 0},
                "running": {"status": "pending", "started": True, "open_suggestions": 0},
                "unreviewed": {"status": "", "started": False, "open_suggestions": 0},
            },
        )

    def test_dismissing_a_suggestion_and_closing_the_review(self):
        self._store_review([
            {"id": 1, "action": "remove", "result_id": self.band.id, "reason": ""},
            {"id": 2, "action": "update", "result_id": self.hemoglobin.id, "changes": {"value": "14.5"}, "reason": ""},
        ])

        self.assertEqual(self.client.delete(f"{self.url}suggestions/1/").status_code, 204)
        other_url = f"/api/medical-reports/reports/{self.other_report.id}/ai-review/suggestions/1/"
        self.assertEqual(self.client.delete(other_url).status_code, 404)
        self.report.refresh_from_db()
        self.assertEqual([item["id"] for item in self.report.ai_review["suggestions"]], [2])

        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertIsNone(self.client.get(self.detail_url).data["ai_review"])

    @patch("medical_reports.tasks.review_report_task.apply_async")
    def test_running_review_blocks_another_until_it_is_lost(self, mock_delay):
        self._configure()
        self.report.ai_review = pending_review()
        self.report.save()

        self.assertEqual(self.client.post(self.url, format="json").status_code, 409)
        self.assertEqual(self.client.get(self.status_url).data["ai_review_status"], "pending")
        mock_delay.assert_not_called()

        # Waiting behind other reports is not a failure; a review that started and never finished is.
        self.report.ai_review["queued_at"] = (timezone.now() - timedelta(hours=2)).isoformat()
        self.report.save()
        self.assertEqual(self.client.get(self.status_url).data["ai_review_status"], "pending")
        self.report.ai_review["started_at"] = (timezone.now() - timedelta(hours=2)).isoformat()
        self.report.save()
        self.assertEqual(self.client.get(self.status_url).data["ai_review_status"], "failed")
        self.assertEqual(self.client.get(self.detail_url).data["ai_review"]["status"], "failed")

        self.report.ai_review = {**pending_review(), "queued_at": (timezone.now() - timedelta(hours=25)).isoformat()}
        self.report.save()
        self.assertEqual(self.client.get(self.status_url).data["ai_review_status"], "failed")

    @patch("medical_reports.tasks.parse_report_task.delay")
    def test_upload_forms_pass_their_ai_review_choice_to_parsing(self, mock_parse_delay):
        def pdf(name):
            return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")

        with self.captureOnCommitCallbacks(execute=True):
            bulk = self.client.post(
                "/api/medical-reports/reports/bulk-upload/",
                {"files": [pdf("2026-05-01_lab.pdf"), pdf("2026-05-02_lab.pdf")], "ai_review": "true"},
                format="multipart",
            )
            single = self.client.post(
                "/api/medical-reports/reports/",
                {"title": "CBC", "report_type": "LAB", "report_date": "2026-05-03", "file": pdf("cbc.pdf"), "ai_review": "false"},
                format="multipart",
            )
            no_choice = self.client.post(
                "/api/medical-reports/reports/",
                {"title": "Lipids", "report_type": "LAB", "report_date": "2026-05-04", "file": pdf("lipids.pdf")},
                format="multipart",
            )

        self.assertEqual((bulk.status_code, single.status_code, no_choice.status_code), (200, 201, 201))
        self.assertEqual([call.kwargs["review"] for call in mock_parse_delay.call_args_list], [True, True, False, None])

    @patch("medical_reports.tasks.review_report_task.apply_async")
    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_parsing_follows_the_upload_choice_over_the_automatic_setting(self, mock_parse, mock_review_delay):
        mock_parse.return_value = {"test_results": [{"test_name": "Hemoglobin", "value": "13.5"}]}
        self._configure(auto_review=False)

        with self.captureOnCommitCallbacks(execute=True):
            parse_report_task(self.report.id, review=True)
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_review["status"], "pending")
        mock_review_delay.assert_called_once()

        AIServiceConfig.objects.filter(role="report_review").update(auto_review=True)
        mock_review_delay.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            parse_report_task(self.report.id, review=False)
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_review, {})
        mock_review_delay.assert_not_called()

    @patch("medical_reports.tasks.review_report_task.apply_async")
    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_parsing_queues_a_review_when_automatic_review_is_on(self, mock_parse, mock_delay):
        self._configure(auto_review=True)
        mock_parse.return_value = {
            "text": "Hemoglobin 13.5 g/dL",
            "test_results": [
                {"test_name": "Hemoglobin", "value": "13.5", "line_number": 0},
                {"test_name": "unknown", "value": "x", "confidence": 0.2},
            ],
        }

        with self.captureOnCommitCallbacks(execute=True):
            parse_report_task(self.report.id)

        self.report.refresh_from_db()
        result = TestResult.objects.get(report=self.report)
        self.assertEqual(self.report.parsed_data["test_results"][0]["result_id"], result.id)
        self.assertNotIn("result_id", self.report.parsed_data["test_results"][1])
        self.assertEqual(self.report.ai_review["status"], "pending")
        run_id = self.report.ai_review["run_id"]
        mock_delay.assert_called_once_with((self.report.id, run_id), task_id=run_id)

    @patch("medical_reports.tasks.review_report_task.apply_async")
    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_reparsing_without_automatic_review_clears_the_old_review(self, mock_parse, mock_delay):
        self._configure()
        self.report.ai_review = {"status": "completed", "run_id": "old", "suggestions": []}
        self.report.save()
        mock_parse.return_value = {"test_results": [{"test_name": "Hemoglobin", "value": "13.5"}]}

        with self.captureOnCommitCallbacks(execute=True):
            parse_report_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_review, {})
        mock_delay.assert_not_called()

    @patch("medical_reports.tasks.review_report_task.apply_async", side_effect=RuntimeError("broker unavailable"))
    @patch("medical_reports.tasks.parse_medical_pdf_hybrid", return_value={"test_results": []})
    def test_review_that_cannot_be_queued_is_shown_as_failed(self, _parse, _delay):
        self._configure(auto_review=True)

        with self.captureOnCommitCallbacks(execute=True):
            parse_report_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual((self.report.status, self.report.ai_review["status"]), ("COMPLETED", "failed"))
        self.assertIn("Could not queue the AI review", self.report.ai_review["error"])

    def test_review_task_stores_the_outcome_only_for_the_current_review(self):
        self._configure(auto_review=True)
        self.report.ai_review = pending_review()
        self.report.save()
        run_id = self.report.ai_review["run_id"]
        completed = {"status": "completed", "summary": "", "suggestions": [], "parts": 1, "failed_parts": []}

        def review_marked_as_started(report, config, **options):
            self.assertIn("started_at", MedicalReport.objects.get(pk=report.pk).ai_review)
            return completed

        with patch("utils.report_review.review_report", side_effect=review_marked_as_started) as mock_review:
            review_report_task(self.report.id, "an-older-run")
            mock_review.assert_not_called()
            review_report_task(self.report.id, run_id)

        self.report.refresh_from_db()
        self.assertEqual((self.report.ai_review["status"], self.report.ai_review["run_id"]), ("completed", run_id))

    def test_review_task_keeps_a_newer_review_and_records_failures(self):
        self._configure(auto_review=True)
        first = pending_review()
        self.report.ai_review = first
        self.report.save()

        def replaced_during_review(report, config, **options):
            MedicalReport.objects.filter(pk=report.pk).update(
                ai_review={"status": "completed", "run_id": "newer", "suggestions": []}
            )
            return {"status": "completed", "suggestions": []}

        with patch("utils.report_review.review_report", side_effect=replaced_during_review):
            review_report_task(self.report.id, first["run_id"])
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_review["run_id"], "newer")

        second = pending_review()
        MedicalReport.objects.filter(pk=self.report.pk).update(ai_review=second)
        failure = ReportReviewError("The review model did not respond (Timeout).")
        with patch("utils.report_review.review_report", side_effect=failure):
            review_report_task(self.report.id, second["run_id"])
        self.report.refresh_from_db()
        self.assertEqual(
            (self.report.ai_review["status"], self.report.ai_review["error"]),
            ("failed", "The review model did not respond (Timeout)."),
        )


class ReviewPartPlanningTests(SimpleTestCase):
    def test_parts_stay_within_text_and_row_budgets(self):
        rows = [{"id": index} for index in range(4)]

        parts = plan_parts([10, 10, 10, 10], [(rows[0], 0), (rows[1], 1), (rows[2], 1), (rows[3], 3)], 25, 10)

        self.assertEqual(
            [(part.start, part.end, [row["id"] for row in part.rows]) for part in parts],
            [(0, 2, [0, 1, 2]), (2, 4, [3])],
        )

    def test_crowded_page_is_shared_and_unplaced_rows_fill_spare_room(self):
        rows = [{"id": index} for index in range(5)]

        parts = plan_parts([1, 1], [(rows[0], 0), (rows[1], 0), (rows[2], 0), (rows[3], None), (rows[4], 7)], 2, 2)

        self.assertEqual(
            [(part.start, part.end, [row["id"] for row in part.rows]) for part in parts],
            [(0, 1, [0, 1, 4]), (0, 2, [2, 3])],
        )

    def test_rows_are_located_by_parser_position_then_name_and_value_then_text(self):
        page_lines = [["Haemoglobin 13.5 g/dL", "Platelet Count 250"], ["Serum Creatinine 1.1 mg/dL"]]
        parsed = {
            "text": "\n".join(line for page in page_lines for line in page),
            "test_results": [
                {"result_id": 1, "line_number": 0, "test_name": "hemoglobin", "display_name": "Hemoglobin", "value": "13.5"},
                {"test_name": "platelet_count", "display_name": "Platelet Count", "value": "250", "line_number": 1},
                {"test_name": "TSH", "value": "2.0", "page_number": 2},
            ],
        }
        rows = [
            {"id": 1, "test_name": "Hemoglobin", "value": "13.5"},
            {"id": 2, "test_name": "Platelet Count", "value": "250"},
            {"id": 3, "test_name": "Creatinine", "value": "1.1"},
            {"id": 4, "test_name": "TSH", "value": "2.0"},
            {"id": 5, "test_name": "Vitamin D", "value": "30"},
        ]

        self.assertEqual(
            locate_rows(rows, parsed, page_lines),
            {
                1: RowLocation(0, 0),  # the saved row the parser recorded
                2: RowLocation(1, 0),  # parser row with the same name and value
                3: RowLocation(2, 1),  # text line printing the name and value
                4: RowLocation(None, 1),  # only the page is known
                5: RowLocation(None, None),
            },
        )
        # Line numbers counted in different text are not trusted.
        self.assertEqual(locate_rows(rows[:1], {**parsed, "text": "older extraction"}, page_lines)[1], RowLocation(None, None))


class ReviewQueueRoutingTests(SimpleTestCase):
    def test_reviews_run_on_their_own_queue_and_parsing_stays_on_the_default(self):
        router = review_report_task.app.amqp.router
        self.assertEqual(router.route({}, review_report_task.name)["queue"].name, "ai_review")
        self.assertEqual(router.route({}, parse_report_task.name)["queue"].name, "celery")
