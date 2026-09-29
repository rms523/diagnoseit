from django.urls import path
from . import ai_chat, test_aliases, views

urlpatterns = [
    path('reports/', views.MedicalReportListCreateView.as_view(), name='medical-report-list'),
    path('reports/<int:pk>/', views.MedicalReportDetailView.as_view(), name='medical-report-detail'),
    path('reports/<int:report_id>/download/', views.download_report_file, name='medical-report-download'),
    path('reports/<int:report_id>/status/', views.report_status, name='report-status'),
    path('reports/<int:report_id>/chat/', ai_chat.report_chat, name='report-chat'),
    path('reports/<int:report_id>/ai-review/', views.ai_review_report, name='report-ai-review'),
    path('reports/<int:report_id>/ai-review/stop/', views.stop_ai_review, name='report-ai-review-stop'),
    path(
        'reports/<int:report_id>/ai-review/suggestions/<int:suggestion_id>/',
        views.dismiss_ai_review_suggestion,
        name='report-ai-review-suggestion',
    ),
    path('reports/<int:report_id>/ai-review/accept/', views.accept_ai_review_suggestions, name='report-ai-review-accept'),
    path(
        'reports/<int:report_id>/ai-review/applied/<int:applied_id>/undo/',
        views.undo_ai_review_change,
        name='report-ai-review-undo',
    ),
    path('reports/bulk-upload/', views.bulk_upload_reports, name='bulk-upload-reports'),
    path('reports/bulk-ai-review/', views.bulk_ai_review_reports, name='bulk-ai-review-reports'),
    path('reports/<int:report_id>/test-results/', views.TestResultListCreateView.as_view(), name='test-result-list'),
    path('reports/<int:report_id>/test-results/<int:pk>/', views.TestResultDetailView.as_view(), name='test-result-detail'),
    path('test-results/search/', views.search_test_results, name='test-result-search'),
    path('test-results/<int:pk>/', views.TestResultUpdateView.as_view(), name='test-result-update'),
    path('test-results/<int:test_result_id>/convert-unit/', views.convert_test_result_unit, name='convert-test-result-unit'),
    path('test-results/<int:test_result_id>/validate/', views.validate_test_result, name='validate-test-result'),
    path('trends/parameters/', views.get_health_trend_parameters, name='health-trend-parameters'),
    path('trends/', views.get_health_trends, name='health-trends'),
    path('trends/multi/', views.get_health_trends_multi, name='health-trends-multi'),
    path('test-aliases/', test_aliases.test_aliases, name='test-aliases'),
    path('test-aliases/suggest/', test_aliases.suggest_test_aliases, name='test-aliases-suggest'),
    path('test-aliases/<int:alias_id>/', test_aliases.test_alias_detail, name='test-alias-detail'),
]
