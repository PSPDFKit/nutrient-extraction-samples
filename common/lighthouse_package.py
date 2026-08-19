"""One evidence and CLI contract for every lighthouse vertical package.

The vertical scripts intentionally contain only copy and a ``PackageConfig``.
This module owns the evidence boundary: fixture-derived provisional layout data
is always tagged as provisional, while live evidence can only be created by an
explicit in-memory transport call and replayed from a narrow cache plus receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import math
import os
import sys
import textwrap
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

import pypdfium2 as pdfium

from . import api as nutrient_api
from .api import EXTRACT_ENDPOINT, ApiError, build_extract_instructions
from .atomic import atomic_write
from .cache import MAX_PDF_BYTES, cache_path
from .lighthouse import (
    COMMITTED_CACHE_KEYS,
    LIVE_RECEIPT_SOURCE_STATUS,
    PROVISIONAL_SOURCE_STATUS,
    LighthouseError,
    LighthouseEvidence,
    LiveRefreshEvidence,
    LighthouseFixture,
    ProvisionalEvidence,
    PublicFormFixture,
    SyntheticFixture,
    committed_response_digest,
    compare_evidence,
    expected_from_fixture,
    load_committed_live_evidence,
    load_fixture,
    load_provisional_evidence,
    project_committed_cache,
    render_lighthouse_page,
    validate_committed_cache,
)
from .render import ensure_page_png


Transport: TypeAlias = Callable[
    [bytes, str, Mapping[str, Any], str],
    Awaitable[dict[str, Any]] | dict[str, Any],
]

_DOCUMENT_CONFIG_KEYS = frozenset({"id", "name", "file", "mode", "schema"})
_OUTPUT_KEYS = frozenset({"data", "metadata", "pages"})
_MAX_REPOSITORY_JSON_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class PackageConfig:
    """Vertical copy and paths consumed by the shared package runner."""

    demo_dir: Path
    slug: str
    page_title: str
    provisional_summary: str
    live_summary: str
    reviewed_summary: str

    @property
    def fixture_path(self) -> Path:
        return self.demo_dir / "fixture.json"

    @property
    def docs_path(self) -> Path:
        return self.demo_dir / "docs.json"

    @property
    def expected_path(self) -> Path:
        return self.demo_dir / "expected.json"

    @property
    def provisional_path(self) -> Path:
        return self.demo_dir / "provisional" / "evidence.json"

    @property
    def cache_dir(self) -> Path:
        return self.demo_dir / "cache"

    @property
    def output_dir(self) -> Path:
        return self.demo_dir / "output"

    @property
    def output_image_path(self) -> Path:
        return self.output_dir / "source-page.png"

    @property
    def output_comparison_path(self) -> Path:
        return self.output_dir / "comparison.json"

    @property
    def output_html_path(self) -> Path:
        return self.output_dir / "index.html"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _read_repository_json(path: Path, *, label: str) -> Any:
    """Read a small, regular JSON file without accepting duplicate keys."""

    try:
        if path.is_symlink() or not path.is_file():
            raise LighthouseError(f"{label} must be a regular, non-symlink file")
        if path.stat().st_size > _MAX_REPOSITORY_JSON_BYTES:
            raise LighthouseError(f"{label} exceeds the repository JSON size limit")
        payload = path.read_bytes()
    except LighthouseError:
        raise
    except OSError:
        raise LighthouseError(f"could not safely read {label}") from None

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise LighthouseError(f"{label} contains duplicate key {key!r}")
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
        raise LighthouseError(f"could not read valid {label} JSON") from None


def load_fixture_and_expected(
    config: PackageConfig,
) -> tuple[LighthouseFixture, Any]:
    """Load source truth and prove expected.json still derives from the fixture."""

    fixture = load_fixture(config.fixture_path, expected_slug=config.slug)
    if isinstance(fixture, PublicFormFixture):
        source_pdf_path(config, fixture)
    expected = _read_repository_json(config.expected_path, label="expected source truth")
    derived = expected_from_fixture(fixture)
    try:
        matches = _canonical_json(expected) == _canonical_json(derived)
    except (TypeError, ValueError, RecursionError):
        matches = False
    if not matches:
        raise LighthouseError(
            "expected.json does not exactly match expected_from_fixture(fixture); "
            "rebuild and review the fixture before using evidence"
        )
    return fixture, expected


def load_document_config(
    config: PackageConfig,
    fixture: LighthouseFixture,
) -> dict[str, Any]:
    documents = _read_repository_json(
        config.docs_path,
        label="document configuration",
    )
    if (
        not isinstance(documents, list)
        or len(documents) != 1
        or not isinstance(documents[0], dict)
    ):
        raise LighthouseError("docs.json must contain exactly one document object")
    document = documents[0]
    if set(document) != _DOCUMENT_CONFIG_KEYS:
        raise LighthouseError(
            "document configuration has unsupported or missing keys"
        )
    if document["id"] != config.slug or document["file"] != fixture.filename.as_posix():
        raise LighthouseError("document configuration does not match fixture identity")
    if not isinstance(document["name"], str) or not document["name"].strip():
        raise LighthouseError("document configuration name must be non-empty text")
    if not isinstance(document["mode"], str) or not document["mode"].strip():
        raise LighthouseError("document configuration mode must be non-empty text")
    if not isinstance(document["schema"], Mapping):
        raise LighthouseError("document configuration schema must be an object")
    return document


def _validate_public_form_source(
    source: Path,
    fixture: PublicFormFixture,
) -> None:
    try:
        payload = source.read_bytes()
    except OSError:
        raise LighthouseError("could not safely read the public-form source PDF") from None
    digest = hashlib.sha256(payload).hexdigest()
    if digest != fixture.provenance.source_sha256:
        raise LighthouseError(
            "public-form source PDF does not match provenance.sourceSha256"
        )

    document = None
    page = None
    try:
        document = pdfium.PdfDocument(source)
        if len(document) != 1:
            raise LighthouseError(
                "public-form source PDF must contain exactly one page"
            )
        page = document[0]
        width, height = page.get_size()
    except LighthouseError:
        raise
    except (OSError, RuntimeError, ValueError, pdfium.PdfiumError):
        raise LighthouseError(
            "public-form source PDF must be a readable one-page PDF"
        ) from None
    finally:
        if page is not None:
            page.close()
        if document is not None:
            document.close()
    if not (
        math.isclose(width, fixture.page_width, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(height, fixture.page_height, rel_tol=0.0, abs_tol=1e-6)
    ):
        raise LighthouseError(
            "public-form source PDF dimensions do not exactly match the fixture"
        )


def source_pdf_path(config: PackageConfig, fixture: LighthouseFixture) -> Path:
    source = config.demo_dir.joinpath(*fixture.filename.parts)
    try:
        if source.is_symlink() or not source.is_file():
            raise LighthouseError("source PDF must be a regular, non-symlink file")
        if source.stat().st_size > MAX_PDF_BYTES:
            raise LighthouseError("source PDF exceeds the size limit")
    except LighthouseError:
        raise
    except OSError:
        raise LighthouseError("could not safely inspect the source PDF") from None
    if isinstance(fixture, PublicFormFixture):
        _validate_public_form_source(source, fixture)
    return source


def _visible_scalar(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _estimated_helvetica_width(line: str) -> float:
    """Estimate the 12pt Helvetica width used by the deterministic fixture PDF."""

    width = 0.0
    for character in line:
        if character == " ":
            width += 3.35
        elif character in "ilI.,'!:;|":
            width += 3.0
        elif character in "MW@%&":
            width += 9.4
        elif character.isupper():
            width += 7.8
        elif character.isdigit():
            width += 6.7
        elif character in "-/()":
            width += 4.2
        else:
            width += 6.0
    return width


def provisional_field_boxes(
    fixture: SyntheticFixture,
) -> dict[tuple[str | int, ...], dict[str, Any]]:
    """Return source-aligned boxes for the shared two-column synthetic PDF.

    The geometry mirrors ``build_synthetic_pdf`` including its two-line wrap.
    It is deliberately fixture-derived layout data, never represented as API
    source metadata.
    """

    if not isinstance(fixture, SyntheticFixture):
        raise LighthouseError(
            "generated two-column geometry accepts only synthetic fixtures"
        )

    margin = 42.0
    gutter = 16.0
    columns = 2
    column_width = (fixture.page_width - (2 * margin) - gutter) / columns
    rows = math.ceil(len(fixture.fields) / columns)
    layout_top = fixture.page_height - 148.0
    layout_bottom = 38.0
    row_height = min(82.0, (layout_top - layout_bottom) / rows)
    if row_height < 58.0:
        raise LighthouseError("fixture fields do not fit the shared one-page layout")

    boxes: dict[tuple[str | int, ...], dict[str, Any]] = {}
    wrap_width = max(20, int(column_width / 6.5))
    for index, field in enumerate(fixture.fields):
        row = index // columns
        column = index % columns
        field_x = margin + column * (column_width + gutter)
        row_top = layout_top - row * row_height
        first_baseline = row_top - 41.0
        lines = textwrap.wrap(
            _visible_scalar(field.value),
            width=wrap_width,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        if len(lines) > 2:
            raise LighthouseError(
                f"fixture value for {field.label!r} no longer fits the source layout"
            )
        text_width = max(_estimated_helvetica_width(line) for line in lines)
        boxes[field.path] = {
            "pageIndex": 0,
            "bbox": {
                "x": round(field_x + 10.0, 2),
                "y": round(fixture.page_height - first_baseline - 11.0, 2),
                "width": round(
                    min(column_width - 20.0, max(28.0, text_width + 4.0)),
                    2,
                ),
                "height": round(16.0 + 15.0 * (len(lines) - 1), 2),
            },
        }
    return boxes


def _metadata_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _metadata_shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_metadata_shape(child) for child in value]
    return None


def _set_path(root: Any, path: tuple[str | int, ...], value: Any) -> None:
    cursor = root
    for part in path[:-1]:
        try:
            cursor = cursor[part]
        except (KeyError, IndexError, TypeError):
            raise LighthouseError(
                f"fixture layout path {path!r} does not match expected.json"
            ) from None
    try:
        cursor[path[-1]] = value
    except (KeyError, IndexError, TypeError):
        raise LighthouseError(
            f"fixture layout path {path!r} does not match expected.json"
        ) from None


def build_provisional_envelope(
    fixture: LighthouseFixture,
    expected: Any,
) -> dict[str, Any]:
    """Build the exact tagged provisional envelope used by every package."""

    metadata = _metadata_shape(expected)
    if isinstance(fixture, PublicFormFixture):
        boxes = {}
        for field in fixture.fields:
            if field.source_box is None:
                raise LighthouseError(
                    "public-form fixture field is missing its independent source box"
                )
            source_box = field.source_box.as_metadata()
            bbox = source_box["bbox"]
            if (
                source_box["pageIndex"] != 0
                or any(
                    isinstance(bbox[name], bool)
                    or not isinstance(bbox[name], (int, float))
                    or not math.isfinite(float(bbox[name]))
                    for name in ("x", "y", "width", "height")
                )
                or bbox["x"] < 0
                or bbox["y"] < 0
                or bbox["width"] <= 0
                or bbox["height"] <= 0
                or bbox["x"] + bbox["width"] > fixture.page_width
                or bbox["y"] + bbox["height"] > fixture.page_height
            ):
                raise LighthouseError(
                    "public-form fixture field has an invalid source box"
                )
            boxes[field.path] = source_box
    else:
        boxes = provisional_field_boxes(fixture)
    for field in fixture.fields:
        _set_path(metadata, field.path, boxes[field.path])

    output = {
        "data": expected_from_fixture(fixture),
        "metadata": metadata,
        "pages": [
            {"width": fixture.page_width, "height": fixture.page_height}
        ],
    }
    digest = hashlib.sha256(_canonical_json(output).encode("utf-8")).hexdigest()
    response = validate_committed_cache(
        {
            "status": 200,
            "requestId": f"provisional-layout-{fixture.slug}-{digest[:12]}",
            "output": output,
            "reconstructed": False,
        }
    )
    return {
        "sourceStatus": PROVISIONAL_SOURCE_STATUS,
        "response": response,
    }


def load_package_provisional(
    path: Path,
    *,
    fixture: LighthouseFixture | None = None,
    expected: Any = None,
) -> ProvisionalEvidence:
    evidence = load_provisional_evidence(path)
    response = validate_committed_cache(evidence.response)
    if set(response) != COMMITTED_CACHE_KEYS or set(response["output"]) != _OUTPUT_KEYS:
        raise LighthouseError(
            "provisional package response must use the exact cache-shaped envelope"
        )
    if isinstance(fixture, PublicFormFixture):
        if expected is None:
            raise LighthouseError(
                "public-form provisional validation requires expected source truth"
            )
        required = build_provisional_envelope(fixture, expected)["response"]
        if _canonical_json(response) != _canonical_json(required):
            raise LighthouseError(
                "public-form provisional evidence does not exactly match its "
                "independent fixture values and source boxes"
            )
    return evidence


def extraction_instructions(document: Mapping[str, Any]) -> dict[str, Any]:
    return build_extract_instructions(document["mode"], document["schema"])


def live_evidence_paths(
    config: PackageConfig,
    fixture: LighthouseFixture,
    document: Mapping[str, Any],
) -> tuple[Path, Path]:
    response_path = cache_path(
        source_pdf_path(config, fixture),
        EXTRACT_ENDPOINT,
        extraction_instructions(document),
        config.cache_dir,
    )
    receipt_path = response_path.with_name(f"{response_path.stem}.receipt.json")
    return response_path, receipt_path


def project_live_response(response: Any) -> dict[str, Any]:
    """Drop transport siblings while preserving the full document field trees."""

    if not isinstance(response, Mapping):
        raise LighthouseError("live Extract response must be a JSON object")
    output = response.get("output")
    if not isinstance(output, Mapping):
        raise LighthouseError("live Extract response is missing its output object")
    missing_output = _OUTPUT_KEYS - set(output)
    if missing_output:
        raise LighthouseError(
            "live Extract response is missing "
            + ", ".join(f"output.{key}" for key in sorted(missing_output))
        )
    projected = project_committed_cache(
        {
            "status": response.get("status"),
            "requestId": response.get("requestId"),
            "output": {
                "data": output["data"],
                "metadata": output["metadata"],
                "pages": output["pages"],
            },
            "reconstructed": response.get("reconstructed", False),
        }
    )
    if set(projected) != COMMITTED_CACHE_KEYS or set(projected["output"]) != _OUTPUT_KEYS:
        raise LighthouseError("live response did not project to the exact package envelope")
    marker = projected["reconstructed"]
    if projected["requestId"] == "reconstructed" or (
        marker is not None and marker is not False
    ):
        raise LighthouseError("reconstructed responses cannot be persisted as live evidence")
    return projected


def _live_receipt(projected: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "receiptVersion": 1,
        "sourceStatus": LIVE_RECEIPT_SOURCE_STATUS,
        "requestId": projected["requestId"],
        "projectedResponseSha256": committed_response_digest(projected),
    }


async def refresh_live_evidence(
    config: PackageConfig,
    fixture: LighthouseFixture,
    document: Mapping[str, Any],
    *,
    transport: Transport | None = None,
    environment: Mapping[str, str] | None = None,
) -> LiveRefreshEvidence:
    """Call Extract in memory and persist only an exact cache and bound receipt."""

    selected_environment = os.environ if environment is None else environment
    api_key = selected_environment.get("NUTRIENT_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        raise LighthouseError(
            "--refresh requires NUTRIENT_API_KEY in the current environment"
        )

    pdf_path = source_pdf_path(config, fixture)
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError:
        raise LighthouseError("could not read the source PDF") from None
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise LighthouseError("source PDF exceeds the size limit")

    selected_transport = transport or nutrient_api.extract_transport
    try:
        pending = selected_transport(
            pdf_bytes,
            pdf_path.name,
            extraction_instructions(document),
            api_key,
        )
        raw_response = await pending if inspect.isawaitable(pending) else pending
    except ApiError:
        raise
    except Exception:
        raise ApiError("Nutrient extract request failed.") from None

    projected = project_live_response(raw_response)
    serialized = _canonical_json(projected)
    if api_key in serialized:
        raise LighthouseError(
            "live Extract response contained sensitive request material and was not persisted"
        )

    response_path, receipt_path = live_evidence_paths(
        config,
        fixture,
        document,
    )
    receipt = _live_receipt(projected)
    # Both payloads are completely validated before either narrow destination is
    # replaced. A partial write still fails closed because replay requires both.
    response_payload = _json_bytes(projected)
    receipt_payload = _json_bytes(receipt)
    atomic_write(response_path, response_payload)
    atomic_write(receipt_path, receipt_payload)
    return load_committed_live_evidence(
        response_path,
        receipt_path,
        reviewed=False,
    )


def load_live_replay(
    config: PackageConfig,
    fixture: LighthouseFixture,
    document: Mapping[str, Any],
    *,
    reviewed: bool,
) -> LiveRefreshEvidence:
    response_path, receipt_path = live_evidence_paths(config, fixture, document)
    if not response_path.is_file() or not receipt_path.is_file():
        raise LighthouseError(
            "receipt-bound live evidence is unavailable because its cache or "
            "receipt is missing. No provisional fallback was used; select "
            "--provisional for generation or --allow-provisional for a "
            "layout-only check"
        )
    try:
        return load_committed_live_evidence(
            response_path,
            receipt_path,
            reviewed=reviewed,
        )
    except LighthouseError as error:
        raise LighthouseError(
            f"receipt-bound live evidence is invalid: {error}. No provisional "
            "fallback was used"
        ) from None


def comparison_artifact(
    evidence: LighthouseEvidence,
    report: Any,
) -> dict[str, Any]:
    return {
        "artifactVersion": 1,
        "evidenceKind": evidence.kind,
        "evidenceLabel": evidence.label,
        "reviewed": isinstance(evidence, LiveRefreshEvidence) and evidence.reviewed,
        "comparison": report.as_dict(),
    }


def _write_comparison(
    config: PackageConfig,
    evidence: LighthouseEvidence,
    report: Any,
) -> None:
    atomic_write(
        config.output_comparison_path,
        _json_bytes(comparison_artifact(evidence, report)),
    )


def _summary(config: PackageConfig, evidence: LighthouseEvidence) -> str:
    if isinstance(evidence, ProvisionalEvidence):
        return config.provisional_summary
    if evidence.reviewed:
        return config.reviewed_summary
    return config.live_summary


def write_generated_outputs(
    config: PackageConfig,
    fixture: LighthouseFixture,
    expected: Any,
    evidence: LighthouseEvidence,
) -> int:
    """Render complete artifacts and return the complete comparison exit code."""

    report = compare_evidence(expected, evidence)
    response = evidence.response
    page = response["output"]["pages"][0]
    pdf_path = source_pdf_path(config, fixture)
    ensure_page_png(
        pdf_path,
        0,
        config.output_image_path,
        page_dims=page,
        refresh=True,
    )
    _write_comparison(config, evidence, report)
    html = render_lighthouse_page(
        title=config.page_title,
        summary=_summary(config, evidence),
        document_name=fixture.title,
        document_image=config.output_image_path.read_bytes(),
        expected=expected,
        evidence=evidence,
        source_status=fixture.source_status,
    )
    normalized_html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    atomic_write(config.output_html_path, normalized_html.encode("utf-8"))

    print(f"Evidence: {evidence.label}")
    print(
        "Comparison: "
        f"{report.matched_leaves}/{report.expected_leaves} values matched; "
        f"{report.grounded_leaves}/{report.expected_leaves} source-grounded; "
        f"{len(report.issues)} issue(s)."
    )
    print(f"Wrote {config.output_image_path}")
    print(f"Wrote {config.output_comparison_path}")
    print(f"Wrote {config.output_html_path}")
    if isinstance(evidence, ProvisionalEvidence):
        print("RESULT: PROVISIONAL LAYOUT ONLY — NO API CALL; not release evidence.")
    elif evidence.reviewed and report.passed:
        print("PASS: reviewed live evidence matches the independent source oracle.")
    elif report.passed:
        print("RESULT: LIVE MATCH — REVIEW REQUIRED before any public claim.")
    else:
        print("FAIL: retained issues block a successful-extraction claim.")
    return report.exit_code


def build_generator_parser(config: PackageConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Generate the {config.slug} lighthouse package. Every mode is "
            "explicit; only --refresh can read NUTRIENT_API_KEY or call Extract."
        )
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--provisional",
        action="store_true",
        help="Build deterministic layout-only evidence without credentials or network access.",
    )
    modes.add_argument(
        "--refresh",
        action="store_true",
        help="Explicitly call Extract and write an unreviewed exact cache plus receipt.",
    )
    modes.add_argument(
        "--replay-live",
        action="store_true",
        help="Replay a receipt-bound live cache with the review-required label.",
    )
    modes.add_argument(
        "--replay-reviewed",
        action="store_true",
        help="Replay receipt-bound live evidence after a recorded human review.",
    )
    return parser


def build_checker_parser(config: PackageConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Compare {config.slug} evidence with its independent source oracle."
        )
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--allow-provisional",
        action="store_true",
        help="Check tagged layout-only data while acknowledging it is not API evidence.",
    )
    modes.add_argument(
        "--reviewed-live",
        action="store_true",
        help="Check the receipt-bound live cache after a recorded human review.",
    )
    return parser


def generator_main(
    config: PackageConfig,
    argv: list[str] | None = None,
    *,
    transport: Transport | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    args = build_generator_parser(config).parse_args(argv)
    try:
        fixture, expected = load_fixture_and_expected(config)
        document = load_document_config(config, fixture)

        if args.provisional:
            envelope = build_provisional_envelope(fixture, expected)
            atomic_write(config.provisional_path, _json_bytes(envelope))
            evidence: LighthouseEvidence = load_package_provisional(
                config.provisional_path,
                fixture=fixture,
                expected=expected,
            )
        elif args.refresh:
            print(
                "LIVE REFRESH: this explicit path can consume Data Extraction API "
                "credits and requires NUTRIENT_API_KEY."
            )
            evidence = asyncio.run(
                refresh_live_evidence(
                    config,
                    fixture,
                    document,
                    transport=transport,
                    environment=environment,
                )
            )
        else:
            evidence = load_live_replay(
                config,
                fixture,
                document,
                reviewed=args.replay_reviewed,
            )

        return write_generated_outputs(config, fixture, expected, evidence)
    except (ApiError, LighthouseError, OSError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


def checker_main(
    config: PackageConfig,
    argv: list[str] | None = None,
) -> int:
    args = build_checker_parser(config).parse_args(argv)
    try:
        fixture, expected = load_fixture_and_expected(config)
        if args.allow_provisional:
            evidence: LighthouseEvidence = load_package_provisional(
                config.provisional_path,
                fixture=fixture,
                expected=expected,
            )
            print(
                "PROVISIONAL LAYOUT ONLY — NO API CALL: this comparison cannot "
                "support a release claim."
            )
        else:
            document = load_document_config(config, fixture)
            evidence = load_live_replay(
                config,
                fixture,
                document,
                reviewed=args.reviewed_live,
            )
            if args.reviewed_live:
                print("Checking recorded, reviewed, receipt-bound live evidence.")
            else:
                print("LIVE API RESPONSE — REVIEW REQUIRED before any public claim.")

        report = compare_evidence(expected, evidence)
        _write_comparison(config, evidence, report)
        for issue in report.issues:
            print(f"{issue.code} {issue.path}: {issue.message}")
        if isinstance(evidence, ProvisionalEvidence) and report.passed:
            print(
                f"RESULT: PROVISIONAL LAYOUT MATCH — NO API CALL; "
                f"{report.matched_leaves}/{report.expected_leaves} values and "
                f"{report.grounded_leaves}/{report.expected_leaves} layout boxes match."
            )
        elif isinstance(evidence, LiveRefreshEvidence) and not evidence.reviewed and report.passed:
            print(
                f"RESULT: LIVE MATCH — REVIEW REQUIRED; "
                f"{report.matched_leaves}/{report.expected_leaves} values match."
            )
        elif report.passed:
            print(
                f"PASS: {report.matched_leaves}/{report.expected_leaves} values "
                "match and every leaf has a valid source box."
            )
        else:
            print(
                f"FAIL: retained {len(report.issues)} issue(s); "
                "successful-extraction claims remain blocked."
            )
        return report.exit_code
    except (LighthouseError, OSError, TypeError, ValueError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 1
