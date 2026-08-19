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
REVIEWED_LIVE_CACHE_INVENTORY = {
    "mortgage_verification": {
        "current_cache_key": "2eab5c8c1c843ef5f0f0bef9e361f818369a6e5e7652f00e6e614d381a36018e-extraction-extract-c916fe75b45defb3f9078a09545733ea7e8ae8d20310dfb490ecbeb2bff6c2aa",
        "current_response_sha256": "2c20be96b8496f675ed8f0a70c77226afbd7008a59cdb47eea8a000f7b6c04e8",
        "current_receipt_sha256": "c931efb663f093748713de0cd4b51d497dbe808443e6a6afca4143210048facb",
        "legacy_cache_key": "15f9be3fc3c78a78bb5a67e8f2b8fa0d09383626b0c2600676e2a3f95d054e77-extraction-extract-b35c962edca85f56a9f2707e49646779b4db844e5c22ad71f6b29b445118de59",
        "legacy_response_sha256": "a1c31e6f3b8b2f9647107926687d1396ced32dbe47d47c378c9c8894e109f1a1",
        "legacy_receipt_sha256": "4d08edf9538d4dc5d8cedfce5edf15dd4deb7e7c343440044400158597dd7d1a",
    },
    "insurance_claim_intake": {
        "current_cache_key": "82bd017e04267eca150ef8ccb3f2471a5b445680d882f8375a174391c47fbbeb-extraction-extract-5270e4d2c6eb39ec7ff32e01fc0e8a6012e6a031be8a2532f16b9ff3ed397207",
        "current_response_sha256": "72170c3c25bfaea102ef747097ee94d27a11179a12564c6d19d940923ee0424a",
        "current_receipt_sha256": "254617154a5b3f34984ce4e094403dc2366cf3fd01f8e6d8e4696f961171029c",
        "legacy_cache_key": "acb9970d933b9b1af6d9b8c08c3843006f09e8d574f07ea0b29cf51c27e2ca33-extraction-extract-ab82c0e620306ef4a76f60768e4d990f80af692bc65304953f8499474f5921b0",
        "legacy_response_sha256": "57dff011062c8cac680176e371b644a1ac97a854a72b26c80627c8076b9c1a30",
        "legacy_receipt_sha256": "0ffe741675fadf513682a3d7e1ddcd5001d1cf3801164c708172f8ab270eed1c",
    },
    "prior_authorization": {
        "current_cache_key": "18bb2e0c4419c0c2acb002acb0b4857efacc7e96f37d15decebfe06d3394d530-extraction-extract-335056f54e95ba9cd7e96cd888db202cfb359998701790e7c15b155719d8c579",
        "current_response_sha256": "407ee89890604ca46ff356ec72a20968f504ad2f6015998719d49edd4f736805",
        "current_receipt_sha256": "c63cb5d4b14dd5460af7ae321f2357aaecba600faefee3427141abdaf9b2ce59",
        "legacy_cache_key": "8b71d8dfe70b98f5d35b1e3709fc6eb0891daf3108c705676341f4c22f936354-extraction-extract-1f70709d4b47f8041baa824b5664ab140725273ae45199fe9c8dd06b36e178b4",
        "legacy_response_sha256": "934ad86cefc1419537d7380bc736770ee2ccac5fa13c673cf6ea34446b2abbb0",
        "legacy_receipt_sha256": "80aecfe92b4465500f5bca5d949a08ab2459bda441786d18d3e5c7ae46d0d920",
    },
}


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


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_symlinked_cache_entry_is_rejected(tmp_path: Path) -> None:
    cache_file = tmp_path / "linked.json"
    cache_file.symlink_to("/dev/zero")

    with pytest.raises(cache.CacheError, match="symbolic link"):
        cache.read_cached_response(cache_file, EXTRACT_ENDPOINT)


def test_oversized_cache_entry_is_rejected(tmp_path: Path) -> None:
    cache_file = tmp_path / "oversized.json"
    with cache_file.open("wb") as oversized_cache:
        oversized_cache.truncate(cache.MAX_CACHE_BYTES + 1)

    with pytest.raises(cache.CacheError, match="exceeds") as raised:
        cache.read_cached_response(cache_file, EXTRACT_ENDPOINT)

    assert str(cache.MAX_CACHE_BYTES) in str(raised.value)


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_non_regular_cache_entry_is_rejected(
    tmp_path: Path,
    kind: str,
) -> None:
    cache_file = tmp_path / kind
    if kind == "directory":
        cache_file.mkdir()
    else:
        os.mkfifo(cache_file)

    with pytest.raises(cache.CacheError, match="not a regular file"):
        cache.read_cached_response(cache_file, EXTRACT_ENDPOINT)


def test_deeply_nested_cached_response_is_rejected(tmp_path: Path) -> None:
    nested: Any = "leaf"
    for _ in range(cache.MAX_RESPONSE_DEPTH + 1):
        nested = {"child": nested}
    cache_file = tmp_path / "deep.json"
    _write_json(cache_file, _extract_response(nested))

    with pytest.raises(cache.CacheError, match="depth limit"):
        cache.read_cached_response(cache_file, EXTRACT_ENDPOINT)


def test_overlong_string_in_cached_response_is_rejected(tmp_path: Path) -> None:
    cache_file = tmp_path / "long-string.json"
    _write_json(
        cache_file,
        _extract_response("x" * (cache.MAX_RESPONSE_STRING_LENGTH + 1)),
    )

    with pytest.raises(cache.CacheError, match="character limit"):
        cache.read_cached_response(cache_file, EXTRACT_ENDPOINT)


def test_cached_response_node_limit_is_enforced(tmp_path: Path) -> None:
    cache_file = tmp_path / "many-nodes.json"
    _write_json(
        cache_file,
        _extract_response([None] * cache.MAX_RESPONSE_NODES),
    )

    with pytest.raises(cache.CacheError, match="node limit"):
        cache.read_cached_response(cache_file, EXTRACT_ENDPOINT)


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


def test_seed_never_persists_usage_from_source_response(tmp_path: Path) -> None:
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"offline-pdf")
    safe_response = {
        **_extract_response(),
        "configuration": {"mode": "agentic"},
        "metrics": {"pagesProcessed": 1},
    }
    source_response = {
        **safe_response,
        "usage": {
            "remainingCredits": 123,
            "price_composition": {"total": 24},
        },
    }

    cache_file = cache.seed_cached_response(
        pdf_path,
        EXTRACT_ENDPOINT,
        _extract_instructions(),
        source_response,
        tmp_path / "cache",
    )

    persisted = _load_json(cache_file)
    assert persisted == safe_response
    assert "usage" not in persisted
    persisted_text = cache_file.read_text(encoding="utf-8")
    assert "remainingCredits" not in persisted_text
    assert "price_composition" not in persisted_text


@pytest.mark.parametrize(
    "denied_key",
    [
        "credit",
        "unitPrice",
        "processing_cost",
        "remainingQuota",
        "accountBalance",
    ],
)
def test_projection_rejects_nested_billing_keys(denied_key: str) -> None:
    response = {
        **_extract_response(),
        "metrics": {"future": {"billing": {denied_key: 1}}},
    }

    with pytest.raises(cache.CacheError, match="denied key"):
        cache.cache_response_projection(response)


def test_sentinel_key_is_refused_and_never_persisted_or_exposed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "sentinel-nutrient-key-must-never-be-cached"
    committed_cache_files = sorted(REPO_ROOT.glob("demos/*/cache/*.json"))
    committed_cache_paths = set(committed_cache_files)
    seed_manifest = _load_json(REPO_ROOT / "demos" / "seed_manifest.json")
    assert isinstance(seed_manifest, list)
    manifest_by_demo = {entry["demo"]: entry for entry in seed_manifest}
    seeded_demos = {demo for demo, _source, _endpoint in SEEDED_FIXTURES}
    assert set(manifest_by_demo) == (
        seeded_demos | set(REVIEWED_LIVE_CACHE_INVENTORY)
    )
    seeded_cache_paths = {
        REPO_ROOT
        / "demos"
        / demo
        / "cache"
        / f"{manifest_by_demo[demo]['cache_key']}.json"
        for demo, _source, _endpoint in SEEDED_FIXTURES
    }
    assert seeded_cache_paths <= committed_cache_paths

    for demo, expected in REVIEWED_LIVE_CACHE_INVENTORY.items():
        entry = manifest_by_demo[demo]
        assert entry["inventory_kind"] == "reviewed_live_authentic_form"
        assert entry["cache_key"] == expected["current_cache_key"]
        assert entry["sha256"]["response_cache"] == expected[
            "current_response_sha256"
        ]
        assert entry["sha256"]["receipt"] == expected[
            "current_receipt_sha256"
        ]
        assert entry["legacy_evidence"]["cache_key"] == expected[
            "legacy_cache_key"
        ]
        assert entry["legacy_evidence"]["sha256"]["response_cache"] == expected[
            "legacy_response_sha256"
        ]
        assert entry["legacy_evidence"]["sha256"]["receipt"] == expected[
            "legacy_receipt_sha256"
        ]

        cache_dir = REPO_ROOT / "demos" / demo / "cache"
        for prefix, response_hash, receipt_hash in (
            (
                expected["current_cache_key"],
                expected["current_response_sha256"],
                expected["current_receipt_sha256"],
            ),
            (
                expected["legacy_cache_key"],
                expected["legacy_response_sha256"],
                expected["legacy_receipt_sha256"],
            ),
        ):
            response_path = cache_dir / f"{prefix}.json"
            receipt_path = cache_dir / f"{prefix}.receipt.json"
            assert response_path in committed_cache_paths
            assert receipt_path in committed_cache_paths
            assert _sha256(response_path) == response_hash
            assert _sha256(receipt_path) == receipt_hash

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
    safe_response = {
        **_extract_response(),
        "configuration": {"mode": "agentic"},
        "metrics": {"pagesProcessed": 1},
    }
    response = {
        **safe_response,
        "usage": {
            "remainingCredits": 1,
            "price_composition": {"total": 1},
        },
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
    assert actual == safe_response
    assert expected_path.is_file()
    persisted = _load_json(expected_path)
    assert set(persisted) == {
        "status",
        "requestId",
        "output",
        "configuration",
        "metrics",
    }
    assert "usage" not in persisted


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
