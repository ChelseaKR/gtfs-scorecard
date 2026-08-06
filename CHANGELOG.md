# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); this project
uses [SemVer](https://semver.org/) (see `README.md`'s Versioning section for
the declared public surface).

> **Known gap, found while writing this file (2026-07-05):** the `v1.0.0`
> and `v1` tags point at a commit (`0d8778530c...`, "make the scorer ref
> track the action version for the Marketplace") that is **not an ancestor
> of `main`'s current history** — `git merge-base --is-ancestor v1.0.0 HEAD`
> returns false, and a tree diff between the tag and `HEAD` touches over
> 28,000 files. The branch was evidently rewritten (rebased or
> history-squashed) at some point after the tag was cut, orphaning it. This
> is a real REL-07/REL-08 problem beyond what the 2026-07-05 audit named
> (lightweight/unsigned tags) — the tag doesn't just lack a signature, it no
> longer corresponds to reachable history. Recommended fix, for a human to
> decide and execute (not done here — retagging is a real git operation
> this remediation pass does not perform): cut a new annotated, signed point
> release (e.g. `v1.0.1` or `v1.1.0`) against current `main` as part of
> landing the real release pipeline (remediation P1-10), and treat `v1.0.0`
> as a permanently historical marker rather than trying to move it.
>
> **Resolved 2026-07-11:** done as recommended. `v1.1.0` is an annotated,
> signed tag on current `main`; the floating `v1` tag was moved to it;
> `v1.0.0` stays as a historical marker.

## [Unreleased]

### Fixed
- **Three notice codes had a published fix guide and no plain-language entry**,
  so every scorecard showed the generic "flagged by the MobilityData validator"
  fallback for them while the wording sat finished in `docs/fixes/`:
  `missing_timepoint_value`, `fast_travel_between_far_stops`, and
  `invalid_currency_amount`. `missing_timepoint_value` alone is 58.4% of all
  finding instances in the national corpus, so the line agencies met most often
  was the one the translation table exists to replace. Adding a fix page and
  adding a translation were separate acts with nothing checking they agreed;
  `test_every_published_fix_page_has_a_curated_translation` is now that check,
  scoped to validator codes since `scorecard_*` findings carry their own
  wording. Instance-weighted plain-language coverage moves 36.2% to 94.6% as a
  result, on 57 to 60 of 118 codes curated — a jump that is real but
  concentrated, and `docs/ideation/02-large-scale-fixes.md` now states why that
  number must never be reported without naming the codes that moved it.
- **Correction to published behaviour: the subscribe form recorded a narrower
  consent than it appeared to offer.** `subscriptions.yaml` documents that
  omitting `kinds` means every kind, and the YAML path honours that. The form
  path inverted it: the subscribe Lambda held
  `ALERT_KINDS = ("expiry", "regression")`, and a payload that omitted `kinds`
  was stored as that explicit closed two-item list rather than as a
  "wants everything" marker. A form-created subscriber was therefore
  permanently opted out of `lapse_risk`, `export_change`, and `anomaly`, was
  never told, and could not have discovered it from the form, which only ever
  showed two checkboxes. The Lambda now accepts all five kinds and the form
  offers all five, checked by default, so consent is explicit rather than
  inferred. No subscriber was affected: the subscriptions table was empty and
  no address in `subscriptions.yaml` was verified when this was found, so this
  is a correction made before anyone relied on it, not a remediation.
  The two lists live in separate deployables and the Lambda cannot import the
  pipeline package, so nothing but a test stops them drifting again; one now
  imports both and compares them. A test that had pinned the old two-item
  default — asserting the bug — was corrected in the same change.
  *Requires a Lambda deploy; code correctness alone does not change live
  behaviour.*

### Added
- Deliver the structural export diff (EXP-18) through the alert channels, not
  just the agency page. A run whose export changed shape now produces an
  `export_change` item in the email digest (its own section, deliverable to
  webhooks), an `export_change` entry in the site-wide Atom feed, and one in
  that agency's own Atom feed. Subscribers can opt into or out of the kind by
  name in `subscriptions.yaml`. Site-wide entries are gated to the same
  comparison-eligible cohort as grade-change entries, so a duplicate feed
  identity cannot announce one change twice. `changes/latest.json` is
  unchanged and still carries grade and score moves only; `docs/api.md` states
  the difference.
- Move proposal-only `scorecard sync` intake to Mobility Database
  `feeds_v2.csv`, while keeping mirror recovery and replacement discovery on
  the legacy catalog. Normalize numeric Mobility Database identities across
  both forms, reject unsafe V2 schema drift, prefer HTTPS endpoint spellings,
  and leave ambiguous Realtime endpoints unattached with a review note.
- Add `scorecard sync --source-metadata-out` receipts that bind the exact
  source bytes, header, filters, registry identity inputs, rendered proposal
  bytes, and proposal-tool source tree. Proposal outputs cannot overwrite their
  catalog input or the curated registry, and an empty run clears stale output.
- Extend the sync receipt with a versioned candidate-disposition ledger that
  accounts for every recognized Mobility Database Schedule row without
  publishing raw endpoints or contact data. Proposal selection is
  deterministic, existing registry matches are named, and conflicting catalog
  ids fail closed.

### Changed

- Cap oversized per-agency route tables at 500 rows while preserving the total
  route count and linking the complete current JSON record. Normal agency pages
  remain unchanged; national aggregates no longer produce multi-megabyte HTML.
- Move the Alice Springs registry source to the Northern Territory publisher's
  current canonical download. The retired URL now takes six redirects across a
  renamed department and filenames, beyond the scorer's guarded redirect cap.
- Treat a vanished public publisher hostname as an availability failure eligible
  for an identity-pinned mirror. Private, malformed, and otherwise unsafe URLs
  still fail closed and can never route through fallback infrastructure.
- Resolve legacy numeric Mobility Database mirror records through the current
  `files.mobilitydatabase.org/mdb-N/latest.zip` endpoint. The retired GCS
  object path no longer blocks recovery when a publisher endpoint is offline.
  Track Danville Mass Transit's latest first-party document URL even though its
  host currently rejects unattended fetches.
- Recover the final missing coverage cohort with current first-party Schedule
  downloads for DCTA, Rockford Mass Transit, and SamTrans. Their retired,
  archived, or key-gated registry URLs now point to the agencies' public GTFS
  downloads; feeds whose publisher is still unavailable continue to use the
  explicitly disclosed Mobility Database mirror fallback.
- Retry lifecycle tagging after transient S3 connection failures in both daily
  and targeted publication. A single dropped response no longer leaves an
  otherwise successful daily corpus refresh red or triggers the watchdog.
- Keep reviewed national aggregates scoreable when `stop_times.txt` exceeds
  the 1 GiB whole-table reader cap. The graded scorecard now publishes while
  the zero-deduction routability block says it was not measured, instead of
  failing the entire feed. Nullable contact fields are also treated as missing
  data rather than a pipeline error. Mark the OVapi national aggregate for the
  reviewed large-feed tier and move Cache Valley, Greenlink, and Jacksonville
  to their current catalog-confirmed Schedule sources.
- Make the contributor-facing failures in `docs/add-your-agency.md` plain
  messages instead of Python tracebacks (#188). Walking that walkthrough from a
  clean fork, both cases the doc promises "fail immediately with a plain
  message" — a malformed registry entry and an unreachable feed URL — produced
  an uncaught twenty-frame traceback. The underlying messages were already
  precise; they were just buried. `main` now reports `AgencyConfigError`,
  `UnsafeURLError`, and `requests` failures as one line and exits 1, and a
  single-agency `scorecard run` logs the failure without a stack (a `--all`
  batch keeps the stack, because whoever is debugging 900 feeds wants it).
  `SCORECARD_TRACEBACK=1` restores the full traceback for either audience.
  The walkthrough now also names `scorecard lint --strict` — the registry gate
  CI actually runs on the pull request — as a fast, Java-free first check.
- Harden the newly published sync-receipt contract as schema 1.2. The 1.1
  schema stays frozen at its existing URL and both versions have stable,
  retrievable schema references. New receipts validate before either output
  is written. Registry provenance binds each external identity to the public
  registry record that currently carries it. Tool evidence also binds the
  packaged jurisdiction data and exact schema bytes. Scope, count, and decision
  contradictions are rejected, while Mobility Database-only receipt runs reuse
  one proposer evaluation.

### Fixed

- Gate the README's European cohort figures ("a 528-record reviewed European
  cohort across 26 countries") against the registry and the Europe beta gate's
  own country list. Both numbers were correct when checked, but they are the
  only public figures quoted exactly rather than as a floor, so they go stale
  on the next admitted European record. `check_doc_stats.py` gains an `exact`
  mode for them.
- Correct a stale registry figure in `CLAUDE.md`. Its status banner claimed
  1,286 curated feed records; the registry holds 2,185, so the published
  number understated the corpus by roughly half. The count is now stated as a
  floor ("more than 2,100") in line with the README, and `check_doc_stats.py`
  gates it. Every figure that already had a rule in that script stayed
  correct through the same period, which is why the missing rule, not the
  wrong number, is the actual defect being fixed.
- Stop citing a nonexistent rule as authority for where agent instructions
  live. `CLAUDE.md` attributed its "agent-facing instructions live here, not
  in the README" note to "DOCUMENTATION-STANDARD §9 [DOC-18]"; the pinned
  v1.0.1 standard has eight sections and no `DOC-18`, and its §2 and §7 place
  the agent entrypoint in the README. The arrangement is unchanged and still
  deliberate, but it is now declared as a divergence in
  `docs/standards-conformance-gaps.md` rather than presented as conformance.

## [1.4.0] - 2026-07-25

### Added
- Grow reviewed coverage by 123 records to 1,734 by deepening countries already
  in the registry. A sixth gtfs-data.jp pass adds 40 first-party Japanese
  operators across 15 prefectures under CC BY 4.0, CC0, and CC BY 2.1 JP, taking
  Japan to 225. A United States small and rural pass adds 14 feeds under a
  confirmable reuse basis: Caltrans DDS California agency feeds (CC BY 4.0) and
  National Park Service park shuttles and ferries (US Government works). A Canada
  and Australia pass adds 69, including BC Transit regional systems, Québec exo
  and RTC networks, Queensland qconnect towns, and Ontario operators such as the
  TTC and GO Transit. European counts are unchanged. Every record carries a live
  license check, a current-calendar preflight, and a closed reuse-evidence block;
  rejections are recorded in `docs/feeds.md`.
- Raise the archive-shape ceiling for opted-in large feeds. A few national and
  regional feeds unzip past the standard limits (a national `stop_times.txt` can
  reach 2.4 GiB), so the standard tier rejected them before the validator ran.
  These now carry `large_feed: true`, and the large-tier per-entry ceiling rises
  from 2 GiB to 3 GiB. Verkehrsverbund Rhein-Neckar now scores. The two larger
  aggregates, the gtfs.de Germany-wide feed and the Swiss national timetable,
  clear this guard but remain unscored because a separate per-table reader cap
  still applies (see below).
- Stop an oversized table from failing a whole feed's score. Scorecard's own
  reader caps a single table at 1 GiB, and the ungraded ferry profile reads
  `stop_times.txt` whole; on a national aggregate whose `stop_times.txt` runs to
  1.9 GiB or more, that raised an error and failed the entire feed. The ferry
  profile now skips a table it cannot read and reports no profile. This is a
  partial step: the same aggregates still hit the cap in another whole-table
  reader (routability), so gtfs.de and the Swiss national timetable stay
  unscored. Fully scoring national feeds of this size needs a streaming reader,
  tracked in `docs/follow-ups.md`. The European beta gate stands at 99.2% of its
  reviewed cohort measured for translation and portable location, not 100%.
- Grow reviewed coverage by 91 records to 1,609 and reach the European beta
  gate's 250 reviewed-feed-record threshold. Two more waves: a fifth gtfs-data.jp
  pass takes Japan from 145 to 185 records, and an eighth European wave adds 51
  non-UK-led records that lift the European cohort to 251 across 22 countries.
  France stays the largest single country at 27% and the United Kingdom fell to
  14%, both under the 40% concentration limit, so the cohort now meets the gate's
  count, country-spread, and concentration criteria. The European additions lean
  on France's Licence Ouverte networks and Norway's Entur operators under NLOD
  2.0; the Netherlands, Romania, and Belgium produced nothing that clears an
  explicit first-party open license, and those rejections are recorded in
  `docs/feeds.md`.
- Add local-zip support to `scorecard try`, so a maintainer can apply the
  conservative autofix to a copy and rescore original and corrected bytes
  without uploading either file. Local runs preserve the SHA-256 and state
  their provenance in the confidence notes.
- Preserve a machine-readable and narrative Davis–Yolo repair rehearsal with
  dated source hashes, before/after measurements, explicit unknowns, and the
  failed first attempt that exposed an autofix mismatch. Agency feed bytes are
  not redistributed because reuse terms are not stated.
- Make the conservative route-case autofix clear the validator finding it
  claims to address by recasing uppercase `route_desc` values as well as
  `route_long_name`. A local Yolobus before/after rehearsal exposed the prior
  mismatch: the first corrected copy changed names but left all 15
  `mixed_case_recommended_field` notices intact.
- Correct the Unitrans realtime record after its March 2026 move from UmoIQ to
  Swiftly. The registry and source notes no longer point maintainers at the
  retired provider; because Unitrans does not publicly document a Swiftly
  GTFS-Realtime endpoint or credential path, realtime remains explicitly
  unmeasured and does not affect the grade.
- Grow reviewed coverage by 95 records to 1,518 through a Japanese deepening and
  a seventh European wave. Two more passes over the national gtfs-data.jp
  repository take Japan from 65 to 145 records, going deeper into its 40
  prefectures with more first-party private bus and rail operators under CC BY
  4.0, CC0, and CC BY 2.1 JP. The seventh European wave adds 15 non-UK-led
  records and takes the European cohort from 185 to 200 across 22 countries:
  Norway joins with eleven county-authority Entur feeds under NLOD 2.0, Slovakia
  with Bratislava, and Latvia and Plzeň deepen countries already present. The
  United Kingdom share fell to 17% and France, the largest single country, to
  20.5%, both well under the 40% concentration limit. Every record carries a live
  license check, a current-calendar preflight, and a closed reuse-evidence block;
  rejections are documented in `docs/feeds.md`.
- Grow reviewed coverage by 64 records to 1,423 across three more parallel waves.
  A deeper Japanese pass over the national gtfs-data.jp repository adds 38
  first-party records and takes Japan from 27 to 65 across 40 prefectures, now
  admitting the CC BY 2.1 JP license alongside CC BY 4.0 and CC0 with the exact
  version stated in each record. A Transitland Atlas sweep of the regions the
  Mobility Database is thin in adds the first Malaysian coverage: six data.gov.my
  records under CC BY 4.0 for KTMB national rail and Prasarana's Rapid networks
  in Kuala Lumpur, Penang, and Kuantan. A sixth European wave adds 20 non-UK-led
  records and takes the European cohort to 185 across 20 countries as Bulgaria
  (Sofia) and Croatia (Zagreb) join and additions in France, Spain, Italy, and
  Germany open Occitanie and Saxony; no United Kingdom feed was added, so its
  share fell to 18% and France stays the largest single country at 22%, both
  under the 40% concentration limit the beta gate sets. Every record carries a
  live license check, a current-calendar preflight, and a closed reuse-evidence
  block; rejections are documented in `docs/feeds.md`.
- Translate the most common untranslated validator notices into plain-language
  fixes. Every notice was ranked by the number of scored feeds it affects, and
  the twelve most frequent untranslated codes now carry a curated explanation and
  a concrete fix rather than an auto-humanized label. The most common of them
  shows up in about half the scored feeds. Each new entry clears the same
  readability bars as the existing translations.
- Grow reviewed coverage by 35 records to 1,359 across three parallel waves.
  Eighteen official Japanese GTFS-JP feeds from the national gtfs-data.jp
  repository (one flagship municipal network across eighteen new prefectures,
  CC BY 4.0 or CC0), a fifth European wave of sixteen non-UK-led feeds that
  takes the European cohort to 165 records across eighteen countries with the
  United Kingdom at 20.6% (well under the 40% ceiling) — opening Bavaria,
  Slovenia, Emilia-Romagna, and a Portuguese CC0 record — and one genuinely-new
  California agency (SacRT's SCT/Link) after a fail-closed pass confirmed the
  other untracked US candidates were dead sources already carried via mirrors.
  Every record carries a live license check, a current-calendar preflight, and
  a closed reuse-evidence block; rejections are documented in `docs/feeds.md`.
- Disclose each region's own reviewed-cohort denominator in the finder. When a
  visitor filters the directory to a country or subdivision, a line beside the
  location controls states how many reviewed feed records the cohort holds there
  (for example "19 reviewed feed records in Italy"), read from the directory
  summary counts already present, so a region is never read against only the
  US-heavy global denominator. The count is stated as a cohort size, never as a
  census or a claim of complete coverage. Announced as a text status region, no
  color-only meaning, mobile-friendly.
- Let the world coverage map drill down into a country's subdivisions. Selecting
  a country with committed subdivision geometry swaps the world choropleth for
  its states, provinces, or prefectures, each shaded by expired-feed share, each announcing
  its counts in text and filtering the list on selection, with a Back control to
  the world. Subdivision geometry ships as committed per-country assets
  (`web/subdivisions/<cc>.json`) generated by `scripts/build_subdivision_maps.py`
  from public-domain Natural Earth admin-1 data, for the United Kingdom, France,
  Germany, Spain, Italy, Canada, Australia, New Zealand, Japan, Malaysia, and
  Brazil; a country without
  geometry, or a subdivision with none, degrades to the existing chip-and-list
  behavior. Fully keyboard-navigable and mobile-friendly, with no external map
  tiles.
- Wire in the Transitland Atlas as a second feed-discovery source alongside the
  Mobility Database: `scorecard sync --source transitland` (or `all`) reads the
  keyless, CC-BY Atlas DMFR registry and emits the same `CatalogFeed` shape, so
  a Transitland candidate flows through the same proposer, deduplication, and
  curator review as a Mobility Database feed. It is strongest exactly where the
  Mobility Database is thin. DMFR carries no ISO country, so a candidate's
  location is left blank for review rather than guessed; key-gated feeds are
  flagged and skipped as usual.
- Add a large-feed tier so official national and metropolitan feeds that exceed
  the standard ingestion caps can be scored. A record opts in with
  `large_feed: true`; the tier streams the download to disk with a bounded
  memory footprint (`net.safe_download`), raises the size ceilings to a bounded
  larger level (512 MiB download, 2 GiB single entry, 4 GiB total), and gives
  the validator an explicit heap ceiling (`SCORECARD_LARGE_FEED_HEAP`, default
  6g). The zip-bomb shape guards are unchanged. First feeds on the tier: Israel's
  national feed, Melbourne (PTV), HSL Helsinki, Wiener Linien, and Carris
  Metropolitana — the latter two were already tracked but failing the daily run
  as over-cap until now. Verified end to end on HSL, whose `stop_times.txt`
  expands to ~1 GiB.
- Add the first official coverage outside Europe, North America, and Oceania
  (global coverage roadmap Phases 2-3): nine reviewed first-party open-data feed
  records — Belo Horizonte's two networks and Rio de Janeiro (Brazil, CC BY),
  the Tokyo Toei bus and subway networks and Donan Bus (Japan, CC BY via ODPT
  and the Hokkaido platform), the İzmir metro and tram (Turkey, CC BY 4.0), and
  the OTP Namtang Bangkok feed (Thailand, CC BY 4.0). Israel's national feed is
  size-deferred to the large-feed shard; Santiago and Bogotá are deferred on
  rotating dated URLs; and every African candidate is held for the roadmap's
  partnership-gated phase because all catalog-listed African GTFS is
  community- or survey-produced.
- Publish a comprehensive multi-region global coverage roadmap
  (`docs/global-coverage-roadmap.md`) that sequences expansion by
  defensibility: official openly licensed feeds first, a partnership-gated
  phase for the Global South and informal transit that this project will not
  curate without a named local steward, and cross-cutting enablers (large-feed
  sharding, beta-gate generalization, alternative-catalog ingestion). Coverage
  remains explicitly not a success measure.
- Add the first Oceania coverage wave: eleven reviewed Australian and New
  Zealand government open-data feed records (six Queensland TransLink networks
  including Brisbane, Transperth in Perth, the Northern Territory's Darwin and
  Alice Springs networks, and Auckland Transport and Baybus in New Zealand).
  Sydney, Melbourne, Canberra, Tasmania, and Metlink Wellington are deferred
  with recorded reasons (size cap, registration wall, bot block, share-alike,
  or unstated license).
- Add a world coverage choropleth to the app overview: every country with
  tracked feed records is shaded by its expired-feed share using the same
  contrast-gated quintile tokens and text legend as the United States map,
  with each country announcing its counts in text and filtering the list like
  its chip. The geometry ships as a committed 119 KB asset generated by
  `scripts/build_world_map.py` (public-domain Natural Earth source); the map
  degrades silently to the chip grid when the asset is unavailable.
- Add two gate-progress charts to the status page's European beta section in
  the shared route-bar grammar: reviewed records as a share of the release
  threshold, and per-country cohort shares beside the concentration ceiling.
  Thresholds come from the published criteria payload, never a second copy.
- Add a third 75-record European depth wave from every remaining non-Swedish
  queue, reviewed in parallel: twenty in France, twelve each in Italy and
  Finland, eleven in the United Kingdom, nine in Spain, five in Ireland, four in
  Poland, one in Portugal, and Czechia's first two records. The reviewed
  cohort reaches 148 records in 17 countries alongside the parallel Nordic-Baltic and Central Europe waves, with the United Kingdom at 23%.
  Documented rejections include seventeen French ODbL datasets, size-capped
  archives in Austria, Portugal, and Finland, Belgium's source-gated
  operators, Estonia's broken register endpoint, and community rebuilds on
  third-party hosts refused on identity grounds.
- Add a second 21-record European depth wave: twelve more Great Britain
  Passenger-platform operators, five Baden-Württemberg network feeds from
  NVBW's portal, three French networks including the Yeu-Continent ferry and
  a combined realtime stream for Cap Cotentin, and Trenitalia's regional rail
  resource from Regione Toscana. The reviewed cohort reaches 63 records in 13
  countries with the United Kingdom at 36.5% of the cohort; new rejections
  (unstated licenses, uncovered hosts, an unreachable National Access Point
  listing, ODbL with unread special conditions) are documented alongside the
  first wave's.
- Add 27 source-, reuse-, and identity-reviewed European depth-wave records
  from the named review queues: ten Great Britain operators on the Passenger
  open-data platform, seven in Spain, four in Italy, four in Germany (a new
  registry country), and two in France, including two feeds with public
  realtime endpoints. The reviewed cohort now spans 42 feed records in 13
  countries with the United Kingdom the largest at 26%, still explicitly below the
  250-record beta gate; rejected candidates and their reasons are documented
  in `docs/global-expansion.md`.
- Externalize the interactive app's shell copy (loading, fetch errors, the
  error and not-found boxes, compare-picker validation) into a reviewed app
  string catalog rendered as a generated module, with a derived `en-XA`
  pseudolocale behind an explicit `?l10n=en-XA` preview, browser tests for
  expansion overflow, fail-closed English fallback, and right-to-left
  direction, and exact-baseline ratchets on hardcoded strings and directional
  CSS (ADR 0038). English remains the only production interface language and
  the language-steward gate is unchanged.
- Add nine source-, reuse-, and identity-reviewed European feed records across
  Belgium, Switzerland, Denmark, Estonia, Spain, Finland, the United Kingdom,
  Poland, and Portugal. The bounded cohort now spans 15 feed records in 12
  countries while remaining explicitly below the 250-record beta gate.

### Changed
- Record the large-feed tier decision in `docs/decisions/0039-large-feed-tier.md`:
  a per-record `large_feed` opt-in raises only the raw size ceilings to a bounded
  larger level and streams the download to disk, while every zip-bomb shape guard
  stays unchanged.
- Broaden the European canaries beyond a bus-first view with metro, tram,
  national multimodal, ferry, and GTFS-Flex demand-responsive service, while
  keeping multi-operator aggregates counted as one feed record.
- Bump the artifact schema through 1.17 with additive reader-archive,
  endpoint-specific realtime, and headsign-applicability evidence. The
  versioned reader archive profile is `raw-v1` or `flat-single-root-v1`; raw
  hashes, archived bytes, and canonical validator inputs remain exact, and
  flat-profile rows stay outside the default raw-profile comparison cohort.

### Fixed
- Do not recommend `trip_headsign` for a verifiable simple loop when its
  applicable linear trips are already labeled. The exemption requires one
  closed stop pattern, one shape, one direction, no repeated interior stops,
  and complete stop-time evidence. Ambiguous, malformed, or oversized cases
  keep the ordinary finding, and raw headsign coverage remains visible.
- Keep the daily 2,000-plus-feed scoring run inside AWS credential windows by
  defaulting to 32 shards and refreshing OIDC credentials immediately before
  lifecycle tagging. Manual runs can still override the shard count.
- Upgrade both Lambda images to the reviewed Amazon Linux
  `2023.12.20260720` repository snapshot, so fixed `glib2` and `libacl`
  packages replace the vulnerable base-image versions.
- On the first day of a new scoring contract, label the coverage snapshot as
  a baseline instead of claiming that no material changes were detected.
  Same-day rechecks now explain that they update the existing daily point.
- Restore keyboard focus to the country a user drilled from when they leave a
  subdivision map via Back. The focus-return guard tested `HTMLElement`, but SVG
  paths are `SVGElement`, so focus silently fell to the page body (a WCAG 2.4.3
  focus-order regression); the e2e test now asserts focus returns.
- Score Wiener Linien and HSL Helsinki, which the daily run had been rejecting
  as over the single-entry cap since they were added, by moving them to the new
  large-feed tier.
- Read an otherwise unambiguous GTFS export through a deterministic flat view
  when every file is under one root folder or a filename has surrounding
  whitespace. Ambiguous layouts and post-trim collisions remain hard errors.
- Treat stops assigned to a served GTFS-Flex location group as served in the
  router-free usability check. GeoJSON service zones count as trip locations
  without inventing links to unrelated ordinary stops.
- Replace two Cal-ITP-hosted California feed URLs that now redirect to an HTML
  page: Wasco now uses the listed DDS ZIP and Clean Air Express uses its current
  provider-hosted ZIP.

## [1.3.0] - 2026-07-16

### Added
- Publish an auditable European GTFS beta gate in the status page, feature
  finder, and versioned API. Structured provider-source, reuse-terms,
  attribution, review-date, and identity evidence now determines the bounded
  cohort; the initial six-record result is explicitly not ready.
- Add a five-record, source- and reuse-reviewed ferry cohort covering Magnetic
  Island, Brittany Ferries, Transmanche, Sardegna–Corsica, and Sardegna's minor
  islands. Each feed is official, current, and explicitly open for reuse.
- Add an ungraded ferry data profile for ferry-serving feeds. It reports the
  ferry subset's terminal hierarchy, `stop_access`, published accessibility,
  bicycle and car carriage, plus clearly labelled whole-feed fare and realtime
  facts in agency pages, artifacts, and the feature API.
- Publish an ungraded service-mode contract from GTFS `route_type` and trip
  counts. Mode membership and primary mode now flow through artifacts, the
  feature API, finder deep links, and CSV shortlists, including a direct Ferry
  filter and explicit unknown handling.
- Measure rider-facing `translations.txt` adoption, language tags, row counts,
  and translated tables without changing feed grades. Publish the measurements
  through the adoption rollup, feature API, interactive filters, and CSV export.

### Changed
- Make scorecard language follow the measured service mode. Ferry-only feeds
  use vessel and terminal language, mixed feeds use neutral vehicle language,
  and every measured feed identifies its ungraded service mode in the status
  board without changing any score.
- Recorded the public `v1.2.1` Marketplace listing and moved the 90-day roadmap
  from release preparation to participant recruitment.
- Put the consumer feature finder in primary navigation, disclose the current
  U.S.-heavy coverage denominator beside its filters, and document the reviewed
  European GTFS beta gate separately from full interface localization and NeTEx.

### Fixed
- Complete ferry-only terminology in generated rider summaries, accessibility
  sub-scores, conformance copy, and scorecard section navigation while keeping
  GTFS field and file names exact.
- Close the mobile primary menu after following a navigation link and rebalance
  the feature controls across desktop and narrow layouts.
- Make Mobility Database registry proposals fail closed around authenticated
  Schedule feeds and already-tracked feed identities. Strict registry lint now
  blocks duplicate canonical feed URLs and Mobility Database ids, and reviewed
  reuse evidence cannot be dated in the future.
- Repair exact Mobility Database identity pins for the Malaysia, New Zealand,
  France, and Ireland canaries so rediscovery cannot select a redirect alias or
  a prefixed non-catalog identifier.

## [1.2.1] - 2026-07-15

### Changed
- Pinned the Action's uv runtime and disabled its workspace cache. A consuming
  repository no longer receives empty-workspace or missing-cache-input warnings.

### Fixed
- Create parent directories before writing standalone HTML or comment output.
  The first clean downstream `v1.2.0` run exposed this when
  `html: output/scorecard.html` failed after scoring the feed successfully.

## [1.2.0] - 2026-07-15

Superseded by `v1.2.1`: the first clean downstream run found that nested HTML
output paths were not created before writing the report.

### Added
- Marketplace release metadata and a publication runbook for the composite GTFS
  quality gate, prepared for a protected `v1.2.0` tag and the floating `v1` tag.

### Changed
- Replaced parallel expansion queues with one proof-gated 90-day sequence:
  Marketplace release, participant recruitment, six concierge remediation
  requests, audited exact-feed closure receipts, and a pass-or-stop decision.
- Kept deterministic autofix as an explicit local command; scheduled scoring no
  longer generates, hosts, or advertises modified agency feed copies.
- Public coverage pages now focus on feeds that need attention and recent changes
  instead of ranking agencies from best to worst.
- Cross-feed comparisons exclude incompatible scoring profiles and duplicate feed
  records. Agency pages no longer present a national percentile as a performance
  judgment.
- Coverage totals now describe feed records or scorecards rather than implying each
  record is a distinct transit agency.
- Unitrans realtime copy now says its UmoIQ feeds require an API key and remain
  unmeasured here; it no longer says the agency publishes no realtime feed.
- Action documentation is prepared for the v1 line (`@v1` and the planned
  `@v1.2.0` release ref) instead of referencing a nonexistent v2 tag.

### Fixed
- Rubric-version copy no longer implies that every historical scorecard was computed
  with the current methodology.

### Security
- Moved validator results, structural fingerprints, and raw finding-clearance
  state behind private storage paths. Pages and CloudFront now publish from
  positive filename allowlists, and publishers retire legacy public cache,
  structure, fixlog, and corrected-feed objects.

## [1.1.0] - 2026-07-11

Cut from current `main` to re-anchor releases to reachable history:
`v1.0.0` was orphaned by a branch rewrite (see the note above) and stays as
a historical marker. The floating `v1` tag now points at this release. It
prepared the action for Marketplace submission, but the listing remained
unpublished; Marketplace publication is a v1.2.0 release step.

### Added
- Searchable, quality-gated fix library; canonical feed identity ledger;
  reviewed listing-claim/correction workflow; vendor evidence packets; fix
  outcome analytics; program campaign pages; and fair-comparison guardrails.
- GitHub Action gate controls, EXP-16 policy research materials, board-ready
  reports, and transparent project sponsorship documentation.
- Spanish-first `/es/` agency lookup backed by key-parity `en`/`es` locale
  catalogs, with explicit limits on what a scorecard certifies.
- Responsible-technology audit register and consequence, bias, privacy, and
  threat-model reviews; a release checklist; and a reproducible
  `make golden-refresh` command.
- CycloneDX SBOM/VEX release assets and build-provenance attestations.
- `scorecard report` (also `python -m scorecard_pipeline.report`): renders one
  agency's published scorecard as a single self-contained HTML file for a
  board packet or a grant application, printable to PDF, with an optional
  `--brand` YAML (name, logo, accent) so a state program or consultancy can
  put its name on reports for the agencies it supports. See
  `docs/board-report.md`.
- "Fixes shared across this group" section on `/program/<state>/` pages (#23).
- `docs/crosswalk.md` rendered as an on-site `/crosswalk/` page (#22).
- Fix-KB pages and validator rule links for the four highest-prevalence
  realtime gaps (#21).
- California Minimum GTFS Guidelines checklist on agency pages (#19).
- Neutral peer-distribution framing on per-state program pages (#17).
- "Expired over a year" findings split by whether the feed URL itself still
  answers (#16).
- Several more fix-KB gap closures for the most common validator findings
  (#15, #18).
- 2026-07-05 remediation pass (this change): restored the vendored
  `docs/standards/ACCESSIBILITY-STANDARD.md` to its pinned upstream state;
  added a `## Standards conformance` + `## Observability` + `## Versioning`
  section to `README.md`; reconciled `pipeline/pyproject.toml` /
  `CITATION.cff` / `server.json` to one version number with a `make verify`
  drift check; added dependency-audit (pip-audit + osv-scanner), CodeQL
  (python + actions), zizmor, TruffleHog, and OpenSSF Scorecard workflows;
  authored (not yet applied — see the workflow files) a branch-protection
  ruleset; this CHANGELOG and a wheel-build CI step.

### Fixed
- Container ingestion now rejects oversized or suspiciously compressed GTFS
  archives before Java starts. Both production images pass HIGH/CRITICAL Trivy
  scanning with reviewed, expiring VEX entries for unreachable upstream code.
- Standards pinning is self-contained and merge-blocking; Lighthouse now gates
  performance, LCP, CLS, and responsiveness as well as accessibility.
- Workflow shell lint is clean, generated pages are synchronized with the
  merged feature set, and Docker build context is reduced from roughly 400 MB
  to the source and pinned validator inputs actually needed.
- Badge embed's copied Markdown now names the agency and grade instead of
  the generic "GTFS data quality" (#24, and an earlier partial fix).
- `shapes_readiness` allowed in the artifact schema — was failing 100% of
  runs since the prior release that introduced it (#20).

## [1.0.0] - 2026-06-21

First tagged release (`v1`/`v1.0.0`). Summarized
rather than itemized commit-by-commit: the tag predates a history rewrite on
`main` (see the note above), so an exact commit list can't be reconstructed
from `git log` against current history. As of this tag, the repo shipped:

### Added
- The scoring pipeline (fetch → MobilityData validator → score → publish)
  covering Correctness, Freshness, Rider-experience completeness, and
  Realtime quality, with plain-language findings and "top 3 things to fix."
- The static frontend (agency picker, scorecard pages, trend charts) with a
  WCAG-AAA-targeted accessibility posture.
- The composite GitHub Action (`action.yml`) gating a caller's CI on feed
  grade/expiry, packaged for reuse as `ChelseaKR/gtfs-scorecard@v1`.
- NTD certification-readiness signals and the `agencies.yaml` scale-out path
  (grown to roughly 1,100 agencies nationally by 2026-07).
- Realtime drift/plausibility checks, embeddable grade badges, and rollup
  views across agency cohorts.

[Unreleased]: https://github.com/ChelseaKR/gtfs-scorecard/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/ChelseaKR/gtfs-scorecard/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.3.0
[1.2.1]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.2.1
[1.2.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.2.0
[1.1.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.1.0
[1.0.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.0.0
