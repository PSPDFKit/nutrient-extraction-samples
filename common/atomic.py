"""Shared atomic file-write helper."""

from __future__ import annotations

import tempfile
from pathlib import Path


def atomic_write(destination: Path, payload: bytes) -> None:
    """Atomically replace destination with payload from its own directory."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(payload)
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
