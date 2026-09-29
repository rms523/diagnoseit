from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db.models.signals import post_delete
from django.dispatch import receiver

User = get_user_model()


# A prescription is as often photographed as it is downloaded, so an image is a first-class upload here;
# it is read by the report OCR model, the way a scanned PDF is.
PRESCRIPTION_UPLOAD_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff', 'heic', 'heif']


class Prescription(models.Model):
    """Model for storing prescription images and data"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prescriptions')
    doctor_name = models.CharField(max_length=200, blank=True)
    hospital_clinic = models.CharField(max_length=200, blank=True)
    prescription_date = models.DateField()
    file = models.FileField(
        upload_to='prescriptions/',
        validators=[FileExtensionValidator(allowed_extensions=PRESCRIPTION_UPLOAD_EXTENSIONS)]
    )
    parsed_data = models.JSONField(default=dict, blank=True)  # Store extracted data
    is_parsed = models.BooleanField(default=False)
    # Reading a prescription runs in the background, like a report's: the upload returns at PENDING.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    parse_error = models.TextField(blank=True)
    # The conversation about this prescription (utils.ai_chat), kept for the next visit.
    ai_chat = models.JSONField(default=dict, blank=True)
    # The AI review's state and its open suggestions (prescriptions.ai_review).
    ai_review = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-prescription_date', '-created_at']

    def __str__(self):
        return f"Prescription - {self.user.username} ({self.prescription_date})"


class Medication(models.Model):
    """Model for storing individual medications from prescriptions"""
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='medications')
    medication_name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=100, blank=True)  # e.g., "twice daily", "as needed"
    duration = models.CharField(max_length=100, blank=True)  # e.g., "7 days", "1 month"
    instructions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['medication_name']

    def __str__(self):
        return f"{self.medication_name} - {self.dosage}"


@receiver(post_delete, sender=Prescription)
def delete_prescription_file(sender, instance, **kwargs):
    """Remove private prescription content when its database owner is deleted."""
    if instance.file and instance.file.name:
        instance.file.storage.delete(instance.file.name)
