#!/usr/bin/env python3
"""Build the deterministic privacy-safe GSA SF 91 demo fixture.

The official source remains byte-for-byte frozen under ``source/``. This
builder renders only page 1 to pixels, places that image below a provenance
rail, and paints the fixture oracle values into the matching printed fields.
The derived PDF therefore carries no XFA, AcroForm, Widget, or JavaScript
objects from the downloaded form.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from pypdfium2 import raw


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.atomic import atomic_write  # noqa: E402
from common.lighthouse import expected_json_bytes, parse_fixture  # noqa: E402


DEMO_DIR = Path(__file__).resolve().parent
SOURCE_PATH = DEMO_DIR / "source" / "SF91-20.pdf"
LEGACY_PATH = DEMO_DIR / "data" / "legacy-synthetic-insurance-claim-intake.pdf"
PDF_PATH = DEMO_DIR / "data" / "insurance-claim-intake.pdf"
FIXTURE_PATH = DEMO_DIR / "fixture.json"
EXPECTED_PATH = DEMO_DIR / "expected.json"

ORIGINAL_SHA256 = "18a11675590189964522114c294b8ea0974f86989fb7f49a31788ba2807d44ac"
LEGACY_SHA256 = "acb9970d933b9b1af6d9b8c08c3843006f09e8d574f07ea0b29cf51c27e2ca33"

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
RAIL_HEIGHT = 28.0
FORM_SCALE = (PAGE_HEIGHT - RAIL_HEIGHT) / PAGE_HEIGHT
FORM_X = (PAGE_WIDTH - PAGE_WIDTH * FORM_SCALE) / 2.0
RASTER_SCALE = 3.0


@dataclass(frozen=True)
class FieldSpec:
    path: tuple[str, ...]
    label: str
    value: str
    # Exact page-1 Widget rectangle from the downloaded SF 91, in PDF points.
    rect: tuple[float, float, float, float]
    font_size: float = 8.25
    top_aligned: bool = False


FIELDS = (
    FieldSpec(
        ("crash", "date"),
        "Crash date",
        "08/03/2026",
        (484.458, 676.459, 575.924, 688.450),
    ),
    FieldSpec(
        ("federal_vehicle", "driver_name"),
        "Federal vehicle driver name",
        "Alvarez, Noah",
        (27.000, 675.723, 297.850, 688.479),
    ),
    FieldSpec(
        ("federal_vehicle", "tag_id"),
        "Federal vehicle tag or identification number",
        "GSA-48312",
        (27.000, 626.201, 169.622, 638.957),
    ),
    FieldSpec(
        ("federal_vehicle", "estimated_repair_cost"),
        "Federal vehicle estimated repair cost",
        "2750.00",
        (184.207, 626.201, 273.768, 638.957),
    ),
    FieldSpec(
        ("federal_vehicle", "year"),
        "Federal vehicle year",
        "2023",
        (276.766, 626.201, 352.542, 638.957),
    ),
    FieldSpec(
        ("federal_vehicle", "make"),
        "Federal vehicle make",
        "Subaru",
        (355.263, 626.201, 422.784, 638.957),
    ),
    FieldSpec(
        ("federal_vehicle", "model"),
        "Federal vehicle model",
        "Outback",
        (425.384, 626.201, 492.568, 638.957),
    ),
    FieldSpec(
        ("federal_vehicle", "damage"),
        "Federal vehicle damage description",
        "Rear bumper and liftgate dented; vehicle remains drivable.",
        (27.000, 604.460, 585.071, 617.216),
        font_size=7.25,
    ),
    FieldSpec(
        ("other_vehicle", "driver_name"),
        "Other vehicle driver name",
        "Chen, Maya",
        (27.000, 554.230, 250.937, 566.986),
    ),
    FieldSpec(
        ("other_vehicle", "insurance", "company"),
        "Other vehicle driver's insurance company",
        "Prairie Mutual Insurance",
        (27.000, 407.651, 421.761, 443.991),
        top_aligned=True,
    ),
    FieldSpec(
        ("other_vehicle", "insurance", "policy_number"),
        "Other vehicle driver's insurance policy number",
        "PN-84-221907",
        (424.814, 431.206, 585.828, 443.962),
    ),
)


class FixtureBuildError(RuntimeError):
    """Raised when a frozen source or generated artifact violates the contract."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_frozen(path: Path, *, expected_sha256: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FixtureBuildError(f"{label} must be a regular, non-symlink file")
    payload = path.read_bytes()
    if _sha256(payload) != expected_sha256:
        raise FixtureBuildError(f"{label} does not match its frozen SHA-256")
    return payload


def _pdf_number(value: float) -> str:
    if not math.isfinite(value):
        raise FixtureBuildError("PDF coordinates must be finite")
    rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _pdf_text(value: str) -> str:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise FixtureBuildError("fixture PDF text must be ASCII") from None
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_page_one(source: Path) -> tuple[bytes, int, int]:
    document = pdfium.PdfDocument(source)
    page = None
    bitmap = None
    try:
        if len(document) != 5:
            raise FixtureBuildError(
                "frozen SF 91 source must contain exactly five pages"
            )
        page = document[0]
        width, height = page.get_size()
        if not (
            math.isclose(width, PAGE_WIDTH, rel_tol=0.0, abs_tol=1e-6)
            and math.isclose(height, PAGE_HEIGHT, rel_tol=0.0, abs_tol=1e-6)
        ):
            raise FixtureBuildError("SF 91 page 1 must be exactly 612x792 points")
        bitmap = page.render(
            scale=RASTER_SCALE,
            may_draw_forms=False,
            fill_color=(255, 255, 255, 255),
            force_bitmap_format=raw.FPDFBitmap_BGRA,
            rev_byteorder=True,
        )
        rgba = bytes(bitmap.buffer)
        image_width = bitmap.width
        image_height = bitmap.height
        if len(rgba) != image_width * image_height * 4:
            raise FixtureBuildError("SF 91 raster buffer is not tightly packed RGBA")
        rgb = bytearray(image_width * image_height * 3)
        rgb[0::3] = rgba[0::4]
        rgb[1::3] = rgba[1::4]
        rgb[2::3] = rgba[2::4]
        return bytes(rgb), image_width, image_height
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        document.close()


def _field_baseline(field: FieldSpec) -> tuple[float, float]:
    x0, y0, _x1, y1 = field.rect
    source_y = y1 - field.font_size - 3.0 if field.top_aligned else y0 + 2.45
    return (
        FORM_X + FORM_SCALE * (x0 + 2.5),
        FORM_SCALE * source_y,
    )


def _field_box(field: FieldSpec) -> dict[str, Any]:
    x0, y0, x1, y1 = field.rect
    return {
        "pageIndex": 0,
        "bbox": {
            "x": round(FORM_X + FORM_SCALE * x0, 2),
            "y": round(PAGE_HEIGHT - FORM_SCALE * y1, 2),
            "width": round(FORM_SCALE * (x1 - x0), 2),
            "height": round(FORM_SCALE * (y1 - y0), 2),
        },
    }


def _content_stream() -> bytes:
    commands = [
        "q",
        (
            f"{_pdf_number(PAGE_WIDTH * FORM_SCALE)} 0 0 "
            f"{_pdf_number(PAGE_HEIGHT * FORM_SCALE)} {_pdf_number(FORM_X)} 0 cm"
        ),
        "/Im0 Do",
        "Q",
        "0.035 0.184 0.271 rg",
        f"0 {_pdf_number(PAGE_HEIGHT - RAIL_HEIGHT)} {_pdf_number(PAGE_WIDTH)} {_pdf_number(RAIL_HEIGHT)} re f",
        "BT",
        "/F2 9.2 Tf",
        "1 1 1 rg",
        "18 774.2 Td",
        f"({_pdf_text('AUTHENTIC PUBLIC FORM - PRIVACY-SAFE DEMO VALUES')}) Tj",
        "ET",
        "0.024 0.282 0.431 rg",
    ]
    for field in FIELDS:
        x, y = _field_baseline(field)
        commands.extend(
            [
                "BT",
                f"/F2 {_pdf_number(field.font_size * FORM_SCALE)} Tf",
                f"{_pdf_number(x)} {_pdf_number(y)} Td",
                f"({_pdf_text(field.value)}) Tj",
                "ET",
            ]
        )
    return ("\n".join(commands) + "\n").encode("ascii")


def _assemble_pdf(image_rgb: bytes, image_width: int, image_height: int) -> bytes:
    compressed_image = zlib.compress(image_rgb, level=9)
    content = _content_stream()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/CropBox [0 0 612 792] /Resources << "
            b"/XObject << /Im0 4 0 R >> /Font << /F1 5 0 R /F2 6 0 R >> >> "
            b"/Contents 7 0 R >>"
        ),
        (
            f"<< /Type /XObject /Subtype /Image /Width {image_width} "
            f"/Height {image_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
            f"/Filter /FlateDecode /Length {len(compressed_image)} >>\nstream\n"
        ).encode("ascii")
        + compressed_image
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length "
        + str(len(content)).encode("ascii")
        + b" >>\nstream\n"
        + content
        + b"endstream",
    ]
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{object_number} 0 obj\n".encode("ascii"))
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(payload)


def _fixture_payload(source_sha256: str) -> dict[str, Any]:
    return {
        "version": 2,
        "slug": "insurance_claim_intake",
        "sourceStatus": "public-form-demo",
        "document": {
            "filename": "data/insurance-claim-intake.pdf",
            "title": "GSA STANDARD FORM 91 - MOTOR VEHICLE ACCIDENT (CRASH) REPORT",
            "subtitle": "Authentic public form with privacy-safe demo values - not customer claim data",
            "width": PAGE_WIDTH,
            "height": PAGE_HEIGHT,
        },
        "provenance": {
            "publisher": "U.S. General Services Administration",
            "officialFormName": "Standard Form 91, Motor Vehicle Accident (Crash) Report, revision 09/2020",
            "canonicalSourceUrl": "https://www.gsa.gov/system/files/SF91-20.pdf",
            "originalSha256": ORIGINAL_SHA256,
            "sourceSha256": source_sha256,
        },
        "fields": [
            {
                "path": list(field.path),
                "label": field.label,
                "value": field.value,
                "source": _field_box(field),
            }
            for field in FIELDS
        ],
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def _check_bytes(path: Path, expected: bytes) -> None:
    if path.is_symlink() or not path.is_file():
        raise FixtureBuildError(f"generated artifact is missing: {path}")
    if path.read_bytes() != expected:
        raise FixtureBuildError(f"generated artifact is stale: {path}")


def build(*, check: bool) -> str:
    _read_frozen(
        SOURCE_PATH, expected_sha256=ORIGINAL_SHA256, label="official SF 91 source"
    )
    _read_frozen(
        LEGACY_PATH, expected_sha256=LEGACY_SHA256, label="legacy synthetic fixture"
    )
    image_rgb, image_width, image_height = _render_page_one(SOURCE_PATH)
    pdf_payload = _assemble_pdf(image_rgb, image_width, image_height)
    derived_sha256 = _sha256(pdf_payload)
    fixture_value = _fixture_payload(derived_sha256)
    fixture = parse_fixture(fixture_value, expected_slug="insurance_claim_intake")
    fixture_payload = _json_bytes(fixture_value)
    expected_payload = expected_json_bytes(fixture)

    if check:
        _check_bytes(PDF_PATH, pdf_payload)
        _check_bytes(FIXTURE_PATH, fixture_payload)
        _check_bytes(EXPECTED_PATH, expected_payload)
    else:
        atomic_write(PDF_PATH, pdf_payload)
        atomic_write(FIXTURE_PATH, fixture_payload)
        atomic_write(EXPECTED_PATH, expected_payload)
    return derived_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the derived PDF, fixture, and oracle byte-for-byte without writing.",
    )
    args = parser.parse_args(argv)
    try:
        digest = build(check=args.check)
    except (FixtureBuildError, OSError, RuntimeError, ValueError) as error:
        print(f"fixture build failed: {error}", file=sys.stderr)
        return 1
    action = "Verified" if args.check else "Built"
    print(f"{action} deterministic GSA SF 91 demo input: {digest}")
    print(f"{action} {FIXTURE_PATH.relative_to(REPO_ROOT)}")
    print(f"{action} {EXPECTED_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
