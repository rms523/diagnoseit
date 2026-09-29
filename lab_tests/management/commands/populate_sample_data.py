from django.core.management.base import BaseCommand
from lab_tests.models import LabTestType, LabTestUnit, LabTestTypeUnit, LabTestValidationRule
from decimal import Decimal


class Command(BaseCommand):
    help = 'Populate database with sample lab test data'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample lab test data...')
        
        # Get or create test types
        alt_test = LabTestType.objects.get_or_create(
            name='alt',
            defaults={'display_name': 'ALT (Alanine Aminotransferase)', 'category': 'liver'}
        )[0]
        
        ast_test = LabTestType.objects.get_or_create(
            name='ast',
            defaults={'display_name': 'AST (Aspartate Aminotransferase)', 'category': 'liver'}
        )[0]
        
        albumin_test = LabTestType.objects.get_or_create(
            name='albumin',
            defaults={'display_name': 'Albumin', 'category': 'protein'}
        )[0]
        
        # Get or create units
        u_l_unit = LabTestUnit.objects.get_or_create(
            name='u_l',
            defaults={'display_name': 'Units per Liter', 'symbol': 'U/L', 'category': 'enzyme'}
        )[0]
        
        g_dl_unit = LabTestUnit.objects.get_or_create(
            name='g_dl',
            defaults={'display_name': 'Grams per Deciliter', 'symbol': 'g/dL', 'category': 'protein'}
        )[0]
        
        # Create test type units
        alt_unit, created = LabTestTypeUnit.objects.get_or_create(
            test_type=alt_test,
            unit=u_l_unit,
            defaults={
                'normal_min': Decimal('7'),
                'normal_max': Decimal('56'),
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created ALT unit relationship')
        
        ast_unit, created = LabTestTypeUnit.objects.get_or_create(
            test_type=ast_test,
            unit=u_l_unit,
            defaults={
                'normal_min': Decimal('10'),
                'normal_max': Decimal('40'),
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created AST unit relationship')
        
        albumin_unit, created = LabTestTypeUnit.objects.get_or_create(
            test_type=albumin_test,
            unit=g_dl_unit,
            defaults={
                'normal_min': Decimal('3.5'),
                'normal_max': Decimal('5.0'),
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created Albumin unit relationship')
        
        # Create validation rules
        alt_validation, created = LabTestValidationRule.objects.get_or_create(
            test_type=alt_test,
            unit=u_l_unit,
            defaults={
                'normal_min': Decimal('7'),
                'normal_max': Decimal('56'),
                'critical_low_min': Decimal('0'),
                'critical_high_max': Decimal('200'),
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created ALT validation rule')
        
        ast_validation, created = LabTestValidationRule.objects.get_or_create(
            test_type=ast_test,
            unit=u_l_unit,
            defaults={
                'normal_min': Decimal('10'),
                'normal_max': Decimal('40'),
                'critical_low_min': Decimal('0'),
                'critical_high_max': Decimal('200'),
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created AST validation rule')
        
        albumin_validation, created = LabTestValidationRule.objects.get_or_create(
            test_type=albumin_test,
            unit=g_dl_unit,
            defaults={
                'normal_min': Decimal('3.5'),
                'normal_max': Decimal('5.0'),
                'critical_low_min': Decimal('2.0'),
                'critical_high_max': Decimal('6.0'),
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created Albumin validation rule')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully populated sample lab test data!')
        )