# Mortgage-assistance form extraction

This developer sample maps page 1 of an authentic public Request for Mortgage
Assistance (RMA) form to eight reviewable fields. The visible names,
identifiers, address, phone number, selections, and hardship explanation are
privacy-safe demo values. They are not customer data, a real borrower, or a
lending decision.

The committed output is a reviewed, receipt-bound live API response over this
public-form demo input. It matched 6/8 predeclared values exactly, returned a
valid page-bounded primary region for all eight fields, and retains both
punctuation mismatches. Reviewed does not mean correct, and it does not approve
publication.

**[Open this reviewed proof on GitHub Pages →](https://pspdfkit.github.io/nutrient-extraction-samples/docs/lighthouse/assets/mortgage-verification-reviewed.html?utm_campaign=de_lighthouse_pilot_v1&utm_source=github&utm_medium=repository&utm_content=mortgage_verification.github_sample.v01.proof)**

## Source and transformation

- Publisher: U.S. Department of the Treasury, Making Home Affordable.
- Form: Request for Mortgage Assistance (RMA).
- Program context: <https://home.treasury.gov/data/troubled-assets-relief-program/housing/mha>.
- Frozen original: `source/rma_form.pdf`.
- Original SHA-256:
  `15ea438e22263407da910f88ac353855c205cfe4cf479ef17468cb74b683db8c`.
- Derived demo SHA-256:
  `2eab5c8c1c843ef5f0f0bef9e361f818369a6e5e7652f00e6e614d381a36018e`.

The exact historical download URL for the repository scan was not recorded.
The Treasury URL above is canonical program context and is not claimed to be
the byte-download URL for the frozen file.

`build_public_form.py` verifies the original bytes, preserves the previous
bespoke PDF as `data/legacy-synthetic-mortgage-verification.pdf`, rasterizes
source page 1, and fits it beneath the provenance rail on one exact 612x792
PDF page. The result contains no AcroForm field tree, Widget annotations, or
JavaScript. The eight source boxes in `fixture.json` were independently drawn
over the final rendered page and visually checked against their exact values.

Rebuild the deterministic PDF from the repository root:

```bash
python3 demos/mortgage_verification/build_public_form.py
```

Two consecutive builds must report the same derived SHA-256 above.

## Offline provisional proof

From the repository root:

```bash
python3 demos/mortgage_verification/generate_demo.py --provisional
python3 demos/mortgage_verification/check_expected.py --allow-provisional
```

Open `demos/mortgage_verification/output/index.html` directly. The page is
self-contained. These commands do not read `NUTRIENT_API_KEY`, access a live
cache, call the network, or consume credits. A zero exit code means only that
the fixture-derived values and independently recorded source boxes match the
oracle in `expected.json`.

## Live refresh gate

Only `--refresh` can read `NUTRIENT_API_KEY`, call the Data Extraction API, and
consume credits. Run it only within an explicitly approved live gate:

```bash
python3 demos/mortgage_verification/generate_demo.py --refresh
python3 demos/mortgage_verification/check_expected.py
python3 demos/mortgage_verification/generate_demo.py --replay-live
```

The refresh path writes a new cache whose key is bound to this public-form PDF
and a matching request-ID/SHA-256 receipt. Historical synthetic caches and
receipts remain preserved and are not valid evidence for the new input. Live
replays require both a matching cache and receipt; they never fall back to provisional evidence.

After the live response has received a recorded independent review, reproduce
that reviewed state with:

```bash
python3 demos/mortgage_verification/generate_demo.py --replay-reviewed
python3 demos/mortgage_verification/check_expected.py --reviewed-live
```

Those flags reproduce a recorded review; they do not perform a new review or
approve publication.

## Boundaries

This sample demonstrates extraction and returned primary source regions. It is not
KYC, underwriting, an eligibility decision, or an accuracy, compliance,
security, or performance benchmark. The servicer region clips the decisive
final period, so the page does not claim complete semantic grounding.

Generated artifacts are `provisional/evidence.json`,
`output/source-page.png`, `output/comparison.json`, and `output/index.html`.
The current output artifacts represent the reviewed public-form response;
historical captures in `output/playwright/` remain legacy evidence.
