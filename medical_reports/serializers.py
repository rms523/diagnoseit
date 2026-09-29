from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from .ai_review import review_summary, visible_review
from .models import MedicalReport, TestResult
from lab_tests.services import build_test_type_matcher, resolve_test_type
from utils.private_files import private_file_url
from utils.upload_validation import validate_medical_upload


class PrivateReportFileField(serializers.FileField):
    """Accept uploads normally, but expose only a short-lived download URL."""

    default_validators = [FileExtensionValidator(allowed_extensions=['pdf'])]

    def to_representation(self, value):
        if not value or not value.name:
            return None
        return private_file_url(
            self.context.get('request'),
            'medical-report-download',
            value.instance.pk,
            value.name,
        )


def _user_id(context) -> int | None:
    request = context.get('request')
    user = getattr(request, 'user', None)
    return user.pk if user is not None and user.is_authenticated else None


class TestResultSerializer(serializers.ModelSerializer):
    """Serializer for TestResult model"""

    # Explicit null for results not linked to the catalog (custom tests); a dotted source would omit the key.
    test_type_name = serializers.SerializerMethodField()

    class Meta:
        model = TestResult
        fields = [
            'id', 'test_type_name', 'test_name', 'value', 'unit', 'reference_range',
            'status', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_test_type_name(self, obj):
        return obj.test_type.name if obj.test_type_id else None

    def validate(self, attrs):
        # Relink when the name or value changes: a value without a number ("Negative") never links.
        if 'test_name' in attrs or 'value' in attrs:
            instance = self.instance if isinstance(self.instance, TestResult) else None
            attrs['test_type'] = resolve_test_type(
                attrs.get('test_name', instance.test_name if instance else ''),
                result_value=attrs.get('value', instance.value if instance else ''),
                user_id=_user_id(self.context),
            )
        return attrs


class MedicalReportSerializer(serializers.ModelSerializer):
    """Serializer for MedicalReport model"""
    test_results = TestResultSerializer(many=True, read_only=True)
    file = PrivateReportFileField()
    ai_review = serializers.SerializerMethodField()
    neighbors = serializers.SerializerMethodField()

    class Meta:
        model = MedicalReport
        fields = [
            'id', 'title', 'report_type', 'lab_name', 'report_date',
            'file', 'parsed_data', 'is_parsed', 'status', 'parse_error', 'ai_review',
            'test_results', 'neighbors', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'parsed_data', 'is_parsed', 'status', 'parse_error', 'created_at', 'updated_at']

    def get_ai_review(self, obj):
        return visible_review(obj)

    def validate_file(self, value):
        if self.instance is not None:
            raise serializers.ValidationError(
                'The document file cannot be replaced. Delete this report and upload the new file instead.'
            )
        try:
            validate_medical_upload(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def get_neighbors(self, obj):
        """The reports before and after this one in the owner's report list, which lists newest first."""
        reports = list(MedicalReport.objects.filter(user_id=obj.user_id).values_list('id', 'title'))
        ids = [pk for pk, _ in reports]
        if obj.pk not in ids:
            return None
        index = ids.index(obj.pk)

        def brief(position):
            if 0 <= position < len(reports):
                return {'id': reports[position][0], 'title': reports[position][1]}
            return None

        return {'previous': brief(index - 1), 'next': brief(index + 1), 'position': index + 1, 'total': len(reports)}

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class MedicalReportListSerializer(serializers.ModelSerializer):
    """Simplified serializer for MedicalReport list view"""
    test_results = TestResultSerializer(many=True, read_only=True)
    ai_review_summary = serializers.SerializerMethodField()

    class Meta:
        model = MedicalReport
        fields = [
            'id', 'title', 'report_type', 'lab_name', 'report_date',
            'is_parsed', 'status', 'ai_review_summary', 'test_results', 'created_at'
        ]

    def get_ai_review_summary(self, obj):
        # One catalog lookup per list response, shared by every report on the page.
        if 'test_type_catalog' not in self.context:
            self.context['test_type_catalog'] = build_test_type_matcher(_user_id(self.context))
        return review_summary(obj, self.context['test_type_catalog'])


class TestResultCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating TestResult"""
    
    class Meta:
        model = TestResult
        fields = [
            'test_name', 'value', 'unit', 'reference_range',
            'status', 'notes'
        ]

    def create(self, validated_data):
        validated_data['report'] = self.context['report']
        validated_data['test_type'] = resolve_test_type(
            validated_data.get('test_name'),
            result_value=validated_data.get('value', ''),
            user_id=self.context['report'].user_id,
        )
        return super().create(validated_data)
