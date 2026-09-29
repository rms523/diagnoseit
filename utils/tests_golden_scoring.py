"""Unit tests for golden corpus scoring helpers."""

from django.test import SimpleTestCase

from utils.golden_corpus import (
    best_name_match,
    candidate_match_score,
    classify_score,
    norm_unit,
    norm_value,
    section_context_matches_unit,
    unit_family,
    units_match,
    values_match,
)


class GoldenScoringTests(SimpleTestCase):
    def test_values_match_numeric_tolerance(self):
        self.assertTrue(values_match("15.0", "15.00"))
        self.assertTrue(values_match("<10", "<10"))

    def test_values_match_qualitative(self):
        self.assertTrue(values_match("Negative", "negative"))
        self.assertTrue(values_match("Not Detected", "Not Detected"))

    def test_values_match_rejects_clear_mismatch(self):
        self.assertFalse(values_match("3.00", "0.06"))

    def test_norm_value_strips_commas(self):
        self.assertEqual(norm_value("1,234.5"), "1234.5")

    def test_best_name_match_fuzzy(self):
        name, score = best_name_match("hemoglobin", ["Hemoglobin", "WBC"])
        self.assertEqual(name, "Hemoglobin")
        self.assertGreaterEqual(score, 0.55)

    def test_units_match_micro_aliases(self):
        self.assertTrue(units_match("µg/dL", "ug/dL"))
        self.assertTrue(units_match("/hpf", "/HPF"))

    def test_norm_unit_collapses_variants(self):
        self.assertEqual(norm_unit("µg/dL"), "ug/dl")

    def test_unit_family_dlc_alc(self):
        self.assertEqual(unit_family("%"), "percent")
        self.assertEqual(unit_family("thou/mm3"), "absolute")
        self.assertEqual(unit_family("cells/cu.mm"), "absolute")
        self.assertEqual(unit_family("Million/cu.mm"), "absolute")

    def test_section_context_matches_unit(self):
        self.assertTrue(section_context_matches_unit("dlc", "%"))
        self.assertTrue(section_context_matches_unit("alc", "thou/mm3"))
        self.assertFalse(section_context_matches_unit("dlc", "thou/mm3"))

    def test_candidate_prefers_matching_unit_over_wrong_dlc_row(self):
        exp = {"test_name": "Neutrophils", "unit": "thou/mm3", "value": "2.50"}
        alc_row = {"test_name": "neutrophils", "unit": "thou/mm3", "value": "2.50", "section_context": "alc"}
        dlc_row = {"test_name": "neutrophils", "unit": "%", "value": "40.00", "section_context": "dlc"}
        alc_score = candidate_match_score(exp, alc_row, 0.9)
        dlc_score = candidate_match_score(exp, dlc_row, 0.9)
        self.assertGreater(alc_score, dlc_score)

    def test_classify_score_buckets(self):
        self.assertEqual(classify_score(0, 0, 0, 100, 100), "OK_EMPTY")
        self.assertEqual(classify_score(10, 0, 0, 0, 0), "MISS_ALL")
        self.assertEqual(classify_score(10, 8, 8, 80, 75), "OK")
        self.assertEqual(classify_score(10, 5, 5, 50, 80), "PARTIAL")
