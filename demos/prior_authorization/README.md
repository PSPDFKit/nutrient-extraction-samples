# CMS GLP-1 Bridge prior-authorization extraction

This developer sample maps page 1 of the official CMS Medicare GLP-1 Bridge
Prior Authorization Request Form to structured intake fields with source
regions. The form contains only clearly fictional, privacy-safe demo values. It
contains no PHI and does not represent a patient, prescription, payer decision,
clinical determination, or coverage outcome.

The unchanged downloaded CMS source is preserved at
`source/cms-glp-1-bridge-original.pdf` with SHA-256
`c223dc0f6acaf1d7b7e345bdf968ba2373ce94b39994b006a1e9915a07768fa0`.
Its canonical publisher URL is `https://www.cms.gov/glp-1-bridge.pdf`.

**[Open this reviewed proof on GitHub Pages →](https://pspdfkit.github.io/nutrient-extraction-samples/docs/lighthouse/assets/prior-authorization-reviewed.html?utm_campaign=de_lighthouse_pilot_v1&utm_source=github&utm_medium=repository&utm_content=prior_authorization.github_sample.v01.proof)**

`data/prior-authorization.pdf` is a deterministic one-page derivative. It
keeps CMS page 1 as vector content, reserves a restrained provenance rail, and
adds only the eleven approved demo values in their printed fields and
checkboxes. It has no AcroForm tree or Widget annotations. The previous bespoke
fixture remains available as `data/legacy-synthetic-prior-authorization.pdf`.

## Rebuild the public-form input

From the repository root:

```bash
python3 demos/prior_authorization/build_public_form.py
```

The builder verifies the approved original hash and prints the derived PDF's
SHA-256. Repeated runs must print the same digest recorded in `fixture.json`.

## Offline provisional package

```bash
python3 demos/prior_authorization/generate_demo.py --provisional
python3 demos/prior_authorization/check_expected.py --allow-provisional
```

Open `demos/prior_authorization/output/index.html` directly. The page is
self-contained. These commands do not read `NUTRIENT_API_KEY`, use a response
cache, call the network, or consume credits. A zero exit code means only that
the fixture-derived values and manually reviewed page-0 source boxes match the
independent oracle. Provisional evidence is not API-performance evidence.

## Live refresh gate

`--refresh` is the only credential-reading and network-capable path. It consumes
Extract API credits and may run only through the separately approved live gate:

```bash
python3 demos/prior_authorization/generate_demo.py --refresh
python3 demos/prior_authorization/check_expected.py
python3 demos/prior_authorization/generate_demo.py --replay-live
```

The historical cache and receipt are preserved, but they are bound to the
legacy synthetic input and cannot serve as evidence for this public-form
fixture. Replays require an exact input/request match.
Replays never fall back to provisional evidence.

After a replacement live response has received a recorded independent review,
reproduce that reviewed state with:

```bash
python3 demos/prior_authorization/generate_demo.py --replay-reviewed
python3 demos/prior_authorization/check_expected.py --reviewed-live
```

These commands replay receipt-bound evidence and its recorded review. They do
not perform a new review or themselves approve publication.

## Boundaries

This is intake and source review only. It does not decide patient care, medical
necessity, coverage, payer action, or compliance. It is not an accuracy,
compliance, security, or performance benchmark. Source regions make results
reviewable; the independent oracle determines whether this single form matches.

Generated artifacts are `provisional/evidence.json`,
`output/source-page.png`, `output/comparison.json`, and `output/index.html`.
