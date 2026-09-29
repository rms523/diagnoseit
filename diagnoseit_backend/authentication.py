"""Authentication policies for the API."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """DRF token authentication with a finite, configurable lifetime."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        lifetime_days = int(getattr(settings, 'API_TOKEN_TTL_DAYS', 30))
        if lifetime_days > 0 and token.created < timezone.now() - timedelta(days=lifetime_days):
            token.delete()
            raise AuthenticationFailed('Token has expired. Sign in again.')
        return user, token
