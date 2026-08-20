"""Shared contracts for the Data Extraction lighthouse packages.

This module deliberately keeps provisional layout data and live API evidence in
different runtime types.  It also owns the source-fixture-to-oracle path so an
API response can never become the source of expected values.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, TypeAlias
from urllib.parse import urlsplit, urlunsplit

from .api import EXTRACT_ENDPOINT
from .cache import CacheError, MAX_CACHE_BYTES, validate_response
from .html_env import create_html_env


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
PathPart: TypeAlias = str | int

COMMITTED_CACHE_KEYS = frozenset(
    {"status", "requestId", "output", "reconstructed"}
)
REQUIRED_CACHE_KEYS = frozenset({"status", "requestId", "output"})
EXTRACT_OUTPUT_KEYS = frozenset({"data", "metadata", "pages"})
LIVE_RECEIPT_KEYS = frozenset(
    {"receiptVersion", "sourceStatus", "requestId", "projectedResponseSha256"}
)
PROVISIONAL_SOURCE_STATUS = "provisional-layout"
LIVE_RECEIPT_SOURCE_STATUS = "live-refresh"
SYNTHETIC_SOURCE_STATUS = "synthetic"
PUBLIC_FORM_SOURCE_STATUS = "public-form-demo"
PROVISIONAL_LABEL = "PROVISIONAL LAYOUT DATA — NO API CALL WAS MADE"
LIVE_REVIEW_LABEL = "LIVE API RESPONSE — REVIEW REQUIRED"
REVIEWED_LIVE_LABEL = "REVIEWED LIVE API RESPONSE"

MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_JSON_STRING_LENGTH = 200_000
MAX_FIXTURE_BYTES = 1_000_000
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_FIELDS = 16
MIN_PAGE_WIDTH = 500.0
MAX_PAGE_WIDTH = 1_200.0
MIN_PAGE_HEIGHT = 600.0
MAX_PAGE_HEIGHT = 1_600.0

_SLUG = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SAFE_PATH_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SAFE_FILE_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HTTPS_HOSTNAME = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
_MISSING = object()
_LIVE_EVIDENCE_TOKEN = object()


class LighthouseError(ValueError):
    """Raised when lighthouse evidence or fixture input fails closed."""


@dataclass(frozen=True)
class ProvisionalEvidence:
    """Offline-only layout data that can never render with a live label."""

    response: dict[str, Any]

    @property
    def label(self) -> str:
        return PROVISIONAL_LABEL

    @property
    def kind(self) -> Literal["provisional"]:
        return "provisional"


@dataclass(frozen=True, init=False)
class LiveRefreshEvidence:
    """Receipt-bound live evidence; direct construction is forbidden."""

    _response: dict[str, Any]
    _projected_response_sha256: str
    reviewed: bool

    def __init__(
        self,
        response: Any = None,
        reviewed: bool = False,
        *,
        projected_response_sha256: str | None = None,
        _token: object | None = None,
    ) -> None:
        if _token is not _LIVE_EVIDENCE_TOKEN:
            raise LighthouseError(
                "live evidence can only be loaded from a committed cache and receipt"
            )
        if not isinstance(reviewed, bool):
            raise LighthouseError("reviewed must be a boolean")
        validated = validate_committed_cache(response)
        digest = committed_response_digest(validated)
        if projected_response_sha256 != digest:
            raise LighthouseError("live evidence digest does not match its receipt")
        object.__setattr__(self, "_response", validated)
        object.__setattr__(self, "_projected_response_sha256", digest)
        object.__setattr__(self, "reviewed", reviewed)

    @property
    def response(self) -> dict[str, Any]:
        return _json_clone(self._response, label="live evidence response")

    def assert_provenance(self) -> None:
        if committed_response_digest(self._response) != self._projected_response_sha256:
            raise LighthouseError("live evidence no longer matches its receipt")

    @property
    def label(self) -> str:
        return REVIEWED_LIVE_LABEL if self.reviewed else LIVE_REVIEW_LABEL

    @property
    def kind(self) -> Literal["live"]:
        return "live"


LighthouseEvidence: TypeAlias = ProvisionalEvidence | LiveRefreshEvidence


@dataclass(frozen=True)
class ComparisonIssue:
    """One independently retained expected/actual/grounding mismatch."""

    code: Literal[
        "MISSING", "UNEXPECTED", "WRONG", "UNGROUNDED", "INVALID_METADATA"
    ]
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class ComparisonReport:
    """Complete comparison result; any issue makes the evidence fail."""

    issues: tuple[ComparisonIssue, ...]
    expected_leaves: int
    matched_leaves: int
    grounded_leaves: int

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "exitCode": self.exit_code,
            "expectedLeaves": self.expected_leaves,
            "matchedLeaves": self.matched_leaves,
            "groundedLeaves": self.grounded_leaves,
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class SourceBox:
    """One independently recorded, page-bounded source location."""

    page_index: Literal[0]
    x: float
    y: float
    width: float
    height: float

    def as_metadata(self) -> dict[str, Any]:
        return {
            "pageIndex": self.page_index,
            "bbox": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
            },
        }


@dataclass(frozen=True)
class FixtureField:
    path: tuple[PathPart, ...]
    label: str
    value: JsonScalar
    source_box: SourceBox | None = None


@dataclass(frozen=True)
class SyntheticFixture:
    version: int
    slug: str
    source_status: Literal["synthetic"]
    filename: PurePosixPath
    title: str
    subtitle: str
    page_width: float
    page_height: float
    fields: tuple[FixtureField, ...]


@dataclass(frozen=True)
class PublicFormProvenance:
    """Frozen identity for an official form and its privacy-safe demo copy."""

    publisher: str
    official_form_name: str
    canonical_source_url: str
    original_sha256: str
    source_sha256: str


@dataclass(frozen=True)
class PublicFormFixture:
    """Authentic public form populated only with privacy-safe demo values."""

    version: int
    slug: str
    source_status: Literal["public-form-demo"]
    filename: PurePosixPath
    title: str
    subtitle: str
    page_width: float
    page_height: float
    fields: tuple[FixtureField, ...]
    provenance: PublicFormProvenance


LighthouseFixture: TypeAlias = SyntheticFixture | PublicFormFixture


def _validate_json_tree(value: Any, *, label: str) -> None:
    """Reject non-JSON, cyclic, oversized, and non-finite structures."""

    pending: list[tuple[Any, int]] = [(value, 0)]
    seen: set[int] = set()
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise LighthouseError(f"{label} exceeds the JSON node limit")
        if depth > MAX_JSON_DEPTH:
            raise LighthouseError(f"{label} exceeds the JSON depth limit")

        if current is None or isinstance(current, (bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise LighthouseError(f"{label} contains a non-finite number")
            continue
        if isinstance(current, str):
            if len(current) > MAX_JSON_STRING_LENGTH:
                raise LighthouseError(f"{label} contains an oversized string")
            continue
        if isinstance(current, dict):
            identity = id(current)
            if identity in seen:
                raise LighthouseError(f"{label} contains a cyclic container")
            seen.add(identity)
            for key, child in current.items():
                if not isinstance(key, str):
                    raise LighthouseError(f"{label} contains a non-string object key")
                if len(key) > MAX_JSON_STRING_LENGTH:
                    raise LighthouseError(f"{label} contains an oversized object key")
                pending.append((child, depth + 1))
            continue
        if isinstance(current, list):
            identity = id(current)
            if identity in seen:
                raise LighthouseError(f"{label} contains a cyclic container")
            seen.add(identity)
            pending.extend((child, depth + 1) for child in current)
            continue
        raise LighthouseError(f"{label} contains unsupported JSON data")


def _json_clone(value: Any, *, label: str) -> Any:
    _validate_json_tree(value, label=label)
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return json.loads(serialized)
    except (TypeError, ValueError, RecursionError):
        raise LighthouseError(f"{label} is not safe JSON") from None


def _read_json(
    path: str | Path,
    *,
    label: str,
    max_bytes: int = MAX_FIXTURE_BYTES,
) -> Any:
    try:
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise LighthouseError(f"{label} path must be a regular, non-symlink file")
        if source.stat().st_size > max_bytes:
            raise LighthouseError(f"{label} file exceeds the size limit")
        payload = source.read_bytes()
    except LighthouseError:
        raise
    except (OSError, TypeError, ValueError):
        raise LighthouseError(f"could not safely read {label} file") from None

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise LighthouseError(f"{label} contains a duplicate object key")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                LighthouseError(f"{label} contains a non-finite number")
            ),
        )
    except LighthouseError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise LighthouseError(f"{label} file is malformed JSON") from None


def _validated_extract_response(response: Any, *, label: str) -> dict[str, Any]:
    cloned = _json_clone(response, label=label)
    try:
        validated = validate_response(cloned, EXTRACT_ENDPOINT)
    except (CacheError, TypeError, ValueError, RecursionError):
        raise LighthouseError(f"{label} is not a valid Extract response") from None
    request_id = validated.get("requestId")
    if (
        not isinstance(request_id, str)
        or not request_id
        or len(request_id) > 1_000
    ):
        raise LighthouseError(f"{label}.requestId must be short, non-empty text")
    return validated


def provisional_evidence(response: Any) -> ProvisionalEvidence:
    """Tag layout-only data with an unforgeable-by-label provisional type."""

    return ProvisionalEvidence(
        response=_validated_extract_response(response, label="provisional response")
    )


def load_provisional_evidence(path: str | Path) -> ProvisionalEvidence:
    """Load the required provisional envelope, never a raw/live cache object."""

    envelope = _read_json(path, label="provisional evidence")
    if not isinstance(envelope, dict):
        raise LighthouseError("provisional evidence must be a JSON object")
    if set(envelope) != {"sourceStatus", "response"}:
        raise LighthouseError(
            "provisional evidence must contain only sourceStatus and response"
        )
    if envelope["sourceStatus"] != PROVISIONAL_SOURCE_STATUS:
        raise LighthouseError("unsupported provisional source status")
    return provisional_evidence(envelope["response"])


def validate_committed_cache(response: Any) -> dict[str, Any]:
    """Validate the narrow top-level and Extract-output cache envelopes."""

    if not isinstance(response, Mapping):
        raise LighthouseError("committed cache must be a JSON object")
    actual_keys = set(response)
    unexpected = actual_keys - COMMITTED_CACHE_KEYS
    missing = REQUIRED_CACHE_KEYS - actual_keys
    if unexpected:
        raise LighthouseError(
            "committed cache contains unsupported top-level keys: "
            + ", ".join(sorted(str(key) for key in unexpected))
        )
    if missing:
        raise LighthouseError(
            "committed cache is missing required top-level keys: "
            + ", ".join(sorted(missing))
        )
    validated = _validated_extract_response(response, label="committed cache")
    output = validated["output"]
    output_keys = set(output)
    if output_keys != EXTRACT_OUTPUT_KEYS:
        unexpected_output = output_keys - EXTRACT_OUTPUT_KEYS
        missing_output = EXTRACT_OUTPUT_KEYS - output_keys
        details: list[str] = []
        if unexpected_output:
            details.append(
                "unsupported output keys "
                + ", ".join(sorted(str(key) for key in unexpected_output))
            )
        if missing_output:
            details.append(
                "missing output keys " + ", ".join(sorted(missing_output))
            )
        raise LighthouseError("committed cache has " + "; ".join(details))
    _page_dimensions_from_pages(output["pages"])
    return validated


def project_committed_cache(response: Any) -> dict[str, Any]:
    """Project a live response to only the exact lighthouse allowlist."""

    if not isinstance(response, Mapping):
        raise LighthouseError("live response must be a JSON object")
    projected = {
        key: response[key]
        for key in ("status", "requestId", "output", "reconstructed")
        if key in response
    }
    return validate_committed_cache(projected)


def committed_response_digest(response: Any) -> str:
    """Return the deterministic digest bound into a live-refresh receipt."""

    validated = validate_committed_cache(response)
    payload = json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_live_receipt(receipt: Any, response: Mapping[str, Any]) -> str:
    if not isinstance(receipt, dict) or set(receipt) != LIVE_RECEIPT_KEYS:
        raise LighthouseError(
            "live-refresh receipt must contain exactly the documented keys"
        )
    if receipt["receiptVersion"] != 1 or isinstance(
        receipt["receiptVersion"], bool
    ):
        raise LighthouseError("unsupported live-refresh receipt version")
    if receipt["sourceStatus"] != LIVE_RECEIPT_SOURCE_STATUS:
        raise LighthouseError("unsupported live-refresh receipt source status")
    request_id = receipt["requestId"]
    if not isinstance(request_id, str) or request_id != response["requestId"]:
        raise LighthouseError("live-refresh receipt requestId does not match cache")
    digest = receipt["projectedResponseSha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise LighthouseError("live-refresh receipt digest is malformed")
    if digest != committed_response_digest(response):
        raise LighthouseError("live-refresh receipt digest does not match cache")
    return digest


def _is_reconstructed_response(response: Mapping[str, Any]) -> bool:
    if response.get("requestId") == "reconstructed":
        return True
    if "reconstructed" not in response:
        return False
    marker = response["reconstructed"]
    return marker is not None and marker is not False


def load_committed_live_evidence(
    cache_path: str | Path,
    receipt_path: str | Path,
    *,
    reviewed: bool = False,
) -> LiveRefreshEvidence:
    """Load live evidence only from a cache plus its matching refresh receipt."""

    response = validate_committed_cache(
        _read_json(
            cache_path,
            label="committed live cache",
            max_bytes=MAX_CACHE_BYTES,
        )
    )
    if _is_reconstructed_response(response):
        raise LighthouseError("reconstructed responses cannot be labelled live")
    receipt = _read_json(
        receipt_path,
        label="live-refresh receipt",
        max_bytes=MAX_FIXTURE_BYTES,
    )
    digest = _validate_live_receipt(receipt, response)
    return LiveRefreshEvidence(
        response=response,
        reviewed=reviewed,
        projected_response_sha256=digest,
        _token=_LIVE_EVIDENCE_TOKEN,
    )


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if _SAFE_PATH_KEY.fullmatch(key):
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _equal_json_scalar(expected: JsonScalar, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if expected is None or actual is None:
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return expected == actual
    return type(expected) is type(actual) and expected == actual


def _page_dimensions_from_pages(pages: Any) -> tuple[float, float]:
    if not isinstance(pages, list) or len(pages) != 1:
        raise LighthouseError("lighthouse evidence requires exactly one page")
    page = pages[0]
    if not isinstance(page, dict):
        raise LighthouseError("lighthouse page metadata must be an object")
    width = _finite_dimension(
        page.get("width"),
        label="API page width",
        lower=1.0,
        upper=20_000.0,
    )
    height = _finite_dimension(
        page.get("height"),
        label="API page height",
        lower=1.0,
        upper=20_000.0,
    )
    return width, height


def _grounding_issue(
    metadata: Any,
    path: str,
    page_dimensions: tuple[float, float],
) -> ComparisonIssue | None:
    if metadata is None:
        return ComparisonIssue("UNGROUNDED", path, "no source metadata")
    if not isinstance(metadata, dict):
        return ComparisonIssue(
            "INVALID_METADATA", path, "source metadata must be an object"
        )
    bbox = metadata.get("bbox")
    page_index = metadata.get("pageIndex")
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index != 0:
        return ComparisonIssue(
            "INVALID_METADATA", path, "pageIndex must be exactly 0 for one-page evidence"
        )
    if not isinstance(bbox, dict):
        return ComparisonIssue(
            "UNGROUNDED", path, "source metadata has no bounding box"
        )
    required_bbox_keys = {"x", "y", "width", "height"}
    if set(bbox) != required_bbox_keys:
        return ComparisonIssue(
            "INVALID_METADATA",
            path,
            "bounding box must contain exactly x, y, width, and height",
        )
    for coordinate in ("x", "y", "width", "height"):
        value = bbox[coordinate]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return ComparisonIssue(
                "INVALID_METADATA", path, f"bounding box {coordinate} must be numeric"
            )
        if not math.isfinite(float(value)):
            return ComparisonIssue(
                "INVALID_METADATA", path, f"bounding box {coordinate} must be finite"
            )
    if bbox["x"] < 0 or bbox["y"] < 0:
        return ComparisonIssue(
            "INVALID_METADATA", path, "bounding box origin must be non-negative"
        )
    if bbox["width"] <= 0 or bbox["height"] <= 0:
        return ComparisonIssue(
            "INVALID_METADATA", path, "bounding box dimensions must be positive"
        )
    page_width, page_height = page_dimensions
    if bbox["x"] + bbox["width"] > page_width:
        return ComparisonIssue(
            "INVALID_METADATA", path, "bounding box exceeds the page width"
        )
    if bbox["y"] + bbox["height"] > page_height:
        return ComparisonIssue(
            "INVALID_METADATA", path, "bounding box exceeds the page height"
        )
    return None


def _subtree_leaf_items(value: Any, path: str) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        if not value:
            return [(path, value)]
        leaves: list[tuple[str, Any]] = []
        for key in sorted(value):
            leaves.extend(_subtree_leaf_items(value[key], _path(path, key)))
        return leaves
    if isinstance(value, list):
        if not value:
            return [(path, value)]
        leaves: list[tuple[str, Any]] = []
        for index, child in enumerate(value):
            leaves.extend(_subtree_leaf_items(child, _path(path, index)))
        return leaves
    return [(path, value)]


def _subtree_leaf_paths(value: Any, path: str) -> list[str]:
    return [leaf_path for leaf_path, _value in _subtree_leaf_items(value, path)]


def compare_expected(
    expected: Any,
    actual: Any,
    metadata: Any,
    *,
    pages: Any,
) -> ComparisonReport:
    """Compare independent source truth with output and retain every issue.

    Exit semantics are encoded on ``ComparisonReport``: zero means every
    expected leaf matched and was grounded; one means the evidence cannot
    support a successful-extraction claim.
    """

    expected = _json_clone(expected, label="expected source truth")
    actual = _json_clone(actual, label="actual output")
    metadata = _json_clone(metadata, label="source metadata")
    pages = _json_clone(pages, label="API pages")
    page_dimensions = _page_dimensions_from_pages(pages)
    issues: list[ComparisonIssue] = []
    expected_leaves = 0
    matched_leaves = 0
    grounded_leaves = 0

    def visit(expected_node: Any, actual_node: Any, meta_node: Any, path: str) -> None:
        nonlocal expected_leaves, matched_leaves, grounded_leaves
        if isinstance(expected_node, dict):
            if not isinstance(actual_node, dict):
                leaf_paths = _subtree_leaf_paths(expected_node, path)
                issues.append(
                    ComparisonIssue(
                        "WRONG",
                        path,
                        f"expected object, got {_json_type(actual_node)}",
                    )
                )
                expected_leaves += len(leaf_paths)
                for leaf_path in leaf_paths:
                    if leaf_path != path:
                        issues.append(
                            ComparisonIssue(
                                "WRONG",
                                leaf_path,
                                f"ancestor {path} has the wrong container type",
                            )
                        )
                if isinstance(actual_node, list):
                    for leaf_path, leaf_value in _subtree_leaf_items(
                        actual_node, path
                    ):
                        if leaf_path != path:
                            issues.append(
                                ComparisonIssue(
                                    "UNEXPECTED",
                                    leaf_path,
                                    f"unexpected value {leaf_value!r} is inside wrong-shape ancestor {path}",
                                )
                            )
                return
            expected_keys = set(expected_node)
            actual_keys = set(actual_node)
            for key in sorted(expected_keys - actual_keys):
                child_path = _path(path, key)
                leaf_paths = _subtree_leaf_paths(expected_node[key], child_path)
                for leaf_path in leaf_paths:
                    issues.append(
                        ComparisonIssue(
                            "MISSING", leaf_path, "expected source leaf is absent"
                        )
                    )
                expected_leaves += len(leaf_paths)
            for key in sorted(actual_keys - expected_keys):
                child_path = _path(path, key)
                for leaf_path, leaf_value in _subtree_leaf_items(
                    actual_node[key], child_path
                ):
                    issues.append(
                        ComparisonIssue(
                            "UNEXPECTED",
                            leaf_path,
                            f"unexpected value {leaf_value!r} is not in source truth",
                        )
                    )
            for key in sorted(expected_keys & actual_keys):
                child_meta = meta_node.get(key) if isinstance(meta_node, dict) else None
                visit(expected_node[key], actual_node[key], child_meta, _path(path, key))
            return

        if isinstance(expected_node, list):
            if not isinstance(actual_node, list):
                leaf_paths = _subtree_leaf_paths(expected_node, path)
                issues.append(
                    ComparisonIssue(
                        "WRONG",
                        path,
                        f"expected array, got {_json_type(actual_node)}",
                    )
                )
                expected_leaves += len(leaf_paths)
                for leaf_path in leaf_paths:
                    if leaf_path != path:
                        issues.append(
                            ComparisonIssue(
                                "WRONG",
                                leaf_path,
                                f"ancestor {path} has the wrong container type",
                            )
                        )
                if isinstance(actual_node, dict):
                    for leaf_path, leaf_value in _subtree_leaf_items(
                        actual_node, path
                    ):
                        if leaf_path != path:
                            issues.append(
                                ComparisonIssue(
                                    "UNEXPECTED",
                                    leaf_path,
                                    f"unexpected value {leaf_value!r} is inside wrong-shape ancestor {path}",
                                )
                            )
                return
            for index in range(len(actual_node), len(expected_node)):
                child_path = _path(path, index)
                leaf_paths = _subtree_leaf_paths(expected_node[index], child_path)
                for leaf_path in leaf_paths:
                    issues.append(
                        ComparisonIssue(
                            "MISSING", leaf_path, "expected source leaf is absent"
                        )
                    )
                expected_leaves += len(leaf_paths)
            for index in range(len(expected_node), len(actual_node)):
                child_path = _path(path, index)
                for leaf_path, leaf_value in _subtree_leaf_items(
                    actual_node[index], child_path
                ):
                    issues.append(
                        ComparisonIssue(
                            "UNEXPECTED",
                            leaf_path,
                            f"unexpected value {leaf_value!r} is not in source truth",
                        )
                    )
            metadata_items = meta_node if isinstance(meta_node, list) else []
            for index in range(min(len(expected_node), len(actual_node))):
                child_meta = (
                    metadata_items[index] if index < len(metadata_items) else None
                )
                visit(
                    expected_node[index],
                    actual_node[index],
                    child_meta,
                    _path(path, index),
                )
            return

        expected_leaves += 1
        if isinstance(actual_node, (dict, list)):
            issues.append(
                ComparisonIssue(
                    "WRONG",
                    path,
                    f"expected {_json_type(expected_node)}, got {_json_type(actual_node)}",
                )
            )
            for leaf_path, leaf_value in _subtree_leaf_items(actual_node, path):
                if leaf_path != path:
                    issues.append(
                        ComparisonIssue(
                            "UNEXPECTED",
                            leaf_path,
                            f"unexpected value {leaf_value!r} is inside wrong-shape leaf {path}",
                        )
                    )
        elif not _equal_json_scalar(expected_node, actual_node):
            issues.append(
                ComparisonIssue(
                    "WRONG",
                    path,
                    f"expected {expected_node!r}, got {actual_node!r}",
                )
            )
        else:
            matched_leaves += 1
        grounding_issue = _grounding_issue(meta_node, path, page_dimensions)
        if grounding_issue is None:
            grounded_leaves += 1
        else:
            issues.append(grounding_issue)

    visit(expected, actual, metadata, "$")
    return ComparisonReport(
        issues=tuple(issues),
        expected_leaves=expected_leaves,
        matched_leaves=matched_leaves,
        grounded_leaves=grounded_leaves,
    )


def compare_evidence(expected: Any, evidence: LighthouseEvidence) -> ComparisonReport:
    """Compare a typed evidence response against separate expected truth."""

    if not isinstance(evidence, (ProvisionalEvidence, LiveRefreshEvidence)):
        raise LighthouseError("evidence must use a lighthouse evidence type")
    if isinstance(evidence, LiveRefreshEvidence):
        evidence.assert_provenance()
    output = evidence.response["output"]
    return compare_expected(
        expected,
        output["data"],
        output["metadata"],
        pages=output["pages"],
    )


def _fixture_text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise LighthouseError(f"{label} must be text")
    if not allow_empty and not value.strip():
        raise LighthouseError(f"{label} must not be empty")
    if len(value) > 160:
        raise LighthouseError(f"{label} is too long")
    if any(ord(character) < 32 or ord(character) > 126 for character in value):
        raise LighthouseError(f"{label} must use printable ASCII")
    return value


def _finite_dimension(value: Any, *, label: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LighthouseError(f"{label} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not lower <= normalized <= upper:
        raise LighthouseError(f"{label} is outside the supported finite range")
    return normalized


def _safe_relative_filename(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise LighthouseError("document.filename must be non-empty text")
    if "\\" in value:
        raise LighthouseError("document.filename must use a safe relative path")
    filename = PurePosixPath(value)
    if (
        filename.is_absolute()
        or ".." in filename.parts
        or "." in filename.parts
        or filename.suffix.lower() != ".pdf"
        or not filename.parts
        or any(not _SAFE_FILE_PART.fullmatch(part) for part in filename.parts)
    ):
        raise LighthouseError("document.filename must be a safe relative PDF path")
    return filename


def _canonical_https_url(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise LighthouseError(
            "provenance.canonicalSourceUrl must be canonical HTTPS text"
        )
    if len(value) > 2_048 or any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise LighthouseError(
            "provenance.canonicalSourceUrl must be canonical HTTPS text"
        )
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise LighthouseError(
            "provenance.canonicalSourceUrl must be a canonical HTTPS URL"
        ) from None
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or not _HTTPS_HOSTNAME.fullmatch(hostname)
        or not any(character.isalpha() for character in hostname)
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or "\\" in parsed.path
        or any(part in {".", ".."} for part in parsed.path.split("/"))
        or re.search(r"%(?![0-9A-F]{2})", parsed.path)
    ):
        raise LighthouseError(
            "provenance.canonicalSourceUrl must be a canonical HTTPS URL"
        )
    canonical = urlunsplit(("https", hostname, parsed.path or "/", "", ""))
    if value != canonical:
        raise LighthouseError(
            "provenance.canonicalSourceUrl must be a canonical HTTPS URL"
        )
    return value


def _fixture_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LighthouseError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _source_box(
    value: Any,
    *,
    label: str,
    page_width: float,
    page_height: float,
) -> SourceBox:
    if not isinstance(value, dict) or set(value) != {"pageIndex", "bbox"}:
        raise LighthouseError(
            f"{label} must contain exactly pageIndex and bbox"
        )
    if value["pageIndex"] != 0 or isinstance(value["pageIndex"], bool):
        raise LighthouseError(f"{label}.pageIndex must be exactly 0")
    bbox = value["bbox"]
    if not isinstance(bbox, dict) or set(bbox) != {"x", "y", "width", "height"}:
        raise LighthouseError(
            f"{label}.bbox must contain exactly x, y, width, and height"
        )
    coordinates: dict[str, float] = {}
    for name in ("x", "y", "width", "height"):
        raw = bbox[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise LighthouseError(f"{label}.bbox.{name} must be numeric")
        normalized = float(raw)
        if not math.isfinite(normalized):
            raise LighthouseError(f"{label}.bbox.{name} must be finite")
        coordinates[name] = normalized
    if coordinates["x"] < 0 or coordinates["y"] < 0:
        raise LighthouseError(f"{label}.bbox origin must be non-negative")
    if coordinates["width"] <= 0 or coordinates["height"] <= 0:
        raise LighthouseError(f"{label}.bbox dimensions must be positive")
    if coordinates["x"] + coordinates["width"] > page_width:
        raise LighthouseError(f"{label}.bbox exceeds the declared page width")
    if coordinates["y"] + coordinates["height"] > page_height:
        raise LighthouseError(f"{label}.bbox exceeds the declared page height")
    return SourceBox(
        page_index=0,
        x=coordinates["x"],
        y=coordinates["y"],
        width=coordinates["width"],
        height=coordinates["height"],
    )


def _fixture_fields(
    raw_fields: Any,
    *,
    page_width: float,
    page_height: float,
    require_source_boxes: bool,
) -> tuple[FixtureField, ...]:
    if not isinstance(raw_fields, list) or not 1 <= len(raw_fields) <= MAX_FIELDS:
        raise LighthouseError(f"fixture.fields must contain 1 to {MAX_FIELDS} items")
    fields: list[FixtureField] = []
    seen_paths: set[tuple[PathPart, ...]] = set()
    required_keys = {"path", "label", "value", "source"} if require_source_boxes else {
        "path",
        "label",
        "value",
    }
    for index, raw_field in enumerate(raw_fields):
        label_prefix = f"fixture.fields[{index}]"
        if not isinstance(raw_field, dict) or set(raw_field) != required_keys:
            raise LighthouseError(f"{label_prefix} has unsupported or missing keys")
        raw_path = raw_field["path"]
        if not isinstance(raw_path, list) or not raw_path or len(raw_path) > 16:
            raise LighthouseError(f"{label_prefix}.path must be a non-empty array")
        parts: list[PathPart] = []
        for part in raw_path:
            if isinstance(part, bool) or not isinstance(part, (str, int)):
                raise LighthouseError(f"{label_prefix}.path contains an invalid segment")
            if isinstance(part, int) and part < 0:
                raise LighthouseError(f"{label_prefix}.path indices must be non-negative")
            if isinstance(part, str) and (not part or len(part) > 80):
                raise LighthouseError(f"{label_prefix}.path keys must be short and non-empty")
            parts.append(part)
        path = tuple(parts)
        if path in seen_paths:
            raise LighthouseError(f"{label_prefix}.path is duplicated")
        for prior in seen_paths:
            if path[: len(prior)] == prior or prior[: len(path)] == path:
                raise LighthouseError("fixture field paths must not overlap")
        seen_paths.add(path)

        scalar = raw_field["value"]
        if isinstance(scalar, (dict, list)):
            raise LighthouseError(f"{label_prefix}.value must be a JSON scalar")
        _validate_json_tree(scalar, label=f"{label_prefix}.value")
        visible = _visible_scalar(scalar)
        _fixture_text(visible, label=f"{label_prefix}.value", allow_empty=True)
        source_box = (
            _source_box(
                raw_field["source"],
                label=f"{label_prefix}.source",
                page_width=page_width,
                page_height=page_height,
            )
            if require_source_boxes
            else None
        )
        fields.append(
            FixtureField(
                path=path,
                label=_fixture_text(raw_field["label"], label=f"{label_prefix}.label"),
                value=scalar,
                source_box=source_box,
            )
        )
    return tuple(fields)


def parse_fixture(value: Any, *, expected_slug: str | None = None) -> LighthouseFixture:
    """Parse a generated-synthetic or authentic-public-form fixture."""

    value = _json_clone(value, label="fixture")
    if not isinstance(value, dict):
        raise LighthouseError("fixture must be a JSON object")
    version = value.get("version")
    source_status = value.get("sourceStatus")
    if version == 1 and not isinstance(version, bool):
        if source_status != SYNTHETIC_SOURCE_STATUS:
            raise LighthouseError(
                "unsupported fixture source status; version-1 fixtures must remain synthetic"
            )
        required = {"version", "slug", "sourceStatus", "document", "fields"}
    elif version == 2 and not isinstance(version, bool):
        if source_status != PUBLIC_FORM_SOURCE_STATUS:
            raise LighthouseError(
                "unsupported fixture version/source status pairing"
            )
        required = {
            "version",
            "slug",
            "sourceStatus",
            "document",
            "provenance",
            "fields",
        }
    else:
        raise LighthouseError("unsupported fixture version")
    if set(value) != required:
        raise LighthouseError("fixture must contain exactly the documented top-level keys")
    slug = value["slug"]
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        raise LighthouseError("fixture.slug is malformed")
    if expected_slug is not None and slug != expected_slug:
        raise LighthouseError("fixture.slug does not match the selected demo")

    document = value["document"]
    if not isinstance(document, dict):
        raise LighthouseError("fixture.document must be an object")
    if set(document) != {"filename", "title", "subtitle", "width", "height"}:
        raise LighthouseError("fixture.document has unsupported or missing keys")
    page_width = _finite_dimension(
        document["width"],
        label="document.width",
        lower=MIN_PAGE_WIDTH,
        upper=MAX_PAGE_WIDTH,
    )
    page_height = _finite_dimension(
        document["height"],
        label="document.height",
        lower=MIN_PAGE_HEIGHT,
        upper=MAX_PAGE_HEIGHT,
    )
    fields = _fixture_fields(
        value["fields"],
        page_width=page_width,
        page_height=page_height,
        require_source_boxes=version == 2,
    )
    common = dict(
        version=version,
        slug=slug,
        filename=_safe_relative_filename(document["filename"]),
        title=_fixture_text(document["title"], label="document.title"),
        subtitle=_fixture_text(
            document["subtitle"], label="document.subtitle", allow_empty=True
        ),
        page_width=page_width,
        page_height=page_height,
        fields=fields,
    )
    if version == 1:
        return SyntheticFixture(
            source_status=SYNTHETIC_SOURCE_STATUS,
            **common,
        )

    provenance = value["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "publisher",
        "officialFormName",
        "canonicalSourceUrl",
        "originalSha256",
        "sourceSha256",
    }:
        raise LighthouseError("fixture.provenance has unsupported or missing keys")
    return PublicFormFixture(
        source_status=PUBLIC_FORM_SOURCE_STATUS,
        provenance=PublicFormProvenance(
            publisher=_fixture_text(
                provenance["publisher"], label="provenance.publisher"
            ),
            official_form_name=_fixture_text(
                provenance["officialFormName"],
                label="provenance.officialFormName",
            ),
            canonical_source_url=_canonical_https_url(
                provenance["canonicalSourceUrl"]
            ),
            original_sha256=_fixture_sha256(
                provenance["originalSha256"],
                label="provenance.originalSha256",
            ),
            source_sha256=_fixture_sha256(
                provenance["sourceSha256"],
                label="provenance.sourceSha256",
            ),
        ),
        **common,
    )


def load_fixture(path: str | Path, *, expected_slug: str | None = None) -> LighthouseFixture:
    return parse_fixture(_read_json(path, label="fixture"), expected_slug=expected_slug)


def _assign_expected(root: Any, path: tuple[PathPart, ...], value: JsonScalar) -> Any:
    if root is None:
        root = [] if isinstance(path[0], int) else {}
    cursor = root
    for index, part in enumerate(path):
        is_last = index == len(path) - 1
        next_is_index = not is_last and isinstance(path[index + 1], int)
        if isinstance(part, str):
            if not isinstance(cursor, dict):
                raise LighthouseError("fixture paths mix incompatible object and array shapes")
            if is_last:
                if part in cursor:
                    raise LighthouseError("fixture paths assign the same source value twice")
                cursor[part] = value
            else:
                if part not in cursor:
                    cursor[part] = [] if next_is_index else {}
                cursor = cursor[part]
        else:
            if not isinstance(cursor, list):
                raise LighthouseError("fixture paths mix incompatible object and array shapes")
            if part > len(cursor):
                raise LighthouseError("fixture array paths must be contiguous")
            if part == len(cursor):
                cursor.append(None if is_last else ([] if next_is_index else {}))
            if is_last:
                if cursor[part] is not None:
                    raise LighthouseError("fixture paths assign the same source value twice")
                cursor[part] = value
            else:
                cursor = cursor[part]
    return root


def expected_from_fixture(fixture: LighthouseFixture) -> JsonValue:
    """Derive the oracle only from fields that are visibly printed in the PDF."""

    root: Any = None
    for field in fixture.fields:
        root = _assign_expected(root, field.path, field.value)
    if root is None:
        raise LighthouseError("fixture has no source fields")
    return _json_clone(root, label="generated expected values")


def expected_json_bytes(fixture: LighthouseFixture) -> bytes:
    return (
        json.dumps(
            expected_from_fixture(fixture),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _visible_scalar(value: JsonScalar) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LighthouseError("fixture value must be finite")
        return json.dumps(value, allow_nan=False)
    return str(value)


def _pdf_literal(value: str) -> str:
    _fixture_text(value, label="PDF text", allow_empty=True)
    return "(" + value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _pdf_number(value: float) -> str:
    if not math.isfinite(value):
        raise LighthouseError("PDF coordinate must be finite")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_synthetic_pdf(fixture: SyntheticFixture) -> bytes:
    """Build a stable one-page labelled-field PDF using only the stdlib."""

    if not isinstance(fixture, SyntheticFixture):
        raise LighthouseError(
            "synthetic PDF generation accepts only version-1 synthetic fixtures"
        )

    width = fixture.page_width
    height = fixture.page_height
    margin = 42.0
    gutter = 16.0
    column_width = (width - (2 * margin) - gutter) / 2
    columns = 2
    rows = math.ceil(len(fixture.fields) / columns)
    top = height - 148.0
    bottom = 38.0
    available = top - bottom
    row_height = min(82.0, available / rows)
    if row_height < 58.0:
        raise LighthouseError("fixture fields do not fit on one supported page")

    commands = [
        "q",
        "0.965 0.953 0.914 rg",
        f"0 0 {_pdf_number(width)} {_pdf_number(height)} re f",
        "0.075 0.082 0.092 rg",
        f"0 {_pdf_number(height - 112)} {_pdf_number(width)} 112 re f",
        "BT",
        "/F2 22 Tf",
        "0.97 0.96 0.91 rg",
        f"1 0 0 1 {_pdf_number(margin)} {_pdf_number(height - 62)} Tm",
        f"{_pdf_literal(fixture.title)} Tj",
        "ET",
        "BT",
        "/F1 9 Tf",
        "0.72 0.75 0.78 rg",
        f"1 0 0 1 {_pdf_number(margin)} {_pdf_number(height - 84)} Tm",
        f"{_pdf_literal(fixture.subtitle)} Tj",
        "ET",
    ]

    for index, field in enumerate(fixture.fields):
        row = index // columns
        column = index % columns
        x = margin + column * (column_width + gutter)
        y_top = top - row * row_height
        y = y_top - row_height + 7.0
        commands.extend(
            [
                "0.995 0.991 0.974 rg",
                f"{_pdf_number(x)} {_pdf_number(y)} {_pdf_number(column_width)} "
                f"{_pdf_number(row_height - 9)} re f",
                "0.83 0.81 0.74 RG",
                "0.65 w",
                f"{_pdf_number(x)} {_pdf_number(y)} {_pdf_number(column_width)} "
                f"{_pdf_number(row_height - 9)} re S",
                "BT",
                "/F2 8 Tf",
                "0.28 0.31 0.35 rg",
                f"1 0 0 1 {_pdf_number(x + 12)} {_pdf_number(y_top - 20)} Tm",
                f"{_pdf_literal(field.label.upper())} Tj",
                "ET",
            ]
        )
        visible_value = _visible_scalar(field.value)
        wrapped = textwrap.wrap(
            visible_value,
            width=max(20, int(column_width / 6.5)),
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        if len(wrapped) > 2:
            raise LighthouseError(
                f"fixture value for {field.label!r} needs more than two PDF lines"
            )
        for line_index, line in enumerate(wrapped):
            commands.extend(
                [
                    "BT",
                    "/F1 12 Tf",
                    "0.05 0.06 0.07 rg",
                    f"1 0 0 1 {_pdf_number(x + 12)} "
                    f"{_pdf_number(y_top - 41 - line_index * 15)} Tm",
                    f"{_pdf_literal(line)} Tj",
                    "ET",
                ]
            )

    commands.extend(
        [
            "BT",
            "/F1 7 Tf",
            "0.38 0.4 0.42 rg",
            f"1 0 0 1 {_pdf_number(margin)} 20 Tm",
            f"{_pdf_literal('Synthetic fixture - no real personal or customer data')} Tj",
            "ET",
            "Q",
        ]
    )
    content = ("\n".join(commands) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_pdf_number(width)} "
            f"{_pdf_number(height)}] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> "
            "/Contents 6 0 R >>"
        ).encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream",
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


def _page_dimensions(response: Mapping[str, Any]) -> tuple[float, float]:
    return _page_dimensions_from_pages(response["output"]["pages"])


def _lookup_path(root: Any, path: tuple[PathPart, ...]) -> Any:
    cursor = root
    for part in path:
        if isinstance(part, str) and isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        elif isinstance(part, int) and isinstance(cursor, list) and part < len(cursor):
            cursor = cursor[part]
        else:
            return _MISSING
    return cursor


def _iter_leaves(value: Any, path: tuple[PathPart, ...] = ()) -> list[tuple[tuple[PathPart, ...], Any]]:
    leaves: list[tuple[tuple[PathPart, ...], Any]] = []
    if isinstance(value, dict):
        if value:
            for key in sorted(value):
                leaves.extend(_iter_leaves(value[key], path + (key,)))
        else:
            leaves.append((path, value))
    elif isinstance(value, list):
        if value:
            for index, child in enumerate(value):
                leaves.extend(_iter_leaves(child, path + (index,)))
        else:
            leaves.append((path, value))
    else:
        leaves.append((path, value))
    return leaves


def _display_json(value: Any) -> str:
    if value is _MISSING:
        return "Missing"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _embedded_asset_url(path: Path, *, mime: str, label: str) -> str:
    """Return a bundled design asset as a self-contained data URL."""

    try:
        payload = path.read_bytes()
    except OSError:
        raise LighthouseError(f"could not read bundled {label}") from None
    if not payload:
        raise LighthouseError(f"bundled {label} is empty")
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")


def _cards(expected: Any, response: Mapping[str, Any], report: ComparisonReport) -> list[dict[str, Any]]:
    output = response["output"]
    actual = output["data"]
    metadata = output["metadata"]
    page_dimensions = _page_dimensions(response)
    issue_codes: dict[str, list[str]] = {}
    for issue in report.issues:
        issue_codes.setdefault(issue.path, []).append(issue.code)
    cards: list[dict[str, Any]] = []
    for path, expected_value in _iter_leaves(expected):
        path_text = "$"
        for part in path:
            path_text = _path(path_text, part)
        actual_value = _lookup_path(actual, path)
        meta_value = _lookup_path(metadata, path)
        bbox = None
        page_index = None
        if _grounding_issue(meta_value, path_text, page_dimensions) is None:
            bbox = {coordinate: float(meta_value["bbox"][coordinate]) for coordinate in ("x", "y", "width", "height")}
            page_index = meta_value["pageIndex"]
        codes = issue_codes.get(path_text, [])
        cards.append(
            {
                "path": path_text,
                "expected": _display_json(expected_value),
                "actual": _display_json(actual_value),
                "status": "pass" if not codes else "fail",
                "issues": codes,
                "bbox": bbox,
                "pageIndex": page_index,
            }
        )
    return cards


def _source_copy(source_status: str) -> dict[str, str]:
    if source_status == SYNTHETIC_SOURCE_STATUS:
        return {
            "eyebrow": "Reviewed evidence / synthetic fixture",
            "reviewed_detail": "Reviewed against the visible synthetic source.",
            "page_label": "Synthetic source · page 1",
            "image_alt_prefix": "Synthetic source document",
            "metric_label": "source grounded",
            "footnote": (
                "Correctness is determined by the independent synthetic-source "
                "oracle. Recognition signals and bounding boxes are supporting "
                "evidence, not a substitute for comparison."
            ),
        }
    if source_status == PUBLIC_FORM_SOURCE_STATUS:
        return {
            "eyebrow": "Reviewed evidence / authentic public form",
            "reviewed_detail": (
                "Reviewed against the visible authentic public form with "
                "privacy-safe demo values."
            ),
            "page_label": (
                "Authentic public form · privacy-safe demo values · page 1"
            ),
            "image_alt_prefix": (
                "Authentic public form with privacy-safe demo values"
            ),
            "metric_label": "primary regions returned",
            "footnote": (
                "Correctness is determined by the independent source oracle for "
                "this authentic public form with privacy-safe demo values. "
                "Recognition signals and bounding boxes are supporting evidence, "
                "not a substitute for comparison."
            ),
        }
    raise LighthouseError("unsupported rendered fixture source status")


def render_lighthouse_page(
    *,
    title: str,
    summary: str,
    document_name: str,
    document_image: bytes,
    expected: Any,
    evidence: LighthouseEvidence,
    image_mime: str = "image/png",
    source_status: str = SYNTHETIC_SOURCE_STATUS,
) -> str:
    """Render one responsive, self-contained and context-safe proof page."""

    if not isinstance(evidence, (ProvisionalEvidence, LiveRefreshEvidence)):
        raise LighthouseError("evidence must use a lighthouse evidence type")
    if image_mime not in _IMAGE_MIME_TYPES:
        raise LighthouseError("unsupported embedded image type")
    if not isinstance(document_image, bytes) or not document_image:
        raise LighthouseError("document image must contain bytes")
    if len(document_image) > MAX_IMAGE_BYTES:
        raise LighthouseError("document image exceeds the embedded size limit")
    for value, label in (
        (title, "page title"),
        (summary, "page summary"),
        (document_name, "document name"),
    ):
        if not isinstance(value, str) or not value:
            raise LighthouseError(f"{label} must be non-empty text")

    expected = _json_clone(expected, label="expected source truth")
    if isinstance(evidence, LiveRefreshEvidence):
        evidence.assert_provenance()
    response = _validated_extract_response(evidence.response, label="page evidence")
    if isinstance(evidence, LiveRefreshEvidence):
        response = validate_committed_cache(response)
    report = compare_expected(
        expected,
        response["output"]["data"],
        response["output"]["metadata"],
        pages=response["output"]["pages"],
    )
    page_width, page_height = _page_dimensions(response)
    cards = _cards(expected, response, report)
    image_url = (
        f"data:{image_mime};base64,"
        + base64.b64encode(document_image).decode("ascii")
    )
    assets_dir = Path(__file__).resolve().parent / "assets"
    logo_url = _embedded_asset_url(
        assets_dir / "logotype" / "nutrient-logo.svg",
        mime="image/svg+xml",
        label="Nutrient logo",
    )
    request_id = (
        response["requestId"] if isinstance(evidence, LiveRefreshEvidence) else None
    )
    source_copy = _source_copy(source_status)
    client_data = {
        "cards": cards,
        "page": {"width": page_width, "height": page_height},
        "comparison": report.as_dict(),
    }
    template_dir = Path(__file__).resolve().parent / "templates"
    template = create_html_env(template_dir).get_template("lighthouse.html")
    return template.render(
        title=title,
        summary=summary,
        document_name=document_name,
        image_url=image_url,
        logo_url=logo_url,
        evidence_kind=evidence.kind,
        evidence_label=evidence.label,
        reviewed=isinstance(evidence, LiveRefreshEvidence) and evidence.reviewed,
        request_id=request_id,
        comparison=report,
        cards=cards,
        client_data=client_data,
        source_copy=source_copy,
    )
