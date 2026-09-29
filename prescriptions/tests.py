from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from urllib.parse import urlsplit

from .models import Medication, Prescription

PAGE_SIZE = settings.REST_FRAMEWORK["PAGE_SIZE"]


class PrescriptionFileLifecycleTests(TestCase):
    def test_deleting_prescription_removes_stored_file(self):
        user = get_user_model().objects.create_user(
            username="rx-owner", password="testpass123"
        )
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            prescription = Prescription.objects.create(
                user=user,
                prescription_date=date(2026, 4, 1),
                file=SimpleUploadedFile(
                    "prescription.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                ),
            )
            stored_path = Path(prescription.file.path)
            self.assertTrue(stored_path.exists())

            prescription.delete()

            self.assertFalse(stored_path.exists())

    def test_detail_exposes_short_lived_private_download(self):
        user = get_user_model().objects.create_user(
            username="private-rx-owner", password="testpass123"
        )
        prescription = Prescription.objects.create(
            user=user,
            prescription_date=date(2026, 4, 2),
            file=SimpleUploadedFile(
                "private.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
            ),
        )
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}"
        )

        detail = client.get(f"/api/prescriptions/prescriptions/{prescription.id}/")
        self.assertEqual(detail.status_code, 200)
        signed_url = urlsplit(detail.data["file"])

        anonymous = APIClient()
        self.assertEqual(
            anonymous.get(f"{signed_url.path}?{signed_url.query}").status_code,
            200,
        )
        self.assertEqual(anonymous.get(signed_url.path).status_code, 404)


def _prescription(user, name, **fields):
    return Prescription.objects.create(
        user=user,
        prescription_date=date(2026, 4, 1),
        file=f"prescriptions/{name}.pdf",
        **fields,
    )


class PrescriptionAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="rx-patient", password="testpass123"
        )
        self.other = get_user_model().objects.create_user(
            username="rx-stranger", password="testpass123"
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}"
        )
        self.theirs = _prescription(self.other, "theirs", doctor_name="Dr. Private")
        self.their_medication = Medication.objects.create(
            prescription=self.theirs, medication_name="Private med", dosage="5 mg"
        )

    def test_endpoints_require_authentication(self):
        anonymous = APIClient()
        for url in (
            "/api/prescriptions/prescriptions/",
            f"/api/prescriptions/prescriptions/{self.theirs.id}/",
            f"/api/prescriptions/prescriptions/{self.theirs.id}/medications/",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    anonymous.get(url).status_code, status.HTTP_401_UNAUTHORIZED
                )

    @patch("prescriptions.tasks.parse_prescription_task.delay")
    def test_create_assigns_requesting_user(self, mock_queue):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/api/prescriptions/prescriptions/",
                {
                    "prescription_date": "2026-04-03",
                    "file": SimpleUploadedFile(
                        "new.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                    ),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Prescription.objects.get(pk=response.data["id"]).user, self.user
        )

    def test_list_is_paginated_and_scoped_to_owner(self):
        for i in range(PAGE_SIZE + 1):
            _prescription(self.user, f"mine-{i}")

        first = self.client.get("/api/prescriptions/prescriptions/")
        second = self.client.get("/api/prescriptions/prescriptions/", {"page": 2})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["count"], PAGE_SIZE + 1)
        self.assertEqual(len(first.data["results"]), PAGE_SIZE)
        self.assertEqual(len(second.data["results"]), 1)
        ids = {row["id"] for row in first.data["results"] + second.data["results"]}
        self.assertNotIn(self.theirs.id, ids)

    def test_other_users_prescription_is_not_reachable(self):
        url = f"/api/prescriptions/prescriptions/{self.theirs.id}/"

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {"doctor_name": "Tampered"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        # An authenticated non-owner without a signed token must not stream the file.
        self.assertEqual(
            self.client.get(f"{url}download/").status_code, status.HTTP_404_NOT_FOUND
        )
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.doctor_name, "Dr. Private")

    def test_a_parsed_prescriptions_file_cannot_be_replaced_by_patch(self):
        prescription = _prescription(
            self.user, "mine", status="COMPLETED", is_parsed=True,
            parsed_data={"text": "original"},
        )
        medication = Medication.objects.create(
            prescription=prescription, medication_name="Amoxicillin", dosage="500 mg"
        )
        original_name = prescription.file.name

        response = self.client.patch(
            f"/api/prescriptions/prescriptions/{prescription.id}/",
            {"file": SimpleUploadedFile("replacement.pdf", b"%PDF-1.4 fake", content_type="application/pdf")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        prescription.refresh_from_db()
        self.assertEqual((prescription.file.name, prescription.parsed_data), (original_name, {"text": "original"}))
        self.assertTrue(Medication.objects.filter(pk=medication.pk).exists())

    def test_other_users_medications_are_not_reachable(self):
        mine = _prescription(self.user, "mine")
        their_medications = f"/api/prescriptions/prescriptions/{self.theirs.id}/medications/"
        # Pairing an owned prescription with another user's medication id must fail.
        crossed = (
            f"/api/prescriptions/prescriptions/{mine.id}/medications/"
            f"{self.their_medication.id}/"
        )

        self.assertEqual(
            self.client.get(their_medications).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(
            self.client.post(
                their_medications, {"medication_name": "Injected"}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.get(crossed).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(crossed, {"dosage": "500 mg"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(crossed).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(self.theirs.medications.count(), 1)
        self.their_medication.refresh_from_db()
        self.assertEqual(self.their_medication.dosage, "5 mg")
