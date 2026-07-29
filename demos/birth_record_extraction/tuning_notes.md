# Schema Tuning Notes — Indiana Birth Record

## The Problem: Printed Name vs. Handwritten Signature

The bottom of the Indiana birth record form has two adjacent elements:

- A labeled field: **"Print Name of Applicant"** — filled with typed/printed text
- A labeled box: **"Signature of Applicant"** — filled with a handwritten cursive signature

In the initial extraction run, `applicant_signature_block.printed_name` returned:

```
"O.G. Bennet"
```

The correct value is `"Olivia Grace Bennett"`. The API grabbed from the cursive signature
scrawl ("O.G.Bene...") instead of the printed name field directly above it.

## Why It Happened

The initial schema description was:

> "The printed name of the applicant."

This was not specific enough to distinguish between the two adjacent text elements in
the signature area. The model selected the most visually prominent text in the
signature block region.

## How Grounding Made It Catchable

Without bounding boxes, `"O.G. Bennet"` appears in the JSON output with no indication
of where it came from. Manual comparison of every field against every line of the
original document would be required to catch it.

With Nutrient's grounding, the highlight box landed on the cursive signature — not the
printed name line. The source of the error was visible in one second.

## The Fix

Updated the schema description to:

> "The name as printed or typed in the 'Print Name of Applicant' labeled field —
>  NOT from the handwritten cursive signature next to it."

## Before vs. After

| | Before | After |
|---|---|---|
| Description | "The printed name of the applicant." | "...from the 'Print Name of Applicant' field — NOT from the handwritten signature..." |
| Extracted value | "O.G. Bennet" ❌ | "Olivia Grace Bennett" ✓ |
| Grounding highlight | Lands on cursive signature | Lands on printed name field |

## Key Takeaway

The same pattern holds across all documents in this repo: grounding doesn't just improve
accuracy — it makes errors **immediately auditable** without manual document review.

## Future Enhancement

Consider adding an interactive before/after toggle to the HTML demo that switches
between the wrong and correct extraction results, showing both highlights side by side.
Flagged for a future version.
