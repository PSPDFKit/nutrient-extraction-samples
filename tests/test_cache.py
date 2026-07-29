import asyncio
import json
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

REPO_ROOT = Path(__file__).resolve().parents[1]

SEEDED_CASES = (
    (
        "grounded_extraction",
        "output/metadata.json",
        EXTRACT_ENDPOINT,
    ),
    (
        "birth_record_extraction",
        "output/metadata.json",
        EXTRACT_ENDPOINT,
    ),
    (
        "rma_extraction",
        "output/metadata.json",
        EXTRACT_ENDPOINT,
    ),
    (
        "sc100_extraction",
        "data/reconstructed_response.json",
        EXTRACT_ENDPOINT,
    ),
    (
        "parse_citations",
        "data/appraisal_report_parse_results.json",
        PARSE_ENDPOINT,
    ),
)


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
    SEEDED_CASES,
    ids=[case[0] for case in SEEDED_CASES],
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

    expected = _load_json(demo_dir / source_file)
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
    assert len(committed_cache_files) == 5
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
        _pdf_path: str | Path,
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
