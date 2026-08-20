# Data Extraction lighthouse pilot measurement brief

## Status and boundary

This is the measurement contract for the three-package Data Extraction developer-marketing pilot:

- banking: `mortgage_verification`,
- insurance: `insurance_claim_intake`, and
- healthcare: `prior_authorization`.

It measures a Layer 1 developer/PLG awareness and activation program. A conversation about source-grounded human review is a future-facing Layer 2 signal, not evidence that a complete Govern product is demonstrated, generally available, or shipped.

This brief is **non-authorizing**. It does not authorize tracking changes, analytics configuration, account creation, credit grants, API calls, deployment, publication, community posting, or any other production change. It only defines what must be measured if and when the relevant owners approve a launch.

## Questions the pilot must answer

1. Which vertical story moves an eligible developer from evidence inspection to a first authenticated Extract request?
2. Which story produces a second request within seven days, rather than a one-off trial?
3. Where does each vertical lose people: sample inspection, destination CTA, key creation, or first request?
4. Which story prompts qualified conversations about future governed-review workflows without treating those conversations as product proof?

Reach, impressions, video views, stars, and raw traffic are diagnostic context. They do not decide the winning vertical.

## Link taxonomy

### Required parameters

Every campaign-controlled outbound link must use these lowercase, enumerated fields:

| Field | Contract | Example |
|---|---|---|
| `utm_campaign` | Fixed for the entire pilot: `de_lighthouse_pilot_v1` | `de_lighthouse_pilot_v1` |
| `utm_source` | The channel or surface containing the link | `x` |
| `utm_medium` | The channel class | `organic_social` |
| `utm_content` | `<vertical>.<asset>.<variant>.<cta>` | `mortgage_verification.social_video.v01.github` |

`utm_content` carries four required tokens:

| Token | Allowed values |
|---|---|
| `vertical` | `mortgage_verification`, `insurance_claim_intake`, `prior_authorization`, `cross_vertical` |
| `asset` | `social_video`, `technical_walkthrough`, `github_sample`, `proof_page`, `owned_hub`, `product_page`, `workflow_template` |
| `variant` | `v01`, `v02`, `v03`, incremented only when creative or CTA changes materially |
| `cta` | `github`, `proof`, `studio`, `docs`, `signup` |

No free-form values are allowed. Campaign parameters must never contain a person's name, email, company, document name, account ID, request ID, medical information, financial information, claim information, or any other personal or customer data.

### Channel values

These values describe candidate distribution surfaces; listing them does not authorize using them.

| Surface | `utm_source` | `utm_medium` |
|---|---|---|
| X post | `x` | `organic_social` |
| LinkedIn post | `linkedin` | `organic_social` |
| Show HN post | `hacker_news` | `community` |
| r/dataengineering post | `reddit_dataengineering` | `community` |
| Vertical README or repository link | `github` | `repository` |
| Nutrient proof page or pilot hub | `nutrient_owned` | `owned` |
| Nutrient Data Extraction product page | `nutrient_owned` | `owned` |
| n8n template or workflow listing | `n8n` | `workflow_template` |

Use the source of the link being clicked, not the user's presumed original source. Preserve the session's original campaign touch separately. For example, a proof-page-to-Studio link uses `utm_source=nutrient_owned`; the page session retains the X or GitHub acquisition touch that brought the visitor there.

### Examples

```text
# X video -> banking GitHub sample
?utm_campaign=de_lighthouse_pilot_v1&utm_source=x&utm_medium=organic_social&utm_content=mortgage_verification.social_video.v01.github

# Banking README -> banking proof page
?utm_campaign=de_lighthouse_pilot_v1&utm_source=github&utm_medium=repository&utm_content=mortgage_verification.github_sample.v01.proof

# Insurance proof page -> Studio
?utm_campaign=de_lighthouse_pilot_v1&utm_source=nutrient_owned&utm_medium=owned&utm_content=insurance_claim_intake.proof_page.v01.studio

# Mortgage product-page module -> reviewed proof
?utm_campaign=de_lighthouse_pilot_v1&utm_source=nutrient_owned&utm_medium=owned&utm_content=mortgage_verification.product_page.v01.proof

# Healthcare technical walkthrough -> docs
?utm_campaign=de_lighthouse_pilot_v1&utm_source=linkedin&utm_medium=organic_social&utm_content=prior_authorization.technical_walkthrough.v01.docs
```

Before launch, an owner must create a link ledger with one row per public link and these columns:

```text
link_id, destination_url, utm_campaign, utm_source, utm_medium,
vertical, asset, variant, cta, planned_surface, owner, approval_status
```

The destination URL must resolve to the exact GitHub sample, proof page, Studio entry, documentation page, or signup flow. Do not substitute the homepage. The ledger is the reconciliation source for valid campaign values; this document neither creates redirect links nor configures tracking.

## Time windows and baseline

Let `T0` be the UTC timestamp when the first approved public pilot asset is published.

- **Baseline:** the 21 complete UTC days in `[T0 - 21 days, T0)`.
- **Observation:** the 21 days in `[T0, T0 + 21 days)`.
- **Seven-day maturity addendum:** events through `T0 + 28 days` are used only to complete the seven-day repeat outcome for organizations whose first request occurred late in the observation window.

The day-21 report includes the seven-day repeat rate only for first requests at or before `T0 + 14 days`; later first requests are labelled `pending`, not failures. The day-28 addendum reports the fully matured 21-day first-request cohort.

### What must be collected before `T0`

No baseline value is assumed. Before publication, the measurement owner must record:

1. Daily eligible sessions and destination-CTA clicks for the exact current Studio, docs, signup, and Data Extraction landing surfaces.
2. Daily new API-key organizations, first authenticated Extract requests, and seven-day second-request outcomes for new-key cohorts.
3. Existing bot, employee, agency, synthetic-monitoring, and test-account exclusion rules.
4. Current consent coverage and the proportion of web sessions that remain unattributed.
5. GitHub repository unique visitors and unique cloners captured daily; GitHub's available retention window must not be assumed to preserve the full pilot.
6. Existing qualified Data Extraction conversations and their qualification rubric, if one is already in use.
7. Exact source-system names, query owners, and query or dashboard version identifiers.

If a source cannot produce a historical field, report the baseline as `not available`; do not reconstruct vertical, identity, or intent from names, email domains, or document content.

## Event and metric definitions

### Eligibility and exclusions

An **eligible session** is a consented, bot-filtered first-party web session that views a pilot proof page or hub and is not identified as Nutrient staff, an agency working on the pilot, synthetic monitoring, a test account, or an approval-gated evidence run. Sessions without analytics consent remain in source-system operational totals where policy permits, but they are reported as unattributed and are not fingerprinted or estimated back into the campaign funnel.

An **attributed organization** is an external organization whose consented first-party campaign touch can be joined, inside the approved restricted data environment, to its signup or developer account. Primary attribution is the most recent valid pilot touch in the seven days before the conversion. Preserve the earliest valid pilot touch as an assisted-touch field. If no compliant join exists, count the event in the operational total and mark it `unattributed`.

For all activation metrics, deduplicate at organization level. Event totals may be shown separately for troubleshooting, but one active developer generating many requests must not outweigh several organizations activating once.

### Exact funnel definitions

| Event or metric | Exact definition | Primary source of truth | Owner placeholder |
|---|---|---|---|
| `pilot_asset_view` | One eligible first-party session viewing a pilot proof page, hub, or reviewed-examples product-page module. Deduplicate to one view per session, vertical, and asset. A product-page module view requires an existing consented section-view signal; a page load alone must not be relabelled as module exposure. | Existing consented first-party web analytics | `[Owner: Web Analytics]` |
| Native asset reach | Platform-reported impressions, video views, and outbound clicks for the exact post. Report by platform definition; never merge unlike platform definitions. | Native X, LinkedIn, HN, Reddit, or n8n reporting | `[Owner: Developer Marketing]` |
| GitHub repository traffic | Daily repository unique visitors and unique cloners from GitHub Traffic. This is repository-level context, not vertical attribution. Stars and forks are context only. | GitHub Traffic | `[Owner: Developer Relations]` |
| GitHub vertical engagement | An eligible first-party session arriving from a tagged CTA in a vertical README or sample. Deduplicate by session and destination. This is the attributable GitHub signal because repository traffic does not establish path-level vertical intent. | First-party web analytics plus the link ledger | `[Owner: Web Analytics]` |
| `destination_cta_click` | One click from an eligible asset session to `github`, `proof`, `studio`, `docs`, or `signup`. Deduplicate repeated clicks to the same destination within a session. | Existing first-party web analytics or native outbound-click reporting | `[Owner: Web Analytics]` |
| `destination_cta_ctr` | Distinct eligible sessions with at least one specified CTA click divided by eligible sessions that viewed the source asset. Compute separately by vertical, asset, channel, and CTA. | Derived from eligible views and clicks | `[Owner: Growth Analytics]` |
| `api_key_created` | The first API key created during the observation window for an external organization that had no API key before the event. Key rotations and additional keys do not count. | Developer-account or key-management system | `[Owner: Developer Platform]` |
| `first_authenticated_extract_request` | The earliest request from an eligible external organization to the Extract endpoint for which authentication succeeded. Downstream extraction success is not required; record completion status separately so setup and product failures remain visible. Exclude staff, tests, live-evidence runs, and rejected authentication. | API gateway plus Extract request records | `[Owner: Data Extraction Engineering]` |
| `first_request_conversion` | Attributed organizations with a first authenticated Extract request divided by attributed organizations with `api_key_created`. Also report activated organizations per 100 eligible proof-page sessions as the cross-vertical primary rate. | Restricted join of account and API operational records | `[Owner: Growth Analytics]` |
| `second_extract_request_7d` | An eligible organization has a second distinct authenticated Extract request within 168 hours after its first. A repeated log line or transport retry with the same request ID is not distinct. | API gateway plus Extract request records | `[Owner: Data Extraction Engineering]` |
| `seven_day_repeat_rate` | Organizations with `second_extract_request_7d` divided by organizations whose first authenticated request has had the full 168-hour opportunity to mature. Pending organizations are excluded from both numerator and denominator. | Derived from API operational records | `[Owner: Growth Analytics]` |
| `qualified_governed_review_conversation` | One external organization, counted once, enters a two-way conversation during the observation window, is attributable to the pilot or explicitly self-reports it, describes a real document workflow, and states a need for at least one future-facing control such as source verification, human review, approval, exception handling, audit evidence, or access control. A qualified owner must record the qualifying need and next step. | CRM record plus manual qualification | `[Owner: RevOps / Product Marketing]` |

For `first_authenticated_extract_request`, report the first request's outcome as `completed`, `product_error`, or `client_error` using the source system's existing status contract. Authentication failures remain a separate setup diagnostic; they do not satisfy the event.

### Required rates and cuts

Every report must include raw numerator, denominator, rate, and unattributed count. Required cuts are vertical, channel, originating asset, CTA destination, and day. Do not publish a percentage when its denominator is hidden.

The decision metrics are, in order:

1. **Activation:** distinct organizations with a first authenticated Extract request per 100 eligible proof-page sessions.
2. **Depth:** seven-day repeat rate among matured first-request organizations.
3. **Future workflow fit:** distinct qualified governed-review conversations, with the stated need categorized but not presented as shipped-product adoption.

The diagnostic metrics are GitHub unique visitors/cloners, GitHub vertical engagement, destination CTA CTR, key creation, request outcome, native reach, and video completion. They explain a funnel break; they do not override activation and depth.

## Attribution and reconciliation

### Attribution rules

1. Validate every campaign link against the approved link ledger. Invalid or partially populated values become `unattributed`; analysts must not repair them by guessing.
2. Store the first valid pilot touch and the most recent valid pilot touch. Use seven-day last-pilot-touch for the primary funnel and first touch only as an assisted view.
3. A proof-page CTA click retains both the page session's acquisition touch and the CTA link's own `nutrient_owned` asset identity.
4. Use organization-level operational records for key creation and requests. Never place API keys, request IDs, document identifiers, or organization identifiers in browser analytics.
5. Keep GitHub aggregate traffic separate from vertical-attributed README return traffic. Do not allocate aggregate clones, stars, or views across verticals by assumption.
6. Count one qualified conversation per organization. A CRM thread and a meeting about the same workflow are one conversation outcome, not two.

### Reconciliation procedure

`[Owner: Growth Analytics]` must maintain a read-only reporting extract or workbook with these daily UTC stages:

1. Freeze the approved link-ledger version and list any links actually used.
2. Export raw and eligible asset sessions and CTA clicks, retaining bot, consent, staff, and test exclusions as separate counts.
3. Export operational key-creation and Extract-request cohorts. Backend source totals must reconcile exactly to staged totals before exclusions; any difference is an error, not sampling noise.
4. Join only through the approved restricted identity mapping. Split operational events into `attributed`, `unattributed`, `excluded_internal_or_test`, and `join_error`; never inflate web totals to compensate for consent or blocking.
5. Deduplicate conversations by organization and have `[Owner: RevOps / Product Marketing]` sign off on the qualification fields.
6. Compare each daily total with the prior export. Late-arriving or corrected events must carry an as-of timestamp and explanation.
7. Produce day-7, day-14, and day-21 snapshots, then the day-28 seven-day-maturity addendum. Each snapshot records source query/dashboard versions and the link-ledger version.

Any unresolved join error, unexplained operational-count mismatch, taxonomy parse failure, or changed exclusion rule must be disclosed beside the metric. It must not be silently converted to zero.

## Stop, continue, and iterate criteria

### Comparable-exposure rule

Compare verticals on equal first-party exposure, not raw traffic. Let `n` be the smallest eligible proof-page-session count among the three verticals. Compute the comparison rates on the first `n` eligible sessions for each vertical, ordered by UTC timestamp. If `n < 50` at day 21, the comparison is **underpowered**: do not name a winning or losing industry and do not stop a vertical because its post received less distribution.

The `50`-session value is a pilot decision floor, not a claimed historical baseline or a statistical-significance guarantee. Show interval estimates and absolute counts; treat close rates as a tie rather than manufacturing precision.

### Continue

Continue a vertical's current story into a second distribution cycle when all of the following are true:

1. its evidence and claim-quality gates remain valid,
2. it has at least one attributed first authenticated Extract request, and
3. it has at least one depth signal: a matured seven-day second request or a qualified governed-review conversation.

If more than one vertical qualifies, rank first by activation rate on equalized exposure, then by seven-day repeat rate. Qualified conversations break a remaining tie; impressions, stars, and raw views do not.

### Iterate

Iterate the asset, CTA, or onboarding step rather than the industry thesis when any of these patterns occurs:

- `n < 50`: distribution is insufficient; improve reach to the same proof artifact without declaring product-market evidence.
- destination CTA CTR is at or above the three-vertical pooled rate but key creation or first-request conversion is below it: inspect destination continuity, signup, key issuance, docs, and first-request setup.
- GitHub vertical engagement is present but proof-page CTA engagement is weak: revise the README-to-proof handoff or CTA, preserving the sample and evidence contract.
- first requests occur but no matured organization sends a second request and no qualified conversation appears: interview the activated cohort and revise the repeat-use path before increasing distribution.
- native reach is high but eligible proof-page sessions are low: revise the post's demonstration and link framing; do not count the reach as success.

Change one material variable per variant and increment `variant`; otherwise attribution cannot identify what improved.

### Stop or reposition

Stop the **current story/asset combination**, not the underlying industry, when equalized exposure has reached at least 50 eligible sessions and it has both:

1. zero attributed first authenticated Extract requests, and
2. zero qualified governed-review conversations.

Also stop immediately if the package loses its evidence chain, exposes sensitive data, makes an unsupported compliance or correctness claim, or implies that the future Layer 2 Govern experience is demonstrated or shipped. A stop for evidence integrity overrides favorable reach or click metrics.

At day 21, `[Decision owner: CEO / Growth lead]`, `[Owner: Developer Marketing]`, `[Owner: Growth Analytics]`, and `[Owner: Data Extraction Product]` record one outcome per vertical: `continue`, `iterate_distribution`, `iterate_activation`, `stop_current_story`, or `underpowered`. The record must include the exact numerator, denominator, baseline comparison, exclusions, and unresolved data-quality issues.

## Privacy and identity boundaries

- Follow the existing consent, retention, access-control, deletion, and regional policies; this brief does not override or extend them.
- Do not add cross-device fingerprinting, third-party enrichment, email-domain inference, document inspection, or deanonymization to recover attribution.
- Browser events contain only the enumerated campaign fields and non-sensitive asset interaction. They never contain API keys, request IDs, raw URLs with secrets, document contents, extracted values, schemas containing customer data, or personal identifiers.
- Account-to-request joining occurs only in the approved restricted data environment using existing internal identifiers. Reporting outside that environment is aggregated by organization and suppresses row-level identity.
- Synthetic fixture identities and approval-gated live-evidence accounts are excluded from commercial funnel results.
- CRM qualification records the workflow category, stated review need, attribution basis, owner, and next step. It does not copy confidential documents or sensitive conversation content into the campaign report.
- Unconsented or unjoinable activity remains explicitly unattributed. No modeled uplift or identity stitching may be used to make the pilot appear more successful.

## Pre-launch assignment checklist

The pilot is not measurement-ready until the responsible owners have filled and approved all of the following:

- `[Measurement owner: unassigned]`
- `[Developer Marketing owner: unassigned]`
- `[Web Analytics owner: unassigned]`
- `[Developer Platform / key-data owner: unassigned]`
- `[Data Extraction request-data owner: unassigned]`
- `[RevOps qualification owner: unassigned]`
- `[Privacy review owner: unassigned]`
- `[Decision owner: unassigned]`
- `[Existing analytics source and query/dashboard version: unassigned]`
- `[Key-management source and query version: unassigned]`
- `[API request source and query version: unassigned]`
- `[CRM source and qualification view: unassigned]`
- `[Baseline snapshot location and as-of timestamp: unassigned]`
- `[Approved link-ledger location and version: unassigned]`

Until those assignments, baselines, and approvals exist, this document remains a planning artifact only.
