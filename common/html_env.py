"""Hardened Jinja environment and sink-specific coercion helpers."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup


def script_safe_json(value: Any) -> Markup:
    """Serialize JSON that cannot terminate its containing script element."""

    serialized = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
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

    try:
        if kind in ("float", float):
            result = float(value)
        elif kind in ("int", int):
            result = int(value)
        else:
            raise ValueError("numeric coercion kind must be 'float' or 'int'")
    except (TypeError, ValueError, OverflowError):
        raise ValueError("value must be numeric") from None

    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("value must be finite")
    return result


def create_html_env(template_dir: str | Path) -> Environment:
    """Create an autoescaping environment for one demo template directory."""

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    environment.filters["script_safe_json"] = script_safe_json
    environment.filters["coerce_num"] = coerce_num
    environment.globals["script_safe_json"] = script_safe_json
    environment.globals["coerce_num"] = coerce_num
    return environment
