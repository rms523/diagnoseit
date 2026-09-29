"""
Example report format for a made-up laboratory, "DiagnoseIt Example Lab".

Copy this file, rename the class, and change ``matches`` and the row pattern to fit your
laboratory's layout. The example layout prints one result per line with dotted leaders:

    Haemoglobin ............ 13.5 g/dL   [13.0 - 17.0]
    Blood Group ............ B Positive
"""
import re

from utils.report_formats import ReportFormat, ReportRow, register

ROW = re.compile(
    r"^(?P<name>[A-Za-z][\w ()/,%-]*?)\s*\.{3,}\s*"   # test name, then dotted leader
    r"(?P<value>\S+(?: [A-Za-z]+)?)"                  # value: "13.5", "<0.5", "B Positive"
    r"(?:\s+(?P<unit>[^\s\[]+))?"                     # optional unit
    r"(?:\s*\[(?P<range>[^\]]*)\])?\s*$"              # optional [reference range]
)


@register
class ExampleLab(ReportFormat):
    name = "example-lab"

    def matches(self, text):
        return "DIAGNOSEIT EXAMPLE LAB" in text.upper()

    def parse(self, text):
        rows = []
        for line in text.splitlines():
            match = ROW.match(line.strip())
            if match:
                rows.append(ReportRow(
                    test_name=match["name"],
                    value=match["value"],
                    unit=match["unit"] or "",
                    reference_range=(match["range"] or "").strip(),
                ))
        return rows
