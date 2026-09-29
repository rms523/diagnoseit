"""
Serializers for lab test management
"""
from rest_framework import serializers
from .models import (
    LabTestType, LabTestUnit, LabTestTypeUnit, UnitConversion,
    LabTestPattern, LabTestValidationRule
)


class LabTestUnitSerializer(serializers.ModelSerializer):
    """Serializer for lab test units"""

    class Meta:
        model = LabTestUnit
        fields = ['id', 'name', 'display_name', 'symbol', 'category', 'is_base_unit', 'conversion_factor', 'is_active']


class LabTestTypeUnitSerializer(serializers.ModelSerializer):
    """Serializer for test type and unit relationships"""

    # Only include basic test type info to avoid circular reference
    test_type_name = serializers.CharField(source='test_type.name', read_only=True)
    test_type_display_name = serializers.CharField(source='test_type.display_name', read_only=True)

    # Include full unit info
    unit = LabTestUnitSerializer(read_only=True)

    class Meta:
        model = LabTestTypeUnit
        fields = [
            'id', 'test_type_name', 'test_type_display_name', 'unit',
            'normal_min', 'normal_max', 'conversion_factor', 'is_active'
        ]


class LabTestTypeSerializer(serializers.ModelSerializer):
    """Serializer for lab test types"""

    supported_units = LabTestTypeUnitSerializer(many=True, read_only=True)
    # Results linked to this test; the catalog page shows what a removal would unlink.
    result_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = LabTestType
        fields = [
            'id', 'name', 'display_name', 'description', 'category', 'aliases',
            'default_unit', 'normal_min', 'normal_max', 'is_active',
            'source', 'edited_by_user', 'result_count',
            'supported_units', 'created_at', 'updated_at'
        ]


class UnitConversionSerializer(serializers.ModelSerializer):
    """Serializer for unit conversions"""

    from_unit = LabTestUnitSerializer(read_only=True)
    to_unit = LabTestUnitSerializer(read_only=True)
    test_type_name = serializers.CharField(source='test_type.name', read_only=True)

    class Meta:
        model = UnitConversion
        fields = [
            'id', 'test_type_name', 'from_unit', 'to_unit', 'conversion_factor', 'reverse_factor',
            'formula', 'notes', 'is_active'
        ]


class LabTestPatternSerializer(serializers.ModelSerializer):
    """Serializer for lab test patterns"""

    test_type = LabTestTypeSerializer(read_only=True)

    class Meta:
        model = LabTestPattern
        fields = [
            'id', 'test_type', 'pattern_name', 'regex_pattern', 'priority',
            'value_group', 'unit_group', 'range_group', 'is_active'
        ]


class LabTestValidationRuleSerializer(serializers.ModelSerializer):
    """Serializer for lab test validation rules"""

    test_type = LabTestTypeSerializer(read_only=True)
    unit = LabTestUnitSerializer(read_only=True)

    class Meta:
        model = LabTestValidationRule
        fields = [
            'id', 'test_type', 'unit', 'min_value', 'max_value',
            'normal_min', 'normal_max', 'critical_low_min', 'critical_high_max',
            'notes', 'is_active'
        ]


class UnitConversionRequestSerializer(serializers.Serializer):
    """Serializer for unit conversion requests"""

    test_type = serializers.CharField(help_text="Test type identifier")
    value = serializers.DecimalField(max_digits=10, decimal_places=4, help_text="Value to convert")
    from_unit = serializers.CharField(help_text="Source unit")
    to_unit = serializers.CharField(help_text="Target unit")

    def validate(self, data):
        """Validate the conversion request"""
        test_type = data.get('test_type')
        from_unit = data.get('from_unit')
        to_unit = data.get('to_unit')

        # Check if test type exists
        from .services import resolve_test_type

        test_type_obj = resolve_test_type(test_type)
        if test_type_obj is None:
            raise serializers.ValidationError(f"Test type '{test_type}' not found")

        # Check if units exist
        try:
            from_unit_obj = LabTestUnit.objects.get(name=from_unit)
            to_unit_obj = LabTestUnit.objects.get(name=to_unit)
        except LabTestUnit.DoesNotExist as e:
            raise serializers.ValidationError(f"Unit not found: {e}")

        # Check if conversion exists
        try:
            UnitConversion.objects.get(
                test_type=test_type_obj,
                from_unit=from_unit_obj,
                to_unit=to_unit_obj,
                is_active=True,
            )
        except UnitConversion.DoesNotExist:
            raise serializers.ValidationError(f"No conversion available from {from_unit} to {to_unit}")

        data['test_type_obj'] = test_type_obj
        data['from_unit_obj'] = from_unit_obj
        data['to_unit_obj'] = to_unit_obj
        return data


class UnitConversionResponseSerializer(serializers.Serializer):
    """Serializer for unit conversion responses"""

    original_value = serializers.DecimalField(max_digits=10, decimal_places=4)
    original_unit = serializers.CharField()
    converted_value = serializers.DecimalField(max_digits=10, decimal_places=4)
    converted_unit = serializers.CharField()
    conversion_factor = serializers.DecimalField(max_digits=15, decimal_places=8)
    formula = serializers.CharField()


class TestValueValidationSerializer(serializers.Serializer):
    """Serializer for test value validation requests"""

    test_type = serializers.CharField(help_text="Test type identifier")
    value = serializers.DecimalField(max_digits=10, decimal_places=4, help_text="Value to validate")
    unit = serializers.CharField(help_text="Unit of measurement")

    def validate(self, data):
        """Validate the validation request"""
        test_type = data.get('test_type')
        unit = data.get('unit')

        from .services import resolve_test_type

        if resolve_test_type(test_type) is None:
            raise serializers.ValidationError(f"Test type '{test_type}' not found")

        # Check if unit exists
        try:
            LabTestUnit.objects.get(name=unit)
        except LabTestUnit.DoesNotExist:
            raise serializers.ValidationError(f"Unit '{unit}' not found")

        return data


class TestValueValidationResponseSerializer(serializers.Serializer):
    """Serializer for test value validation responses"""

    status = serializers.CharField()  # NORMAL, HIGH, LOW, CRITICAL_HIGH, CRITICAL_LOW, INVALID, UNKNOWN
    message = serializers.CharField()
    value = serializers.DecimalField(max_digits=10, decimal_places=4)
    unit = serializers.CharField()
    normal_range = serializers.CharField(allow_null=True)
    critical_range = serializers.CharField(allow_null=True)
