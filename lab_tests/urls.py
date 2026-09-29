"""
URL configuration for lab test management
"""
from django.urls import path
from . import views

app_name = 'lab_tests'

urlpatterns = [
    # Lab test types (the catalog: list and add, then read, change, or remove one by its key)
    path('types/', views.LabTestTypeListView.as_view(), name='test-type-list'),
    path('types/search/', views.search_test_types, name='test-type-search'),
    path('types/suggest-key/', views.suggest_test_type_key, name='test-type-suggest-key'),
    path('types/<str:name>/', views.LabTestTypeDetailView.as_view(), name='test-type-detail'),
    path('types/<str:test_type>/units/', views.LabTestTypeUnitsView.as_view(), name='test-type-units'),
    
    # Lab test units
    path('units/', views.LabTestUnitListView.as_view(), name='unit-list'),
    
    # Unit conversions
    path('convert/', views.convert_units, name='convert-units'),
    path('units/conversions/', views.get_unit_conversions, name='unit-conversions'),
    
    # Validation
    path('validate/', views.validate_test_value, name='validate-value'),
    
    # Categories
    path('categories/test-types/', views.get_test_categories, name='test-categories'),
    path('categories/units/', views.get_unit_categories, name='unit-categories'),
]