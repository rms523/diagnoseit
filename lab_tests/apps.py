"""
Lab tests app configuration
"""
from django.apps import AppConfig


class LabTestsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lab_tests'
    verbose_name = 'Lab Test Management'