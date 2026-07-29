# Schema Tuning Notes — RMA Form

## The Problem: Dense Multi-Column Table

Page 2 of the RMA form contains three side-by-side financial tables:

| Monthly Household Income | Monthly Household Expenses/Debt | Household Assets |
|--------------------------|----------------------------------|------------------|
| ...                      | ...                              | ...              |
| Total (Gross Income): $3,450 | Total Debt/Expenses: $2,210 | Total Assets: $6,500 |

All three "total" rows are at the same vertical position on the page. In the initial
extraction run, the API returned `total_gross_income.amount = 6,500.00` — the Total
Assets value — instead of the correct `3,450.00`.

## Why It Happened

The initial schema description was:

> "The Total (Gross Income) from the Monthly Household Income table on page 2."

This was not specific enough to differentiate the leftmost total from the rightmost total
in a dense three-column layout. The model selected the most salient dollar total at the
bottom of the table, which happened to be the largest value: $6,500.

## The Fix

Updated the schema description to:

> "The Total Gross Income dollar amount from the LEFTMOST 'Monthly Household Income'
> table on page 2, from the row labeled 'Total (Gross Income)'. This is NOT the
> Total Assets value and NOT the Total Debt/Expenses value."

This explicitly anchors the field to the correct column and uses negative examples to
rule out the adjacent totals.

## Before vs. After

| | Before | After |
|---|---|---|
| Schema description | "The Total Gross Income from the income table on page 2." | "...from the LEFTMOST table...NOT the Total Assets value..." |
| Extracted value | $6,500.00 ❌ | $3,450.00 ✓ |
| Grounding highlight | Lands on Total Assets cell | Lands on Total (Gross Income) cell |

## Key Takeaway

Grounding doesn't just fix errors — it makes them **visible before they reach production**.
Without the bounding box showing exactly where $6,500.00 came from, this error would
have required a manual audit of all four pages to catch.

## Future Enhancement

Consider adding an interactive before/after toggle to the HTML demo that switches between
the two JSON outputs and shows both highlights side by side. This would let developers
see the incorrect highlight (Total Assets) vs. the correct one (Gross Income) without
needing to read code. Flagged for a future version.
