"""Personal details and boilerplate are kept out of what the AI review sends."""

import io

import pdfplumber
from django.test import SimpleTestCase
from PIL import Image

from utils.report_redaction import REDACTED, Redactor, is_boilerplate, prepare_report_text, redact_page_image
from utils.vlm_pdf_parser import _render_page_to_png


def _pdf(lines):
    """A one-page PDF printing these lines in Helvetica, with a text layer."""
    content = "BT /F1 12 Tf 24 TL 72 720 Td " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return data


class ReportRedactionTests(SimpleTestCase):
    def test_names_and_contact_details_are_redacted_while_age_gender_and_results_stay(self):
        redactor = Redactor(["Anita", "Deshpande"])
        cases = [
            ("Name : DUMMY KUMAR Collected : 29/5/2021 1:37:00AM", f"Name : {REDACTED} Collected : 29/5/2021 1:37:00AM"),
            ("Patient Name : Mrs. SUNITA RAO Age/Sex : 45 Y / F", f"Patient Name : Mrs. {REDACTED} Age/Sex : 45 Y / F"),
            ("MR. RAHUL SHARMA 25 Years Male", f"MR. {REDACTED} 25 Years Male"),
            ("Report of anita deshpande", f"Report of {REDACTED} {REDACTED}"),
            (
                "Contact customer care Tel No. +91-11-39885050 or care@lab.example",
                f"Contact customer care Tel No. {REDACTED} or {REDACTED}",
            ),
            ("Platelet Count 250000 150000 - 450000 cells/cumm", "Platelet Count 250000 150000 - 450000 cells/cumm"),
            ("pH 6.0 5.0 - 8.0", "pH 6.0 5.0 - 8.0"),
            ("Test Name : Hemoglobin", "Test Name : Hemoglobin"),
            ("Hemoglobin 13.5 g/dL 13.0 - 17.0", "Hemoglobin 13.5 g/dL 13.0 - 17.0"),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(redactor.line(line), expected)
        self.assertLessEqual({"dummy", "kumar", "rahul", "sharma", "anita", "911139885050"}, redactor.tokens)

    def test_boilerplate_lines_are_recognised(self):
        for line in (
            "Page 1 of 2",
            "Kindly correlate clinically.",
            "Test results are not valid for medico legal purposes.",
            "---------End of report---------",
            "www.lab.example",
            ".",
        ):
            with self.subTest(line=line):
                self.assertTrue(is_boilerplate(line))
        for line in ("Hemoglobin 13.5 g/dL 13.0 - 17.0", "Interpretation: Non-Diabetic <5.7", "Glucose Fasting 95 mg/dL"):
            with self.subTest(line=line):
                self.assertFalse(is_boilerplate(line))

    def test_repeated_headers_are_sent_once_per_request_and_result_lines_always(self):
        header = "LPL - PRODUCTION TEST COLLECTION CENTRE"
        pages = [
            [header, "Name : DUMMY KUMAR Age : 25 Years", "Hemoglobin 13.5 g/dL 13.0 - 17.0", "Page 1 of 2"],
            [header, "Name : DUMMY KUMAR Age : 25 Years", "Please correlate clinically Glucose 95 mg/dL", "Page 2 of 2"],
        ]
        prepared = prepare_report_text(pages, [], keep={6})

        (whole,) = prepared.select(range(8))
        first, second = prepared.select(range(0, 4), range(4, 8))
        (second_alone,) = prepared.select(range(4, 8))

        self.assertEqual(whole, [
            header,
            f"Name : {REDACTED} Age : 25 Years",
            "Hemoglobin 13.5 g/dL 13.0 - 17.0",
            "Please correlate clinically Glucose 95 mg/dL",
        ])
        self.assertEqual(second, ["Please correlate clinically Glucose 95 mg/dL"])
        self.assertEqual(second_alone, [header, f"Name : {REDACTED} Age : 25 Years", "Please correlate clinically Glucose 95 mg/dL"])

    def test_short_page_headers_barcodes_and_instruction_blocks_are_left_out(self):
        pages = [
            ["CENTRE", "DELHI 110085", "Hemoglobin 13.5 g/dL 13.0 - 17.0", "Absent", "*LAB134*"],
            [
                "CENTRE", "DELHI 110085", "Colour Pale yellow", "Glucose (sugar)", "Absent",
                "AHEEEHAPMCIOAAMGABHMKINKAHPEFLFCNKKOAFPCJGCJOPAHEEEHA",
                "IMPORTANT INSTRUCTIONS", "Sample repeats are accepted within 7 days.", "Urine Protein Absent", "*LAB134*",
            ],
        ]
        prepared = prepare_report_text(pages, [], keep={13})

        (sent,) = prepared.select(range(15))

        # Headers and footers printed at the same place on both pages are sent once; a value line elsewhere stays.
        self.assertEqual(sent, [
            "CENTRE", "DELHI 110085", "Hemoglobin 13.5 g/dL 13.0 - 17.0", "Absent", "*LAB134*",
            "Colour Pale yellow", "Glucose (sugar)", "Absent", "Urine Protein Absent",
        ])

    def test_page_images_black_out_only_the_redacted_words(self):
        lines = ["Name : DUMMY KUMAR Age : 25", "Hemoglobin 13.5 g/dL"]
        pdf = _pdf(lines)
        png = _render_page_to_png(pdf, 0, dpi=72)
        prepared = prepare_report_text([lines], [], keep=set())

        redacted = Image.open(io.BytesIO(redact_page_image(pdf, 0, png, prepared.tokens))).convert("L")
        original = Image.open(io.BytesIO(png)).convert("L")
        with pdfplumber.open(io.BytesIO(pdf)) as document:
            words = {word["text"]: word for word in document.pages[0].extract_words()}

        def region(image, word):
            return image.crop((int(word["x0"]), int(word["top"]), int(word["x1"]), int(word["bottom"])))

        self.assertEqual(region(redacted, words["DUMMY"]).getextrema(), (0, 0))
        self.assertEqual(region(redacted, words["KUMAR"]).getextrema(), (0, 0))
        self.assertEqual(
            list(region(redacted, words["Hemoglobin"]).getdata()), list(region(original, words["Hemoglobin"]).getdata())
        )
        self.assertEqual(redact_page_image(pdf, 0, png, set()), png)
