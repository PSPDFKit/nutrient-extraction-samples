# Parse Demo — Small Residential Income Property Appraisal Report

This demo uses the [Nutrient Parse API](https://www.nutrient.io/api/document-parsing/) to decompose a 4-page appraisal report into spatially-grounded semantic blocks.

**Open `output/index.html` in your browser — no setup required.**

Hover over any block in the sidebar. A blue bounding box highlights its exact location on the document.

## What This Shows

### Layout-Aware Parsing for RAG Pipelines

Standard text extraction collapses all content into a flat string. The Parse API returns each semantic region as a discrete block with its coordinates on the page — paragraph, table, picture, or section header. Every block carries:

- **`type`** — the structural role (`paragraph`, `table`, `picture`)
- **`role`** — semantic annotation when present (`SectionHeader`)
- **`bounds`** — `{x, y, width, height}` in PDF coordinate space
- **`readingOrder`** — the correct reading sequence, even across multi-column layouts
- **`confidence`** — parser confidence score per block

This is the foundation for layout-aware RAG chunking: instead of splitting on token count, you split on natural document boundaries and attach source coordinates to every chunk. A retrieval result carries its own citation — not just the text, but exactly where on the document it came from.

### The Document

**Freddie Mac Form 72 — Small Residential Income Property Appraisal Report** (sample).
A standard multi-page real estate appraisal form that mixes narrative commentary sections (neighborhood description, market conditions, appraiser remarks) with structured fields and tables. The narrative sections are why this document is a good parse target: they contain the kind of free-form text a RAG system needs to retrieve accurately, and the coordinates ground every retrieved chunk back to its source.

Page 1 alone contains 243 parsed blocks in reading order.

## Running the Demo Yourself

1. Place the PDF at `data/appraisal_report.pdf`
2. Install dependencies: `pip install -r ../../requirements.txt`
3. Set your API key: add `NUTRIENT_API_KEY=your_key_here` to `.env` at the repo root
4. Run from this folder: `python3 generate_demo.py`
5. Open `output/index.html` in your browser

Get an API key at [nutrient.io](https://www.nutrient.io/api/).

## Parse API vs. Extract API

| | Parse API | Extract API |
|---|---|---|
| Endpoint | `/parse` | `/extraction/extract` |
| Output | `output.elements[]` — semantic blocks | `output.data` + `output.metadata` — schema fields |
| Input | PDF, mode (`understand`) | PDF, schema (JSON Schema) |
| Use case | Chunking, layout analysis, RAG indexing | Structured field extraction, form processing |
| Highlights | Blue `#00aaff` in this demo | Green `#00ff66` in extraction demos |

The extraction demos in this repo (`grounded_extraction`, `rma_extraction`, `birth_record_extraction`) use the Extract API with a schema. This demo uses the Parse API — a different endpoint with a different output structure entirely.
