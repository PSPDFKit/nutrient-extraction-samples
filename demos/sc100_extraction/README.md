# Grounded Extraction Demo — California SC-100 Small Claims Court Form

This demo extracts structured data from a real California SC-100 Small Claims court form using the
[Nutrient Data Extraction API](https://www.nutrient.io/api/data-extraction/).

**Open `output/index.html` in your browser — no setup required.**

Hover over any extracted field in the sidebar. A green bounding box highlights its exact location
on the scanned document.

## What This Shows

### Narrative Paragraph Extraction and Grounding

The headline capability: the API extracts a complete multi-sentence free-text explanation from an
open-ended field ("Why are you suing the defendant?") and pins it to its exact location on the page
with a single bounding box. Standard OCR tools return the raw text of that region as noise — they
cannot identify which block is the explanation field, where it begins and ends, or return it as a
structured value.

The extracted narrative:

> *"On 06/02/2026, I paid BrightWave Appliance Repair, LLC $1,850.00 to repair my refrigerator.
> The technician replaced the compressor, but the unit stopped cooling again within 3 days. I
> contacted BrightWave multiple times requesting a refund or proper repair, but they refused to
> correct the work or return my payment."*

That paragraph is returned as a single structured field — not as three fragmented lines — and
grounded to the exact region on the document.

### Cross-Page Extraction

Fields are pulled from pages 2 and 3 of a 4-page form. Each citation shows which page the value
came from. The demo renders all four pages, so hovering any card shows a live highlight on its
source page.

### Legal Entity Handling

`BrightWave Appliance Repair, LLC` is extracted cleanly as the defendant name — the LLC
designation and comma are preserved exactly as written. Ambiguous company name formatting is
handled without schema tuning.

## Fields Extracted

| Field | Value | Page | Confidence |
|---|---|---|---|
| plaintiff_name | Daniel R. Ortiz | 2 | 100% |
| defendant_name | BrightWave Appliance Repair, LLC | 2 | 100% |
| claim_amount.amount | 1,850.00 | 2 | 100% |
| claim_amount.iso_4217_currency_code | USD | 2 | 100% |
| incident_date | 06/02/2026 | 3 | 100% |
| incident_reason | *Full 3-sentence narrative paragraph* | 2 | 100% |

## Document

**California SC-100 — Plaintiff's Claim and ORDER to Go to Small Claims Court**
A standard California judicial council form used to file small claims court cases.
Public government form, filled with sample data.

## Running the Demo Yourself

1. Place the PDF at `data/sc100.pdf`
2. Install dependencies: `pip install -r ../../requirements.txt`
3. Set your API key: add `NUTRIENT_API_KEY=your_key_here` to `.env` at the repo root
4. Run from this folder: `python3 generate_demo.py`
5. Open `output/index.html` in your browser

Get an API key at [nutrient.io](https://www.nutrient.io/api/data-extraction/).
