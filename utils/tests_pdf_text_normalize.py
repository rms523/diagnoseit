"""Tests for PDF PUA font decoding."""

from django.test import SimpleTestCase

from utils.pdf_text_normalize import decode_pua_font_text, normalize_pdf_extracted_text, normalize_pdf_page_lines


class PdfTextNormalizeTests(SimpleTestCase):
    def test_decodes_pua_font_lab_line(self):
        encoded = "\uf049\uf072\uf06f\uf06e \uf035\uf030\uf02e\uf030\uf030 \uf0b5\uf067\uf02f\uf064\uf04c"
        self.assertEqual(decode_pua_font_text(encoded), "Iron 50.00 µg/dL")

    def test_leaves_plain_text_unchanged(self):
        plain = "Hemoglobin 15.00 g/dL 13.00 - 17.00"
        self.assertEqual(normalize_pdf_extracted_text(plain), plain)

    def test_normalizes_encoded_extract(self):
        encoded = "\uf048\uf065\uf06d\uf06f\uf067\uf06c\uf06f\uf062\uf069\uf06e \uf031\uf031\uf02e\uf030\uf030 \uf067\uf02f\uf064\uf04c"
        out = normalize_pdf_extracted_text(encoded)
        self.assertIn("Hemoglobin", out)
        self.assertIn("11.00", out)

    def test_page_lines_rejoin_to_the_normalized_document(self):
        pages = ["Hemoglobin  13.5 g/dL\n\n", "", "  Platelet Count 250\r\nEnd"]

        page_lines = normalize_pdf_page_lines(pages)

        self.assertEqual(page_lines, [["Hemoglobin 13.5 g/dL"], [], ["Platelet Count 250", "End"]])
        self.assertEqual(
            "\n".join(line for page in page_lines for line in page),
            normalize_pdf_extracted_text("\n".join(pages)),
        )

    def test_page_lines_decide_font_decoding_for_the_whole_document(self):
        encoded = "\uf048\uf065\uf06d\uf06f\uf067\uf06c\uf06f\uf062\uf069\uf06e \uf031\uf031\uf02e\uf030\uf030"
        pages = [encoded, "Page 2 \uf031"]

        page_lines = normalize_pdf_page_lines(pages)

        # Page 2 alone is mostly plain text, but the document is font-encoded, so it is decoded too.
        self.assertEqual(page_lines, [["Hemoglobin 11.00"], ["Page 2 1"]])
        self.assertEqual(normalize_pdf_extracted_text(pages[1]), "Page 2 \uf031")
        self.assertEqual("\n".join(sum(page_lines, [])), normalize_pdf_extracted_text("\n".join(pages)))
