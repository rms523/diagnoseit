import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prescriptions", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prescription",
            name="file",
            field=models.FileField(
                upload_to="prescriptions/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf"]
                    )
                ],
            ),
        ),
    ]
