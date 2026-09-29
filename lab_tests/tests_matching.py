"""Printed lab test names resolve to the right catalog test, and different analytes stay apart."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .matching import TestNameMatcher
from .models import LabTestType
from .services import tidy_test_name
from .services import build_test_type_matcher


class CatalogMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('populate_lab_tests', stdout=StringIO())

    def setUp(self):
        self.matcher = build_test_type_matcher()

    def assertMatches(self, cases, context=None):
        for printed, expected in cases:
            with self.subTest(printed=printed, context=context):
                test_type = self.matcher.match(printed, context=context)
                self.assertEqual(test_type.name if test_type else None, expected)

    def test_every_catalog_name_display_name_and_alias_resolves_to_its_own_test(self):
        for test_type in LabTestType.objects.filter(is_active=True):
            self.assertMatches([(text, test_type.name) for text in (test_type.name, test_type.display_name, *test_type.aliases)])

    def test_printed_variants_resolve_to_one_catalog_test(self):
        self.assertMatches([
            ('ALT (SGPT), SERUM', 'alt'),
            ('ALT (SGPT)', 'alt'),
            ('AST (SGOT)', 'ast'),
            ('C-REACTIVE PROTEIN; CRP, SERUM', 'crp'),
            ('C-REACTIVE PROTEIN (CRP)', 'crp'),
            ('C-Reactive Protein', 'crp'),
            ('CALCIUM, SERUM', 'calcium'),
            ('Calcium, Total', 'calcium'),
            ('ERYTHROCYTE SEDIMENTATION RATE (ESR)', 'esr'),
            ('Alkaline Phosphatase (ALP)', 'alkaline_phosphatase'),
            ('MEAN CORPUSCULAR VOLUME (MCV), WHOLE BLOOD (Electrical Impedance)', 'mcv'),
            ('MCHC (Mean Corpuscular Hb Concn.)', 'mchc'),
            ('MPV (Mean Platelet Volume)', 'mpv'),
            ('Mean Platelet Volume', 'mpv'),
            ('Red Cell Distribution Width- CV (RDW-CV)', 'rdw'),
            ('Packed Cell Volume (PCV)', 'hematocrit'),
            ('Total Leukocyte Count (TLC)', 'wbc'),
            ('RBC Count', 'rbc'),
            ('Platelet Count', 'platelet_count'),
            ('TRI-IODOTHYRONINE (T3, TOTAL)', 't3'),
            ('T4, Total', 't4'),
            ('THYROXINE (T4, TOTAL)', 't4'),
            ('GGTP', 'ggt'),
            ('Globulin(Calculated)', 'globulin'),
            ('Bilirubin Direct', 'direct_bilirubin'),
            ('Bilirubin Indirect', 'indirect_bilirubin'),
            ('Bilirubin Total', 'total_bilirubin'),
            ('Urea', 'urea'),
            ('Urea Nitrogen Blood', 'bun'),
            ('BUN', 'bun'),
            ('Vitamin B12; Cyanocobalamin', 'vitamin_b12'),
            ('Vitamin D, 25 Hydroxy', 'vitamin_d'),
            ('Estimated average glucose (eAG)', 'eag'),
            ('Non-HDL Cholesterol', 'non_hdl_cholesterol'),
            ('GLUCOSE, FASTING (F), PLASMA (Hexokinase)', 'glucose_fasting'),
            ('Glucose Fasting', 'glucose_fasting'),
            ('FBS (Fasting Blood Sugar)', 'glucose_fasting'),
            ('Blood Sugar Random (RBS)', 'glucose_random'),
            ('GLUCOSE, POST PRANDIAL (PP), 2 HOURS, PLASMA', 'glucose_pp'),
            ('Glucose (PP)', 'glucose_pp'),
            ('Post Prandial Blood Sugar', 'glucose_pp'),
            ('Plasma Glucose', 'glucose'),
            ('E.S.R.', 'esr'),
            ('A/G Ratio', 'ag_ratio'),
            ('Albumin/Globulin Ratio', 'ag_ratio'),
            ('BUN/Creatinine Ratio', 'bun_creatinine_ratio'),
            ('Apolipoprotein (Apo A1)', 'apo_a1'),
            ('Apolipoprotein (Apo B)', 'apo_b'),
            ('Apolipoprotein B / Apo A1 Ratio', 'apo_b_a1_ratio'),
            ('Cystatin C', 'cystatin_c'),
            ('eGFR (Cystatin C)', 'egfr_cystatin_c'),
            ('eGFRcystatin C', 'egfr_cystatin_c'),
            ('eGFR', 'egfr'),
            ('Testosterone, Total', 'testosterone_total'),
            ('Total Iron Binding Capacity (TIBC)', 'tibc'),
            ('Transferrin Saturation', 'transferrin_saturation'),
            ('Mentzer Index', 'mentzer_index'),
            ('Amylase', 'amylase'),
            ('Dengue Fever Antibody, IgG', 'dengue_igg'),
            ('DENGUE FEVER ANTIBODY,IGM', 'dengue_igm'),
            ('DENGUE FEVER ANTIGEN, NS1, EIA, SERUM *', 'dengue_ns1'),
            ('IgA -', 'iga'),
            ('Immunoglobulin IgG, Serum -', 'igg'),
            ('Immunoglobulin IgM, Serum -', 'igm'),
            ('TOTAL IgE -', 'ige_total'),
            ('ACE (Angiotensin Converting Enzyme)', 'ace'),
            ('C3', 'complement_c3'),
            ('C4', 'complement_c4'),
            ('Parathyroid Hormone (Intact PTH)', 'pth_intact'),
            ('GFR Estimated', 'egfr'),
            ('LDL Cholesterol, Calculated', 'ldl_cholesterol'),
            ('TSH, Ultrasensitive', 'tsh'),
            ('TSH - SANDWICH CHEMI LUMINESCENT IMMUNO', 'tsh'),
            ('Hemoglobin \u2014 Photometry', 'hemoglobin'),
            ('.eGFR - ESTIMATED GLOMERULAR', 'egfr'),
        ])

    def test_different_analytes_stay_apart(self):
        self.assertMatches([
            ('CARDIO C-REACTIVE PROTEIN (hsCRP), SERUM', 'hs_crp'),
            ('hsCRP', 'hs_crp'),
            ('Free T3', 'free_t3'),
            ('FT4', 'free_t4'),
            ('Cholesterol/HDL Ratio', 'cholesterol_hdl_ratio'),
            ('Urine Glucose', None),
            ('Glucose Fasting and Random', None),
            ('Ionized Calcium', None),
            ('GFR Category', None),
            ('Herpes simplex virus 1+2, IgG', None),
            ('Hepatitis B Core Antibody (Anti-HBc), IgM', None),
            ('Neutrophils', None),
            ('C-Reactive Active protein', None),
            ('L58 - MR.JOHN DOE (', None),
        ])

    def test_report_section_picks_the_variant_only_when_it_fits(self):
        self.assertMatches(
            [('Neutrophils', 'dlc_neutrophils'), ('Segmented Neutrophils', 'dlc_neutrophils'), ('Platelet Count', 'platelet_count')],
            context='dlc',
        )
        self.assertMatches([('Basophils', 'alc_basophils')], context='alc')
        self.assertMatches(
            [
                ('Creatinine', 'urine_creatinine'), ('Protein', 'urine_protein'), ('Glucose', None),
                ('Pus cells (WBCs)', 'urine_pus_cells'), ('pH', 'urine_ph'), ('Specific Gravity', 'urine_specific_gravity'),
                ('Epithelial Cells', 'urine_epithelial_cells'),
            ],
            context='urine',
        )

    def test_microscopy_units_keep_urine_cells_out_of_blood_counts(self):
        for printed, unit in (('Red blood cells', '/hpf'), ('RBC', '/hpf')):
            with self.subTest(printed=printed, unit=unit):
                self.assertEqual(self.matcher.match(printed, unit=unit).name, 'urine_rbc')
        self.assertEqual(self.matcher.match('Pus cells (WBCs)', unit='cells/HPF').name, 'urine_pus_cells')
        self.assertEqual(self.matcher.match('Red Blood Cell Count', unit='million/cumm').name, 'rbc')

    def test_results_without_a_number_never_link(self):
        for value in ('Negative', 'Absent', 'Nil', 'Trace', 'Non Reactive', 'Positive (1.2)', 'G1'):
            with self.subTest(value=value):
                self.assertIsNone(self.matcher.match('C-Reactive Protein (CRP)', value=value))
        for value in ('<0.5', '12.4', '1+', '', None):
            with self.subTest(value=value):
                self.assertEqual(self.matcher.match('C-Reactive Protein (CRP)', value=value).name, 'crp')

    def test_user_links_match_in_any_word_order_but_keep_qualifiers_and_sections_apart(self):
        glucose_pp = LabTestType.objects.get(name='glucose_pp')
        matcher = TestNameMatcher(
            LabTestType.objects.filter(is_active=True), user_aliases=[('Sugar Level Post Lunch', glucose_pp)]
        )
        self.assertIsNone(self.matcher.match('Sugar Level Post Lunch'))
        self.assertEqual(matcher.match('POST LUNCH SUGAR').name, 'glucose_pp')
        self.assertIsNone(matcher.match('Urine Sugar Post Lunch'))
        self.assertIsNone(matcher.match('Sugar Level Post Lunch', context='urine'))
        self.assertIsNone(matcher.match('Sugar Level Post Lunch', value='Nil'))
        self.assertEqual(matcher.match('ALT (SGPT)').name, 'alt')

        # A link to a count variant follows the section; a link to any other test applies in blood count sections.
        linked = TestNameMatcher(
            LabTestType.objects.filter(is_active=True),
            user_aliases=[
                ('Mono Count', LabTestType.objects.get(name='alc_monocytes')),
                ('Liver Enzyme X', LabTestType.objects.get(name='alt')),
            ],
        )
        self.assertEqual(linked.match('Mono Count').name, 'alc_monocytes')
        self.assertIsNone(linked.match('Mono Count', unit='%'))
        self.assertEqual(linked.match('Liver Enzyme X', context='dlc').name, 'alt')
        self.assertIsNone(linked.match('Liver Enzyme X', context='urine'))

    def test_units_place_rows_printed_outside_a_known_section(self):
        cases = [
            ('Monocytes', '%', 'dlc_monocytes'),
            ('Segmented Neutrophils', '%', 'dlc_neutrophils'),
            ('Monocytes', 'thou/mm3', 'alc_monocytes'),
            ('Neutrophils', '10^3/\u00b5L', 'alc_neutrophils'),
            ('Hematocrit', '%', 'hematocrit'),
            ('Total Leukocyte Count (TLC)', 'thou/mm3', 'wbc'),
            ('Pus Cells', '/hpf', 'urine_pus_cells'),
            ('Monocytes', '', None),
        ]
        for printed, unit, expected in cases:
            with self.subTest(printed=printed, unit=unit):
                test_type = self.matcher.match(printed, unit=unit)
                self.assertEqual(test_type.name if test_type else None, expected)

    def test_printed_names_lose_the_separators_the_report_put_after_them(self):
        for printed, expected in [
            ('IgA -', 'IgA'),
            ('Epithelial cells.', 'Epithelial cells'),
            ('Reaction. -', 'Reaction'),
            ('T3 :', 'T3'),
            ('Anti-HCV', 'Anti-HCV'),
            ('Vitamin B12', 'Vitamin B12'),
            ('-', '-'),
        ]:
            with self.subTest(printed=printed):
                self.assertEqual(tidy_test_name(printed), expected)

