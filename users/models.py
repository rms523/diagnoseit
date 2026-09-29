from django.contrib.auth.models import AbstractUser
from django.db import models
from rest_framework.authtoken.models import TokenProxy


class User(AbstractUser):
    """Extended User model with additional health-related fields"""
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        null=True,
        blank=True
    )
    phone_number = models.CharField(max_length=15, blank=True)
    emergency_contact = models.CharField(max_length=100, blank=True)
    emergency_phone = models.CharField(max_length=15, blank=True)
    # The user's own summary of their health, sent with health timeline diagnoses.
    health_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.email})"


class ApiToken(TokenProxy):
    """API tokens as shown in the admin, labelled by user so the secret key is never rendered."""

    class Meta:
        proxy = True
        verbose_name = 'API token'
        verbose_name_plural = 'API tokens'

    def __str__(self):
        return f"API token for {self.user}"
