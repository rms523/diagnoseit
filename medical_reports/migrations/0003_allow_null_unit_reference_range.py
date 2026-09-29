# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_reports', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='testresult',
            name='unit',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='testresult',
            name='reference_range',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]