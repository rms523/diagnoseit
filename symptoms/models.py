from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Symptom(models.Model):
    """Model for storing user-reported symptoms"""
    SEVERITY_CHOICES = [
        (1, 'Mild'),
        (2, 'Moderate'),
        (3, 'Severe'),
        (4, 'Very Severe'),
    ]
    
    DURATION_CHOICES = [
        ('ACUTE', 'Acute (< 1 week)'),
        ('SUBACUTE', 'Subacute (1-4 weeks)'),
        ('CHRONIC', 'Chronic (> 4 weeks)'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='symptoms')
    description = models.TextField()
    severity = models.IntegerField(choices=SEVERITY_CHOICES, default=1)
    duration = models.CharField(max_length=20, choices=DURATION_CHOICES, default='ACUTE')
    body_part = models.CharField(max_length=100, blank=True)  # e.g., "head", "chest", "abdomen"
    onset_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    is_ongoing = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-onset_date', '-created_at']

    def __str__(self):
        return f"{self.description[:50]}... - {self.user.username}"


class SymptomLog(models.Model):
    """Model for tracking symptom changes over time"""
    symptom = models.ForeignKey(Symptom, on_delete=models.CASCADE, related_name='logs')
    severity = models.IntegerField(choices=Symptom.SEVERITY_CHOICES)
    notes = models.TextField(blank=True)
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-logged_at']

    def __str__(self):
        return f"{self.symptom.description[:30]}... - Severity {self.severity}"
