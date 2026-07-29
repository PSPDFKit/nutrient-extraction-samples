# Nutrient Extraction Samples

Self-contained demos for the [Nutrient Data Extraction API](https://www.nutrient.io/api/data-extraction/). Pre-generated HTML outputs are committed to this repo — open any `output/index.html` directly in a browser with no server, no installation, and no API key required.

Regenerating demos with custom documents requires a Nutrient API key.

## Demos

### 1. Grounded Extraction (Hero Demo)
`demos/grounded_extraction/`

Schema-driven field extraction from a scanned government form. Each extracted field is pinned to its exact location on the source document with a bounding box, confidence score, and match grounding — hover a field to see its citation highlight on the document.

→ Open [`demos/grounded_extraction/output/index.html`](demos/grounded_extraction/output/index.html)

### 2. Parse-Based Citations
`demos/parse_citations/`

Document parsing with visual citation overlay. Parsed text blocks are linked back to their source coordinates on the page.

→ Open [`demos/parse_citations/output/index.html`](demos/parse_citations/output/index.html)

## Regenerating demos with custom documents

### Prerequisites

- Python 3.9+
- `poppler` for PDF rendering: `brew install poppler`
- A [Nutrient API key](https://www.nutrient.io/api/)

### Setup

```bash
git clone https://github.com/PSPDFKit/nutrient-extraction-samples.git
cd nutrient-extraction-samples
pip install -r requirements.txt
cp .env.example .env
# Add NUTRIENT_API_KEY to .env
```

### Run

```bash
# Grounded extraction demo
cd demos/grounded_extraction
python generate_demo.py

# Parse citations demo
cd demos/parse_citations
python generate_demo.py
```

## Roadmap

- **Claude Code skill integration** — a one-line install that wires the Nutrient extract skill directly into Claude Code, making this repo a distribution channel for the skill alongside the demos. Pending confirmation of the source skill repo.

## Repo structure

```
nutrient-extraction-samples/
├── demos/
│   ├── grounded_extraction/
│   │   ├── data/              # Source PDFs
│   │   ├── output/            # Pre-generated HTML + PNG (committed)
│   │   ├── docs.json          # Extraction schema config
│   │   ├── generate_demo.py   # Demo generator script
│   │   └── template.html      # HTML template
│   └── parse_citations/
│       ├── data/              # Source PDFs
│       ├── output/            # Pre-generated HTML + PNG (committed)
│       ├── generate_demo.py
│       └── template.html
├── .env.example
└── requirements.txt
```
