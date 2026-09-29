# Report formats

DiagnoseIt's generic parser reads most tabular lab reports. When a laboratory's layout defeats it,
add a **report format**: a small Python class that recognises that layout and reads its results.
Every `*.py` file in this folder is loaded automatically; files starting with `_` are skipped.

## Writing one

Start from [`example_lab.py`](example_lab.py):

```python
from utils.report_formats import ReportFormat, ReportRow, register

@register
class AcmeLabs(ReportFormat):
    name = "acme-labs"              # unique id

    def matches(self, text):        # text = the PDF's extracted text
        return "ACME LABORATORIES" in text

    def parse(self, text):
        return [ReportRow(test_name="Hemoglobin", value="13.5", unit="g/dL", reference_range="13.0-17.0")]
```

- **`ReportRow`** takes the name, value, unit, and reference range as printed. Rows are linked to the
  lab test catalog, converted, and charted like any other result. `status` is optional and is worked
  out from the reference range when it's blank. `section` (`urine`, `dlc`, `alc`) keeps, for example,
  urine creatinine apart from serum creatinine.
- **`mode`**: `REPLACE` (the default) uses this format's rows instead of the generic parser's.
  `SUPPLEMENT` adds them to the generic parser's result, which suits a format that only reads one
  section the generic parser misses.
- **`priority`**: when several formats match one report, higher priority runs first. The first
  `REPLACE` format that returns rows wins, and every matching `SUPPLEMENT` format adds its rows.
- A format that raises an exception is logged and skipped, so it can't break parsing.

Formats read the PDF's text layer. Scanned reports go through OCR instead, which formats don't affect.

## Installing formats

- **In this repository:** drop the file here. With Docker, rebuild or restart the app containers.
- **Without rebuilding the image:** put your formats in a folder on the host and mount it; see
  `REPORT_FORMATS_DIR` in [`.env.example`](../.env.example) and the commented volume in `docker-compose.yml`.
- **As a Python package:** list its modules in `REPORT_FORMATS`, for example
  `REPORT_FORMATS=acme_formats.cbc,acme_formats.lipids`.

## Testing

Add a test with synthetic report text; see `utils/tests_report_formats.py`. Never commit or attach a real
patient's report, even redacted.
