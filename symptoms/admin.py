from django.contrib import admin

from utils.admin_mixins import NoEditAdminMixin
from .models import Symptom, SymptomLog


class SymptomLogInline(NoEditAdminMixin, admin.TabularInline):
    model = SymptomLog
    fields = ('logged_at', 'severity', 'notes')
    readonly_fields = fields
    extra = 0


@admin.register(Symptom)
class SymptomAdmin(NoEditAdminMixin, admin.ModelAdmin):
    list_display = (
        'short_description', 'user', 'severity', 'duration', 'body_part', 'onset_date', 'is_ongoing',
    )
    list_filter = ('is_ongoing', 'severity', 'duration')
    search_fields = ('description', 'body_part', 'user__username', 'user__email')
    list_select_related = ('user',)
    date_hierarchy = 'onset_date'
    inlines = (SymptomLogInline,)

    @admin.display(description='Description')
    def short_description(self, obj):
        return obj.description if len(obj.description) <= 60 else f'{obj.description[:57]}...'
