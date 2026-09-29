from django.contrib import admin
from django.db.models import Count

from utils.admin_mixins import NoEditAdminMixin
from .models import MedicalReport, TestResult


class TestResultInline(NoEditAdminMixin, admin.TabularInline):
    model = TestResult
    fields = ('test_name', 'test_type', 'value', 'unit', 'reference_range', 'status', 'notes')
    readonly_fields = fields
    extra = 0


@admin.register(MedicalReport)
class MedicalReportAdmin(NoEditAdminMixin, admin.ModelAdmin):
    list_display = (
        'title', 'user', 'report_type', 'lab_name', 'report_date', 'status', 'result_count', 'created_at',
    )
    list_filter = ('status', 'report_type', 'is_parsed', 'report_date')
    search_fields = ('title', 'lab_name', 'user__username', 'user__email')
    list_select_related = ('user',)
    date_hierarchy = 'report_date'
    # Uploads are served only through short-lived signed download URLs, never raw paths.
    exclude = ('file',)
    inlines = (TestResultInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_result_count=Count('test_results'))

    @admin.display(description='Results', ordering='_result_count')
    def result_count(self, obj):
        return obj._result_count
