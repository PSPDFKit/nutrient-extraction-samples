"""Build the deterministic, flattened CMS public-form demo input.

The downloaded CMS PDF remains unchanged under ``source/``. This builder keeps
page 1 as vector content, scales it just enough to reserve a top provenance
rail, and overlays only the privacy-safe values approved for the demo.
"""

from __future__ import annotations

import hashlib
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
PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
FORM_SCALE = 0.96
FORM_X = (PAGE_WIDTH - PAGE_WIDTH * FORM_SCALE) / 2
FORM_Y = 0.0
TOP_GAP = PAGE_HEIGHT - (PAGE_HEIGHT * FORM_SCALE + FORM_Y)

PROVENANCE_RAIL = "AUTHENTIC PUBLIC FORM - PRIVACY-SAFE DEMO VALUES"
INK = (24 / 255, 52 / 255, 91 / 255)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def build() -> str:
    if _sha256(ORIGINAL) != ORIGINAL_SHA256:
        raise ValueError("official CMS source hash does not match the approved source")

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

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".pdf.tmp")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(OUTPUT)

    reopened = PdfReader(OUTPUT)
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
    return _sha256(OUTPUT)


if __name__ == "__main__":
    print(build())
