"""
Scanned-report derivatives of the golden pathology corpus.

The corpus has no real scanned or photographed reports yet, so selected golden PDFs are
rendered to image-only PDFs (no text layer) at evaluation time and scored against the
same reviewed expected results. The derivatives are deterministic and never committed.

Used by:
- `utils.tests_golden_corpus` (image-only sanity checks and the opt-in OCR gate)
- `manage.py evaluate_golden_corpus --scanned`
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image, ImageEnhance, ImageFilter

from utils.golden_corpus import REPO_ROOT, repo_path, select_reports

DEFAULT_SCANNED_INDEX = REPO_ROOT / "samples/pathology-reports/golden/scanned-index.json"


@dataclass(frozen=True)
class ScanVariant:
    name: str
    dpi: int
    grayscale: bool = False
    contrast: float = 1.0
    rotate_degrees: float = 0.0
    blur_radius: float = 0.0
    jpeg_quality: int | None = None


SCAN_VARIANTS = {
    # Flatbed-quality scan: full colour, straight, sharp.
    "clean": ScanVariant("clean", dpi=200),
    # Phone photo of a printout: lower resolution, washed out, tilted, soft, compressed.
    "phone": ScanVariant(
        "phone",
        dpi=150,
        grayscale=True,
        contrast=0.85,
        rotate_degrees=1.5,
        blur_radius=0.6,
        jpeg_quality=55,
    ),
}


def load_scanned_index(path: Path | None = None) -> dict[str, Any]:
    index_path = path or DEFAULT_SCANNED_INDEX
    if not index_path.is_file():
        raise FileNotFoundError(f"Scanned index not found: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def _degrade(image: Image.Image, variant: ScanVariant) -> Image.Image:
    image = image.convert("L" if variant.grayscale else "RGB").convert("RGB")
    if variant.contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(variant.contrast)
    if variant.rotate_degrees:
        image = image.rotate(
            variant.rotate_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor="white",
        )
    if variant.blur_radius:
        image = image.filter(ImageFilter.GaussianBlur(variant.blur_radius))
    if variant.jpeg_quality is not None:
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=variant.jpeg_quality)
        image = Image.open(BytesIO(buffer.getvalue()))
        image.load()
    return image


def rasterize_pdf(source: Path, variant: ScanVariant) -> bytes:
    """Render every page of a PDF to an image and rebuild it as an image-only PDF."""
    document = pdfium.PdfDocument(str(source))
    try:
        pages = [
            _degrade(document[i].render(scale=variant.dpi / 72.0).to_pil(), variant)
            for i in range(len(document))
        ]
    finally:
        document.close()
    buffer = BytesIO()
    pages[0].save(
        buffer,
        format="PDF",
        resolution=float(variant.dpi),
        save_all=True,
        append_images=pages[1:],
    )
    return buffer.getvalue()


def materialize_scanned_reports(
    golden_index: dict[str, Any],
    scanned_index: dict[str, Any],
    out_dir: Path,
) -> list[dict[str, Any]]:
    """
    Write scan derivatives into `out_dir` and return golden-shaped report entries.

    Each entry keeps its source report's expected results under a `<code>@<variant>`
    report code. `source_pdf` is the derivative's absolute path, which `repo_path()`
    returns unchanged, so the entries score with `evaluate_reports()` as-is.
    """
    variants = [SCAN_VARIANTS[name] for name in scanned_index.get("variants") or []]
    codes = [row["report_code"] for row in scanned_index.get("reports") or []]
    entries: list[dict[str, Any]] = []
    for golden in select_reports(golden_index, codes):
        for variant in variants:
            code = f"{golden['report_code']}@{variant.name}"
            path = out_dir / f"{code}.pdf"
            path.write_bytes(rasterize_pdf(repo_path(golden["source_pdf"]), variant))
            entries.append(
                {
                    **golden,
                    "report_code": code,
                    "source_pdf": str(path),
                    "derived_from": golden["source_pdf"],
                    "scan_variant": variant.name,
                }
            )
    return entries
