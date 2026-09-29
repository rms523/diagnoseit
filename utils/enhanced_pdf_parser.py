"""
Enhanced PDF parser for medical reports with improved accuracy using lab test database
and tabular line detection for common lab report formats.
"""
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
import pdfplumber
import pypdf
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

from lab_tests.matching import TestNameMatcher
from lab_tests.trend_units import normalize_unit
from lab_tests.models import (
    LabTestType, LabTestUnit, LabTestPattern, UnitConversion,
    LabTestValidationRule
)
from utils.lab_units import (
    PERSON_TITLE_RE,
    CATEGORICAL_LINE_RE,
    DESCRIPTIVE_LINE_RE,
    QUALITATIVE_LINE_RE,
    NON_RESULT_TEXT_VALUES,
    SIMPLE_NUMERIC_LINE_RE,
    SIMPLE_TEXT_PAIR_LINE_RE,
    TABULAR_LINE_RE,
    UNITLESS_NUMERIC_LINE_RE,
    is_qualitative_value,
    match_right_anchored_tabular,
    match_value_range_unit,
    name_embeds_lab_unit,
    parse_comparable_number,
)
from utils.pdf_text_normalize import normalize_pdf_extracted_text
from utils.report_formats import ReportRow, apply_report_formats


# ----- Lines to skip (page headers, footers, metadata) -----
SKIP_PATTERNS = [
    re.compile(r'^\s*Page\s+\d+\s+(of|/)\s+\d+', re.IGNORECASE),
    re.compile(r'^\s*Name\s*:', re.IGNORECASE),
    re.compile(r'^\s*Patient\s+Name\b', re.IGNORECASE),
    re.compile(r'^\s*Age\s*(/|:|\s+Gender)\b', re.IGNORECASE),
    re.compile(r'^\s*Gender\s*:', re.IGNORECASE),
    re.compile(r'^\s*(UHID|MR\s+No|Visit\s+ID|IP/OP)\b', re.IGNORECASE),
    re.compile(r'^\s*(Ref\s+Doctor|Ref\s+By|Client\s+Name|Patient\s+location)\b', re.IGNORECASE),
    re.compile(r'^\s*DEPARTMENT\s+OF\b', re.IGNORECASE),
    re.compile(r'^\s*(?:\*+\s*)?End Of Report', re.IGNORECASE),
    # Accession / sample IDs printed as "XXX No:" (SIN, SID, Acc No, Lab No).
    re.compile(r'^\s*(?:SIN|SID|Acc(?:ession)?|Lab|Sample)\s*(?:No\.?|ID|#)\s*:', re.IGNORECASE),
    re.compile(r'^\s*Lab\s+No', re.IGNORECASE),
    re.compile(r'^\s*Collected\s*(at|:)', re.IGNORECASE),
    re.compile(r'^\s*A/c\s+Status', re.IGNORECASE),
    re.compile(r'^\s*(National|Block|ROHINI|DELHI|Sector)\s', re.IGNORECASE),
    re.compile(r'^\s*Test\s+(Report|Name)', re.IGNORECASE),
    re.compile(r'^\s*(Note|Interpretation|Important|Please|If\s+Test)\b', re.IGNORECASE),
    re.compile(r'^\s*\*\w+\*\s*$'),        # barcode markers like *WM17SPF*
    re.compile(r'^\s*\.+\s*$'),             # lone dots
    re.compile(r'^\s*-{5,}'),               # horizontal rules
    re.compile(r'^\s*\|'),                  # table borders
    re.compile(r'^\s*Dr\s+', re.IGNORECASE),  # Doctor names
    PERSON_TITLE_RE,  # Patient names, such as "L58 - MR.JOHN DOE"
    re.compile(r'^\s*MD,', re.IGNORECASE),
    re.compile(r'^\s*Tel:', re.IGNORECASE),
    re.compile(r'^\s*If\s+', re.IGNORECASE),
    re.compile(r'^\s*This\s+is\s+', re.IGNORECASE),
    re.compile(r'^\s*Report\s+Status', re.IGNORECASE),
    re.compile(r'^[A-Z]{10,}$'),            # long barcode-like all-caps rows
    re.compile(r'^[HP]{10,}$'),             # pattern rows
    re.compile(r'^\s*Ÿ'),                   # special chars from PDF footer
    re.compile(r'^\s*·'),                   # bullet point lines
    re.compile(r'^\s*\d+\.\s+', re.IGNORECASE),  # numbered notes ("1. As per...")
    re.compile(r'within\s+\d+\s+(hours|days)', re.IGNORECASE),  # "within 72 hours"
    re.compile(r'^\s*(Differential|Absolute)\s+', re.IGNORECASE),  # section headers
    re.compile(r'^\s*\(', re.IGNORECASE),   # lines starting with parens (method notes)
    re.compile(r'^\s*(Treatment|Guidelines|Guideline)', re.IGNORECASE),
    re.compile(r'^\s*Reported\s*:', re.IGNORECASE),
    re.compile(r'^\s*(Consultant|Technical|Senior|Deputy|Research)\s', re.IGNORECASE),
    re.compile(r'\bHOD\b', re.IGNORECASE),
    re.compile(r'Courts/Forum', re.IGNORECASE),
    re.compile(r'^\s*NRL\s+-', re.IGNORECASE),
]

# Units and line regexes live in utils.lab_units (shared with VLM parser).


class EnhancedMedicalPDFParser:
    """Enhanced parser for medical PDF documents with database-driven pattern matching"""

    # Section headers that switch parsing context
    CONTEXT_HEADERS: Dict[str, List[re.Pattern]] = {
        'urine': [
            re.compile(r'protein\s*[-–]\s*creatinine\s*ratio,\s*urine', re.IGNORECASE),
            re.compile(r'urine\s+routine', re.IGNORECASE),
            re.compile(r'urine\s+analysis', re.IGNORECASE),
            re.compile(r'urine\s+examination', re.IGNORECASE),
            re.compile(r'urinalysis|routine\s+urine', re.IGNORECASE),
            re.compile(r'urine\s+creatinine', re.IGNORECASE),
        ],
        'dlc': [
            re.compile(r'differential\s+leucocyt(?:e|ic)\s+count', re.IGNORECASE),
            re.compile(r'differential\s+leukocyt(?:e|ic)\s+count', re.IGNORECASE),
            re.compile(r'dlc\s*\(differential', re.IGNORECASE),
        ],
        'alc': [
            re.compile(r'absolute\s+leucocyt(?:e|ic)\s+count', re.IGNORECASE),
            re.compile(r'absolute\s+leukocyt(?:e|ic)\s+count', re.IGNORECASE),
            re.compile(r'alc\s*\(absolute', re.IGNORECASE),
        ],
    }

    # A heading for a blood panel ends a urine or blood count section: "LIVER & KIDNEY PANEL, SERUM", "HAEMOGRAM".
    SECTION_END_PATTERN = re.compile(
        r'\b(?:serum|plasma|edta|whole\s+blood|ha?emogram|complete\s+blood\s+count|cbc|lipid\s+profile'
        r'|liver\s+function|kidney\s+function|renal\s+function|thyroid\s+(?:profile|function)|ha?ematology'
        r'|biochemistry|panel|profile)\b',
        re.IGNORECASE,
    )
    _STANDALONE_NUMBER = re.compile(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])')

    # Contextual remapping: when in a given context, a raw test name maps to a different DB test type
    CONTEXT_MAPPINGS: Dict[str, Dict[str, str]] = {
        'urine': {
            'creatinine': 'urine_creatinine',
            'protein total': 'urine_protein',
            'protein': 'urine_protein',
        },
        'dlc': {
            'segmented neutrophils': 'dlc_neutrophils',
            'neutrophils': 'dlc_neutrophils',
            'lymphocytes': 'dlc_lymphocytes',
            'monocytes': 'dlc_monocytes',
            'eosinophils': 'dlc_eosinophils',
            'basophils': 'dlc_basophils',
        },
        'alc': {
            'segmented neutrophils': 'alc_neutrophils',
            'neutrophils': 'alc_neutrophils',
            'lymphocytes': 'alc_lymphocytes',
            'monocytes': 'alc_monocytes',
            'eosinophils': 'alc_eosinophils',
            'basophils': 'alc_basophils',
        },
    }

    def __init__(self):
        self.test_types: Dict[str, Any] = {}
        self.units: Dict[str, Any] = {}
        self.patterns: Dict[str, list] = {}
        self.conversions: Dict[tuple, Any] = {}
        self.validation_rules: Dict[str, Any] = {}
        self.unit_rules: Dict[str, list] = {}
        self.matcher: Optional[TestNameMatcher] = None
        self._load_database_data()

    def _load_database_data(self):
        """Load lab test data from database for improved parsing"""
        # Load test types
        active_types = list(LabTestType.objects.filter(is_active=True))
        for test_type in active_types:
            self.test_types[test_type.name.lower()] = test_type
            self.test_types[test_type.display_name.lower()] = test_type
            for alias in test_type.aliases or []:
                self.test_types[alias.lower()] = test_type
        self.matcher = TestNameMatcher(active_types)

        # Load units
        for unit in LabTestUnit.objects.filter(is_active=True):
            self.units[unit.name] = unit
            self.units[unit.symbol.lower()] = unit

        # Load patterns
        for pattern in LabTestPattern.objects.filter(is_active=True).select_related('test_type'):
            test_name = pattern.test_type.name
            if test_name not in self.patterns:
                self.patterns[test_name] = []
            self.patterns[test_name].append(pattern)

        # Load conversions
        for conversion in UnitConversion.objects.filter(is_active=True).select_related('test_type', 'from_unit', 'to_unit'):
            key = (conversion.test_type.name, conversion.from_unit.name, conversion.to_unit.name)
            self.conversions[key] = conversion

        # Load validation rules: every unit's rule per test, and the test's default-unit rule for disambiguation
        for rule in LabTestValidationRule.objects.filter(is_active=True).select_related('test_type', 'unit'):
            test_name = rule.test_type.name
            self.unit_rules.setdefault(test_name, []).append(rule)
            if test_name not in self.validation_rules or rule.unit.name == rule.test_type.default_unit:
                self.validation_rules[test_name] = rule

    # ------------------------------------------------------------------ #
    # Text extraction
    # ------------------------------------------------------------------ #
    def extract_text_from_pdf(self, pdf_file) -> str:
        """Extract text from PDF file with improved error handling"""
        try:
            with pdfplumber.open(pdf_file) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return normalize_pdf_extracted_text(text)
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}")
            try:
                pdf_reader = pypdf.PdfReader(pdf_file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return normalize_pdf_extracted_text(text)
            except Exception as e2:
                logger.error(f"pypdf also failed: {e2}")
                return ""

    # ------------------------------------------------------------------ #
    # Main extraction pipeline
    # ------------------------------------------------------------------ #
    def extract_test_results(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract test results from text.

        Strategy (in priority order):
        1. **Tabular line parser** – handles the common lab report format
           ``TestName  Value  Unit  RefRange`` in a single regex.
        2. **Database pattern matcher** – uses regex patterns stored in the DB.
        3. Skip the overly-broad basic fallback to avoid garbage.
        """
        results: List[Dict[str, Any]] = []
        seen_keys: set = set()  # for deduplication
        lines = text.split('\n')
        current_context: Optional[str] = None

        for line_num, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line or len(line) < 3:
                continue

            line = self._maybe_join_continuation_line(lines, line_num, line)

            # ---- detect section context (e.g. DLC, ALC, urine) ----
            current_context, is_header = self._advance_context(current_context, line)
            if is_header:
                continue

            # ---- skip noise lines ----
            if self._should_skip_line(line):
                continue

            # ---- 1. Tabular line parser (primary) ----
            tabular = self._parse_tabular_line(line, line_num, current_context)
            if tabular:
                key = (
                    (tabular.get('raw_test_name') or tabular['test_name']).lower(),
                    tabular.get('section_context') or '',
                    tabular['value'],
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(tabular)
                continue

            # ---- 1b. Qualitative result lines (serology, stool, HLA, etc.) ----
            qualitative = self._parse_qualitative_line(line, line_num, current_context)
            if qualitative:
                key = (
                    (qualitative.get('raw_test_name') or qualitative['test_name']).lower(),
                    qualitative.get('section_context') or '',
                    qualitative['value'],
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(qualitative)
                continue

            # ---- 1c. Descriptive physical-exam style rows ----
            descriptive = self._parse_descriptive_line(line, line_num, current_context)
            if descriptive:
                key = (
                    (descriptive.get('raw_test_name') or descriptive['test_name']).lower(),
                    descriptive.get('section_context') or '',
                    descriptive['value'],
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(descriptive)
                continue

            # ---- 1d. Short categorical rows (blood group, etc.) ----
            categorical = self._parse_categorical_line(line, line_num, current_context)
            if categorical:
                key = (
                    (categorical.get('raw_test_name') or categorical['test_name']).lower(),
                    categorical.get('section_context') or '',
                    categorical['value'],
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(categorical)
                continue

            # ---- 1e. Unitless numeric / simple numeric / text-pair rows ----
            simple = None
            for parser_fn in (
                self._parse_unitless_numeric_line,
                self._parse_simple_numeric_line,
                self._parse_simple_text_pair_line,
            ):
                simple = parser_fn(line, line_num, current_context)
                if simple:
                    key = (
                        (simple.get('raw_test_name') or simple['test_name']).lower(),
                        simple.get('section_context') or '',
                        simple['value'],
                    )
                    if key not in seen_keys:
                        seen_keys.add(key)
                        results.append(simple)
                    break
            if simple:
                continue

            # ---- 2. Database-driven pattern matcher ----
            db_match = self._match_test_patterns(line, line_num, current_context)
            if db_match:
                key = (
                    (db_match.get('raw_test_name') or db_match['test_name']).lower(),
                    db_match.get('section_context') or '',
                    db_match['value'],
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(db_match)

            # No basic fallback – avoids garbage matches

        return results

    # ------------------------------------------------------------------ #
    # Context detection
    # ------------------------------------------------------------------ #
    def _detect_context(self, line: str) -> Optional[str]:
        """Detect section headers that change parsing context (DLC, ALC, urine, etc.)."""
        for context, patterns in self.CONTEXT_HEADERS.items():
            for pat in patterns:
                if pat.search(line):
                    return context
        return None

    def _advance_context(self, current: Optional[str], line: str) -> tuple[Optional[str], bool]:
        """The section context after this line, and whether the line is a section header."""
        detected = self._detect_context(line)
        if detected:
            return detected, True
        if current and self._ends_section(line):
            return None, False
        return current, False

    def _ends_section(self, line: str) -> bool:
        """Whether a line is a blood panel heading: panel words, no result value, and a heading's length."""
        return (
            bool(self.SECTION_END_PATTERN.search(line))
            and not self._STANDALONE_NUMBER.search(line)
            and len(line.split()) <= 8
        )

    def section_contexts(self, text: str) -> List[Optional[str]]:
        """The section context this parser gives each line of the text, so stored rows can be matched again."""
        lines = text.split('\n')
        contexts: List[Optional[str]] = []
        current: Optional[str] = None
        for line_num, raw_line in enumerate(lines):
            line = raw_line.strip()
            if line and len(line) >= 3:
                line = self._maybe_join_continuation_line(lines, line_num, line)
                current, _ = self._advance_context(current, line)
            contexts.append(current)
        return contexts

    # ------------------------------------------------------------------ #
    # 1. Tabular line parser
    # ------------------------------------------------------------------ #
    def _parse_tabular_line(self, line: str, line_num: int, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Parse a tabular lab-report line of the form:
            TestName   Value   Unit   RefRange
        or:
            TestName   Value   RefRange   Unit
        """
        anchored = match_value_range_unit(line)
        if anchored:
            raw_name = anchored["name"]
            raw_value = anchored["value"]
            raw_unit = anchored["unit"]
            raw_ref = anchored.get("ref") or ""
        else:
            m = TABULAR_LINE_RE.match(line)
            if not m:
                anchored = match_right_anchored_tabular(line)
                if not anchored:
                    return None
                raw_name = anchored["name"]
                raw_value = anchored["value"]
                raw_unit = anchored["unit"]
                raw_ref = anchored.get("ref") or ""
            else:
                raw_name = m.group('name').strip()
                raw_value = m.group('value').strip()
                raw_unit = m.group('unit').strip()
                raw_ref = m.group('ref').strip() if m.group('ref') else ''

        if not self._looks_like_test_label(raw_name):
            return None

        # Try to identify from the database (with section context)
        identified = self._identify_test_type(raw_name, context=context, unit=raw_unit, value=raw_value)
        if identified:
            identified = self._disambiguate_test_type(identified, raw_value, raw_unit, raw_ref)

        # Determine display name
        if identified:
            display_name = identified.display_name
            test_name = identified.name
        else:
            display_name = raw_name
            test_name = raw_name

        # Determine status from the reference range string
        status = self._status_from_ref_string(raw_value, raw_ref)

        # If status still unknown, try the DB validation rules
        if status == 'UNKNOWN' and identified:
            status = self._status_from_db(raw_value, raw_unit, identified)

        return {
            'test_name': test_name,
            'display_name': display_name,
            'raw_test_name': raw_name,
            'value': raw_value,
            'unit': raw_unit,   # keep the original human-readable unit
            'reference_range': raw_ref if raw_ref else '',
            'status': status,
            'section_context': context or '',
            'raw_line': line,
            'line_number': line_num,
            'confidence': 0.9 if identified else 0.7,
        }

    def _parse_qualitative_line(
        self, line: str, line_num: int, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Parse qualitative rows such as ``HIV  Negative  Negative``."""
        m = QUALITATIVE_LINE_RE.match(line)
        if not m:
            return None

        raw_name = m.group('name').strip()
        raw_value = m.group('value').strip()
        raw_unit = (m.group('unit') or '').strip()
        raw_ref = (m.group('ref') or '').strip()

        if not self._looks_like_test_label(raw_name):
            return None

        identified = self._identify_test_type(raw_name, context=context, unit=raw_unit, value=raw_value)
        if identified:
            display_name = identified.display_name
            test_name = identified.name
        else:
            display_name = raw_name
            test_name = raw_name

        status = 'UNKNOWN'
        ref_lower = raw_ref.lower()
        val_lower = raw_value.lower()
        if ref_lower and val_lower == ref_lower:
            status = 'NORMAL'
        elif val_lower in ('negative', 'not detected', 'absent', 'nil'):
            status = 'NORMAL'
        elif val_lower in ('positive', 'detected', 'present', 'reactive'):
            status = 'HIGH'

        return {
            'test_name': test_name,
            'display_name': display_name,
            'raw_test_name': raw_name,
            'value': raw_value,
            'unit': raw_unit or '',
            'reference_range': raw_ref,
            'status': status,
            'section_context': context or '',
            'raw_line': line,
            'line_number': line_num,
            'confidence': 0.85 if identified else 0.75,
        }

    def _parse_descriptive_line(
        self, line: str, line_num: int, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Parse descriptive rows such as ``Colour  Dark Brown  Brown``."""
        m = DESCRIPTIVE_LINE_RE.match(line)
        if not m:
            return None
        if not self._looks_like_test_label(m.group('name').strip()):
            return None
        return self._build_text_result_row(
            m.group('name').strip(),
            m.group('value').strip(),
            (m.group('unit') or '').strip(),
            (m.group('ref') or '').strip(),
            line,
            line_num,
            context,
        )

    def _parse_categorical_line(
        self, line: str, line_num: int, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Parse unitless categorical rows such as ``ABO Group  A``."""
        m = CATEGORICAL_LINE_RE.match(line)
        if not m:
            return None
        if not self._looks_like_test_label(m.group('name').strip()):
            return None
        return self._build_text_result_row(
            m.group('name').strip(),
            m.group('value').strip(),
            '',
            '',
            line,
            line_num,
            context,
        )

    def _build_text_result_row(
        self,
        raw_name: str,
        raw_value: str,
        raw_unit: str,
        raw_ref: str,
        line: str,
        line_num: int,
        context: Optional[str],
    ) -> Dict[str, Any]:
        identified = self._identify_test_type(raw_name, context=context, unit=raw_unit, value=raw_value)
        if identified:
            display_name = identified.display_name
            test_name = identified.name
        else:
            display_name = raw_name
            test_name = raw_name

        status = 'UNKNOWN'
        ref_lower = raw_ref.lower()
        val_lower = raw_value.lower()
        if ref_lower and val_lower == ref_lower:
            status = 'NORMAL'
        elif val_lower in ('negative', 'not detected', 'absent', 'nil', 'none seen'):
            status = 'NORMAL'
        elif val_lower in ('positive', 'detected', 'present', 'reactive'):
            status = 'HIGH'

        return {
            'test_name': test_name,
            'display_name': display_name,
            'raw_test_name': raw_name,
            'value': raw_value,
            'unit': raw_unit or '',
            'reference_range': raw_ref,
            'status': status,
            'section_context': context or '',
            'raw_line': line,
            'line_number': line_num,
            'confidence': 0.85 if identified else 0.75,
        }

    def _parse_unitless_numeric_line(
        self, line: str, line_num: int, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        m = UNITLESS_NUMERIC_LINE_RE.match(line)
        if not m or not self._looks_like_test_label(m.group('name').strip()):
            return None
        return self._build_numeric_result_row(
            m.group('name').strip(),
            m.group('value').strip(),
            '',
            m.group('ref').strip(),
            line,
            line_num,
            context,
        )

    def _parse_simple_numeric_line(
        self, line: str, line_num: int, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        m = SIMPLE_NUMERIC_LINE_RE.match(line)
        if not m:
            return None
        raw_name = m.group('name').strip()
        raw_value = m.group('value').strip()
        if not self._looks_like_test_label(raw_name):
            return None
        # Column bleed: name already carries unit token, value is ref-interval endpoint.
        if name_embeds_lab_unit(raw_name):
            return None
        return self._build_numeric_result_row(
            raw_name,
            raw_value,
            '',
            '',
            line,
            line_num,
            context,
        )

    def _parse_simple_text_pair_line(
        self, line: str, line_num: int, context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        m = SIMPLE_TEXT_PAIR_LINE_RE.match(line)
        if not m:
            return None
        raw_name = m.group('name').strip()
        val = m.group('value').strip()
        if not self._looks_like_test_label(raw_name, val):
            return None
        if raw_name.rstrip().endswith(','):
            return None
        if ';' in raw_name:
            return None
        if is_qualitative_value(val):
            return None
        if val.lower() in NON_RESULT_TEXT_VALUES:
            return None
        return self._build_text_result_row(
            raw_name,
            val,
            '',
            '',
            line,
            line_num,
            context,
        )

    def _build_numeric_result_row(
        self,
        raw_name: str,
        raw_value: str,
        raw_unit: str,
        raw_ref: str,
        line: str,
        line_num: int,
        context: Optional[str],
    ) -> Dict[str, Any]:
        identified = self._identify_test_type(raw_name, context=context, unit=raw_unit, value=raw_value)
        if identified:
            identified = self._disambiguate_test_type(identified, raw_value, raw_unit, raw_ref)
        if identified:
            display_name = identified.display_name
            test_name = identified.name
        else:
            display_name = raw_name
            test_name = raw_name
        status = self._status_from_ref_string(raw_value, raw_ref)
        if status == 'UNKNOWN' and identified:
            status = self._status_from_db(raw_value, raw_unit, identified)
        return {
            'test_name': test_name,
            'display_name': display_name,
            'raw_test_name': raw_name,
            'value': raw_value,
            'unit': raw_unit or '',
            'reference_range': raw_ref,
            'status': status,
            'section_context': context or '',
            'raw_line': line,
            'line_number': line_num,
            'confidence': 0.85 if identified else 0.75,
        }

    # ------------------------------------------------------------------ #
    # 2. Database-driven regex pattern matcher
    # ------------------------------------------------------------------ #
    def _match_test_patterns(self, line: str, line_num: int, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Match line against database patterns"""
        for test_name, patterns in self.patterns.items():
            for pattern in sorted(patterns, key=lambda p: p.priority, reverse=True):
                try:
                    match = re.search(pattern.regex_pattern, line, re.IGNORECASE)
                    if match:
                        result = self._parse_pattern_match(match, pattern, line, line_num, context)
                        if result:
                            return result
                except re.error as e:
                    logger.warning(f"Regex error in pattern {pattern.pattern_name}: {e}")
                    continue
        return None

    def _parse_pattern_match(self, match, pattern, line: str, line_num: int, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse a successful pattern match"""
        try:
            value = match.group(pattern.value_group) if pattern.value_group <= len(match.groups()) else None
            if not value:
                return None

            # Extract unit
            unit = ''
            if pattern.unit_group and pattern.unit_group <= len(match.groups()):
                unit_str = match.group(pattern.unit_group)
                if unit_str:
                    unit = unit_str.strip()

            # Try to extract reference range from the rest of the line
            ref_range = ''
            if pattern.range_group and pattern.range_group <= len(match.groups()):
                ref_range = match.group(pattern.range_group) or ''

            # If no ref range from pattern, try to find it in the remaining line
            if not ref_range:
                ref_range = self._extract_ref_from_line_tail(line, match.end())

            # Disambiguate test type based on context, then value / ref range
            identified = self._apply_context(pattern.test_type, context)
            identified = self._disambiguate_test_type(identified, value, unit, ref_range)

            # Determine status
            status = self._status_from_ref_string(value, ref_range)
            if status == 'UNKNOWN':
                status = self._status_from_db(value, unit, identified)

            return {
                'test_name': identified.name,
                'display_name': identified.display_name,
                'raw_test_name': str(match.group(1)).strip(),
                'value': value,
                'unit': unit or 'N/A',
                'reference_range': ref_range,
                'status': status,
                'section_context': context or '',
                'raw_line': line,
                'line_number': line_num,
                'confidence': self._calculate_confidence(match, pattern),
            }
        except (IndexError, ValueError, InvalidOperation) as e:
            logger.warning(f"Error parsing pattern match: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Helper: extract reference range from line tail
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_ref_from_line_tail(line: str, start_pos: int) -> str:
        """Try to find a reference range in the text after the match."""
        tail = line[start_pos:].strip()
        if not tail:
            return ''
        # Pattern: number - number
        m = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)', tail)
        if m:
            return f'{m.group(1)} - {m.group(2)}'
        # Pattern: <number or >number
        m = re.search(r'([<>])\s*(\d+\.?\d*)', tail)
        if m:
            return f'{m.group(1)}{m.group(2)}'
        return ''

    # ------------------------------------------------------------------ #
    # Status determination helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _status_from_ref_string(value_str: str, ref_str: str) -> str:
        """Determine NORMAL / HIGH / LOW from a reference range string."""
        if not ref_str:
            return 'UNKNOWN'
        val = parse_comparable_number(value_str)
        if val is None:
            return 'UNKNOWN'

        # Range: "min - max"
        m = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)', ref_str)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if val < lo:
                return 'LOW'
            elif val > hi:
                return 'HIGH'
            else:
                return 'NORMAL'

        # Less-than: "<value"
        m = re.search(r'<\s*(\d+\.?\d*)', ref_str)
        if m:
            limit = float(m.group(1))
            return 'HIGH' if val >= limit else 'NORMAL'

        # Greater-than: ">value"
        m = re.search(r'>\s*(\d+\.?\d*)', ref_str)
        if m:
            limit = float(m.group(1))
            return 'LOW' if val <= limit else 'NORMAL'

        return 'UNKNOWN'

    def _status_from_db(self, value_str: str, unit_str: str, test_type) -> str:
        """Determine status using the validation rule for the printed unit, else the test's default unit."""
        try:
            val = Decimal(value_str)
            printed = normalize_unit(unit_str)
            rule = next((
                candidate for candidate in self.unit_rules.get(test_type.name, [])
                if printed and printed in {normalize_unit(candidate.unit.symbol), normalize_unit(candidate.unit.name)}
            ), None) or self.validation_rules.get(test_type.name)
            if rule:
                status, _ = rule.validate_value(val)
                return status
        except Exception:
            pass
        return 'UNKNOWN'

    # ------------------------------------------------------------------ #
    # Test type identification
    # ------------------------------------------------------------------ #
    def _identify_test_type(
        self, raw_name: str, context: Optional[str] = None, unit: Optional[str] = None, value: Optional[str] = None
    ) -> Optional[Any]:
        """Identify the catalog test for a printed name, using the section context (DLC, ALC, urine) when it fits.

        Matching is shared with the rest of the app (lab_tests.matching): catalog names and aliases decide
        what merges, and qualifiers such as urine, free, direct/indirect, or ratio keep analytes apart.
        A qualitative value ("Negative", "Absent") never links to a catalog test.
        """
        if self.matcher is None:
            return None
        candidate = self.matcher.match(raw_name, context=context, unit=unit, value=value)
        return self._apply_context(candidate, context)

    def _apply_context(self, candidate, context: Optional[str]) -> Optional[Any]:
        """Remap a candidate test type based on the current section context."""
        if not candidate or not context:
            return candidate
        mapping = self.CONTEXT_MAPPINGS.get(context, {})
        # Direct name match
        mapped_name = mapping.get(candidate.name)
        if mapped_name:
            mapped = self.test_types.get(mapped_name)
            if mapped:
                return mapped
        # Strip known prefixes (dlc_, alc_, urine_) and try again
        base_name = candidate.name
        for prefix in ('dlc_', 'alc_', 'urine_'):
            if base_name.startswith(prefix):
                base_name = base_name[len(prefix):]
                break
        mapped_name = mapping.get(base_name)
        if mapped_name:
            mapped = self.test_types.get(mapped_name)
            if mapped:
                return mapped
        return candidate

    def _disambiguate_test_type(self, candidate, raw_value: str, raw_unit: str, raw_ref: str):
        """Switch candidate test type when value/reference range indicates a different variant."""
        if not candidate:
            return candidate

        val = parse_comparable_number(raw_value)
        if val is None:
            return candidate

        # Extract ref range max if available
        ref_max = None
        if raw_ref:
            m = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)', raw_ref)
            if m:
                ref_max = float(m.group(2))

        rule = self.validation_rules.get(candidate.name)
        normal_max = float(rule.normal_max) if rule and rule.normal_max else None

        # Creatinine: serum vs urine
        if candidate.name == 'creatinine':
            serum_ceiling = normal_max if normal_max else 1.5
            if val > serum_ceiling * 5 or (ref_max and ref_max > serum_ceiling * 10):
                urine = self.test_types.get('urine_creatinine')
                if urine:
                    return urine
        elif candidate.name == 'urine_creatinine':
            urine_ceiling = normal_max if normal_max else 392.0
            if val < urine_ceiling / 20:
                serum = self.test_types.get('creatinine')
                if serum:
                    return serum

        return candidate

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #
    @staticmethod
    def _maybe_join_continuation_line(lines: list[str], line_num: int, line: str) -> str:
        """
        Join a header-only line with the following value line.

        Handles timed stimulation panels where the test name and timed value
        appear on separate extracted lines. Does not glue method-only wrap
        fragments (e.g. COLOUROMETER) onto the next analyte.
        """
        if (
            TABULAR_LINE_RE.match(line)
            or match_right_anchored_tabular(line)
            or QUALITATIVE_LINE_RE.match(line)
            or DESCRIPTIVE_LINE_RE.match(line)
            or CATEGORICAL_LINE_RE.match(line)
            or UNITLESS_NUMERIC_LINE_RE.match(line)
        ):
            return line
        if line_num + 1 >= len(lines):
            return line
        nxt = lines[line_num + 1].strip()
        if not nxt:
            return line
        # Next line already looks like its own result row (Name  Value …).
        # Method-only wraps such as COLOUROMETER must not steal that row.
        if re.match(r'^[A-Za-z]', nxt) and (
            TABULAR_LINE_RE.match(nxt)
            or match_right_anchored_tabular(nxt)
            or QUALITATIVE_LINE_RE.match(nxt)
            or DESCRIPTIVE_LINE_RE.match(nxt)
            or CATEGORICAL_LINE_RE.match(nxt)
            or UNITLESS_NUMERIC_LINE_RE.match(nxt)
            or SIMPLE_NUMERIC_LINE_RE.match(nxt)
            or SIMPLE_TEXT_PAIR_LINE_RE.match(nxt)
        ):
            return line
        combined = f"{line} {nxt}"
        if TABULAR_LINE_RE.match(combined) or QUALITATIVE_LINE_RE.match(combined):
            return combined
        return line

    @staticmethod
    def _looks_like_test_label(raw_name: str, value: str = '') -> bool:
        """Reject prose sentences mistaken for lab result rows."""
        if not raw_name or len(raw_name) < 2:
            return False
        if re.match(r'^\d+$', raw_name):
            return False
        # EMR metadata rows ("Visit ID : Dummy101 Status : Final Report").
        if ':' in raw_name:
            return False
        if len(raw_name) > 70 or len(raw_name.split()) > 10:
            return False
        if raw_name.endswith('.'):
            return False
        if re.search(r',\S', raw_name):
            return False
        lower = raw_name.lower()
        val_lower = (value or '').lower()
        if '&' in raw_name and val_lower in NON_RESULT_TEXT_VALUES:
            return False
        if val_lower in ('serum', 'urine', 'plasma', 'csf', 'edta', 'blood'):
            # Panel headers (ALLERGY SCREEN, SERUM) — not specimen-type result rows.
            if re.search(r'\b(type of sample|sample type|specimen type|specimen)\b', lower):
                pass
            elif re.match(r'^[a-z\s,]+$', lower):
                return False
            elif len(raw_name) > 12 and raw_name.upper() == raw_name:
                return False
        if val_lower in ('iv', 'im', 'po', 'sc', 'collection', 'centre', 'center', 'test'):
            return False
        if val_lower in NON_RESULT_TEXT_VALUES:
            return False
        if re.search(r'\b(collection cent(?:re|er)|reference lab(?:oratory)?)\b', lower):
            return False
        if lower.startswith('head '):
            return False
        if re.search(r'\b(ph\.?d|m\.?d)\b', lower):
            return False
        # Subordinate / narrative clause markers — generic, not corpus-specific.
        if re.search(
            r'\b(that|which|are|were|with|have|has|had|patient|cases|similar|clinical|'
            r'affected|define|development|factors|organs|commentary|bacteria|levels|'
            r'may|organism|volume of)\b',
            lower,
        ):
            return False
        if re.search(r'\b(in the|on the|of the|to the|from the|for the)\b', lower):
            return False
        noise_starts = (
            'page', 'note', 'collected', 'reported', 'lab no',
            'name', 'ref by', 'ref doctor', 'a/c', 'national', 'block',
            'important', 'interpretation', 'advised', 'disclaimer',
            'department of', 'visit id', 'client name', 'patient location',
            'patient name', 'uhid',
        )
        return not any(lower.startswith(ns) for ns in noise_starts)

    @staticmethod
    def _looks_like_qualitative_test_name(raw_name: str) -> bool:
        """Backward-compatible alias for qualitative label checks."""
        return EnhancedMedicalPDFParser._looks_like_test_label(raw_name)

    @staticmethod
    def _should_skip_line(line: str) -> bool:
        """Return True if the line is noise (headers, footers, etc.)."""
        stripped = line.strip()
        if re.match(r'^\s*(Differential|Absolute)\s+', stripped, re.IGNORECASE):
            if TABULAR_LINE_RE.match(stripped) or match_right_anchored_tabular(stripped):
                return False
        for pat in SKIP_PATTERNS:
            if pat.search(line):
                if pat.pattern.find('Differential|Absolute') >= 0:
                    if TABULAR_LINE_RE.match(stripped) or match_right_anchored_tabular(stripped):
                        return False
                return True
        return False

    @staticmethod
    def _calculate_confidence(match, pattern) -> float:
        base_confidence = min(pattern.priority / 10.0, 1.0)
        group_boost = len([g for g in match.groups() if g]) * 0.1
        return min(base_confidence + group_boost, 1.0)

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #
    def parse_medical_report(self, pdf_file) -> Dict[str, Any]:
        """Parse a medical report PDF with enhanced accuracy"""
        text = self.extract_text_from_pdf(pdf_file)
        if not text:
            return {'error': 'Could not extract text from PDF'}

        test_results, report_formats = apply_report_formats(
            text, self.extract_test_results(text), self._report_format_row
        )

        if test_results:
            avg_confidence = sum(r.get('confidence', 0) for r in test_results) / len(test_results)
        else:
            avg_confidence = 0

        return {
            'text': text,
            'test_results': test_results,
            'parsed_successfully': len(test_results) > 0,
            'confidence_score': avg_confidence,
            'total_tests_found': len(test_results),
            'high_confidence_tests': len([r for r in test_results if r.get('confidence', 0) > 0.7]),
            'report_formats': report_formats,
        }

    def _report_format_row(self, row: ReportRow, format_name: str) -> Dict[str, Any]:
        """A report format's row in the generic parser's shape, linked to the catalog like any other."""
        parsed = self._build_numeric_result_row(
            str(row.test_name).strip(), str(row.value).strip(), str(row.unit or '').strip(),
            str(row.reference_range or '').strip(), '', None, row.section or None,
        )
        if row.status:
            parsed['status'] = str(row.status).strip().upper()
        # No line number: relinking keeps the format's section instead of recomputing it from the text.
        parsed.update(raw_line='', line_number=None, confidence=0.9, report_format=format_name)
        return parsed


def parse_medical_pdf_enhanced(pdf_file) -> Dict[str, Any]:
    """Enhanced convenience function to parse medical PDF"""
    parser = EnhancedMedicalPDFParser()
    return parser.parse_medical_report(pdf_file)
