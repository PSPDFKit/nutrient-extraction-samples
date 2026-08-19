# Lighthouse design source

The lighthouse pages copy the visual system from the local Nutrient website
`homepage-vnext` snapshot identified through agent-memory.

## Frozen source

- Repository: `/Users/admin/Projects/nutrient-website`
- Branch: `jdrhyne/homepage-vnext`
- Commit: `71f76eb62384241e2cf18d76fd31020b95a0a1f6`
- Commit date: `2026-06-30T10:38:20-04:00`
- Reference screenshot: `vnext-fullpage-desktop.png`

The local branch and its `origin/jdrhyne/homepage-vnext` tracking ref resolve to
the same commit. A fresh fetch was attempted on 2026-08-17 but DNS resolution
for `github.com` failed, so this document intentionally describes a local source
snapshot rather than claiming the branch is current on the remote.

## Copied design language

- ABC Monument Grotesk for display and body copy.
- ABC Monument Grotesk Semi-Mono for uppercase supertitles and compact labels.
- ABC Monument Grotesk Mono for paths, counts, and request metadata.
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
| `common/assets/fonts/ABCMonumentGroteskVariable.woff2` | `a290892b541674d3682e01f18277185ca8ee48caa011e45b901f55ccca7fe5ac` |
| `common/assets/fonts/ABCMonumentGroteskSemi-Mono-Regular.woff2` | `d2764ac72c40dc455279147d6a20b1fd1e3368bae32fae374a1507de706c2cfb` |
| `common/assets/fonts/ABCMonumentGroteskMono-Medium.woff2` | `99a97a4e9dbc8016ea9f0b11b0f1b499bdf70767cc6d576b8d2fd1b921aa8a73` |
| `common/assets/logotype/nutrient-logo.svg` | `c9102300d8cce70ed381f1775057fb72f5f874fafafde3efabdc82d8a0cbcb88` |

The deployable hub contains byte-identical copies under
`docs/lighthouse/assets/` so it has no dependency on the adjacent website
checkout.

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
insurance alone is marked `Pass`. This is a three-document demonstration, not
an accuracy, production, or performance benchmark. A recorded review is not
publication approval.
