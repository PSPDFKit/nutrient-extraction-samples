"""Generate the authentic GSA SF 91 lighthouse package."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.lighthouse_package import PackageConfig, generator_main  # noqa: E402


CONFIG = PackageConfig(
    demo_dir=Path(__file__).resolve().parent,
    slug="insurance_claim_intake",
    page_title="A loss notice, mapped back to source",
    provisional_summary=(
        "An offline layout rehearsal for the authentic GSA SF 91 with "
        "privacy-safe demo values. No API call was made, and this is not "
        "release evidence."
    ),
    live_summary=(
        "A receipt-bound live Extract response over the authentic GSA SF 91 "
        "demo input, paired with source grounding. Independent evidence review "
        "remains required."
    ),
    reviewed_summary=(
        "A receipt-bound live Extract response with a recorded independent "
        "field-by-field audit against the visible authentic public form. The "
        "package retains every exact match and mismatch; the page shows the "
        "API's primary returned source region for each field."
    ),
)


if __name__ == "__main__":
    raise SystemExit(generator_main(CONFIG))
