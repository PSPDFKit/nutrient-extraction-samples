"""Content-addressed, cache-first access to Nutrient extraction responses."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from .api import (
    EXTRACT_ENDPOINT,
    PARSE_ENDPOINT,
    ApiError,
    extract_transport,
    parse_transport,
)

Transport = Callable[
    [str | Path, Mapping[str, Any], str],
    Awaitable[dict[str, Any]] | dict[str, Any],
]


class CacheError(ValueError):
    """Raised when a cached response cannot safely be used."""


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically for hashing and equality checks."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(
    pdf_path: str | Path,
    endpoint: str,
    instructions: Mapping[str, Any],
) -> str:
    """Return the donor-compatible content-addressed cache key."""

    _require_supported_endpoint(endpoint)
    source_path = Path(pdf_path)
    file_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    config_hash = hashlib.sha256(
        canonical_json(instructions).encode("utf-8")
    ).hexdigest()
    return f"{file_hash}-{endpoint}-{config_hash}"


def cache_path(
    pdf_path: str | Path,
    endpoint: str,
    instructions: Mapping[str, Any],
    cache_dir: str | Path,
) -> Path:
    """Return the cache JSON path for a PDF, endpoint, and client config."""

    return Path(cache_dir) / f"{cache_key(pdf_path, endpoint, instructions)}.json"


def validate_response(response: Any, endpoint: str) -> dict[str, Any]:
    """Validate the minimum persisted response shape for an endpoint."""

    _require_supported_endpoint(endpoint)
    if not isinstance(response, dict):
        raise ValueError("response must be a JSON object")

    output = response.get("output")
    if not isinstance(output, dict):
        raise ValueError("response.output must be a JSON object")

    if endpoint == PARSE_ENDPOINT:
        if not isinstance(output.get("elements"), list):
            raise ValueError("parse response.output.elements must be a list")
    else:
        if any(key not in response for key in ("status", "requestId")):
            raise ValueError("extract response is missing required top-level keys")
        if any(key not in output for key in ("data", "metadata", "pages")):
            raise ValueError("extract response.output is missing required keys")
        if not isinstance(output["data"], dict):
            raise ValueError("extract response.output.data must be a JSON object")
        if not isinstance(output["metadata"], dict):
            raise ValueError("extract response.output.metadata must be a JSON object")
        if not isinstance(output["pages"], list):
            raise ValueError("extract response.output.pages must be a list")

    return response


def read_cached_response(cache_file: str | Path, endpoint: str) -> dict[str, Any]:
    """Read and validate a cache file, failing closed on any malformed input."""

    source_path = Path(cache_file)
    try:
        with source_path.open(encoding="utf-8") as response_file:
            response = json.load(response_file)
        return validate_response(response, endpoint)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise CacheError(
            f"Malformed cache file {source_path}; rerun with --refresh to replace it."
        ) from None


def seed_cached_response(
    pdf_path: str | Path,
    endpoint: str,
    instructions: Mapping[str, Any],
    response: Any,
    cache_dir: str | Path,
) -> Path:
    """Validate and persist a committed response without reading an API key."""

    destination = cache_path(pdf_path, endpoint, instructions, cache_dir)
    try:
        validated_response = validate_response(response, endpoint)
        canonical_json(validated_response)
    except (TypeError, ValueError):
        raise CacheError(
            "Seed response did not match the required cache shape."
        ) from None
    _write_cached_response(destination, validated_response)
    return destination


async def get_cached_response(
    pdf_path: str | Path,
    endpoint: str,
    instructions: Mapping[str, Any],
    cache_dir: str | Path,
    *,
    refresh: bool = False,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Return a cached response or refresh it through the selected transport."""

    response_path = cache_path(pdf_path, endpoint, instructions, cache_dir)

    if response_path.exists() and not refresh:
        return read_cached_response(response_path, endpoint)
    if not refresh:
        raise CacheError(
            f"No cached response at {response_path}; rerun with --refresh to create it."
        )

    api_key = _api_key()
    selected_transport = transport or _transport_for(endpoint)
    try:
        pending_response = selected_transport(pdf_path, instructions, api_key)
        if inspect.isawaitable(pending_response):
            response = await pending_response
        else:
            response = pending_response
    except Exception:
        raise ApiError(f"Nutrient {endpoint} request failed.") from None

    try:
        validated_response = validate_response(response, endpoint)
        serialized_response = canonical_json(validated_response)
    except (TypeError, ValueError):
        raise ApiError(
            f"Nutrient {endpoint} response did not match the required response shape."
        ) from None

    if api_key in serialized_response:
        raise ApiError(
            f"Nutrient {endpoint} response contained sensitive request material "
            "and was not cached."
        )

    _write_cached_response(response_path, validated_response)
    return validated_response


def _require_supported_endpoint(endpoint: str) -> None:
    if endpoint not in (EXTRACT_ENDPOINT, PARSE_ENDPOINT):
        raise ValueError(f"unsupported endpoint: {endpoint}")


def _transport_for(endpoint: str) -> Transport:
    _require_supported_endpoint(endpoint)
    if endpoint == EXTRACT_ENDPOINT:
        return extract_transport
    return parse_transport


def _api_key() -> str:
    api_key = os.environ.get("NUTRIENT_API_KEY")
    if not api_key:
        raise ApiError(
            "NUTRIENT_API_KEY is required for a live request; "
            "provide it or use a valid cache."
        )
    return api_key


def _write_cached_response(cache_file: Path, response: dict[str, Any]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cache_file.parent,
            prefix=f".{cache_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(response, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        temporary_path.replace(cache_file)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
