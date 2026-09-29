import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical_reports", "0006_testresult_test_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicalreport",
            name="file",
            field=models.FileField(
                upload_to="medical_reports/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf"]
                    )
                ],
            ),
        ),
    ]
