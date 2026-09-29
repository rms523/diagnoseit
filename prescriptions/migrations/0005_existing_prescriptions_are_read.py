"""Prescriptions stored before reading moved to the background were read as they were uploaded.

They would otherwise sit at the PENDING default forever and show as still being read.
"""

from django.db import migrations


def mark_existing_as_read(apps, schema_editor):
    apps.get_model('prescriptions', 'Prescription').objects.update(status='COMPLETED')


class Migration(migrations.Migration):

    dependencies = [
        ('prescriptions', '0004_prescription_parsing_and_chat'),
    ]

    operations = [
        migrations.RunPython(mark_existing_as_read, migrations.RunPython.noop),
    ]
