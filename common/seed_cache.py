"""Seed deterministic, committed cache entries from the demos' response fixtures."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
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
from common.cache import (  # noqa: E402
    cache_key as compute_cache_key,
    seed_cached_response,
)

DEMOS_ROOT = REPO_ROOT / "demos"
MANIFEST_PATH = DEMOS_ROOT / "seed_manifest.json"
SC100_CARDS_PATH = DEMOS_ROOT / "sc100_extraction/output/metadata.json"
SC100_HTML_PATH = DEMOS_ROOT / "sc100_extraction/output/index.html"
SC100_RESPONSE_PATH = DEMOS_ROOT / "sc100_extraction/data/reconstructed_response.json"

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
    (demo, source_file, EXTRACT_ENDPOINT) for demo, source_file in EXTRACT_FIXTURES
) + ((*PARSE_FIXTURE, PARSE_ENDPOINT),)

MANAGED_DEMOS = frozenset(demo for demo, _source, _endpoint in SEEDED_FIXTURES)
PRESERVED_INVENTORY_KIND = "reviewed_live_authentic_form"
PRESERVED_ENTRY_KEYS = frozenset(
    {
        "demo",
        "inventory_kind",
        "source_file",
        "pdf",
        "endpoint",
        "replay_config_source",
        "cache_key",
        "receipt_file",
        "comparison_file",
        "reviewed_output_file",
        "source_page_file",
        "sha256",
        "legacy_evidence",
    }
)
PRESERVED_SHA256_KEYS = frozenset(
    {
        "pdf",
        "response_cache",
        "receipt",
        "comparison",
        "reviewed_output",
        "source_page",
    }
)
PRESERVED_LEGACY_KEYS = frozenset({"pdf", "cache_key", "receipt_file", "sha256"})
PRESERVED_LEGACY_SHA256_KEYS = frozenset({"pdf", "response_cache", "receipt"})
LIVE_RECEIPT_KEYS = frozenset(
    {"receiptVersion", "sourceStatus", "requestId", "projectedResponseSha256"}
)
LIVE_CACHE_KEYS = frozenset({"status", "requestId", "output", "reconstructed"})
_DEMO_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXTRACT_CACHE_KEY = re.compile(
    rf"([0-9a-f]{{64}})-{re.escape(EXTRACT_ENDPOINT)}-([0-9a-f]{{64}})\Z"
)


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
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == payload:
        return
    atomic_write(path, payload)


def _reject_duplicate_object_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"seed manifest contains duplicate key {key!r}")
        value[key] = item
    return value


def _load_existing_manifest() -> list[Any]:
    if MANIFEST_PATH.is_symlink():
        raise ValueError("seed manifest must not be a symbolic link")
    if not MANIFEST_PATH.exists():
        return []
    try:
        with MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
            value = json.load(
                manifest_file,
                object_pairs_hook=_reject_duplicate_object_keys,
            )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"seed manifest is malformed: {error}") from None
    if not isinstance(value, list):
        raise ValueError("seed manifest must be a JSON array")
    return value


def _require_exact_keys(
    value: Any,
    expected: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} must contain exactly {sorted(expected)!r}")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: Any, label: str) -> str:
    digest = _require_string(value, label)
    if not _SHA256.fullmatch(digest):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _safe_preserved_path(
    value: Any,
    *,
    demo: str,
    label: str,
    expected: str | None = None,
) -> Path:
    path_value = _require_string(value, label)
    if expected is not None and path_value != expected:
        raise ValueError(f"{label} must be {expected!r}")
    if "\\" in path_value:
        raise ValueError(f"{label} must use canonical POSIX separators")

    raw_parts = path_value.split("/")
    relative_path = PurePosixPath(path_value)
    if (
        relative_path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or relative_path.as_posix() != path_value
    ):
        raise ValueError(f"{label} must be a canonical repo-relative path")
    if relative_path.parts[:2] != ("demos", demo):
        raise ValueError(f"{label} must stay inside demos/{demo}")

    candidate = REPO_ROOT.joinpath(*relative_path.parts)
    cursor = REPO_ROOT
    for part in relative_path.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"{label} must not traverse a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to((DEMOS_ROOT / demo).resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError(
            f"{label} must resolve to an existing file inside demos/{demo}"
        ) from None
    if not candidate.is_file():
        raise ValueError(f"{label} must identify a regular file")
    return candidate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        while chunk := source_file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_file_digest(path: Path, expected: Any, label: str) -> None:
    expected_digest = _require_sha256(expected, f"{label} SHA-256")
    if _sha256_file(path) != expected_digest:
        raise ValueError(f"{label} does not match its preserved SHA-256")


def _validate_extract_cache_key(
    value: Any,
    *,
    pdf_sha256: str,
    label: str,
) -> str:
    cache_key = _require_string(value, label)
    match = _EXTRACT_CACHE_KEY.fullmatch(cache_key)
    if match is None or match.group(1) != pdf_sha256:
        raise ValueError(
            f"{label} must be an Extract cache key bound to its PDF SHA-256"
        )
    return cache_key


def _response_digest(response: dict[str, Any]) -> str:
    try:
        payload = json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError("preserved live cache is not canonical JSON") from None
    return hashlib.sha256(payload).hexdigest()


def _validate_receipt_bound_cache(
    response_path: Path,
    receipt_path: Path,
    *,
    label: str,
) -> None:
    response = _load_json(response_path)
    if (
        not isinstance(response, dict)
        or set(response) != LIVE_CACHE_KEYS
        or response.get("status") != 200
        or not isinstance(response.get("requestId"), str)
        or not response["requestId"]
        or not isinstance(response.get("output"), dict)
        or set(response["output"]) != {"data", "metadata", "pages"}
        or not isinstance(response["output"]["data"], dict)
        or not isinstance(response["output"]["metadata"], dict)
        or not isinstance(response["output"]["pages"], list)
        or response["reconstructed"] is not False
    ):
        raise ValueError(
            f"{label} cache must be an exact, non-reconstructed live response"
        )

    receipt = _load_json(receipt_path)
    if not isinstance(receipt, dict) or set(receipt) != LIVE_RECEIPT_KEYS:
        raise ValueError(f"{label} receipt must contain exactly the live receipt keys")
    if receipt["receiptVersion"] != 1 or isinstance(receipt["receiptVersion"], bool):
        raise ValueError(f"{label} receiptVersion must be 1")
    if receipt["sourceStatus"] != "live-refresh":
        raise ValueError(f"{label} receipt sourceStatus must be 'live-refresh'")
    request_id = response["requestId"]
    if (
        not isinstance(request_id, str)
        or not request_id
        or receipt["requestId"] != request_id
    ):
        raise ValueError(f"{label} receipt requestId must match its cache")
    receipt_digest = _require_sha256(
        receipt["projectedResponseSha256"],
        f"{label} receipt projectedResponseSha256",
    )
    if receipt_digest != _response_digest(response):
        raise ValueError(f"{label} receipt digest must match its cache")


def _validate_preserved_entry(
    entry: dict[str, Any],
) -> tuple[list[str], list[str]]:
    _require_exact_keys(entry, PRESERVED_ENTRY_KEYS, "preserved manifest entry")
    demo = _require_string(entry["demo"], "preserved manifest demo")
    if not _DEMO_ID.fullmatch(demo):
        raise ValueError("preserved manifest demo must be a safe demo identifier")
    if demo in MANAGED_DEMOS:
        raise ValueError(f"managed demo {demo!r} cannot be preserved")
    if entry["inventory_kind"] != PRESERVED_INVENTORY_KIND:
        raise ValueError(
            "unmanaged manifest entries must explicitly use inventory_kind "
            f"{PRESERVED_INVENTORY_KIND!r}"
        )
    if entry["endpoint"] != EXTRACT_URL:
        raise ValueError(f"preserved manifest entry {demo!r} must use {EXTRACT_URL}")

    demo_prefix = f"demos/{demo}"
    sha256 = _require_exact_keys(
        entry["sha256"],
        PRESERVED_SHA256_KEYS,
        f"{demo}.sha256",
    )
    pdf_sha256 = _require_sha256(sha256["pdf"], f"{demo}.sha256.pdf")
    cache_key = _validate_extract_cache_key(
        entry["cache_key"],
        pdf_sha256=pdf_sha256,
        label=f"{demo}.cache_key",
    )
    expected_paths = {
        "source_file": f"{demo_prefix}/cache/{cache_key}.json",
        "replay_config_source": f"{demo_prefix}/docs.json",
        "receipt_file": f"{demo_prefix}/cache/{cache_key}.receipt.json",
        "comparison_file": f"{demo_prefix}/output/comparison.json",
        "reviewed_output_file": f"{demo_prefix}/output/index.html",
        "source_page_file": f"{demo_prefix}/output/source-page.png",
    }
    paths = {
        key: _safe_preserved_path(
            entry[key],
            demo=demo,
            label=f"{demo}.{key}",
            expected=expected,
        )
        for key, expected in expected_paths.items()
    }
    paths["pdf"] = _safe_preserved_path(
        entry["pdf"],
        demo=demo,
        label=f"{demo}.pdf",
    )

    config = _document_config(DEMOS_ROOT / demo)
    if _configured_pdf_path(DEMOS_ROOT / demo, config) != paths["pdf"].resolve():
        raise ValueError(f"{demo}.pdf does not match its docs.json config")
    mode = config.get("mode")
    schema = config.get("schema")
    if not isinstance(mode, str) or not isinstance(schema, dict):
        raise ValueError(f"{demo}.docs.json must contain an Extract mode and schema")
    expected_cache_key = compute_cache_key(
        paths["pdf"],
        EXTRACT_ENDPOINT,
        build_extract_instructions(mode, schema),
    )
    if cache_key != expected_cache_key:
        raise ValueError(f"{demo}.cache_key does not match its PDF and docs.json")

    hash_paths = {
        "pdf": "pdf",
        "response_cache": "source_file",
        "receipt": "receipt_file",
        "comparison": "comparison_file",
        "reviewed_output": "reviewed_output_file",
        "source_page": "source_page_file",
    }
    for hash_name, path_name in hash_paths.items():
        _validate_file_digest(
            paths[path_name],
            sha256[hash_name],
            f"{demo} {hash_name}",
        )
    _validate_receipt_bound_cache(
        paths["source_file"],
        paths["receipt_file"],
        label=f"{demo} current evidence",
    )

    legacy = _require_exact_keys(
        entry["legacy_evidence"],
        PRESERVED_LEGACY_KEYS,
        f"{demo}.legacy_evidence",
    )
    legacy_sha256 = _require_exact_keys(
        legacy["sha256"],
        PRESERVED_LEGACY_SHA256_KEYS,
        f"{demo}.legacy_evidence.sha256",
    )
    legacy_pdf_sha256 = _require_sha256(
        legacy_sha256["pdf"],
        f"{demo}.legacy_evidence.sha256.pdf",
    )
    legacy_cache_key = _validate_extract_cache_key(
        legacy["cache_key"],
        pdf_sha256=legacy_pdf_sha256,
        label=f"{demo}.legacy_evidence.cache_key",
    )
    if legacy_cache_key == cache_key:
        raise ValueError(f"{demo} current and legacy cache keys must differ")
    legacy_paths = {
        "pdf": _safe_preserved_path(
            legacy["pdf"],
            demo=demo,
            label=f"{demo}.legacy_evidence.pdf",
        ),
        "response_cache": _safe_preserved_path(
            f"{demo_prefix}/cache/{legacy_cache_key}.json",
            demo=demo,
            label=f"{demo}.legacy_evidence.response_cache",
        ),
        "receipt": _safe_preserved_path(
            legacy["receipt_file"],
            demo=demo,
            label=f"{demo}.legacy_evidence.receipt_file",
            expected=f"{demo_prefix}/cache/{legacy_cache_key}.receipt.json",
        ),
    }
    legacy_relative_pdf = PurePosixPath(legacy["pdf"])
    if legacy_relative_pdf.parts[:3] != ("demos", demo, "data"):
        raise ValueError(f"{demo}.legacy_evidence.pdf must stay in its data directory")
    for hash_name, path in legacy_paths.items():
        _validate_file_digest(
            path,
            legacy_sha256[hash_name],
            f"{demo} legacy {hash_name}",
        )
    _validate_receipt_bound_cache(
        legacy_paths["response_cache"],
        legacy_paths["receipt"],
        label=f"{demo} legacy evidence",
    )

    preserved_paths = [entry[key] for key in (*expected_paths, "pdf")]
    preserved_paths.extend(
        [
            legacy["pdf"],
            _repo_relative(legacy_paths["response_cache"]),
            legacy["receipt_file"],
        ]
    )
    return [cache_key, legacy_cache_key], preserved_paths


def _load_preserved_manifest_entries() -> tuple[
    list[dict[str, Any]], set[str], set[str]
]:
    preserved: list[dict[str, Any]] = []
    seen_demos: set[str] = set()
    cache_key_owners: dict[str, str] = {}
    path_owners: dict[str, str] = {}

    for index, raw_entry in enumerate(_load_existing_manifest()):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"seed manifest entry {index} must be a JSON object")
        demo = _require_string(
            raw_entry.get("demo"), f"seed manifest entry {index}.demo"
        )
        if not _DEMO_ID.fullmatch(demo):
            raise ValueError(f"seed manifest entry {index}.demo is unsafe")
        if demo in seen_demos:
            raise ValueError(f"seed manifest demo collision for {demo!r}")
        seen_demos.add(demo)

        if demo in MANAGED_DEMOS:
            if "inventory_kind" in raw_entry:
                raise ValueError(f"managed demo {demo!r} cannot be preserved")
            continue
        if raw_entry.get("inventory_kind") != PRESERVED_INVENTORY_KIND:
            raise ValueError(
                f"unmanaged demo {demo!r} lacks an explicitly supported inventory_kind"
            )

        cache_keys, paths = _validate_preserved_entry(raw_entry)
        for cache_key in cache_keys:
            if cache_key in cache_key_owners:
                raise ValueError(
                    "preserved cache-key collision between "
                    f"{cache_key_owners[cache_key]!r} and {demo!r}"
                )
            cache_key_owners[cache_key] = demo
        for path in paths:
            if path in path_owners:
                raise ValueError(
                    "preserved path collision between "
                    f"{path_owners[path]!r} and {demo!r}: {path}"
                )
            path_owners[path] = demo
        preserved.append(raw_entry)

    return preserved, set(cache_key_owners), set(path_owners)


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _document_config(demo_dir: Path) -> dict[str, Any]:
    configs = _load_json(demo_dir / "docs.json")
    if (
        not isinstance(configs, list)
        or len(configs) != 1
        or not isinstance(configs[0], dict)
    ):
        raise ValueError(
            f"{_repo_relative(demo_dir / 'docs.json')} must have one config"
        )
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
        raise ValueError(
            "SC-100 index.html must contain pages 1 through 4 exactly once"
        )
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


def _validate_managed_manifest(
    manifest: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    if len(manifest) != len(SEEDED_FIXTURES):
        raise RuntimeError("seed manifest entry count does not match fixtures")

    expected_keys = frozenset(
        {"demo", "source_file", "pdf", "endpoint", "replay_config", "cache_key"}
    )
    cache_keys: set[str] = set()
    paths: set[str] = set()
    seen_demos: set[str] = set()
    for entry, (demo, source_file, endpoint) in zip(
        manifest,
        SEEDED_FIXTURES,
        strict=True,
    ):
        _require_exact_keys(entry, expected_keys, f"managed manifest entry {demo}")
        if entry["demo"] != demo or demo in seen_demos:
            raise RuntimeError("managed seed manifest demo order or identity changed")
        seen_demos.add(demo)

        demo_dir = DEMOS_ROOT / demo
        config = _document_config(demo_dir)
        pdf_path = _configured_pdf_path(demo_dir, config)
        expected_source = _repo_relative(demo_dir / source_file)
        expected_pdf = _repo_relative(pdf_path)
        expected_url = EXTRACT_URL if endpoint == EXTRACT_ENDPOINT else PARSE_URL
        if entry["source_file"] != expected_source:
            raise RuntimeError(f"managed seed source path changed for {demo}")
        if entry["pdf"] != expected_pdf:
            raise RuntimeError(f"managed seed PDF path changed for {demo}")
        if entry["endpoint"] != expected_url:
            raise RuntimeError(f"managed seed endpoint changed for {demo}")

        if endpoint == EXTRACT_ENDPOINT:
            mode = config.get("mode")
            schema = config.get("schema")
            if not isinstance(mode, str) or not isinstance(schema, dict):
                raise RuntimeError(f"managed Extract config is malformed for {demo}")
            expected_replay_config = build_extract_instructions(mode, schema)
        else:
            mode = config.get("mode")
            if mode != "agentic":
                raise RuntimeError(f"managed Parse config is malformed for {demo}")
            expected_replay_config = build_parse_instructions(mode)
        if entry["replay_config"] != expected_replay_config:
            raise RuntimeError(f"managed replay config changed for {demo}")

        expected_cache_key = compute_cache_key(
            pdf_path,
            endpoint,
            expected_replay_config,
        )
        if entry["cache_key"] != expected_cache_key:
            raise RuntimeError(f"managed cache key changed unexpectedly for {demo}")
        if expected_cache_key in cache_keys:
            raise RuntimeError(f"managed cache-key collision for {demo}")
        cache_keys.add(expected_cache_key)

        managed_paths = {
            expected_source,
            expected_pdf,
            f"demos/{demo}/docs.json",
            f"demos/{demo}/cache/{expected_cache_key}.json",
        }
        if paths & managed_paths:
            raise RuntimeError(f"managed seed path collision for {demo}")
        paths.update(managed_paths)

    if seen_demos != MANAGED_DEMOS:
        raise RuntimeError("managed seed manifest does not cover every fixture")
    return cache_keys, paths


def _reject_manifest_collisions(
    managed_cache_keys: set[str],
    managed_paths: set[str],
    preserved_cache_keys: set[str],
    preserved_paths: set[str],
) -> None:
    cache_collisions = managed_cache_keys & preserved_cache_keys
    if cache_collisions:
        raise ValueError(
            f"managed and preserved cache-key collision: {sorted(cache_collisions)!r}"
        )
    path_collisions = managed_paths & preserved_paths
    if path_collisions:
        raise ValueError(
            f"managed and preserved path collision: {sorted(path_collisions)!r}"
        )


def main() -> None:
    (
        preserved_entries,
        preserved_cache_keys,
        preserved_paths,
    ) = _load_preserved_manifest_entries()

    reconstructed_response = reconstruct_sc100_response()
    _write_json(SC100_RESPONSE_PATH, reconstructed_response)

    managed_manifest: list[dict[str, Any]] = []
    for demo, source_file in EXTRACT_FIXTURES:
        demo_dir = DEMOS_ROOT / demo
        config = _document_config(demo_dir)
        instructions = build_extract_instructions(
            config["mode"],
            config["schema"],
        )
        managed_manifest.append(
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
    managed_manifest.append(
        _seed_entry(
            parse_demo,
            parse_source,
            PARSE_ENDPOINT,
            PARSE_URL,
            build_parse_instructions(parse_config["mode"]),
        )
    )

    managed_cache_keys, managed_paths = _validate_managed_manifest(managed_manifest)
    _reject_manifest_collisions(
        managed_cache_keys,
        managed_paths,
        preserved_cache_keys,
        preserved_paths,
    )
    manifest = [*managed_manifest, *preserved_entries]
    _write_json(MANIFEST_PATH, manifest)

    for entry in managed_manifest:
        print(f"{entry['demo']}: {entry['cache_key']}")
    for entry in preserved_entries:
        print(f"{entry['demo']}: preserved {entry['cache_key']}")


if __name__ == "__main__":
    main()
