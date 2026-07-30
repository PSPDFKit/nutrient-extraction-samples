# nutrient-extraction-samples

Interactive demos for the [Nutrient Data Extraction API](https://www.nutrient.io/api/data-extraction/) and [Nutrient Parse API](https://www.nutrient.io/api/data-extraction/).

Each demo is a Python script that calls the API, then generates a self-contained HTML file that opens in any browser — no server, no signup, no API key needed to view the output.

---

## Why grounded extraction matters

Most document AI tools return values. Nutrient returns values **and proof**.

Every extracted field comes with:
- **Bounding box** — the exact pixel region on the page the value was pulled from
- **Confidence score** — how certain the model is about that value
- **Page index** — which page of the document the value lives on

When a value is wrong, there is no need to search the document manually. Hover over the field card and the highlight lands on exactly where the model looked. A wrong highlight location is an immediately visible audit trail.

This is the difference between a black box and an auditable extraction pipeline.

---

## Demos

### 1. CMS-1500 Health Insurance Claim
`demos/grounded_extraction/`

**API:** Data Extraction (grounded schema)
**Document:** CMS-1500, the standard US healthcare reimbursement form
**What it shows:** Table row extraction across a dense printed grid. The form uses a dropout-red ink grid that scanners typically destroy — Nutrient extracts procedure codes, diagnosis codes, billing amounts, and provider fields correctly, each highlighted in the exact table cell it came from.

→ **[Open demo](https://pspdfkit.github.io/nutrient-extraction-samples/demos/grounded_extraction/output/index.html)**

---

### 2. Indiana State Birth Record
`demos/birth_record_extraction/`

**API:** Data Extraction (grounded schema)
**Document:** Indiana Certificate of Live Birth application (state vital records form)
**What it shows:** Signature block detection on a handwritten/printed mixed document. The schema distinguishes between the *printed name* field and the adjacent *cursive signature* — two visually adjacent fields that trip up most models. The demo includes a before/after tuning comparison showing how schema description specificity fixes extraction errors.

→ **[Open demo](https://pspdfkit.github.io/nutrient-extraction-samples/demos/birth_record_extraction/output/index.html)**

---

### 3. Making Home Affordable — Request for Modification
`demos/rma_extraction/`

**API:** Data Extraction (grounded schema)
**Document:** Making Home Affordable Program RMA form (HUD/Treasury)
**What it shows:** Value isolation in a dense 3-column financial table. The form has three adjacent columns (Monthly Income, Total Assets, Total Expenses) with nearly identical labels. The demo includes a tuning story: before/after showing how a vague schema description extracts the wrong column, and how a precise description fixes it — with the highlight visually confirming the correction.

→ **[Open demo](https://pspdfkit.github.io/nutrient-extraction-samples/demos/rma_extraction/output/index.html)**

---

### 4. CA SC-100 Small Claims Court
`demos/sc100_extraction/`

**API:** Data Extraction (grounded schema)
**Document:** California Judicial Council SC-100, Plaintiff's Claim and ORDER to Go to Small Claims Court
**What it shows:** Full narrative paragraph extraction from a free-text legal form field. The `incident_reason` field captures a complete multi-sentence plaintiff explanation across multiple lines — grounded with a single bounding box covering the entire explanation area. Also demonstrates cross-page extraction: five fields pulled from three different pages of the same document.

→ **[Open demo](https://pspdfkit.github.io/nutrient-extraction-samples/demos/sc100_extraction/output/index.html)**

---

### 5. Small Residential Income Property Appraisal Report
`demos/parse_citations/`

**API:** Parse API (layout-aware block decomposition)
**Document:** Freddie Mac Form 72 residential appraisal report
**What it shows:** Document decomposed into semantic blocks — paragraphs, section headers, tables — each with spatial coordinates. Demonstrates the RAG citation use case: every text block in the sidebar links back to its exact location in the document, so retrieval pipelines can cite the source precisely. Use Parse when structure-aware chunking is needed rather than field-level extraction.

→ **[Open demo](https://pspdfkit.github.io/nutrient-extraction-samples/demos/parse_citations/output/index.html)**

---

## How to run any demo

Each demo folder contains:

```
demo_name/
├── docs.json              # extraction schema (or parse config)
├── generate_demo.py       # calls the API, writes the HTML
├── template.html          # visual layout
└── README.md              # demo-specific notes and tuning story
```

```bash
cd demos/grounded_extraction    # or birth_record_extraction, rma_extraction, sc100_extraction, parse_citations
pip install -r ../../requirements.txt
# place your PDF in data/ matching the filename in docs.json
export NUTRIENT_API_KEY=your_key
python3 generate_demo.py
open output/index.html
```

---

## Pre-built outputs

The `output/` folder in each demo contains a pre-committed HTML file built from sample data. Open any of these directly in a browser to see the demo without running the script or owning an API key:

- [`demos/grounded_extraction/output/index.html`](demos/grounded_extraction/output/index.html)
- [`demos/birth_record_extraction/output/index.html`](demos/birth_record_extraction/output/index.html)
- [`demos/rma_extraction/output/index.html`](demos/rma_extraction/output/index.html)
- [`demos/sc100_extraction/output/index.html`](demos/sc100_extraction/output/index.html)
- [`demos/parse_citations/output/index.html`](demos/parse_citations/output/index.html)

---

## Document verticals covered

| Vertical | Demo |
|---|---|
| Healthcare billing | CMS-1500 |
| Government / vital records | Indiana Birth Record |
| Mortgage / housing assistance | Making Home Affordable RMA |
| Legal / civil court | CA SC-100 Small Claims |
| Real estate / lending | Appraisal Report (Form 72) |

---

## Prerequisites

- Python 3.9+
- `poppler` for PDF rendering: `brew install poppler`
- A [Nutrient API key](https://www.nutrient.io/api/)
- Dependencies: `pip install -r requirements.txt`

---

## API reference

- [Data Extraction API docs](https://www.nutrient.io/guides/dws-data-extraction/getting-started/)
- [Parse API docs](https://www.nutrient.io/guides/dws-data-extraction/getting-started/)
- [API reference](https://www.nutrient.io/api/reference/data-extraction/public/#description/introduction)
- [Nutrient Studio](https://dashboard.nutrient.io/data-extraction-api/studio/extract) — test documents visually before writing code

---

## Contributing

To suggest a new document type, open an issue with the document name and the fields to extract.
