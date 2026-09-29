from django.contrib import admin

from utils.admin_mixins import NoEditAdminMixin
from .models import Diagnosis, DiagnosisHistory, HealthTrend


class DiagnosisHistoryInline(NoEditAdminMixin, admin.TabularInline):
    model = DiagnosisHistory
    fields = ('created_at', 'condition_name', 'confidence_score', 'recommendations')
    readonly_fields = fields
    extra = 0


@admin.register(Diagnosis)
class DiagnosisAdmin(NoEditAdminMixin, admin.ModelAdmin):
    list_display = ('condition_name', 'user', 'confidence_score', 'follow_up_required', 'created_at')
    list_filter = ('confidence_score', 'follow_up_required', 'created_at')
    search_fields = ('condition_name', 'user__username', 'user__email')
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    inlines = (DiagnosisHistoryInline,)


@admin.register(HealthTrend)
class HealthTrendAdmin(NoEditAdminMixin, admin.ModelAdmin):
    list_display = (
        'parameter_name', 'user', 'trend_type', 'current_value', 'previous_value', 'trend_period', 'created_at',
    )
    list_filter = ('trend_type', 'created_at')
    search_fields = ('parameter_name', 'user__username', 'user__email')
    list_select_related = ('user',)
