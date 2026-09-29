"""API tests for registration, login, profile, password change, and logout."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()

PASSWORD = "Str0ng-passphrase!"
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(PASSWORD_HASHERS=FAST_HASHERS, REGISTRATION_OPEN=True)
class AuthFlowTests(TestCase):
    def setUp(self):
        # Registration and login are rate limited per IP through the default cache.
        cache.clear()
        self.client = APIClient()

    def _register(self, username="newuser", **overrides):
        payload = {
            "username": username,
            "email": f"{username}@example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            **overrides,
        }
        return self.client.post("/api/auth/register/", payload, format="json")

    def test_register_returns_token_without_password(self):
        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("password_confirm", response.data["user"])
        user = User.objects.get(username="newuser")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(Token.objects.get(user=user).key, response.data["token"])

    def test_register_rejects_mismatched_passwords(self):
        response = self._register(password_confirm="Different-passphrase!")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username="taken", password=PASSWORD)

        response = self._register(username="taken")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.filter(username="taken").count(), 1)

    def test_register_is_rate_limited(self):
        statuses = [
            self._register(username=f"user{i}").status_code for i in range(6)
        ]

        self.assertEqual(statuses[:5], [status.HTTP_201_CREATED] * 5)
        self.assertEqual(statuses[5], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_limit_counts_each_client_behind_the_proxy(self):
        # nginx forwards every request, so the limit must follow X-Real-IP rather than its address.
        def attempt(ip):
            return self.client.post(
                "/api/auth/login/", {"username": "nobody", "password": "wrong"}, format="json", HTTP_X_REAL_IP=ip
            ).status_code

        self.assertEqual([attempt("203.0.113.5") for _ in range(6)][-1], status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(attempt("203.0.113.6"), status.HTTP_401_UNAUTHORIZED)

    def test_login_returns_users_token(self):
        user = User.objects.create_user(username="loginuser", password=PASSWORD)

        response = self.client.post(
            "/api/auth/login/",
            {"username": "loginuser", "password": PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertEqual(response.data["token"], Token.objects.get(user=user).key)

    def test_login_rejects_bad_or_missing_credentials(self):
        User.objects.create_user(username="loginuser", password=PASSWORD)

        wrong = self.client.post(
            "/api/auth/login/",
            {"username": "loginuser", "password": "not-the-password"},
            format="json",
        )
        missing = self.client.post(
            "/api/auth/login/", {"username": "loginuser"}, format="json"
        )

        self.assertEqual(wrong.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("token", wrong.data)
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS, REGISTRATION_OPEN=False)
class RegistrationAccessTests(TestCase):
    """Only the first account can sign itself up unless REGISTRATION_OPEN is set."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _register(self, username):
        return self.client.post(
            "/api/auth/register/",
            {"username": username, "email": f"{username}@example.com", "password": PASSWORD, "password_confirm": PASSWORD},
            format="json",
        )

    def test_first_account_becomes_administrator_and_closes_sign_up(self):
        self.assertTrue(self.client.get("/api/auth/registration/").data["open"])

        first = self._register("owner")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        owner = User.objects.get(username="owner")
        self.assertTrue(owner.is_staff and owner.is_superuser)
        self.assertTrue(first.data["user"]["is_staff"])
        self.assertFalse(self.client.get("/api/auth/registration/").data["open"])

        second = self._register("stranger")

        self.assertEqual(second.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("closed", second.data["error"])
        self.assertFalse(User.objects.filter(username="stranger").exists())

    def test_open_registration_admits_members_without_admin_rights(self):
        User.objects.create_user(username="owner", password=PASSWORD, is_staff=True)

        with self.settings(REGISTRATION_OPEN=True):
            self.assertTrue(self.client.get("/api/auth/registration/").data["open"])
            response = self._register("member")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        member = User.objects.get(username="member")
        self.assertFalse(member.is_staff or member.is_superuser)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class ProfileAndSessionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="profile", password=PASSWORD, first_name="Ada"
        )
        self.other = User.objects.create_user(
            username="someone-else", password=PASSWORD, first_name="Grace"
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_account_endpoints_require_authentication(self):
        anonymous = APIClient()

        self.assertEqual(
            anonymous.get("/api/auth/profile/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        for url in ("/api/auth/change-password/", "/api/auth/logout/"):
            with self.subTest(url=url):
                self.assertEqual(
                    anonymous.post(url, {}, format="json").status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_profile_returns_requesting_user(self):
        response = self.client.get("/api/auth/profile/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(response.data["username"], "profile")
        self.assertNotIn("password", response.data)

    def test_profile_update_cannot_target_another_user(self):
        response = self.client.patch(
            "/api/auth/profile/",
            {"id": self.other.id, "first_name": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.id)
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.other.first_name, "Grace")

    def test_change_password_requires_correct_old_password(self):
        new_password = "An0ther-passphrase!"

        response = self.client.post(
            "/api/auth/change-password/",
            {
                "old_password": "not-the-password",
                "new_password": new_password,
                "new_password_confirm": new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_change_password_replaces_credentials(self):
        new_password = "An0ther-passphrase!"

        response = self.client.post(
            "/api/auth/change-password/",
            {
                "old_password": PASSWORD,
                "new_password": new_password,
                "new_password_confirm": new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data["token"], self.token.key)
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(PASSWORD))

        self.assertEqual(self.client.get("/api/auth/profile/").status_code, status.HTTP_401_UNAUTHORIZED)
        current = APIClient()
        current.credentials(HTTP_AUTHORIZATION=f'Token {response.data["token"]}')
        self.assertEqual(current.get("/api/auth/profile/").status_code, status.HTTP_200_OK)

    @override_settings(API_TOKEN_TTL_DAYS=30)
    def test_expired_token_is_rejected_and_removed(self):
        Token.objects.filter(pk=self.token.pk).update(created=timezone.now() - timedelta(days=31))

        self.assertEqual(self.client.get("/api/auth/profile/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Token.objects.filter(pk=self.token.pk).exists())

    def test_logout_revokes_token(self):
        response = self.client.post("/api/auth/logout/", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(
            self.client.get("/api/auth/profile/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
