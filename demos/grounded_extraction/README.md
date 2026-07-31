# Grounded Extraction Demo — CMS-1500 Health Insurance Claim

This demo extracts structured data from a real CMS-1500 health insurance claim form using the
[Nutrient Data Extraction API](https://www.nutrient.io/api/data-extraction-api/).

**Open `output/index.html` in your browser — no setup required.**

Hover over any extracted field in the sidebar. A green bounding box highlights its exact location
on the form.

## What This Shows

### Dense Table Row Extraction and Grounding

The CMS-1500 places service-line data inside a dense printed grid. The API returns each row as a
structured object containing the date of service, procedure code, line charge, and rendering
provider NPI. Each value is grounded to the exact table cell where it was found.

### Repeating Structured Data

The `service_lines` array preserves the relationship between values from the same claim row
instead of returning a flat collection of disconnected text. The demo also extracts top-level
fields such as the patient name, insured ID, prior authorization number, and total charge.

### Auditable Healthcare Extraction

The dropout-red grid and compact box labels make this form difficult to inspect as plain OCR.
Grounding makes the result reviewable: hovering over a value shows whether it came from the
expected box or service-line cell.

## Document

**CMS-1500 Health Insurance Claim Form**
The standard US healthcare claim form used for professional medical billing.
This one-page sample is filled with synthetic data.

## Running the Demo Yourself

1. Use Python 3.10 or newer.
2. Install dependencies: `pip install -r ../../requirements.txt`
3. From this folder, replay the committed response cache (no API key or network
   request required): `python3 generate_demo.py`
4. Open `output/index.html` in your browser.

To extract a replacement document, place it at `data/CMS-1500.pdf` and opt in to the
keyed network path:

```bash
NUTRIENT_API_KEY=your_key_here python3 generate_demo.py --refresh
```

Get a Data Extraction API key at
[nutrient.io](https://www.nutrient.io/api/data-extraction-api/).
