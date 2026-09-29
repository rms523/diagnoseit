from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.UserRegistrationView.as_view(), name='user-register'),
    path('registration/', views.registration_status, name='registration-status'),
    path('login/', views.UserLoginView.as_view(), name='user-login'),
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
    path('change-password/', views.change_password, name='change-password'),
    path('logout/', views.logout, name='user-logout'),
    path('csrf-token/', views.get_csrf_token, name='get-csrf-token'),
]