"""Adding, changing, and removing lab test catalog entries from the app.

The catalog is shared for reading and maintained by staff. `populate_lab_tests`
loads the built-in tests after every migration and deploy, and would undo an edit made here, so an entry
someone changes in the app is marked (`edited_by_user`) and the loader then leaves that entry alone.
Removing a built-in entry deactivates it rather than deleting it, since the loader would otherwise put it
back; an entry someone added here is deleted outright.

A name or an alias decides which printed test names a result is matched under (`lab_tests.matching`), so an
alias that already belongs to another test is refused, and every change re-matches stored results for every
user (`medical_reports.relinking`). Results of a removed test are not deleted: they keep their printed name
and go back to being unlinked.
"""

from __future__ import annotations

import re

from rest_framework import serializers

from .matching import TestNameMatcher
from .models import LabTestType, LabTestTypeUnit, LabTestUnit, LabTestValidationRule

# A catalog key such as "glucose_fasting" or "vitamin_d": the stable identifier results and links refer to.
KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
MAX_ALIASES = 40

CATALOG_FIELDS = [
    'id', 'name', 'display_name', 'description', 'category', 'aliases',
    'default_unit', 'normal_min', 'normal_max', 'is_active',
    'source', 'edited_by_user', 'created_at', 'updated_at',
]


def suggest_key(display_name: object) -> str:
    """A catalog key made from a display name: "Vitamin D (25-OH)" -> "vitamin_d_25_oh"."""
    key = re.sub(r"[^a-z0-9]+", "_", str(display_name or '').casefold()).strip('_')
    return key[:200]


def clean_aliases(values: object) -> list[str]:
    """The alias list without blanks, surrounding spaces, or repeats (ignoring case)."""
    if not isinstance(values, (list, tuple)):
        raise serializers.ValidationError('Give the other names as a list.')
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or '')).strip()
        if not text:
            continue
        if len(text) > 200:
            raise serializers.ValidationError(f'"{text[:40]}…" is longer than 200 characters.')
        if text.casefold() in seen:
            continue
        seen.add(text.casefold())
        aliases.append(text)
    if len(aliases) > MAX_ALIASES:
        raise serializers.ValidationError(f'Give at most {MAX_ALIASES} other names.')
    return aliases


def conflicting_test(name: str, exclude_pk: int | None = None) -> LabTestType | None:
    """The other active catalog test this name already matches, if any.

    Two tests answering to one name would make results match neither (the matcher needs exactly one fit),
    so a name or alias that belongs elsewhere is refused before it can unlink results.
    """
    others = LabTestType.objects.filter(is_active=True)
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    # A value is needed because a name alone never links a result without a number; "1" stands in for one.
    return TestNameMatcher(others).match(name, value='1')


def sync_default_unit(test_type: LabTestType) -> None:
    """Keep the entry's own unit and reference range usable for unit conversion and value validation."""
    unit = LabTestUnit.objects.filter(name=test_type.default_unit).first()
    if unit is None:
        return
    LabTestTypeUnit.objects.update_or_create(
        test_type=test_type,
        unit=unit,
        defaults={'normal_min': test_type.normal_min, 'normal_max': test_type.normal_max, 'is_active': True},
    )
    # Critical limits are left as they are: the built-in ones come from populate_lab_tests.CRITICAL_LIMITS,
    # and a test added here has none, since they cannot be derived from the normal range.
    LabTestValidationRule.objects.update_or_create(
        test_type=test_type,
        unit=unit,
        defaults={'normal_min': test_type.normal_min, 'normal_max': test_type.normal_max, 'is_active': True},
    )


def relink_everyone() -> int:
    """Re-match every user's stored results to the catalog; the number of results that changed."""
    from medical_reports.models import MedicalReport
    from medical_reports.relinking import relink_results

    return len(relink_results(MedicalReport.objects.all(), apply=True).updated)


def remove_test_type(test_type: LabTestType) -> str:
    """Remove an entry: deleted when someone added it here, deactivated when the loader would restore it."""
    if test_type.source == LabTestType.SOURCE_USER:
        test_type.delete()
        return 'deleted'
    # Its units and conversions are left alone, so putting the entry back restores it whole.
    test_type.is_active = False
    test_type.edited_by_user = True
    test_type.save(update_fields=['is_active', 'edited_by_user', 'updated_at'])
    return 'deactivated'


class LabTestTypeWriteSerializer(serializers.ModelSerializer):
    """Reads and writes one catalog entry; `source` and `edited_by_user` are set by the view, not the client."""

    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    aliases = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    result_count = serializers.SerializerMethodField()

    class Meta:
        model = LabTestType
        fields = CATALOG_FIELDS + ['result_count']
        read_only_fields = ['id', 'source', 'edited_by_user', 'created_at', 'updated_at']

    def get_result_count(self, test_type: LabTestType) -> int:
        """Stored results linked to this test; they are unlinked, never deleted, when it is removed."""
        count = getattr(test_type, 'result_count', None)
        return count if isinstance(count, int) else test_type.test_results.count()

    def validate_name(self, value: str) -> str:
        key = str(value or '').strip().casefold()
        if key and not KEY_RE.match(key):
            raise serializers.ValidationError(
                'Use lowercase letters, numbers, and underscores for the key, such as "vitamin_d".'
            )
        return key

    def validate_display_name(self, value: str) -> str:
        display_name = re.sub(r"\s+", " ", str(value or '')).strip()
        if not display_name:
            raise serializers.ValidationError('Give the name to show for this test.')
        return display_name

    def validate_aliases(self, value: object) -> list[str]:
        return clean_aliases(value)

    def validate_default_unit(self, value: str) -> str:
        unit = str(value or '').strip()
        if not LabTestUnit.objects.filter(name=unit).exists():
            raise serializers.ValidationError(f'"{unit}" is not a known unit. Choose one from the list.')
        return unit

    def validate(self, data: dict) -> dict:
        instance = self.instance
        if not data.get('name') and instance is None:
            data['name'] = suggest_key(data.get('display_name'))
        if not data.get('name') and instance is not None:
            data.pop('name', None)
        name = data.get('name') or (instance.name if instance else '')
        if not name:
            raise serializers.ValidationError({'name': 'Give a key for this test, such as "vitamin_d".'})
        clash = LabTestType.objects.filter(name=name).exclude(pk=instance.pk if instance else None).first()
        if clash is not None:
            raise serializers.ValidationError({'name': f'The key "{name}" is already used by {clash.display_name}.'})

        low = data.get('normal_min', instance.normal_min if instance else None)
        high = data.get('normal_max', instance.normal_max if instance else None)
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {'normal_max': 'The top of the normal range must not be below the bottom.'}
            )

        # Names the catalog would now answer to; each must not already belong to a different test.
        display_name = data.get('display_name', instance.display_name if instance else '')
        aliases = data.get('aliases', instance.aliases if instance else []) or []
        is_active = data.get('is_active', instance.is_active if instance else True)
        if is_active:
            for candidate in [name, display_name, *aliases]:
                other = conflicting_test(candidate, exclude_pk=instance.pk if instance else None)
                if other is not None:
                    raise serializers.ValidationError(
                        {'aliases': f'"{candidate}" already names {other.display_name}. Remove it there first.'}
                    )
        return data
