# GSA SF 91 extraction with returned source regions

This developer sample maps page 1 of the U.S. General Services
Administration's **Standard Form 91, Motor Vehicle Accident (Crash) Report,
revision 09/2020** to structured fields with independently recorded source
regions.

The blank official form is frozen at `source/SF91-20.pdf` from the canonical
GSA URL:

`https://www.gsa.gov/system/files/SF91-20.pdf`

The one-page demo input is a flattened raster of the official first page with
11 privacy-safe demo values painted into the matching printed fields. It has no
XFA, JavaScript, AcroForm field tree, or Widget annotations. The values are not
customer data, a real person, or a real claim. They do not represent coverage,
liability, fraud, eligibility, payment, or adjudication.

**[Open this reviewed proof on GitHub Pages →](https://pspdfkit.github.io/nutrient-extraction-samples/docs/lighthouse/assets/insurance-claim-intake-reviewed.html?utm_campaign=de_lighthouse_pilot_v1&utm_source=github&utm_medium=repository&utm_content=insurance_claim_intake.github_sample.v01.proof)**

## Rebuild the frozen input and oracle

From the repository root:

```bash
python3 demos/insurance_claim_intake/build_fixture.py
python3 demos/insurance_claim_intake/build_fixture.py --check
```

The builder verifies the frozen official-source and legacy-fixture hashes,
renders only SF 91 page 1, creates the deterministic 612x792 flattened PDF,
and derives `expected.json` only from the 11 values defined in the fixture. It
does not read a credential, call the network, or consume credits.

The earlier bespoke sheet remains byte-for-byte preserved as
`data/legacy-synthetic-insurance-claim-intake.pdf`. The existing cache and
receipt also remain unchanged as historical evidence for that earlier source;
they are not valid replay evidence for the new public-form input.

## Offline provisional package

```bash
python3 demos/insurance_claim_intake/generate_demo.py --provisional
python3 demos/insurance_claim_intake/check_expected.py --allow-provisional
```

Open `demos/insurance_claim_intake/output/index.html` directly. The page is
self-contained. These commands do not read `NUTRIENT_API_KEY`, access or mutate
the historical live cache, call the network, or consume credits. A zero exit
code means only that the fixture-derived values and the 11 manually reviewed
page-0 source boxes match the independent oracle. Provisional evidence cannot
support a release claim.

## Current reviewed live response

The one approved replacement request completed once with HTTP 200. Its reviewed
receipt-bound response matched 11/11 predeclared values exactly, returned 11/11
valid page-bounded primary regions, and retained zero issues. Reproduce it
offline without a credential or network request:

```bash
python3 demos/insurance_claim_intake/generate_demo.py --replay-reviewed
python3 demos/insurance_claim_intake/check_expected.py --reviewed-live
```

Reviewed records the evidence audit; it does not generalize beyond this form or
approve publication.

## Future refresh gate

The approved replacement call is complete. No additional refresh or retry is
authorized. Only `--refresh` can read `NUTRIENT_API_KEY`, call the API, and
consume credits. A future separately approved gate would use:

```bash
python3 demos/insurance_claim_intake/generate_demo.py --refresh
python3 demos/insurance_claim_intake/check_expected.py
python3 demos/insurance_claim_intake/generate_demo.py --replay-live
```

`--refresh` keeps the broad response in memory and writes only the narrow cache
plus its request-ID/SHA-256 receipt. Replays never fall back to provisional evidence.
The retained historical synthetic cache remains deliberately ineligible for
this public-form input.

## Provenance boundary

- Publisher: U.S. General Services Administration
- Form: Standard Form 91, Motor Vehicle Accident (Crash) Report, revision
  09/2020
- Canonical URL: `https://www.gsa.gov/system/files/SF91-20.pdf`
- Original SHA-256:
  `18a11675590189964522114c294b8ea0974f86989fb7f49a31788ba2807d44ac`
- Transformation: rasterize page 1 without form rendering, fit it beneath the
  ASCII provenance rail, and paint only the 11 fixture values into the printed
  fields

Generated provisional artifacts are `provisional/evidence.json`,
`output/source-page.png`, `output/comparison.json`, and `output/index.html`.
