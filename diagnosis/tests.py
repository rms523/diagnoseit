"""API tests for diagnoses, health trends, AI generation, and cross-user isolation."""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from medical_reports.models import MedicalReport, TestResult
from prescriptions.models import Medication, Prescription
from symptoms.models import Symptom, SymptomLog
from utils.llm_service import LLMError
from .models import Diagnosis, DiagnosisHistory, HealthTrend

User = get_user_model()

PAGE_SIZE = settings.REST_FRAMEWORK["PAGE_SIZE"]

FAKE_LLM_DIAGNOSIS = {
    "condition_name": "Iron deficiency",
    "description": "Pattern consistent with low iron stores.",
    "confidence_score": 3,
    "recommendations": "Repeat ferritin.",
    "follow_up_required": True,
    "follow_up_notes": "Review in four weeks.",
}


def _diagnosis(user, condition_name="Anaemia"):
    return Diagnosis.objects.create(
        user=user, condition_name=condition_name, description="Observed pattern."
    )


def _trend(user, parameter_name="Creatinine"):
    return HealthTrend.objects.create(
        user=user,
        trend_type="STABLE",
        parameter_name=parameter_name,
        current_value="1.0",
        trend_period="Last 6 months",
        analysis="Stable.",
    )


class DiagnosisAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="patient", password="testpass123")
        self.other = User.objects.create_user(username="stranger", password="testpass123")
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}"
        )
        self.their_diagnosis = _diagnosis(self.other, "Their condition")
        DiagnosisHistory.objects.create(
            diagnosis=self.their_diagnosis,
            condition_name="Their condition",
            description="Observed pattern.",
            confidence_score=3,
        )
        self.their_trend = _trend(self.other)

    def test_endpoints_require_authentication(self):
        anonymous = APIClient()
        for url in (
            "/api/diagnosis/diagnoses/",
            f"/api/diagnosis/diagnoses/{self.their_diagnosis.id}/",
            f"/api/diagnosis/diagnoses/{self.their_diagnosis.id}/history/",
            "/api/diagnosis/trends/",
            f"/api/diagnosis/trends/{self.their_trend.id}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    anonymous.get(url).status_code, status.HTTP_401_UNAUTHORIZED
                )
        self.assertEqual(
            anonymous.post(
                "/api/diagnosis/diagnoses/generate/", {}, format="json"
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_diagnosis_list_is_paginated_and_scoped_to_owner(self):
        for i in range(PAGE_SIZE + 1):
            _diagnosis(self.user, f"Condition {i}")

        first = self.client.get("/api/diagnosis/diagnoses/")
        second = self.client.get("/api/diagnosis/diagnoses/", {"page": 2})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["count"], PAGE_SIZE + 1)
        self.assertEqual(len(first.data["results"]), PAGE_SIZE)
        self.assertEqual(len(second.data["results"]), 1)
        ids = {row["id"] for row in first.data["results"] + second.data["results"]}
        self.assertNotIn(self.their_diagnosis.id, ids)

    def test_other_users_diagnosis_is_not_reachable(self):
        url = f"/api/diagnosis/diagnoses/{self.their_diagnosis.id}/"

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(
                url, {"condition_name": "Tampered"}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.get(f"{url}history/").status_code, status.HTTP_404_NOT_FOUND
        )
        self.their_diagnosis.refresh_from_db()
        self.assertEqual(self.their_diagnosis.condition_name, "Their condition")

    def test_trends_are_scoped_to_owner(self):
        mine = _trend(self.user, "Glucose")
        url = f"/api/diagnosis/trends/{self.their_trend.id}/"

        listing = self.client.get("/api/diagnosis/trends/")

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in listing.data["results"]], [mine.id])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {"analysis": "Tampered"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.their_trend.refresh_from_db()
        self.assertEqual(self.their_trend.analysis, "Stable.")

    def test_trend_create_assigns_requesting_user(self):
        response = self.client.post(
            "/api/diagnosis/trends/",
            {
                "trend_type": "IMPROVING",
                "parameter_name": "HbA1c",
                "current_value": "6.1",
                "trend_period": "Last year",
                "analysis": "Improving.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(HealthTrend.objects.get(pk=response.data["id"]).user, self.user)

    @patch("diagnosis.views.generate_diagnosis", return_value=FAKE_LLM_DIAGNOSIS)
    def test_generate_requires_symptoms_or_test_results(self, mock_generate):
        response = self.client.post("/api/diagnosis/diagnoses/generate/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_generate.assert_not_called()

    @patch("diagnosis.views.generate_diagnosis", return_value=FAKE_LLM_DIAGNOSIS)
    def test_generate_saves_diagnosis_and_history_for_requester(self, mock_generate):
        response = self.client.post(
            "/api/diagnosis/diagnoses/generate/",
            {"symptoms": [{"description": "Fatigue", "severity": 2}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        diagnosis = Diagnosis.objects.get(pk=response.data["id"])
        self.assertEqual(diagnosis.user, self.user)
        self.assertEqual(diagnosis.condition_name, "Iron deficiency")
        self.assertEqual(diagnosis.history.count(), 1)

    @patch("diagnosis.views.generate_diagnosis", return_value=FAKE_LLM_DIAGNOSIS)
    def test_generate_only_sends_requesters_history_to_llm(self, mock_generate):
        own_report = MedicalReport.objects.create(
            user=self.user,
            title="Mine",
            report_date=date(2026, 1, 1),
            file="medical_reports/mine.pdf",
        )
        their_report = MedicalReport.objects.create(
            user=self.other,
            title="Theirs",
            report_date=date(2026, 1, 2),
            file="medical_reports/theirs.pdf",
        )
        TestResult.objects.create(
            report=own_report, test_name="Ferritin", value="12", unit="ng/mL"
        )
        TestResult.objects.create(
            report=their_report, test_name="HbA1c", value="9.1", unit="%"
        )
        Symptom.objects.create(
            user=self.user, description="Fatigue", onset_date=timezone.now()
        )
        Symptom.objects.create(
            user=self.other, description="Their symptom", onset_date=timezone.now()
        )

        response = self.client.post(
            "/api/diagnosis/diagnoses/generate/",
            {
                "symptoms": [{"description": "Fatigue"}],
                "include_test_results": True,
                "include_medical_history": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user_data = mock_generate.call_args.args[0]
        self.assertEqual(
            [row["test_name"] for row in user_data["test_results"]], ["Ferritin"]
        )
        self.assertEqual(
            [row["description"] for row in user_data["medical_history"]], ["Fatigue"]
        )


class TimelineDiagnosisTests(TestCase):
    """Health timeline diagnoses: the user's dated history for a period, their summary, and honest failures."""

    preview_url = "/api/diagnosis/diagnoses/timeline-preview/"
    generate_url = "/api/diagnosis/diagnoses/generate/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="tracker", password="testpass123", first_name="Anita", last_name="Rao",
            date_of_birth=date(1990, 1, 1), gender="F",
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.today = timezone.localdate()

        self._report(self.days_ago(400), [("HbA1c", "6.9", "%", "4.0 - 5.6", "HIGH")])
        self._report(self.days_ago(200), [("HbA1c", "7.4", "%", "4.0 - 5.6", "HIGH"), ("Creatinine", "1.0", "mg/dL", "", "")])
        self._report(self.days_ago(30), [("HbA1c", "6.8", "%", "4.0 - 5.6", "HIGH"), ("Anita Rao", "4", "", "", "")])

        prescription = Prescription.objects.create(
            user=self.user, doctor_name="Dr. Mehta", prescription_date=self.days_ago(100), file="prescriptions/p.pdf",
        )
        Medication.objects.create(
            prescription=prescription, medication_name="Metformin", dosage="500 mg", frequency="twice daily",
            duration="3 months", instructions="After meals",
        )

        fatigue = Symptom.objects.create(
            user=self.user, description="Fatigue", severity=2, duration="CHRONIC", onset_date=self.noon(500), is_ongoing=True,
        )
        log = SymptomLog.objects.create(symptom=fatigue, severity=3, notes="Worse after lunch")
        SymptomLog.objects.filter(pk=log.pk).update(logged_at=self.noon(10))
        Symptom.objects.create(
            user=self.user, description="Headache", onset_date=self.noon(60), end_date=self.noon(20), is_ongoing=False,
        )

        _diagnosis(self.user, "Prediabetes")
        _diagnosis(self.user, "LLM Service Not Configured")
        stranger = User.objects.create_user(username="someone", password="testpass123")
        Symptom.objects.create(user=stranger, description="Their symptom", onset_date=self.noon(5))

    def days_ago(self, days):
        return self.today - timedelta(days=days)

    def noon(self, days):
        return timezone.make_aware(datetime.combine(self.days_ago(days), time(12)))

    def _report(self, report_date, rows):
        report = MedicalReport.objects.create(
            user=self.user, title=f"report-{report_date}", lab_name="Lal PathLabs", report_date=report_date,
            file=f"medical_reports/{report_date}.pdf",
        )
        for name, value, unit, reference, flag in rows:
            TestResult.objects.create(
                report=report, test_name=name, value=value, unit=unit, reference_range=reference, status=flag
            )

    def test_preview_lists_the_period_oldest_first_without_personal_details(self):
        response = self.client.post(
            self.preview_url,
            {"period": "1y", "summary": "Type 2 diabetes since 2024. Anita tracks HbA1c.", "symptoms": ["Tired"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prompt = response.data["prompt"]
        self.assertIn("- Age: ", prompt)
        self.assertIn("- Gender: Female", prompt)
        self.assertIn("[REDACTED] tracks HbA1c.", prompt)
        self.assertIn("- Tired", prompt)
        self.assertNotIn("HbA1c: 6.9", prompt)
        self.assertIn(f"Symptom ongoing since {self.days_ago(500).isoformat()}: Fatigue, moderate, chronic (> 4 weeks), still ongoing", prompt)
        self.assertIn("Lab results from Lal PathLabs:\n    - HbA1c: 7.4 % (reference 4.0 - 5.6) HIGH", prompt)
        self.assertIn("Prescription:\n    - Metformin, 500 mg, twice daily, for 3 months. Instructions: After meals", prompt)
        self.assertIn("Symptom began: Headache, mild", prompt)
        self.assertIn("Symptom ended: Headache", prompt)
        self.assertIn("Symptom update: Fatigue is severe. Notes: Worse after lunch", prompt)
        self.assertIn("Earlier AI assessment, not a doctor's diagnosis: Prediabetes (confidence 3/5)", prompt)
        self.assertIn("[REDACTED] [REDACTED]: 4", prompt)
        for private in ("Anita", "Dr. Mehta", "LLM Service Not Configured", "Their symptom", "report-"):
            self.assertNotIn(private, prompt)
        dates = [self.days_ago(days).isoformat() for days in (365, 200, 100, 60, 30, 20, 10)]
        self.assertEqual([prompt.index(f"\n{day}\n") for day in dates], sorted(prompt.index(f"\n{day}\n") for day in dates))
        self.assertEqual(
            response.data["counts"],
            {"symptoms": 2, "symptom_updates": 1, "reports": 2, "results": 4, "prescriptions": 1, "medications": 1, "assessments": 1},
        )
        self.assertEqual((response.data["since"], response.data["omitted_dates"]), (self.days_ago(365).isoformat(), 0))

    @patch("diagnosis.views.LLMService.generate_timeline_diagnosis", return_value=FAKE_LLM_DIAGNOSIS)
    def test_timeline_diagnosis_is_saved_with_what_it_was_based_on(self, mock_generate):
        response = self.client.post(
            self.generate_url, {"mode": "timeline", "period": "6m", "summary": "Tracking HbA1c.", "symptoms": []}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        diagnosis = Diagnosis.objects.get(pk=response.data["id"])
        self.assertEqual((diagnosis.user, diagnosis.condition_name, diagnosis.history.count()), (self.user, "Iron deficiency", 1))
        self.assertEqual(
            {key: response.data["context"][key] for key in ("mode", "period", "since", "summary_included")},
            {"mode": "timeline", "period": "6m", "since": self.days_ago(182).isoformat(), "summary_included": True},
        )
        self.assertEqual(response.data["context"]["counts"]["reports"], 1)
        prompt = mock_generate.call_args.args[0]
        self.assertIn("Tracking HbA1c.", prompt)
        self.assertIn("No new symptoms", prompt)
        self.user.refresh_from_db()
        self.assertEqual(self.user.health_summary, "Tracking HbA1c.")

    @patch(
        "diagnosis.views.LLMService.generate_timeline_diagnosis",
        side_effect=LLMError("The AI diagnosis model did not respond (ReadTimeout)."),
    )
    def test_a_model_failure_is_reported_instead_of_saved(self, _generate):
        before = Diagnosis.objects.count()

        response = self.client.post(self.generate_url, {"mode": "timeline", "summary": "Kept anyway."}, format="json")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("did not respond", response.data["error"])
        self.assertEqual(Diagnosis.objects.count(), before)
        self.user.refresh_from_db()
        self.assertEqual(self.user.health_summary, "Kept anyway.")

    def test_invalid_period_and_long_histories(self):
        self.assertEqual(self.client.post(self.preview_url, {"period": "5y"}, format="json").status_code, 400)

        with patch("diagnosis.timeline.MAX_TIMELINE_CHARS", 300):
            response = self.client.post(self.preview_url, {"period": "all"}, format="json")

        self.assertGreater(response.data["omitted_dates"], 0)
        self.assertIn("earliest date", response.data["prompt"])
        self.assertIn(self.days_ago(10).isoformat(), response.data["prompt"])
