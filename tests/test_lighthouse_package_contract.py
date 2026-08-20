from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import common.lighthouse_package as lighthouse_package
import demos.prior_authorization.build_public_form as prior_authorization_builder
from common.lighthouse import (
    COMMITTED_CACHE_KEYS,
    LighthouseError,
    PUBLIC_FORM_SOURCE_STATUS,
    build_synthetic_pdf,
    committed_response_digest,
    expected_from_fixture,
    load_committed_live_evidence,
    parse_fixture,
)
from common.lighthouse_package import (
    PackageConfig,
    build_checker_parser,
    build_generator_parser,
    build_provisional_envelope,
    checker_main,
    generator_main,
    live_evidence_paths,
    load_document_config,
    load_fixture_and_expected,
)
from demos.insurance_claim_intake.generate_demo import CONFIG as INSURANCE_CONFIG
from demos.mortgage_verification.generate_demo import CONFIG as MORTGAGE_CONFIG
from demos.prior_authorization.generate_demo import CONFIG as HEALTHCARE_CONFIG


PACKAGE_CONFIGS = (MORTGAGE_CONFIG, INSURANCE_CONFIG, HEALTHCARE_CONFIG)
OUTPUT_ARTIFACTS = (
    "provisional/evidence.json",
    "provisional/output/source-page.png",
    "provisional/output/comparison.json",
    "provisional/output/index.html",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def test_prior_authorization_builder_checks_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "prior-authorization.pdf"
    output.write_bytes(prior_authorization_builder.OUTPUT.read_bytes())
    before = output.read_bytes()
    monkeypatch.setattr(prior_authorization_builder, "OUTPUT", output)

    assert prior_authorization_builder.build(check=True) == (
        prior_authorization_builder.DERIVED_SHA256
    )
    assert output.read_bytes() == before


def test_prior_authorization_builder_never_overwrites_on_digest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "prior-authorization.pdf"
    output.write_bytes(b"reviewed-input-must-survive")
    monkeypatch.setattr(prior_authorization_builder, "OUTPUT", output)
    monkeypatch.setattr(prior_authorization_builder, "DERIVED_SHA256", "0" * 64)

    with pytest.raises(ValueError, match="derived demo SHA-256 mismatch"):
        prior_authorization_builder.build(check=False)
    assert output.read_bytes() == b"reviewed-input-must-survive"


def _copy_config(tmp_path: Path, original: PackageConfig) -> PackageConfig:
    destination = tmp_path / original.slug
    destination.mkdir()
    for filename in ("fixture.json", "docs.json", "expected.json"):
        shutil.copy2(original.demo_dir / filename, destination / filename)
    fixture = _json(original.demo_dir / "fixture.json")
    relative_pdf = Path(fixture["document"]["filename"])
    copied_pdf = destination / relative_pdf
    copied_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original.demo_dir / relative_pdf, copied_pdf)
    return replace(original, demo_dir=destination)


def _public_form_config(
    tmp_path: Path,
    *,
    declared_width: int = 612,
    declared_height: int = 792,
) -> PackageConfig:
    slug = "public_form_demo"
    demo_dir = tmp_path / slug
    source_path = demo_dir / "data" / "privacy-safe-public-form.pdf"
    source_path.parent.mkdir(parents=True)
    generated_fixture = parse_fixture(
        {
            "version": 1,
            "slug": slug,
            "sourceStatus": "synthetic",
            "document": {
                "filename": "data/generated.pdf",
                "title": "Test-only PDF",
                "subtitle": "Package contract test source",
                "width": 612,
                "height": 792,
            },
            "fields": [
                {
                    "path": ["applicant", "name"],
                    "label": "Applicant name",
                    "value": "Alex Example",
                }
            ],
        }
    )
    source_payload = build_synthetic_pdf(generated_fixture)
    source_path.write_bytes(source_payload)
    fixture_value = {
        "version": 2,
        "slug": slug,
        "sourceStatus": PUBLIC_FORM_SOURCE_STATUS,
        "document": {
            "filename": "data/privacy-safe-public-form.pdf",
            "title": "Official Form 123 demo",
            "subtitle": "Authentic public form with privacy-safe demo values",
            "width": declared_width,
            "height": declared_height,
        },
        "provenance": {
            "publisher": "Example Public Agency",
            "officialFormName": "Official Form 123",
            "canonicalSourceUrl": "https://www.example.gov/forms/official-123.pdf",
            "originalSha256": "1" * 64,
            "sourceSha256": hashlib.sha256(source_payload).hexdigest(),
        },
        "fields": [
            {
                "path": ["applicant", "name"],
                "label": "Applicant name",
                "value": "Alex Example",
                "source": {
                    "pageIndex": 0,
                    "bbox": {"x": 13, "y": 17, "width": 101, "height": 19},
                },
            }
        ],
    }
    _write_json(demo_dir / "fixture.json", fixture_value)
    fixture = parse_fixture(fixture_value, expected_slug=slug)
    _write_json(demo_dir / "expected.json", expected_from_fixture(fixture))
    _write_json(
        demo_dir / "docs.json",
        [
            {
                "id": slug,
                "name": "Official Form 123",
                "file": "data/privacy-safe-public-form.pdf",
                "mode": "extract",
                "schema": {
                    "type": "object",
                    "properties": {
                        "applicant": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        }
                    },
                },
            }
        ],
    )
    return PackageConfig(
        demo_dir=demo_dir,
        slug=slug,
        page_title="Official public form proof",
        provisional_summary="Offline public-form layout proof.",
        live_summary="Live public-form evidence requires review.",
        reviewed_summary="Reviewed public-form evidence.",
    )


def _hashes(config: PackageConfig) -> dict[str, str]:
    return {
        relative: hashlib.sha256((config.demo_dir / relative).read_bytes()).hexdigest()
        for relative in OUTPUT_ARTIFACTS
    }


class _NoEnvironmentAccess(dict[str, str]):
    def get(self, key: str, default: Any = None) -> Any:
        raise AssertionError(f"offline mode read environment key {key}")


@pytest.mark.parametrize("original", PACKAGE_CONFIGS, ids=lambda item: item.slug)
def test_provisional_generation_is_offline_exact_and_deterministic(
    tmp_path: Path,
    original: PackageConfig,
) -> None:
    config = _copy_config(tmp_path, original)

    def forbidden_transport(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("offline mode called the live transport")

    first_exit = generator_main(
        config,
        ["--provisional"],
        transport=forbidden_transport,
        environment=_NoEnvironmentAccess(),
    )
    first_hashes = _hashes(config)
    second_exit = generator_main(
        config,
        ["--provisional"],
        transport=forbidden_transport,
        environment=_NoEnvironmentAccess(),
    )

    assert first_exit == second_exit == 0
    assert first_hashes == _hashes(config)
    assert not config.cache_dir.exists()

    envelope = _json(config.provisional_path)
    assert set(envelope) == {"sourceStatus", "response"}
    assert envelope["sourceStatus"] == "provisional-layout"
    assert set(envelope["response"]) == COMMITTED_CACHE_KEYS
    assert set(envelope["response"]["output"]) == {"data", "metadata", "pages"}

    artifact = _json(config.provisional_output_comparison_path)
    assert set(artifact) == {
        "artifactVersion",
        "evidenceKind",
        "evidenceLabel",
        "reviewed",
        "comparison",
    }
    assert artifact["artifactVersion"] == 1
    assert artifact["evidenceKind"] == "provisional"
    assert artifact["reviewed"] is False
    assert set(artifact["comparison"]) == {
        "passed",
        "exitCode",
        "expectedLeaves",
        "matchedLeaves",
        "groundedLeaves",
        "issues",
    }

    html = config.provisional_output_html_path.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html
    assert "http://" not in html
    assert "https://" not in html
    assert "PROVISIONAL LAYOUT MATCH · NO API CALL" in html
    assert ">Pass<" not in html
    assert "background: var(--citrus);" in html
    assert "background: var(--success);" not in html


def test_public_form_uses_current_explicit_insurance_damage_box() -> None:
    fixture, expected = load_fixture_and_expected(INSURANCE_CONFIG)
    envelope = build_provisional_envelope(fixture, expected)
    damage = envelope["response"]["output"]["metadata"]["federal_vehicle"][
        "damage"
    ]

    assert damage == {
        "pageIndex": 0,
        "bbox": {
            "x": 36.86,
            "y": 196.6,
            "width": 538.34,
            "height": 12.31,
        },
    }
    assert damage["bbox"]["x"] + damage["bbox"]["width"] <= fixture.page_width
    assert damage["bbox"]["y"] + damage["bbox"]["height"] <= fixture.page_height


@pytest.mark.parametrize("original", PACKAGE_CONFIGS, ids=lambda item: item.slug)
def test_provisional_commands_never_overwrite_reviewed_outputs(
    tmp_path: Path,
    original: PackageConfig,
) -> None:
    config = _copy_config(tmp_path, original)
    reviewed = {
        config.output_image_path: b"reviewed-image",
        config.output_comparison_path: b"reviewed-comparison",
        config.output_html_path: b"reviewed-html",
    }
    for path, payload in reviewed.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    assert generator_main(config, ["--provisional"]) == 0
    assert checker_main(config, ["--allow-provisional"]) == 0

    assert all(path.read_bytes() == payload for path, payload in reviewed.items())
    assert config.provisional_output_image_path.is_file()
    assert config.provisional_output_comparison_path.is_file()
    assert config.provisional_output_html_path.is_file()


def test_public_form_provisional_uses_only_explicit_independent_boxes_and_copy(
    tmp_path: Path,
) -> None:
    config = _public_form_config(tmp_path)
    fixture, expected = load_fixture_and_expected(config)

    envelope = build_provisional_envelope(fixture, expected)
    source = envelope["response"]["output"]["metadata"]["applicant"]["name"]
    assert source == {
        "pageIndex": 0,
        "bbox": {"x": 13.0, "y": 17.0, "width": 101.0, "height": 19.0},
    }

    assert generator_main(
        config,
        ["--provisional"],
        transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("offline public-form mode called the live transport")
        ),
        environment=_NoEnvironmentAccess(),
    ) == 0
    html = config.provisional_output_html_path.read_text(encoding="utf-8")
    assert "Reviewed evidence / authentic public form" in html
    assert "Authentic public form · privacy-safe demo values · page 1" in html
    assert "customer data" not in html.lower()
    assert "synthetic fixture" not in html.lower()
    assert "primary regions returned" in html
    assert "source grounded" not in html


def test_public_form_package_rejects_source_hash_and_page_dimension_drift(
    tmp_path: Path,
) -> None:
    hash_config = _public_form_config(tmp_path / "hash")
    source_path = hash_config.demo_dir / "data" / "privacy-safe-public-form.pdf"
    source_path.write_bytes(source_path.read_bytes() + b"\nmutated")
    with pytest.raises(LighthouseError, match="sourceSha256"):
        load_fixture_and_expected(hash_config)

    dimension_config = _public_form_config(
        tmp_path / "dimensions",
        declared_width=700,
    )
    with pytest.raises(LighthouseError, match="dimensions do not exactly match"):
        load_fixture_and_expected(dimension_config)


def test_public_form_checker_rejects_provisional_box_substitution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _public_form_config(tmp_path)
    assert generator_main(config, ["--provisional"]) == 0
    envelope = _json(config.provisional_path)
    envelope["response"]["output"]["metadata"]["applicant"]["name"]["bbox"][
        "x"
    ] = 14
    _write_json(config.provisional_path, envelope)

    assert checker_main(config, ["--allow-provisional"]) == 1
    assert "does not exactly match its independent fixture values and source boxes" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("original", PACKAGE_CONFIGS, ids=lambda item: item.slug)
def test_missing_live_evidence_exits_one_without_provisional_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    original: PackageConfig,
) -> None:
    config = _copy_config(tmp_path, original)

    assert generator_main(config, ["--replay-live"]) == 1
    assert checker_main(config, []) == 1

    captured = capsys.readouterr()
    assert "No provisional fallback was used" in captured.err
    assert not config.provisional_path.exists()
    assert not config.output_html_path.exists()


def test_broad_live_response_is_projected_in_memory_and_mismatch_is_retained(
    tmp_path: Path,
) -> None:
    config = _copy_config(tmp_path, MORTGAGE_CONFIG)
    fixture, expected = load_fixture_and_expected(config)
    provisional = build_provisional_envelope(fixture, expected)["response"]
    broad_data = json.loads(json.dumps(expected))
    broad_data["transport_visible_extra"] = "document-extra-preserved"
    broad_metadata = json.loads(json.dumps(provisional["output"]["metadata"]))
    broad_metadata["transport_visible_extra"] = {
        "pageIndex": 0,
        "bbox": {"x": 12, "y": 12, "width": 80, "height": 16},
    }
    raw_marker = "RAW-ONLY-MARKER-MUST-NEVER-BE-WRITTEN"
    broad_response = {
        "status": 200,
        "requestId": "request-broad-live-1",
        "configuration": {"rawMarker": raw_marker},
        "metrics": {"rawMarker": raw_marker},
        "output": {
            "data": broad_data,
            "metadata": broad_metadata,
            "pages": provisional["output"]["pages"],
            "transportDebug": {"rawMarker": raw_marker},
        },
        "reconstructed": False,
        "rawTopLevel": raw_marker,
    }

    def fake_transport(
        _pdf: bytes,
        _filename: str,
        _instructions: Any,
        api_key: str,
    ) -> dict[str, Any]:
        assert api_key == "test-api-key-not-a-real-secret"
        return broad_response

    exit_code = generator_main(
        config,
        ["--refresh"],
        transport=fake_transport,
        environment={"NUTRIENT_API_KEY": "test-api-key-not-a-real-secret"},
    )

    assert exit_code == 1
    document = load_document_config(config, fixture)
    response_path, receipt_path = live_evidence_paths(config, fixture, document)
    cache = _json(response_path)
    receipt = _json(receipt_path)
    assert set(cache) == COMMITTED_CACHE_KEYS
    assert set(cache["output"]) == {"data", "metadata", "pages"}
    assert "configuration" not in cache
    assert "metrics" not in cache
    assert "rawTopLevel" not in cache
    assert "transportDebug" not in cache["output"]
    assert cache["output"]["data"]["transport_visible_extra"] == (
        "document-extra-preserved"
    )
    assert receipt["requestId"] == cache["requestId"]
    assert receipt["projectedResponseSha256"] == committed_response_digest(cache)
    assert sorted(path.name for path in config.cache_dir.iterdir()) == sorted(
        [response_path.name, receipt_path.name]
    )
    assert raw_marker not in "".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in config.demo_dir.rglob("*")
        if path.is_file()
    )

    comparison = _json(config.output_comparison_path)["comparison"]
    assert comparison["passed"] is False
    assert comparison["exitCode"] == 1
    assert any(
        issue["code"] == "UNEXPECTED"
        and issue["path"] == "$.transport_visible_extra"
        for issue in comparison["issues"]
    )


def test_live_replay_requires_request_and_digest_binding(tmp_path: Path) -> None:
    config = _copy_config(tmp_path, HEALTHCARE_CONFIG)
    fixture, expected = load_fixture_and_expected(config)
    document = load_document_config(config, fixture)
    response = build_provisional_envelope(fixture, expected)["response"]
    response["requestId"] = "request-live-binding-1"
    response_path, receipt_path = live_evidence_paths(config, fixture, document)
    _write_json(response_path, response)
    receipt = {
        "receiptVersion": 1,
        "sourceStatus": "live-refresh",
        "requestId": response["requestId"],
        "projectedResponseSha256": committed_response_digest(response),
    }
    _write_json(receipt_path, receipt)

    assert load_committed_live_evidence(response_path, receipt_path).kind == "live"

    receipt["requestId"] = "different-request"
    _write_json(receipt_path, receipt)
    with pytest.raises(LighthouseError, match="requestId does not match"):
        load_committed_live_evidence(response_path, receipt_path)

    receipt["requestId"] = response["requestId"]
    receipt["projectedResponseSha256"] = "0" * 64
    _write_json(receipt_path, receipt)
    with pytest.raises(LighthouseError, match="digest does not match"):
        load_committed_live_evidence(response_path, receipt_path)


def test_checker_retains_provisional_mismatch_and_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _copy_config(tmp_path, INSURANCE_CONFIG)
    assert generator_main(config, ["--provisional"]) == 0
    exact_envelope = config.provisional_path.read_bytes()
    original_loader = lighthouse_package.load_fixture_and_expected

    def load_with_changed_expected(
        selected_config: PackageConfig,
    ) -> tuple[Any, Any]:
        fixture, expected = original_loader(selected_config)
        changed_expected = json.loads(json.dumps(expected))
        changed_expected["other_vehicle"]["insurance"]["policy_number"] = (
            "WRONG-POLICY"
        )
        return fixture, changed_expected

    monkeypatch.setattr(
        lighthouse_package,
        "load_fixture_and_expected",
        load_with_changed_expected,
    )

    assert checker_main(config, ["--allow-provisional"]) == 1
    assert config.provisional_path.read_bytes() == exact_envelope
    artifact = _json(config.provisional_output_comparison_path)
    assert artifact["comparison"]["exitCode"] == 1
    assert any(
        issue["code"] == "WRONG"
        and issue["path"] == "$.other_vehicle.insurance.policy_number"
        for issue in artifact["comparison"]["issues"]
    )


@pytest.mark.parametrize("original", PACKAGE_CONFIGS, ids=lambda item: item.slug)
def test_expected_fixture_drift_blocks_generator_and_checker_before_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    original: PackageConfig,
) -> None:
    config = _copy_config(tmp_path, original)
    config.expected_path.write_text("{}\n", encoding="utf-8")

    assert generator_main(config, ["--provisional"]) == 1
    assert checker_main(config, ["--allow-provisional"]) == 1
    captured = capsys.readouterr()
    assert captured.err.count("expected.json does not exactly match") == 2
    assert not config.provisional_path.exists()


def _options(parser: Any) -> set[str]:
    return {
        option
        for action in parser._actions
        for option in action.option_strings
        if option != "--help" and option != "-h"
    }


@pytest.mark.parametrize("config", PACKAGE_CONFIGS, ids=lambda item: item.slug)
def test_all_packages_expose_only_the_normalized_cli_flags(
    config: PackageConfig,
) -> None:
    generator = build_generator_parser(config)
    checker = build_checker_parser(config)

    assert _options(generator) == {
        "--provisional",
        "--refresh",
        "--replay-live",
        "--replay-reviewed",
    }
    assert _options(checker) == {"--allow-provisional", "--reviewed-live"}
    with pytest.raises(SystemExit) as missing_mode:
        generator.parse_args([])
    assert missing_mode.value.code == 2
    with pytest.raises(SystemExit):
        generator.parse_args(["--provisional", "--refresh"])
    with pytest.raises(SystemExit):
        checker.parse_args(["--allow-provisional", "--reviewed-live"])


@pytest.mark.parametrize("config", PACKAGE_CONFIGS, ids=lambda item: item.slug)
def test_readme_uses_the_normalized_commands_and_preserves_no_fallback_language(
    config: PackageConfig,
) -> None:
    readme = (config.demo_dir / "README.md").read_text(encoding="utf-8")
    relative_script = f"demos/{config.slug}"

    for command in (
        f"python3 {relative_script}/generate_demo.py --provisional",
        f"python3 {relative_script}/check_expected.py --allow-provisional",
        f"python3 {relative_script}/generate_demo.py --refresh",
        f"python3 {relative_script}/check_expected.py",
        f"python3 {relative_script}/generate_demo.py --replay-live",
        f"python3 {relative_script}/generate_demo.py --replay-reviewed",
        f"python3 {relative_script}/check_expected.py --reviewed-live",
    ):
        assert command in readme
    assert "never fall back to provisional evidence" in readme
    assert "--reviewed-replay" not in readme
    assert "--replay-reviewed-live" not in readme


@pytest.mark.skipif(
    os.environ.get("NUTRIENT_LIGHTHOUSE_PLAYWRIGHT") != "1",
    reason=(
        "set NUTRIENT_LIGHTHOUSE_PLAYWRIGHT=1 to run the opt-in local-browser "
        "sticky-verdict regression"
    ),
)
def test_playwright_mobile_provisional_verdict_stays_visible_after_card_scroll(
    tmp_path: Path,
) -> None:
    """Exercise the real 390x844 sticky containing block for all packages."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.fail(
            "NUTRIENT_LIGHTHOUSE_PLAYWRIGHT=1 requires an available Playwright "
            "Python runtime and Chromium browser"
        )

    configs = [_copy_config(tmp_path, original) for original in PACKAGE_CONFIGS]
    for config in configs:
        assert generator_main(config, ["--provisional"]) == 0

    def leaf_paths(
        value: Any,
        path: tuple[str | int, ...] = (),
    ) -> list[tuple[str | int, ...]]:
        if isinstance(value, dict) and value:
            return [
                leaf
                for key in sorted(value)
                for leaf in leaf_paths(value[key], path + (key,))
            ]
        if isinstance(value, list) and value:
            return [
                leaf
                for index, child in enumerate(value)
                for leaf in leaf_paths(child, path + (index,))
            ]
        return [path]

    def rendered_path(path: tuple[str | int, ...]) -> str:
        result = "$"
        for part in path:
            if isinstance(part, int):
                result += f"[{part}]"
            elif part.isascii() and part.isidentifier():
                result += f".{part}"
            else:
                result += f"[{json.dumps(part, ensure_ascii=False)}]"
        return result

    targets: list[tuple[PackageConfig, str]] = []
    for config in configs:
        fixture, expected = load_fixture_and_expected(config)
        assert fixture.source_status == PUBLIC_FORM_SOURCE_STATUS
        current_leaf_paths = leaf_paths(expected)
        assert len(current_leaf_paths) == len(fixture.fields)
        targets.append((config, rendered_path(current_leaf_paths[-1])))

    expected_verdict = "PROVISIONAL LAYOUT MATCH · NO API CALL"
    viewport = {"width": 390, "height": 844}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport=viewport)
            for config, field_path in targets:
                page.goto(config.provisional_output_html_path.as_uri(), wait_until="load")
                card = page.locator(".field-card", has_text=field_path)
                assert card.count() == 1, field_path
                assert card.evaluate(
                    "element => element === element.parentElement.lastElementChild"
                )
                card.scroll_into_view_if_needed()
                page.wait_for_timeout(50)

                verdict = page.locator(".results-head .verdict")
                assert verdict.inner_text().strip() == expected_verdict
                assert verdict.is_visible()
                bounds = verdict.bounding_box()
                assert bounds is not None
                assert 0 <= bounds["x"]
                assert bounds["x"] + bounds["width"] <= viewport["width"]
                assert 0 <= bounds["y"]
                assert bounds["y"] + bounds["height"] <= viewport["height"]
        finally:
            browser.close()
