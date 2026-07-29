"""Shared hardened primitives for the Nutrient extraction demos."""

from .api import (
    EXTRACT_ENDPOINT,
    EXTRACT_URL,
    PARSE_ENDPOINT,
    PARSE_URL,
    ApiError,
    build_extract_instructions,
    build_parse_instructions,
    extract_transport,
    parse_transport,
)
from .cache import (
    CacheError,
    cache_key,
    cache_path,
    canonical_json,
    get_cached_response,
    read_cached_response,
    seed_cached_response,
    validate_response,
)
from .html_env import coerce_num, create_html_env, script_safe_json

__all__ = [
    "ApiError",
    "CacheError",
    "EXTRACT_ENDPOINT",
    "EXTRACT_URL",
    "PARSE_ENDPOINT",
    "PARSE_URL",
    "build_extract_instructions",
    "build_parse_instructions",
    "cache_key",
    "cache_path",
    "canonical_json",
    "coerce_num",
    "create_html_env",
    "extract_transport",
    "get_cached_response",
    "parse_transport",
    "read_cached_response",
    "script_safe_json",
    "seed_cached_response",
    "validate_response",
]
