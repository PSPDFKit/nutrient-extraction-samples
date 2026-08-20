"""Compare source-reviewed CMS-1500 ground truth and grounding with a response."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


DEMO_ROOT = Path(__file__).resolve().parent
DEFAULT_EXPECTED = DEMO_ROOT / "expected.json"
DEFAULT_RESPONSE = DEMO_ROOT / "output" / "metadata.json"


def _path(parent: str, key: str | int) -> str:
    return f"{parent}[{key}]" if isinstance(key, int) else f"{parent}.{key}"


def _has_grounding(metadata: Any, pages: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    bbox = metadata.get("bbox")
    page_index = metadata.get("pageIndex")
    if not isinstance(bbox, dict) or isinstance(page_index, bool):
        return False
    if (
        not isinstance(page_index, int)
        or not isinstance(pages, list)
        or page_index < 0
        or page_index >= len(pages)
    ):
        return False
    page = pages[page_index]
    if not isinstance(page, dict):
        return False
    dimensions: dict[str, float] = {}
    for dimension in ("width", "height"):
        value = page.get(dimension)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0:
            return False
        dimensions[dimension] = numeric
    coordinates: dict[str, float] = {}
    for coordinate in ("x", "y", "width", "height"):
        value = bbox.get(coordinate)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        numeric = float(value)
        if not math.isfinite(numeric):
            return False
        coordinates[coordinate] = numeric
    return (
        coordinates["x"] >= 0
        and coordinates["y"] >= 0
        and coordinates["width"] > 0
        and coordinates["height"] > 0
        and coordinates["x"] + coordinates["width"] <= dimensions["width"]
        and coordinates["y"] + coordinates["height"] <= dimensions["height"]
    )


def compare(
    expected: Any,
    actual: Any,
    metadata: Any,
    pages: Any,
    path: str = "$",
) -> tuple[list[str], int]:
    issues: list[str] = []
    grounded_leaves = 0

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"WRONG {path}: expected object, got {type(actual).__name__}"], 0
        actual_keys = set(actual)
        expected_keys = set(expected)
        for key in sorted(expected_keys - actual_keys):
            issues.append(f"MISSING {_path(path, key)}")
        for key in sorted(actual_keys - expected_keys):
            issues.append(f"UNEXPECTED {_path(path, key)}")
        for key in sorted(expected_keys & actual_keys):
            child_meta = metadata.get(key) if isinstance(metadata, dict) else None
            child_issues, child_grounded = compare(
                expected[key], actual[key], child_meta, pages, _path(path, key)
            )
            issues.extend(child_issues)
            grounded_leaves += child_grounded
        return issues, grounded_leaves

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"WRONG {path}: expected array, got {type(actual).__name__}"], 0
        if len(actual) < len(expected):
            for index in range(len(actual), len(expected)):
                issues.append(f"MISSING {_path(path, index)}")
        if len(actual) > len(expected):
            for index in range(len(expected), len(actual)):
                issues.append(f"UNEXPECTED {_path(path, index)}")
        metadata_items = metadata if isinstance(metadata, list) else []
        for index in range(min(len(expected), len(actual))):
            child_meta = metadata_items[index] if index < len(metadata_items) else None
            child_issues, child_grounded = compare(
                expected[index], actual[index], child_meta, pages, _path(path, index)
            )
            issues.extend(child_issues)
            grounded_leaves += child_grounded
        return issues, grounded_leaves

    if actual != expected:
        issues.append(f"WRONG {path}: expected {expected!r}, got {actual!r}")
    if not _has_grounding(metadata, pages):
        issues.append(f"UNGROUNDED {path}")
    else:
        grounded_leaves += 1
    return issues, grounded_leaves


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source_file:
        return json.load(source_file)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check source-reviewed values and grounding in a CMS-1500 response."
    )
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--response", type=Path, default=DEFAULT_RESPONSE)
    args = parser.parse_args()

    expected = _load_json(args.expected)
    response = _load_json(args.response)
    try:
        output = response["output"]
        actual = output["data"]
        metadata = output["metadata"]
        pages = output["pages"]
    except (KeyError, TypeError):
        print("WRONG $: response must contain output.data, output.metadata, and output.pages")
        return 1

    issues, grounded_leaves = compare(expected, actual, metadata, pages)
    if issues:
        print("\n".join(issues))
        return 1

    print(
        f"PASS: source-reviewed values match; "
        f"{grounded_leaves} leaves include grounding"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
