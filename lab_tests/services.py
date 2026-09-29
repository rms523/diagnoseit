"""Shared catalog lookups used by parsing, validation, and conversion APIs."""

from __future__ import annotations

import re

from .matching import TestNameMatcher
from .models import LabTestType, UserTestAlias


def normalize_test_identifier(value: object) -> str:
    """Normalize a name for exact comparisons (case and spacing only); use the matcher to find catalog tests."""
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


# The separator or full stop a report prints after a name: "IgA -", "Epithelial cells.", "Reaction. -".
_TRAILING_SEPARATOR_RE = re.compile(r"(?:\s+[-\u2013\u2014:]+|[.:]+)\s*$")


def tidy_test_name(value: object) -> str:
    """A printed test name without the separators or full stops the report put after it."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    tidied = text
    for _ in range(3):
        shorter = _TRAILING_SEPARATOR_RE.sub("", tidied).strip()
        if shorter == tidied:
            break
        tidied = shorter
    return tidied or text


def build_test_type_matcher(user_id: int | None = None) -> TestNameMatcher:
    """A matcher over every active catalog test, plus the names this user linked; build one per request or parse."""
    aliases = []
    if user_id is not None:
        rows = UserTestAlias.objects.filter(user_id=user_id, test_type__is_active=True).select_related('test_type')
        aliases = [(row.name, row.test_type) for row in rows]
    return TestNameMatcher(LabTestType.objects.filter(is_active=True), user_aliases=aliases)


def resolve_test_type(
    name: object, context: str | None = None, *, result_value: object = None, user_id: int | None = None
) -> LabTestType | None:
    """The catalog test a printed or typed name refers to, if any (none for a value without a number)."""
    return build_test_type_matcher(user_id).match(name, context=context, value=result_value)
