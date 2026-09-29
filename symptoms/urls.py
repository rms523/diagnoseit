from django.urls import path
from . import views

urlpatterns = [
    path('symptoms/', views.SymptomListCreateView.as_view(), name='symptom-list'),
    # Static paths must come before <int:pk> routes
    path('symptoms/active/', views.get_active_symptoms, name='active-symptoms'),
    path('symptoms/<int:pk>/', views.SymptomDetailView.as_view(), name='symptom-detail'),
    path('symptoms/<int:symptom_id>/logs/', views.SymptomLogListCreateView.as_view(), name='symptom-log-list'),
    path('symptoms/<int:symptom_id>/logs/<int:pk>/', views.SymptomLogDetailView.as_view(), name='symptom-log-detail'),
]