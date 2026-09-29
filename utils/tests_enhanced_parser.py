"""Unit tests for enhanced PDF tabular/qualitative parsing."""

from django.test import SimpleTestCase, TestCase

from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser
from utils.lab_units import (
    CATEGORICAL_LINE_RE,
    DESCRIPTIVE_LINE_RE,
    QUALITATIVE_LINE_RE,
    SIMPLE_NUMERIC_LINE_RE,
    SIMPLE_TEXT_PAIR_LINE_RE,
    TABULAR_LINE_RE,
)


class TabularLineRegexTests(SimpleTestCase):
    def test_parses_standard_numeric_row(self):
        m = TABULAR_LINE_RE.match("Hemoglobin 15.00 g/dL 13.00 - 17.00")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("name"), "Hemoglobin")
        self.assertEqual(m.group("value"), "15.00")
        self.assertEqual(m.group("unit"), "g/dL")

    def test_parses_comparator_value_with_unit(self):
        m = TABULAR_LINE_RE.match("Basophils 1.00 % <2.00")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "1.00")

    def test_parses_leading_less_than_value(self):
        m = TABULAR_LINE_RE.match("CRP <10 mg/L <10")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "<10")
        self.assertEqual(m.group("unit"), "mg/L")

    def test_parses_expanded_units(self):
        for line in (
            "IgE Total 120 kUA/L 0 - 100",
            "TSH 2.1 mIU/mL 0.4 - 4.0",
            "Anti-HCV Index 0.2 Index Negative",
            "PLATELET COUNT 169000 cells/cu.mm 150000-410000",
            "RBC COUNT 5.57 Million/cu.mm 4.5-5.5",
        ):
            m = TABULAR_LINE_RE.match(line)
            self.assertIsNotNone(m, msg=line)

    def test_parses_thousands_separator_value(self):
        m = TABULAR_LINE_RE.match(
            "TOTAL LEUCOCYTE COUNT (TLC) 11,050 cells/cu.mm 4000-10000"
        )
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "11,050")
        self.assertEqual(m.group("unit"), "cells/cu.mm")

    def test_parses_unit_after_reference_range(self):
        from utils.lab_units import match_value_range_unit

        row = match_value_range_unit(
            "HEMOGLOBIN (HB) 11.5 11.1 - 14.1 g/dL"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "11.5")
        self.assertEqual(row["unit"], "g/dL")
        self.assertIn("11.1", row["ref"])

        flagged = match_value_range_unit(
            "Hemoglobin (Hb) 13.00 Normal 13.00 - 17.00 g/dL"
        )
        self.assertIsNotNone(flagged)
        self.assertEqual(flagged["value"], "13.00")
        self.assertEqual(flagged["unit"], "g/dL")

    def test_parses_ug_per_dl_unit(self):
        m = TABULAR_LINE_RE.match("Cortisol, Basal 22.00 ug/dL 4.30 - 22.40")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("unit"), "ug/dL")

    def test_parses_multiline_stimulation_when_joined(self):
        line = "Cortisol Post ACTH stimulation 30 minutes 2222.00 ug/dL Peak"
        m = TABULAR_LINE_RE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "2222.00")

    def test_rejects_noise_without_unit(self):
        self.assertIsNone(TABULAR_LINE_RE.match("Note: sample hemolyzed"))


class QualitativeLineRegexTests(SimpleTestCase):
    def test_parses_negative_result(self):
        m = QUALITATIVE_LINE_RE.match("HIV I & II Negative Negative")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "Negative")

    def test_parses_not_detected(self):
        m = QUALITATIVE_LINE_RE.match("Occult Blood Not Detected Absent")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "Not Detected")


    def test_parses_blood_group(self):
        m = CATEGORICAL_LINE_RE.match("ABO Group A")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "A")

    def test_parses_stool_colour(self):
        m = DESCRIPTIVE_LINE_RE.match("Colour Dark Brown Brown")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "Dark Brown")


class SimpleLineRegexTests(SimpleTestCase):
    def test_right_anchored_avoids_minutes_false_value(self):
        from utils.lab_units import match_right_anchored_tabular

        row = match_right_anchored_tabular(
            "DHEA, Post stimulation by ACTH after 90 minutes 1.00 g/mL"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "1.00")
        self.assertEqual(row["unit"], "g/mL")

    def test_unitless_numeric_index(self):
        from utils.lab_units import UNITLESS_NUMERIC_LINE_RE

        m = UNITLESS_NUMERIC_LINE_RE.match("Immunoglobulin Synthesis Index 0.50 0.30 - 0.70")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "0.50")

    def test_simple_numeric_ph(self):
        m = SIMPLE_NUMERIC_LINE_RE.match("pH 11.0")
        self.assertIsNotNone(m)

    def test_simple_text_sample_type(self):
        m = SIMPLE_TEXT_PAIR_LINE_RE.match("Type of Sample Urine")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("value"), "Urine")

    def test_does_not_join_method_fragment_onto_next_analyte(self):
        from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser

        lines = [
            "HAEMOGLOBIN 12.9 g/dL 13-17 CYANIDE FREE",
            "COLOUROMETER",
            "PCV 38.20 % 40-50 PULSE HEIGHT AVERAGE",
        ]
        joined = EnhancedMedicalPDFParser._maybe_join_continuation_line(
            lines, 1, "COLOUROMETER"
        )
        self.assertEqual(joined, "COLOUROMETER")

    def test_still_joins_name_with_following_timed_value_line(self):
        from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser

        lines = [
            "Cortisol Post ACTH stimulation",
            "30 minutes 2222.00 ug/dL Peak concentration > 20",
        ]
        joined = EnhancedMedicalPDFParser._maybe_join_continuation_line(
            lines, 0, "Cortisol Post ACTH stimulation"
        )
        self.assertIn("2222.00", joined)
        self.assertIn("ug/dL", joined)

    def test_does_not_join_simple_row_onto_following_qualitative(self):
        from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser

        lines = [
            "Type of Sample Urine",
            "Mycobacterium tuberculosis Complex DNA Not Detected",
        ]
        joined = EnhancedMedicalPDFParser._maybe_join_continuation_line(
            lines, 0, "Type of Sample Urine"
        )
        self.assertEqual(joined, "Type of Sample Urine")

        lines2 = [
            "pH 11.0",
            "Reducing Substances Positive",
        ]
        joined2 = EnhancedMedicalPDFParser._maybe_join_continuation_line(
            lines2, 0, "pH 11.0"
        )
        self.assertEqual(joined2, "pH 11.0")

    def test_name_embeds_lab_unit_detects_column_bleed(self):
        from utils.lab_units import name_embeds_lab_unit

        self.assertTrue(name_embeds_lab_unit("Immunoglobulin IgE, Serum kUA/L"))
        self.assertFalse(name_embeds_lab_unit("pH"))


class EnhancedParserTextPipelineTests(TestCase):
    def setUp(self):
        self.parser = EnhancedMedicalPDFParser()

    def test_blood_panel_heading_ends_a_urine_section(self):
        text = "\n".join([
            "URINE ROUTINE EXAMINATION",
            "Protein Nil",
            "COMPLETE BLOOD COUNT; CBC, EDTA WHOLE BLOOD",
            "Hemoglobin 14.5 g/dL 13.0 - 17.0",
            "DIFFERENTIAL LEUCOCYTE COUNT (DLC)",
            "Neutrophils 60 % 40 - 80",
        ])

        self.assertEqual(self.parser.section_contexts(text), ["urine", "urine", None, None, "dlc", "dlc"])
        hemoglobin = next(row for row in self.parser.extract_test_results(text) if "Hemoglobin" in str(row.get("raw_test_name")))
        self.assertEqual(hemoglobin["section_context"], "")

    def test_extracts_comparator_and_qualitative_rows(self):
        text = """
Differential Leucocyte Count (DLC)
Basophils 1.00 % <2.00
Absolute Leucocyte Count
Basophils 0.02 thou/mm3 0.02 - 0.10
HIV I & II Negative Negative
CRP <10 mg/L <10
"""
        results = self.parser.extract_test_results(text)
        values = {r["value"] for r in results}
        self.assertIn("1.00", values)
        self.assertIn("0.02", values)
        self.assertIn("Negative", values)
        self.assertIn("<10", values)

    def test_rejects_prose_false_positive(self):
        text = (
            "allergens that react with specific IgE antibodies in the patient serum. All "
            "positive\n"
            "those cases in which skin tests are equivocal\n"
        )
        results = self.parser.extract_test_results(text)
        self.assertEqual(results, [])

    def test_dlc_and_alc_basophils_both_kept(self):
        text = """
Differential Leucocyte Count (DLC)
Basophils 1.00 % <2.00
Absolute Leucocyte Count
Basophils 0.02 thou/mm3 0.02 - 0.10
"""
        results = self.parser.extract_test_results(text)
        baso = [r for r in results if "basophil" in r["test_name"].lower()]
        self.assertEqual(len(baso), 2)
        self.assertEqual({r["value"] for r in baso}, {"1.00", "0.02"})

    def test_multiline_timed_cortisol(self):
        text = """
Cortisol Post ACTH stimulation
30 minutes 2222.00 ug/dL Peak concentration > 20
"""
        results = self.parser.extract_test_results(text)
        vals = {r["value"] for r in results}
        self.assertIn("2222.00", vals)

    def test_extracts_indian_count_units_and_comma_values(self):
        text = """
COMPLETE BLOOD COUNT (CBC) , WHOLE BLOOD EDTA
HAEMOGLOBIN 12.9 g/dL 13-17 CYANIDE FREE
COLOUROMETER
PCV 38.20 % 40-50 PULSE HEIGHT AVERAGE
RBC COUNT 5.57 Million/cu.mm 4.5-5.5 Electrical Impedence
TOTAL LEUCOCYTE COUNT (TLC) 11,050 cells/cu.mm 4000-10000 Electrical Impedance
DIFFERENTIAL LEUCOCYTIC COUNT (DLC)
NEUTROPHILS 83 % 40-80 Electrical Impedance
ABSOLUTE LEUCOCYTE COUNT
NEUTROPHILS 9171.5 Cells/cu.mm 2000-7000 Calculated
PLATELET COUNT 169000 cells/cu.mm 150000-410000 IMPEDENCE/MICROSCOPY
"""
        results = self.parser.extract_test_results(text)
        self.assertIn("12.9", {r["value"] for r in results})
        self.assertIn("38.20", {r["value"] for r in results})
        platelet = next(r for r in results if "PLATELET" in r["test_name"].upper())
        self.assertEqual(platelet["value"], "169000")
        tlc = next(r for r in results if "TLC" in r["test_name"].upper() or "LEUCOCYTE COUNT" in r["test_name"].upper())
        self.assertEqual(tlc["value"].replace(",", ""), "11050")
        # Method wrap must not steal PCV.
        pcv_names = [r["test_name"] for r in results if "PCV" in r["test_name"].upper()]
        self.assertTrue(pcv_names)
        self.assertFalse(any("COLOUROMETER" in n.upper() for n in pcv_names))
        # DLC % and ALC absolute neutrophils both kept.
        neut = [r for r in results if "NEUTROPHIL" in r["test_name"].upper()]
        self.assertGreaterEqual(len(neut), 2)

    def test_rejects_interim_column_bleed_and_clinical_prose(self):
        text = """
ALLERGY SCREEN, SERUM
Phadiatop,IgE kUA/L <0.35
Immunoglobulin IgE, Serum kUA/L <64.00
Asthma, Angioedema or Cutaneous disease
"""
        results = self.parser.extract_test_results(text)
        self.assertEqual(results, [])

    def test_rejects_emr_header_text_pairs(self):
        text = """
Visit ID : ABC101 Status : Final Report
Ref Doctor : Dr.SELF Client Name : CITY DIAGNOSTICS LAB
DEPARTMENT OF HAEMATOLOGY
COMPLETE BLOOD COUNT (CBC) , WHOLE BLOOD EDTA
Patient Name : Jane Doe
Age / Gender : 40 Y / F
UHID/MR No : MR0001
SIN No:SAMP001
"""
        results = self.parser.extract_test_results(text)
        self.assertEqual(results, [])


class CatalogStatusFallbackTests(TestCase):
    """A row with no printed range is read against the catalog's rule for the unit it was printed in."""

    @classmethod
    def setUpTestData(cls):
        from io import StringIO

        from django.core.management import call_command

        call_command("populate_lab_tests", stdout=StringIO())

    def test_the_rule_for_the_printed_unit_is_used(self):
        from lab_tests.models import LabTestType

        parser = EnhancedMedicalPDFParser()
        calcium = LabTestType.objects.get(name="calcium")

        self.assertEqual(parser._status_from_db("9.5", "mg/dL", calcium), "NORMAL")
        self.assertEqual(parser._status_from_db("2.3", "mmol/L", calcium), "NORMAL")
        self.assertEqual(parser._status_from_db("1.9", "mmol/l", calcium), "LOW")
        # An unknown spelling falls back to the test's default unit.
        self.assertEqual(parser._status_from_db("9.5", "mg%", calcium), "NORMAL")
