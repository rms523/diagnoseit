"""Noticing a report file the user has already uploaded (medical_reports/duplicates.py)."""

import hashlib
import importlib
from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from medical_reports.models import MedicalReport

User = get_user_model()

CBC = b"%PDF-1.4 complete blood count"
LIPIDS = b"%PDF-1.4 lipid profile"


def _pdf(name: str, content: bytes = CBC) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


@patch("medical_reports.tasks.parse_report_task.delay")
class DuplicateUploadTests(TestCase):
    def setUp(self):
        media_root = TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        media = override_settings(MEDIA_ROOT=media_root.name)
        media.enable()
        self.addCleanup(media.disable)
        self.user = User.objects.create_user(username="patient", password="testpass123")
        self.client = _client_for(self.user)

    def _upload(self, client=None, **extra):
        data = {"title": "CBC May", "report_type": "LAB", "report_date": "2026-05-14", "file": _pdf("cbc.pdf"), **extra}
        with self.captureOnCommitCallbacks(execute=True):
            return (client or self.client).post("/api/medical-reports/reports/", data, format="multipart")

    def _bulk(self, files, **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                "/api/medical-reports/reports/bulk-upload/", {"files": files, **extra}, format="multipart"
            )

    def test_uploading_a_file_again_is_refused_with_the_report_it_matches(self, mock_parse):
        first = self._upload()
        self.assertEqual(first.status_code, 201)
        report = MedicalReport.objects.get(pk=first.data["id"])
        self.assertEqual(report.file_sha256, hashlib.sha256(CBC).hexdigest())

        again = self._upload(title="Same CBC")

        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["code"], "duplicate_file")
        self.assertEqual(
            {key: again.data["duplicate_of"][key] for key in ("id", "title", "report_date")},
            {"id": report.id, "title": "CBC May", "report_date": "2026-05-14"},
        )
        self.assertIn('already uploaded as "CBC May"', again.data["error"])
        self.assertEqual(MedicalReport.objects.filter(user=self.user).count(), 1)
        self.assertEqual(mock_parse.call_count, 1)

    def test_a_file_can_be_uploaded_again_when_asked(self, mock_parse):
        self._upload()

        again = self._upload(title="Same CBC", allow_duplicate="true")

        self.assertEqual(again.status_code, 201)
        self.assertEqual(MedicalReport.objects.filter(user=self.user, file_sha256=hashlib.sha256(CBC).hexdigest()).count(), 2)
        self.assertEqual(mock_parse.call_count, 2)

    def test_another_accounts_copy_of_the_file_is_never_matched_or_named(self, _parse):
        stranger = User.objects.create_user(username="stranger", password="testpass123")
        self.assertEqual(self._upload(client=_client_for(stranger), title="Their CBC").status_code, 201)

        mine = self._upload()

        self.assertEqual(mine.status_code, 201)
        self.assertNotIn("Their CBC", str(mine.data))

    def test_bulk_upload_skips_files_already_uploaded_earlier_or_in_the_same_batch(self, mock_parse):
        earlier = self._upload()

        response = self._bulk([
            _pdf("2026-05-14_lalpath.pdf"),  # the file uploaded above, under another name
            _pdf("2026-06-01_lalpath.pdf", LIPIDS),
            _pdf("2026-06-01_copy.pdf", LIPIDS),  # the file before it, again in this batch
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.data["total"], response.data["created"], response.data["errors"], response.data["duplicates"]),
            (3, 1, 2, 2),
        )
        lipids = MedicalReport.objects.get(title="2026-06-01_lalpath.pdf")
        self.assertEqual(
            [(item["file"], item["duplicate_of"]["id"]) for item in response.data["error_details"]],
            [("2026-05-14_lalpath.pdf", earlier.data["id"]), ("2026-06-01_copy.pdf", lipids.id)],
        )
        # Apps that only know about errors still say why the file was not uploaded.
        self.assertTrue(all("already uploaded" in item["error"] for item in response.data["error_details"]))
        self.assertEqual(mock_parse.call_count, 2)

    def test_bulk_upload_takes_duplicates_when_asked(self, _parse):
        self._upload()

        response = self._bulk([_pdf("2026-05-14_lalpath.pdf"), _pdf("2026-05-14_again.pdf")], allow_duplicate="true")

        self.assertEqual((response.data["created"], response.data["duplicates"]), (2, 0))
        self.assertEqual(MedicalReport.objects.filter(user=self.user).count(), 3)


class StoredFileHashMigrationTests(TestCase):
    def test_reports_uploaded_before_hashes_were_stored_are_hashed(self):
        migration = importlib.import_module("medical_reports.migrations.0010_medicalreport_file_sha256")
        user = User.objects.create_user(username="patient", password="testpass123")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            stored = MedicalReport(user=user, title="Old CBC", report_date=date(2025, 4, 28))
            stored.file.save("old.pdf", ContentFile(CBC), save=True)
            missing = MedicalReport.objects.create(
                user=user, title="Lost", report_date=date(2025, 4, 28), file="medical_reports/lost.pdf"
            )

            migration.hash_stored_files(apps, None)

        stored.refresh_from_db()
        missing.refresh_from_db()
        self.assertEqual(stored.file_sha256, hashlib.sha256(CBC).hexdigest())
        self.assertEqual(missing.file_sha256, "")
