# Grounded Extraction Demo — Indiana Birth Record Application

This demo extracts structured data from a real scanned government form using the
[Nutrient Data Extraction API](https://www.nutrient.io/api/data-extraction-api/).

**Open `output/index.html` in your browser — no setup required.**

Hover over any extracted field in the sidebar. A green bounding box highlights its exact
location on the scanned document.

## What This Shows

### Handwritten Signature Detection
The API detects whether a handwritten signature is present, returns a YES/NO flag, and
pins a bounding box to the exact ink strokes on the page. Standard OCR engines skip
cursive signatures entirely. This API returns a structured signature block:

```json
"applicant_signature_block": {
  "printed_name": "Olivia Grace Bennett",
  "signature_date": "07/28/2026",
  "is_signed": "YES",
  "title_or_role": "Signature of Applicant"
}
```

### Dotted-Line Noise Isolation
Scanned government forms are filled with dotted guidelines that cause standard OCR to
misread dots as decimals or garbled characters. Hover over `date_of_birth` or
`mailing_address` — the highlight lands precisely on the filled value without bleeding
into the printed label or surrounding dots.

### Auditable Schema Tuning
In an early run, `applicant_signature_block.printed_name` returned `"O.G. Bennet"` —
grabbed from the cursive signature scrawl — instead of `"Olivia Grace Bennett"` from
the printed name field directly above it. Because the API grounds every value to its
source, the highlight landed on the signature, making the mismatch immediately visible.

One description change fixed it. See [`tuning_notes.md`](tuning_notes.md).

## Document

**Indiana Application for Search and Certified Copy of Birth Record**
State Form 49607 (R12/1-24) — Indiana Department of Health, Division of Vital Records.
A public government form used to request certified birth record copies.

## Running the Demo Yourself

1. Use Python 3.10 or newer.
2. Install dependencies: `pip install -r ../../requirements.txt`
3. From this folder, replay the committed response cache (no API key or network
   request required): `python3 generate_demo.py`
4. Open `output/index.html` in your browser.

To extract a replacement document, place it at `data/birth_record.pdf` and opt in to
the keyed network path:

```bash
NUTRIENT_API_KEY=your_key_here python3 generate_demo.py --refresh
```

Get an API key at [nutrient.io](https://www.nutrient.io/api/data-extraction-api/).
