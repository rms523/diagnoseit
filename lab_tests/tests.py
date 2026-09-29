from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import (
    LabTestType,
    LabTestTypeUnit,
    LabTestUnit,
    LabTestValidationRule,
    UnitConversion,
)


class LabTestSafetyTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="lab-user", password="testpass123", is_staff=True
        )
        token = Token.objects.create(user=user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.mg_dl = LabTestUnit.objects.create(
            name="mg_dl", display_name="Milligrams per Deciliter",
            symbol="mg/dL", category="concentration"
        )
        self.mmol_l = LabTestUnit.objects.create(
            name="mmol_l", display_name="Millimoles per Liter",
            symbol="mmol/L", category="concentration"
        )
        self.glucose = LabTestType.objects.create(
            name="glucose", display_name="Glucose", aliases=["blood sugar"],
            default_unit="mg_dl", normal_min=70, normal_max=100
        )
        self.cholesterol = LabTestType.objects.create(
            name="total_cholesterol", display_name="Total Cholesterol",
            aliases=["cholesterol"], default_unit="mg_dl",
            normal_min=0, normal_max=200
        )
        for test_type in (self.glucose, self.cholesterol):
            LabTestTypeUnit.objects.create(
                test_type=test_type, unit=self.mg_dl,
                normal_min=test_type.normal_min, normal_max=test_type.normal_max
            )
            LabTestTypeUnit.objects.create(
                test_type=test_type, unit=self.mmol_l,
                normal_min=0, normal_max=10
            )

        UnitConversion.objects.create(
            test_type=self.glucose, from_unit=self.mg_dl, to_unit=self.mmol_l,
            conversion_factor=Decimal("0.0555"), reverse_factor=Decimal("18.018")
        )
        UnitConversion.objects.create(
            test_type=self.cholesterol, from_unit=self.mg_dl, to_unit=self.mmol_l,
            conversion_factor=Decimal("0.02586"), reverse_factor=Decimal("38.67")
        )

    def test_conversion_is_scoped_to_analyte(self):
        glucose = self.client.post(
            "/api/lab-tests/convert/",
            {"test_type": "Glucose", "value": "100", "from_unit": "mg_dl", "to_unit": "mmol_l"},
            format="json",
        )
        cholesterol = self.client.post(
            "/api/lab-tests/convert/",
            {"test_type": "cholesterol", "value": "100", "from_unit": "mg_dl", "to_unit": "mmol_l"},
            format="json",
        )

        self.assertEqual(glucose.status_code, 200)
        self.assertEqual(cholesterol.status_code, 200)
        self.assertEqual(Decimal(glucose.data["converted_value"]), Decimal("5.5500"))
        self.assertEqual(Decimal(cholesterol.data["converted_value"]), Decimal("2.5860"))

    def test_validation_falls_back_to_supported_unit_range(self):
        response = self.client.post(
            "/api/lab-tests/validate/",
            {"test_type": "blood sugar", "value": "85", "unit": "mg_dl"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "NORMAL")

    def test_zero_bounds_are_applied(self):
        rule = LabTestValidationRule(
            test_type=self.cholesterol,
            unit=self.mg_dl,
            min_value=Decimal("0"),
            normal_min=Decimal("0"),
            normal_max=Decimal("10"),
        )

        self.assertEqual(rule.validate_value("5")[0], "NORMAL")
        self.assertEqual(rule.validate_value("-1")[0], "INVALID")

    def test_unit_lists_are_unpaginated_arrays(self):
        all_units = self.client.get("/api/lab-tests/units/")
        test_units = self.client.get("/api/lab-tests/types/Glucose/units/")

        self.assertEqual(all_units.status_code, 200)
        self.assertIsInstance(all_units.data, list)
        self.assertEqual(test_units.status_code, 200)
        self.assertIsInstance(test_units.data, list)

    def test_catalog_requires_authentication(self):
        anonymous = APIClient()
        for url in (
            "/api/lab-tests/types/",
            "/api/lab-tests/types/glucose/",
            "/api/lab-tests/types/search/?q=glu",
            "/api/lab-tests/units/",
            "/api/lab-tests/units/conversions/?test_type=glucose",
            "/api/lab-tests/categories/test-types/",
        ):
            with self.subTest(url=url):
                self.assertEqual(anonymous.get(url).status_code, 401)
        self.assertEqual(
            anonymous.post(
                "/api/lab-tests/convert/",
                {"test_type": "glucose", "value": "100", "from_unit": "mg_dl", "to_unit": "mmol_l"},
                format="json",
            ).status_code,
            401,
        )

    def test_catalog_editing_needs_sign_in_and_ignores_client_set_bookkeeping(self):
        """The catalog is shared, and any signed-in user maintains its definitions."""
        anonymous = APIClient()
        refused = anonymous.post(
            "/api/lab-tests/types/",
            {"name": "injected", "display_name": "Injected", "default_unit": "mg_dl"},
            format="json",
        )

        self.assertEqual(refused.status_code, 401)
        self.assertFalse(LabTestType.objects.filter(name="injected").exists())

        member = get_user_model().objects.create_user(username='member', password='testpass123')
        member_client = APIClient()
        member_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=member).key}")
        self.assertEqual(member_client.post(
            "/api/lab-tests/types/", {"name": "by_member", "display_name": "By member", "default_unit": "mg_dl"}, format="json"
        ).status_code, 201)
        self.assertEqual(member_client.get(
            "/api/lab-tests/types/suggest-key/", {"display_name": "Vitamin K"}
        ).data, {"key": "vitamin_k"})
        self.assertEqual(member_client.patch(
            "/api/lab-tests/types/by_member/", {"display_name": "By a member"}, format="json"
        ).status_code, 200)
        self.assertEqual(member_client.delete("/api/lab-tests/types/by_member/").status_code, 200)

        # source and edited_by_user say whether populate_lab_tests may overwrite the entry, so the
        # client does not get to choose them.
        response = self.client.post(
            "/api/lab-tests/types/",
            {"name": "added", "display_name": "Added", "default_unit": "mg_dl",
             "source": "catalog", "edited_by_user": False},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        added = LabTestType.objects.get(name="added")
        self.assertEqual(added.source, LabTestType.SOURCE_USER)
        self.assertTrue(added.edited_by_user)

    def test_type_list_is_paginated(self):
        response = self.client.get("/api/lab-tests/types/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {row["name"] for row in response.data["results"]},
            {"glucose", "total_cholesterol"},
        )
