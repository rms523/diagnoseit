from django.contrib import admin
from django.db.models import Count

from utils.admin_mixins import NoEditAdminMixin
from .models import Medication, Prescription


class MedicationInline(NoEditAdminMixin, admin.TabularInline):
    model = Medication
    fields = ('medication_name', 'dosage', 'frequency', 'duration', 'instructions')
    readonly_fields = fields
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(NoEditAdminMixin, admin.ModelAdmin):
    list_display = (
        'prescription_date', 'user', 'doctor_name', 'hospital_clinic', 'is_parsed',
        'medication_count', 'created_at',
    )
    list_filter = ('is_parsed', 'prescription_date')
    search_fields = ('doctor_name', 'hospital_clinic', 'user__username', 'user__email')
    list_select_related = ('user',)
    date_hierarchy = 'prescription_date'
    # Uploads are served only through short-lived signed download URLs, never raw paths.
    exclude = ('file',)
    inlines = (MedicationInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_medication_count=Count('medications'))

    @admin.display(description='Medications', ordering='_medication_count')
    def medication_count(self, obj):
        return obj._medication_count
