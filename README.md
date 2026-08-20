<h1 align="center">Nutrient Extraction Samples</h1>

<p align="center">
  <strong>Extract structured values.<br>Inspect the returned source regions.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-1a1a1a"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-1a1a1a">
  <img alt="8 demos" src="https://img.shields.io/badge/demos-8-1a1a1a">
  <a href="https://www.nutrient.io/guides/dws-data-extraction/getting-started/"><img alt="Nutrient Data Extraction API" src="https://img.shields.io/badge/Nutrient-Data%20Extraction%20API-1a1a1a"></a>
</p>

<p align="center">
  <img src="docs/screenshots/hover-demo.gif" alt="Hovering a field highlights the source region returned for that result" width="100%">
</p>

<p align="center"><em>Hover a field. The demo highlights the source region returned for that result.</em></p>

When the API returns grounding metadata, an extracted field can carry a **bounding box**, a **recognition signal**, and a **page index**. In these reviewed demos, hovering a grounded field shows the source region used for that result. A highlight in the wrong place makes a grounding problem visible; it does not prove the extracted value is correct.

```jsonc
// Send a schema. Get back values with provenance.
"procedure_code": "99213",                                   // the value
"bbox": { "x": 412, "y": 288, "width": 74, "height": 18 },   // where it came from
"confidence": 0.95,                                          // recognition signal; not correctness probability
"pageIndex": 0                                               // which page
```

<p align="center">
  <a href="https://pspdfkit.github.io/nutrient-extraction-samples/demos/grounded_extraction/output/index.html"><strong>Open a live demo →</strong></a>
  &nbsp;·&nbsp;
  <a href="#run-it-yourself"><strong>Run it yourself</strong></a>
  &nbsp;·&nbsp;
  <a href="docs/reproducible-proof.md"><strong>Reproduce the proof</strong></a>
  &nbsp;·&nbsp;
  <a href="docs/lighthouse/index.html"><strong>Browse the hub source</strong></a>
  &nbsp;·&nbsp;
  <a href="#install-the-agent-skill"><strong>Give it to an agent</strong></a>
</p>

---

## Three authentic-form evidence packages

On three selected one-page authentic public forms populated with privacy-safe demo values, one live Nutrient Data Extraction API response per form exactly matched **26 of 30 predeclared fields**: mortgage **6/8**, insurance **11/11**, and healthcare **9/11**. All **30/30** returned fields included valid page-bounded primary source regions, and **four mismatches** were retained for review.

| Package | Selected public form | Exact values | Primary regions returned | Verdict |
|---|---|---:|---:|---|
| [`mortgage_verification`](demos/mortgage_verification/) | U.S. Treasury Request for Mortgage Assistance | 6/8 | 8/8 | Review blocked |
| [`insurance_claim_intake`](demos/insurance_claim_intake/) | GSA Standard Form 91 crash report | 11/11 | 11/11 | 11/11 exact → Continue |
| [`prior_authorization`](demos/prior_authorization/) | CMS GLP-1 Bridge prior-authorization form | 9/11 | 11/11 | Review blocked |

**[Browse the lighthouse hub source →](docs/lighthouse/index.html)**

**[Open the reviewed proof hub on GitHub Pages →](https://pspdfkit.github.io/nutrient-extraction-samples/docs/lighthouse/?utm_campaign=de_lighthouse_pilot_v1&utm_source=github&utm_medium=repository&utm_content=cross_vertical.github_sample.v01.proof)**

This is a three-document demonstration, not an accuracy, production, or performance benchmark. “Reviewed” means that an independent field-by-field evidence audit was recorded; it is not user approval or publication approval. Three of the four mismatches are exposed by returned metadata. The mortgage servicer primary and nested regions clip the decisive final period, so the fourth issue remains visible in the expected-versus-actual ledger beside the returned region. The forms contain privacy-safe demo values—not real people, real claims, PHI, lending decisions, adjudication, coverage decisions, or clinical determinations.

Pricing and credit usage can change. Check the current official pricing before making a live request. The retained evidence does not independently reconcile account usage or billing.

---

## Five additional documents, five hard problems

Each demo is a Python script that calls the API and generates a self-contained HTML file. The generated output is committed — open any of them in a browser with no signup, no key, and no install.

<table>
<tr>
<td width="50%" valign="top">

### CMS-1500 Health Insurance Claim
`demos/grounded_extraction/` · Data Extraction

Table row extraction across a dense printed grid. The reviewed output includes service dates, procedure codes, billing amounts, and provider fields, with displayed grounded values linked to their returned source regions. The source checker also exposes two incorrect service dates in the committed response.

**[Open demo →](https://pspdfkit.github.io/nutrient-extraction-samples/demos/grounded_extraction/output/index.html)**

</td>
<td width="50%" valign="top">

### Indiana State Birth Record
`demos/birth_record_extraction/` · Data Extraction

Signature block detection on a mixed handwritten/printed document. The schema separates the *printed name* from the adjacent *cursive signature*. The tuning notes document one observed mismatch and a later reviewed response after the schema description was clarified.

**[Open demo →](https://pspdfkit.github.io/nutrient-extraction-samples/demos/birth_record_extraction/output/index.html)**

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Making Home Affordable — RMA
`demos/rma_extraction/` · Data Extraction

Value isolation in a dense 3-column financial table. Monthly Income, Total Assets, and Total Expenses sit side by side with similar labels. The tuning notes compare one wrong cached result with a later reviewed result after the schema description was clarified; the highlights show the regions returned for each response.

**[Open demo →](https://pspdfkit.github.io/nutrient-extraction-samples/demos/rma_extraction/output/index.html)**

</td>
<td width="50%" valign="top">

### CA SC-100 Small Claims
`demos/sc100_extraction/` · Data Extraction

Full narrative extraction from a free-text legal field. `incident_reason` captures a complete multi-sentence plaintiff explanation across multiple lines, grounded with a single box covering the whole area. Also shows cross-page extraction: five fields from three different pages.

**[Open demo →](https://pspdfkit.github.io/nutrient-extraction-samples/demos/sc100_extraction/output/index.html)**

</td>
</tr>
<tr>
<td colspan="2" valign="top">

### Small Residential Income Property Appraisal Report
`demos/parse_citations/` · Parse API

The document decomposed into semantic blocks — paragraphs, section headers, and tables — with spatial coordinates. In this reviewed response, each rendered block links to its returned source region. Reach for Parse when you need structure-aware chunking rather than field-level extraction.

**[Open demo →](https://pspdfkit.github.io/nutrient-extraction-samples/demos/parse_citations/output/index.html)**

</td>
</tr>
</table>

| Vertical | Demo |
|---|---|
| Healthcare billing | CMS-1500 |
| Government / vital records | Indiana Birth Record |
| Mortgage / housing assistance | Making Home Affordable RMA |
| Legal / civil court | CA SC-100 Small Claims |
| Real estate / lending | Appraisal Report (Form 72) |

<details>
<summary><strong>Screenshots</strong> — the hover interaction in each demo</summary>

![CMS-1500 extraction demo — procedure code highlighted in the billing grid](docs/screenshots/grounded-extraction.png)
![Indiana birth record demo — applicant signature field highlighted](docs/screenshots/birth-record-extraction.png)
![RMA extraction demo — monthly income field isolated in the 3-column financial table](docs/screenshots/rma-extraction.png)
![SC-100 extraction demo — plaintiff narrative paragraph highlighted across multiple lines](docs/screenshots/sc100-extraction.png)
![Parse citations demo — semantic block highlighted with its location in the appraisal document](docs/screenshots/parse-results.png)

</details>

---

<h2 id="run-it-yourself">Run it yourself</h2>

Just want to look? Every `output/index.html` is committed — open one in a browser and you're done. To regenerate against your own documents:

```bash
# 1. Python 3.10+
pip install -r requirements.txt

# 2. Replay the committed cache (no API key or credits required)
cd demos/grounded_extraction
python3 generate_demo.py
open output/index.html

# 3. To replace the cache with a live response, provide your Data Extraction
#    key (separate from the Processor API key) and opt in explicitly
NUTRIENT_API_KEY=your_key python3 generate_demo.py --refresh
```

Every demo folder is the same four files:

```
demo_name/
├── docs.json          # extraction schema (or parse config)
├── generate_demo.py   # replays cache; --refresh calls API
├── template.html      # visual layout
└── README.md          # demo notes and tuning story
```

**Getting a key.** Data Extraction uses a **separate product key from the Processor API key**. You only need one for a live `--refresh` run. Sign up, open the dashboard, or try the playground on the [Data Extraction API page](https://www.nutrient.io/api/data-extraction-api/).

Prefer to try before writing code? Test documents visually in [Nutrient Studio](https://dashboard.nutrient.io/data-extraction-api/studio/extract).

---

## What a run costs

Parse credits are charged by mode and page. **Extract requests add 6 credits per page on top of the Parse rate**, so an `agentic` extraction costs 24 credits per page.

| Mode | Parse credits per page |
|---|---:|
| `text` | 1 |
| `structure` | 1.5 |
| `understand` | 9 |
| `agentic` | 18 |

All eight demos use `agentic` mode.

| Demo | Pages | Normal run | If run live |
|---|---:|---:|---:|
| CMS-1500 | 1 | 0 | 24 |
| Indiana Birth Record | 1 | 0 | 24 |
| Request for Modification | 4 | 0 | 96 |
| CA SC-100 | 4 | 0 | 96 |
| Authentic-form mortgage verification | 1 | 0 | 24 |
| Authentic-form insurance claim intake | 1 | 0 | 24 |
| Authentic-form prior authorization | 1 | 0 | 24 |
| **Extraction subtotal** | **13** | **0** | **312** |
| Appraisal Report (Parse) | 4 | 0 | 72 |
| **Total** | **17** | **0** | **384** |

Every normal generator run replays its committed cache and costs **0 credits**. Network access is opt-in through `--refresh`: refreshing all seven extraction demos costs 312 credits, and refreshing all eight demos costs 384 credits.

The free tier includes 5,000 credits per month, enough for about **13 live all-eight refreshes**.

---

## Privacy and PII before you commit

Extraction lifts document values into every derivative, so review more than the PDFs. Before committing a document swap, check:

- `demos/*/data/*.pdf` — public-source, synthetic, or authentic public forms with privacy-safe demo values only
- `demos/*/output/metadata.json` — document values and non-billing response metadata
- `demos/parse_citations/data/*_parse_results.json` — document text
- `demos/*/cache/*.json` — the full `output` payload
- `demos/*/output/index.html` — rendered field values

Two things to know about what is already committed here:

**An SSN-formatted value.** `000-45-6789` appears in `rma_extraction`'s `metadata.json`, `cache/*.json`, and `output/index.html`. The `000-` prefix is never issued by the SSA — this is a synthetic value from the sample form used for demonstration purposes. The RMA schema requests `borrower_ssn`, so if replacing the source PDF with a real document, confirm the form contains no actual SSN before committing.

**The metadata files don't all have the same shape.** `birth_record_extraction`, `grounded_extraction`, and `rma_extraction` contain the safe persisted response fields; `sc100_extraction` contains derived display-card data only. The cache projection excludes the API's top-level `usage` field and its account billing data.

Full pre-publication procedure: [`docs/launch-checklist.md`](docs/launch-checklist.md).

---

<h2 id="install-the-agent-skill">Install the agent skill</h2>

Agents can call the Data Extraction API directly through the `document-extraction-api` skill in [`PSPDFKit-labs/nutrient-skills`](https://github.com/PSPDFKit-labs/nutrient-skills), verified at revision `3da3211` (PR #27, merged 2026-07-23):

```bash
npx skills add pspdfkit-labs/nutrient-skills --skill document-extraction-api
```

The skill bundles a schema-driven extract script with per-field citations and a cost preflight, plus reference docs on schema design and reading citation output. Reach for the skill when an agent should run extractions itself; reach for these demos when a human wants to see grounded extraction with its highlights.

The pin is deliberate: install resolves against upstream `main`, so record the revision you verified and re-review before moving it.

---

## API reference

- [Data Extraction API docs](https://www.nutrient.io/guides/dws-data-extraction/getting-started/)
- [Parse API docs](https://www.nutrient.io/guides/dws-data-extraction/getting-started/)
- [API reference](https://www.nutrient.io/api/reference/data-extraction/public/#description/introduction)
- [Nutrient Studio](https://dashboard.nutrient.io/data-extraction-api/studio/extract) — test documents visually before writing code

## Sample code disclaimer

Documents in this repository are public-source, synthetic, or authentic public forms populated with privacy-safe demo values. Extraction results are illustrative only.

This repository is sample code, not a production-ready workflow. Before processing real documents:

- Validate extracted outputs before using them in automation
- Ensure handling of regulated or personal data complies with applicable laws (HIPAA, GDPR, CCPA, and others)
- Review all derivatives — `metadata.json`, cache files, and rendered HTML — for sensitive values before committing

---

## Contributing

To suggest a new document type, open an issue with the document name and the fields to extract. To add one yourself, copy an existing demo folder, swap the PDF and `docs.json`, and run the generator — then run the PII review above before committing.

Shared helpers live in `common/` (cache, escaping, rendering), and all eight demo generators use them.

## License

MIT — see [LICENSE](LICENSE).
