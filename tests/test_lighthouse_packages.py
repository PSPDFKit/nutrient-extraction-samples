from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
HUB = ROOT / "docs" / "lighthouse" / "index.html"
VERTICAL_READMES = (
    ROOT / "demos" / "mortgage_verification" / "README.md",
    ROOT / "demos" / "insurance_claim_intake" / "README.md",
    ROOT / "demos" / "prior_authorization" / "README.md",
)
MEASUREMENT_ENUMS = {
    "utm_campaign": {"de_lighthouse_pilot_v1"},
    "utm_source": {"nutrient_owned"},
    "utm_medium": {"owned"},
}
VERTICALS = {
    "mortgage_verification",
    "insurance_claim_intake",
    "prior_authorization",
    "cross_vertical",
}
ASSETS = {"owned_hub"}
VARIANTS = {"v01"}
CTAS = {"github", "proof", "studio", "docs", "signup"}
PROOF_ASSETS = {
    "mortgage-verification-reviewed.html": (
        ROOT / "demos" / "mortgage_verification" / "output" / "index.html"
    ),
    "insurance-claim-intake-reviewed.html": (
        ROOT / "demos" / "insurance_claim_intake" / "output" / "index.html"
    ),
    "prior-authorization-reviewed.html": (
        ROOT / "demos" / "prior_authorization" / "output" / "index.html"
    ),
}
COMPARISONS = {
    "mortgage_verification": {
        "expectedLeaves": 8,
        "groundedLeaves": 8,
        "matchedLeaves": 6,
        "issues": 2,
        "passed": False,
        "verdict": "Review blocked",
    },
    "insurance_claim_intake": {
        "expectedLeaves": 11,
        "groundedLeaves": 11,
        "matchedLeaves": 11,
        "issues": 0,
        "passed": True,
        "verdict": "Pass",
    },
    "prior_authorization": {
        "expectedLeaves": 11,
        "groundedLeaves": 11,
        "matchedLeaves": 9,
        "issues": 2,
        "passed": False,
        "verdict": "Review blocked",
    },
}
SCREENSHOTS = {
    "lighthouse-hub-375.png",
    "lighthouse-hub-414.png",
    "lighthouse-hub-768.png",
    "lighthouse-hub-1024.png",
    "lighthouse-hub-1440.png",
    "lighthouse-mortgage-desktop.png",
    "lighthouse-mortgage-mobile.png",
    "lighthouse-insurance-desktop.png",
    "lighthouse-insurance-mobile.png",
    "lighthouse-healthcare-desktop.png",
    "lighthouse-healthcare-mobile.png",
}
DESIGN_ASSETS = {
    "fonts/ABCMonumentGroteskVariable.woff2": (
        "a290892b541674d3682e01f18277185ca8ee48caa011e45b901f55ccca7fe5ac"
    ),
    "fonts/ABCMonumentGroteskSemi-Mono-Regular.woff2": (
        "d2764ac72c40dc455279147d6a20b1fd1e3368bae32fae374a1507de706c2cfb"
    ),
    "fonts/ABCMonumentGroteskMono-Medium.woff2": (
        "99a97a4e9dbc8016ea9f0b11b0f1b499bdf70767cc6d576b8d2fd1b921aa8a73"
    ),
    "nutrient-logo.svg": (
        "c9102300d8cce70ed381f1775057fb72f5f874fafafde3efabdc82d8a0cbcb88"
    ),
}


class _HubParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []
        self.ids: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "img":
            self.images.append(values)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_hub() -> tuple[str, _HubParser]:
    html = HUB.read_text(encoding="utf-8")
    parser = _HubParser()
    parser.feed(html)
    return html, parser


def test_hub_has_complete_local_reviewed_evidence() -> None:
    html, parser = _parse_hub()
    readme = README.read_text(encoding="utf-8")

    assert {"main", "evidence", "proofs", "limits"} <= parser.ids
    assert "26/30" in html
    assert "mortgage 6/8, insurance 11/11" in html
    assert "healthcare 9/11" in html
    assert "30/30" in html
    assert "four mismatches were retained for review" in html
    assert html.count('class="proof-verdict blocked">Review blocked</span>') == 2
    assert (
        html.count(
            'class="proof-verdict pass">11/11 exact → Continue</span>'
        )
        == 1
    )
    assert html.count("Pricing and credit usage can change.") == 2
    assert "Review current pricing" in html
    assert "11/11 exact → Continue" in readme
    assert "Pricing and credit usage can change." in readme
    for public_summary in (html, readme):
        assert "72 credits" not in public_summary
        assert "72-credit" not in public_summary
    assert "not an accuracy,\n            production, or performance benchmark" in html
    assert "does not approve publication" in html
    assert "Three of the four mismatches are exposed by returned metadata" in html
    assert "clip the decisive final period" in html
    assert "source-grounded" not in html.lower()
    assert "semantically grounded" not in html.lower()
    for vertical_readme in VERTICAL_READMES:
        assert "source-grounded" not in vertical_readme.read_text(
            encoding="utf-8"
        ).lower()
    assert "customer data" not in html.lower()
    assert "30/30</strong><span>JSON values matched" not in html
    assert not re.search(r"GMxy[A-Za-z0-9]+", html)

    for copied_name, reviewed_output in PROOF_ASSETS.items():
        copied = ROOT / "docs" / "lighthouse" / "assets" / copied_name
        assert copied.is_file()
        assert _sha256(copied) == _sha256(reviewed_output)

    aggregate = {
        "expected": 0,
        "grounded": 0,
        "matched": 0,
        "issues": 0,
    }
    for demo, expected in COMPARISONS.items():
        artifact = _load_json(
            ROOT / "demos" / demo / "output" / "comparison.json"
        )
        assert isinstance(artifact, dict)
        assert artifact["evidenceKind"] == "live"
        assert artifact["evidenceLabel"] == "REVIEWED LIVE API RESPONSE"
        assert artifact["reviewed"] is True
        comparison = artifact["comparison"]
        assert comparison["expectedLeaves"] == expected["expectedLeaves"]
        assert comparison["groundedLeaves"] == expected["groundedLeaves"]
        assert comparison["matchedLeaves"] == expected["matchedLeaves"]
        assert len(comparison["issues"]) == expected["issues"]
        assert comparison["passed"] is expected["passed"]
        aggregate["expected"] += comparison["expectedLeaves"]
        aggregate["grounded"] += comparison["groundedLeaves"]
        aggregate["matched"] += comparison["matchedLeaves"]
        aggregate["issues"] += len(comparison["issues"])

        proof_html = (
            ROOT / "demos" / demo / "output" / "index.html"
        ).read_text(encoding="utf-8")
        assert expected["verdict"] in proof_html
        assert "primary regions returned" in proof_html
        assert "source grounded" not in proof_html.lower()

    assert aggregate == {
        "expected": 30,
        "grounded": 30,
        "matched": 26,
        "issues": 4,
    }

    screenshot_dir = ROOT / "docs" / "screenshots"
    assert all((screenshot_dir / name).is_file() for name in SCREENSHOTS)
    proof_images = [image for image in parser.images if image.get("loading")]
    assert len(proof_images) == 3
    assert all(image.get("loading") == "eager" for image in proof_images)
    assert all(image.get("alt", "").strip() for image in parser.images)


def test_hub_and_proofs_use_the_frozen_website_v3_design_assets() -> None:
    html, _ = _parse_hub()
    design_source = (ROOT / "docs" / "lighthouse-design-source.md").read_text(
        encoding="utf-8"
    )

    assert "71f76eb62384241e2cf18d76fd31020b95a0a1f6" in design_source
    assert 'font-family: "ABC Monument Grotesk"' in html
    assert "Website-v3 company theme" in html
    assert 'src="assets/nutrient-logo.svg"' in html
    assert (
        '<link rel="icon" href="assets/nutrient-logo.svg" '
        'type="image/svg+xml">'
    ) in html

    deployed_assets = ROOT / "docs" / "lighthouse" / "assets"
    for relative, expected_hash in DESIGN_ASSETS.items():
        asset = deployed_assets / relative
        assert asset.is_file()
        assert _sha256(asset) == expected_hash

    for reviewed_output in PROOF_ASSETS.values():
        proof_html = reviewed_output.read_text(encoding="utf-8")
        assert "font-src data:" in proof_html
        assert "data:font/woff2;base64," in proof_html
        assert "Website-v3 visual layer" in proof_html
        assert 'alt="Nutrient"' in proof_html
        assert "max-height: none" in proof_html


def test_hub_links_follow_fixed_measurement_contract() -> None:
    _, parser = _parse_hub()
    campaign_links = [href for href in parser.links if "utm_campaign=" in href]

    assert len(campaign_links) == 10
    for href in campaign_links:
        query = parse_qs(urlparse(href).query, strict_parsing=True)
        assert set(query) == {
            "utm_campaign",
            "utm_source",
            "utm_medium",
            "utm_content",
        }
        for parameter, allowed in MEASUREMENT_ENUMS.items():
            assert set(query[parameter]) <= allowed

        content = query["utm_content"][0].split(".")
        assert len(content) == 4
        vertical, asset, variant, cta = content
        assert vertical in VERTICALS
        assert asset in ASSETS
        assert variant in VARIANTS
        assert cta in CTAS


def test_hub_links_resolve_or_use_the_expected_public_hosts() -> None:
    _, parser = _parse_hub()
    external_hosts = set()

    for href in parser.links:
        parsed = urlparse(href)
        if parsed.scheme in {"http", "https"}:
            external_hosts.add(parsed.netloc)
            continue
        if href.startswith("#"):
            continue
        local_path = (HUB.parent / parsed.path).resolve()
        assert local_path.is_file(), href

    assert external_hosts == {"github.com", "www.nutrient.io", "dashboard.nutrient.io"}
