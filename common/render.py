"""PDF page rasterization helpers with deterministic PNG output."""

from __future__ import annotations

import binascii
import math
import os
import struct
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from pypdfium2 import raw

from .atomic import atomic_write

DEFAULT_SCALE = 200 / 72
MAX_RENDER_WIDTH = 10_000
# 25M pixels * 4 bytes per RGBA pixel = 100 MB for one packed bitmap;
# PDFium's bitmap plus PNG scanline/compression buffers require additional memory.
MAX_RENDER_PIXELS = 25_000_000


def _target_width(page_dims: Any) -> float | None:
    """Return a validated target width when API page dimensions provide one."""

    width: Any
    if page_dims is None:
        return None
    if isinstance(page_dims, Mapping):
        width = page_dims.get("width")
        if width is None:
            return None
    elif isinstance(page_dims, Sequence) and not isinstance(
        page_dims, (str, bytes, bytearray)
    ):
        if len(page_dims) != 2:
            raise ValueError("page_dims must contain width and height")
        width = page_dims[0]
    else:
        raise TypeError("page_dims must be a mapping or a width/height sequence")

    if isinstance(width, bool):
        raise ValueError("page width must be numeric")
    try:
        normalized = float(width)
    except (TypeError, ValueError):
        raise ValueError("page width must be numeric") from None
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError("page width must be a positive finite number")
    if normalized > MAX_RENDER_WIDTH:
        raise ValueError(f"page width must not exceed {MAX_RENDER_WIDTH} pixels")
    return normalized


def _validate_page_index(page_index: int) -> None:
    if (
        isinstance(page_index, bool)
        or not isinstance(page_index, int)
        or page_index < 0
    ):
        raise ValueError("page_index must be a non-negative integer")


def _render_geometry(
    page_width: float,
    page_height: float,
    page_dims: Any,
) -> tuple[float, tuple[int, int]]:
    if (
        not math.isfinite(page_width)
        or not math.isfinite(page_height)
        or page_width <= 0
        or page_height <= 0
    ):
        raise ValueError("PDF page dimensions must be positive finite numbers")

    target_width = _target_width(page_dims)
    scale = target_width / page_width if target_width is not None else DEFAULT_SCALE
    scaled_width = page_width * scale
    scaled_height = page_height * scale
    if (
        not math.isfinite(scale)
        or scale <= 0
        or not math.isfinite(scaled_width)
        or not math.isfinite(scaled_height)
    ):
        raise ValueError("render scale must produce positive finite dimensions")
    image_width = math.ceil(scaled_width)
    image_height = math.ceil(scaled_height)
    if image_width > MAX_RENDER_WIDTH:
        raise ValueError(f"render width must not exceed {MAX_RENDER_WIDTH} pixels")
    if image_width * image_height > MAX_RENDER_PIXELS:
        raise ValueError(
            f"rendered image must not exceed {MAX_RENDER_PIXELS} pixels"
        )
    return scale, (image_width, image_height)


def _expected_image_size(
    pdf_path: str | os.PathLike[str],
    page_index: int,
    page_dims: Any,
) -> tuple[int, int]:
    _validate_page_index(page_index)
    document = pdfium.PdfDocument(Path(pdf_path))
    page = None
    try:
        if page_index >= len(document):
            raise IndexError(
                f"page_index {page_index} is outside the PDF's {len(document)} pages"
            )
        page = document[page_index]
        _, image_size = _render_geometry(*page.get_size(), page_dims)
        return image_size
    finally:
        if page is not None:
            page.close()
        document.close()


def _rasterize_page(
    pdf_path: str | os.PathLike[str],
    page_index: int,
    page_dims: Any = None,
) -> tuple[bytes, tuple[int, int]]:
    """Render one PDF page to packed RGBA bytes."""

    _validate_page_index(page_index)

    document = pdfium.PdfDocument(Path(pdf_path))
    page = None
    bitmap = None
    try:
        if page_index >= len(document):
            raise IndexError(
                f"page_index {page_index} is outside the PDF's {len(document)} pages"
            )
        page = document[page_index]
        page_width, page_height = page.get_size()
        scale, expected_size = _render_geometry(page_width, page_height, page_dims)
        bitmap = page.render(
            scale=scale,
            fill_color=(255, 255, 255, 255),
            force_bitmap_format=raw.FPDFBitmap_BGRA,
            rev_byteorder=True,
        )
        rgba = bytes(bitmap.buffer)
        image_size = (bitmap.width, bitmap.height)
        if image_size != expected_size:
            raise ValueError("rasterized bitmap dimensions do not match the render target")
        if len(rgba) != image_size[0] * image_size[1] * 4:
            raise ValueError("rasterized bitmap is not tightly packed RGBA data")
        return rgba, image_size
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        document.close()


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _png_bytes(rgba: bytes, image_size: tuple[int, int]) -> bytes:
    """Encode packed RGBA bytes as a PNG without an imaging dependency."""

    width, height = image_size
    if width < 1 or height < 1:
        raise ValueError("image dimensions must be positive")
    row_size = width * 4
    if len(rgba) != row_size * height:
        raise ValueError("rasterized RGBA byte count does not match the image dimensions")

    scanlines = b"".join(
        b"\x00" + rgba[offset : offset + row_size]
        for offset in range(0, len(rgba), row_size)
    )
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
            ),
            _png_chunk(b"IDAT", zlib.compress(scanlines, level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as png_file:
            header = png_file.read(24)
    except OSError:
        return None
    if (
        len(header) < 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        return None
    return struct.unpack(">II", header[16:24])


def ensure_page_png(
    pdf_path: str | os.PathLike[str],
    page_index: int,
    output_path: str | os.PathLike[str],
    *,
    page_dims: Mapping[str, Any] | Sequence[Any] | None = None,
    refresh: bool = False,
) -> Path:
    """Render a page when refreshed, missing, or dimensionally stale."""

    destination = Path(output_path)
    expected_size = _expected_image_size(pdf_path, page_index, page_dims)
    if (
        destination.exists()
        and not refresh
        and _png_dimensions(destination) == expected_size
    ):
        return destination

    rgba, image_size = _rasterize_page(pdf_path, page_index, page_dims)
    atomic_write(destination, _png_bytes(rgba, image_size))
    return destination
