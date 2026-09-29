from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Count
from rest_framework.authtoken.admin import TokenAdmin
from rest_framework.authtoken.models import TokenProxy

from .models import ApiToken, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Account overview with per-user record counts; the records themselves are read-only."""

    list_display = (
        'username', 'email', 'first_name', 'last_name', 'date_joined', 'last_login',
        'is_active', 'is_staff', 'report_count', 'prescription_count', 'symptom_count',
        'diagnosis_count',
    )
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'gender', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-date_joined',)
    readonly_fields = ('last_login', 'date_joined', 'created_at', 'updated_at')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Health profile', {
            'fields': ('date_of_birth', 'gender', 'phone_number', 'emergency_contact', 'emergency_phone'),
        }),
        ('Record timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _report_count=Count('medical_reports', distinct=True),
            _prescription_count=Count('prescriptions', distinct=True),
            _symptom_count=Count('symptoms', distinct=True),
            _diagnosis_count=Count('diagnoses', distinct=True),
        )

    @admin.display(description='Reports', ordering='_report_count')
    def report_count(self, obj):
        return obj._report_count

    @admin.display(description='Prescriptions', ordering='_prescription_count')
    def prescription_count(self, obj):
        return obj._prescription_count

    @admin.display(description='Symptoms', ordering='_symptom_count')
    def symptom_count(self, obj):
        return obj._symptom_count

    @admin.display(description='Diagnoses', ordering='_diagnosis_count')
    def diagnosis_count(self, obj):
        return obj._diagnosis_count


# DRF's token admin renders raw keys (in the list, page titles, and delete confirmation),
# which would let any admin act as that user; ApiToken is labelled by user instead.
admin.site.unregister(TokenProxy)


@admin.register(ApiToken)
class ApiTokenAdmin(TokenAdmin):
    """Show who holds an API token without revealing the key; deleting one signs that user out."""

    list_display = ('user', 'created')
    fields = ('user', 'created')
    readonly_fields = ('user', 'created')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
