from django.urls import path

from . import views

urlpatterns = [
    path('', views.list_ai_settings, name='ai-settings'),
    # Static paths must come before <str:role> routes
    path('status/', views.ai_status, name='ai-status'),
    path('<str:role>/', views.ai_setting_detail, name='ai-setting-detail'),
    path('<str:role>/test/', views.test_ai_setting, name='ai-setting-test'),
]
