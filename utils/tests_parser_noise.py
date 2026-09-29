"""Lines that print a person's name are not parsed as lab results."""

from django.test import SimpleTestCase

from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser
from utils.vlm_pdf_parser import _should_skip_ocr_line


class PersonNameLineTests(SimpleTestCase):
    def test_lines_with_a_persons_title_are_skipped(self):
        for line in ("L58 - MR.JOHN DOE (", "Patient: Mrs. Anita Rao 45 Y", "MS.PRIYA 12.5"):
            with self.subTest(line=line):
                self.assertTrue(EnhancedMedicalPDFParser._should_skip_line(line))
                self.assertTrue(_should_skip_ocr_line(line))

    def test_result_lines_are_kept(self):
        for line in ("Hemoglobin 13.5 g/dL 13.0 - 17.0", "MCV 88.2 fL 80 - 100", "Mean Platelet Volume 9.1 fL"):
            with self.subTest(line=line):
                self.assertFalse(EnhancedMedicalPDFParser._should_skip_line(line))
