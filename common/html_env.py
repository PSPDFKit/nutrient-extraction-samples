"""Hardened Jinja environment and sink-specific coercion helpers."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup


def script_safe_json(value: Any) -> Markup:
    """Serialize JSON for a script element.

    WARNING: The returned Markup is safe only in script-element content, not in
    HTML attribute context.
    """

    serialized = (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return Markup(serialized)


def coerce_num(
    value: Any,
    kind: Literal["float", "int"] | type[float] | type[int] = "float",
) -> float | int:
    """Coerce an API-derived value to a finite float or integer."""

    if kind not in ("float", "int", float, int):
        raise ValueError("numeric coercion kind must be 'float' or 'int'")
    if isinstance(value, bool):
        raise ValueError("value must be numeric")
    if kind in ("int", int) and isinstance(value, int):
        return value

    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("value must be numeric") from None

    if not math.isfinite(normalized):
        raise ValueError("value must be finite")
    if kind in ("float", float):
        return normalized
    if not normalized.is_integer():
        raise ValueError("value must be an integer")
    return int(normalized)


def create_html_env(template_dir: str | Path) -> Environment:
    """Create an autoescaping environment for one demo template directory."""

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    environment.filters["script_safe_json"] = script_safe_json
    environment.filters["coerce_num"] = coerce_num
    environment.globals["script_safe_json"] = script_safe_json
    environment.globals["coerce_num"] = coerce_num
    return environment
