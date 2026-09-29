from rest_framework import serializers

from .models import AIServiceConfig


class AIServiceConfigUpdateSerializer(serializers.Serializer):
    """Fields users may change; the API key is write-only and never returned."""

    enabled = serializers.BooleanField(required=False)
    provider = serializers.ChoiceField(choices=AIServiceConfig.PROVIDER_CHOICES, required=False)
    base_url = serializers.CharField(required=False, allow_blank=True, max_length=500)
    api_key = serializers.CharField(required=False, allow_blank=True, max_length=500, write_only=True)
    clear_api_key = serializers.BooleanField(required=False, default=False)
    model = serializers.CharField(required=False, allow_blank=True, max_length=200)
    timeout_seconds = serializers.IntegerField(required=False, min_value=5, max_value=1800)
    max_tokens = serializers.IntegerField(required=False, min_value=64, max_value=32000)
    temperature = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=2)
    parallel_requests = serializers.IntegerField(required=False, min_value=1, max_value=16)
    ocr_mode = serializers.ChoiceField(choices=AIServiceConfig.OCR_MODE_CHOICES, required=False)
    review_input = serializers.ChoiceField(choices=AIServiceConfig.REVIEW_INPUT_CHOICES, required=False)
    auto_review = serializers.BooleanField(required=False)
    auto_apply = serializers.BooleanField(required=False)

    def validate_base_url(self, value):
        value = value.strip().rstrip('/')
        if value and not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError('Use a full URL starting with http:// or https://')
        return value
