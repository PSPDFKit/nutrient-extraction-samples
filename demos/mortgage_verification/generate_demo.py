"""Generate the mortgage-verification lighthouse package."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.lighthouse_package import PackageConfig, generator_main


CONFIG = PackageConfig(
    demo_dir=Path(__file__).resolve().parent,
    slug="mortgage_verification",
    page_title="Mortgage-assistance form extraction",
    provisional_summary=(
        "An offline layout proof over an authentic Treasury RMA public form "
        "carrying privacy-safe demo values. No API call was made, and this is "
        "not release evidence."
    ),
    live_summary=(
        "A receipt-bound live Extract response over the authentic public RMA "
        "demo input. Independent evidence review remains required before "
        "public use."
    ),
    reviewed_summary=(
        "A receipt-bound live Extract response with a recorded independent "
        "field-by-field audit against the visible public-form source. The "
        "package retains every exact match and mismatch; the page shows the "
        "API's primary returned source region for each field."
    ),
)


if __name__ == "__main__":
    raise SystemExit(generator_main(CONFIG))
