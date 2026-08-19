"""Build the privacy-safe one-page Treasury RMA demo input.

The repository source is a four-page scan whose first page already contains
the approved demo values.  This builder freezes the original bytes, preserves
the previous bespoke fixture, rasterizes only page 1, and places that page
beneath an ASCII provenance rail on an exact US-letter canvas.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader
from pypdfium2 import raw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parents[1]
REPOSITORY_SOURCE = REPO_ROOT / "demos" / "rma_extraction" / "data" / "rma_form.pdf"
FROZEN_SOURCE = DEMO_DIR / "source" / "rma_form.pdf"
ACTIVE_INPUT = DEMO_DIR / "data" / "mortgage-verification.pdf"
LEGACY_INPUT = DEMO_DIR / "data" / "legacy-synthetic-mortgage-verification.pdf"

ORIGINAL_SHA256 = "15ea438e22263407da910f88ac353855c205cfe4cf479ef17468cb74b683db8c"
LEGACY_SHA256 = "15f9be3fc3c78a78bb5a67e8f2b8fa0d09383626b0c2600676e2a3f95d054e77"
DERIVED_SHA256 = "2eab5c8c1c843ef5f0f0bef9e361f818369a6e5e7652f00e6e614d381a36018e"
PROVENANCE_RAIL = "AUTHENTIC PUBLIC FORM - PRIVACY-SAFE DEMO VALUES"

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
RAIL_HEIGHT = 32.0
FORM_TOP_GAP = 6.0
FORM_BOTTOM_MARGIN = 8.0
FORM_SIDE_MARGIN = 12.0
RENDER_SCALE = 1.5


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == payload:
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _require_digest(path: Path, expected: str, *, label: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"{label} must be a regular, non-symlink file")
        payload = path.read_bytes()
    except RuntimeError:
        raise
    except OSError as error:
        raise RuntimeError(f"could not read {label}: {path}") from error
    actual = _sha256(payload)
    if actual != expected:
        raise RuntimeError(
            f"{label} SHA-256 mismatch: expected {expected}, found {actual}"
        )
    return payload


def _freeze_inputs() -> None:
    source_payload = _require_digest(
        REPOSITORY_SOURCE,
        ORIGINAL_SHA256,
        label="repository Treasury RMA source",
    )
    if FROZEN_SOURCE.exists():
        _require_digest(
            FROZEN_SOURCE,
            ORIGINAL_SHA256,
            label="frozen Treasury RMA source",
        )
    else:
        _atomic_write(FROZEN_SOURCE, source_payload)

    if LEGACY_INPUT.exists():
        _require_digest(LEGACY_INPUT, LEGACY_SHA256, label="legacy bespoke fixture")
    else:
        legacy_payload = _require_digest(
            ACTIVE_INPUT,
            LEGACY_SHA256,
            label="current bespoke fixture before preservation",
        )
        _atomic_write(LEGACY_INPUT, legacy_payload)


def _render_first_page(source: Path) -> Image.Image:
    document = pdfium.PdfDocument(source)
    page = None
    bitmap = None
    try:
        if len(document) != 4:
            raise RuntimeError("the frozen Treasury RMA source must contain four pages")
        page = document[0]
        bitmap = page.render(
            scale=RENDER_SCALE,
            may_draw_forms=False,
            fill_color=(255, 255, 255, 255),
            force_bitmap_format=raw.FPDFBitmap_BGRA,
            rev_byteorder=True,
        )
        return bitmap.to_pil().convert("RGB")
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        document.close()


def _build_pdf(source: Path) -> bytes:
    image = _render_first_page(source)
    encoded_image = io.BytesIO()
    image.save(
        encoded_image,
        format="JPEG",
        quality=92,
        subsampling=0,
        optimize=False,
        progressive=False,
        dpi=(216, 216),
    )
    encoded_image.seek(0)
    form_height = PAGE_HEIGHT - RAIL_HEIGHT - FORM_TOP_GAP - FORM_BOTTOM_MARGIN
    form_width = PAGE_WIDTH - (2 * FORM_SIDE_MARGIN)
    scale = min(form_width / image.width, form_height / image.height)
    draw_width = image.width * scale
    draw_height = image.height * scale
    draw_x = (PAGE_WIDTH - draw_width) / 2
    draw_y = FORM_BOTTOM_MARGIN

    output = io.BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        bottomup=1,
        pageCompression=1,
        invariant=1,
        pdfVersion=(1, 4),
    )
    pdf.setTitle("Treasury RMA privacy-safe public-form demo")
    pdf.setAuthor("Nutrient")
    pdf.setSubject("Authentic public form with privacy-safe demo values")
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    pdf.drawImage(
        ImageReader(encoded_image),
        draw_x,
        draw_y,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        anchor="c",
        mask=None,
    )
    pdf.setFillColorRGB(0.075, 0.082, 0.092)
    pdf.rect(0, PAGE_HEIGHT - RAIL_HEIGHT, PAGE_WIDTH, RAIL_HEIGHT, stroke=0, fill=1)
    pdf.setFillColorRGB(0.97, 0.96, 0.91)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(
        PAGE_WIDTH / 2,
        PAGE_HEIGHT - 20.5,
        PROVENANCE_RAIL,
    )
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _validate_output(payload: bytes) -> None:
    reader = PdfReader(io.BytesIO(payload), strict=True)
    if len(reader.pages) != 1:
        raise RuntimeError("derived demo input must contain exactly one page")
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    if not (
        math.isclose(width, PAGE_WIDTH, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(height, PAGE_HEIGHT, rel_tol=0.0, abs_tol=1e-6)
    ):
        raise RuntimeError("derived demo input must be exactly 612x792 points")
    root = reader.trailer["/Root"]
    if "/AcroForm" in root:
        raise RuntimeError("derived demo input must not contain an AcroForm tree")
    if "/OpenAction" in root or "/AA" in root:
        raise RuntimeError("derived demo input must not contain document actions")
    names = root.get("/Names")
    if names is not None and "/JavaScript" in names.get_object():
        raise RuntimeError("derived demo input must not contain JavaScript")
    for annotation in page.get("/Annots", []):
        if annotation.get_object().get("/Subtype") == "/Widget":
            raise RuntimeError("derived demo input must not contain Widget annotations")


def main() -> int:
    _freeze_inputs()
    payload = _build_pdf(FROZEN_SOURCE)
    _validate_output(payload)
    digest = _sha256(payload)
    if digest != DERIVED_SHA256:
        raise RuntimeError(
            f"derived demo SHA-256 mismatch: expected {DERIVED_SHA256}, found {digest}"
        )
    _atomic_write(ACTIVE_INPUT, payload)
    print(f"Wrote {ACTIVE_INPUT}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
