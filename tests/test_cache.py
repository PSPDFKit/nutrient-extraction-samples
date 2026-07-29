import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from common import cache
from common.api import (
    EXTRACT_ENDPOINT,
    PARSE_ENDPOINT,
    ApiError,
    build_extract_instructions,
    build_parse_instructions,
)
from common.seed_cache import (
    SEEDED_FIXTURES,
    _configured_pdf_path,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _extract_response(value: Any = "cached") -> dict[str, Any]:
    return {
        "status": 200,
        "requestId": "offline-test",
        "output": {
            "data": {"value": value},
            "metadata": {},
            "pages": [],
        },
    }


def _extract_instructions() -> dict[str, Any]:
    return build_extract_instructions(
        "agentic",
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
        },
    )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source_file:
        return json.load(source_file)


def _fail_transport(*_args: object, **_kwargs: object) -> dict[str, Any]:
    raise AssertionError("cache replay must not call a transport")


def _fail_key_read() -> str:
    raise AssertionError("non-refresh replay must not read NUTRIENT_API_KEY")


def test_cache_hit_returns_without_network_or_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"offline-pdf")
    cache_dir = tmp_path / "cache"
    instructions = _extract_instructions()
    expected = _extract_response()
    cache.seed_cached_response(
        pdf_path,
        EXTRACT_ENDPOINT,
        instructions,
        expected,
        cache_dir,
    )
    monkeypatch.setattr(cache, "extract_transport", _fail_transport)
    monkeypatch.setattr(cache, "_api_key", _fail_key_read)

    actual = asyncio.run(
        cache.get_cached_response(
            pdf_path,
            EXTRACT_ENDPOINT,
            instructions,
            cache_dir,
        )
    )

    assert cache.canonical_json(actual) == cache.canonical_json(expected)


def test_non_refresh_cache_miss_fails_before_key_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"offline-pdf")
    monkeypatch.setattr(cache, "_api_key", _fail_key_read)
    monkeypatch.setattr(cache, "extract_transport", _fail_transport)

    with pytest.raises(cache.CacheError) as error:
        asyncio.run(
            cache.get_cached_response(
                pdf_path,
                EXTRACT_ENDPOINT,
                _extract_instructions(),
                tmp_path / "cache",
                refresh=False,
            )
        )

    assert "--refresh" in str(error.value)


def test_malformed_cache_fails_closed_without_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"offline-pdf")
    cache_dir = tmp_path / "cache"
    instructions = _extract_instructions()
    malformed_path = cache.cache_path(
        pdf_path,
        EXTRACT_ENDPOINT,
        instructions,
        cache_dir,
    )
    malformed_path.parent.mkdir(parents=True)
    malformed_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(cache, "_api_key", _fail_key_read)
    monkeypatch.setattr(cache, "extract_transport", _fail_transport)

    with pytest.raises(cache.CacheError) as error:
        asyncio.run(
            cache.get_cached_response(
                pdf_path,
                EXTRACT_ENDPOINT,
                instructions,
                cache_dir,
            )
        )

    assert "Malformed cache file" in str(error.value)
    assert "--refresh" in str(error.value)


@pytest.mark.parametrize(
    ("demo", "source_file", "endpoint"),
    SEEDED_FIXTURES,
    ids=[case[0] for case in SEEDED_FIXTURES],
)
def test_seeded_cache_round_trips_committed_response(
    demo: str,
    source_file: str,
    endpoint: str,
) -> None:
    demo_dir = REPO_ROOT / "demos" / demo
    configs = _load_json(demo_dir / "docs.json")
    assert isinstance(configs, list) and len(configs) == 1
    doc_config = configs[0]
    pdf_path = demo_dir / doc_config["file"]
    if endpoint == EXTRACT_ENDPOINT:
        instructions = build_extract_instructions(
            doc_config["mode"],
            doc_config["schema"],
        )
    else:
        assert doc_config["mode"] == "agentic"
        instructions = build_parse_instructions(doc_config["mode"])

    expected = cache.cache_response_projection(_load_json(demo_dir / source_file))
    cache_file = cache.cache_path(
        pdf_path,
        endpoint,
        instructions,
        demo_dir / "cache",
    )

    assert cache_file.is_file()
    actual = asyncio.run(
        cache.get_cached_response(
            pdf_path,
            endpoint,
            instructions,
            demo_dir / "cache",
            transport=_fail_transport,
        )
    )
    assert cache.canonical_json(actual) == cache.canonical_json(expected)


def test_sentinel_key_is_refused_and_never_persisted_or_exposed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "sentinel-nutrient-key-must-never-be-cached"
    committed_cache_files = sorted(REPO_ROOT.glob("demos/*/cache/*.json"))
    assert len(committed_cache_files) == len(SEEDED_FIXTURES)
    assert all(
        sentinel not in cache_file.read_text(encoding="utf-8")
        for cache_file in committed_cache_files
    )

    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"offline-pdf")
    cache_dir = tmp_path / "cache"
    instructions = _extract_instructions()
    response = _extract_response(sentinel)
    destination = cache.cache_path(
        pdf_path,
        EXTRACT_ENDPOINT,
        instructions,
        cache_dir,
    )
    monkeypatch.setenv("NUTRIENT_API_KEY", sentinel)

    async def sentinel_transport(
        _pdf_bytes: bytes,
        _filename: str,
        _instructions: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        assert api_key == sentinel
        return response

    with pytest.raises(ApiError) as error:
        asyncio.run(
            cache.get_cached_response(
                pdf_path,
                EXTRACT_ENDPOINT,
                instructions,
                cache_dir,
                refresh=True,
                transport=sentinel_transport,
            )
        )

    assert sentinel not in str(error.value)
    assert not destination.exists()
    assert not list(cache_dir.glob("*.json"))


@pytest.mark.parametrize("endpoint", [EXTRACT_ENDPOINT, PARSE_ENDPOINT])
def test_validate_response_rejects_non_object_response(endpoint: str) -> None:
    with pytest.raises(ValueError, match="response must be a JSON object"):
        cache.validate_response([], endpoint)


@pytest.mark.parametrize("endpoint", [EXTRACT_ENDPOINT, PARSE_ENDPOINT])
def test_validate_response_rejects_non_object_output(endpoint: str) -> None:
    with pytest.raises(ValueError, match=r"response\.output"):
        cache.validate_response({"status": 200, "output": []}, endpoint)


@pytest.mark.parametrize("endpoint", [EXTRACT_ENDPOINT, PARSE_ENDPOINT])
def test_validate_response_rejects_non_200_status(endpoint: str) -> None:
    response = (
        {
            "status": 500,
            "requestId": "failed",
            "output": {"data": {}, "metadata": {}, "pages": []},
        }
        if endpoint == EXTRACT_ENDPOINT
        else {"status": 500, "output": {"elements": []}}
    )

    with pytest.raises(ValueError, match=r"response\.status must be 200"):
        cache.validate_response(response, endpoint)


@pytest.mark.parametrize(
    "response",
    [
        {"status": 200, "output": {"data": {}, "metadata": {}, "pages": []}},
        {"status": 200, "requestId": "id", "output": {"metadata": {}, "pages": []}},
        {"status": 200, "requestId": "id", "output": {"data": {}, "pages": []}},
        {"status": 200, "requestId": "id", "output": {"data": {}, "metadata": {}}},
        {
            "status": 200,
            "requestId": "id",
            "output": {"data": [], "metadata": {}, "pages": []},
        },
        {
            "status": 200,
            "requestId": "id",
            "output": {"data": {}, "metadata": [], "pages": []},
        },
        {
            "status": 200,
            "requestId": "id",
            "output": {"data": {}, "metadata": {}, "pages": {}},
        },
    ],
)
def test_validate_response_rejects_extract_shape_branches(
    response: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        cache.validate_response(response, EXTRACT_ENDPOINT)


def test_validate_response_rejects_parse_elements_shape() -> None:
    with pytest.raises(ValueError, match=r"output\.elements must be a list"):
        cache.validate_response(
            {"status": 200, "output": {"elements": {}}},
            PARSE_ENDPOINT,
        )


def test_validate_response_rejects_unsupported_endpoint() -> None:
    with pytest.raises(ValueError, match="unsupported endpoint"):
        cache.validate_response({}, "unsupported")


def test_refresh_supports_sync_transport_and_uses_hashed_pdf_bytes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "document.pdf"
    original_pdf_bytes = b"original-pdf-bytes"
    replacement_pdf_bytes = b"replacement-pdf-bytes"
    pdf_path.write_bytes(original_pdf_bytes)
    instructions = _extract_instructions()
    response = {
        **_extract_response(),
        "usage": {"remainingCredits": 1},
        "metrics": {"price_composition": {"total": 1}},
    }
    monkeypatch.setenv("NUTRIENT_API_KEY", "test-key")

    def sync_transport(
        pdf_bytes: bytes,
        filename: str,
        received_instructions: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        assert pdf_bytes == original_pdf_bytes
        assert filename == pdf_path.name
        assert received_instructions == instructions
        assert api_key == "test-key"
        pdf_path.write_bytes(replacement_pdf_bytes)
        return response

    actual = asyncio.run(
        cache.get_cached_response(
            pdf_path,
            EXTRACT_ENDPOINT,
            instructions,
            tmp_path / "cache",
            refresh=True,
            transport=sync_transport,
        )
    )

    expected_key = (
        f"{hashlib.sha256(original_pdf_bytes).hexdigest()}-"
        f"{EXTRACT_ENDPOINT}-"
        f"{hashlib.sha256(cache.canonical_json(instructions).encode()).hexdigest()}"
    )
    expected_path = tmp_path / "cache" / f"{expected_key}.json"
    assert actual == _extract_response()
    assert expected_path.is_file()
    assert set(_load_json(expected_path)) == {"status", "requestId", "output"}


def test_missing_pdf_error_names_path_and_is_not_a_transport_error(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "missing.pdf"

    with pytest.raises(cache.CacheError) as raised:
        asyncio.run(
            cache.get_cached_response(
                pdf_path,
                EXTRACT_ENDPOINT,
                _extract_instructions(),
                tmp_path / "cache",
                refresh=True,
            )
        )

    assert str(pdf_path) in str(raised.value)
    assert "Nutrient request failed" not in str(raised.value)


def test_oversized_pdf_is_rejected_before_read(tmp_path: Path) -> None:
    pdf_path = tmp_path / "oversized.pdf"
    with pdf_path.open("wb") as oversized_pdf:
        oversized_pdf.truncate(cache.MAX_PDF_BYTES + 1)

    with pytest.raises(cache.CacheError, match="exceeds") as raised:
        cache.cache_key(pdf_path, EXTRACT_ENDPOINT, _extract_instructions())

    assert str(pdf_path) in str(raised.value)


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_non_regular_pdf_inputs_are_rejected(tmp_path: Path, kind: str) -> None:
    pdf_path = tmp_path / kind
    if kind == "directory":
        pdf_path.mkdir()
    else:
        os.mkfifo(pdf_path)

    with pytest.raises(cache.CacheError, match="not a regular file") as raised:
        cache.cache_key(pdf_path, EXTRACT_ENDPOINT, _extract_instructions())

    assert str(pdf_path) in str(raised.value)


@pytest.mark.parametrize(
    "configured_file",
    [None, "", "/tmp/outside.pdf", "../outside.pdf", "data/../../outside.pdf"],
)
def test_seed_config_rejects_unsafe_pdf_paths(
    tmp_path: Path,
    configured_file: Any,
) -> None:
    with pytest.raises(ValueError, match=r"config\.file"):
        _configured_pdf_path(tmp_path, {"file": configured_file})


def test_seed_config_accepts_relative_pdf_path_inside_demo(tmp_path: Path) -> None:
    pdf_path = tmp_path / "data" / "inside.pdf"
    pdf_path.parent.mkdir()
    pdf_path.write_bytes(b"pdf")

    assert _configured_pdf_path(
        tmp_path,
        {"file": "data/inside.pdf"},
    ) == pdf_path.resolve()


def test_seed_config_rejects_symlink_resolving_outside_demo(tmp_path: Path) -> None:
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"pdf")
    (demo_dir / "linked.pdf").symlink_to(outside_pdf)

    with pytest.raises(ValueError, match="inside its demo directory"):
        _configured_pdf_path(demo_dir, {"file": "linked.pdf"})
