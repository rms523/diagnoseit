"""Re-match stored test results to the lab test catalog and to each owner's name links.

A result is matched by the name printed on the report when the report's parsed data shows its stored
name came from the parser or from an earlier link. A result a user renamed is matched by its own name, so
a rename is never replaced by the printed one. A result without a number is never linked. A row the text
parser read is matched in the report section the current parser gives its line, so parser fixes to section
tracking reach stored results without parsing the report again.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from lab_tests.services import build_test_type_matcher, normalize_test_identifier, tidy_test_name

from .models import MedicalReport, TestResult


@dataclass
class RelinkOutcome:
    checked: int = 0
    updated: list[TestResult] = field(default_factory=list)
    # (printed name, stored name, catalog test before, new name, catalog test after) -> number of results
    changes: Counter = field(default_factory=Counter)


def relink_results(reports: QuerySet[MedicalReport], apply: bool) -> RelinkOutcome:
    """Re-match every result of these reports with its owner's matcher, saving the changes when apply is set."""
    outcome = RelinkOutcome()
    matchers: dict[int, Any] = {}
    parser = None
    reports = reports.prefetch_related('test_results__test_type').order_by('id')
    for report in reports.iterator(chunk_size=200):
        if report.user_id not in matchers:
            matchers[report.user_id] = build_test_type_matcher(report.user_id)
        matcher = matchers[report.user_id]
        sources = _parser_rows(report)
        contexts: list = []
        data = report.parsed_data if isinstance(report.parsed_data, dict) else {}
        if data.get('text') and any(isinstance(row.get('line_number'), int) for row in sources[0].values()):
            if parser is None:
                from utils.enhanced_pdf_parser import EnhancedMedicalPDFParser

                parser = EnhancedMedicalPDFParser()
            contexts = parser.section_contexts(str(data['text']))
        for result in report.test_results.all():
            outcome.checked += 1
            printed, context, from_parser = _printed_name(result, sources, contexts)
            test_type = matcher.match(printed, context=context, unit=result.unit, value=result.value)
            new_name = (test_type.display_name if test_type else tidy_test_name(printed))[:200]
            type_changed = (test_type.pk if test_type else None) != result.test_type_id
            if not type_changed and not (from_parser and new_name != result.test_name):
                continue
            before = result.test_type.name if result.test_type else '-'
            after = test_type.name if test_type else '-'
            outcome.changes[(printed, result.test_name, before, new_name, after)] += 1
            result.test_type = test_type
            result.test_name = new_name
            outcome.updated.append(result)

    if apply and outcome.updated:
        with transaction.atomic():
            TestResult.objects.bulk_update(outcome.updated, ['test_type', 'test_name'], batch_size=500)
    return outcome


def _parser_rows(report: MedicalReport) -> tuple[dict[int, dict], dict[tuple[str, str], list[dict]]]:
    data = report.parsed_data if isinstance(report.parsed_data, dict) else {}
    rows = [row for row in data.get('test_results') or [] if isinstance(row, dict)]
    by_result_id = {row['result_id']: row for row in rows if isinstance(row.get('result_id'), int)}
    by_name_and_value: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        names = {normalize_test_identifier(row.get(key)) for key in ('display_name', 'test_name')} - {''}
        for name in names:
            by_name_and_value.setdefault((name, str(row.get('value', '')).strip()), []).append(row)
    return by_result_id, by_name_and_value


def _printed_name(result: TestResult, sources, contexts: list) -> tuple[str, Any, bool]:
    """The name to match, the parser section it was read in, and whether the stored name came from the parser.

    A stored name equal to the linked catalog test's name came from linking, so it follows the printed
    name too: removing a name link or a catalog alias can then unlink the result again.
    """
    by_result_id, by_name_and_value = sources
    stored = normalize_test_identifier(result.test_name)
    row = by_result_id.get(result.id)
    if row is None:
        matches = by_name_and_value.get((stored, (result.value or '').strip()), [])
        row = matches[0] if len(matches) == 1 else None
    if row is not None:
        parser_names = {normalize_test_identifier(row.get(key)) for key in ('display_name', 'test_name')}
        linked_name = normalize_test_identifier(result.test_type.display_name) if result.test_type_id else None
        if stored in parser_names or stored == linked_name:
            printed = str(row.get('raw_test_name') or row.get('display_name') or result.test_name)
            line = row.get('line_number')
            if isinstance(line, int) and 0 <= line < len(contexts):
                return printed, contexts[line], True
            return printed, row.get('section_context') or None, True
    return result.test_name, None, False
