# Reproduce one grounded extraction

This path fixes the document, instructions, response projection, source-reviewed ground truth, and regression command so the example can be inspected without relying on a screenshot or a marketing claim. It deliberately exposes a known extraction failure; it is not presented as an accuracy success.

## Reviewed inputs and output

- Document: [`demos/grounded_extraction/data/CMS-1500.pdf`](../demos/grounded_extraction/data/CMS-1500.pdf), a one-page form filled with synthetic values.
- Request instructions: [`demos/grounded_extraction/instructions.json`](../demos/grounded_extraction/instructions.json).
- Sanitized response projection: [`demos/grounded_extraction/cache/b8cec10a5a750bbe1e40e8a628e2f1bc9e6644e22fd7cd12a0397200eebc5dda-extraction-extract-9d969f5b8b34b9942b916be84e5e124a1c971cc584fa2803e2c8efc68aa4acec.json`](../demos/grounded_extraction/cache/b8cec10a5a750bbe1e40e8a628e2f1bc9e6644e22fd7cd12a0397200eebc5dda-extraction-extract-9d969f5b8b34b9942b916be84e5e124a1c971cc584fa2803e2c8efc68aa4acec.json). It is not the service's complete raw transport envelope.
- Reviewed rendering, source ground truth, and generated metadata: [`demos/grounded_extraction/output/index.html`](../demos/grounded_extraction/output/index.html), [`expected.json`](../demos/grounded_extraction/expected.json), and [`metadata.json`](../demos/grounded_extraction/output/metadata.json).
- Deterministic checker: [`demos/grounded_extraction/check_expected.py`](../demos/grounded_extraction/check_expected.py).

The response is illustrative, not a promise that a later model version will return identical values. Grounding metadata shows what source region the response refers to; it does not establish that the value is correct.

Direct review of the synthetic PDF finds `07 10 26` in Box 24A for both service lines, matching the schema's requested `MM DD YY` format. The committed response instead contains `10 26 07` and `10 07`. `expected.json` records the document values, so the checker intentionally reports both fields as `WRONG`. A corrected public proof requires a newly reviewed keyed response or a different independently verified fixture; the cached response must not be edited to manufacture a pass.

## Replay the reviewed response offline

From a clean checkout with Python 3.10 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
cd demos/grounded_extraction
python generate_demo.py
python check_expected.py
```

The generator is cache-first. Without `--refresh`, it neither reads `NUTRIENT_API_KEY` nor calls the network. `python check_expected.py` currently exits nonzero for the two service-date mismatches above. The regression suite passes only when it verifies that those known mismatches are detected; it does not declare the cached response correct. The suite also pins the reviewed artifact hashes and fails if the committed cache no longer reproduces them.

## Make the live request

Live extraction requires a Data Extraction API key and consumes credits. Run this from the repository root:

```bash
curl --fail-with-body \
  --request POST \
  --url https://api.nutrient.io/extraction/extract \
  --header "Authorization: Bearer ${NUTRIENT_API_KEY}" \
  --form "file=@demos/grounded_extraction/data/CMS-1500.pdf;type=application/pdf" \
  --form "instructions=<demos/grounded_extraction/instructions.json;type=application/json"
```

Do not commit a live response until every derivative has passed the repository's privacy and PII checklist. A new response may differ from the tagged example because the service and its models can change.

## Known limits

- The source document and committed response are a reviewed synthetic example, not an accuracy benchmark.
- The committed response contains the two service-date errors described above and therefore is not a passing launch proof.
- Recognition and grounding signals are not calibrated correctness probabilities.
- Some responses or fields may not contain grounding metadata.
- The generated HTML is sample code, not a production review or approval workflow.
- Before using extracted values in automation, validate them against the source and apply the controls required for the document's sensitivity.

## Observed failure example

An earlier schema for the RMA demo returned `6,500.00` for `total_gross_income`; the reviewed expected value was `3,450.00`. Its returned source region pointed to the adjacent Total Assets cell. A more specific schema description corrected that reviewed example. See the [RMA tuning notes](../demos/rma_extraction/tuning_notes.md). This example shows how grounding can expose a source mismatch; it is not a general accuracy comparison.
