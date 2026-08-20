# Lighthouse design source

The lighthouse pages adapt the visual system from a frozen Nutrient website
`homepage-vnext` snapshot while keeping the public sample self-contained.

## Frozen source

- Repository: `PSPDFKit/nutrient-website`
- Branch: `jdrhyne/homepage-vnext`
- Commit: `71f76eb62384241e2cf18d76fd31020b95a0a1f6`
- Commit date: `2026-06-30T10:38:20-04:00`
- Reference screenshot: `vnext-fullpage-desktop.png`

## Copied design language

- An editorial sans-serif system stack for display and body copy.
- A system monospace stack for uppercase supertitles, paths, counts, and request
  metadata.
- White primary canvas, warm-gray secondary surfaces, near-black text and
  feature bands, thin warm-gray separators, and restrained data-green status.
- Large calm type, 16–32 px rounded containers, compact black buttons, and
  layout density that alternates between generous narrative sections and
  structured evidence rows.

The pilot keeps its existing evidence contract and accessibility behavior. It
does not copy the homepage's uncited trust-gap statistics or product claims.

## Frozen assets

| Asset | SHA-256 |
|---|---|
| `common/assets/logotype/nutrient-logo.svg` | `c9102300d8cce70ed381f1775057fb72f5f874fafafde3efabdc82d8a0cbcb88` |

The deployable hub contains a byte-identical logo copy under
`docs/lighthouse/assets/`. It uses system font stacks and redistributes no
commercial font binaries.

## Authentic-form evidence refresh

The V4 hub keeps this frozen visual system while replacing the earlier
synthetic-fixture presentation with three selected one-page authentic public
forms populated with privacy-safe demo values. Each linked proof page is a
byte-identical copy of the corresponding current reviewed output under
`demos/*/output/index.html`.

The presentation reports the recorded envelope rather than converting it into
a broader product claim: 26/30 predeclared fields matched exactly, all 30
returned fields included valid page-bounded primary source regions, and four
mismatches remain visible. Mortgage and healthcare are marked `Review blocked`;
the insurance summary routes `11/11 exact → Continue`, while its technical
checker page reports `Pass`. This is a three-document demonstration, not an
accuracy, production, or performance benchmark. A recorded review is not
publication approval.
