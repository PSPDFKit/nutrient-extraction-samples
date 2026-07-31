from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import pytest

from common import cache as common_cache

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS = (
    "birth_record_extraction",
    "grounded_extraction",
    "parse_citations",
    "rma_extraction",
    "sc100_extraction",
)
EXTRACTION_DEMOS = tuple(name for name in DEMOS if name != "parse_citations")
# These hashes pin the reviewed output corpus rather than trusting whatever files
# happen to be present before a replay. The Parse HTML hash includes its two
# intentional autoescape corrections.
EXPECTED_ARTIFACT_SHA256 = {
    "birth_record_extraction": {
        "index.html": "e95909e860b85ccac37f6bbe8bf8ef16df3e78967086f8f52bff462e9ef60a5b",
        "indiana_birth_record_page_0.png": "e812f4c4e7f8572dac98a8f51eb6d442e9eb51c754cebfab0775271f1ef78bfd",
        "metadata.json": "21a3fbccb0110b83f9e44db0144efd64eff608de2c7ed6c6df05117f70402642",
    },
    "grounded_extraction": {
        "cms_1500_page_0.png": "c95d02b7df14fc03024fabb7fabf0409b8be891d2582c420aaca741114516ae8",
        "index.html": "2ce45e5ec368ba356b8abe8e71a17c298eb98a98de15a44cc5f1c88ba363b1a0",
        "metadata.json": "d04e81770eac358a27afb8f9ca92b419a0c558cd30a1f1ab113c991e3484ea64",
    },
    "parse_citations": {
        "appraisal_report_page_0.png": "2c109c531094705052272607c5c48de653596e9d93f38cc349e766ea24f8bf6b",
        "elements.json": "42e79cc0d1866b1c0d166cf5c90b3b0025a647be33572913a0213eecbd8c8615",
        "index.html": "5c72f30c8644a488ba6d5f6ec85b0b01f8e78fe5ef857e4eb6f94a1b49067b5a",
    },
    "rma_extraction": {
        "index.html": "fc391170fb2691c7ecb9c72cfa0589f4e465308ab8ba963cd678298c30740fee",
        "metadata.json": "74fde3087eb56c4b3022681aac9a8769ea96eea922872371ae796dd1cc874bbb",
        "rma_form_page_0.png": "c2b113900b13f0026fcb09fe14659745d40c0dc755af9c6c4d96c45fe4613746",
        "rma_form_page_1.png": "8e59143a303aad9f6c7587bc844db3cdcb743d5048070bc068fb3f83ecf4235a",
        "rma_form_page_2.png": "eb2be460d8e2dfa0b3204b90becd7965dced54ebfe50d8cce1e01c3c6c12fa52",
        "rma_form_page_3.png": "66eafba837166925534ab9aa7b7bff38c23132cf98dc25ebdc3baf9ffc25e6fd",
    },
    "sc100_extraction": {
        "index.html": "db9651fed7f6b37f13f18ce8a8d34a910fb9511d9b663a90d83b3ce75e0762fd",
        "metadata.json": "e064a49152be666bad499b0981f939aa9fc80e2343f1ceee2b4476b18ffc96a3",
        "sc100_page_0.png": "72722b7cac22b8dd77c4af0524566c1f39061fe66cb14225a0ea8c2dd86e7e36",
        "sc100_page_1.png": "857a924db862df1759d2094b4d14eea9fe36c7f36da780173b902da8cbbda98a",
        "sc100_page_2.png": "4be88b73498afa03fe124277efc02002a187d5fcccb995542d2eb66b2c71efe3",
        "sc100_page_3.png": "9b8be3c89e3dfc2dc9fc051b2e2d912297b311e370efa50815919dc2822d34f2",
    },
}
HOSTILE = "</script><script>alert(1)</script>"
ESCAPED_HOSTILE = "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
TEXT_LEAF_POSITIONS = ("first", "middle", "last")
EXTRACTION_NUMERIC_SINKS = (
    "page.width",
    "page.height",
    "bbox.x",
    "bbox.y",
    "bbox.width",
    "bbox.height",
    "confidence",
    "pageIndex",
)
PARSE_NUMERIC_SINKS = (
    "page.width",
    "page.height",
    "page.pageIndex",
    "bounds.x",
    "bounds.y",
    "bounds.width",
    "bounds.height",
    "confidence",
    "readingOrder",
)


class UnexpectedTransport(BaseException):
    """Escape broad ``except Exception`` handlers when offline replay regresses."""


def _copy_demo(tmp_path: Path, demo_name: str) -> Path:
    destination = tmp_path / "demos" / demo_name
    shutil.copytree(REPO_ROOT / "demos" / demo_name, destination)
    return destination


def _load_generator(demo_dir: Path) -> ModuleType:
    generator_path = demo_dir / "generate_demo.py"
    module_name = f"test_generator_{demo_dir.name}_{id(demo_dir)}"
    spec = importlib.util.spec_from_file_location(module_name, generator_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load generator at {generator_path}")
    module = importlib.util.module_from_spec(spec)
    original_path = sys.path.copy()
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    return module


def _output_artifact_hashes(demo_dir: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((demo_dir / "output").iterdir())
        if path.is_file()
    }


def _cache_file(demo_dir: Path) -> Path:
    cache_files = list((demo_dir / "cache").glob("*.json"))
    assert len(cache_files) == 1
    return cache_files[0]


def _rewrite_cache(
    demo_dir: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    cache_file = _cache_file(demo_dir)
    response = json.loads(cache_file.read_text(encoding="utf-8"))
    mutate(response)
    cache_file.write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _rendered_extraction_leaves(
    data_node: Any,
    meta_node: Any,
) -> list[tuple[Any, str | int, dict[str, Any]]]:
    leaves: list[tuple[Any, str | int, dict[str, Any]]] = []
    if isinstance(data_node, dict):
        for key, child in data_node.items():
            child_meta = meta_node.get(key, {}) if isinstance(meta_node, dict) else {}
            if isinstance(child, (dict, list)):
                leaves.extend(_rendered_extraction_leaves(child, child_meta))
            elif isinstance(child_meta, dict) and child_meta.get("bbox"):
                leaves.append((data_node, key, child_meta))
    elif isinstance(data_node, list):
        meta_list = meta_node if isinstance(meta_node, list) else []
        for index, child in enumerate(data_node):
            child_meta = meta_list[index] if index < len(meta_list) else {}
            if isinstance(child, (dict, list)):
                leaves.extend(_rendered_extraction_leaves(child, child_meta))
            elif isinstance(child_meta, dict) and child_meta.get("bbox"):
                leaves.append((data_node, index, child_meta))
    return leaves


def _rendered_parse_elements(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        element
        for element in response["output"]["elements"]
        if element.get("page", {}).get("pageIndex", 0) == 0
        and element.get("bounds")
        and element.get("text", "").strip()
    ]


def _position_index(length: int, position: str) -> int:
    if position == "first":
        return 0
    if position == "middle":
        return length // 2
    if position == "last":
        return length - 1
    raise AssertionError(f"Unknown leaf position: {position}")


def _inject_hostile(
    response: dict[str, Any],
    demo_name: str,
    position: str,
) -> None:
    output = response["output"]
    if demo_name == "parse_citations":
        elements = _rendered_parse_elements(response)
        assert len(elements) >= len(TEXT_LEAF_POSITIONS)
        elements[_position_index(len(elements), position)]["text"] = HOSTILE
        return

    leaves = _rendered_extraction_leaves(output["data"], output["metadata"])
    assert len(leaves) >= len(TEXT_LEAF_POSITIONS)
    container, key, _metadata = leaves[_position_index(len(leaves), position)]
    container[key] = HOSTILE


def _inject_non_numeric_extraction_sink(
    response: dict[str, Any],
    sink: str,
) -> None:
    output = response["output"]
    if sink.startswith("page."):
        key = sink.removeprefix("page.")
        assert output["pages"]
        for page in output["pages"]:
            page[key] = "not-a-number"
        return

    leaves = _rendered_extraction_leaves(output["data"], output["metadata"])
    assert leaves
    for _container, _key, metadata in leaves:
        if sink.startswith("bbox."):
            metadata["bbox"][sink.removeprefix("bbox.")] = "not-a-number"
        else:
            metadata[sink] = "not-a-number"


def _inject_non_numeric_parse_sink(
    response: dict[str, Any],
    sink: str,
) -> None:
    elements = _rendered_parse_elements(response)
    assert elements
    container_name, key = sink.split(".", 1) if "." in sink else ("", sink)
    for element in elements:
        container = element[container_name] if container_name else element
        container[key] = "not-a-number"


def _inject_non_dict_bounds(
    response: dict[str, Any],
    demo_name: str,
) -> None:
    if demo_name == "parse_citations":
        elements = _rendered_parse_elements(response)
        assert elements
        elements[0]["bounds"] = ["not", "a", "mapping"]
        return

    output = response["output"]
    leaves = _rendered_extraction_leaves(output["data"], output["metadata"])
    assert leaves
    leaves[0][2]["bbox"] = ["not", "a", "mapping"]


def _fail_transport(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise UnexpectedTransport("cache replay selected a network transport")


@pytest.mark.parametrize("demo_name", DEMOS)
def test_committed_cache_replay_is_offline_and_preserves_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_name: str,
) -> None:
    demo_dir = _copy_demo(tmp_path, demo_name)
    monkeypatch.setenv("NUTRIENT_API_KEY", "")
    monkeypatch.setattr(common_cache, "_transport_for", _fail_transport)
    monkeypatch.setattr(common_cache, "extract_transport", _fail_transport)
    monkeypatch.setattr(common_cache, "parse_transport", _fail_transport)

    generator = _load_generator(demo_dir)
    asyncio.run(generator.main(refresh=False))

    assert _output_artifact_hashes(demo_dir) == EXPECTED_ARTIFACT_SHA256[demo_name]


@pytest.mark.parametrize("position", TEXT_LEAF_POSITIONS)
@pytest.mark.parametrize("demo_name", DEMOS)
def test_hostile_cached_document_values_are_escaped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_name: str,
    position: str,
) -> None:
    demo_dir = _copy_demo(tmp_path, demo_name)
    _rewrite_cache(
        demo_dir,
        lambda response: _inject_hostile(response, demo_name, position),
    )
    monkeypatch.setenv("NUTRIENT_API_KEY", "")
    monkeypatch.setattr(common_cache, "_transport_for", _fail_transport)

    generator = _load_generator(demo_dir)
    asyncio.run(generator.main(refresh=False))

    rendered = (demo_dir / "output" / "index.html").read_text(encoding="utf-8")
    assert HOSTILE not in rendered
    assert ESCAPED_HOSTILE in rendered


@pytest.mark.parametrize(
    ("demo_name", "sink"),
    [
        (demo_name, sink)
        for demo_name in EXTRACTION_DEMOS
        for sink in EXTRACTION_NUMERIC_SINKS
    ]
    + [
        ("parse_citations", sink)
        for sink in PARSE_NUMERIC_SINKS
    ],
)
def test_non_numeric_template_sink_fails_before_template_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_name: str,
    sink: str,
) -> None:
    demo_dir = _copy_demo(tmp_path, demo_name)
    if demo_name == "parse_citations":
        mutate = lambda response: _inject_non_numeric_parse_sink(response, sink)
    else:
        mutate = lambda response: _inject_non_numeric_extraction_sink(response, sink)
    _rewrite_cache(demo_dir, mutate)
    monkeypatch.setenv("NUTRIENT_API_KEY", "")
    monkeypatch.setattr(common_cache, "_transport_for", _fail_transport)
    generator = _load_generator(demo_dir)
    monkeypatch.setattr(
        generator,
        "create_html_env",
        lambda *_args, **_kwargs: pytest.fail(
            f"non-numeric {sink} reached template construction"
        ),
    )

    with pytest.raises(ValueError, match="numeric"):
        asyncio.run(generator.main(refresh=False))


@pytest.mark.parametrize("demo_name", DEMOS)
def test_non_dict_bbox_uses_numeric_value_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_name: str,
) -> None:
    demo_dir = _copy_demo(tmp_path, demo_name)
    _rewrite_cache(
        demo_dir,
        lambda response: _inject_non_dict_bounds(response, demo_name),
    )
    monkeypatch.setenv("NUTRIENT_API_KEY", "")
    monkeypatch.setattr(common_cache, "_transport_for", _fail_transport)
    generator = _load_generator(demo_dir)

    with pytest.raises(ValueError, match="^value must be numeric$"):
        asyncio.run(generator.main(refresh=False))


@pytest.mark.parametrize("demo_name", DEMOS)
def test_template_avoids_unsafe_escape_bypasses(demo_name: str) -> None:
    template = (
        REPO_ROOT / "demos" / demo_name / "template.html"
    ).read_text(encoding="utf-8")

    banned = {
        "safe filter": r"\|\s*safe\b",
        "disabled autoescape": r"{%\s*autoescape\s+false\b",
        "raw block": r"{%\s*raw\b",
    }
    for label, pattern in banned.items():
        assert re.search(pattern, template, flags=re.IGNORECASE) is None, label

    attribute_script_json = re.compile(
        r"<[^>]*{{[^}]*\bscript_safe_json\b[^}]*}}[^>]*>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert attribute_script_json.search(template) is None
