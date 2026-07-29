import struct
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from common import render

REPO_ROOT = Path(__file__).resolve().parents[1]
GROUNDED_PDF = REPO_ROOT / "demos/grounded_extraction/data/CMS-1500.pdf"
COMMITTED_PNG = (
    REPO_ROOT / "demos/grounded_extraction/output/cms_1500_page_0.png"
)


def _png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG with an IHDR first chunk")
    return struct.unpack(">II", payload[16:24])


def _one_page_pdf(path: Path, width: float, height: float) -> None:
    document = pdfium.PdfDocument.new()
    page = None
    try:
        page = document.new_page(width, height)
        page.close()
        page = None
        document.save(path)
    finally:
        if page is not None:
            page.close()
        document.close()


def test_grounded_page_matches_committed_png_dimensions(tmp_path: Path) -> None:
    rendered_path = tmp_path / "grounded.png"

    result = render.ensure_page_png(
        GROUNDED_PDF,
        0,
        rendered_path,
        page_dims={"width": 1700, "height": 2200},
    )

    assert result == rendered_path
    assert _png_dimensions(rendered_path) == _png_dimensions(COMMITTED_PNG)
    assert _png_dimensions(rendered_path) == (1700, 2200)


def test_missing_api_dimensions_use_200_dpi_scale(tmp_path: Path) -> None:
    pdf_path = tmp_path / "points.pdf"
    rendered_path = tmp_path / "points.png"
    _one_page_pdf(pdf_path, width=72, height=36)

    render.ensure_page_png(pdf_path, 0, rendered_path)

    assert _png_dimensions(rendered_path) == (200, 100)


def test_existing_png_is_untouched_without_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered_path = tmp_path / "existing.png"
    rendered_path.write_bytes(COMMITTED_PNG.read_bytes())
    original_bytes = rendered_path.read_bytes()
    original_mtime = rendered_path.stat().st_mtime_ns

    def fail_rasterize(
        *_args: object, **_kwargs: object
    ) -> tuple[bytes, tuple[int, int]]:
        raise AssertionError("replay mode must not rasterize an existing PNG")

    monkeypatch.setattr(render, "_rasterize_page", fail_rasterize)

    result = render.ensure_page_png(
        GROUNDED_PDF,
        0,
        rendered_path,
        page_dims=(1700, 2200),
        refresh=False,
    )

    assert result == rendered_path
    assert rendered_path.read_bytes() == original_bytes
    assert rendered_path.stat().st_mtime_ns == original_mtime
