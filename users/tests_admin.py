"""Admin site tests: user overview, non-editable health records, user deletion, and hidden API token keys."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from diagnosis.models import Diagnosis, HealthTrend
from medical_reports.models import MedicalReport, TestResult
from prescriptions.models import Medication, Prescription
from symptoms.models import Symptom, SymptomLog

User = get_user_model()


def _pdf(name):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminSiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="site-admin", email="admin@example.com", password="Admin-pass-123"
        )
        cls.patient = User.objects.create_user(
            username="patient-one", email="patient@example.com", password="Patient-pass-123"
        )
        cls.report = MedicalReport.objects.create(
            user=cls.patient,
            title="CBC",
            lab_name="lalpath",
            report_date=date(2026, 5, 14),
            file="medical_reports/cbc-private.pdf",
        )
        TestResult.objects.create(report=cls.report, test_name="Hemoglobin", value="14.2", unit="g/dL")
        Prescription.objects.create(
            user=cls.patient, prescription_date=date(2026, 5, 1), file="prescriptions/rx-private.pdf"
        )
        cls.token = Token.objects.create(user=cls.patient)

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_admin_requires_staff_login(self):
        self.client.force_login(self.patient)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_user_list_shows_accounts_with_record_counts(self):
        response = self.client.get("/admin/users/user/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "patient-one")
        patient = next(u for u in response.context["cl"].result_list if u.username == "patient-one")
        self.assertEqual(
            (patient._report_count, patient._prescription_count, patient._symptom_count, patient._diagnosis_count),
            (1, 1, 0, 0),
        )

    def test_user_search_matches_email(self):
        response = self.client.get("/admin/users/user/", {"q": "patient@example.com"})

        self.assertEqual([u.username for u in response.context["cl"].result_list], ["patient-one"])

    def test_health_records_cannot_be_added_or_edited(self):
        detail_url = f"/admin/medical_reports/medicalreport/{self.report.pk}/change/"

        detail = self.client.get(detail_url)

        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.context["has_change_permission"])
        self.assertContains(detail, "Hemoglobin")
        self.assertNotContains(detail, "cbc-private.pdf")
        self.assertEqual(self.client.post(detail_url, {"title": "Tampered"}).status_code, 403)
        self.assertEqual(self.client.get("/admin/medical_reports/medicalreport/add/").status_code, 403)
        self.report.refresh_from_db()
        self.assertEqual(self.report.title, "CBC")

    def test_every_health_record_list_loads(self):
        for url in (
            "/admin/medical_reports/medicalreport/",
            "/admin/prescriptions/prescription/",
            "/admin/symptoms/symptom/",
            "/admin/diagnosis/diagnosis/",
            "/admin/diagnosis/healthtrend/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_deleting_user_removes_their_health_data_and_files(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            leaving = User.objects.create_user(username="leaving-patient", password="Patient-pass-123")
            report = MedicalReport.objects.create(
                user=leaving, title="Old CBC", report_date=date(2026, 1, 2), file=_pdf("old-cbc.pdf")
            )
            TestResult.objects.create(report=report, test_name="Hemoglobin", value="13.9")
            prescription = Prescription.objects.create(
                user=leaving, prescription_date=date(2026, 1, 3), file=_pdf("old-rx.pdf")
            )
            Medication.objects.create(prescription=prescription, medication_name="Paracetamol")
            symptom = Symptom.objects.create(user=leaving, description="Cough", onset_date=timezone.now())
            SymptomLog.objects.create(symptom=symptom, severity=2)
            Diagnosis.objects.create(user=leaving, condition_name="Cold", description="Mild")
            HealthTrend.objects.create(
                user=leaving, trend_type="STABLE", parameter_name="Glucose",
                current_value="95", trend_period="Last month", analysis="Stable.",
            )
            Token.objects.create(user=leaving)
            stored_files = [Path(report.file.path), Path(prescription.file.path)]
            delete_url = f"/admin/users/user/{leaving.pk}/delete/"

            confirmation = self.client.get(delete_url)
            response = self.client.post(delete_url, {"post": "yes"})

            self.assertEqual(confirmation.status_code, 200)
            self.assertFalse(confirmation.context["perms_lacking"])
            self.assertEqual(response.status_code, 302)
            self.assertFalse(User.objects.filter(pk=leaving.pk).exists())
            for model in (MedicalReport, Prescription, Symptom, Diagnosis, HealthTrend, Token):
                with self.subTest(model=model.__name__):
                    self.assertFalse(model.objects.filter(user_id=leaving.pk).exists())
            self.assertFalse(TestResult.objects.filter(report_id=report.pk).exists())
            self.assertFalse(Medication.objects.filter(prescription_id=prescription.pk).exists())
            self.assertEqual([path.exists() for path in stored_files], [False, False])
        self.assertTrue(MedicalReport.objects.filter(user=self.patient).exists())

    def test_api_token_keys_are_never_displayed(self):
        changelist = self.client.get("/admin/users/apitoken/")
        detail = self.client.get(f"/admin/users/apitoken/{self.patient.pk}/change/")
        delete_confirmation = self.client.get(f"/admin/users/apitoken/{self.patient.pk}/delete/")

        for page in (changelist, detail, delete_confirmation):
            with self.subTest(page=page.request["PATH_INFO"]):
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "patient-one")
                self.assertNotContains(page, self.token.key)
        self.assertEqual(self.client.get("/admin/users/apitoken/add/").status_code, 403)
        # DRF's own token admin renders keys, so it must stay unregistered.
        self.assertEqual(self.client.get("/admin/authtoken/tokenproxy/").status_code, 404)

    def test_deleting_api_token_signs_user_out(self):
        response = self.client.post(f"/admin/users/apitoken/{self.patient.pk}/delete/", {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Token.objects.filter(user=self.patient).exists())
