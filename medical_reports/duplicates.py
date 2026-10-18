"""Noticing a report file the user has already uploaded.

Each report stores the SHA-256 of its file. The same PDF uploaded twice makes two reports with one date, so
every result in it shows twice on Health Trends. An upload whose file matches one of the user's own reports
is refused (single upload, 409) or skipped (bulk upload) and names that report, unless the request asks to
upload it anyway (allow_duplicate). Only the uploader's own reports are compared, so an upload never tells
anyone about another account's files.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .models import MedicalReport

DUPLICATE_CODE = 'duplicate_file'


def file_sha256(uploaded_file) -> str:
    """The SHA-256 of an uploaded or stored file, read in chunks and left rewound."""
    digest = hashlib.sha256()
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)
    return digest.hexdigest()


def allows_duplicate(request) -> bool:
    """Whether the upload asked to go ahead although the file is already uploaded."""
    return str(request.data.get('allow_duplicate', '')).strip().lower() in ('1', 'true', 'yes', 'on')


def duplicate_of(user, digest: str) -> MedicalReport | None:
    """The user's earliest report with this file, if any."""
    if not digest:
        return None
    return MedicalReport.objects.filter(user=user, file_sha256=digest).order_by('created_at', 'id').first()


def describe(report: MedicalReport) -> dict[str, Any]:
    return {
        'id': report.id,
        'title': report.title,
        'report_date': str(report.report_date),
        'created_at': report.created_at.isoformat(),
    }


def duplicate_message(report: MedicalReport) -> str:
    return f'This file is already uploaded as "{report.title}" (report date {report.report_date}).'
