"""Relinking stored results to the catalog, and Health Trends grouped by catalog test."""

from datetime import date
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from lab_tests.models import LabTestType, UserTestAlias
from medical_reports.models import MedicalReport, TestResult
from medical_reports.tasks import _build_test_results

User = get_user_model()


class CatalogLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("populate_lab_tests", stdout=StringIO())

    def setUp(self):
        self.user = User.objects.create_user(username="linker", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.report = self._report(self.user, "LFT", date(2026, 5, 1))

    @staticmethod
    def _report(user, title, report_date):
        return MedicalReport.objects.create(
            user=user, title=title, report_date=report_date, file=f"medical_reports/{title}.pdf", status="COMPLETED"
        )

    @staticmethod
    def _result(report, test_name, value, type_name=None, **fields):
        test_type = LabTestType.objects.get(name=type_name) if type_name else None
        return TestResult.objects.create(report=report, test_name=test_name, value=value, test_type=test_type, **fields)

    def test_relink_lists_changes_then_applies_them_without_replacing_renamed_results(self):
        mpv = self._result(self.report, "Platelet Count", "9.1", "platelet_count")
        urea = self._result(self.report, "Urea Nitrogen (BUN)", "32", "urea")
        bun = self._result(self.report, "Urea Nitrogen (BUN)", "15", "urea")
        renamed = self._result(self.report, "My liver enzyme", "40")
        custom = self._result(self.report, "ALT (SGPT), SERUM", "41")
        self.report.parsed_data = {"test_results": [
            {"result_id": mpv.id, "raw_test_name": "Mean Platelet Volume", "test_name": "platelet_count",
             "display_name": "Platelet Count", "value": "9.1"},
            {"raw_test_name": "Urea", "test_name": "urea", "display_name": "Urea Nitrogen (BUN)", "value": "32"},
            {"raw_test_name": "Urea Nitrogen Blood", "test_name": "urea", "display_name": "Urea Nitrogen (BUN)", "value": "15"},
            {"result_id": renamed.id, "raw_test_name": "SGPT", "test_name": "alt",
             "display_name": "ALT (Alanine Aminotransferase)", "value": "40"},
        ]}
        self.report.save()

        dry_run = StringIO()
        call_command("relink_test_results", stdout=dry_run)

        self.assertIn("Dry run", dry_run.getvalue())
        self.assertIn('printed "Mean Platelet Volume"', dry_run.getvalue())
        mpv.refresh_from_db()
        self.assertEqual(mpv.test_type.name, "platelet_count")

        call_command("relink_test_results", "--apply", stdout=StringIO())

        linked = {
            row.id: (row.test_type.name if row.test_type else None, row.test_name)
            for row in TestResult.objects.filter(report=self.report)
        }
        self.assertEqual(linked[mpv.id], ("mpv", "MPV (Mean Platelet Volume)"))
        self.assertEqual(linked[urea.id], ("urea", "Urea"))
        self.assertEqual(linked[bun.id], ("bun", "Urea Nitrogen (BUN)"))
        self.assertEqual(linked[renamed.id], (None, "My liver enzyme"))
        self.assertEqual(linked[custom.id], ("alt", "ALT (Alanine Aminotransferase)"))

    def test_health_trends_list_one_entry_per_catalog_test(self):
        later = self._report(self.user, "LFT-2", date(2026, 6, 1))
        self._result(self.report, "ALT (SGPT)", "40", "alt")
        self._result(later, "ALT (Alanine Aminotransferase)", "35", "alt")
        self._result(self.report, "SwasthFit Super", "1")
        self._result(later, "SWASTHFIT SUPER", "1")
        other = User.objects.create_user(username="other-linker", password="testpass123")
        self._result(self._report(other, "Theirs", date(2026, 5, 1)), "ALT (SGPT)", "90", "alt")

        parameters = self.client.get("/api/medical-reports/trends/parameters/").data

        self.assertEqual(
            [(item["name"], item["test_type"], item["result_count"], item["printed_names"]) for item in parameters],
            [
                ("ALT (Alanine Aminotransferase)", "alt", 2, ["ALT (Alanine Aminotransferase)", "ALT (SGPT)"]),
                ("SWASTHFIT SUPER", None, 2, ["SWASTHFIT SUPER", "SwasthFit Super"]),
            ],
        )
        by_test = self.client.get("/api/medical-reports/trends/", {"test_type": "alt"}).data
        self.assertEqual([point["value"] for point in by_test["trends"]], ["40", "35"])
        by_printed_name = self.client.get("/api/medical-reports/trends/", {"parameter": "SGPT"}).data
        self.assertEqual((by_printed_name["parameter"], len(by_printed_name["trends"])), ("ALT (Alanine Aminotransferase)", 2))

    def test_relink_unlinks_results_without_a_number(self):
        negative = self._result(self.report, "CRP (C-Reactive Protein)", "Negative", "crp")
        measured = self._result(self.report, "CRP (C-Reactive Protein)", "4.2", "crp")

        call_command("relink_test_results", "--apply", stdout=StringIO())

        negative.refresh_from_db()
        measured.refresh_from_db()
        self.assertIsNone(negative.test_type)
        self.assertEqual(measured.test_type.name, "crp")

        parameters = self.client.get("/api/medical-reports/trends/parameters/").data
        self.assertEqual(next(row for row in parameters if row["test_type"] == "crp")["numeric_count"], 1)
        self.assertEqual(next(row for row in parameters if row["test_type"] is None)["numeric_count"], 0)

        by_test = self.client.get("/api/medical-reports/trends/", {"test_type": "crp"}).data
        by_name = self.client.get("/api/medical-reports/trends/", {"name": "CRP (C-Reactive Protein)"}).data
        self.assertEqual([point["value"] for point in by_test["trends"]], ["4.2"])
        self.assertEqual([point["value"] for point in by_name["trends"]], ["Negative"])

    def test_a_confirmed_name_link_relinks_only_this_users_measured_results_and_can_be_removed(self):
        printed = self._result(self.report, "Sugar Level Post Lunch", "132")
        qualitative = self._result(self.report, "Sugar Level Post Lunch", "Nil")
        self.report.parsed_data = {"test_results": [
            {"result_id": printed.id, "raw_test_name": "Sugar Level Post Lunch", "test_name": "Sugar Level Post Lunch",
             "display_name": "Sugar Level Post Lunch", "value": "132"},
        ]}
        self.report.save()
        other_user = User.objects.create_user(username="other", password="testpass123")
        theirs = self._result(self._report(other_user, "Theirs", date(2026, 5, 2)), "Sugar Level Post Lunch", "140")

        rejected = self.client.post(
            "/api/medical-reports/test-aliases/", {"name": "Urine Sugar Post Lunch", "test_type": "glucose_pp"}, format="json"
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("urine", rejected.data["error"])

        created = self.client.post(
            "/api/medical-reports/test-aliases/", {"name": "Sugar Level Post Lunch", "test_type": "glucose_pp"}, format="json"
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["relinked"], 1)
        printed.refresh_from_db()
        qualitative.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual((printed.test_type.name, printed.test_name), ("glucose_pp", "Post Prandial Glucose"))
        self.assertIsNone(qualitative.test_type)
        self.assertIsNone(theirs.test_type)

        parsed = _build_test_results(self.report, [{"test_name": "POST LUNCH SUGAR", "value": "128", "unit": "mg/dL"}])
        self.assertEqual(parsed[0][1].test_type.name, "glucose_pp")

        listed = self.client.get("/api/medical-reports/test-aliases/")
        self.assertEqual([(row["name"], row["test_type"]) for row in listed.data], [("Sugar Level Post Lunch", "glucose_pp")])

        removed = self.client.delete(f"/api/medical-reports/test-aliases/{listed.data[0]['id']}/")
        self.assertEqual((removed.status_code, removed.data["relinked"]), (200, 1))
        printed.refresh_from_db()
        self.assertEqual((printed.test_type, printed.test_name), (None, "Sugar Level Post Lunch"))
        self.assertFalse(UserTestAlias.objects.exists())

    def test_ai_suggestions_are_checked_against_the_catalog_rules(self):
        self._result(self.report, "Sugar Level Post Lunch", "132", unit="mg/dL")
        reply = (
            '{"suggestions": ['
            '{"name": "Sugar Level Post Lunch", "test_type": "glucose_pp", "reason": "after a meal"},'
            '{"name": "Urine Sugar", "test_type": "glucose", "reason": "sugar"},'
            '{"name": "Pimpri", "test_type": "made_up", "reason": "?"}]}'
        )
        config = MagicMock(is_configured=True, max_tokens=800)
        with patch("medical_reports.test_aliases.get_ai_config", return_value=config), \
                patch("medical_reports.test_aliases.chat_json", return_value=reply) as chat:
            response = self.client.post(
                "/api/medical-reports/test-aliases/suggest/",
                {"names": ["Sugar Level Post Lunch", "Urine Sugar", "Pimpri", "Unknown Thing"]},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(row["name"], row["test_type"]) for row in response.data["suggestions"]],
            [("Sugar Level Post Lunch", "glucose_pp"), ("Urine Sugar", None), ("Pimpri", None), ("Unknown Thing", None)],
        )
        prompt = chat.call_args.args[1][1]["content"]
        self.assertIn("glucose_pp: Post Prandial Glucose [mg/dL]", prompt)
        self.assertIn('"units": ["mg/dL"]', prompt)
        self.assertFalse(UserTestAlias.objects.exists())

    def test_health_trends_convert_other_units_and_mark_what_cannot_be_converted(self):
        dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]
        reports = [self._report(self.user, f"Sugar-{index}", when) for index, when in enumerate(dates)]
        self._result(reports[0], "Fasting Glucose", "90", "glucose_fasting", unit="mg/dL", reference_range="70 - 100")
        self._result(reports[1], "Fasting Glucose", "5.4", "glucose_fasting", unit="mmol/L", reference_range="3.9-5.6")
        self._result(reports[2], "Fasting Glucose", "101", "glucose_fasting", unit="mg/dl", reference_range="70 - 100")
        self._result(reports[3], "Fasting Glucose", "0.9", "glucose_fasting", unit="g/L")

        response = self.client.get("/api/medical-reports/trends/", {"test_type": "glucose_fasting"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["unit"], response.data["unconverted_count"]), ("mg/dL", 1))
        points = [
            (point["value"], point["unit"], point["reference_range"], point["unit_status"])
            for point in response.data["trends"]
        ]
        self.assertEqual(points, [
            ("90", "mg/dL", "70 - 100", "same"),
            ("97.3", "mg/dL", "70.27 - 100.9", "converted"),
            ("101", "mg/dl", "70 - 100", "same"),
            ("0.9", "g/L", "", "unconverted"),
        ])
        self.assertEqual(
            (response.data["trends"][1]["original_value"], response.data["trends"][1]["original_unit"]), ("5.4", "mmol/L")
        )

    def test_relink_matches_stored_rows_in_the_section_the_parser_now_gives_them(self):
        lines = [
            "URINE ROUTINE EXAMINATION",
            "Protein Nil",
            "COMPLETE BLOOD COUNT; CBC, EDTA WHOLE BLOOD",
            "Hemoglobin 14.5 g/dL 13.0 - 17.0",
        ]
        hemoglobin = self._result(self.report, "Hemoglobin", "14.5", unit="g/dL")
        self.report.parsed_data = {"text": "\n".join(lines), "test_results": [
            {"result_id": hemoglobin.id, "raw_test_name": "Hemoglobin", "test_name": "Hemoglobin",
             "display_name": "Hemoglobin", "value": "14.5", "section_context": "urine", "line_number": 3},
        ]}
        self.report.save()

        call_command("relink_test_results", "--apply", stdout=StringIO())

        hemoglobin.refresh_from_db()
        self.assertEqual(hemoglobin.test_type.name, "hemoglobin")

    def test_spellings_of_an_unlinked_name_share_one_entry_and_trend(self):
        later = self._report(self.user, "AMH-2", date(2026, 6, 1))
        self._result(self.report, "Anti-Mullerian Hormone, Serum", "2.1")
        self._result(later, "ANTI-MULLERIAN HORMONE,SERUM", "1.8")

        unlinked = [row for row in self.client.get("/api/medical-reports/trends/parameters/").data if row["test_type"] is None]
        trend = self.client.get("/api/medical-reports/trends/", {"name": unlinked[0]["name"]}).data

        self.assertEqual(
            [(row["result_count"], row["printed_names"]) for row in unlinked],
            [(2, ["ANTI-MULLERIAN HORMONE,SERUM", "Anti-Mullerian Hormone, Serum"])],
        )
        self.assertEqual([point["value"] for point in trend["trends"]], ["2.1", "1.8"])

    def test_search_finds_results_by_name_with_their_reports_for_this_user_only(self):
        later = self._report(self.user, "Wellness", date(2026, 6, 1))
        self._result(self.report, "SWASTHFIT SUPER", "4")
        self._result(later, "SwasthFit Super", "1")
        self._result(self.report, "ALT (SGPT)", "40", "alt")
        other = User.objects.create_user(username="searcher", password="testpass123")
        self._result(self._report(other, "Theirs", date(2026, 5, 3)), "SWASTHFIT SUPER", "2")
        url = "/api/medical-reports/test-results/search/"

        by_name = self.client.get(url, {"q": "swasthfit"})
        by_catalog_name = self.client.get(url, {"q": "Alanine"}).data

        self.assertEqual(by_name.status_code, 200)
        self.assertEqual(
            [(hit["report"]["title"], hit["test_name"], hit["value"]) for hit in by_name.data["results"]],
            [("Wellness", "SwasthFit Super", "1"), ("LFT", "SWASTHFIT SUPER", "4")],
        )
        self.assertEqual([hit["test_name"] for hit in by_catalog_name["results"]], ["ALT (SGPT)"])
        self.assertEqual(self.client.get(url, {"q": "a"}).status_code, 400)

    def test_report_detail_names_the_reports_before_and_after_it_in_the_list(self):
        newest = self._report(self.user, "Newest", date(2026, 7, 1))
        oldest = self._report(self.user, "Oldest", date(2026, 1, 1))

        middle = self.client.get(f"/api/medical-reports/reports/{self.report.id}/").data["neighbors"]
        first = self.client.get(f"/api/medical-reports/reports/{newest.id}/").data["neighbors"]

        self.assertEqual(middle, {
            "previous": {"id": newest.id, "title": "Newest"},
            "next": {"id": oldest.id, "title": "Oldest"},
            "position": 2,
            "total": 3,
        })
        self.assertEqual((first["previous"], first["next"]["id"], first["position"]), (None, self.report.id, 1))

    def test_relink_links_new_catalog_tests_and_tidies_printed_names(self):
        iga = self._result(self.report, "IgA -", "250", unit="mg/dL")
        sugar = self._result(self.report, "Sugar -", "Absent")
        self.report.parsed_data = {"test_results": [
            {"result_id": iga.id, "raw_test_name": "IgA -", "test_name": "IgA -", "display_name": "IgA -", "value": "250"},
            {"result_id": sugar.id, "raw_test_name": "Sugar -", "test_name": "Sugar -", "display_name": "Sugar -", "value": "Absent"},
        ]}
        self.report.save()

        call_command("relink_test_results", "--apply", stdout=StringIO())

        iga.refresh_from_db()
        sugar.refresh_from_db()
        self.assertEqual((iga.test_type.name, iga.test_name), ("iga", "Immunoglobulin A (IgA)"))
        self.assertEqual((sugar.test_type, sugar.test_name), (None, "Sugar"))

