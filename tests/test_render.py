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


def test_existing_png_with_wrong_dimensions_is_rerendered(tmp_path: Path) -> None:
    pdf_path = tmp_path / "points.pdf"
    rendered_path = tmp_path / "stale.png"
    _one_page_pdf(pdf_path, width=72, height=36)
    rendered_path.write_bytes(COMMITTED_PNG.read_bytes())

    render.ensure_page_png(
        pdf_path,
        0,
        rendered_path,
        refresh=False,
    )

    assert _png_dimensions(rendered_path) == (200, 100)


@pytest.mark.parametrize("page_dims", [(100,), (100, 200, 300)])
def test_target_width_rejects_wrong_length_sequence(page_dims: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="width and height"):
        render._target_width(page_dims)


def test_target_width_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError, match="mapping or a width/height sequence"):
        render._target_width(100)


def test_target_width_rejects_boolean() -> None:
    with pytest.raises(ValueError, match="numeric"):
        render._target_width({"width": True})


@pytest.mark.parametrize("width", [0, -1])
def test_target_width_rejects_non_positive_value(width: int) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        render._target_width({"width": width})


@pytest.mark.parametrize("width", [float("inf"), float("-inf"), float("nan")])
def test_target_width_rejects_non_finite_value(width: float) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        render._target_width({"width": width})


@pytest.mark.parametrize("page_dims", [None, {}, {"height": 200}])
def test_target_width_returns_none_when_width_is_missing(page_dims: object) -> None:
    assert render._target_width(page_dims) is None


def test_target_width_rejects_over_cap() -> None:
    with pytest.raises(ValueError, match=str(render.MAX_RENDER_WIDTH)):
        render._target_width({"width": render.MAX_RENDER_WIDTH + 1})


def test_render_width_cap_is_enforced_directly() -> None:
    _, image_size = render._render_geometry(
        100,
        1,
        {"width": render.MAX_RENDER_WIDTH},
    )
    assert image_size == (render.MAX_RENDER_WIDTH, 100)

    with pytest.raises(ValueError, match=str(render.MAX_RENDER_WIDTH)):
        render._render_geometry(
            100,
            1,
            {"width": render.MAX_RENDER_WIDTH + 1},
        )

    with pytest.raises(ValueError, match="render width"):
        render._render_geometry(
            (render.MAX_RENDER_WIDTH / render.DEFAULT_SCALE) + 1,
            1,
            None,
        )


def test_render_pixel_cap_is_enforced_directly() -> None:
    assert render.MAX_RENDER_PIXELS == 25_000_000
    assert render.MAX_RENDER_PIXELS * 4 == 100_000_000

    _, image_size = render._render_geometry(
        100,
        25,
        {"width": render.MAX_RENDER_WIDTH},
    )
    assert image_size[0] * image_size[1] == render.MAX_RENDER_PIXELS

    with pytest.raises(ValueError, match=str(render.MAX_RENDER_PIXELS)):
        render._render_geometry(
            100,
            25.01,
            {"width": render.MAX_RENDER_WIDTH},
        )


def test_render_rejects_over_pixel_cap_before_rasterizing(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tall.pdf"
    _one_page_pdf(pdf_path, width=100, height=1_000)

    with pytest.raises(ValueError, match=str(render.MAX_RENDER_PIXELS)):
        render.ensure_page_png(
            pdf_path,
            0,
            tmp_path / "tall.png",
            page_dims={"width": render.MAX_RENDER_WIDTH},
        )

    assert not (tmp_path / "tall.png").exists()


@pytest.mark.parametrize("page_index", [-1, True, 0.0, "0", None])
def test_page_index_guard_rejects_invalid_values(page_index: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        render._validate_page_index(page_index)  # type: ignore[arg-type]


def test_page_index_guard_accepts_zero() -> None:
    render._validate_page_index(0)


@pytest.mark.parametrize("page_index", [-1, True])
def test_rasterize_rejects_invalid_page_index(
    tmp_path: Path,
    page_index: int,
) -> None:
    pdf_path = tmp_path / "one-page.pdf"
    _one_page_pdf(pdf_path, width=72, height=36)

    with pytest.raises(ValueError, match="non-negative integer"):
        render._rasterize_page(pdf_path, page_index)


def test_rasterize_rejects_out_of_range_page_index(tmp_path: Path) -> None:
    pdf_path = tmp_path / "one-page.pdf"
    _one_page_pdf(pdf_path, width=72, height=36)

    with pytest.raises(IndexError, match="outside"):
        render._rasterize_page(pdf_path, 1)


@pytest.mark.parametrize("width", ["not-a-number", object()])
def test_target_width_rejects_non_numeric_values(width: object) -> None:
    with pytest.raises(ValueError, match="numeric"):
        render._target_width({"width": width})
