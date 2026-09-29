"""Small, dependency-free checks for user-supplied medical documents."""

from __future__ import annotations

from pathlib import Path


DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _head(uploaded_file, length: int = 1024) -> bytes:
    position = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else 0
    uploaded_file.seek(0)
    value = uploaded_file.read(length)
    uploaded_file.seek(position)
    return bytes(value)


def validate_medical_upload(uploaded_file, *, prescription: bool = False) -> None:
    """Reject oversized files and content that does not match its allowed extension.

    This is deliberately a signature check, not a claim that the document itself is safe or valid;
    parsers still run outside the request in a worker.
    """
    if uploaded_file.size > DEFAULT_MAX_UPLOAD_BYTES:
        raise ValueError('The file is larger than the 100 MB upload limit.')

    suffix = Path(uploaded_file.name).suffix.casefold()
    head = _head(uploaded_file)
    if suffix == '.pdf':
        if b'%PDF-' not in head:
            raise ValueError('The uploaded file is not a valid PDF.')
        return
    if not prescription:
        raise ValueError('Only PDF files are supported.')

    signatures = {
        '.jpg': head.startswith(b'\xff\xd8\xff'),
        '.jpeg': head.startswith(b'\xff\xd8\xff'),
        '.png': head.startswith(b'\x89PNG\r\n\x1a\n'),
        '.webp': head.startswith(b'RIFF') and head[8:12] == b'WEBP',
        '.bmp': head.startswith(b'BM'),
        '.tif': head.startswith((b'II*\x00', b'MM\x00*')),
        '.tiff': head.startswith((b'II*\x00', b'MM\x00*')),
        '.heic': head[4:8] == b'ftyp' and head[8:12] in (b'heic', b'heix', b'hevc', b'hevx', b'mif1'),
        '.heif': head[4:8] == b'ftyp' and head[8:12] in (b'heif', b'heim', b'mif1', b'msf1', b'heic'),
    }
    if not signatures.get(suffix, False):
        raise ValueError('The uploaded file content does not match its extension.')
