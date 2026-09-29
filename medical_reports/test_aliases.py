"""A user's links from printed test names the catalog does not know to catalog tests.

The AI suggests a catalog test for each name; a link is saved only when the user confirms it, and it
applies to that user's results only. Saving or removing a link relinks the user's stored results.
"""

from __future__ import annotations

import json
import logging
from collections import Counter

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ai_settings.client import chat_json, parse_json_object
from ai_settings.services import DEFAULT_TEMPERATURES, ROLE_REPORT_REVIEW, get_ai_config
from lab_tests.matching import alias_key, allowed_qualifiers, qualifiers
from lab_tests.models import LabTestType, LabTestUnit, UserTestAlias
from lab_tests.services import normalize_test_identifier

from .models import MedicalReport, TestResult
from .relinking import relink_results

logger = logging.getLogger(__name__)

MAX_SUGGEST_NAMES = 50

SUGGEST_SYSTEM_PROMPT = (
    "You match lab test names printed on reports to a catalog of lab tests. "
    "Reply with a JSON object only."
)

SUGGEST_INSTRUCTIONS = """Catalog tests, one per line as key: name [default unit] (other names):
{catalog}

Printed names, with the units and some values printed next to them:
{names}

For each printed name, give the catalog key of the test it is, or null.
- Choose a test only when the printed name is clearly the same measurement: the same analyte, the same
  specimen (blood, urine), and the same variant (free or total, direct or indirect, fasting, random or
  after a meal, a ratio or its parts). The units should fit the test.
- Use null when no catalog test is that measurement, when unsure, or when the name is not a lab test.

Reply as {{"suggestions": [{{"name": "<printed name as given>", "test_type": "<catalog key or null>", "reason": "<at most 15 words>"}}]}}"""


def _alias_json(alias: UserTestAlias) -> dict:
    return {
        'id': alias.id,
        'name': alias.name,
        'test_type': alias.test_type.name,
        'test_type_display_name': alias.test_type.display_name,
        'created_at': alias.created_at.isoformat(),
    }


def link_error(name: str, test_type: LabTestType) -> str | None:
    """Why this name cannot be linked to this test, or None when it can."""
    if alias_key(name) is None:
        return f'"{name}" has no test name words to link.'
    extra = qualifiers(name) - allowed_qualifiers(test_type)
    if extra:
        return f'"{name}" is a different test ({", ".join(sorted(extra))}) than {test_type.display_name}.'
    return None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def test_aliases(request):
    """GET: the user's name links. POST {name, test_type}: link a printed name to a catalog test."""
    if request.method == 'GET':
        aliases = UserTestAlias.objects.filter(user=request.user).select_related('test_type')
        return Response([_alias_json(alias) for alias in aliases])

    name = str(request.data.get('name') or '').strip()
    test_type_name = str(request.data.get('test_type') or '').strip()
    if not name or len(name) > 200:
        return Response({'error': 'Give the printed test name (at most 200 characters).'}, status=status.HTTP_400_BAD_REQUEST)
    test_type = LabTestType.objects.filter(name=test_type_name, is_active=True).first()
    if test_type is None:
        return Response({'error': 'Choose a test from the catalog.'}, status=status.HTTP_400_BAD_REQUEST)
    error = link_error(name, test_type)
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

    alias, _ = UserTestAlias.objects.update_or_create(
        user=request.user, match_key=alias_key(name), defaults={'name': name, 'test_type': test_type}
    )
    outcome = relink_results(MedicalReport.objects.filter(user=request.user), apply=True)
    return Response({'alias': _alias_json(alias), 'relinked': len(outcome.updated)}, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def test_alias_detail(request, alias_id):
    """Remove a name link; results it linked go back to their printed names."""
    deleted, _ = UserTestAlias.objects.filter(user=request.user, pk=alias_id).delete()
    if not deleted:
        return Response({'error': 'Name link not found.'}, status=status.HTTP_404_NOT_FOUND)
    outcome = relink_results(MedicalReport.objects.filter(user=request.user), apply=True)
    return Response({'relinked': len(outcome.updated)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def suggest_test_aliases(request):
    """POST {names}: the report review model's catalog test for each printed name, for the user to confirm."""
    raw_names = request.data.get('names')
    if not isinstance(raw_names, list):
        return Response({'error': 'names must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
    names = list(dict.fromkeys(str(name).strip() for name in raw_names if str(name).strip()))[:MAX_SUGGEST_NAMES]
    if not names:
        return Response({'error': 'Give at least one name.'}, status=status.HTTP_400_BAD_REQUEST)

    config = get_ai_config(ROLE_REPORT_REVIEW)
    if not config.is_configured:
        return Response(
            {'error': 'Set up the report review model in AI settings to get suggestions.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from django_ratelimit.core import is_ratelimited

    if is_ratelimited(request, group='test-alias-suggestions', key='user', rate='10/m', increment=True):
        return Response(
            {'error': 'Too many AI suggestion requests. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    catalog = {test_type.name: test_type for test_type in LabTestType.objects.filter(is_active=True)}
    content = SUGGEST_INSTRUCTIONS.format(
        catalog=_catalog_lines(catalog.values()),
        names=json.dumps(_name_samples(request.user, names), ensure_ascii=False),
    )
    messages = [{'role': 'system', 'content': SUGGEST_SYSTEM_PROMPT}, {'role': 'user', 'content': content}]
    try:
        temperature = config.temperature_or(DEFAULT_TEMPERATURES[ROLE_REPORT_REVIEW])
        reply = chat_json(config, messages, max_tokens=config.max_tokens, temperature=temperature)
    except Exception as exc:
        logger.warning('Test name suggestions failed: %s', exc)
        return Response(
            {'error': f'The review model did not respond ({type(exc).__name__}).'}, status=status.HTTP_502_BAD_GATEWAY
        )
    try:
        payload = parse_json_object(reply)
    except ValueError:
        return Response({'error': 'The review model did not return valid JSON.'}, status=status.HTTP_502_BAD_GATEWAY)

    picked: dict[str, dict] = {}
    items = payload.get('suggestions') if isinstance(payload, dict) else None
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            picked.setdefault(normalize_test_identifier(item.get('name')), item)

    suggestions = []
    for name in names:
        item = picked.get(normalize_test_identifier(name)) or {}
        test_type = catalog.get(str(item.get('test_type') or '').strip())
        # A suggestion the catalog rules would reject (urine vs blood, free vs total) is dropped.
        if test_type is not None and link_error(name, test_type):
            test_type = None
        suggestions.append({
            'name': name,
            'test_type': test_type.name if test_type else None,
            'test_type_display_name': test_type.display_name if test_type else None,
            'reason': str(item.get('reason') or '')[:200],
        })
    return Response({'suggestions': suggestions})


def _catalog_lines(test_types) -> str:
    symbols = dict(LabTestUnit.objects.values_list('name', 'symbol'))
    lines = []
    for test_type in sorted(test_types, key=lambda item: item.name):
        unit = symbols.get(test_type.default_unit) or test_type.default_unit
        aliases = ', '.join(str(alias) for alias in (test_type.aliases or [])[:6])
        lines.append(f"{test_type.name}: {test_type.display_name} [{unit}]" + (f" ({aliases})" if aliases else ''))
    return '\n'.join(lines)


def _name_samples(user, names: list[str]) -> list[dict]:
    wanted = {normalize_test_identifier(name): name for name in names}
    units: dict[str, Counter] = {key: Counter() for key in wanted}
    values: dict[str, list[str]] = {key: [] for key in wanted}
    for test_name, unit, value in TestResult.objects.filter(report__user=user).values_list('test_name', 'unit', 'value'):
        key = normalize_test_identifier(test_name)
        if key not in wanted:
            continue
        if unit:
            units[key][unit] += 1
        if value and len(values[key]) < 3:
            values[key].append(value)
    return [
        {'name': name, 'units': [unit for unit, _ in units[key].most_common(2)], 'values': values[key]}
        for key, name in wanted.items()
    ]
