"""Tests for async medical report parsing and status API."""

import os
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from medical_reports.models import MedicalReport, TestResult
from medical_reports.tasks import normalize_test_status, parse_report_task
from lab_tests.models import LabTestType

User = get_user_model()


def _fake_pdf(name: str = "report.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class ParseReportTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="parser",
            email="parser@example.com",
            password="testpass123",
        )
        self.report = MedicalReport.objects.create(
            user=self.user,
            title="Lab Report",
            report_date=date(2026, 1, 15),
            file=_fake_pdf(),
            status="PENDING",
        )
        self.creatinine_type = LabTestType.objects.create(
            name="creatinine",
            display_name="Creatinine",
            aliases=["creat"],
            default_unit="mg_dl",
        )

    def test_normalize_test_status(self):
        self.assertEqual(normalize_test_status("NORMAL"), "NORMAL")
        self.assertEqual(normalize_test_status("critical_low"), "LOW")
        self.assertEqual(normalize_test_status("CRITICAL_HIGH"), "HIGH")
        self.assertEqual(normalize_test_status("UNKNOWN"), "")
        self.assertEqual(normalize_test_status("INVALID"), "")
        self.assertEqual(normalize_test_status(""), "")

    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_parse_report_task_creates_results_and_completes(self, mock_parse):
        mock_parse.return_value = {
            "test_results": [
                {
                    "test_name": "Creatinine",
                    "value": "1.1",
                    "unit": "mg/dL",
                    "reference_range": "0.7-1.3",
                    "status": "NORMAL",
                    "confidence": 0.95,
                },
                {
                    "test_name": "unknown",
                    "value": "x",
                    "unit": "",
                    "status": "UNKNOWN",
                    "confidence": 0.2,
                },
                {
                    "test_name": "ALT",
                    "value": "80",
                    "unit": "U/L",
                    "status": "CRITICAL_HIGH",
                    "confidence": 0.9,
                },
            ],
            "parsed_successfully": True,
        }

        parse_report_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "COMPLETED")
        self.assertTrue(self.report.is_parsed)
        self.assertEqual(self.report.parse_error, "")

        results = list(TestResult.objects.filter(report=self.report).order_by("test_name"))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].test_name, "ALT")
        self.assertEqual(results[0].status, "HIGH")
        self.assertEqual(results[1].test_name, "Creatinine")
        self.assertEqual(results[1].status, "NORMAL")
        self.assertEqual(results[1].test_type, self.creatinine_type)

    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_parse_report_task_keeps_processing_status_before_retry(self, mock_parse):
        mock_parse.side_effect = RuntimeError("temporary parser outage")

        with patch.object(parse_report_task, "max_retries", 2):
            # In eager mode Celery re-raises the original exception for retries.
            with self.assertRaises(RuntimeError):
                parse_report_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "PROCESSING")
        self.assertIn("retrying", self.report.parse_error)

    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_parse_report_task_is_idempotent(self, mock_parse):
        mock_parse.return_value = {
            "test_results": [
                {
                    "test_name": "Glucose",
                    "value": "95",
                    "unit": "mg/dL",
                    "status": "NORMAL",
                    "confidence": 0.9,
                }
            ],
            "parsed_successfully": True,
        }

        parse_report_task(self.report.id)
        parse_report_task(self.report.id)

        self.assertEqual(TestResult.objects.filter(report=self.report).count(), 1)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "COMPLETED")

    @patch("medical_reports.tasks.parse_medical_pdf_hybrid")
    def test_parse_report_task_marks_failed_on_error(self, mock_parse):
        mock_parse.side_effect = RuntimeError("ollama unavailable")

        # Force no retries so failure is terminal in this test
        with patch.object(parse_report_task, "max_retries", 0):
            parse_report_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "FAILED")
        self.assertIn("ollama unavailable", self.report.parse_error)
        self.assertEqual(TestResult.objects.filter(report=self.report).count(), 0)

    @staticmethod
    def _image_only_pdf_upload(name="scan.pdf"):
        page = Image.new("RGB", (400, 400), "white")
        buffer = BytesIO()
        page.save(buffer, format="PDF")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")

    def test_parse_report_task_fails_unreadable_scan_with_ocr_reason(self):
        with (
            TemporaryDirectory() as media_root,
            override_settings(MEDIA_ROOT=media_root),
            patch.dict(os.environ, {"USE_VLM_PARSER": "false"}),
            patch.object(parse_report_task, "max_retries", 0),
        ):
            scan = MedicalReport.objects.create(
                user=self.user,
                title="Scanned report",
                report_date=date(2026, 1, 16),
                file=self._image_only_pdf_upload(),
                status="PENDING",
            )
            parse_report_task(scan.id)

        scan.refresh_from_db()
        self.assertEqual(scan.status, "FAILED")
        self.assertFalse(scan.is_parsed)
        self.assertIn("no text layer", scan.parse_error)
        self.assertIn("OCR is disabled", scan.parse_error)
        self.assertEqual(TestResult.objects.filter(report=scan).count(), 0)

    @patch("utils.vlm_pdf_parser._call_vlm")
    @patch("utils.vlm_pdf_parser._vlm_reachable", return_value=True)
    @patch("utils.vlm_pdf_parser._use_vlm_parser", return_value=True)
    def test_parse_report_task_completes_scan_read_by_ocr(self, _enabled, _reachable, mock_call):
        # The text parser reports "Could not extract text" on scans; OCR rows must still be saved.
        mock_call.return_value = [
            {
                "test_name": "Creatinine",
                "value": "1.1",
                "unit": "mg/dL",
                "reference_range": "0.7-1.3",
                "status": "NORMAL",
                "confidence": 0.9,
            }
        ]

        with (
            TemporaryDirectory() as media_root,
            override_settings(MEDIA_ROOT=media_root),
            patch.object(parse_report_task, "max_retries", 0),
        ):
            scan = MedicalReport.objects.create(
                user=self.user,
                title="Scanned report",
                report_date=date(2026, 1, 17),
                file=self._image_only_pdf_upload(),
                status="PENDING",
            )
            parse_report_task(scan.id)

        scan.refresh_from_db()
        self.assertEqual(scan.status, "COMPLETED", msg=scan.parse_error)
        self.assertTrue(scan.is_parsed)
        results = list(TestResult.objects.filter(report=scan))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].test_type, self.creatinine_type)
        self.assertNotIn("error", scan.parsed_data)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class MedicalReportAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="apiuser",
            email="api@example.com",
            password="testpass123",
        )
        self.other = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="testpass123",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    @patch("medical_reports.tasks.parse_report_task.delay")
    def test_create_pdf_report_queues_parse_task(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/medical-reports/reports/",
                {
                    "title": "Upload Test",
                    "report_type": "LAB",
                    "report_date": "2026-02-01",
                    "file": _fake_pdf("2026-02-01-labs.pdf"),
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report_id = response.data["id"]
        self.assertEqual(response.data["status"], "PENDING")
        mock_delay.assert_called_once_with(report_id, review=None)

        signed_url = urlsplit(response.data["file"])
        anonymous = APIClient()
        download = anonymous.get(f"{signed_url.path}?{signed_url.query}")
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        denied = anonymous.get(f"{signed_url.path}?{signed_url.query}x")
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

    @patch("medical_reports.tasks.parse_report_task.delay")
    def test_queue_dispatch_failure_is_persisted(self, mock_delay):
        mock_delay.side_effect = RuntimeError("broker unavailable")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/medical-reports/reports/",
                {
                    "title": "Queue Failure",
                    "report_type": "LAB",
                    "report_date": "2026-02-01",
                    "file": _fake_pdf("queue-failure.pdf"),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = MedicalReport.objects.get(pk=response.data["id"])
        self.assertEqual(report.status, "FAILED")
        self.assertIn("Could not queue", report.parse_error)

    @patch("medical_reports.tasks.parse_report_task.delay")
    def test_create_image_report_is_rejected(self, mock_delay):
        image = SimpleUploadedFile(
            "scan.png",
            b"\x89PNG\r\n\x1a\n",
            content_type="image/png",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/medical-reports/reports/",
                {
                    "title": "Image Report",
                    "report_type": "OTHER",
                    "report_date": "2026-02-01",
                    "file": image,
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_delay.assert_not_called()

    def test_report_status_endpoint_scoped_to_owner(self):
        report = MedicalReport.objects.create(
            user=self.user,
            title="Mine",
            report_date=date(2026, 3, 1),
            file=_fake_pdf(),
            status="PROCESSING",
        )
        other_report = MedicalReport.objects.create(
            user=self.other,
            title="Theirs",
            report_date=date(2026, 3, 1),
            file=_fake_pdf("other.pdf"),
            status="PENDING",
        )

        ok = self.client.get(f"/api/medical-reports/reports/{report.id}/status/")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data["status"], "PROCESSING")

        denied = self.client.get(
            f"/api/medical-reports/reports/{other_report.id}/status/"
        )
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_parsed_reports_file_cannot_be_replaced_by_patch(self):
        report = MedicalReport.objects.create(
            user=self.user, title="Mine", report_date=date(2026, 3, 1), file=_fake_pdf(),
            status="COMPLETED", is_parsed=True, parsed_data={"text": "original"},
        )
        result = TestResult.objects.create(report=report, test_name="Glucose", value="95")
        original_name = report.file.name

        response = self.client.patch(
            f"/api/medical-reports/reports/{report.id}/",
            {"file": _fake_pdf("replacement.pdf")}, format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        report.refresh_from_db()
        self.assertEqual((report.file.name, report.parsed_data), (original_name, {"text": "original"}))
        self.assertTrue(TestResult.objects.filter(pk=result.pk).exists())

    def test_session_authentication_is_not_accepted_by_api(self):
        session_client = APIClient()
        session_client.force_login(self.user)

        response = session_client.get("/api/medical-reports/reports/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_deleting_report_removes_stored_file(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            report = MedicalReport.objects.create(
                user=self.user,
                title="Disposable",
                report_date=date(2026, 3, 2),
                file=_fake_pdf("disposable.pdf"),
            )
            stored_path = Path(report.file.path)
            self.assertTrue(stored_path.exists())

            report.delete()

            self.assertFalse(stored_path.exists())


PAGE_SIZE = settings.REST_FRAMEWORK["PAGE_SIZE"]


def _report(user, title, **fields):
    fields.setdefault("report_date", date(2026, 3, 1))
    return MedicalReport.objects.create(
        user=user, title=title, file=f"medical_reports/{title}.pdf", **fields
    )


class MedicalReportIsolationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="testpass123")
        self.other = User.objects.create_user(username="intruder-target", password="testpass123")
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}"
        )
        self.theirs = _report(self.other, "theirs", status="COMPLETED")
        self.their_result = TestResult.objects.create(
            report=self.theirs, test_name="HbA1c", value="9.1", unit="%", status="HIGH"
        )

    def test_endpoints_require_authentication(self):
        anonymous = APIClient()
        for url in (
            "/api/medical-reports/reports/",
            f"/api/medical-reports/reports/{self.theirs.id}/",
            f"/api/medical-reports/reports/{self.theirs.id}/status/",
            f"/api/medical-reports/reports/{self.theirs.id}/test-results/",
            "/api/medical-reports/trends/?parameter=HbA1c",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    anonymous.get(url).status_code, status.HTTP_401_UNAUTHORIZED
                )

    def test_list_is_paginated_and_scoped_to_owner(self):
        for i in range(PAGE_SIZE + 1):
            _report(self.user, f"mine-{i}")

        first = self.client.get("/api/medical-reports/reports/")
        second = self.client.get("/api/medical-reports/reports/", {"page": 2})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["count"], PAGE_SIZE + 1)
        self.assertEqual(len(first.data["results"]), PAGE_SIZE)
        self.assertEqual(len(second.data["results"]), 1)
        ids = {row["id"] for row in first.data["results"] + second.data["results"]}
        self.assertNotIn(self.theirs.id, ids)

    def test_other_users_report_is_not_reachable(self):
        url = f"/api/medical-reports/reports/{self.theirs.id}/"

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {"title": "Tampered"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        # An authenticated non-owner without a signed token must not stream the file.
        self.assertEqual(
            self.client.get(f"{url}download/").status_code, status.HTTP_404_NOT_FOUND
        )
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, "theirs")

    def test_other_users_test_results_are_not_reachable(self):
        mine = _report(self.user, "mine")
        their_results = f"/api/medical-reports/reports/{self.theirs.id}/test-results/"
        # Pairing an owned report with another user's result id must not reach it.
        crossed = (
            f"/api/medical-reports/reports/{mine.id}/test-results/{self.their_result.id}/"
        )

        self.assertEqual(
            self.client.get(their_results).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(
            self.client.post(
                their_results, {"test_name": "Glucose", "value": "90"}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.get(crossed).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(crossed, {"value": "5.0"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(crossed).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(
                f"/api/medical-reports/test-results/{self.their_result.id}/",
                {"value": "5.0"},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.theirs.test_results.count(), 1)
        self.their_result.refresh_from_db()
        self.assertEqual(self.their_result.value, "9.1")

    def test_result_actions_on_other_users_result_return_404(self):
        for action in ("convert-unit", "validate"):
            with self.subTest(action=action):
                response = self.client.post(
                    f"/api/medical-reports/test-results/{self.their_result.id}/{action}/",
                    {"target_unit": "mmol_l"},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.their_result.refresh_from_db()
        self.assertEqual(self.their_result.value, "9.1")
        self.assertEqual(self.their_result.status, "HIGH")

    def test_trends_only_include_requesters_results(self):
        mine = _report(self.user, "mine")
        TestResult.objects.create(report=mine, test_name="HbA1c", value="5.4", unit="%")

        response = self.client.get("/api/medical-reports/trends/", {"parameter": "HbA1c"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["value"] for row in response.data["trends"]], ["5.4"])

    @patch("medical_reports.tasks.parse_report_task.delay")
    def test_bulk_upload_assigns_requesting_user(self, mock_delay):
        with (
            TemporaryDirectory() as media_root,
            override_settings(MEDIA_ROOT=media_root),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                "/api/medical-reports/reports/bulk-upload/",
                {"files": [_fake_pdf("2026-05-01-a.pdf"), _fake_pdf("2026-05-02-b.pdf")]},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        created = MedicalReport.objects.filter(
            pk__in=[row["id"] for row in response.data["reports"]]
        )
        self.assertEqual({report.user for report in created}, {self.user})
        self.assertEqual(
            sorted(report.report_date for report in created),
            [date(2026, 5, 1), date(2026, 5, 2)],
        )
        self.assertEqual(mock_delay.call_count, 2)

    @patch("medical_reports.tasks.parse_report_task.delay")
    def test_bulk_upload_reads_lab_name_after_underscore(self, mock_delay):
        names = ["2026-05-14_lalpath.pdf", "2026-05-15-cbc.pdf", "2026-05-16.pdf"]
        with (
            TemporaryDirectory() as media_root,
            override_settings(MEDIA_ROOT=media_root),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                "/api/medical-reports/reports/bulk-upload/",
                {"files": [_fake_pdf(name) for name in names]},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 3)
        reports = {
            report.title: (report.report_date, report.lab_name)
            for report in MedicalReport.objects.filter(
                pk__in=[row["id"] for row in response.data["reports"]]
            )
        }
        self.assertEqual(
            reports,
            {
                "2026-05-14_lalpath.pdf": (date(2026, 5, 14), "lalpath"),
                "2026-05-15-cbc.pdf": (date(2026, 5, 15), ""),
                "2026-05-16.pdf": (date(2026, 5, 16), ""),
            },
        )
        self.assertEqual(
            {row["title"]: row["lab_name"] for row in response.data["reports"]}["2026-05-14_lalpath.pdf"],
            "lalpath",
        )
