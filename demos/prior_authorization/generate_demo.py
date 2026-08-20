"""Generate the prior-authorization intake lighthouse package."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.lighthouse_package import PackageConfig, generator_main


CONFIG = PackageConfig(
    demo_dir=Path(__file__).resolve().parent,
    slug="prior_authorization",
    page_title="CMS prior-authorization intake, field by field",
    provisional_summary=(
        "An offline rehearsal of an authentic CMS public form with privacy-safe "
        "demo values and independently reviewed source regions. No API call was "
        "made, and this is not release evidence."
    ),
    live_summary=(
        "A receipt-bound live Extract response compared with the independent "
        "public-form oracle. Independent evidence review remains required."
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
