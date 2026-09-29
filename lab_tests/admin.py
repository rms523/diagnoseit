"""
Admin configuration for lab tests
"""
from django.contrib import admin
from .models import (
    LabTestType, LabTestUnit, LabTestTypeUnit, UnitConversion,
    LabTestPattern, LabTestValidationRule, UserTestAlias
)


@admin.register(LabTestType)
class LabTestTypeAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'category', 'default_unit', 'normal_min', 'normal_max',
        'is_active', 'source', 'edited_by_user', 'aliases',
    ]
    list_filter = ['category', 'is_active', 'source', 'edited_by_user', 'created_at']
    search_fields = ['name', 'display_name', 'aliases']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['category', 'display_name']


@admin.register(LabTestUnit)
class LabTestUnitAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'symbol', 'category', 'is_base_unit', 'conversion_factor', 'is_active']
    list_filter = ['category', 'is_base_unit', 'is_active']
    search_fields = ['name', 'display_name', 'symbol']
    readonly_fields = ['created_at']
    ordering = ['category', 'name']


@admin.register(LabTestTypeUnit)
class LabTestTypeUnitAdmin(admin.ModelAdmin):
    list_display = ['test_type', 'unit', 'normal_min', 'normal_max', 'conversion_factor', 'is_active']
    list_filter = ['test_type__category', 'unit__category', 'is_active']
    search_fields = ['test_type__display_name', 'unit__display_name']
    readonly_fields = ['created_at']
    ordering = ['test_type', 'unit']


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ['test_type', 'from_unit', 'to_unit', 'conversion_factor', 'reverse_factor', 'is_active']
    list_filter = ['test_type__category', 'from_unit__category', 'to_unit__category', 'is_active']
    search_fields = ['test_type__name', 'test_type__display_name', 'from_unit__name', 'to_unit__name', 'formula']
    readonly_fields = ['created_at']
    ordering = ['test_type', 'from_unit', 'to_unit']


@admin.register(LabTestPattern)
class LabTestPatternAdmin(admin.ModelAdmin):
    list_display = ['test_type', 'pattern_name', 'priority', 'is_active']
    list_filter = ['test_type__category', 'is_active']
    search_fields = ['test_type__display_name', 'pattern_name', 'regex_pattern']
    readonly_fields = ['created_at']
    ordering = ['test_type', '-priority']


@admin.register(LabTestValidationRule)
class LabTestValidationRuleAdmin(admin.ModelAdmin):
    list_display = ['test_type', 'unit', 'normal_min', 'normal_max', 'is_active']
    list_filter = ['test_type__category', 'unit__category', 'is_active']
    search_fields = ['test_type__display_name', 'unit__display_name']
    readonly_fields = ['created_at']
    ordering = ['test_type', 'unit']


@admin.register(UserTestAlias)
class UserTestAliasAdmin(admin.ModelAdmin):
    list_display = ['name', 'test_type', 'user', 'created_at']
    search_fields = ['name', 'test_type__display_name', 'user__username']
    raw_id_fields = ['user']
