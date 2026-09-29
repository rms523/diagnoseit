"""
Pluggable report formats: layout-specific parsers that run alongside the generic text parser.

A report format recognises one laboratory's layout from the report text and reads its results.
Formats are discovered from two places, so they can be added without editing the parser:

- every ``*.py`` file in ``REPORT_FORMATS_DIR`` (default ``report_formats/`` at the repository root,
  mounted at ``/app/report_formats`` in Docker), skipping files that start with ``_``;
- the dotted module paths in ``REPORT_FORMATS`` (comma-separated), for formats installed as packages.

A module registers formats with the ``@register`` decorator::

    from utils.report_formats import ReportFormat, ReportRow, register

    @register
    class AcmeLabs(ReportFormat):
        name = "acme-labs"
        def matches(self, text):
            return "ACME LABORATORIES" in text
        def parse(self, text):
            return [ReportRow(test_name="Hemoglobin", value="13.5", unit="g/dL", reference_range="13-17")]

Any number of formats can be installed. For each report, every format whose ``matches()`` is true
runs, highest ``priority`` first. The first ``REPLACE`` format that returns rows supplies the report's
results in place of the generic parser's; ``SUPPLEMENT`` formats add their rows to whichever result
wins. A format that raises is logged and skipped, so a broken format never stops a report from parsing.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

REPLACE = "replace"
SUPPLEMENT = "supplement"

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ReportRow:
    """One result as printed on the report. The catalog link is worked out from ``test_name`` later."""

    test_name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    # NORMAL, HIGH, LOW, or ABNORMAL; left blank, it is worked out from the value and reference range.
    status: str = ""
    # Section the row was printed in when that changes its meaning: "urine", "dlc", or "alc".
    section: str = ""


class ReportFormat:
    """Base class for a report format. Subclass it, set ``name``, and implement both methods."""

    name: str = ""
    priority: int = 0
    mode: str = REPLACE

    def matches(self, text: str) -> bool:
        """Whether this report is in this format. ``text`` is the PDF's extracted text."""
        raise NotImplementedError

    def parse(self, text: str) -> list[ReportRow]:
        """Every result in the report."""
        raise NotImplementedError


_registered: list[type[ReportFormat]] = []
_loaded: list[ReportFormat] | None = None


def register(cls: type[ReportFormat]) -> type[ReportFormat]:
    """Class decorator that makes a report format available to the parser."""
    if not (isinstance(cls, type) and issubclass(cls, ReportFormat)):
        raise TypeError(f"{cls!r} is not a ReportFormat subclass")
    if not cls.name:
        raise ValueError(f"{cls.__name__} needs a name")
    if cls.mode not in (REPLACE, SUPPLEMENT):
        raise ValueError(f"{cls.__name__}.mode must be REPLACE or SUPPLEMENT")
    if cls not in _registered:
        _registered.append(cls)
    return cls


def _formats_dir() -> Path:
    return Path(os.getenv("REPORT_FORMATS_DIR") or REPO_ROOT / "report_formats")


def _import_plugins() -> None:
    directory = _formats_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module_name = f"report_formats_plugin_{path.stem}"
            loaded = sys.modules.get(module_name)
            if loaded is not None and getattr(loaded, "__file__", None) == str(path):
                # Imported before: register its formats again instead of re-running the file.
                for value in vars(loaded).values():
                    if isinstance(value, type) and issubclass(value, ReportFormat) and value.name and value.__module__ == module_name:
                        register(value)
                continue
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                sys.modules[module_name] = module
            except Exception:
                logger.exception("Could not load report format file %s", path)
    for dotted in filter(None, (m.strip() for m in os.getenv("REPORT_FORMATS", "").split(","))):
        try:
            importlib.import_module(dotted)
        except Exception:
            logger.exception("Could not load report format module %s", dotted)


def installed_formats() -> list[ReportFormat]:
    """Every registered format, highest priority first. Plugins are imported on first use."""
    global _loaded
    if _loaded is None:
        _import_plugins()
        names: set[str] = set()
        formats = []
        for cls in _registered:
            if cls.name in names:
                logger.warning("Ignoring report format %s: the name %r is already registered", cls.__name__, cls.name)
                continue
            names.add(cls.name)
            formats.append(cls())
        _loaded = sorted(formats, key=lambda f: -f.priority)
        if _loaded:
            logger.info("Report formats: %s", ", ".join(f.name for f in _loaded))
    return _loaded


def reset_formats() -> None:
    """Forget loaded formats so the next report re-discovers them (used by tests)."""
    global _loaded
    _loaded = None


def apply_report_formats(
    text: str,
    generic_rows: list[dict],
    to_parser_row: Callable[[ReportRow, str], dict],
    formats: Iterable[ReportFormat] | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Combine the generic parser's rows with those of every matching format.

    Returns the rows and the names of the formats that contributed to them.
    """
    replacement: list[dict] | None = None
    supplements: list[dict] = []
    used: list[str] = []
    for fmt in installed_formats() if formats is None else formats:
        if replacement is not None and fmt.mode == REPLACE:
            continue
        try:
            if not fmt.matches(text):
                continue
            rows = [to_parser_row(row, fmt.name) for row in fmt.parse(text) or []]
        except Exception:
            logger.exception("Report format %s failed; continuing without it", fmt.name)
            continue
        if not rows:
            continue
        used.append(fmt.name)
        if fmt.mode == REPLACE:
            replacement = rows
        else:
            supplements.extend(rows)

    if not used:
        return generic_rows, []
    combined = list(generic_rows if replacement is None else replacement)
    seen = {_row_key(row) for row in combined}
    for row in supplements:
        if _row_key(row) not in seen:
            seen.add(_row_key(row))
            combined.append(row)
    return combined, used


def _row_key(row: dict) -> tuple[str, str, str]:
    name = str(row.get("raw_test_name") or row.get("test_name") or "").strip().lower()
    return name, str(row.get("section_context") or ""), str(row.get("value") or "").strip()
