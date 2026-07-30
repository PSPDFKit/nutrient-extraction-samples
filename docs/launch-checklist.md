# Pre-public launch checklist

This repository is currently **private**. Everything committed before the visibility flip becomes
public retroactively, so the scans below are **re-run against final history immediately before the
flip** — the results recorded here are a first pass, not the record of what actually ships.

Owners are named because two items need someone with credentials or authority this checklist can't
supply.

---

## 1. Secret scan (owner: flip owner, re-run at flip time)

Full history, not just the working tree.

```bash
gitleaks detect --source . --log-opts="--all" --redact
```

Use gitleaks with provider rules rather than a prefix grep — a grep for one key shape misses
everything it wasn't told to look for. Extraction API keys are `pdf_live_`-prefixed; that pattern is
a supplement to the scanner, never a substitute.

- [ ] First pass run and clean
- [ ] **Re-run on final history immediately before the flip**

## 2. PII and billing-data review (owner: flip owner, re-run at flip time)

Extraction lifts document values into every derivative, so the review covers more than the PDFs.

| Surface | What to check |
|---|---|
| `demos/*/data/*.pdf` | Public-source or synthetic only |
| `demos/*/output/metadata.json` | Document values; **account billing fields** (see below) |
| `demos/parse_citations/data/*_parse_results.json` | Document text |
| `demos/*/cache/*.json` | Full `output` payload per demo |
| `demos/*/output/index.html` | Rendered field values |

Two known items:

- **Account billing data is committed.** `birth_record_extraction`, `grounded_extraction`, and
  `rma_extraction` `output/metadata.json` files are full API responses including
  `usage.data_extraction_credits.remainingCredits` and `usage.price_composition` (costs, unit costs,
  currency). `sc100_extraction`'s file is derived card data and is clean. Decide whether to strip
  these before publication. The `common/` cache layer already stores only
  `status`/`requestId`/`output`/`reconstructed`, so newly generated caches don't carry it.
- **An SSN-formatted value is committed.** `000-45-6789` appears in `rma_extraction`'s
  `output/metadata.json`, `cache/*.json`, and `output/index.html`. The `000-` prefix is never issued
  by the SSA, so it reads as synthetic — confirm that, since the RMA schema requests `borrower_ssn`
  and a filled source form would commit a real one.

- [ ] Every surface above reviewed
- [ ] Billing-field decision made (strip or accept)
- [ ] SSN value confirmed synthetic
- [ ] **Re-run on final history immediately before the flip**

## 3. Keyed `--refresh` smoke (owner: whoever holds an extraction key)

**Blocking gate before the flip.** Nothing in this repo has been verified against the live API since
the hardening landed. Run one extraction demo and the parse demo with a real key and confirm:

- [ ] Both requests succeed (the preserved request shapes still work)
- [ ] Rendered output still matches what's committed (overlays land correctly)
- [ ] Error paths don't print the `Authorization` header or key
- [ ] Parse mode question resolved: `docs.json` and the committed response echo both say `agentic`,
      but the sidecar's echo records `outputFormat: "both"` while the generator sends the elements
      shape. Confirm which is authoritative — only the person who ran the original capture knows.

Upgrade this to pre-merge if a key becomes available sooner.

## 4. Repo hygiene (owner: Marija)

- [ ] LICENSE present (MIT — landed)
- [ ] Screenshots in the README, one per demo showing the hover interaction
- [ ] GitHub Pages configured so demos open from a URL without cloning
- [ ] Tuning-story copy reviewed (RMA and SC-100 schema descriptions as teaching examples)

## 5. Visibility flip (owner: Marija / Jonathan)

- [ ] Items 1–3 all pass **on final history**
- [ ] Flip to public

Note: PR descriptions, review comments, and issue text become public too. This checklist covers git
history; skim the PR bodies before flipping.
