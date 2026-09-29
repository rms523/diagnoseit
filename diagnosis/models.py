from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Diagnosis(models.Model):
    """Model for storing AI-generated diagnoses"""
    CONFIDENCE_CHOICES = [
        (1, 'Very Low'),
        (2, 'Low'),
        (3, 'Medium'),
        (4, 'High'),
        (5, 'Very High'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diagnoses')
    condition_name = models.CharField(max_length=200)
    description = models.TextField()
    confidence_score = models.IntegerField(choices=CONFIDENCE_CHOICES, default=3)
    symptoms_considered = models.JSONField(default=list)  # List of symptom IDs
    test_results_considered = models.JSONField(default=list)  # List of test result IDs
    recommendations = models.TextField(blank=True)
    follow_up_required = models.BooleanField(default=False)
    follow_up_notes = models.TextField(blank=True)
    # The differential and the reasoning behind it (utils.llm_service.normalize_diagnosis): the ranked
    # candidates, what argues for and against each, the model's own likely false positives, patterns it
    # noticed, cautions, and red flags. condition_name and description above are its leading entry.
    analysis = models.JSONField(default=dict, blank=True)
    # What a health timeline diagnosis was based on: mode, period, and how many entries of each kind were sent.
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.condition_name} - {self.user.username} (Confidence: {self.confidence_score})"


class DiagnosisHistory(models.Model):
    """Model for tracking diagnosis changes over time"""
    diagnosis = models.ForeignKey(Diagnosis, on_delete=models.CASCADE, related_name='history')
    condition_name = models.CharField(max_length=200)
    description = models.TextField()
    confidence_score = models.IntegerField(choices=Diagnosis.CONFIDENCE_CHOICES)
    recommendations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.condition_name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class HealthTrend(models.Model):
    """Model for storing health trend analysis"""
    TREND_TYPES = [
        ('IMPROVING', 'Improving'),
        ('STABLE', 'Stable'),
        ('DETERIORATING', 'Deteriorating'),
        ('FLUCTUATING', 'Fluctuating'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='health_trends')
    trend_type = models.CharField(max_length=20, choices=TREND_TYPES)
    parameter_name = models.CharField(max_length=200)  # e.g., "Creatinine", "Blood Pressure"
    current_value = models.CharField(max_length=100)
    previous_value = models.CharField(max_length=100, blank=True)
    trend_period = models.CharField(max_length=100)  # e.g., "Last 6 months", "Last year"
    analysis = models.TextField()
    recommendations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.parameter_name} - {self.trend_type} ({self.user.username})"
