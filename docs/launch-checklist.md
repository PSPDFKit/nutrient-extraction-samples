# Maintainer checklist

This repository is public. Use this checklist when adding new demos or swapping source documents.

---

## Adding a new demo

- [ ] Source PDF is public-domain, synthetic, or explicitly licensed for redistribution
- [ ] All names, identifiers, and personal values in the document are synthetic or anonymized
- [ ] Generator committed, `docs.json` schema defined, template renders correctly
- [ ] Cache seeded (`python common/seed_cache.py`) so the demo runs without an API key
- [ ] `output/index.html` committed and opens correctly in a browser
- [ ] Screenshot added to `docs/screenshots/` and referenced in the README
- [ ] Per-demo `README.md` written with a tuning story or usage note
- [ ] PII review completed on all derivatives (see [Privacy section in README](../README.md#privacy-and-pii-before-you-commit))

## Before any `--refresh` run

- [ ] API key is set in `.env` and is not committed
- [ ] Confirm the refresh will not capture real document values (synthetic source only)
- [ ] Check that `metadata.json` output does not include the `usage` field after the run

## Secret scanning

Run against full history before any major release:

```bash
gitleaks detect --source . --log-opts="--all" --redact
```

Extraction API keys are `pdf_live_`-prefixed. The scanner covers all key shapes; the prefix check is a supplement only.

## Known committed values

**SSN-formatted value:** `000-45-6789` appears in `rma_extraction`'s `metadata.json`, `cache/*.json`, and `output/index.html`. The `000-` prefix is never issued by the SSA — this is a synthetic value from a sample form used for demonstration purposes only.

**Billing data:** The `usage` field (remainingCredits, price_composition) was stripped from all committed `metadata.json` files. The `common/` cache layer excludes the `usage` field on all future runs.
