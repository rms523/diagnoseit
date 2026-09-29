from django.db import migrations, models
import django.db.models.deletion


def normalize(value):
    return " ".join(str(value or "").strip().casefold().split())


def backfill_test_types(apps, schema_editor):
    LabTestType = apps.get_model("lab_tests", "LabTestType")
    TestResult = apps.get_model("medical_reports", "TestResult")

    lookup = {}
    for test_type in LabTestType.objects.filter(is_active=True):
        candidates = [test_type.name, test_type.display_name]
        candidates.extend(test_type.aliases or [])
        for candidate in candidates:
            key = normalize(candidate)
            if key:
                lookup.setdefault(key, test_type.pk)

    pending = []
    for result in TestResult.objects.filter(test_type__isnull=True).iterator():
        test_type_id = lookup.get(normalize(result.test_name))
        if test_type_id:
            result.test_type_id = test_type_id
            pending.append(result)

    if pending:
        TestResult.objects.bulk_update(pending, ["test_type"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("lab_tests", "0002_scope_unit_conversions_to_test_type"),
        ("medical_reports", "0005_medicalreport_status_and_parse_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="testresult",
            name="test_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="test_results",
                to="lab_tests.labtesttype",
            ),
        ),
        migrations.RunPython(backfill_test_types, migrations.RunPython.noop),
    ]
