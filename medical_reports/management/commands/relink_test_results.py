"""
Re-match stored test results to the lab test catalog and each user's name links.

Run after the catalog or name matching changes, for example after populate_lab_tests adds tests:

  uv run python manage.py relink_test_results           # dry run: list what would change
  uv run python manage.py relink_test_results --apply   # save the changes

See medical_reports.relinking for which name each result is matched by.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from medical_reports.models import MedicalReport
from medical_reports.relinking import relink_results


class Command(BaseCommand):
    help = "Re-match stored test results to the lab test catalog (a dry run unless --apply is given)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Save the changes instead of only listing them.')

    def handle(self, *args, **options):
        apply = options['apply']
        outcome = relink_results(MedicalReport.objects.all(), apply=apply)

        for (printed, stored, before, new_name, after), count in sorted(
            outcome.changes.items(), key=lambda item: (-item[1], item[0])
        ):
            self.stdout.write(f'{count:>5}  printed "{printed}": "{stored}" [{before}] -> "{new_name}" [{after}]')
        self.stdout.write(
            f"Checked {outcome.checked} results; {len(outcome.updated)} {'relinked' if apply else 'would change'}."
        )
        if outcome.updated and not apply:
            self.stdout.write('Dry run: nothing was saved. Run again with --apply to save these changes.')
