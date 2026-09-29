"""API tests for symptom tracking, pagination, and cross-user isolation."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Symptom, SymptomLog

User = get_user_model()

PAGE_SIZE = settings.REST_FRAMEWORK["PAGE_SIZE"]


def _symptom(user, description="Headache", **fields):
    return Symptom.objects.create(
        user=user, description=description, onset_date=timezone.now(), **fields
    )


class SymptomAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="patient", password="testpass123")
        self.other = User.objects.create_user(username="stranger", password="testpass123")
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}"
        )
        self.theirs = _symptom(self.other, "Their symptom", notes="private")
        self.their_log = SymptomLog.objects.create(
            symptom=self.theirs, severity=3, notes="private"
        )

    def test_endpoints_require_authentication(self):
        anonymous = APIClient()
        for url in (
            "/api/symptoms/symptoms/",
            "/api/symptoms/symptoms/active/",
            f"/api/symptoms/symptoms/{self.theirs.id}/",
            f"/api/symptoms/symptoms/{self.theirs.id}/logs/",
            f"/api/symptoms/symptoms/{self.theirs.id}/logs/{self.their_log.id}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    anonymous.get(url).status_code, status.HTTP_401_UNAUTHORIZED
                )

    def test_create_assigns_requesting_user(self):
        response = self.client.post(
            "/api/symptoms/symptoms/",
            {
                "description": "Cough",
                "severity": 2,
                "onset_date": timezone.now().isoformat(),
                "user": self.other.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Symptom.objects.get(pk=response.data["id"]).user, self.user)

    def test_list_is_paginated_and_scoped_to_owner(self):
        for i in range(PAGE_SIZE + 3):
            _symptom(self.user, f"Symptom {i}")

        first = self.client.get("/api/symptoms/symptoms/")
        second = self.client.get("/api/symptoms/symptoms/", {"page": 2})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["count"], PAGE_SIZE + 3)
        self.assertEqual(len(first.data["results"]), PAGE_SIZE)
        self.assertIsNotNone(first.data["next"])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second.data["results"]), 3)
        self.assertIsNone(second.data["next"])
        ids = {row["id"] for row in first.data["results"] + second.data["results"]}
        self.assertEqual(len(ids), PAGE_SIZE + 3)
        self.assertNotIn(self.theirs.id, ids)

    def test_other_users_symptom_is_not_reachable(self):
        url = f"/api/symptoms/symptoms/{self.theirs.id}/"

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {"notes": "tampered"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.notes, "private")

    def test_other_users_logs_are_not_reachable(self):
        mine = _symptom(self.user)
        their_logs = f"/api/symptoms/symptoms/{self.theirs.id}/logs/"
        # Pairing an owned symptom with another user's log id must not reach the log.
        crossed = f"/api/symptoms/symptoms/{mine.id}/logs/{self.their_log.id}/"

        self.assertEqual(
            self.client.get(their_logs).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(
            self.client.post(
                their_logs, {"severity": 4, "notes": "injected"}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"{their_logs}{self.their_log.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.get(crossed).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(crossed, {"notes": "tampered"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(crossed).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(SymptomLog.objects.filter(symptom=self.theirs).count(), 1)
        self.their_log.refresh_from_db()
        self.assertEqual(self.their_log.notes, "private")

    def test_owner_can_log_severity_changes(self):
        mine = _symptom(self.user)
        url = f"/api/symptoms/symptoms/{mine.id}/logs/"

        created = self.client.post(url, {"severity": 3, "notes": "worse"}, format="json")
        listing = self.client.get(url)

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertIsInstance(listing.data, list)
        self.assertEqual([row["severity"] for row in listing.data], [3])

    def test_active_symptoms_are_owned_and_ongoing(self):
        ongoing = _symptom(self.user, "Ongoing")
        _symptom(self.user, "Resolved", is_ongoing=False)

        response = self.client.get("/api/symptoms/symptoms/active/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data], [ongoing.id])
