from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


def remove_ambiguous_conversions(apps, schema_editor):
    """Existing rows cannot be assigned safely because their analyte was not stored."""
    UnitConversion = apps.get_model("lab_tests", "UnitConversion")
    UnitConversion.objects.all().delete()
    if schema_editor.connection.vendor == "postgresql":
        # Flush deferred FK checks queued by the delete; otherwise PostgreSQL rejects the
        # later ALTER TABLE / CREATE INDEX in this transaction ("pending trigger events").
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def seed_scoped_conversions(apps, schema_editor):
    LabTestType = apps.get_model("lab_tests", "LabTestType")
    LabTestUnit = apps.get_model("lab_tests", "LabTestUnit")
    LabTestTypeUnit = apps.get_model("lab_tests", "LabTestTypeUnit")
    UnitConversion = apps.get_model("lab_tests", "UnitConversion")

    conversion_groups = [
        (["vitamin_d"], "ng_ml", "nmol_l", "2.496", "0.4006"),
        (["glucose"], "mg_dl", "mmol_l", "0.0555", "18.018"),
        (["total_cholesterol", "hdl_cholesterol", "ldl_cholesterol", "vldl_cholesterol"], "mg_dl", "mmol_l", "0.02586", "38.67"),
        (["triglycerides"], "mg_dl", "mmol_l", "0.01129", "88.54"),
        (["creatinine", "urine_creatinine"], "mg_dl", "umol_l", "88.4", "0.01131"),
        (["total_bilirubin", "direct_bilirubin"], "mg_dl", "umol_l", "17.104", "0.05847"),
        (["iron"], "ug_dl", "umol_l", "0.1791", "5.585"),
        (["vitamin_b12"], "pg_ml", "pmol_l", "0.7378", "1.355"),
        (["folate"], "ng_ml", "nmol_l", "2.266", "0.441"),
        (["hemoglobin", "total_protein", "albumin"], "g_dl", "g_l", "10", "0.1"),
    ]

    for test_names, from_name, to_name, factor, reverse in conversion_groups:
        from_unit = LabTestUnit.objects.filter(name=from_name).first()
        to_unit = LabTestUnit.objects.filter(name=to_name).first()
        if from_unit is None or to_unit is None:
            continue
        factor_decimal = Decimal(factor)
        reverse_decimal = Decimal(reverse)
        for test_type in LabTestType.objects.filter(name__in=test_names):
            UnitConversion.objects.update_or_create(
                test_type=test_type,
                from_unit=from_unit,
                to_unit=to_unit,
                defaults={
                    "conversion_factor": factor_decimal,
                    "reverse_factor": reverse_decimal,
                    "is_active": True,
                },
            )
            UnitConversion.objects.update_or_create(
                test_type=test_type,
                from_unit=to_unit,
                to_unit=from_unit,
                defaults={
                    "conversion_factor": reverse_decimal,
                    "reverse_factor": factor_decimal,
                    "is_active": True,
                },
            )

            if test_type.default_unit == from_name:
                LabTestTypeUnit.objects.update_or_create(
                    test_type=test_type,
                    unit=to_unit,
                    defaults={
                        "normal_min": (
                            test_type.normal_min * factor_decimal
                            if test_type.normal_min is not None else None
                        ),
                        "normal_max": (
                            test_type.normal_max * factor_decimal
                            if test_type.normal_max is not None else None
                        ),
                        "conversion_factor": factor_decimal,
                        "is_active": True,
                    },
                )


class Migration(migrations.Migration):

    dependencies = [
        ("lab_tests", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="unitconversion",
            name="test_type",
            field=models.ForeignKey(
                help_text="Analyte this conversion factor applies to",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unit_conversions",
                to="lab_tests.labtesttype",
            ),
        ),
        migrations.RunPython(
            remove_ambiguous_conversions,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterUniqueTogether(
            name="unitconversion",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="unitconversion",
            name="test_type",
            field=models.ForeignKey(
                help_text="Analyte this conversion factor applies to",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unit_conversions",
                to="lab_tests.labtesttype",
            ),
        ),
        migrations.AddConstraint(
            model_name="unitconversion",
            constraint=models.UniqueConstraint(
                fields=("test_type", "from_unit", "to_unit"),
                name="unique_test_type_unit_conversion",
            ),
        ),
        migrations.RunPython(
            seed_scoped_conversions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
