from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db.models.signals import post_delete
from django.dispatch import receiver

User = get_user_model()


class MedicalReport(models.Model):
    """Model for storing medical lab reports and test results"""
    REPORT_TYPES = [
        ('LAB', 'Laboratory Report'),
        ('BLOOD', 'Blood Test'),
        ('URINE', 'Urine Test'),
        ('XRAY', 'X-Ray'),
        ('MRI', 'MRI Scan'),
        ('CT', 'CT Scan'),
        ('OTHER', 'Other'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='medical_reports')
    title = models.CharField(max_length=200)
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES, default='LAB')
    lab_name = models.CharField(max_length=200, blank=True)
    report_date = models.DateField()
    file = models.FileField(
        upload_to='medical_reports/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])]
    )
    parsed_data = models.JSONField(default=dict, blank=True)  # Store extracted data
    is_parsed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    parse_error = models.TextField(blank=True)
    # AI review of the parsed results: pending while queued, then its suggestions or why it failed.
    ai_review = models.JSONField(default=dict, blank=True)
    # The conversation about this report (medical_reports.ai_chat), kept so it is there on the next visit.
    ai_chat = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username} ({self.report_date})"


class TestResult(models.Model):
    """Model for storing individual test results from medical reports"""
    report = models.ForeignKey(MedicalReport, on_delete=models.CASCADE, related_name='test_results')
    test_type = models.ForeignKey(
        'lab_tests.LabTestType',
        on_delete=models.SET_NULL,
        related_name='test_results',
        null=True,
        blank=True,
    )
    test_name = models.CharField(max_length=200)
    value = models.CharField(max_length=100)
    unit = models.CharField(max_length=50, blank=True, null=True, default=None)
    reference_range = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=[('NORMAL', 'Normal'), ('HIGH', 'High'), ('LOW', 'Low'), ('ABNORMAL', 'Abnormal')],
        blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['test_name']

    def __str__(self):
        return f"{self.test_name}: {self.value} {self.unit}"


@receiver(post_delete, sender=MedicalReport)
def delete_medical_report_file(sender, instance, **kwargs):
    """Remove private report content when its database owner is deleted."""
    if instance.file and instance.file.name:
        instance.file.storage.delete(instance.file.name)
