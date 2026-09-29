from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AIServiceConfig(models.Model):
    """Saved connection settings for one AI role, shared by all users; unsaved roles use environment variables."""

    ROLE_DIAGNOSIS = 'diagnosis'
    ROLE_OCR = 'ocr'
    ROLE_REPORT_REVIEW = 'report_review'
    ROLE_CHOICES = [
        (ROLE_DIAGNOSIS, 'AI diagnosis'),
        (ROLE_OCR, 'Report OCR'),
        (ROLE_REPORT_REVIEW, 'Report review assistant'),
    ]

    PROVIDER_OPENAI = 'openai'
    PROVIDER_OLLAMA = 'ollama'
    PROVIDER_CHOICES = [
        (PROVIDER_OPENAI, 'OpenAI-compatible API'),
        (PROVIDER_OLLAMA, 'Ollama native API'),
    ]

    OCR_MODE_CHOICES = [
        ('auto', 'Auto-detect from model name'),
        ('paddle_ocr', 'PaddleOCR-VL (table and OCR prompts)'),
        ('json_vlm', 'Vision model returning JSON'),
    ]

    REVIEW_INPUT_CHOICES = [
        ('auto', 'PDF text, or page images for scans'),
        ('text', 'PDF text only'),
        ('images', 'Page images (vision model)'),
    ]

    role = models.CharField(max_length=32, choices=ROLE_CHOICES, unique=True)
    enabled = models.BooleanField(default=True)
    provider = models.CharField(max_length=16, choices=PROVIDER_CHOICES, default=PROVIDER_OPENAI)
    base_url = models.CharField(max_length=500, blank=True, help_text='For example http://localhost:8080/v1')
    api_key = models.CharField(max_length=500, blank=True)
    model = models.CharField(max_length=200, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=180)
    max_tokens = models.PositiveIntegerField(default=1500)
    temperature = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text='Sampling temperature; blank uses the default for this service.',
    )
    parallel_requests = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(16)],
        help_text="Report OCR only: pages sent to the server at once; match the server's parallel slots.",
    )
    ocr_mode = models.CharField(max_length=16, choices=OCR_MODE_CHOICES, default='auto')
    review_input = models.CharField(max_length=16, choices=REVIEW_INPUT_CHOICES, default='auto')
    auto_review = models.BooleanField(
        default=False,
        help_text='Report review only: review every report after it is parsed. Each report costs one or more model calls.',
    )
    auto_apply = models.BooleanField(
        default=False,
        help_text=(
            'Report review only: apply safe fixes (removing rows that are not results, correcting units, reference '
            'ranges and status) for rows the model was shown. Adds, renames and value changes always wait for the user.'
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        verbose_name = 'AI service configuration'

    def __str__(self):
        return self.get_role_display()
