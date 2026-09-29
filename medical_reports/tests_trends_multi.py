"""Several tests' trends in one response, for charts that stack trends on one time axis."""

from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from lab_tests.models import LabTestType
from medical_reports.models import MedicalReport, TestResult

User = get_user_model()


class MultiTrendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("populate_lab_tests", stdout=StringIO())

    def setUp(self):
        self.user = User.objects.create_user(username="charter", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.may = self._report("May panel", date(2026, 5, 1))
        self.june = self._report("June panel", date(2026, 6, 1))

    def _report(self, title, report_date):
        return MedicalReport.objects.create(
            user=self.user, title=title, report_date=report_date,
            file=f"medical_reports/{report_date}.pdf", status="COMPLETED",
        )

    def _result(self, report, test_name, value, type_name=None, **fields):
        test_type = LabTestType.objects.get(name=type_name) if type_name else None
        return TestResult.objects.create(
            report=report, test_name=test_name, value=value, test_type=test_type, **fields
        )

    def test_several_catalog_tests_come_back_as_separate_series_with_their_own_units(self):
        may_hemoglobin = self._result(self.may, "Hemoglobin (Hb)", "13.2", "hemoglobin", unit="g/dL")
        self._result(self.june, "Hemoglobin", "12.4", "hemoglobin", unit="g/dL")
        self._result(self.may, "Glucose", "96", "glucose", unit="mg/dL")

        response = self.client.get(
            "/api/medical-reports/trends/multi/", {"test_type": ["hemoglobin", "glucose"]}
        )

        self.assertEqual(response.status_code, 200, response.data)
        series = response.data["series"]
        self.assertEqual([item["key"] for item in series], ["type:hemoglobin", "type:glucose"])
        self.assertEqual([item["parameter"] for item in series], ["Hemoglobin", "Glucose"])
        self.assertEqual(series[0]["unit"], "g/dL")
        self.assertEqual([point["date"] for point in series[0]["trends"]], ["2026-05-01", "2026-06-01"])
        self.assertEqual(
            [(point["report_id"], point["report_title"]) for point in series[0]["trends"]],
            [(self.may.id, "May panel"), (self.june.id, "June panel")],
        )
        self.assertEqual(series[0]["trends"][0]["result_id"], may_hemoglobin.id)
        self.assertEqual(series[0]["trends"][0]["printed_name"], "Hemoglobin (Hb)")
        self.assertEqual(len(series[1]["trends"]), 1)

    def test_a_name_the_catalog_does_not_know_keeps_its_own_series(self):
        self._result(self.may, "Mystery Marker", "3.1", unit="ng/mL")
        self._result(self.june, "MYSTERY MARKER", "4.0", unit="ng/mL")

        response = self.client.get(
            "/api/medical-reports/trends/multi/", {"name": "Mystery Marker", "test_type": "hemoglobin"}
        )

        series = {item["parameter"]: item for item in response.data["series"]}
        self.assertEqual(len(series["Mystery Marker"]["trends"]), 2)
        self.assertIsNone(series["Mystery Marker"]["test_type"])
        self.assertEqual(series["Hemoglobin"]["trends"], [])

    def test_one_test_asked_for_twice_is_drawn_once(self):
        self._result(self.may, "Hemoglobin", "13.2", "hemoglobin", unit="g/dL")

        response = self.client.get(
            "/api/medical-reports/trends/multi/", {"test_type": "hemoglobin", "parameter": "Hemoglobin"}
        )

        self.assertEqual([item["key"] for item in response.data["series"]], ["type:hemoglobin"])

    def test_the_endpoint_needs_a_test_and_caps_how_many_it_draws(self):
        empty = self.client.get("/api/medical-reports/trends/multi/")
        self.assertEqual(empty.status_code, 400)

        too_many = self.client.get(
            "/api/medical-reports/trends/multi/",
            {"test_type": ["hemoglobin", "glucose", "creatinine", "urea", "sodium", "potassium", "calcium"]},
        )
        self.assertEqual(too_many.status_code, 400)
        self.assertIn("at most", too_many.data["error"])

    def test_one_users_results_never_appear_in_anothers_series(self):
        other = User.objects.create_user(username="someone-else", password="testpass123")
        their_report = MedicalReport.objects.create(
            user=other, title="Theirs", report_date=date(2026, 5, 1),
            file="medical_reports/theirs.pdf", status="COMPLETED",
        )
        self._result(their_report, "Hemoglobin", "15.0", "hemoglobin", unit="g/dL")

        response = self.client.get("/api/medical-reports/trends/multi/", {"test_type": "hemoglobin"})

        self.assertEqual(response.data["series"][0]["trends"], [])
