# Grounded Extraction Demo — Making Home Affordable Program (RMA Form)

This demo extracts structured data from a real 4-page scanned government form using the
[Nutrient Data Extraction API](https://www.nutrient.io/api/data-extraction/).

**Open `output/index.html` in your browser — no setup required.**

Hover over any extracted field in the sidebar. A green bounding box highlights its exact
location on the scanned document.

## What This Shows

Standard document parsers return values. Nutrient's grounded extraction returns values
**plus the pixel-precise location** where each value was found. Every field is anchored
to its source.

## The Tuning Story: How Grounding Makes Errors Auditable

When we first ran this form with a basic schema, the API returned:

```json
"total_gross_income": { "amount": "6,500.00" }
```

The correct value is **$3,450.00**. The page 2 income table has three adjacent columns
(income, expenses, assets) and the model confused the gross income total with the total
assets value.

**With an ungrounded parser, this is invisible.** `6,500.00` appears in your output and
you have no way to know it came from the wrong cell.

**With Nutrient's grounding, it's immediately auditable.** The green highlight box lands
directly on the "Total Assets" cell — you see exactly why the model picked that number.
That turns a silent error into a visible, catchable exception.

The fix was a one-line description change in the schema:

```
❌ "The Total Gross Income from the Monthly Household Income table on page 2."

✅ "The Total Gross Income dollar amount from the LEFTMOST 'Monthly Household Income'
    table on page 2, from the row labeled 'Total (Gross Income)'. This is NOT the
    Total Assets value and NOT the Total Debt/Expenses value."
```

See [`tuning_notes.md`](tuning_notes.md) for the full breakdown.

## Document

**Making Home Affordable Program — Request for Mortgage Assistance (RMA)**
A US federal government form administered by the Department of the Treasury, Fannie Mae,
and Freddie Mac. Used by homeowners requesting mortgage loan modification.

## Running the Demo Yourself

1. Place the RMA PDF at `data/rma_form.pdf`
2. Install dependencies: `pip install -r ../../requirements.txt`
3. Set your API key: `export NUTRIENT_API_KEY=your_key_here`
4. Run from this folder: `python generate_demo.py`
5. Open `output/index.html` in your browser

Get an API key at [nutrient.io](https://www.nutrient.io/api/data-extraction/).
