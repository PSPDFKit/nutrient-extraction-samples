"""Build the deterministic, flattened CMS public-form demo input.

The downloaded CMS PDF remains unchanged under ``source/``. This builder keeps
page 1 as vector content, scales it just enough to reserve a top provenance
rail, and overlays only the privacy-safe values approved for the demo.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas


DEMO_DIR = Path(__file__).resolve().parent
ORIGINAL = DEMO_DIR / "source" / "cms-glp-1-bridge-original.pdf"
OUTPUT = DEMO_DIR / "data" / "prior-authorization.pdf"

ORIGINAL_SHA256 = "c223dc0f6acaf1d7b7e345bdf968ba2373ce94b39994b006a1e9915a07768fa0"
DERIVED_SHA256 = "18bb2e0c4419c0c2acb002acb0b4857efacc7e96f37d15decebfe06d3394d530"
PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
FORM_SCALE = 0.96
FORM_X = (PAGE_WIDTH - PAGE_WIDTH * FORM_SCALE) / 2
FORM_Y = 0.0
TOP_GAP = PAGE_HEIGHT - (PAGE_HEIGHT * FORM_SCALE + FORM_Y)

PROVENANCE_RAIL = "AUTHENTIC PUBLIC FORM - PRIVACY-SAFE DEMO VALUES"
INK = (24 / 255, 52 / 255, 91 / 255)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_frozen(path: Path, *, expected_sha256: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular, non-symlink file")
    payload = path.read_bytes()
    actual = _sha256(payload)
    if actual != expected_sha256:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, found {actual}"
        )
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and not path.is_symlink() and path.read_bytes() == payload:
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


def _final_x(original_x: float) -> float:
    return FORM_X + original_x * FORM_SCALE


def _final_y_from_top(original_baseline_top: float) -> float:
    return PAGE_HEIGHT - (TOP_GAP + original_baseline_top * FORM_SCALE)


def _draw_value(
    canvas: Canvas,
    value: str,
    *,
    x: float,
    baseline_top: float,
    size: float = 8.5,
    max_width: float | None = None,
) -> None:
    if max_width is not None and stringWidth(value, "Helvetica-Bold", size) > max_width:
        raise ValueError(f"demo value does not fit its printed field: {value!r}")
    canvas.setFont("Helvetica-Bold", size)
    canvas.setFillColorRGB(*INK)
    canvas.drawString(_final_x(x), _final_y_from_top(baseline_top), value)


def _draw_x(canvas: Canvas, *, x: float, top: float, size: float = 6.0) -> None:
    """Draw a centered vector X inside an existing printed checkbox."""

    left = _final_x(x)
    upper = PAGE_HEIGHT - (TOP_GAP + top * FORM_SCALE)
    canvas.setStrokeColorRGB(*INK)
    canvas.setLineWidth(1.0)
    canvas.line(left, upper, left + size, upper - size)
    canvas.line(left, upper - size, left + size, upper)


def _overlay_pdf() -> BytesIO:
    payload = BytesIO()
    canvas = Canvas(
        payload,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        invariant=1,
        pageCompression=1,
    )

    # The rail occupies only the space created above the scaled original page.
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(0, PAGE_HEIGHT - TOP_GAP, PAGE_WIDTH, TOP_GAP, fill=1, stroke=0)
    canvas.setStrokeColorRGB(0.72, 0.74, 0.78)
    canvas.setLineWidth(0.6)
    canvas.line(18, PAGE_HEIGHT - TOP_GAP + 1.5, PAGE_WIDTH - 18, PAGE_HEIGHT - TOP_GAP + 1.5)
    canvas.setFillColorRGB(0.16, 0.18, 0.22)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 18.5, PROVENANCE_RAIL)

    _draw_value(canvas, "Elena Brooks", x=101, baseline_top=194.5, max_width=190)
    _draw_value(canvas, "DEMO-MBI-771204", x=147, baseline_top=222.0, max_width=145)
    _draw_value(canvas, "04/18/1987", x=123, baseline_top=237.0, max_width=170)
    _draw_value(
        canvas,
        "742 Demo Street, Austin, TX 78745",
        x=84,
        baseline_top=252.0,
        size=7.8,
        max_width=210,
    )

    _draw_value(canvas, "Priya Raman, MD", x=392, baseline_top=194.5, max_width=188)
    _draw_value(canvas, "(555) 470-2200", x=350, baseline_top=226.0, max_width=225)
    _draw_value(canvas, "1234567890", x=341, baseline_top=255.0, max_width=92)

    # Replace the selected printed drug option so its visible oracle text is
    # exactly the approved value (without the publisher's registration mark).
    drug_left = _final_x(34)
    drug_top = TOP_GAP + 338.0 * FORM_SCALE
    drug_width = 112 * FORM_SCALE
    drug_height = 22 * FORM_SCALE
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(
        drug_left,
        PAGE_HEIGHT - drug_top - drug_height,
        drug_width,
        drug_height,
        fill=1,
        stroke=0,
    )
    canvas.setStrokeColorRGB(0.25, 0.27, 0.31)
    canvas.setLineWidth(0.7)
    box_x = _final_x(36)
    box_y = PAGE_HEIGHT - (TOP_GAP + 344.0 * FORM_SCALE) - 7.5
    canvas.rect(box_x, box_y, 7.5, 7.5, fill=0, stroke=1)
    _draw_x(canvas, x=36.8, top=345.0, size=5.8)
    _draw_value(canvas, "Wegovy Injection", x=47, baseline_top=352.8, size=8.2, max_width=95)

    _draw_x(canvas, x=60.7, top=513.8)
    _draw_x(canvas, x=326.1, top=578.4)
    _draw_x(canvas, x=326.1, top=654.5)

    canvas.showPage()
    canvas.save()
    payload.seek(0)
    return payload


def _build_payload() -> bytes:
    _read_frozen(
        ORIGINAL,
        expected_sha256=ORIGINAL_SHA256,
        label="official CMS source",
    )

    source_reader = PdfReader(ORIGINAL)
    if len(source_reader.pages) != 3:
        raise ValueError("official CMS source must contain exactly three pages")
    source_page = deepcopy(source_reader.pages[0])
    if float(source_page.mediabox.width) != PAGE_WIDTH or float(source_page.mediabox.height) != PAGE_HEIGHT:
        raise ValueError("official CMS page 1 must be exactly 612x792 points")
    source_page.pop(NameObject("/Annots"), None)

    page = PageObject.create_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.merge_transformed_page(
        source_page,
        Transformation().scale(FORM_SCALE).translate(FORM_X, FORM_Y),
        over=True,
        expand=False,
    )
    overlay_reader = PdfReader(_overlay_pdf())
    page.merge_page(overlay_reader.pages[0], over=True, expand=False)
    page.pop(NameObject("/Annots"), None)

    writer = PdfWriter()
    writer.add_page(page)
    writer.metadata = None
    writer.add_metadata(
        {
            "/Title": "CMS GLP-1 Bridge Prior Authorization Request Form - Privacy-Safe Demo",
            "/Author": "Centers for Medicare & Medicaid Services",
            "/Subject": "Authentic public form with privacy-safe demo values",
            "/Creator": "Nutrient deterministic public-form fixture builder",
            "/Producer": "pypdf",
        }
    )
    writer.root_object.pop(NameObject("/AcroForm"), None)

    payload = BytesIO()
    writer.write(payload)
    return payload.getvalue()


def _validate_output(payload: bytes) -> None:
    reopened = PdfReader(BytesIO(payload), strict=True)
    if len(reopened.pages) != 1:
        raise ValueError("derived demo PDF must contain exactly one page")
    if reopened.get_fields():
        raise ValueError("derived demo PDF must not contain AcroForm fields")
    if "/AcroForm" in reopened.trailer["/Root"]:
        raise ValueError("derived demo PDF must not contain an AcroForm tree")
    widgets = [
        annotation
        for annotation in reopened.pages[0].get("/Annots", [])
        if annotation.get_object().get("/Subtype") == "/Widget"
    ]
    if widgets:
        raise ValueError("derived demo PDF must not contain Widget annotations")
    if float(reopened.pages[0].mediabox.width) != PAGE_WIDTH or float(reopened.pages[0].mediabox.height) != PAGE_HEIGHT:
        raise ValueError("derived demo PDF must remain exactly 612x792 points")


def build(*, check: bool) -> str:
    payload = _build_payload()
    _validate_output(payload)
    digest = _sha256(payload)
    if digest != DERIVED_SHA256:
        raise ValueError(
            f"derived demo SHA-256 mismatch: expected {DERIVED_SHA256}, found {digest}"
        )

    if check:
        _read_frozen(
            OUTPUT,
            expected_sha256=DERIVED_SHA256,
            label="committed derived demo",
        )
        if OUTPUT.read_bytes() != payload:
            raise ValueError("committed derived demo bytes are stale")
    else:
        _atomic_write(OUTPUT, payload)
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the deterministic derived PDF byte-for-byte without writing.",
    )
    args = parser.parse_args(argv)
    try:
        digest = build(check=args.check)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"public-form build failed: {error}", file=sys.stderr)
        return 1
    action = "Verified" if args.check else "Built"
    print(f"{action} deterministic CMS public-form demo: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
