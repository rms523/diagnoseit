"""
Management command to populate the database with comprehensive lab test data
"""
from django.core.management.base import BaseCommand
from decimal import Decimal
from lab_tests.models import (
    LabTestType, LabTestUnit, LabTestTypeUnit, UnitConversion,
    LabTestPattern, LabTestValidationRule
)


class Command(BaseCommand):
    help = 'Populate the database with comprehensive lab test data'

    # Catalog keys this run must not touch; filled in by handle() from LabTestType.edited_by_user.
    protected: set[str] = set()

    def handle(self, *args, **options):
        self.stdout.write('Starting to populate lab test data...')

        # Entries someone added or changed in the app are theirs to keep: this command runs after every
        # migration and deploy, so overwriting them here would undo the edit on the next deploy.
        self.protected = set(
            LabTestType.objects.filter(edited_by_user=True).values_list('name', flat=True)
        )
        if self.protected:
            self.stdout.write(f'Leaving {len(self.protected)} catalog entries edited in the app alone.')

        # Create units first
        self.create_units()
        
        # Create test types
        self.create_test_types()
        
        # Create test type unit relationships
        self.create_test_type_units()

        # Create analyte-specific unit conversions and alternate unit ranges
        self.create_unit_conversions()
        
        # Create validation rules
        self.create_validation_rules()
        
        # Create parsing patterns
        self.create_parsing_patterns()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully populated lab test data!')
        )

    def create_units(self):
        """Create measurement units"""
        units_data = [
            # Concentration units
            {'name': 'mg_dl', 'display_name': 'Milligrams per Deciliter', 'symbol': 'mg/dL', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'g_l', 'display_name': 'Grams per Liter', 'symbol': 'g/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.01')},
            {'name': 'mg_l', 'display_name': 'Milligrams per Liter', 'symbol': 'mg/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('10')},
            {'name': 'ug_dl', 'display_name': 'Micrograms per Deciliter', 'symbol': 'μg/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('1000')},
            {'name': 'ng_ml', 'display_name': 'Nanograms per Milliliter', 'symbol': 'ng/mL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('10000')},
            {'name': 'nmol_l', 'display_name': 'Nanomoles per Liter', 'symbol': 'nmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('1')},
            {'name': 'umol_l', 'display_name': 'Micromoles per Liter', 'symbol': 'μmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.001')},
            {'name': 'mmol_l', 'display_name': 'Millimoles per Liter', 'symbol': 'mmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.000001')},
            
            # Count units
            {'name': 'cells_ul', 'display_name': 'Cells per Microliter', 'symbol': 'cells/μL', 'category': 'count', 'is_base_unit': True},
            {'name': 'cells_ml', 'display_name': 'Cells per Milliliter', 'symbol': 'cells/mL', 'category': 'count', 'is_base_unit': False, 'conversion_factor': Decimal('1000')},
            {'name': 'k_cells_ul', 'display_name': 'Thousand Cells per Microliter', 'symbol': 'K/μL', 'category': 'count', 'is_base_unit': False, 'conversion_factor': Decimal('0.001')},
            {'name': 'thou_mm3', 'display_name': 'Thousand per Cubic Millimeter', 'symbol': 'thou/mm3', 'category': 'count', 'is_base_unit': False, 'conversion_factor': Decimal('0.001')},
            {'name': 'lakh_mm3', 'display_name': 'Lakh per Cubic Millimeter', 'symbol': 'lakh/mm3', 'category': 'count', 'is_base_unit': False, 'conversion_factor': Decimal('0.00001')},
            {'name': 'mill_mm3', 'display_name': 'Million per Cubic Millimeter', 'symbol': 'mill/mm3', 'category': 'count', 'is_base_unit': False, 'conversion_factor': Decimal('0.000001')},

            # Cell index and rate units
            {'name': 'fl', 'display_name': 'Femtoliters', 'symbol': 'fL', 'category': 'volume', 'is_base_unit': True},
            {'name': 'pg', 'display_name': 'Picograms', 'symbol': 'pg', 'category': 'mass', 'is_base_unit': True},
            {'name': 'mm_hr', 'display_name': 'Millimeters per Hour', 'symbol': 'mm/hr', 'category': 'rate', 'is_base_unit': True},
            {'name': 'per_hpf', 'display_name': 'Per High Power Field', 'symbol': '/hpf', 'category': 'count', 'is_base_unit': True},
            {'name': 'index', 'display_name': 'Index', 'symbol': 'Index', 'category': 'ratio', 'is_base_unit': True},
            {'name': 'iu_ml', 'display_name': 'International Units per Milliliter', 'symbol': 'IU/mL', 'category': 'concentration', 'is_base_unit': True},

            # Ratio units
            {'name': 'ratio', 'display_name': 'Ratio', 'symbol': '', 'category': 'ratio', 'is_base_unit': True},
            {'name': 'percent', 'display_name': 'Percent', 'symbol': '%', 'category': 'ratio', 'is_base_unit': False, 'conversion_factor': Decimal('100')},
            
            # Time units
            {'name': 'hours', 'display_name': 'Hours', 'symbol': 'hrs', 'category': 'time', 'is_base_unit': True},
            {'name': 'days', 'display_name': 'Days', 'symbol': 'days', 'category': 'time', 'is_base_unit': False, 'conversion_factor': Decimal('0.04166667')},
            
            # Clotting times, reported in seconds
            {'name': 'seconds', 'display_name': 'Seconds', 'symbol': 'sec', 'category': 'time', 'is_base_unit': False, 'conversion_factor': Decimal('3600')},

            # Antibody units. GPL and MPL are IgG and IgM phospholipid units: they are not interchangeable
            # with each other or with plain U/mL, so each keeps its own unit and never converts.
            {'name': 'u_ml', 'display_name': 'Units per Milliliter', 'symbol': 'U/mL', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'gpl_u_ml', 'display_name': 'GPL Units per Milliliter', 'symbol': 'GPL U/mL', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'mpl_u_ml', 'display_name': 'MPL Units per Milliliter', 'symbol': 'MPL U/mL', 'category': 'concentration', 'is_base_unit': True},

            # Volume units
            {'name': 'ml', 'display_name': 'Milliliters', 'symbol': 'mL', 'category': 'volume', 'is_base_unit': True},
            {'name': 'l', 'display_name': 'Liters', 'symbol': 'L', 'category': 'volume', 'is_base_unit': False, 'conversion_factor': Decimal('0.001')},
            
            # Additional units needed for conversions
            {'name': 'g_dl', 'display_name': 'Grams per Deciliter', 'symbol': 'g/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.001')},
            {'name': 'u_l', 'display_name': 'Units per Liter', 'symbol': 'U/L', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'miu_l', 'display_name': 'Micro International Units per Milliliter', 'symbol': 'μIU/mL', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'ng_dl', 'display_name': 'Nanograms per Deciliter', 'symbol': 'ng/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('1000000')},
            {'name': 'pg_ml', 'display_name': 'Picograms per Milliliter', 'symbol': 'pg/mL', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'ml_min_1_73m2', 'display_name': 'mL/min/1.73m²', 'symbol': 'mL/min/1.73m²', 'category': 'rate', 'is_base_unit': True},

            # Additional units for comprehensive conversions
            {'name': 'pmol_l', 'display_name': 'Picomoles per Liter', 'symbol': 'pmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.001')},
            {'name': 'mmhg', 'display_name': 'Millimeters of Mercury', 'symbol': 'mmHg', 'category': 'pressure', 'is_base_unit': True},
            {'name': 'kpa', 'display_name': 'Kilopascals', 'symbol': 'kPa', 'category': 'pressure', 'is_base_unit': False, 'conversion_factor': Decimal('0.133322')},
            {'name': 'mmol_mol', 'display_name': 'Millimoles per Mole', 'symbol': 'mmol/mol', 'category': 'ratio', 'is_base_unit': True},
            {'name': 'miu_ml', 'display_name': 'Milli International Units per Milliliter', 'symbol': 'mIU/mL', 'category': 'concentration', 'is_base_unit': True},
            {'name': 'ug_l', 'display_name': 'Micrograms per Liter', 'symbol': 'μg/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('10000')},
            # Urine albumin to creatinine ratio, in the US and in the UK
            {'name': 'mg_g', 'display_name': 'Milligrams per Gram', 'symbol': 'mg/g', 'category': 'ratio', 'is_base_unit': True},
            {'name': 'mg_mmol', 'display_name': 'Milligrams per Millimole', 'symbol': 'mg/mmol', 'category': 'ratio', 'is_base_unit': True},
            {'name': 'mg_dl_bili', 'display_name': 'Milligrams per Deciliter (Bilirubin)', 'symbol': 'mg/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.1')},
            {'name': 'mg_dl_creat', 'display_name': 'Milligrams per Deciliter (Creatinine)', 'symbol': 'mg/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.1')},
            {'name': 'mg_dl_chol', 'display_name': 'Milligrams per Deciliter (Cholesterol)', 'symbol': 'mg/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.1')},
            {'name': 'mg_dl_gluc', 'display_name': 'Milligrams per Deciliter (Glucose)', 'symbol': 'mg/dL', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.1')},
            {'name': 'mmol_l_calc', 'display_name': 'Millimoles per Liter (Calcium)', 'symbol': 'mmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.000001')},
            {'name': 'mmol_l_mg', 'display_name': 'Millimoles per Liter (Magnesium)', 'symbol': 'mmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.000001')},
            {'name': 'mmol_l_phos', 'display_name': 'Millimoles per Liter (Phosphate)', 'symbol': 'mmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.000001')},
            {'name': 'mmol_l_hemo', 'display_name': 'Millimoles per Liter (Hemoglobin)', 'symbol': 'mmol/L', 'category': 'concentration', 'is_base_unit': False, 'conversion_factor': Decimal('0.000001')},
        ]
        
        for unit_data in units_data:
            # Units are not edited in the app, so a correction here must reach databases loaded before it.
            unit, created = LabTestUnit.objects.update_or_create(
                name=unit_data['name'],
                defaults=unit_data
            )
            if created:
                self.stdout.write(f'Created unit: {unit.display_name}')
            else:
                self.stdout.write(f'Unit already exists: {unit.display_name}')

    def create_test_types(self):
        """Create lab test types"""
        test_types_data = [
            # Basic Metabolic Panel
            {
                'name': 'glucose', 'display_name': 'Glucose', 'category': 'Chemistry',
                'description': 'Blood sugar level, when the report does not say fasting, random, or after a meal', 'aliases': ['blood sugar', 'sugar', 'blood glucose', 'plasma glucose'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('70'), 'normal_max': Decimal('100')
            },
            # Fasting, random, and after-meal glucose are read against different ranges, so each has its own trend.
            {
                'name': 'glucose_fasting', 'display_name': 'Fasting Glucose', 'category': 'Chemistry',
                'description': 'Blood sugar after an overnight fast', 'aliases': ['fbs', 'fasting blood sugar', 'fasting blood glucose', 'fasting plasma glucose', 'fpg'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('70'), 'normal_max': Decimal('100')
            },
            {
                'name': 'glucose_random', 'display_name': 'Random Glucose', 'category': 'Chemistry',
                'description': 'Blood sugar at any time of day', 'aliases': ['rbs', 'random blood sugar', 'random blood glucose', 'random plasma glucose'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'glucose_pp', 'display_name': 'Post Prandial Glucose', 'category': 'Chemistry',
                'description': 'Blood sugar after a meal, usually 2 hours', 'aliases': ['ppbs', 'pp glucose', 'postprandial glucose', 'postprandial blood sugar', 'post prandial blood sugar', 'post prandial plasma glucose'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'creatinine', 'display_name': 'Creatinine', 'category': 'Chemistry',
                'description': 'Serum creatinine (kidney function marker)', 'aliases': ['creat', 'scr', 'serum creatinine'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0.6'), 'normal_max': Decimal('1.2')
            },
            {
                'name': 'urine_creatinine', 'display_name': 'Urine Creatinine', 'category': 'Chemistry',
                'description': 'Urine creatinine (kidney function marker)', 'aliases': ['urine creat', 'u creatinine', 'creatinine urine'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('24.0'), 'normal_max': Decimal('392.0')
            },
            {
                'name': 'urine_protein', 'display_name': 'Urine Protein', 'category': 'Chemistry',
                'description': 'Urine total protein', 'aliases': ['urine prot', 'u protein', 'protein urine'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0'), 'normal_max': Decimal('14.0')
            },
            {
                'name': 'protein_creatinine_ratio', 'display_name': 'Protein Creatinine Ratio', 'category': 'Chemistry',
                'description': 'Urine protein to creatinine ratio', 'aliases': ['prot creat ratio', 'pcr urine'],
                'default_unit': 'ratio', 'normal_min': Decimal('0'), 'normal_max': Decimal('0.20')
            },
            {
                'name': 'urea', 'display_name': 'Urea', 'category': 'Chemistry',
                'description': 'Blood urea (about 2.14 x BUN)', 'aliases': ['blood urea', 'serum urea'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('15'), 'normal_max': Decimal('40')
            },
            {
                'name': 'bun', 'display_name': 'Urea Nitrogen (BUN)', 'category': 'Chemistry',
                'description': 'Blood urea nitrogen', 'aliases': ['blood urea nitrogen', 'urea nitrogen'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('7'), 'normal_max': Decimal('20')
            },
            {
                'name': 'sodium', 'display_name': 'Sodium', 'category': 'Chemistry',
                'description': 'Electrolyte', 'aliases': ['na'],
                'default_unit': 'mmol_l', 'normal_min': Decimal('136'), 'normal_max': Decimal('145')
            },
            {
                'name': 'potassium', 'display_name': 'Potassium', 'category': 'Chemistry',
                'description': 'Electrolyte', 'aliases': ['k'],
                'default_unit': 'mmol_l', 'normal_min': Decimal('3.5'), 'normal_max': Decimal('5.0')
            },
            {
                'name': 'chloride', 'display_name': 'Chloride', 'category': 'Chemistry',
                'description': 'Electrolyte', 'aliases': ['cl'],
                'default_unit': 'mmol_l', 'normal_min': Decimal('98'), 'normal_max': Decimal('107')
            },
            {
                'name': 'co2', 'display_name': 'CO2 (Bicarbonate)', 'category': 'Chemistry',
                'description': 'Bicarbonate', 'aliases': ['bicarbonate', 'hco3'],
                'default_unit': 'mmol_l', 'normal_min': Decimal('22'), 'normal_max': Decimal('28')
            },
            
            # Lipid Panel
            {
                'name': 'total_cholesterol', 'display_name': 'Total Cholesterol', 'category': 'Chemistry',
                'description': 'Total cholesterol level', 'aliases': ['cholesterol', 'total chol'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0'), 'normal_max': Decimal('200')
            },
            {
                'name': 'hdl_cholesterol', 'display_name': 'HDL Cholesterol', 'category': 'Chemistry',
                'description': 'High-density lipoprotein', 'aliases': ['hdl', 'good cholesterol'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('40'), 'normal_max': Decimal('100')
            },
            {
                'name': 'ldl_cholesterol', 'display_name': 'LDL Cholesterol', 'category': 'Chemistry',
                'description': 'Low-density lipoprotein', 'aliases': ['ldl', 'bad cholesterol', 'direct ldl'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0'), 'normal_max': Decimal('100')
            },
            {
                'name': 'vldl_cholesterol', 'display_name': 'VLDL Cholesterol', 'category': 'Chemistry',
                'description': 'Very low-density lipoprotein', 'aliases': ['vldl'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0'), 'normal_max': Decimal('30')
            },
            {
                'name': 'triglycerides', 'display_name': 'Triglycerides', 'category': 'Chemistry',
                'description': 'Triglyceride level', 'aliases': ['trig'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0'), 'normal_max': Decimal('150')
            },
            
            # Liver Function Tests
            {
                'name': 'alt', 'display_name': 'ALT (Alanine Aminotransferase)', 'category': 'Chemistry',
                'description': 'Liver enzyme', 'aliases': ['alanine aminotransferase', 'sgpt'],
                'default_unit': 'u_l', 'normal_min': Decimal('7'), 'normal_max': Decimal('56')
            },
            {
                'name': 'ast', 'display_name': 'AST (Aspartate Aminotransferase)', 'category': 'Chemistry',
                'description': 'Liver enzyme', 'aliases': ['aspartate aminotransferase', 'sgot'],
                'default_unit': 'u_l', 'normal_min': Decimal('10'), 'normal_max': Decimal('40')
            },
            {
                'name': 'alkaline_phosphatase', 'display_name': 'Alkaline Phosphatase', 'category': 'Chemistry',
                'description': 'Liver enzyme', 'aliases': ['alp', 'alk phos'],
                'default_unit': 'u_l', 'normal_min': Decimal('44'), 'normal_max': Decimal('147')
            },
            {
                'name': 'total_bilirubin', 'display_name': 'Total Bilirubin', 'category': 'Chemistry',
                'description': 'Liver function marker', 'aliases': ['bilirubin', 'total bili'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0.3'), 'normal_max': Decimal('1.2')
            },
            {
                'name': 'direct_bilirubin', 'display_name': 'Direct Bilirubin', 'category': 'Chemistry',
                'description': 'Conjugated bilirubin', 'aliases': ['direct bili', 'conjugated bilirubin'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0.0'), 'normal_max': Decimal('0.3')
            },
            {
                'name': 'total_protein', 'display_name': 'Total Protein', 'category': 'Chemistry',
                'description': 'Total protein level', 'aliases': ['protein'],
                'default_unit': 'g_dl', 'normal_min': Decimal('6.0'), 'normal_max': Decimal('8.3')
            },
            {
                'name': 'albumin', 'display_name': 'Albumin', 'category': 'Chemistry',
                'description': 'Albumin level', 'aliases': ['alb'],
                'default_unit': 'g_dl', 'normal_min': Decimal('3.5'), 'normal_max': Decimal('5.0')
            },
            
            # Complete Blood Count. Hemoglobin, hematocrit, and the red cell count have different ranges for men
            # and women, so like GGT and uric acid they have none here and the range printed on the report is used.
            {
                'name': 'hemoglobin', 'display_name': 'Hemoglobin', 'category': 'Hematology',
                'description': 'Hemoglobin level; the reference range depends on sex', 'aliases': ['hb', 'hgb', 'haemoglobin'],
                'default_unit': 'g_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'hematocrit', 'display_name': 'Hematocrit', 'category': 'Hematology',
                'description': 'Hematocrit percentage; the reference range depends on sex', 'aliases': ['hct', 'pcv', 'packed cell volume'],
                'default_unit': 'percent', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'wbc', 'display_name': 'White Blood Cell Count', 'category': 'Hematology',
                'description': 'White blood cell count', 'aliases': ['white blood cell', 'leukocyte', 'leucocyte', 'tlc'],
                'default_unit': 'cells_ul', 'normal_min': Decimal('4500'), 'normal_max': Decimal('11000')
            },
            {
                'name': 'rbc', 'display_name': 'Red Blood Cell Count', 'category': 'Hematology',
                'description': 'Red blood cell count, in millions; the reference range depends on sex', 'aliases': ['red blood cell', 'erythrocyte'],
                'default_unit': 'mill_mm3', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'platelet_count', 'display_name': 'Platelet Count', 'category': 'Hematology',
                'description': 'Platelet count', 'aliases': ['platelet', 'plt'],
                'default_unit': 'cells_ul', 'normal_min': Decimal('150000'), 'normal_max': Decimal('450000')
            },

            # Differential Leucocyte Count (DLC) – percentages
            {
                'name': 'dlc_neutrophils', 'display_name': 'Neutrophils (DLC)', 'category': 'Hematology',
                'description': 'Differential neutrophils percentage', 'aliases': ['segmented neutrophils dlc'],
                'default_unit': 'percent', 'normal_min': Decimal('40.0'), 'normal_max': Decimal('80.0')
            },
            {
                'name': 'dlc_lymphocytes', 'display_name': 'Lymphocytes (DLC)', 'category': 'Hematology',
                'description': 'Differential lymphocytes percentage', 'aliases': [],
                'default_unit': 'percent', 'normal_min': Decimal('20.0'), 'normal_max': Decimal('40.0')
            },
            {
                'name': 'dlc_monocytes', 'display_name': 'Monocytes (DLC)', 'category': 'Hematology',
                'description': 'Differential monocytes percentage', 'aliases': [],
                'default_unit': 'percent', 'normal_min': Decimal('2.0'), 'normal_max': Decimal('10.0')
            },
            {
                'name': 'dlc_eosinophils', 'display_name': 'Eosinophils (DLC)', 'category': 'Hematology',
                'description': 'Differential eosinophils percentage', 'aliases': [],
                'default_unit': 'percent', 'normal_min': Decimal('1.0'), 'normal_max': Decimal('6.0')
            },
            {
                'name': 'dlc_basophils', 'display_name': 'Basophils (DLC)', 'category': 'Hematology',
                'description': 'Differential basophils percentage', 'aliases': [],
                'default_unit': 'percent', 'normal_min': Decimal('0'), 'normal_max': Decimal('2.0')
            },

            # Absolute Leucocyte Count (ALC) – absolute counts
            {
                'name': 'alc_neutrophils', 'display_name': 'Neutrophils (ALC)', 'category': 'Hematology',
                'description': 'Absolute neutrophils count', 'aliases': ['segmented neutrophils alc'],
                'default_unit': 'thou_mm3', 'normal_min': Decimal('2.0'), 'normal_max': Decimal('7.0')
            },
            {
                'name': 'alc_lymphocytes', 'display_name': 'Lymphocytes (ALC)', 'category': 'Hematology',
                'description': 'Absolute lymphocytes count', 'aliases': [],
                'default_unit': 'thou_mm3', 'normal_min': Decimal('1.0'), 'normal_max': Decimal('3.0')
            },
            {
                'name': 'alc_monocytes', 'display_name': 'Monocytes (ALC)', 'category': 'Hematology',
                'description': 'Absolute monocytes count', 'aliases': [],
                'default_unit': 'thou_mm3', 'normal_min': Decimal('0.2'), 'normal_max': Decimal('1.0')
            },
            {
                'name': 'alc_eosinophils', 'display_name': 'Eosinophils (ALC)', 'category': 'Hematology',
                'description': 'Absolute eosinophils count', 'aliases': [],
                'default_unit': 'thou_mm3', 'normal_min': Decimal('0.02'), 'normal_max': Decimal('0.50')
            },
            {
                'name': 'alc_basophils', 'display_name': 'Basophils (ALC)', 'category': 'Hematology',
                'description': 'Absolute basophils count', 'aliases': [],
                'default_unit': 'thou_mm3', 'normal_min': Decimal('0'), 'normal_max': Decimal('0.1')
            },

            # Thyroid Function
            {
                'name': 'tsh', 'display_name': 'TSH (Thyroid Stimulating Hormone)', 'category': 'Endocrinology',
                # "TSH(THYROID STIMULATING" is how a report prints it when the closing bracket is cut off.
                'description': 'Thyroid stimulating hormone', 'aliases': ['thyroid stimulating hormone', 'ultrasensitive tsh', 'tsh thyroid stimulating', 'thyroid stimulating'],
                'default_unit': 'miu_l', 'normal_min': Decimal('0.4'), 'normal_max': Decimal('4.0')
            },
            {
                'name': 't3', 'display_name': 'T3 (Triiodothyronine)', 'category': 'Endocrinology',
                'description': 'Triiodothyronine', 'aliases': ['triiodothyronine', 'tri-iodothyronine'],
                'default_unit': 'ng_dl', 'normal_min': Decimal('80'), 'normal_max': Decimal('200')
            },
            {
                'name': 't4', 'display_name': 'T4 (Thyroxine)', 'category': 'Endocrinology',
                'description': 'Thyroxine', 'aliases': ['thyroxine'],
                'default_unit': 'ug_dl', 'normal_min': Decimal('4.5'), 'normal_max': Decimal('12.0')
            },
            
            # Vitamins and Minerals
            {
                'name': 'vitamin_d', 'display_name': 'Vitamin D (25-OH)', 'category': 'Endocrinology',
                'description': '25-hydroxyvitamin D', 'aliases': ['25-oh vitamin d', '25-oh vit d', 'vit d'],
                'default_unit': 'ng_ml', 'normal_min': Decimal('30'), 'normal_max': Decimal('100')
            },
            {
                'name': 'vitamin_b12', 'display_name': 'Vitamin B12', 'category': 'Endocrinology',
                'description': 'Cobalamin', 'aliases': ['b12', 'cobalamin'],
                'default_unit': 'pg_ml', 'normal_min': Decimal('200'), 'normal_max': Decimal('900')
            },
            {
                'name': 'folate', 'display_name': 'Folate', 'category': 'Endocrinology',
                'description': 'Folic acid', 'aliases': ['folic acid'],
                'default_unit': 'ng_ml', 'normal_min': Decimal('3.0'), 'normal_max': Decimal('17.0')
            },
            {
                'name': 'iron', 'display_name': 'Iron', 'category': 'Chemistry',
                'description': 'Serum iron', 'aliases': ['serum iron'],
                'default_unit': 'ug_dl', 'normal_min': Decimal('60'), 'normal_max': Decimal('170')
            },
            {
                'name': 'ferritin', 'display_name': 'Ferritin', 'category': 'Chemistry',
                'description': 'Iron stores; the reference range depends on sex', 'aliases': [],
                'default_unit': 'ng_ml', 'normal_min': None, 'normal_max': None
            },
            
            # Diabetes Markers
            {
                'name': 'hba1c', 'display_name': 'HbA1c', 'category': 'Chemistry',
                'description': 'Glycated hemoglobin', 'aliases': ['hemoglobin a1c', 'glycated hemoglobin', 'glycosylated hemoglobin', 'glycosylated haemoglobin'],
                'default_unit': 'percent', 'normal_min': Decimal('4.0'), 'normal_max': Decimal('5.6')
            },
            
            # Kidney Function
            {
                'name': 'egfr', 'display_name': 'eGFR', 'category': 'Chemistry',
                'description': 'Estimated glomerular filtration rate', 'aliases': ['gfr', 'estimated gfr'],
                'default_unit': 'ml_min_1_73m2', 'normal_min': Decimal('90'), 'normal_max': Decimal('120')
            },
            # Red cell and platelet indices
            {
                'name': 'mcv', 'display_name': 'MCV (Mean Corpuscular Volume)', 'category': 'Hematology',
                'description': 'Average red cell volume', 'aliases': ['mean corpuscular volume', 'mean cell volume'],
                'default_unit': 'fl', 'normal_min': Decimal('80'), 'normal_max': Decimal('100')
            },
            {
                'name': 'mch', 'display_name': 'MCH (Mean Corpuscular Hemoglobin)', 'category': 'Hematology',
                'description': 'Average hemoglobin per red cell',
                'aliases': ['mean corpuscular hemoglobin', 'mean corpuscular haemoglobin', 'mean corpuscular hb', 'mean cell hemoglobin'],
                'default_unit': 'pg', 'normal_min': Decimal('27'), 'normal_max': Decimal('33')
            },
            {
                'name': 'mchc', 'display_name': 'MCHC (Mean Corpuscular Hemoglobin Concentration)', 'category': 'Hematology',
                'description': 'Average hemoglobin concentration in red cells',
                'aliases': [
                    'mean corpuscular hemoglobin concentration', 'mean corpuscular haemoglobin concentration',
                    'mean corpuscular hb concentration', 'mean corpuscular hb concn', 'mean cell hemoglobin concentration',
                ],
                'default_unit': 'g_dl', 'normal_min': Decimal('32'), 'normal_max': Decimal('36')
            },
            {
                'name': 'rdw', 'display_name': 'RDW (Red Cell Distribution Width)', 'category': 'Hematology',
                'description': 'Variation in red cell size (coefficient of variation)',
                'aliases': ['red cell distribution width', 'rdw cv', 'red cell distribution width cv'],
                'default_unit': 'percent', 'normal_min': Decimal('11.5'), 'normal_max': Decimal('14.5')
            },
            {
                'name': 'mpv', 'display_name': 'MPV (Mean Platelet Volume)', 'category': 'Hematology',
                'description': 'Average platelet volume', 'aliases': ['mean platelet volume'],
                'default_unit': 'fl', 'normal_min': Decimal('7.5'), 'normal_max': Decimal('11.5')
            },
            {
                'name': 'esr', 'display_name': 'ESR (Erythrocyte Sedimentation Rate)', 'category': 'Hematology',
                'description': 'Erythrocyte sedimentation rate; the reference range depends on age and sex',
                'aliases': ['erythrocyte sedimentation rate', 'sed rate'],
                'default_unit': 'mm_hr', 'normal_min': None, 'normal_max': None
            },

            # Inflammation markers (CRP and hs-CRP are different assays with different reference ranges)
            {
                'name': 'crp', 'display_name': 'CRP (C-Reactive Protein)', 'category': 'Immunology',
                'description': 'C-reactive protein; the reference range depends on the lab', 'aliases': ['c-reactive protein'],
                'default_unit': 'mg_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'hs_crp', 'display_name': 'hs-CRP (High Sensitivity C-Reactive Protein)', 'category': 'Immunology',
                'description': 'High-sensitivity CRP, reported as cardiovascular risk bands',
                'aliases': ['hscrp', 'high sensitivity crp', 'high sensitivity c-reactive protein', 'cardio crp', 'cardio c-reactive protein'],
                'default_unit': 'mg_l', 'normal_min': None, 'normal_max': None
            },

            # Liver and kidney panels
            {
                'name': 'ggt', 'display_name': 'GGT (Gamma-Glutamyl Transferase)', 'category': 'Chemistry',
                'description': 'Liver enzyme; the reference range depends on sex',
                'aliases': ['ggtp', 'gamma gt', 'gamma-glutamyl transferase', 'gamma-glutamyl transpeptidase'],
                'default_unit': 'u_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'globulin', 'display_name': 'Globulin', 'category': 'Chemistry',
                'description': 'Total protein minus albumin', 'aliases': [],
                'default_unit': 'g_dl', 'normal_min': Decimal('2.0'), 'normal_max': Decimal('3.5')
            },
            {
                'name': 'indirect_bilirubin', 'display_name': 'Indirect Bilirubin', 'category': 'Chemistry',
                'description': 'Unconjugated bilirubin (total minus direct)', 'aliases': ['unconjugated bilirubin'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0.1'), 'normal_max': Decimal('1.0')
            },
            {
                'name': 'calcium', 'display_name': 'Calcium', 'category': 'Chemistry',
                'description': 'Total calcium', 'aliases': ['ca'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('8.5'), 'normal_max': Decimal('10.5')
            },
            {
                'name': 'phosphorus', 'display_name': 'Phosphorus', 'category': 'Chemistry',
                'description': 'Inorganic phosphorus', 'aliases': ['phosphate', 'inorganic phosphorus'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('2.5'), 'normal_max': Decimal('4.5')
            },
            {
                'name': 'uric_acid', 'display_name': 'Uric Acid', 'category': 'Chemistry',
                'description': 'Uric acid; the reference range depends on sex', 'aliases': ['urate'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },

            # Lipid and diabetes derived values
            {
                'name': 'non_hdl_cholesterol', 'display_name': 'Non-HDL Cholesterol', 'category': 'Chemistry',
                'description': 'Total cholesterol minus HDL', 'aliases': ['non hdl'],
                'default_unit': 'mg_dl', 'normal_min': Decimal('0'), 'normal_max': Decimal('130')
            },
            {
                'name': 'eag', 'display_name': 'eAG (Estimated Average Glucose)', 'category': 'Chemistry',
                'description': 'Average glucose estimated from HbA1c', 'aliases': ['estimated average glucose'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },

            # Free thyroid hormones (separate from total T3 and T4)
            {
                'name': 'free_t3', 'display_name': 'Free T3', 'category': 'Endocrinology',
                'description': 'Free triiodothyronine; the reference range depends on the assay', 'aliases': ['ft3', 'free triiodothyronine'],
                'default_unit': 'pg_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'free_t4', 'display_name': 'Free T4', 'category': 'Endocrinology',
                'description': 'Free thyroxine; the reference range depends on the assay', 'aliases': ['ft4', 'free thyroxine'],
                'default_unit': 'ng_dl', 'normal_min': None, 'normal_max': None
            },
            # Tests found in reports that the catalog lacked; urine ones match rows in urine sections or counted per field.
            {
                'name': 'ag_ratio', 'display_name': 'A/G Ratio (Albumin/Globulin)', 'category': 'Chemistry',
                'description': 'Albumin to globulin ratio', 'aliases': ['albumin globulin ratio', 'a:g ratio'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'bun_creatinine_ratio', 'display_name': 'BUN/Creatinine Ratio', 'category': 'Chemistry',
                'description': 'Blood urea nitrogen to creatinine ratio', 'aliases': ['urea nitrogen/creatinine ratio', 'bun creatinine ratio'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'amylase', 'display_name': 'Amylase', 'category': 'Chemistry',
                'description': 'Pancreatic enzyme', 'aliases': [],
                'default_unit': 'u_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'apo_a1', 'display_name': 'Apolipoprotein A1 (Apo A1)', 'category': 'Chemistry',
                'description': 'Main protein of HDL cholesterol', 'aliases': ['apoa1'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'apo_b', 'display_name': 'Apolipoprotein B (Apo B)', 'category': 'Chemistry',
                'description': 'Main protein of LDL and VLDL cholesterol', 'aliases': ['apob'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'apo_b_a1_ratio', 'display_name': 'Apo B/Apo A1 Ratio', 'category': 'Chemistry',
                'description': 'Apolipoprotein B to A1 ratio', 'aliases': ['apolipoprotein b / apo a1 ratio', 'apolipoprotein b/a1 ratio', 'apob/apoa1 ratio'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'cystatin_c', 'display_name': 'Cystatin C', 'category': 'Chemistry',
                'description': 'Kidney function marker', 'aliases': [],
                'default_unit': 'mg_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'egfr_cystatin_c', 'display_name': 'eGFR Cystatin C', 'category': 'Chemistry',
                'description': 'Estimated GFR calculated from cystatin C, not creatinine', 'aliases': ['egfrcystatin c', 'egfr cystatin', 'cystatin c egfr'],
                'default_unit': 'ml_min_1_73m2', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'testosterone_total', 'display_name': 'Total Testosterone', 'category': 'Endocrinology',
                'description': 'Total testosterone', 'aliases': ['testosterone'],
                'default_unit': 'ng_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'tibc', 'display_name': 'TIBC (Total Iron Binding Capacity)', 'category': 'Chemistry',
                'description': 'Total iron binding capacity', 'aliases': ['total iron binding capacity', 'iron binding capacity'],
                'default_unit': 'ug_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'transferrin_saturation', 'display_name': 'Transferrin Saturation', 'category': 'Chemistry',
                'description': 'Share of transferrin carrying iron', 'aliases': ['tsat', 'iron saturation'],
                'default_unit': 'percent', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'mentzer_index', 'display_name': 'Mentzer Index', 'category': 'Hematology',
                'description': 'MCV divided by red blood cell count', 'aliases': [],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'urine_ph', 'display_name': 'Urine pH', 'category': 'Urinalysis',
                'description': 'Acidity of urine', 'aliases': ['ph, urine'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'urine_specific_gravity', 'display_name': 'Urine Specific Gravity', 'category': 'Urinalysis',
                'description': 'Concentration of urine', 'aliases': ['specific gravity, urine'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'urine_pus_cells', 'display_name': 'Urine Pus Cells', 'category': 'Urinalysis',
                'description': 'White blood cells per high power field in urine', 'aliases': ['pus cells, urine', 'urine wbc', 'urine leucocytes', 'urine leukocytes'],
                'default_unit': 'per_hpf', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'urine_epithelial_cells', 'display_name': 'Urine Epithelial Cells', 'category': 'Urinalysis',
                'description': 'Epithelial cells per high power field in urine', 'aliases': ['epithelial cells, urine', 'urine squamous epithelial cells'],
                'default_unit': 'per_hpf', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'dengue_ns1', 'display_name': 'Dengue NS1 Antigen', 'category': 'Immunology',
                'description': 'Dengue NS1 antigen index', 'aliases': ['dengue fever antigen ns1', 'dengue ns1'],
                'default_unit': 'index', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'dengue_igg', 'display_name': 'Dengue IgG Antibody', 'category': 'Immunology',
                'description': 'Dengue IgG antibody index', 'aliases': ['dengue fever antibody igg', 'dengue igg'],
                'default_unit': 'index', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'dengue_igm', 'display_name': 'Dengue IgM Antibody', 'category': 'Immunology',
                'description': 'Dengue IgM antibody index', 'aliases': ['dengue fever antibody igm', 'dengue igm'],
                'default_unit': 'index', 'normal_min': None, 'normal_max': None
            },
            # Immunoglobulins, complement, ACE, and PTH.
            {
                'name': 'iga', 'display_name': 'Immunoglobulin A (IgA)', 'category': 'Immunology',
                'description': 'Serum immunoglobulin A', 'aliases': ['immunoglobulin iga'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'igg', 'display_name': 'Immunoglobulin G (IgG)', 'category': 'Immunology',
                'description': 'Serum immunoglobulin G', 'aliases': ['immunoglobulin igg'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'igm', 'display_name': 'Immunoglobulin M (IgM)', 'category': 'Immunology',
                'description': 'Serum immunoglobulin M', 'aliases': ['immunoglobulin igm'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'ige_total', 'display_name': 'Total IgE', 'category': 'Immunology',
                'description': 'Total immunoglobulin E', 'aliases': ['ige', 'immunoglobulin e', 'immunoglobulin ige'],
                'default_unit': 'iu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'ace', 'display_name': 'ACE (Angiotensin Converting Enzyme)', 'category': 'Chemistry',
                'description': 'Angiotensin converting enzyme', 'aliases': ['angiotensin converting enzyme'],
                'default_unit': 'u_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'complement_c3', 'display_name': 'Complement C3', 'category': 'Immunology',
                'description': 'Complement component C3', 'aliases': ['c3'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'complement_c4', 'display_name': 'Complement C4', 'category': 'Immunology',
                'description': 'Complement component C4', 'aliases': ['c4'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'pth_intact', 'display_name': 'Intact PTH (Parathyroid Hormone)', 'category': 'Endocrinology',
                'description': 'Intact parathyroid hormone', 'aliases': ['pth', 'intact parathyroid hormone', 'parathyroid hormone intact'],
                'default_unit': 'pg_ml', 'normal_min': None, 'normal_max': None
            },

            # Coagulation. A clotting time, the lab's control run beside it, and their ratio are three
            # different numbers, so each is its own test: putting a control on the patient's trend would
            # be wrong. These ranges depend on the lab's reagent, so the printed range is used.
            {
                'name': 'aptt', 'display_name': 'aPTT (Activated Partial Thromboplastin Time)', 'category': 'Coagulation',
                'description': "The patient's activated partial thromboplastin time",
                'aliases': ['aptt', 'activated partial thromboplastin time', 'partial thromboplastin time', 'ptt'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'aptt_ls', 'display_name': 'aPTT Lupus Sensitive', 'category': 'Coagulation',
                'description': 'aPTT run with a lupus-sensitive reagent, read separately from the plain aPTT',
                'aliases': ['aptt ls', 'aptt lupus sensitive', 'lupus sensitive aptt'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'aptt_control', 'display_name': 'aPTT Control', 'category': 'Coagulation',
                'description': "The laboratory's control aPTT, not the patient's result",
                'aliases': ['aptt control', 'aptt normal control'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'drvv_screen', 'display_name': 'DRVV Screen', 'category': 'Coagulation',
                'description': 'Dilute Russell viper venom screen, for lupus anticoagulant',
                'aliases': ['drvv screen', 'drvvt screen', 'dilute russell viper venom screen', 'drvv screening'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'drvv_screen_control', 'display_name': 'DRVV Screen Control', 'category': 'Coagulation',
                'description': "The laboratory's control for the DRVV screen",
                'aliases': ['drvv screen control', 'drvv control'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'drvv_screen_ratio', 'display_name': 'DRVV Screen Ratio', 'category': 'Coagulation',
                'description': 'DRVV screen divided by its control',
                'aliases': ['drvv screen ratio', 'drvv ratio'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },

            # Lipid ratio. "ratio" is a qualifier, so this never merges with LDL or HDL themselves.
            {
                'name': 'ldl_hdl_ratio', 'display_name': 'LDL/HDL Ratio', 'category': 'Chemistry',
                'description': 'LDL cholesterol divided by HDL cholesterol',
                'aliases': ['ldl hdl ratio', 'ldl to hdl ratio'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },

            # Urine volume. Reports print it as "Quantity", "Urine Quantity", or "Volume (ml)"; a urine
            # sample is the only volume these panels report, so the bare names are read as this test.
            {
                'name': 'urine_volume', 'display_name': 'Urine Volume', 'category': 'Urinalysis',
                'description': 'Volume of the urine sample',
                'aliases': ['urine quantity', 'quantity', 'volume', 'urine output', 'sample volume'],
                'default_unit': 'ml', 'normal_min': None, 'normal_max': None
            },

            # Antiphospholipid antibodies. IgG and IgM are separate measurements in separate units, and a
            # report writes the name several ways ("Cardiolipin AntibodyACL- IgG", "AntibodyAnti-IgG").
            # None of these names carries a comma: a comma would split off a bare "IgG" reading, and the
            # total immunoglobulin of that class would then match two tests and link to neither.
            {
                'name': 'cardiolipin_igg', 'display_name': 'Cardiolipin Antibody IgG', 'category': 'Immunology',
                'description': 'Anti-cardiolipin antibody, IgG class',
                'aliases': ['cardiolipin antibody igg', 'anticardiolipin igg', 'anti cardiolipin igg', 'acl igg',
                            'cardiolipin antibodyacl igg', 'cardiolipin antibodyanti igg'],
                'default_unit': 'gpl_u_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'cardiolipin_igm', 'display_name': 'Cardiolipin Antibody IgM', 'category': 'Immunology',
                'description': 'Anti-cardiolipin antibody, IgM class',
                'aliases': ['cardiolipin antibody igm', 'anticardiolipin igm', 'anti cardiolipin igm', 'acl igm',
                            'cardiolipin antibodyacl igm', 'cardiolipin antibodyanti igm'],
                'default_unit': 'mpl_u_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'beta2_glycoprotein_igg', 'display_name': 'Beta-2-Glycoprotein 1 IgG', 'category': 'Immunology',
                'description': 'Anti-beta-2-glycoprotein 1 antibody, IgG class',
                'aliases': ['beta 2 glycoprotein 1 igg', 'beta2 glycoprotein igg', 'b2 glycoprotein 1 igg',
                            'anti beta2 glycoprotein 1 igg'],
                'default_unit': 'u_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'beta2_glycoprotein_igm', 'display_name': 'Beta-2-Glycoprotein 1 IgM', 'category': 'Immunology',
                'description': 'Anti-beta-2-glycoprotein 1 antibody, IgM class',
                'aliases': ['beta 2 glycoprotein 1 igm', 'beta2 glycoprotein igm', 'b2 glycoprotein 1 igm',
                            'anti beta2 glycoprotein 1 igm'],
                'default_unit': 'u_ml', 'normal_min': None, 'normal_max': None
            },
            # Common tests the catalog lacked. A range is given only where it does not depend on the lab's assay,
            # sex, age, time of day, or cycle; otherwise the range printed on the report is used.
            {
                'name': 'magnesium', 'display_name': 'Magnesium', 'category': 'Chemistry',
                'description': 'Serum magnesium', 'aliases': [],
                'default_unit': 'mg_dl', 'normal_min': Decimal('1.7'), 'normal_max': Decimal('2.2')
            },
            {
                'name': 'ldh', 'display_name': 'LDH (Lactate Dehydrogenase)', 'category': 'Chemistry',
                'description': 'Tissue damage marker; the reference range depends on the method',
                'aliases': ['lactate dehydrogenase', 'lactic dehydrogenase'],
                'default_unit': 'u_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'ck', 'display_name': 'CK (Creatine Kinase)', 'category': 'Chemistry',
                'description': 'Muscle enzyme; the reference range depends on sex',
                'aliases': ['cpk', 'creatine kinase', 'creatine phosphokinase'],
                'default_unit': 'u_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'lipase', 'display_name': 'Lipase', 'category': 'Chemistry',
                'description': 'Pancreatic enzyme; the reference range depends on the method', 'aliases': [],
                'default_unit': 'u_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'uibc', 'display_name': 'UIBC (Unsaturated Iron Binding Capacity)', 'category': 'Chemistry',
                'description': 'Iron binding capacity not yet carrying iron', 'aliases': ['unsaturated iron binding capacity'],
                'default_unit': 'ug_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'transferrin', 'display_name': 'Transferrin', 'category': 'Chemistry',
                'description': 'Iron transport protein', 'aliases': [],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'homocysteine', 'display_name': 'Homocysteine', 'category': 'Chemistry',
                'description': 'Amino acid linked to B12 and folate status and cardiovascular risk', 'aliases': [],
                'default_unit': 'umol_l', 'normal_min': Decimal('5'), 'normal_max': Decimal('15')
            },
            {
                'name': 'lipoprotein_a', 'display_name': 'Lipoprotein(a)', 'category': 'Chemistry',
                # Reported in mg/dL or nmol/L; the two measure different things and cannot be converted.
                'description': 'Inherited cardiovascular risk marker', 'aliases': ['lp(a)', 'lipoprotein a'],
                'default_unit': 'mg_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'cholesterol_hdl_ratio', 'display_name': 'Total Cholesterol/HDL Ratio', 'category': 'Chemistry',
                'description': 'Total cholesterol divided by HDL cholesterol',
                'aliases': ['cholesterol hdl ratio', 'chol hdl ratio', 'tc hdl ratio', 'total cholesterol to hdl ratio'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'urine_albumin', 'display_name': 'Urine Albumin (Microalbumin)', 'category': 'Urinalysis',
                'description': 'Albumin in urine', 'aliases': ['microalbumin', 'urine microalbumin', 'urinary albumin'],
                'default_unit': 'mg_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'uacr', 'display_name': 'Urine Albumin/Creatinine Ratio (UACR)', 'category': 'Urinalysis',
                # Below 30 mg/g is normal (KDIGO) whatever the lab, sex, or age.
                'description': 'Urine albumin divided by urine creatinine',
                'aliases': ['acr', 'albumin creatinine ratio', 'microalbumin creatinine ratio', 'urine albumin creatinine ratio'],
                'default_unit': 'mg_g', 'normal_min': Decimal('0'), 'normal_max': Decimal('30')
            },
            {
                'name': 'urine_rbc', 'display_name': 'Urine Red Blood Cells', 'category': 'Urinalysis',
                'description': 'Red blood cells per high power field in urine',
                'aliases': ['rbc, urine', 'urine rbc', 'urine red blood cells', 'urine erythrocytes'],
                'default_unit': 'per_hpf', 'normal_min': None, 'normal_max': None
            },

            # Hormones and tumour markers
            {
                'name': 'insulin', 'display_name': 'Insulin', 'category': 'Endocrinology',
                'description': 'Serum insulin; the reference range depends on the assay and on fasting',
                'aliases': ['fasting insulin'],
                'default_unit': 'miu_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'c_peptide', 'display_name': 'C-Peptide', 'category': 'Endocrinology',
                'description': 'Marker of the body\'s own insulin production', 'aliases': ['c peptide'],
                'default_unit': 'ng_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'cortisol', 'display_name': 'Cortisol', 'category': 'Endocrinology',
                'description': 'Serum cortisol; the reference range depends on the time of day', 'aliases': [],
                'default_unit': 'ug_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'prolactin', 'display_name': 'Prolactin', 'category': 'Endocrinology',
                'description': 'Pituitary hormone; the reference range depends on sex', 'aliases': ['prl'],
                'default_unit': 'ng_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'lh', 'display_name': 'LH (Luteinizing Hormone)', 'category': 'Endocrinology',
                'description': 'Luteinizing hormone; the reference range depends on sex and cycle phase',
                'aliases': ['luteinizing hormone', 'luteinising hormone'],
                'default_unit': 'miu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'fsh', 'display_name': 'FSH (Follicle Stimulating Hormone)', 'category': 'Endocrinology',
                'description': 'Follicle stimulating hormone; the reference range depends on sex and cycle phase',
                'aliases': ['follicle stimulating hormone'],
                'default_unit': 'miu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'estradiol', 'display_name': 'Estradiol (E2)', 'category': 'Endocrinology',
                'description': 'Estradiol; the reference range depends on sex and cycle phase', 'aliases': ['oestradiol', 'e2'],
                'default_unit': 'pg_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'progesterone', 'display_name': 'Progesterone', 'category': 'Endocrinology',
                'description': 'Progesterone; the reference range depends on sex and cycle phase', 'aliases': [],
                'default_unit': 'ng_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'dhea_s', 'display_name': 'DHEA-S (DHEA Sulfate)', 'category': 'Endocrinology',
                'description': 'Adrenal androgen; the reference range depends on age and sex',
                'aliases': ['dheas', 'dhea sulfate', 'dhea sulphate', 'dehydroepiandrosterone sulfate', 'dehydroepiandrosterone sulphate'],
                'default_unit': 'ug_dl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'shbg', 'display_name': 'SHBG (Sex Hormone Binding Globulin)', 'category': 'Endocrinology',
                'description': 'Sex hormone binding globulin; the reference range depends on sex', 'aliases': ['sex hormone binding globulin'],
                'default_unit': 'nmol_l', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'testosterone_free', 'display_name': 'Free Testosterone', 'category': 'Endocrinology',
                'description': 'Testosterone not bound to proteins; the reference range depends on sex', 'aliases': [],
                'default_unit': 'pg_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'anti_tpo', 'display_name': 'Anti-TPO (Thyroid Peroxidase Antibodies)', 'category': 'Immunology',
                'description': 'Thyroid autoantibodies; the cut-off depends on the assay',
                'aliases': ['anti tpo', 'tpo antibody', 'thyroid peroxidase antibody', 'anti thyroid peroxidase', 'antithyroid peroxidase'],
                'default_unit': 'iu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'anti_tg', 'display_name': 'Anti-Thyroglobulin Antibodies', 'category': 'Immunology',
                'description': 'Thyroid autoantibodies; the cut-off depends on the assay',
                'aliases': ['anti tg', 'antithyroglobulin', 'anti thyroglobulin', 'thyroglobulin antibody'],
                'default_unit': 'iu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'psa_total', 'display_name': 'PSA (Prostate Specific Antigen), Total', 'category': 'Immunology',
                'description': 'Prostate specific antigen', 'aliases': ['psa', 'prostate specific antigen', 'total psa'],
                'default_unit': 'ng_ml', 'normal_min': Decimal('0'), 'normal_max': Decimal('4.0')
            },
            {
                'name': 'psa_free', 'display_name': 'Free PSA', 'category': 'Immunology',
                'description': 'Prostate specific antigen not bound to proteins', 'aliases': ['free prostate specific antigen'],
                'default_unit': 'ng_ml', 'normal_min': None, 'normal_max': None
            },

            # Inflammation, infection, and heart
            {
                'name': 'rheumatoid_factor', 'display_name': 'Rheumatoid Factor (RF)', 'category': 'Immunology',
                'description': 'Autoantibody seen in rheumatoid arthritis; the cut-off depends on the assay',
                'aliases': ['ra factor', 'rf quantitative'],
                'default_unit': 'iu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'aso', 'display_name': 'ASO (Antistreptolysin O)', 'category': 'Immunology',
                'description': 'Antibody to streptococcal infection; the cut-off depends on age',
                'aliases': ['antistreptolysin o', 'anti streptolysin o', 'aso titre', 'aso titer'],
                'default_unit': 'iu_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'procalcitonin', 'display_name': 'Procalcitonin', 'category': 'Immunology',
                # Not "PCT": a blood count prints plateletcrit as PCT.
                'description': 'Marker of bacterial infection', 'aliases': [],
                'default_unit': 'ng_ml', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'nt_probnp', 'display_name': 'NT-proBNP', 'category': 'Chemistry',
                'description': 'Heart failure marker; the cut-off depends on age',
                'aliases': ['nt pro bnp', 'ntprobnp', 'n terminal pro bnp', 'n terminal pro b type natriuretic peptide'],
                'default_unit': 'pg_ml', 'normal_min': None, 'normal_max': None
            },

            # Blood count indices the catalog lacked. RDW-SD is in fL and RDW-CV in %, so they are separate tests.
            {
                'name': 'rdw_sd', 'display_name': 'RDW-SD (Red Cell Distribution Width SD)', 'category': 'Hematology',
                'description': 'Variation in red cell size (standard deviation)',
                'aliases': ['rdw sd', 'red cell distribution width sd'],
                'default_unit': 'fl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'pdw', 'display_name': 'PDW (Platelet Distribution Width)', 'category': 'Hematology',
                'description': 'Variation in platelet size', 'aliases': ['platelet distribution width'],
                'default_unit': 'fl', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'plateletcrit', 'display_name': 'Plateletcrit', 'category': 'Hematology',
                # Not "PCT", which also means procalcitonin.
                'description': 'Share of blood volume taken up by platelets', 'aliases': [],
                'default_unit': 'percent', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'p_lcr', 'display_name': 'P-LCR (Platelet Large Cell Ratio)', 'category': 'Hematology',
                'description': 'Share of platelets that are large', 'aliases': ['platelet large cell ratio'],
                'default_unit': 'percent', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'reticulocyte_count', 'display_name': 'Reticulocyte Count', 'category': 'Hematology',
                'description': 'Young red blood cells, as a share of all red cells',
                'aliases': ['reticulocytes', 'retic count', 'reticulocyte'],
                'default_unit': 'percent', 'normal_min': None, 'normal_max': None
            },

            # Prothrombin time. Like aPTT, the patient's time, the lab's control, and the INR are separate tests.
            {
                'name': 'pt', 'display_name': 'PT (Prothrombin Time)', 'category': 'Coagulation',
                'description': "The patient's prothrombin time; the range depends on the lab's reagent",
                'aliases': ['prothrombin time', 'pt test', 'pt patient'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'pt_control', 'display_name': 'PT Control', 'category': 'Coagulation',
                'description': "The laboratory's control prothrombin time, not the patient's result",
                'aliases': ['pt control', 'prothrombin time control'],
                'default_unit': 'seconds', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'inr', 'display_name': 'INR (International Normalized Ratio)', 'category': 'Coagulation',
                # No range: the target on warfarin (2-3 or higher) differs from the range without it (about 0.8-1.2).
                'description': 'Prothrombin time standardised across labs',
                'aliases': ['international normalized ratio', 'international normalised ratio', 'pt inr'],
                'default_unit': 'ratio', 'normal_min': None, 'normal_max': None
            },
            {
                'name': 'fibrinogen', 'display_name': 'Fibrinogen', 'category': 'Coagulation',
                'description': 'Clotting protein', 'aliases': [],
                'default_unit': 'mg_dl', 'normal_min': Decimal('200'), 'normal_max': Decimal('400')
            },
        ]
        
        for test_data in test_types_data:
            if test_data['name'] in self.protected:
                self.stdout.write(f'Edited in the app, left alone: {test_data["name"]}')
                continue
            test_type, created = LabTestType.objects.update_or_create(
                name=test_data['name'],
                defaults={key: value for key, value in test_data.items() if key != 'name'}
            )
            if created:
                self.stdout.write(f'Created test type: {test_type.display_name}')
            else:
                self.stdout.write(f'Test type already exists: {test_type.display_name}')

    def create_unit_conversions(self):
        """Create unit conversions"""
        # Each factor is for one analyte: a mass-to-molar factor depends on the molecule's weight.
        conversions_data = [
            # Vitamin D conversions
            {'test_types': ['vitamin_d'], 'from_unit': 'ng_ml', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('2.496'), 'reverse_factor': Decimal('0.4006'), 'formula': 'ng/mL × 2.496 = nmol/L'},
            {'test_types': ['vitamin_d'], 'from_unit': 'nmol_l', 'to_unit': 'ng_ml', 'conversion_factor': Decimal('0.4006'), 'reverse_factor': Decimal('2.496'), 'formula': 'nmol/L × 0.4006 = ng/mL'},

            # Glucose conversions (eAG is a glucose value too)
            {'test_types': ['glucose', 'glucose_fasting', 'glucose_random', 'glucose_pp', 'eag'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.0555'), 'reverse_factor': Decimal('18.018'), 'formula': 'mg/dL × 0.0555 = mmol/L'},
            {'test_types': ['glucose', 'glucose_fasting', 'glucose_random', 'glucose_pp', 'eag'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('18.018'), 'reverse_factor': Decimal('0.0555'), 'formula': 'mmol/L × 18.018 = mg/dL'},

            # Cholesterol conversions
            {'test_types': ['total_cholesterol', 'hdl_cholesterol', 'ldl_cholesterol', 'vldl_cholesterol', 'non_hdl_cholesterol'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.02586'), 'reverse_factor': Decimal('38.67'), 'formula': 'mg/dL × 0.02586 = mmol/L'},
            {'test_types': ['total_cholesterol', 'hdl_cholesterol', 'ldl_cholesterol', 'vldl_cholesterol', 'non_hdl_cholesterol'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('38.67'), 'reverse_factor': Decimal('0.02586'), 'formula': 'mmol/L × 38.67 = mg/dL'},

            # Triglycerides conversions
            {'test_types': ['triglycerides'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.01129'), 'reverse_factor': Decimal('88.54'), 'formula': 'mg/dL × 0.01129 = mmol/L'},
            {'test_types': ['triglycerides'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('88.54'), 'reverse_factor': Decimal('0.01129'), 'formula': 'mmol/L × 88.54 = mg/dL'},

            # Creatinine conversions
            {'test_types': ['creatinine', 'urine_creatinine'], 'from_unit': 'mg_dl', 'to_unit': 'umol_l', 'conversion_factor': Decimal('88.4'), 'reverse_factor': Decimal('0.01131'), 'formula': 'mg/dL × 88.4 = μmol/L'},
            {'test_types': ['creatinine', 'urine_creatinine'], 'from_unit': 'umol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('0.01131'), 'reverse_factor': Decimal('88.4'), 'formula': 'μmol/L × 0.01131 = mg/dL'},
            # Urine creatinine is often reported in mmol/L
            {'test_types': ['urine_creatinine'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.0884'), 'reverse_factor': Decimal('11.31'), 'formula': 'mg/dL × 0.0884 = mmol/L'},
            {'test_types': ['urine_creatinine'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('11.31'), 'reverse_factor': Decimal('0.0884'), 'formula': 'mmol/L × 11.31 = mg/dL'},

            # Urea and BUN, both as mmol/L of urea
            {'test_types': ['urea'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.1665'), 'reverse_factor': Decimal('6.006'), 'formula': 'mg/dL × 0.1665 = mmol/L'},
            {'test_types': ['urea'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('6.006'), 'reverse_factor': Decimal('0.1665'), 'formula': 'mmol/L × 6.006 = mg/dL'},
            {'test_types': ['bun'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.357'), 'reverse_factor': Decimal('2.801'), 'formula': 'mg/dL × 0.357 = mmol/L'},
            {'test_types': ['bun'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('2.801'), 'reverse_factor': Decimal('0.357'), 'formula': 'mmol/L × 2.801 = mg/dL'},

            # Uric acid conversions
            {'test_types': ['uric_acid'], 'from_unit': 'mg_dl', 'to_unit': 'umol_l', 'conversion_factor': Decimal('59.48'), 'reverse_factor': Decimal('0.01681'), 'formula': 'mg/dL × 59.48 = μmol/L'},
            {'test_types': ['uric_acid'], 'from_unit': 'umol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('0.01681'), 'reverse_factor': Decimal('59.48'), 'formula': 'μmol/L × 0.01681 = mg/dL'},

            # Bilirubin conversions
            {'test_types': ['total_bilirubin', 'direct_bilirubin', 'indirect_bilirubin'], 'from_unit': 'mg_dl', 'to_unit': 'umol_l', 'conversion_factor': Decimal('17.104'), 'reverse_factor': Decimal('0.05847'), 'formula': 'mg/dL × 17.104 = μmol/L'},
            {'test_types': ['total_bilirubin', 'direct_bilirubin', 'indirect_bilirubin'], 'from_unit': 'umol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('0.05847'), 'reverse_factor': Decimal('17.104'), 'formula': 'μmol/L × 0.05847 = mg/dL'},

            # Calcium conversions
            {'test_types': ['calcium'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.2495'), 'reverse_factor': Decimal('4.008'), 'formula': 'mg/dL × 0.2495 = mmol/L'},
            {'test_types': ['calcium'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('4.008'), 'reverse_factor': Decimal('0.2495'), 'formula': 'mmol/L × 4.008 = mg/dL'},

            # Iron conversions (TIBC and UIBC are amounts of iron too)
            {'test_types': ['iron', 'tibc', 'uibc'], 'from_unit': 'ug_dl', 'to_unit': 'umol_l', 'conversion_factor': Decimal('0.1791'), 'reverse_factor': Decimal('5.585'), 'formula': 'μg/dL × 0.1791 = μmol/L'},
            {'test_types': ['iron', 'tibc', 'uibc'], 'from_unit': 'umol_l', 'to_unit': 'ug_dl', 'conversion_factor': Decimal('5.585'), 'reverse_factor': Decimal('0.1791'), 'formula': 'μmol/L × 5.585 = μg/dL'},

            # Ferritin: ng/mL and μg/L are the same number
            {'test_types': ['ferritin'], 'from_unit': 'ng_ml', 'to_unit': 'ug_l', 'conversion_factor': Decimal('1'), 'reverse_factor': Decimal('1'), 'formula': 'ng/mL × 1 = μg/L'},
            {'test_types': ['ferritin'], 'from_unit': 'ug_l', 'to_unit': 'ng_ml', 'conversion_factor': Decimal('1'), 'reverse_factor': Decimal('1'), 'formula': 'μg/L × 1 = ng/mL'},

            # Magnesium conversions
            {'test_types': ['magnesium'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.4114'), 'reverse_factor': Decimal('2.431'), 'formula': 'mg/dL × 0.4114 = mmol/L'},
            {'test_types': ['magnesium'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('2.431'), 'reverse_factor': Decimal('0.4114'), 'formula': 'mmol/L × 2.431 = mg/dL'},

            # Phosphate conversions
            {'test_types': ['phosphorus'], 'from_unit': 'mg_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.3229'), 'reverse_factor': Decimal('3.097'), 'formula': 'mg/dL × 0.3229 = mmol/L'},
            {'test_types': ['phosphorus'], 'from_unit': 'mmol_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('3.097'), 'reverse_factor': Decimal('0.3229'), 'formula': 'mmol/L × 3.097 = mg/dL'},

            # Vitamin B12 conversions
            {'test_types': ['vitamin_b12'], 'from_unit': 'pg_ml', 'to_unit': 'pmol_l', 'conversion_factor': Decimal('0.7378'), 'reverse_factor': Decimal('1.355'), 'formula': 'pg/mL × 0.7378 = pmol/L'},
            {'test_types': ['vitamin_b12'], 'from_unit': 'pmol_l', 'to_unit': 'pg_ml', 'conversion_factor': Decimal('1.355'), 'reverse_factor': Decimal('0.7378'), 'formula': 'pmol/L × 1.355 = pg/mL'},

            # Folate conversions
            {'test_types': ['folate'], 'from_unit': 'ng_ml', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('2.266'), 'reverse_factor': Decimal('0.441'), 'formula': 'ng/mL × 2.266 = nmol/L'},
            {'test_types': ['folate'], 'from_unit': 'nmol_l', 'to_unit': 'ng_ml', 'conversion_factor': Decimal('0.441'), 'reverse_factor': Decimal('2.266'), 'formula': 'nmol/L × 0.441 = ng/mL'},

            # Testosterone conversions
            {'test_types': ['testosterone_total'], 'from_unit': 'ng_dl', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('0.03467'), 'reverse_factor': Decimal('28.84'), 'formula': 'ng/dL × 0.03467 = nmol/L'},
            {'test_types': ['testosterone_total'], 'from_unit': 'nmol_l', 'to_unit': 'ng_dl', 'conversion_factor': Decimal('28.84'), 'reverse_factor': Decimal('0.03467'), 'formula': 'nmol/L × 28.84 = ng/dL'},

            # Cortisol conversions
            {'test_types': ['cortisol'], 'from_unit': 'ug_dl', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('27.59'), 'reverse_factor': Decimal('0.03625'), 'formula': 'μg/dL × 27.59 = nmol/L'},
            {'test_types': ['cortisol'], 'from_unit': 'nmol_l', 'to_unit': 'ug_dl', 'conversion_factor': Decimal('0.03625'), 'reverse_factor': Decimal('27.59'), 'formula': 'nmol/L × 0.03625 = μg/dL'},

            # C-peptide conversions
            {'test_types': ['c_peptide'], 'from_unit': 'ng_ml', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('0.331'), 'reverse_factor': Decimal('3.02'), 'formula': 'ng/mL × 0.331 = nmol/L'},
            {'test_types': ['c_peptide'], 'from_unit': 'nmol_l', 'to_unit': 'ng_ml', 'conversion_factor': Decimal('3.02'), 'reverse_factor': Decimal('0.331'), 'formula': 'nmol/L × 3.02 = ng/mL'},

            # PTH conversions
            {'test_types': ['pth_intact'], 'from_unit': 'pg_ml', 'to_unit': 'pmol_l', 'conversion_factor': Decimal('0.106'), 'reverse_factor': Decimal('9.43'), 'formula': 'pg/mL × 0.106 = pmol/L'},
            {'test_types': ['pth_intact'], 'from_unit': 'pmol_l', 'to_unit': 'pg_ml', 'conversion_factor': Decimal('9.43'), 'reverse_factor': Decimal('0.106'), 'formula': 'pmol/L × 9.43 = pg/mL'},

            # HbA1c % and mmol/mol are not proportional (mmol/mol = 10.93 × % − 23.5), so they cannot be
            # converted by a factor and are left unconverted.

            # Thyroid hormone conversions, total and free
            {'test_types': ['t4'], 'from_unit': 'ug_dl', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('12.87'), 'reverse_factor': Decimal('0.0777'), 'formula': 'μg/dL × 12.87 = nmol/L'},
            {'test_types': ['t4'], 'from_unit': 'nmol_l', 'to_unit': 'ug_dl', 'conversion_factor': Decimal('0.0777'), 'reverse_factor': Decimal('12.87'), 'formula': 'nmol/L × 0.0777 = μg/dL'},
            {'test_types': ['t3'], 'from_unit': 'ng_dl', 'to_unit': 'nmol_l', 'conversion_factor': Decimal('0.01536'), 'reverse_factor': Decimal('65.1'), 'formula': 'ng/dL × 0.01536 = nmol/L'},
            {'test_types': ['t3'], 'from_unit': 'nmol_l', 'to_unit': 'ng_dl', 'conversion_factor': Decimal('65.1'), 'reverse_factor': Decimal('0.01536'), 'formula': 'nmol/L × 65.1 = ng/dL'},
            {'test_types': ['free_t4'], 'from_unit': 'ng_dl', 'to_unit': 'pmol_l', 'conversion_factor': Decimal('12.87'), 'reverse_factor': Decimal('0.0777'), 'formula': 'ng/dL × 12.87 = pmol/L'},
            {'test_types': ['free_t4'], 'from_unit': 'pmol_l', 'to_unit': 'ng_dl', 'conversion_factor': Decimal('0.0777'), 'reverse_factor': Decimal('12.87'), 'formula': 'pmol/L × 0.0777 = ng/dL'},
            {'test_types': ['free_t3'], 'from_unit': 'pg_ml', 'to_unit': 'pmol_l', 'conversion_factor': Decimal('1.536'), 'reverse_factor': Decimal('0.651'), 'formula': 'pg/mL × 1.536 = pmol/L'},
            {'test_types': ['free_t3'], 'from_unit': 'pmol_l', 'to_unit': 'pg_ml', 'conversion_factor': Decimal('0.651'), 'reverse_factor': Decimal('1.536'), 'formula': 'pmol/L × 0.651 = pg/mL'},

            # Hemoglobin conversions
            {'test_types': ['hemoglobin'], 'from_unit': 'g_dl', 'to_unit': 'mmol_l', 'conversion_factor': Decimal('0.6206'), 'reverse_factor': Decimal('1.611'), 'formula': 'g/dL × 0.6206 = mmol/L'},
            {'test_types': ['hemoglobin'], 'from_unit': 'mmol_l', 'to_unit': 'g_dl', 'conversion_factor': Decimal('1.611'), 'reverse_factor': Decimal('0.6206'), 'formula': 'mmol/L × 1.611 = g/dL'},
            {'test_types': ['hemoglobin', 'mchc'], 'from_unit': 'g_dl', 'to_unit': 'g_l', 'conversion_factor': Decimal('10'), 'reverse_factor': Decimal('0.1'), 'formula': 'g/dL × 10 = g/L'},
            {'test_types': ['hemoglobin', 'mchc'], 'from_unit': 'g_l', 'to_unit': 'g_dl', 'conversion_factor': Decimal('0.1'), 'reverse_factor': Decimal('10'), 'formula': 'g/L × 0.1 = g/dL'},

            # CRP conversions
            {'test_types': ['crp', 'hs_crp'], 'from_unit': 'mg_dl', 'to_unit': 'mg_l', 'conversion_factor': Decimal('10'), 'reverse_factor': Decimal('0.1'), 'formula': 'mg/dL × 10 = mg/L'},
            {'test_types': ['crp', 'hs_crp'], 'from_unit': 'mg_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('0.1'), 'reverse_factor': Decimal('10'), 'formula': 'mg/L × 0.1 = mg/dL'},

            # Protein conversions
            {'test_types': ['total_protein', 'albumin', 'globulin'], 'from_unit': 'g_dl', 'to_unit': 'g_l', 'conversion_factor': Decimal('10'), 'reverse_factor': Decimal('0.1'), 'formula': 'g/dL × 10 = g/L'},
            {'test_types': ['total_protein', 'albumin', 'globulin'], 'from_unit': 'g_l', 'to_unit': 'g_dl', 'conversion_factor': Decimal('0.1'), 'reverse_factor': Decimal('10'), 'formula': 'g/L × 0.1 = g/dL'},
            {'test_types': ['apo_a1', 'apo_b', 'iga', 'igg', 'igm', 'complement_c3', 'complement_c4', 'transferrin', 'fibrinogen'], 'from_unit': 'mg_dl', 'to_unit': 'g_l', 'conversion_factor': Decimal('0.01'), 'reverse_factor': Decimal('100'), 'formula': 'mg/dL × 0.01 = g/L'},
            {'test_types': ['apo_a1', 'apo_b', 'iga', 'igg', 'igm', 'complement_c3', 'complement_c4', 'transferrin', 'fibrinogen'], 'from_unit': 'g_l', 'to_unit': 'mg_dl', 'conversion_factor': Decimal('100'), 'reverse_factor': Decimal('0.01'), 'formula': 'g/L × 100 = mg/dL'},

            # Urine albumin to creatinine ratio, US (mg/g) and UK (mg/mmol)
            {'test_types': ['uacr'], 'from_unit': 'mg_g', 'to_unit': 'mg_mmol', 'conversion_factor': Decimal('0.1131'), 'reverse_factor': Decimal('8.84'), 'formula': 'mg/g × 0.1131 = mg/mmol'},
            {'test_types': ['uacr'], 'from_unit': 'mg_mmol', 'to_unit': 'mg_g', 'conversion_factor': Decimal('8.84'), 'reverse_factor': Decimal('0.1131'), 'formula': 'mg/mmol × 8.84 = mg/g'},

            # Cell counts. Thousands per mm³ are thousands per μL, as are K/μL and 10³/μL.
            {'test_types': ['wbc', 'platelet_count'], 'from_unit': 'cells_ul', 'to_unit': 'thou_mm3', 'conversion_factor': Decimal('0.001'), 'reverse_factor': Decimal('1000'), 'formula': 'cells/μL × 0.001 = thou/mm3'},
            {'test_types': ['wbc', 'platelet_count'], 'from_unit': 'thou_mm3', 'to_unit': 'cells_ul', 'conversion_factor': Decimal('1000'), 'reverse_factor': Decimal('0.001'), 'formula': 'thou/mm3 × 1000 = cells/μL'},
            {'test_types': ['wbc', 'platelet_count'], 'from_unit': 'cells_ul', 'to_unit': 'k_cells_ul', 'conversion_factor': Decimal('0.001'), 'reverse_factor': Decimal('1000'), 'formula': 'cells/μL × 0.001 = K/μL'},
            {'test_types': ['wbc', 'platelet_count'], 'from_unit': 'k_cells_ul', 'to_unit': 'cells_ul', 'conversion_factor': Decimal('1000'), 'reverse_factor': Decimal('0.001'), 'formula': 'K/μL × 1000 = cells/μL'},
            {'test_types': ['platelet_count'], 'from_unit': 'cells_ul', 'to_unit': 'lakh_mm3', 'conversion_factor': Decimal('0.00001'), 'reverse_factor': Decimal('100000'), 'formula': 'cells/μL × 0.00001 = lakh/mm3'},
            {'test_types': ['platelet_count'], 'from_unit': 'lakh_mm3', 'to_unit': 'cells_ul', 'conversion_factor': Decimal('100000'), 'reverse_factor': Decimal('0.00001'), 'formula': 'lakh/mm3 × 100000 = cells/μL'},
            {'test_types': ['alc_neutrophils', 'alc_lymphocytes', 'alc_monocytes', 'alc_eosinophils', 'alc_basophils'], 'from_unit': 'thou_mm3', 'to_unit': 'cells_ul', 'conversion_factor': Decimal('1000'), 'reverse_factor': Decimal('0.001'), 'formula': 'thou/mm3 × 1000 = cells/μL'},
            {'test_types': ['alc_neutrophils', 'alc_lymphocytes', 'alc_monocytes', 'alc_eosinophils', 'alc_basophils'], 'from_unit': 'cells_ul', 'to_unit': 'thou_mm3', 'conversion_factor': Decimal('0.001'), 'reverse_factor': Decimal('1000'), 'formula': 'cells/μL × 0.001 = thou/mm3'},
        ]

        for conv_data in conversions_data:
            test_type_names = conv_data.get('test_types', [])
            # Rows without an analyte are intentionally ignored. Molecular-weight
            # conversions are unsafe when attached only to a generic unit pair.
            if not test_type_names:
                continue
            try:
                from_unit = LabTestUnit.objects.get(name=conv_data['from_unit'])
                to_unit = LabTestUnit.objects.get(name=conv_data['to_unit'])

                conversion_data = {
                    k: v for k, v in conv_data.items()
                    if k not in ['test_types', 'from_unit', 'to_unit', 'notes']
                }
                conversion_data['notes'] = f'Conversion from {from_unit.display_name} to {to_unit.display_name}'

                for test_type_name in test_type_names:
                    if test_type_name in self.protected:
                        continue
                    test_type = LabTestType.objects.get(name=test_type_name)
                    conversion, created = UnitConversion.objects.update_or_create(
                        test_type=test_type,
                        from_unit=from_unit,
                        to_unit=to_unit,
                        defaults=conversion_data,
                    )
                    self._ensure_supported_conversion_unit(
                        test_type, from_unit, to_unit, conversion.conversion_factor
                    )
                    action = 'Created' if created else 'Updated'
                    self.stdout.write(
                        f'{action} conversion: {test_type.name} '
                        f'{from_unit.name} → {to_unit.name}'
                    )
            except (LabTestType.DoesNotExist, LabTestUnit.DoesNotExist) as e:
                self.stdout.write(f'Catalog entry not found for conversion: {e}')

    def _ensure_supported_conversion_unit(self, test_type, from_unit, to_unit, factor):
        """Add the alternate unit with a range derived from the default range."""
        if test_type.default_unit == from_unit.name:
            alternate_unit = to_unit
            range_factor = factor
        elif test_type.default_unit == to_unit.name:
            alternate_unit = from_unit
            reverse = UnitConversion.objects.get(
                test_type=test_type, from_unit=from_unit, to_unit=to_unit
            ).reverse_factor
            range_factor = reverse
        else:
            return

        normal_min = (
            test_type.normal_min * range_factor
            if test_type.normal_min is not None else None
        )
        normal_max = (
            test_type.normal_max * range_factor
            if test_type.normal_max is not None else None
        )
        LabTestTypeUnit.objects.update_or_create(
            test_type=test_type,
            unit=alternate_unit,
            defaults={
                'normal_min': normal_min,
                'normal_max': normal_max,
                'conversion_factor': range_factor,
                'is_active': True,
            },
        )

    def create_test_type_units(self):
        """Give each catalog test its default unit, with the test's own reference range.

        Any other unit a test had is switched off here; create_unit_conversions switches the alternate units
        its conversions support back on, so a unit the catalog stopped using does not keep a stale range.
        """
        for test_type in LabTestType.objects.filter(source=LabTestType.SOURCE_CATALOG).exclude(name__in=self.protected):
            unit = LabTestUnit.objects.filter(name=test_type.default_unit).first()
            if unit is None:
                self.stdout.write(f'Unit not found for {test_type.name}: {test_type.default_unit}')
                continue
            _, created = LabTestTypeUnit.objects.update_or_create(
                test_type=test_type,
                unit=unit,
                defaults={
                    'normal_min': test_type.normal_min,
                    'normal_max': test_type.normal_max,
                    'conversion_factor': Decimal('1'),
                    'is_active': True,
                },
            )
            LabTestTypeUnit.objects.filter(test_type=test_type).exclude(unit=unit).update(is_active=False)
            action = 'Created' if created else 'Updated'
            self.stdout.write(f'{action} test type unit: {test_type.display_name} - {unit.display_name}')

    # Adult critical (panic) limits in each test's default unit, as low and high; None where there is no
    # commonly used limit on that side. They follow the limits most US laboratories use (Kost 1990; CAP
    # surveys). A laboratory sets its own, so these only mark a value as critical when a report does not.
    # Tests not listed have no critical limits: a limit taken as a multiple of the normal range would call
    # a TSH of 9 critical and a potassium of 9 merely high.
    CRITICAL_LIMITS = {
        'glucose': (Decimal('40'), Decimal('500')),
        'glucose_fasting': (Decimal('40'), Decimal('500')),
        'glucose_random': (Decimal('40'), Decimal('500')),
        'glucose_pp': (Decimal('40'), Decimal('500')),
        'sodium': (Decimal('120'), Decimal('160')),
        'potassium': (Decimal('2.8'), Decimal('6.2')),
        'chloride': (Decimal('80'), Decimal('120')),
        'co2': (Decimal('10'), Decimal('40')),
        'calcium': (Decimal('6.0'), Decimal('13.0')),
        'magnesium': (Decimal('1.0'), Decimal('4.7')),
        'phosphorus': (Decimal('1.0'), Decimal('8.9')),
        'hemoglobin': (Decimal('7.0'), Decimal('20.0')),
        'hematocrit': (Decimal('20'), Decimal('60')),
        'wbc': (Decimal('2000'), Decimal('30000')),
        'platelet_count': (Decimal('20000'), None),
        'alc_neutrophils': (Decimal('0.5'), None),
        'inr': (None, Decimal('5.0')),
        'fibrinogen': (Decimal('100'), None),
    }

    def create_validation_rules(self):
        """A validation rule for each unit a test is used in, with its range and critical limits in that unit."""
        for ttu in LabTestTypeUnit.objects.filter(is_active=True).select_related('test_type', 'unit'):
            if ttu.test_type.name in self.protected:
                continue
            low, high = self.CRITICAL_LIMITS.get(ttu.test_type.name, (None, None))
            # An alternate unit's conversion_factor turns a default-unit value into one in that unit.
            factor = ttu.conversion_factor if ttu.unit.name != ttu.test_type.default_unit else Decimal('1')
            validation_rule, created = LabTestValidationRule.objects.update_or_create(
                test_type=ttu.test_type,
                unit=ttu.unit,
                defaults={
                    'normal_min': ttu.normal_min,
                    'normal_max': ttu.normal_max,
                    'critical_low_min': low * factor if low is not None else None,
                    'critical_high_max': high * factor if high is not None else None,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(f'Created validation rule: {ttu.test_type.display_name} - {ttu.unit.display_name}')
            else:
                self.stdout.write(f'Validation rule already exists: {ttu.test_type.display_name} - {ttu.unit.display_name}')

        # A unit the catalog no longer uses for a test must not keep validating its values.
        for rule in LabTestValidationRule.objects.filter(
            is_active=True, test_type__source=LabTestType.SOURCE_CATALOG,
        ).exclude(test_type__name__in=self.protected).select_related('test_type', 'unit'):
            if not LabTestTypeUnit.objects.filter(test_type=rule.test_type, unit=rule.unit, is_active=True).exists():
                rule.is_active = False
                rule.save(update_fields=['is_active'])

    def create_parsing_patterns(self):
        """Create regex patterns for PDF parsing"""
        patterns_data = [
            # Vitamin D patterns
            {
                'test_type': 'vitamin_d',
                'pattern_name': 'vitamin_d_basic',
                'regex_pattern': r'(?i)(vitamin\s+d|25-?oh\s+vitamin\s+d|25-?oh\s+vit\s+d)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'vitamin_d',
                'pattern_name': 'vitamin_d_ng_ml',
                'regex_pattern': r'(?i)(vit\s+d|25-?oh)\s*:?\s*(\d+\.?\d*)\s*(ng/ml|ng/mL)',
                'value_group': 2,
                'unit_group': 3,
                'priority': 2
            },
            {
                'test_type': 'vitamin_d',
                'pattern_name': 'vitamin_d_nmol_l',
                'regex_pattern': r'(?i)(vit\s+d|25-?oh)\s*:?\s*(\d+\.?\d*)\s*(nmol/l|nmol/L)',
                'value_group': 2,
                'unit_group': 3,
                'priority': 2
            },

            # Glucose patterns
            {
                'test_type': 'glucose',
                'pattern_name': 'glucose_basic',
                # Only a line that starts with the name: "Fasting Blood Sugar 95" belongs to fasting glucose.
                'regex_pattern': r'(?i)^[^a-z]*(?:blood\s+|plasma\s+)?(glucose|sugar)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'glucose_fasting',
                'pattern_name': 'glucose_fasting',
                'regex_pattern': r'(?i)(fasting\s+blood\s+sugar|fasting\s+(?:blood\s+|plasma\s+)?glucose|fbs)\s*:?\s*(\d+\.?\d*)\s*(mg/dl|mmol/l)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 3
            },
            {
                'test_type': 'glucose_random',
                'pattern_name': 'glucose_random',
                'regex_pattern': r'(?i)(random\s+blood\s+sugar|random\s+(?:blood\s+|plasma\s+)?glucose|rbs)\s*:?\s*(\d+\.?\d*)\s*(mg/dl|mmol/l)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 3
            },
            {
                'test_type': 'glucose_pp',
                'pattern_name': 'glucose_pp',
                'regex_pattern': r'(?i)(post\s*prandial\s+(?:blood\s+sugar|(?:plasma\s+)?glucose)|pp\s*bs|pp\s+glucose)\s*:?\s*(\d+\.?\d*)\s*(mg/dl|mmol/l)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 3
            },

            # Cholesterol patterns
            {
                'test_type': 'total_cholesterol',
                'pattern_name': 'cholesterol_basic',
                'regex_pattern': r'(?i)(total\s+cholesterol|cholesterol|total\s+chol)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'hdl_cholesterol',
                'pattern_name': 'hdl_basic',
                'regex_pattern': r'(?i)(hdl\s+cholesterol|hdl|high\s+density\s+lipoprotein)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 2
            },
            {
                'test_type': 'ldl_cholesterol',
                'pattern_name': 'ldl_basic',
                'regex_pattern': r'(?i)(ldl\s+cholesterol|ldl|low\s+density\s+lipoprotein)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 2
            },
            {
                'test_type': 'triglycerides',
                'pattern_name': 'triglycerides_basic',
                'regex_pattern': r'(?i)(triglycerides|trig|tg)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Liver function patterns
            {
                'test_type': 'alt',
                'pattern_name': 'alt_basic',
                'regex_pattern': r'(?i)(alt|alanine\s+aminotransferase|sgpt)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'ast',
                'pattern_name': 'ast_basic',
                'regex_pattern': r'(?i)(ast|aspartate\s+aminotransferase|sgot)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'alkaline_phosphatase',
                'pattern_name': 'alp_basic',
                'regex_pattern': r'(?i)(alkaline\s+phosphatase|alp|alk\s+phos)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'total_bilirubin',
                'pattern_name': 'bilirubin_total',
                'regex_pattern': r'(?i)(total\s+bilirubin|bilirubin|total\s+bili)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'direct_bilirubin',
                'pattern_name': 'bilirubin_direct',
                'regex_pattern': r'(?i)(direct\s+bilirubin|conjugated\s+bilirubin|direct\s+bili)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Kidney function patterns
            {
                'test_type': 'creatinine',
                'pattern_name': 'creatinine_basic',
                'regex_pattern': r'(?i)(creatinine|serum\s+creatinine|creat)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'urine_creatinine',
                'pattern_name': 'urine_creatinine_basic',
                'regex_pattern': r'(?i)(urine\s+creatinine|creatinine\s+urine)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 2
            },
            {
                'test_type': 'urea',
                'pattern_name': 'urea_basic',
                'regex_pattern': r'(?i)\b(blood\s+urea|serum\s+urea|urea)\b(?!\s+nitrogen)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'bun',
                'pattern_name': 'bun_basic',
                'regex_pattern': r'(?i)\b(blood\s+urea\s+nitrogen|urea\s+nitrogen|bun)\b\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'egfr',
                'pattern_name': 'egfr_basic',
                'regex_pattern': r'(?i)(egfr|estimated\s+gfr|gfr)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Electrolyte patterns
            {
                'test_type': 'sodium',
                'pattern_name': 'sodium_basic',
                'regex_pattern': r'(?i)(sodium|na)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'potassium',
                'pattern_name': 'potassium_basic',
                'regex_pattern': r'(?i)(potassium|k)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'chloride',
                'pattern_name': 'chloride_basic',
                'regex_pattern': r'(?i)(chloride|cl)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Complete blood count patterns
            {
                'test_type': 'hemoglobin',
                'pattern_name': 'hemoglobin_basic',
                'regex_pattern': r'(?i)(hemoglobin|hb|hgb)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'hematocrit',
                'pattern_name': 'hematocrit_basic',
                'regex_pattern': r'(?i)(hematocrit|hct)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'wbc',
                'pattern_name': 'wbc_basic',
                'regex_pattern': r'(?i)(wbc|white\s+blood\s+cell|white\s+blood\s+cell\s+count|leukocyte)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'rbc',
                'pattern_name': 'rbc_basic',
                'regex_pattern': r'(?i)(rbc|red\s+blood\s+cell|red\s+blood\s+cell\s+count|erythrocyte)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'platelet_count',
                'pattern_name': 'platelet_basic',
                'regex_pattern': r'(?i)(platelet|plt|platelet\s+count)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # DLC patterns (percentages) – disambiguated by section context
            {
                'test_type': 'dlc_neutrophils',
                'pattern_name': 'neutrophils_dlc',
                'regex_pattern': r'(?i)(segmented\s+neutrophils|neutrophils)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'dlc_lymphocytes',
                'pattern_name': 'lymphocytes_dlc',
                'regex_pattern': r'(?i)(lymphocytes)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'dlc_monocytes',
                'pattern_name': 'monocytes_dlc',
                'regex_pattern': r'(?i)(monocytes)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'dlc_eosinophils',
                'pattern_name': 'eosinophils_dlc',
                'regex_pattern': r'(?i)(eosinophils)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'dlc_basophils',
                'pattern_name': 'basophils_dlc',
                'regex_pattern': r'(?i)(basophils)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # ALC patterns (absolute counts) – disambiguated by section context
            {
                'test_type': 'alc_neutrophils',
                'pattern_name': 'neutrophils_alc',
                'regex_pattern': r'(?i)(segmented\s+neutrophils|neutrophils)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'alc_lymphocytes',
                'pattern_name': 'lymphocytes_alc',
                'regex_pattern': r'(?i)(lymphocytes)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'alc_monocytes',
                'pattern_name': 'monocytes_alc',
                'regex_pattern': r'(?i)(monocytes)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'alc_eosinophils',
                'pattern_name': 'eosinophils_alc',
                'regex_pattern': r'(?i)(eosinophils)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'alc_basophils',
                'pattern_name': 'basophils_alc',
                'regex_pattern': r'(?i)(basophils)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'protein_creatinine_ratio',
                'pattern_name': 'pcr_basic',
                'regex_pattern': r'(?i)(protein\s+creatinine\s+ratio|prot\s+creat\s+ratio|pcr)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 2
            },

            # Thyroid patterns
            {
                'test_type': 'tsh',
                'pattern_name': 'tsh_basic',
                'regex_pattern': r'(?i)(tsh|thyroid\s+stimulating\s+hormone)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 't3',
                'pattern_name': 't3_basic',
                'regex_pattern': r'(?i)(t3|triiodothyronine)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 't4',
                'pattern_name': 't4_basic',
                'regex_pattern': r'(?i)(t4|thyroxine)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Protein patterns
            {
                'test_type': 'total_protein',
                'pattern_name': 'protein_basic',
                'regex_pattern': r'(?i)(total\s+protein|protein)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'albumin',
                'pattern_name': 'albumin_basic',
                'regex_pattern': r'(?i)(albumin|alb)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Diabetes markers
            {
                'test_type': 'hba1c',
                'pattern_name': 'hba1c_basic',
                'regex_pattern': r'(?i)(hba1c|hemoglobin\s+a1c|glycated\s+hemoglobin|a1c)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },

            # Vitamins and minerals
            {
                'test_type': 'vitamin_b12',
                'pattern_name': 'b12_basic',
                'regex_pattern': r'(?i)(vitamin\s+b12|b12|cobalamin)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'iron',
                'pattern_name': 'iron_basic',
                'regex_pattern': r'(?i)(iron|serum\s+iron)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'ferritin',
                'pattern_name': 'ferritin_basic',
                'regex_pattern': r'(?i)(ferritin)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
            {
                'test_type': 'folate',
                'pattern_name': 'folate_basic',
                'regex_pattern': r'(?i)(folate|folic\s+acid)\s*:?\s*(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
                'value_group': 2,
                'unit_group': 3,
                'priority': 1
            },
        ]
        
        # "bun_basic" used to belong to urea when urea meant BUN; BUN now has its own test and pattern.
        LabTestPattern.objects.filter(test_type__name='urea', pattern_name='bun_basic').delete()
        # Likewise "glucose_fasting" belonged to glucose before fasting glucose became its own test.
        LabTestPattern.objects.filter(test_type__name='glucose', pattern_name='glucose_fasting').delete()

        for pattern_data in patterns_data:
            if pattern_data['test_type'] in self.protected:
                continue
            try:
                test_type = LabTestType.objects.get(name=pattern_data['test_type'])
                
                # Remove the test_type from pattern_data since we're passing the instance
                pattern_data_clean = {k: v for k, v in pattern_data.items() if k != 'test_type'}
                
                pattern, created = LabTestPattern.objects.update_or_create(
                    test_type=test_type,
                    pattern_name=pattern_data['pattern_name'],
                    defaults=pattern_data_clean
                )
                if created:
                    self.stdout.write(f'Created pattern: {test_type.display_name} - {pattern.pattern_name}')
                else:
                    self.stdout.write(f'Pattern already exists: {test_type.display_name} - {pattern.pattern_name}')
            except LabTestType.DoesNotExist:
                self.stdout.write(f'Test type not found for pattern: {pattern_data["test_type"]}')
