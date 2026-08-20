from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from common.lighthouse import (
    COMMITTED_CACHE_KEYS,
    LIVE_REVIEW_LABEL,
    PROVISIONAL_LABEL,
    PUBLIC_FORM_SOURCE_STATUS,
    REVIEWED_LIVE_LABEL,
    FixtureField,
    LighthouseError,
    LiveRefreshEvidence,
    ProvisionalEvidence,
    PublicFormFixture,
    SyntheticFixture,
    build_synthetic_pdf,
    committed_response_digest,
    compare_evidence,
    compare_expected,
    expected_from_fixture,
    expected_json_bytes,
    load_committed_live_evidence,
    load_provisional_evidence,
    parse_fixture,
    project_committed_cache,
    provisional_evidence,
    render_lighthouse_page,
    validate_committed_cache,
)
from scripts.build_lighthouse_fixtures import (
    FixtureDriftError,
    build_demo_fixture,
)


HOSTILE = "</script><script>alert('lighthouse')</script>"


def _pages() -> list[dict[str, int]]:
    return [{"width": 612, "height": 792}]


def _metadata_leaf(
    *,
    x: float = 12,
    y: float = 18,
    width: float = 120,
    height: float = 22,
) -> dict[str, Any]:
    return {
        "pageIndex": 0,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "confidence": 0.98,
    }


def _response(
    *,
    data: Any | None = None,
    metadata: Any | None = None,
    request_id: str = "request-live-1",
) -> dict[str, Any]:
    if data is None:
        data = {"name": "Alex Example", "amount": 42}
    if metadata is None:
        metadata = {"name": _metadata_leaf(), "amount": _metadata_leaf(y=52)}
    return {
        "status": 200,
        "requestId": request_id,
        "output": {
            "data": data,
            "metadata": metadata,
            "pages": _pages(),
        },
        "reconstructed": None,
    }


def _fixture_json(slug: str = "sample_demo") -> dict[str, Any]:
    return {
        "version": 1,
        "slug": slug,
        "sourceStatus": "synthetic",
        "document": {
            "filename": "data/synthetic-source.pdf",
            "title": "Synthetic verification packet",
            "subtitle": "Source truth for a one-page extraction demo",
            "width": 612,
            "height": 792,
        },
        "fields": [
            {"path": ["borrower", "name"], "label": "Borrower name", "value": "Alex Example"},
            {"path": ["borrower", "income"], "label": "Monthly income", "value": 7200},
            {"path": ["accounts", 0, "suffix"], "label": "Account suffix", "value": "0042"},
            {"path": ["verified"], "label": "Review flag", "value": True},
        ],
    }


def _public_fixture_json(slug: str = "sample_demo") -> dict[str, Any]:
    return {
        "version": 2,
        "slug": slug,
        "sourceStatus": PUBLIC_FORM_SOURCE_STATUS,
        "document": {
            "filename": "data/privacy-safe-public-form.pdf",
            "title": "Official Form 123 demo",
            "subtitle": "Authentic public form with privacy-safe demo values",
            "width": 612,
            "height": 792,
        },
        "provenance": {
            "publisher": "Example Public Agency",
            "officialFormName": "Official Form 123",
            "canonicalSourceUrl": "https://www.example.gov/forms/official-123.pdf",
            "originalSha256": "1" * 64,
            "sourceSha256": "2" * 64,
        },
        "fields": [
            {
                "path": ["applicant", "name"],
                "label": "Applicant name",
                "value": "Alex Example",
                "source": {
                    "pageIndex": 0,
                    "bbox": {"x": 80, "y": 120, "width": 140, "height": 18},
                },
            },
            {
                "path": ["reference_number"],
                "label": "Reference number",
                "value": "DEMO-0042",
                "source": {
                    "pageIndex": 0,
                    "bbox": {"x": 330, "y": 120, "width": 100, "height": 18},
                },
            },
        ],
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _receipt(
    response: dict[str, Any],
    *,
    source_status: str = "live-refresh",
    request_id: str | None = None,
    digest: str | None = None,
) -> dict[str, Any]:
    return {
        "receiptVersion": 1,
        "sourceStatus": source_status,
        "requestId": request_id or response["requestId"],
        "projectedResponseSha256": digest or committed_response_digest(response),
    }


def _live_evidence(
    tmp_path: Path,
    response: dict[str, Any] | None = None,
    *,
    reviewed: bool = False,
) -> LiveRefreshEvidence:
    selected_response = response or _response()
    cache_path = tmp_path / "cache.json"
    receipt_path = tmp_path / "receipt.json"
    _write_json(cache_path, selected_response)
    _write_json(receipt_path, _receipt(selected_response))
    return load_committed_live_evidence(
        cache_path,
        receipt_path,
        reviewed=reviewed,
    )


def test_provisional_and_live_evidence_have_distinct_fixed_labels(
    tmp_path: Path,
) -> None:
    provisional = provisional_evidence(_response())
    live = _live_evidence(tmp_path / "live")
    reviewed = _live_evidence(tmp_path / "reviewed", reviewed=True)

    assert isinstance(provisional, ProvisionalEvidence)
    assert isinstance(live, LiveRefreshEvidence)
    assert provisional.kind == "provisional"
    assert live.kind == "live"
    assert provisional.label == PROVISIONAL_LABEL
    assert "LIVE" not in provisional.label
    assert live.label == LIVE_REVIEW_LABEL
    assert reviewed.label == REVIEWED_LIVE_LABEL


def test_provisional_loader_requires_the_exact_tagged_envelope(tmp_path: Path) -> None:
    source = tmp_path / "provisional.json"
    _write_json(
        source,
        {"sourceStatus": "provisional-layout", "response": _response()},
    )

    evidence = load_provisional_evidence(source)

    assert isinstance(evidence, ProvisionalEvidence)
    for source_status in ("live", "api-output", "reviewed", "synthetic"):
        _write_json(
            source,
            {"sourceStatus": source_status, "response": _response()},
        )
        with pytest.raises(LighthouseError, match="unsupported provisional source status"):
            load_provisional_evidence(source)


def test_provisional_loader_rejects_raw_cache_and_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    source = tmp_path / "provisional.json"
    _write_json(source, _response())
    with pytest.raises(LighthouseError, match="sourceStatus and response"):
        load_provisional_evidence(source)

    source.write_text(
        '{"sourceStatus":"provisional-layout","sourceStatus":"live","response":{}}',
        encoding="utf-8",
    )
    with pytest.raises(LighthouseError, match="duplicate object key"):
        load_provisional_evidence(source)

    with pytest.raises(LighthouseError, match="regular, non-symlink|could not safely read"):
        load_provisional_evidence("malformed\0path.json")


def test_committed_cache_contract_uses_only_the_four_named_keys() -> None:
    assert COMMITTED_CACHE_KEYS == {
        "status",
        "requestId",
        "output",
        "reconstructed",
    }
    broader = {**_response(), "configuration": {"mode": "agentic"}, "metrics": {}}

    with pytest.raises(LighthouseError, match="configuration, metrics"):
        validate_committed_cache(broader)

    projected = project_committed_cache(broader)
    assert set(projected) == COMMITTED_CACHE_KEYS


def test_committed_cache_requires_status_request_id_and_output() -> None:
    for required in ("status", "requestId", "output"):
        malformed = _response()
        del malformed[required]
        with pytest.raises(LighthouseError, match="missing required"):
            validate_committed_cache(malformed)


@pytest.mark.parametrize("extra_key", ["billing", "internal", "metrics"])
def test_committed_cache_rejects_extra_extract_output_envelope_keys(
    extra_key: str,
) -> None:
    malformed = _response()
    malformed["output"][extra_key] = {"secret": "must not persist"}

    with pytest.raises(LighthouseError, match=f"unsupported output keys {extra_key}"):
        validate_committed_cache(malformed)


def test_committed_cache_allows_document_field_names_inside_output_data() -> None:
    response = _response(
        data={"billing": {"liquid_balance": 12500}},
        metadata={"billing": {"liquid_balance": _metadata_leaf()}},
    )

    validated = validate_committed_cache(response)

    assert validated["output"]["data"]["billing"]["liquid_balance"] == 12500


def test_live_evidence_requires_matching_cache_and_receipt(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    receipt_path = tmp_path / "receipt.json"
    response = _response()
    _write_json(cache_path, response)
    _write_json(receipt_path, _receipt(response))

    evidence = load_committed_live_evidence(
        cache_path,
        receipt_path,
        reviewed=True,
    )

    assert evidence.reviewed is True
    assert set(evidence.response) == COMMITTED_CACHE_KEYS


def test_live_evidence_rejects_direct_construction_and_raw_wrappers(
    tmp_path: Path,
) -> None:
    with pytest.raises(LighthouseError, match="only be loaded"):
        LiveRefreshEvidence(response=_response())

    receipt_path = tmp_path / "receipt.json"
    _write_json(receipt_path, _receipt(_response()))
    with pytest.raises(LighthouseError, match="safely read|regular"):
        load_committed_live_evidence(_response(), receipt_path)  # type: ignore[arg-type]

    provisional_path = tmp_path / "provisional.json"
    _write_json(
        provisional_path,
        {"sourceStatus": "provisional-layout", "response": _response()},
    )
    with pytest.raises(LighthouseError, match="unsupported top-level keys"):
        load_committed_live_evidence(provisional_path, receipt_path)


def test_live_evidence_rejects_missing_mismatched_and_forged_receipts(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "cache.json"
    receipt_path = tmp_path / "receipt.json"
    response = _response()
    _write_json(cache_path, response)

    with pytest.raises(LighthouseError, match="regular, non-symlink"):
        load_committed_live_evidence(cache_path, receipt_path)

    mismatched_request = _receipt(response, request_id="different-request")
    _write_json(receipt_path, mismatched_request)
    with pytest.raises(LighthouseError, match="requestId does not match"):
        load_committed_live_evidence(cache_path, receipt_path)

    mismatched_digest = _receipt(response, digest="0" * 64)
    _write_json(receipt_path, mismatched_digest)
    with pytest.raises(LighthouseError, match="digest does not match"):
        load_committed_live_evidence(cache_path, receipt_path)

    forged_status = _receipt(response, source_status="provisional-layout")
    _write_json(receipt_path, forged_status)
    with pytest.raises(LighthouseError, match="unsupported live-refresh receipt source status"):
        load_committed_live_evidence(cache_path, receipt_path)

    missing_key = _receipt(response)
    del missing_key["projectedResponseSha256"]
    _write_json(receipt_path, missing_key)
    with pytest.raises(LighthouseError, match="exactly the documented keys"):
        load_committed_live_evidence(cache_path, receipt_path)


def test_live_evidence_rejects_reconstructed_and_broader_cache_files(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "cache.json"
    receipt_path = tmp_path / "receipt.json"
    response = _response()

    _write_json(cache_path, {**_response(), "configuration": {}})
    _write_json(receipt_path, _receipt(response))
    with pytest.raises(LighthouseError, match="unsupported"):
        load_committed_live_evidence(cache_path, receipt_path)

    for marker in (True, 0, 0.0, ""):
        response = _response()
        response["reconstructed"] = marker
        _write_json(cache_path, response)
        _write_json(receipt_path, _receipt(response))
        with pytest.raises(LighthouseError, match="reconstructed responses"):
            load_committed_live_evidence(cache_path, receipt_path)


def test_live_evidence_permits_only_absent_none_or_boolean_false_reconstruction_marker(
    tmp_path: Path,
) -> None:
    for index, marker in enumerate((None, False)):
        response = _response()
        response["reconstructed"] = marker
        evidence = _live_evidence(tmp_path / str(index), response)
        assert evidence.kind == "live"

    absent = _response()
    del absent["reconstructed"]
    assert _live_evidence(tmp_path / "absent", absent).kind == "live"


def test_comparison_pass_and_exit_semantics_require_values_and_grounding() -> None:
    expected = {"name": "Alex Example", "amount": 42}
    response = _response()

    report = compare_expected(
        expected,
        response["output"]["data"],
        response["output"]["metadata"],
        pages=response["output"]["pages"],
    )

    assert report.passed is True
    assert report.exit_code == 0
    assert report.issues == ()
    assert report.expected_leaves == 2
    assert report.matched_leaves == 2
    assert report.grounded_leaves == 2


def test_comparison_retains_all_value_shape_and_grounding_mismatches() -> None:
    expected = {"a": "source-a", "b": "source-b", "items": [1, 2]}
    actual = {"a": "wrong", "items": [1, 3, 4], "extra": "not-source"}
    metadata = {
        "a": None,
        "items": [_metadata_leaf(), {"pageIndex": "zero", "bbox": {}}],
    }

    report = compare_expected(expected, actual, metadata, pages=_pages())
    codes_and_paths = {(issue.code, issue.path) for issue in report.issues}

    assert report.passed is False
    assert report.exit_code == 1
    assert ("WRONG", "$.a") in codes_and_paths
    assert ("UNGROUNDED", "$.a") in codes_and_paths
    assert ("MISSING", "$.b") in codes_and_paths
    assert ("WRONG", "$.items[1]") in codes_and_paths
    assert ("INVALID_METADATA", "$.items[1]") in codes_and_paths
    assert ("UNEXPECTED", "$.items[2]") in codes_and_paths
    assert ("UNEXPECTED", "$.extra") in codes_and_paths
    assert len(report.issues) == 7


def test_comparison_uses_strict_json_scalar_types() -> None:
    report = compare_expected(
        {"approved": True},
        {"approved": 1},
        {"approved": _metadata_leaf()},
        pages=_pages(),
    )

    assert report.exit_code == 1
    assert [(issue.code, issue.path) for issue in report.issues] == [
        ("WRONG", "$.approved")
    ]


def test_comparison_rejects_non_finite_values_and_handles_hostile_paths() -> None:
    with pytest.raises(LighthouseError, match="non-finite"):
        compare_expected(
            {"value": 1},
            {"value": float("nan")},
            {"value": _metadata_leaf()},
            pages=_pages(),
        )

    report = compare_expected(
        {HOSTILE: "source"},
        {HOSTILE: "different"},
        {HOSTILE: _metadata_leaf()},
        pages=_pages(),
    )
    assert report.issues[0].path.startswith('$["</script>')


@pytest.mark.parametrize(
    "metadata, message",
    [
        (
            {
                "pageIndex": 0,
                "bbox": {"x": 1, "y": 1, "width": 20, "extra": 4},
            },
            "exactly x, y, width, and height",
        ),
        (
            {
                "pageIndex": 0,
                "bbox": {
                    "x": 1,
                    "y": 1,
                    "width": 20,
                    "height": 10,
                    "extra": 4,
                },
            },
            "exactly x, y, width, and height",
        ),
        (_metadata_leaf(x=600, width=20), "exceeds the page width"),
        (_metadata_leaf(y=780, height=20), "exceeds the page height"),
        ({**_metadata_leaf(), "pageIndex": 1}, "pageIndex must be exactly 0"),
    ],
)
def test_grounding_requires_exact_in_page_one_page_geometry(
    metadata: dict[str, Any],
    message: str,
) -> None:
    report = compare_expected(
        {"value": "source"},
        {"value": "source"},
        {"value": metadata},
        pages=_pages(),
    )

    assert report.exit_code == 1
    assert [(issue.code, issue.path) for issue in report.issues] == [
        ("INVALID_METADATA", "$.value")
    ]
    assert message in report.issues[0].message


@pytest.mark.parametrize(
    "pages",
    [
        [],
        [{"width": 612, "height": 792}, {"width": 612, "height": 792}],
        [{"width": float("nan"), "height": 792}],
        [{"width": 612, "height": 0}],
    ],
)
def test_direct_comparison_rejects_invalid_page_contract(pages: Any) -> None:
    with pytest.raises(LighthouseError, match="exactly one page|non-finite|finite range"):
        compare_expected(
            {"value": "source"},
            {"value": "source"},
            {"value": _metadata_leaf()},
            pages=pages,
        )


def test_structural_mismatches_expand_to_every_affected_leaf() -> None:
    expected = {
        "person": {
            "name": "Alex Example",
            "employer": {"name": "Example Industries"},
        }
    }

    wrong_container = compare_expected(
        expected,
        {"person": "not-an-object"},
        {"person": _metadata_leaf()},
        pages=_pages(),
    )
    wrong_paths = {
        issue.path for issue in wrong_container.issues if issue.code == "WRONG"
    }
    assert "$.person" in wrong_paths
    assert "$.person.name" in wrong_paths
    assert "$.person.employer.name" in wrong_paths

    missing_object = compare_expected(
        expected,
        {"person": {}},
        {"person": {}},
        pages=_pages(),
    )
    missing_paths = {
        issue.path for issue in missing_object.issues if issue.code == "MISSING"
    }
    assert missing_paths == {"$.person.name", "$.person.employer.name"}

    unexpected_object = compare_expected(
        {"known": "source"},
        {
            "known": "source",
            "unexpected": {"nested": {"first": 1, "second": 2}},
        },
        {"known": _metadata_leaf()},
        pages=_pages(),
    )
    unexpected_paths = {
        issue.path for issue in unexpected_object.issues if issue.code == "UNEXPECTED"
    }
    assert unexpected_paths == {
        "$.unexpected.nested.first",
        "$.unexpected.nested.second",
    }


def test_render_marks_shape_affected_cards_failed_and_lists_unexpected_leaves() -> None:
    expected = {"person": {"name": "Alex", "employer": "Example Industries"}}
    response = _response(
        data={
            "person": "wrong-container",
            "unexpected": {"nested": {"secret": "visible-ledger-entry"}},
        },
        metadata={"person": _metadata_leaf()},
    )

    html = render_lighthouse_page(
        title="Structural comparison",
        summary="Every structural failure remains visible.",
        document_name="Synthetic source",
        document_image=b"stable-image-bytes",
        expected=expected,
        evidence=provisional_evidence(response),
    )

    assert html.count('class="field-card fail"') == 2
    assert 'class="field-card pass"' not in html
    assert "$.person.name" in html
    assert "$.person.employer" in html
    assert "$.unexpected.nested.secret" in html
    assert "visible-ledger-entry" in html
    assert "Every retained issue" in html


def test_expected_values_are_derived_from_fixture_source_not_response() -> None:
    fixture = parse_fixture(_fixture_json())
    expected = expected_from_fixture(fixture)
    response_data = json.loads(json.dumps(expected))
    response_data["borrower"]["name"] = "Model Changed This"
    metadata = {
        "borrower": {
            "name": _metadata_leaf(),
            "income": _metadata_leaf(y=45),
        },
        "accounts": [{"suffix": _metadata_leaf(y=75)}],
        "verified": _metadata_leaf(y=105),
    }
    evidence = provisional_evidence(_response(data=response_data, metadata=metadata))

    report = compare_evidence(expected, evidence)

    assert expected["borrower"]["name"] == "Alex Example"
    assert any(
        issue.code == "WRONG" and issue.path == "$.borrower.name"
        for issue in report.issues
    )


def test_fixture_rejects_traversal_real_data_status_and_path_collisions() -> None:
    traversal = _fixture_json()
    traversal["document"]["filename"] = "../outside.pdf"
    with pytest.raises(LighthouseError, match="safe relative PDF path"):
        parse_fixture(traversal)

    nul_path = _fixture_json()
    nul_path["document"]["filename"] = "data/source\0.pdf"
    with pytest.raises(LighthouseError, match="safe relative PDF path"):
        parse_fixture(nul_path)

    real_data = _fixture_json()
    real_data["sourceStatus"] = "customer-data"
    with pytest.raises(LighthouseError, match="unsupported fixture source status"):
        parse_fixture(real_data)

    collision = _fixture_json()
    collision["fields"].append(
        {"path": ["borrower"], "label": "Collision", "value": "bad"}
    )
    with pytest.raises(LighthouseError, match="must not overlap"):
        parse_fixture(collision)


def test_public_form_fixture_requires_distinct_versioned_provenance_and_boxes() -> None:
    fixture = parse_fixture(_public_fixture_json())

    assert isinstance(fixture, PublicFormFixture)
    assert fixture.version == 2
    assert fixture.source_status == PUBLIC_FORM_SOURCE_STATUS
    assert fixture.provenance.publisher == "Example Public Agency"
    assert fixture.provenance.official_form_name == "Official Form 123"
    assert fixture.provenance.canonical_source_url.startswith("https://")
    assert fixture.fields[0].source_box is not None
    assert fixture.fields[0].source_box.as_metadata() == {
        "pageIndex": 0,
        "bbox": {"x": 80.0, "y": 120.0, "width": 140.0, "height": 18.0},
    }
    assert expected_from_fixture(fixture) == {
        "applicant": {"name": "Alex Example"},
        "reference_number": "DEMO-0042",
    }


def test_fixture_source_types_cannot_be_silently_relabelled() -> None:
    relabelled_synthetic = _fixture_json()
    relabelled_synthetic["sourceStatus"] = PUBLIC_FORM_SOURCE_STATUS
    with pytest.raises(
        LighthouseError,
        match="version-1 fixtures must remain synthetic",
    ):
        parse_fixture(relabelled_synthetic)

    relabelled_public = _public_fixture_json()
    relabelled_public["sourceStatus"] = "synthetic"
    with pytest.raises(LighthouseError, match="version/source status"):
        parse_fixture(relabelled_public)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda value: value["provenance"].__setitem__(
                "canonicalSourceUrl", "http://www.example.gov/form.pdf"
            ),
            "canonical HTTPS URL",
        ),
        (
            lambda value: value["provenance"].__setitem__(
                "canonicalSourceUrl", "https://user@example.gov/form.pdf"
            ),
            "canonical HTTPS URL",
        ),
        (
            lambda value: value["provenance"].__setitem__(
                "canonicalSourceUrl", "https://EXAMPLE.gov/form.pdf"
            ),
            "canonical HTTPS URL",
        ),
        (
            lambda value: value["provenance"].__setitem__(
                "sourceSha256", "A" * 64
            ),
            "lowercase SHA-256",
        ),
        (
            lambda value: value["provenance"].__setitem__(
                "originalSha256", "not-a-digest"
            ),
            "lowercase SHA-256",
        ),
        (
            lambda value: value["provenance"].__setitem__("publisher", ""),
            "must not be empty",
        ),
    ],
)
def test_public_form_fixture_rejects_malformed_provenance(
    mutate: Any,
    message: str,
) -> None:
    value = _public_fixture_json()
    mutate(value)
    with pytest.raises(LighthouseError, match=message):
        parse_fixture(value)


@pytest.mark.parametrize(
    "source, message",
    [
        (
            {"pageIndex": 0, "bbox": {"x": 1, "y": 2, "width": 3}},
            "exactly x, y, width, and height",
        ),
        (
            {
                "pageIndex": 1,
                "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
            },
            "pageIndex must be exactly 0",
        ),
        (
            {
                "pageIndex": 0,
                "bbox": {"x": -1, "y": 2, "width": 3, "height": 4},
            },
            "origin must be non-negative",
        ),
        (
            {
                "pageIndex": 0,
                "bbox": {"x": 1, "y": 2, "width": 0, "height": 4},
            },
            "dimensions must be positive",
        ),
        (
            {
                "pageIndex": 0,
                "bbox": {"x": 600, "y": 2, "width": 13, "height": 4},
            },
            "exceeds the declared page width",
        ),
        (
            {
                "pageIndex": 0,
                "bbox": {"x": 1, "y": 790, "width": 3, "height": 3},
            },
            "exceeds the declared page height",
        ),
    ],
)
def test_public_form_fixture_rejects_malformed_or_out_of_page_boxes(
    source: dict[str, Any],
    message: str,
) -> None:
    value = _public_fixture_json()
    value["fields"][0]["source"] = source
    with pytest.raises(LighthouseError, match=message):
        parse_fixture(value)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda value: value["document"].__setitem__("width", float("inf")), "non-finite|finite range"),
        (lambda value: value["fields"][0].__setitem__("label", "line\nbreak"), "printable ASCII"),
        (lambda value: value["fields"][0].__setitem__("value", {"nested": "no"}), "JSON scalar"),
        (lambda value: value.__setitem__("version", 2), "unsupported fixture version"),
    ],
)
def test_fixture_fails_safely_on_malformed_values(mutate: Any, message: str) -> None:
    value = _fixture_json()
    mutate(value)
    with pytest.raises(LighthouseError, match=message):
        parse_fixture(value)


def test_synthetic_pdf_and_expected_json_are_byte_stable() -> None:
    fixture = parse_fixture(_fixture_json())

    first_pdf = build_synthetic_pdf(fixture)
    second_pdf = build_synthetic_pdf(fixture)
    first_expected = expected_json_bytes(fixture)
    second_expected = expected_json_bytes(fixture)

    assert first_pdf == second_pdf
    assert first_pdf.startswith(b"%PDF-1.4")
    assert first_pdf.endswith(b"%%EOF\n")
    assert first_expected == second_expected
    assert json.loads(first_expected) == expected_from_fixture(fixture)
    assert hashlib.sha256(first_pdf).hexdigest() == (
        "a40b66c379e3eac25068f626679fb527377f473e010d59f6d9d53d714201008d"
    )
    assert hashlib.sha256(first_expected).hexdigest() == (
        "271de86a00b49fb54079df8a1f860d6fb65da5adf1f9e45b325a464135a2c0c8"
    )


def test_synthetic_pdf_builder_rejects_public_form_fixture() -> None:
    fixture = parse_fixture(_public_fixture_json())

    with pytest.raises(LighthouseError, match="only version-1 synthetic"):
        build_synthetic_pdf(fixture)  # type: ignore[arg-type]


def test_pdf_generator_escapes_hostile_pdf_literal_text() -> None:
    value = _fixture_json()
    value["fields"][0]["value"] = r"hostile (value) \\ still literal"
    fixture = parse_fixture(value)

    pdf = build_synthetic_pdf(fixture)

    assert b"hostile \\(value\\)" in pdf
    assert b"\\\\\\\\ still literal" in pdf


def test_fixture_builder_writes_and_checks_without_mutating_in_check_mode(
    tmp_path: Path,
) -> None:
    demo_dir = tmp_path / "sample_demo"
    demo_dir.mkdir()
    _write_json(demo_dir / "fixture.json", _fixture_json())

    built = build_demo_fixture(demo_dir)
    expected_before = built.expected_path.read_bytes()
    checked = build_demo_fixture(demo_dir, check=True)

    assert checked.checked is True
    assert built.pdf_path.is_file()
    assert expected_before == built.expected_path.read_bytes()

    built.expected_path.write_text("{}\n", encoding="utf-8")
    stale_before = built.expected_path.read_bytes()
    with pytest.raises(FixtureDriftError, match="stale"):
        build_demo_fixture(demo_dir, check=True)
    assert built.expected_path.read_bytes() == stale_before


def test_fixture_builder_rejects_symlink_destinations(tmp_path: Path) -> None:
    demo_dir = tmp_path / "sample_demo"
    demo_dir.mkdir()
    _write_json(demo_dir / "fixture.json", _fixture_json())
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"preserve")
    data_dir = demo_dir / "data"
    data_dir.mkdir()
    (data_dir / "synthetic-source.pdf").symlink_to(outside)

    with pytest.raises(LighthouseError, match="symbolic link"):
        build_demo_fixture(demo_dir)
    assert outside.read_bytes() == b"preserve"


def test_fixture_builder_never_overwrites_public_form_sources_or_oracles(
    tmp_path: Path,
) -> None:
    demo_dir = tmp_path / "sample_demo"
    source_path = demo_dir / "data" / "privacy-safe-public-form.pdf"
    source_path.parent.mkdir(parents=True)
    source_before = b"preserve-authentic-public-form"
    expected_before = b'{"preserve":"oracle"}\n'
    source_path.write_bytes(source_before)
    (demo_dir / "expected.json").write_bytes(expected_before)
    fixture_value = _public_fixture_json()
    fixture_value["provenance"]["sourceSha256"] = hashlib.sha256(
        source_before
    ).hexdigest()
    _write_json(demo_dir / "fixture.json", fixture_value)

    with pytest.raises(LighthouseError, match="will not overwrite"):
        build_demo_fixture(demo_dir)

    assert source_path.read_bytes() == source_before
    assert (demo_dir / "expected.json").read_bytes() == expected_before


def test_rendered_page_is_self_contained_and_escapes_all_hostile_text(
    tmp_path: Path,
) -> None:
    response = _response(
        data={"name": HOSTILE},
        metadata={"name": _metadata_leaf()},
        request_id=HOSTILE,
    )
    evidence = _live_evidence(tmp_path, response)

    html = render_lighthouse_page(
        title=HOSTILE,
        summary=HOSTILE,
        document_name=HOSTILE,
        document_image=b"stable-image-bytes",
        expected={"name": HOSTILE},
        evidence=evidence,
    )

    assert HOSTILE not in html
    assert "&lt;/script&gt;&lt;script&gt;alert" in html
    assert "\\u003c/script>\\u003cscript>alert" in html
    assert "data:image/png;base64," in html
    assert "http://" not in html
    assert "https://" not in html
    assert LIVE_REVIEW_LABEL in html


def test_provisional_page_never_displays_request_id_or_live_label() -> None:
    response = _response(request_id="fake-live-looking-request")
    evidence = provisional_evidence(response)

    html = render_lighthouse_page(
        title="Layout proof",
        summary="Offline layout test",
        document_name="Synthetic source",
        document_image=b"stable-image-bytes",
        expected={"name": "Alex Example", "amount": 42},
        evidence=evidence,
    )

    assert PROVISIONAL_LABEL in html
    assert "fake-live-looking-request" not in html
    assert LIVE_REVIEW_LABEL not in html
    assert REVIEWED_LIVE_LABEL not in html
    assert "Layout development only; not release evidence." in html
    assert "PROVISIONAL LAYOUT MATCH · NO API CALL" in html
    assert ">Pass<" not in html
    assert "background: var(--citrus);" in html
    assert "background: var(--success);" not in html
    assert "source grounded" in html
    assert "primary regions returned" not in html


def test_public_form_page_uses_authentic_privacy_safe_copy() -> None:
    html = render_lighthouse_page(
        title="Official form proof",
        summary="Privacy-safe source verification",
        document_name="Official Form 123",
        document_image=b"stable-image-bytes",
        expected={"name": "Alex Example", "amount": 42},
        evidence=provisional_evidence(_response()),
        source_status=PUBLIC_FORM_SOURCE_STATUS,
    )

    assert "Reviewed evidence / authentic public form" in html
    assert "Authentic public form · privacy-safe demo values · page 1" in html
    assert "Authentic public form with privacy-safe demo values" in html
    assert "synthetic fixture" not in html.lower()
    assert "synthetic source" not in html.lower()
    assert "customer data" not in html.lower()
    assert "primary regions returned" in html
    assert "source grounded" not in html


def test_reviewed_public_form_page_uses_primary_region_metric(
    tmp_path: Path,
) -> None:
    html = render_lighthouse_page(
        title="Reviewed official form proof",
        summary="Reviewed privacy-safe source verification",
        document_name="Official Form 123",
        document_image=b"stable-image-bytes",
        expected={"name": "Alex Example", "amount": 42},
        evidence=_live_evidence(tmp_path, reviewed=True),
        source_status=PUBLIC_FORM_SOURCE_STATUS,
    )

    assert ">Pass<" in html
    assert "primary regions returned" in html
    assert "source grounded" not in html


def test_only_reviewed_live_match_uses_an_unqualified_pass(tmp_path: Path) -> None:
    unreviewed = _live_evidence(tmp_path / "unreviewed")
    reviewed = _live_evidence(tmp_path / "reviewed", reviewed=True)
    common = {
        "title": "Live evidence state",
        "summary": "Receipt-bound comparison",
        "document_name": "Synthetic source",
        "document_image": b"stable-image-bytes",
        "expected": {"name": "Alex Example", "amount": 42},
    }

    unreviewed_html = render_lighthouse_page(evidence=unreviewed, **common)
    reviewed_html = render_lighthouse_page(evidence=reviewed, **common)

    assert "LIVE MATCH · REVIEW REQUIRED" in unreviewed_html
    assert ">Pass<" not in unreviewed_html
    assert "background: var(--cobalt);" in unreviewed_html
    assert ">Pass<" in reviewed_html
    assert "background: var(--success);" in reviewed_html


def test_render_fails_closed_on_malformed_pages_metadata_and_image_types() -> None:
    response = _response()
    response["output"]["pages"][0]["width"] = float("nan")
    with pytest.raises(LighthouseError, match="non-finite"):
        provisional_evidence(response)

    response = _response(metadata={"name": _metadata_leaf(), "amount": _metadata_leaf(width=-1)})
    html = render_lighthouse_page(
        title="Safe failure report",
        summary="Malformed grounding remains visible as a mismatch.",
        document_name="Synthetic source",
        document_image=b"stable-image-bytes",
        expected={"name": "Alex Example", "amount": 42},
        evidence=provisional_evidence(response),
    )
    assert "INVALID_METADATA" in html
    assert "Review blocked" in html

    with pytest.raises(LighthouseError, match="unsupported embedded image type"):
        render_lighthouse_page(
            title="Bad image",
            summary="No external resources",
            document_name="Synthetic source",
            document_image=b"image",
            image_mime="image/svg+xml",
            expected={"name": "Alex Example", "amount": 42},
            evidence=provisional_evidence(_response()),
        )


def test_render_revalidates_receipt_bound_live_evidence(tmp_path: Path) -> None:
    evidence = _live_evidence(tmp_path)
    evidence._response["output"]["data"]["name"] = "tampered after receipt"

    with pytest.raises(LighthouseError, match="no longer matches its receipt"):
        render_lighthouse_page(
            title="Tampered cache",
            summary="Must fail closed",
            document_name="Synthetic source",
            document_image=b"image",
            expected={"name": "Alex Example", "amount": 42},
            evidence=evidence,
        )


def test_dataclass_fixture_builds_nested_oracle_without_response_input() -> None:
    fixture = SyntheticFixture(
        version=1,
        slug="manual_fixture",
        source_status="synthetic",
        filename=Path("data/manual.pdf"),  # type: ignore[arg-type]
        title="Manual fixture",
        subtitle="Source only",
        page_width=612,
        page_height=792,
        fields=(
            FixtureField(("items", 0, "code"), "Code", "A-1"),
            FixtureField(("items", 1, "code"), "Code", "B-2"),
        ),
    )

    assert expected_from_fixture(fixture) == {
        "items": [{"code": "A-1"}, {"code": "B-2"}]
    }
