"""
Re-score the pathology golden corpus against the current parser.

Examples:
  uv run python manage.py evaluate_golden_corpus
  uv run python manage.py evaluate_golden_corpus --codes B001,H001
  uv run python manage.py evaluate_golden_corpus --full --write samples/pathology-reports/golden/comparison-report.json
  uv run python manage.py evaluate_golden_corpus --full --compare-baseline
  USE_VLM_PARSER=true uv run python manage.py evaluate_golden_corpus --scanned --allow-vlm --compare-baseline
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management.base import BaseCommand, CommandError

from utils.golden_corpus import (
    DEFAULT_BASELINE,
    DEFAULT_GOLDEN_INDEX,
    SMOKE_REPORT_CODES,
    aggregate_floor_violations,
    evaluate_reports,
    load_baseline,
    load_golden_index,
    overall_precision,
    overall_recall,
    overall_value_accuracy,
    recall_by_vendor,
    select_reports,
    vendor_breakdown,
)
from utils.scanned_corpus import (
    DEFAULT_SCANNED_INDEX,
    load_scanned_index,
    materialize_scanned_reports,
)


class Command(BaseCommand):
    help = "Evaluate medical PDF parser recall against the golden pathology corpus"

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            help="Evaluate all reports in golden-index.json (default: smoke set)",
        )
        parser.add_argument(
            "--codes",
            type=str,
            default="",
            help="Comma-separated report_code list (overrides --full / smoke default)",
        )
        parser.add_argument(
            "--scanned",
            action="store_true",
            help=(
                "Evaluate image-only scan derivatives listed in scanned-index.json "
                "(requires --allow-vlm and a reachable OCR server)"
            ),
        )
        parser.add_argument(
            "--index",
            type=str,
            default=str(DEFAULT_GOLDEN_INDEX),
            help="Path to golden-index.json",
        )
        parser.add_argument(
            "--scanned-index",
            type=str,
            default=str(DEFAULT_SCANNED_INDEX),
            help="Path to scanned-index.json (used with --scanned)",
        )
        parser.add_argument(
            "--write",
            type=str,
            default="",
            help="Write full comparison JSON to this path",
        )
        parser.add_argument(
            "--compare-baseline",
            action="store_true",
            help=(
                "Fail if overall recall, precision, or value accuracy drops below "
                "the baseline-summary.json floors (scanned-index.json with --scanned)"
            ),
        )
        parser.add_argument(
            "--baseline",
            type=str,
            default=str(DEFAULT_BASELINE),
            help="Path to baseline-summary.json",
        )
        parser.add_argument(
            "--allow-vlm",
            action="store_true",
            help="Keep USE_VLM_PARSER from the environment (default: force off for stable scores)",
        )
        parser.add_argument(
            "--vendor-breakdown",
            action="store_true",
            help="Print report counts per source vendor folder",
        )

    def handle(self, *args, **options):
        if options["scanned"] and not options["allow_vlm"]:
            raise CommandError(
                "--scanned needs --allow-vlm: image-only scans have no text layer for the legacy parser"
            )
        if not options["allow_vlm"]:
            # Hybrid parser keys off the process env, not Django settings.
            os.environ["USE_VLM_PARSER"] = "false"
            self.stdout.write("USE_VLM_PARSER=false (pass --allow-vlm to keep env default)")

        index_path = Path(options["index"])
        try:
            index = load_golden_index(index_path)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        if options["vendor_breakdown"]:
            breakdown = vendor_breakdown(index)
            total = sum(breakdown.values())
            self.stdout.write("Vendor breakdown (golden-index.json):")
            for vendor, count in breakdown.items():
                pct = count / max(total, 1) * 100.0
                self.stdout.write(f"  {vendor}: {count} ({pct:.1f}%)")
            self.stdout.write(
                "  Vendor coverage notes: samples/pathology-reports/golden/METHODOLOGY.md"
            )
            self.stdout.write("")

        scanned_index = None
        with TemporaryDirectory() as scan_dir:
            if options["scanned"]:
                try:
                    scanned_index = load_scanned_index(Path(options["scanned_index"]))
                except FileNotFoundError as exc:
                    raise CommandError(str(exc)) from exc
                reports = materialize_scanned_reports(index, scanned_index, Path(scan_dir))
                mode = "scanned"
            elif options["codes"].strip():
                codes = [c.strip() for c in options["codes"].split(",") if c.strip()]
                reports = select_reports(index, codes)
                mode = f"codes={','.join(codes)}"
            elif options["full"]:
                reports = select_reports(index)
                mode = "full"
            else:
                reports = select_reports(index, SMOKE_REPORT_CODES)
                mode = "smoke"

            self.stdout.write(f"Evaluating {len(reports)} report(s) ({mode})…")
            result = evaluate_reports(reports)

        recall = overall_recall(result)
        precision = overall_precision(result)
        value_acc = overall_value_accuracy(result)

        self.stdout.write("")
        self.stdout.write("Summary:")
        for flag, count in sorted((result.get("summary") or {}).items()):
            self.stdout.write(f"  {flag}: {count}")
        totals = result.get("totals") or {}
        self.stdout.write(
            f"Totals: reports={totals.get('reports')} "
            f"expected={totals.get('expected_results')} "
            f"matched={totals.get('matched')} "
            f"parsed={totals.get('parsed_results')} "
            f"recall={recall:.1f}% "
            f"precision={precision:.1f}% "
            f"value_acc={value_acc:.1f}%"
        )

        if options["vendor_breakdown"]:
            self.stdout.write("")
            self.stdout.write("Recall by vendor:")
            for vendor, bucket in recall_by_vendor(index, result).items():
                self.stdout.write(
                    f"  {vendor}: {bucket['matched']}/{bucket['expected']} "
                    f"({bucket['recall_pct']}%) across {bucket['reports']} report(s)"
                )

        self.stdout.write("")
        self.stdout.write("Per-report:")
        for row in result["reports"]:
            self.stdout.write(
                f"  [{row['flag']:14s}] {row['report_code']:20s} "
                f"exp={row['expected']:3d} got={row['parsed']:3d} "
                f"match={row['matched']:3d} recall={row['recall_pct']:5.1f}% "
                f"prec={row['precision_pct']:5.1f}% "
                f"val={row['value_acc_pct']:5.1f}%"
            )

        write_path = options["write"].strip()
        if write_path:
            out = Path(write_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))

        if options["compare_baseline"]:
            if scanned_index is not None:
                floors_path = Path(options["scanned_index"])
                thresholds = scanned_index["thresholds"]
            else:
                floors_path = Path(options["baseline"])
                try:
                    thresholds = load_baseline(floors_path)["thresholds"]
                except FileNotFoundError as exc:
                    raise CommandError(str(exc)) from exc
            violations = aggregate_floor_violations(result, thresholds)
            if violations:
                raise CommandError(
                    f"Baseline check failed: {'; '.join(violations)} (see {floors_path})"
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Baseline check passed: recall {recall:.1f}%, precision {precision:.1f}%, "
                    f"value accuracy {value_acc:.1f}% meet floors in {floors_path}"
                )
            )
