"""Seed deterministic, committed cache entries from the demos' response fixtures."""

from __future__ import annotations

import json
import math
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from common.api import (  # noqa: E402
    EXTRACT_ENDPOINT,
    EXTRACT_URL,
    PARSE_ENDPOINT,
    PARSE_URL,
    build_extract_instructions,
    build_parse_instructions,
)
from common.atomic import atomic_write  # noqa: E402
from common.cache import seed_cached_response  # noqa: E402

DEMOS_ROOT = REPO_ROOT / "demos"
MANIFEST_PATH = DEMOS_ROOT / "seed_manifest.json"
SC100_CARDS_PATH = DEMOS_ROOT / "sc100_extraction/output/metadata.json"
SC100_HTML_PATH = DEMOS_ROOT / "sc100_extraction/output/index.html"
SC100_RESPONSE_PATH = (
    DEMOS_ROOT / "sc100_extraction/data/reconstructed_response.json"
)

EXTRACT_FIXTURES = (
    ("grounded_extraction", "output/metadata.json"),
    ("birth_record_extraction", "output/metadata.json"),
    ("rma_extraction", "output/metadata.json"),
    ("sc100_extraction", "data/reconstructed_response.json"),
)
PARSE_FIXTURE = (
    "parse_citations",
    "data/appraisal_report_parse_results.json",
)
SEEDED_FIXTURES = tuple(
    (demo, source_file, EXTRACT_ENDPOINT)
    for demo, source_file in EXTRACT_FIXTURES
) + ((*PARSE_FIXTURE, PARSE_ENDPOINT),)


class _Sc100PageParser(HTMLParser):
    """Collect committed SC-100 page dimensions from image data attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.pages: list[dict[str, int | float]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "img":
            return
        attributes = dict(attrs)
        if not {"data-page", "data-width", "data-height"} <= attributes.keys():
            return

        page_index = _integer_attribute(attributes["data-page"], "data-page")
        width = _positive_numeric_attribute(attributes["data-width"], "data-width")
        height = _positive_numeric_attribute(
            attributes["data-height"],
            "data-height",
        )
        self.pages.append(
            {
                "height": height,
                "page": page_index + 1,
                "width": width,
            }
        )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source_file:
        return json.load(source_file)


def _write_json(path: Path, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if path.exists() and path.read_bytes() == payload:
        return
    atomic_write(path, payload)


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _document_config(demo_dir: Path) -> dict[str, Any]:
    configs = _load_json(demo_dir / "docs.json")
    if (
        not isinstance(configs, list)
        or len(configs) != 1
        or not isinstance(configs[0], dict)
    ):
        raise ValueError(f"{_repo_relative(demo_dir / 'docs.json')} must have one config")
    return configs[0]


def _configured_pdf_path(demo_dir: Path, config: dict[str, Any]) -> Path:
    configured_file = config.get("file")
    if not isinstance(configured_file, str) or not configured_file:
        raise ValueError("config.file must be a non-empty relative string")

    relative_path = Path(configured_file)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("config.file must be a relative path without '..'")

    resolved_demo_dir = demo_dir.resolve()
    resolved_pdf_path = (demo_dir / relative_path).resolve()
    try:
        resolved_pdf_path.relative_to(resolved_demo_dir)
    except ValueError:
        raise ValueError("config.file must resolve inside its demo directory") from None
    return resolved_pdf_path


def _integer_attribute(value: str | None, name: str) -> int:
    if value is None:
        raise ValueError(f"SC-100 {name} must be present")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"SC-100 {name} must be an integer") from None
    if number < 0:
        raise ValueError(f"SC-100 {name} must be non-negative")
    return number


def _positive_numeric_attribute(value: str | None, name: str) -> int | float:
    if value is None:
        raise ValueError(f"SC-100 {name} must be present")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"SC-100 {name} must be numeric") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"SC-100 {name} must be a positive finite number")
    return int(number) if number.is_integer() else number


def _set_nested(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if not parts or any(not part for part in parts):
        raise ValueError(f"SC-100 card path is invalid: {path!r}")

    current = root
    for part in parts[:-1]:
        existing = current.get(part)
        if existing is None:
            existing = {}
            current[part] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"SC-100 card path collides at {part!r}")
        current = existing

    leaf = parts[-1]
    if leaf in current:
        raise ValueError(f"SC-100 card path is duplicated: {path!r}")
    current[leaf] = value


def _sc100_pages() -> list[dict[str, int | float]]:
    parser = _Sc100PageParser()
    parser.feed(SC100_HTML_PATH.read_text(encoding="utf-8"))
    pages = sorted(parser.pages, key=lambda page: int(page["page"]))
    if [page["page"] for page in pages] != [1, 2, 3, 4]:
        raise ValueError("SC-100 index.html must contain pages 1 through 4 exactly once")
    return pages


def reconstruct_sc100_response() -> dict[str, Any]:
    """Reconstruct the minimal response needed to reproduce the six SC-100 cards."""

    cards = _load_json(SC100_CARDS_PATH)
    if not isinstance(cards, list) or len(cards) != 6:
        raise ValueError("SC-100 metadata.json must contain exactly six cards")

    data: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("each SC-100 card must be a JSON object")
        required = {
            "path",
            "value",
            "confidence",
            "x",
            "y",
            "width",
            "height",
            "page_index",
        }
        if not required <= card.keys():
            raise ValueError("each SC-100 card must contain the committed card fields")

        path = card["path"]
        if not isinstance(path, str):
            raise ValueError("SC-100 card path must be a string")
        confidence = card["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0 <= confidence <= 100
        ):
            raise ValueError("SC-100 card confidence must be between 0 and 100")
        page_index = card["page_index"]
        if (
            isinstance(page_index, bool)
            or not isinstance(page_index, int)
            or not 0 <= page_index < 4
        ):
            raise ValueError("SC-100 card page_index must identify one of four pages")

        bbox: dict[str, int | float] = {}
        for coordinate in ("x", "y", "width", "height"):
            coordinate_value = card[coordinate]
            if (
                isinstance(coordinate_value, bool)
                or not isinstance(coordinate_value, (int, float))
                or not math.isfinite(float(coordinate_value))
            ):
                raise ValueError(f"SC-100 card {coordinate} must be finite and numeric")
            bbox[coordinate] = coordinate_value

        _set_nested(data, path, card["value"])
        _set_nested(
            metadata,
            path,
            {
                "bbox": bbox,
                "confidence": confidence / 100,
                "pageIndex": page_index,
            },
        )

    return {
        "reconstructed": True,
        "status": 200,
        "requestId": "reconstructed",
        "output": {
            "data": data,
            "metadata": metadata,
            "pages": _sc100_pages(),
        },
    }


def _seed_entry(
    demo: str,
    source_file: str,
    endpoint: str,
    endpoint_url: str,
    replay_config: dict[str, Any],
) -> dict[str, Any]:
    demo_dir = DEMOS_ROOT / demo
    config = _document_config(demo_dir)
    pdf_path = _configured_pdf_path(demo_dir, config)
    response_path = demo_dir / source_file
    response = _load_json(response_path)
    seeded_path = seed_cached_response(
        pdf_path,
        endpoint,
        replay_config,
        response,
        demo_dir / "cache",
    )
    response_cache_key = seeded_path.stem

    return {
        "demo": demo,
        "source_file": _repo_relative(response_path),
        "pdf": _repo_relative(pdf_path),
        "endpoint": endpoint_url,
        "replay_config": replay_config,
        "cache_key": response_cache_key,
    }


def main() -> None:
    reconstructed_response = reconstruct_sc100_response()
    _write_json(SC100_RESPONSE_PATH, reconstructed_response)

    manifest: list[dict[str, Any]] = []
    for demo, source_file in EXTRACT_FIXTURES:
        demo_dir = DEMOS_ROOT / demo
        config = _document_config(demo_dir)
        instructions = build_extract_instructions(
            config["mode"],
            config["schema"],
        )
        manifest.append(
            _seed_entry(
                demo,
                source_file,
                EXTRACT_ENDPOINT,
                EXTRACT_URL,
                instructions,
            )
        )

    parse_demo, parse_source = PARSE_FIXTURE
    parse_dir = DEMOS_ROOT / parse_demo
    parse_config = _document_config(parse_dir)
    parse_response = _load_json(parse_dir / parse_source)
    if parse_config.get("mode") != "agentic":
        raise ValueError("parse replay config must use the authoritative agentic mode")
    if (
        not isinstance(parse_response, dict)
        or not isinstance(parse_response.get("configuration"), dict)
        or parse_response["configuration"].get("mode") != "agentic"
    ):
        raise ValueError("parse sidecar must echo the authoritative agentic mode")
    manifest.append(
        _seed_entry(
            parse_demo,
            parse_source,
            PARSE_ENDPOINT,
            PARSE_URL,
            build_parse_instructions(parse_config["mode"]),
        )
    )

    if len(manifest) != len(SEEDED_FIXTURES):
        raise RuntimeError("seed manifest entry count does not match fixtures")
    _write_json(MANIFEST_PATH, manifest)

    for entry in manifest:
        print(f"{entry['demo']}: {entry['cache_key']}")


if __name__ == "__main__":
    main()
