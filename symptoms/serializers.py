from rest_framework import serializers
from .models import Symptom, SymptomLog


class SymptomLogSerializer(serializers.ModelSerializer):
    """Serializer for SymptomLog model"""
    
    class Meta:
        model = SymptomLog
        fields = [
            'id', 'severity', 'notes', 'logged_at'
        ]
        read_only_fields = ['id', 'logged_at']


class SymptomSerializer(serializers.ModelSerializer):
    """Serializer for Symptom model"""
    logs = SymptomLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = Symptom
        fields = [
            'id', 'description', 'severity', 'duration', 'body_part',
            'onset_date', 'end_date', 'is_ongoing', 'notes', 'logs',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class SymptomListSerializer(serializers.ModelSerializer):
    """Simplified serializer for Symptom list view"""
    
    class Meta:
        model = Symptom
        fields = [
            'id', 'description', 'severity', 'duration', 'body_part',
            'onset_date', 'is_ongoing', 'created_at'
        ]


class SymptomLogCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating SymptomLog"""
    
    class Meta:
        model = SymptomLog
        fields = ['severity', 'notes']

    def create(self, validated_data):
        validated_data['symptom'] = self.context['symptom']
        return super().create(validated_data)