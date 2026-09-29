from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from .models import PRESCRIPTION_UPLOAD_EXTENSIONS, Prescription, Medication
from utils.private_files import private_file_url
from utils.upload_validation import validate_medical_upload


class PrivatePrescriptionFileField(serializers.FileField):
    """Accept uploads normally, but expose only a short-lived download URL."""

    default_validators = [FileExtensionValidator(allowed_extensions=PRESCRIPTION_UPLOAD_EXTENSIONS)]

    def to_representation(self, value):
        if not value or not value.name:
            return None
        return private_file_url(
            self.context.get('request'),
            'prescription-download',
            value.instance.pk,
            value.name,
        )


class MedicationSerializer(serializers.ModelSerializer):
    """Serializer for Medication model"""
    
    class Meta:
        model = Medication
        fields = [
            'id', 'medication_name', 'dosage', 'frequency',
            'duration', 'instructions', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class PrescriptionSerializer(serializers.ModelSerializer):
    """Serializer for Prescription model"""
    medications = MedicationSerializer(many=True, read_only=True)
    file = PrivatePrescriptionFileField()
    ai_review = serializers.SerializerMethodField()

    def get_ai_review(self, obj):
        from .ai_review import visible_review

        return visible_review(obj)

    def validate_file(self, value):
        if self.instance is not None:
            raise serializers.ValidationError(
                'The document file cannot be replaced. Delete this prescription and upload the new file instead.'
            )
        try:
            validate_medical_upload(value, prescription=True)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value
    
    class Meta:
        model = Prescription
        fields = [
            'id', 'doctor_name', 'hospital_clinic', 'prescription_date',
            'file', 'parsed_data', 'is_parsed', 'status', 'parse_error', 'ai_review', 'medications', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'parsed_data', 'is_parsed', 'status', 'parse_error', 'ai_review', 'created_at', 'updated_at'
        ]

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class PrescriptionListSerializer(serializers.ModelSerializer):
    """Simplified serializer for Prescription list view"""
    
    class Meta:
        model = Prescription
        fields = [
            'id', 'doctor_name', 'hospital_clinic', 'prescription_date',
            'is_parsed', 'status', 'parse_error', 'created_at'
        ]


class MedicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Medication"""

    class Meta:
        model = Medication
        # The id comes back so the page can edit or remove the row it just added.
        fields = [
            'id', 'medication_name', 'dosage', 'frequency',
            'duration', 'instructions'
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        validated_data['prescription'] = self.context['prescription']
        return super().create(validated_data)
