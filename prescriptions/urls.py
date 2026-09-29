from django.urls import path
from . import ai_chat, views

urlpatterns = [
    path('prescriptions/', views.PrescriptionListCreateView.as_view(), name='prescription-list'),
    path('prescriptions/<int:pk>/', views.PrescriptionDetailView.as_view(), name='prescription-detail'),
    path('prescriptions/<int:prescription_id>/download/', views.download_prescription_file, name='prescription-download'),
    path('prescriptions/<int:prescription_id>/status/', views.prescription_status, name='prescription-status'),
    path('prescriptions/<int:prescription_id>/reparse/', views.reparse_prescription, name='prescription-reparse'),
    path('prescriptions/<int:prescription_id>/chat/', ai_chat.prescription_chat, name='prescription-chat'),
    path('prescriptions/<int:prescription_id>/ai-review/', views.review_prescription_with_ai, name='prescription-ai-review'),
    path('prescriptions/<int:prescription_id>/ai-review/stop/', views.stop_prescription_review, name='prescription-ai-review-stop'),
    path('prescriptions/<int:prescription_id>/ai-review/accept/', views.accept_prescription_suggestions, name='prescription-ai-review-accept'),
    path('prescriptions/<int:prescription_id>/ai-review/close/', views.close_prescription_review, name='prescription-ai-review-close'),
    path('prescriptions/<int:prescription_id>/ai-review/suggestions/<int:suggestion_id>/', views.dismiss_prescription_suggestion, name='prescription-ai-review-suggestion'),
    path('prescriptions/<int:prescription_id>/ai-review/applied/<int:applied_id>/undo/', views.undo_prescription_change, name='prescription-ai-review-undo'),
    path('prescriptions/<int:prescription_id>/medications/', views.MedicationListCreateView.as_view(), name='medication-list'),
    path('prescriptions/<int:prescription_id>/medications/<int:pk>/', views.MedicationDetailView.as_view(), name='medication-detail'),
]
