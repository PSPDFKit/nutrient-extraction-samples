"""Check prior-authorization intake evidence against the source oracle."""

from __future__ import annotations

try:
    from .generate_demo import CONFIG
except ImportError:
    from generate_demo import CONFIG

from common.lighthouse_package import checker_main


if __name__ == "__main__":
    raise SystemExit(checker_main(CONFIG))
