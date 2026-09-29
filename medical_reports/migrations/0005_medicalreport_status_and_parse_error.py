# Generated manually for async parsing

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_reports', '0004_alter_testresult_unit'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicalreport',
            name='parse_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalreport',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('PROCESSING', 'Processing'),
                    ('COMPLETED', 'Completed'),
                    ('FAILED', 'Failed'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
    ]
