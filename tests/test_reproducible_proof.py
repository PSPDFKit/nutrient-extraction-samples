from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from common.api import build_extract_instructions


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = REPO_ROOT / "demos" / "grounded_extraction"


def _load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as source_file:
        return json.load(source_file)


def test_published_instructions_match_the_generator_contract() -> None:
    configs = _load_json(DEMO_ROOT / "docs.json")
    assert isinstance(configs, list) and len(configs) == 1
    config = configs[0]
    assert isinstance(config, dict)

    expected = build_extract_instructions(config["mode"], config["schema"])

    assert _load_json(DEMO_ROOT / "instructions.json") == expected


def test_proof_document_links_every_published_artifact() -> None:
    proof = (REPO_ROOT / "docs" / "reproducible-proof.md").read_text(
        encoding="utf-8"
    )
    required_paths = (
        "demos/grounded_extraction/data/CMS-1500.pdf",
        "demos/grounded_extraction/instructions.json",
        "demos/grounded_extraction/expected.json",
        "demos/grounded_extraction/check_expected.py",
        "demos/grounded_extraction/output/index.html",
        "demos/grounded_extraction/output/metadata.json",
    )

    for relative_path in required_paths:
        assert (REPO_ROOT / relative_path).is_file()
        assert relative_path in proof

    cache_files = list((DEMO_ROOT / "cache").glob("*.json"))
    assert len(cache_files) == 1
    assert cache_files[0].relative_to(REPO_ROOT).as_posix() in proof

    assert "https://api.nutrient.io/extraction/extract" in proof
    assert "python -m pytest -q" in proof
    assert "python check_expected.py" in proof


def _run_checker(tmp_path: Path, mutate: str | None = None) -> subprocess.CompletedProcess[str]:
    response = _load_json(DEMO_ROOT / "output" / "metadata.json")
    assert isinstance(response, dict)
    output = response["output"]
    assert isinstance(output, dict)

    if mutate == "missing":
        del output["data"]["patient_name"]
    elif mutate == "wrong":
        output["data"]["patient_name"] = "Wrong Person"
    elif mutate == "ungrounded":
        del output["metadata"]["patient_name"]["bbox"]
    elif mutate == "source_corrected":
        for service_line in output["data"]["service_lines"]:
            service_line["date_of_service_from"] = "07 10 26"

    response_path = tmp_path / "response.json"
    response_path.write_text(json.dumps(response), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(DEMO_ROOT / "check_expected.py"),
            "--response",
            str(response_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_checker_reports_known_wrong_dates_in_reviewed_response(tmp_path: Path) -> None:
    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert (
        "WRONG $.service_lines[0].date_of_service_from: "
        "expected '07 10 26', got '10 26 07'"
    ) in result.stdout
    assert (
        "WRONG $.service_lines[1].date_of_service_from: "
        "expected '07 10 26', got '10 07'"
    ) in result.stdout


def test_checker_accepts_a_source_corrected_response(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, "source_corrected")

    assert result.returncode == 0
    assert result.stdout.startswith("PASS:")


def test_checker_classifies_missing_wrong_and_ungrounded_fields(
    tmp_path: Path,
) -> None:
    for mutation, label in (
        ("missing", "MISSING $.patient_name"),
        ("wrong", "WRONG $.patient_name"),
        ("ungrounded", "UNGROUNDED $.patient_name"),
    ):
        result = _run_checker(tmp_path, mutation)
        assert result.returncode == 1
        assert label in result.stdout
