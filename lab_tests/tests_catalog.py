"""Adding, changing, and removing catalog entries from the app.

The catalog decides which printed names become which test, and `populate_lab_tests` reloads the built-in
entries after every deploy, so these tests cover what an edit does to stored results and what the loader
is allowed to undo.
"""

from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from lab_tests.models import LabTestType, LabTestTypeUnit, LabTestUnit, LabTestValidationRule, UnitConversion
from medical_reports.models import MedicalReport, TestResult

User = get_user_model()


class CatalogEditingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("populate_lab_tests", stdout=StringIO())

    def setUp(self):
        self.user = User.objects.create_user(username="curator", password="testpass123", is_staff=True)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.report = MedicalReport.objects.create(
            user=self.user, title="Panel", report_date=date(2026, 5, 1),
            file="medical_reports/panel.pdf", status="COMPLETED",
        )

    def _result(self, test_name, value, type_name=None, **fields):
        test_type = LabTestType.objects.get(name=type_name) if type_name else None
        return TestResult.objects.create(
            report=self.report, test_name=test_name, value=value, test_type=test_type, **fields
        )

    def test_adding_an_entry_links_matching_results_and_makes_its_unit_usable(self):
        result = self._result("Serum Zinc", "82", unit="ug/dL")

        response = self.client.post("/api/lab-tests/types/", {
            "display_name": "Zinc",
            "category": "Chemistry",
            "aliases": ["serum zinc"],
            "default_unit": "ug_dl",
            "normal_min": "70",
            "normal_max": "120",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["name"], "zinc")
        self.assertEqual(response.data["source"], LabTestType.SOURCE_USER)
        self.assertTrue(response.data["edited_by_user"])
        self.assertEqual(response.data["relinked"], 1)

        result.refresh_from_db()
        self.assertEqual(result.test_type.name, "zinc")
        zinc = LabTestType.objects.get(name="zinc")
        unit = LabTestUnit.objects.get(name="ug_dl")
        self.assertTrue(LabTestTypeUnit.objects.filter(test_type=zinc, unit=unit, is_active=True).exists())
        self.assertTrue(LabTestValidationRule.objects.filter(test_type=zinc, unit=unit).exists())

    def test_an_added_entry_takes_a_key_from_its_name_and_rejects_a_bad_one(self):
        suggested = self.client.get("/api/lab-tests/types/suggest-key/", {"display_name": "Vitamin B12 (Serum)"})
        self.assertEqual(suggested.data["key"], "vitamin_b12_serum")

        response = self.client.post("/api/lab-tests/types/", {
            "name": "My Test!", "display_name": "My Test", "default_unit": "mg_dl",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("lowercase", str(response.data["name"]))

    def test_an_alias_that_already_names_another_test_is_refused(self):
        response = self.client.post("/api/lab-tests/types/", {
            "display_name": "Blood Sugar Reading",
            "aliases": ["glucose"],
            "default_unit": "mg_dl",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Glucose", str(response.data["aliases"]))
        self.assertFalse(LabTestType.objects.filter(display_name="Blood Sugar Reading").exists())

    def test_an_unknown_unit_and_an_upside_down_range_are_refused(self):
        unknown_unit = self.client.post("/api/lab-tests/types/", {
            "display_name": "Made Up", "default_unit": "furlongs_per_fortnight",
        }, format="json")
        self.assertEqual(unknown_unit.status_code, 400)
        self.assertIn("not a known unit", str(unknown_unit.data["default_unit"]))

        bad_range = self.client.post("/api/lab-tests/types/", {
            "display_name": "Made Up", "default_unit": "mg_dl", "normal_min": "10", "normal_max": "2",
        }, format="json")
        self.assertEqual(bad_range.status_code, 400)
        self.assertIn("must not be below", str(bad_range.data["normal_max"]))

    def test_editing_an_alias_moves_results_and_stops_the_loader_overwriting_the_entry(self):
        result = self._result("Random Blood Sugar Reading", "104", unit="mg/dL")
        glucose = LabTestType.objects.get(name="glucose_random")

        response = self.client.patch(f"/api/lab-tests/types/{glucose.name}/", {
            "aliases": [*glucose.aliases, "random blood sugar reading"],
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["relinked"], 1)
        result.refresh_from_db()
        self.assertEqual(result.test_type.name, "glucose_random")

        glucose.refresh_from_db()
        self.assertTrue(glucose.edited_by_user)
        self.assertEqual(glucose.source, LabTestType.SOURCE_CATALOG)

        call_command("populate_lab_tests", stdout=StringIO())

        glucose.refresh_from_db()
        self.assertIn("random blood sugar reading", glucose.aliases)

    def test_removing_a_built_in_entry_hides_it_and_unlinks_its_results_without_deleting_them(self):
        result = self._result("Glucose, Fasting", "95", "glucose_fasting", unit="mg/dL")

        response = self.client.delete("/api/lab-tests/types/glucose_fasting/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["removed"], "deactivated")
        self.assertEqual(response.data["unlinked"], 1)

        result.refresh_from_db()
        self.assertIsNone(result.test_type)
        self.assertEqual(result.test_name, "Glucose, Fasting")

        listed = self.client.get("/api/lab-tests/types/", {"q": "glucose"})
        self.assertNotIn("glucose_fasting", [row["name"] for row in listed.data["results"]])

        removed = self.client.get("/api/lab-tests/types/", {"q": "glucose", "active": "false"})
        self.assertIn("glucose_fasting", [row["name"] for row in removed.data["results"]])

        # The loader runs on every deploy and must not quietly bring a removed entry back.
        call_command("populate_lab_tests", stdout=StringIO())
        self.assertFalse(LabTestType.objects.get(name="glucose_fasting").is_active)

    def test_a_removed_entry_can_be_put_back(self):
        self.client.delete("/api/lab-tests/types/glucose_fasting/")
        result = self._result("Glucose, Fasting", "95", unit="mg/dL")

        response = self.client.patch("/api/lab-tests/types/glucose_fasting/", {"is_active": True}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(LabTestType.objects.get(name="glucose_fasting").is_active)
        result.refresh_from_db()
        self.assertEqual(result.test_type.name, "glucose_fasting")

    def test_removing_an_entry_added_here_deletes_it_outright(self):
        created = self.client.post("/api/lab-tests/types/", {
            "display_name": "Zinc", "default_unit": "ug_dl",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)

        response = self.client.delete("/api/lab-tests/types/zinc/")

        self.assertEqual(response.data["removed"], "deleted")
        self.assertFalse(LabTestType.objects.filter(name="zinc").exists())

    def test_no_built_in_entry_is_blocked_by_the_names_of_another(self):
        """Editing any built-in test must not be refused for a name it already answers to."""
        from lab_tests.catalog import conflicting_test

        blocked = []
        for test_type in LabTestType.objects.filter(is_active=True):
            for candidate in [test_type.name, test_type.display_name, *(test_type.aliases or [])]:
                other = conflicting_test(candidate, exclude_pk=test_type.pk)
                if other is not None:
                    blocked.append(f'{test_type.name}: "{candidate}" also names {other.name}')

        self.assertEqual(blocked, [])

    def test_the_catalog_reads_the_names_reports_actually_print(self):
        """Names taken from real reports, with the catalog test each must reach.

        A name reaching the wrong test, or no test, is the failure this guards: the matcher links a name
        only when exactly one catalog test fits, so a name a second test also answers to links to neither.
        """
        from lab_tests.services import resolve_test_type

        expected = {
            # A clotting time, the lab's control, and their ratio stay three separate tests.
            'aPTT (Test)': 'aptt',
            'aPTT': 'aptt',
            'aPTT (Test) - LS': 'aptt_ls',
            'aPTT-Control': 'aptt_control',
            'DRVV Screen (Test)': 'drvv_screen',
            'DRVV Screen Control': 'drvv_screen_control',
            'DRVV Screen Ratio': 'drvv_screen_ratio',
            # A ratio never collapses into either of the tests it is made from.
            'LDL/HDL RATIO': 'ldl_hdl_ratio',
            'LDL Cholesterol': 'ldl_cholesterol',
            'HDL Cholesterol': 'hdl_cholesterol',
            # The urine sample's volume, however the report words it.
            'Quantity': 'urine_volume',
            'Urine Quantity': 'urine_volume',
            'Volume (ml)': 'urine_volume',
            # A report that prints the name with the closing bracket cut off.
            'TSH(THYROID STIMULATING': 'tsh',
            'TSH': 'tsh',
            # Antiphospholipid antibodies, and the total immunoglobulins they must not swallow.
            'Cardiolipin Antibody-IgG': 'cardiolipin_igg',
            'Cardiolipin AntibodyACL- IgG': 'cardiolipin_igg',
            'Cardiolipin AntibodyAnti-IgM': 'cardiolipin_igm',
            'Beta-2-Glycoprotein 1-IgG': 'beta2_glycoprotein_igg',
            'Beta-2-Glycoprotein 1-IgM': 'beta2_glycoprotein_igm',
            'Total IgG': 'igg',
            'IgG': 'igg',
            'IgA': 'iga',
            'IgM': 'igm',
            'Total IgE': 'ige_total',
            # Names an earlier fix settled, kept here so the catalog cannot drift back.
            'Glucose, Fasting': 'glucose_fasting',
            'Mean Platelet Volume': 'mpv',
            'BUN/Creatinine Ratio': 'bun_creatinine_ratio',
            'Urine Specific Gravity': 'urine_specific_gravity',
            # Tests added later, and the tests beside them they must stay apart from.
            'RDW-SD': 'rdw_sd',
            'RDW-CV': 'rdw',
            'Red Cell Distribution Width - SD': 'rdw_sd',
            'Prothrombin Time': 'pt',
            'Prothrombin Time - Control': 'pt_control',
            'INR': 'inr',
            'PT/INR': 'inr',
            'PSA, Total': 'psa_total',
            'Free PSA': 'psa_free',
            'Testosterone, Total': 'testosterone_total',
            'Free Testosterone': 'testosterone_free',
            'Lipoprotein (a)': 'lipoprotein_a',
            'Lp(a)': 'lipoprotein_a',
            'Microalbumin/Creatinine Ratio': 'uacr',
            'Total Cholesterol/HDL Ratio': 'cholesterol_hdl_ratio',
            'Anti TPO': 'anti_tpo',
            'CPK': 'ck',
            'Magnesium, Serum': 'magnesium',
            'Plateletcrit': 'plateletcrit',
            # PCT names plateletcrit on a blood count and procalcitonin elsewhere, so it links to neither.
            'PCT': None,
        }

        # A value is given because a result without a number never links to a catalog test.
        read = {name: resolve_test_type(name, result_value='1') for name in expected}
        self.assertEqual({name: (test.name if test else None) for name, test in read.items()}, expected)

    def test_the_catalog_needs_a_signed_in_user(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/lab-tests/types/").status_code, 401)
        self.assertEqual(
            anonymous.post("/api/lab-tests/types/", {"display_name": "X", "default_unit": "mg_dl"}, format="json").status_code,
            401,
        )
        self.assertEqual(anonymous.delete("/api/lab-tests/types/glucose/").status_code, 401)


class CatalogLoaderTests(TestCase):
    """What populate_lab_tests loads: units, reference ranges, critical limits, and conversions."""

    @classmethod
    def setUpTestData(cls):
        call_command("populate_lab_tests", stdout=StringIO())

    def _rule(self, test_name, unit_name):
        return LabTestValidationRule.objects.get(test_type__name=test_name, unit__name=unit_name)

    def test_the_red_cell_count_is_in_millions(self):
        rbc = LabTestType.objects.get(name="rbc")
        self.assertEqual(rbc.default_unit, "mill_mm3")
        self.assertTrue(LabTestTypeUnit.objects.filter(test_type=rbc, unit__name="mill_mm3", is_active=True).exists())

    def test_ranges_that_depend_on_sex_are_left_to_the_report(self):
        for name in ("hemoglobin", "hematocrit", "rbc", "ferritin"):
            with self.subTest(name=name):
                test_type = LabTestType.objects.get(name=name)
                self.assertIsNone(test_type.normal_min)
                self.assertIsNone(test_type.normal_max)

    def test_critical_limits_are_clinical_not_a_multiple_of_the_range(self):
        potassium = self._rule("potassium", "mmol_l")
        self.assertEqual((potassium.critical_low_min, potassium.critical_high_max), (Decimal("2.8"), Decimal("6.2")))
        self.assertEqual(potassium.validate_value("6.5")[0], "CRITICAL_HIGH")

        tsh = self._rule("tsh", "miu_l")
        self.assertIsNone(tsh.critical_low_min)
        self.assertIsNone(tsh.critical_high_max)
        self.assertEqual(tsh.validate_value("9")[0], "HIGH")

    def test_an_alternate_unit_gets_its_range_and_critical_limits_converted(self):
        calcium = self._rule("calcium", "mmol_l")
        self.assertAlmostEqual(float(calcium.normal_min), 8.5 * 0.2495, places=3)
        self.assertAlmostEqual(float(calcium.critical_high_max), 13.0 * 0.2495, places=3)
        self.assertEqual(calcium.validate_value("2.3")[0], "NORMAL")

    def test_conversions_that_used_to_be_skipped_now_reach_their_tests(self):
        for name, from_unit, to_unit in (
            ("calcium", "mg_dl", "mmol_l"), ("crp", "mg_dl", "mg_l"), ("free_t4", "ng_dl", "pmol_l"),
            ("testosterone_total", "ng_dl", "nmol_l"), ("wbc", "cells_ul", "thou_mm3"),
        ):
            with self.subTest(name=name):
                self.assertTrue(UnitConversion.objects.filter(
                    test_type__name=name, from_unit__name=from_unit, to_unit__name=to_unit,
                ).exists())
        # HbA1c % and mmol/mol are not proportional, so no factor may convert them.
        self.assertFalse(UnitConversion.objects.filter(test_type__name="hba1c").exists())

    def test_a_unit_the_catalog_stopped_using_no_longer_validates(self):
        rbc = LabTestType.objects.get(name="rbc")
        cells = LabTestUnit.objects.get(name="cells_ul")
        LabTestTypeUnit.objects.create(test_type=rbc, unit=cells, normal_min=Decimal("4.0"), normal_max=Decimal("5.2"))
        LabTestValidationRule.objects.create(test_type=rbc, unit=cells, normal_min=Decimal("4.0"), normal_max=Decimal("5.2"))

        call_command("populate_lab_tests", stdout=StringIO())

        self.assertFalse(LabTestTypeUnit.objects.get(test_type=rbc, unit=cells).is_active)
        self.assertFalse(LabTestValidationRule.objects.get(test_type=rbc, unit=cells).is_active)

    def test_cell_counts_in_thousands_share_a_trend_with_counts_per_microlitre(self):
        from types import SimpleNamespace

        from lab_tests.trend_units import CONVERTED, trend_points

        wbc = LabTestType.objects.get(name="wbc")
        results = [
            SimpleNamespace(value="6500", unit="cells/cumm", status="NORMAL", reference_range="4000 - 11000"),
            SimpleNamespace(value="7200", unit="/cu.mm", status="NORMAL", reference_range="4000 - 11000"),
            SimpleNamespace(value="5.8", unit="thou/cumm", status="NORMAL", reference_range="4 - 11"),
        ]

        _, points = trend_points(results, wbc)

        self.assertEqual(points[2]["unit_status"], CONVERTED)
        self.assertEqual(points[2]["value"], "5800")
