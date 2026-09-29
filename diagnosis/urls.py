from django.urls import path
from . import views

urlpatterns = [
    path('diagnoses/', views.DiagnosisListCreateView.as_view(), name='diagnosis-list'),
    # Static paths must come before <int:pk> routes
    path('diagnoses/generate/', views.generate_diagnosis_view, name='generate-diagnosis'),
    path('diagnoses/timeline-preview/', views.preview_timeline_diagnosis, name='diagnosis-timeline-preview'),
    path('diagnoses/<int:pk>/', views.DiagnosisDetailView.as_view(), name='diagnosis-detail'),
    path('diagnoses/<int:diagnosis_id>/history/', views.get_diagnosis_history, name='diagnosis-history'),
    path('trends/', views.HealthTrendListCreateView.as_view(), name='health-trend-list'),
    path('trends/<int:pk>/', views.HealthTrendDetailView.as_view(), name='health-trend-detail'),
]