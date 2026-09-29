from rest_framework import serializers
from .models import Diagnosis, DiagnosisHistory, HealthTrend


class DiagnosisHistorySerializer(serializers.ModelSerializer):
    """Serializer for DiagnosisHistory model"""
    
    class Meta:
        model = DiagnosisHistory
        fields = [
            'id', 'condition_name', 'description', 'confidence_score',
            'recommendations', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class DiagnosisSerializer(serializers.ModelSerializer):
    """Serializer for Diagnosis model"""
    history = DiagnosisHistorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Diagnosis
        fields = [
            'id', 'condition_name', 'description', 'confidence_score',
            'symptoms_considered', 'test_results_considered', 'recommendations',
            'follow_up_required', 'follow_up_notes', 'analysis', 'context', 'history',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'analysis', 'context', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class DiagnosisListSerializer(serializers.ModelSerializer):
    """Simplified serializer for Diagnosis list view"""
    
    class Meta:
        model = Diagnosis
        fields = [
            'id', 'condition_name', 'confidence_score',
            'follow_up_required', 'created_at'
        ]


class HealthTrendSerializer(serializers.ModelSerializer):
    """Serializer for HealthTrend model"""
    
    class Meta:
        model = HealthTrend
        fields = [
            'id', 'trend_type', 'parameter_name', 'current_value',
            'previous_value', 'trend_period', 'analysis', 'recommendations',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)