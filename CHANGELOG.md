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

### Added

- **Program report bundle, built and not launched (2026-09-01).** The
  program tier the sustainability plan allows (gtfs-scorecard-plans/07:
  agency-facing stays free; only tools for the people who manage many
  agencies may carry a price) now exists as code, behind a gate that is
  closed. `scorecard bundle` renders one program's branded board reports for
  a cohort of up to 100 agencies as one archive with a manifest that names
  every id asked for and what happened to it; `report-bundle.yml` is the
  on-demand fulfilment; `infra/program-bundle` (written, not applied) is the
  post-checkout form, the capability download route, the Stripe webhook, and
  the weekly refresh, with plan-failing preconditions that keep
  `payments_enabled` at "0" until the Stripe configuration is complete;
  `/bundle/` and `/bundle/setup/` are unlinked, `noindex`, out of the
  sitemap, and read every price from `web/bundle/plan.json`, which says
  `paymentsAvailable: false`. ADR 0049 records the decision: a checkout is
  the "named user at the table" the plan required before building this
  tier. The runbook and the day-90 gate are in `docs/program-plan.md`.

- **14 French feed records from the rentrée recheck pass (2026-09-01).** The
  2026-08-30 exhaustion left 100 candidates excluded only for short
  calendars. Two days later, fourteen had refreshed past the 60-day gate and
  passed the same licence, identity, validator, and calendar path — SETRAM
  (Le Mans bus and tramway) and Linead (Dreux) among them, plus five Tarn
  networks from the Gaillac-Graulhet agglomeration. Saint-Sulpice-la-Pointe
  went from zero days of remaining service to 304 across those two days,
  which is the recheck queue doing its job. Dataset-slug matching joined the
  pool dedupe so tracked datasets whose portal resource URL rotated are
  excluded mechanically. Seventy-eight candidates remain queued on short
  calendars as September exports land; the registry moves to 2,275 records
  and the European sample to 618. The pass log is in `docs/feeds.md`.

- **76 reviewed French feed records from a second National Access Point
  exhaustion pass (2026-08-30).** Five weeks after the July exhaustion, the
  transport.data.gouv.fr API snapshot yielded 206 still-untracked datasets
  under Licence Ouverte 2.0 or ODbL. Every admission passed the same gates as
  the first pass: portal licence and named legal-owner attribution recorded as
  reuse evidence, identity review against the tracked registry, the pinned
  canonical MobilityData validator and complete scorecard path, and at least
  60 days of effective service. The pass adds records in twelve metropolitan
  regions plus Guadeloupe, Martinique, and La Réunion, 43 of them with
  official keyless GTFS-Realtime endpoints, and admits Naolib
  (Nantes Métropole tramway/bus/ferry) as the first French record on the
  bounded large-feed tier — its `stop_times.txt` expands past the standard
  512 MiB per-entry cap, and it completed a full local score under the raised
  limits (B, 83 days of service). The exclusion ledger (100 near-expiry
  candidates awaiting the September rentrée refresh, eight regional
  aggregates, seven alternate publications, six tracked datasets on rotated
  resource URLs, five unreachable producer hosts, two 9999-12-31 calendars
  that overflow the freshness date arithmetic, and the "Licence mobilités"
  holdouts including Île-de-France Mobilités and TCL Lyon) is recorded in
  `docs/feeds.md`. The European registry sample moves to 604 records; France
  is now about 56% of it, further above the European beta gate's 40%
  largest-country ceiling, which that gate continues to report honestly as
  unmet.

### Changed

- **The money page no longer links to a page that does not exist
  (2026-09-01).** `/support/`, `docs/support.md`, `SUPPORT.md`, and the
  README all pointed at `chelseakr.com/consulting/`, which returns 404; the
  consulting offer is withdrawn and every reference to it is gone. The
  featured "Professional help" card on `/support/` is now a free card for the
  board report the site already ships. The GitHub Sponsors tiers are now
  explained on the page and in the docs, each sized to a real cost line from
  the sustainability plan (the static core, the per-request edges, a month of
  on-demand scoring) with the caveat that the money is one pot and the caps
  hold regardless. A Sponsor badge joins the README header. The test that
  asserted the consulting link *present* on every public surface, which is
  how the dead link survived, is replaced by its inverse plus a check that
  every money page reaches the one payment rail that exists. A new
  `links.yml` workflow (lychee) checks the external links on those four
  files on every pull request and weekly, so the next dead link fails a
  build instead of waiting for a reader.

### Fixed

- **`scorecard lint` reported and never said whether it passed.**
  `docs/add-your-agency.md` sends a first-time contributor to
  `uv run scorecard lint --strict` and tells them a green result there means a
  green check on their pull request. There was no green result to see. The two
  advisory kinds, `non_https_url` and `missing_mdb_id`, stand at well over a
  thousand rows across the whole registry, so adding one correct entry printed
  a screenful of tab-separated lines about other people's agencies and then
  exited 0 in silence. The summary that would have explained it went to
  `log.info`, which the CLI does not display, so the only signal was an exit
  status nobody reads. Walked from a clean checkout: every malformed entry the
  document names does fail with exactly the one line it promises, so the failure
  path was already right and only the success path said nothing. The report is
  unchanged and still goes to stdout, one row per issue, so anything parsing it
  is unaffected; the verdict now goes to stderr, naming the counts by kind and
  either `PASSED --strict`, the blocking kinds when it failed, or that a run
  without `--strict` is advisory and not the gate. The walkthrough shows what a
  passing run looks like instead of implying it looks like nothing.

- **Nineteen published F grades have been withdrawn, and the site now says so.**
  The refusal that shipped on 2026-09-01 stopped the scorer minting a grade for
  an archive it could not read. It did nothing about the ones already published,
  and it made them permanent: a refused agency writes no artifact, so the daily
  run leaves the old letter exactly where it was and warns into a log. Nineteen
  named transit agencies stayed publicly graded F on feeds nobody had read, and
  twelve of the nineteen are in no registry at all, so no run would ever have
  looked at them again.

  The cause was established per feed rather than assumed. Eleven of the nineteen
  carry the validator's own `invalid_input_files_in_subfolder` notice in their
  published artifact: the archive wraps its GTFS tables in a folder and the
  reader looked at the top level. Several of those are healthy feeds.
  `santa-clarita-transit` was graded F on an archive holding 364 stops and 898
  trips; `miami-dade-transit-331` on one holding 6,973 stops and 24,285 trips.
  The other eight are archives that really do describe no service, confirmed by
  re-reading the same bytes where the feed is still reachable.

  `corrections.yaml` is the reviewed record: for each withdrawn grade, the
  agency, the snapshot and feed hash it was computed from, what was published,
  the period it was public, the verified cause, the evidence, and what stands in
  its place. Neither outcome is a number. A grade taken back because nothing was
  read is not corrected to a different reading of the same nothing; where the
  feed cannot be read the answer is that it is not measured, and where the
  record is no longer a current listing the scorecard is withdrawn and not
  replaced. A later run that does read the feed supersedes the withdrawal on its
  own and publishes its own measurement.

  Deleting the files would not have held. `publish.reindex` re-derives
  `latest.json` from the newest dated artifact beside it, so a retraction made by
  hand comes back on the next run. The withdrawal is enforced in the pipeline:
  reindex removes the current pointers, keeps the id out of the index, and folds
  it into the same S3 deletion plan retirement already uses, and `publish`
  refuses to write a current pointer for a record the file withdraws. Dated
  artifacts are untouched.

  A new `/corrections/` page carries the public record, linked from
  `/how-to-read/` and documented in `docs/listing-policy.md`. Three more
  published grades carry the same defect and are listed in the same file under
  `not_yet_corrected` with the reason each is held back, so the gate cannot be
  satisfied by narrowing what it looks at. One of them, `boxcar`, needs a
  scoring decision first: its archive has no stops, no routes and no trips, but
  its calendar has 89 real rows, so freshness is a genuine measurement and
  `score_feed_content` does not refuse the feed. The next run would publish an A.

- **A stops.txt with classic-Mac line endings read as a feed describing no
  service.** `gtfs._has_data_row` decides `FeedDates.has_service_content`, the
  flag that says whether an archive describes any service at all, and it read
  the table as raw bytes. Iterating bytes splits on `\n` only, so a table whose
  rows end in a bare carriage return is one long line: the header consumed the
  whole file, nothing was left to be a data row, and an archive carrying stops
  published `has_service_content: false`. It now decodes through a
  `TextIOWrapper` with `encoding="utf-8-sig"` and `newline=""`, the same
  decoding `_read_table` and `iter_table_rows` already use, so CR, LF and CRLF
  all split into rows and a UTF-8 BOM is stripped rather than counted as
  content. Reported and fixed by @ghzhost in #336; the regression test is the
  carriage-return case, with the BOM cases kept and labelled as passing either
  way.

- **Six more places where an absence was published as a number.** The same
  defect as the validator-report fix below, found in six other measurements the
  site publishes. In each one a value that means "we could not measure this"
  was written where a measured value goes, so a reader cannot tell the two
  apart. None of them invented a new vocabulary: every fix reuses the
  not-measured convention the project already has.

  - **A realtime fetch that failed inside our own fetcher was published as the
    agency's outage.** `rt.fetch_sample` caught every exception into
    `ok=False`, and that flag is not neutral: it becomes an ERROR finding on the
    agency's page, a deduction from their realtime score, and a "down" reading
    in the uptime record `/realtime/` publishes. Our SSRF guard refusing a URL,
    and any unexpected exception in our own code, were published under an
    agency's name as "your feed is down". `rt.measures_the_endpoint` now decides
    whose failure it was. A `requests` failure, `UnresolvableHostError` (which
    `net.py` already classifies as an origin availability failure) and a body
    that is not a parseable GTFS-Realtime protobuf remain the agency's outage.
    Everything else marks the sample not measured; the feed kind drops out of
    reachability and the rest renormalise, and a window with nothing measurable
    in it publishes no realtime category and records no uptime observation. A
    configured feed kind with no sample record at all keeps its deliberate
    fail-closed reading.

  - **A feed with no trips was failing the NTD shapes check rather than
    unmeasurable by it.** `assess_shapes_readiness` answered `not_ready` when
    `trips.txt` has no rows, while its own detail line beside it said the
    coverage could not be checked. The prose was right and the status was not: a
    stops-only feed sat in the failing bucket of `pct_ready` on every NTD rollup
    and wore a "Not ready" badge. `NOT_CHECKED` already existed for exactly
    this — with a rendered label, a badge class, and a deliberate absence from
    `_RANK`, where membership is what "we measured it" means — and is now used.

  - **A recommendation check that crashed read as a clean bill of health.**
    `recommend._safe` returned `[]` for a crash, which is the value a check
    returns when it ran and found nothing to suggest. An accessibility audit
    that died on a malformed table published the same page as a feed with no
    accessibility gaps at all. The sandbox stays — one broken table must not
    cost an agency its score — but `_safe` now returns `None`, the artifact
    carries `recommendations_not_measured` when a check could not run, and both
    renderers say so instead of falling silent.

  - **A liveness record that says nothing was counted as a healthy feed.**
    `refresh_success_record` read `int(record.get("consecutive_failures") or 0)`,
    so a record missing the field, or carrying null, or carrying anything that
    is not a count, read as a zero-failure record and joined the numerator of
    the public uptime figure on `/status/` and in `api/v1/status.json`. Only a
    non-negative int is a streak now; the rest are reported under a new
    `not_measured` field and leave the share's denominator, and the page names
    the denominator it used.

  - **A ridership impact with no weighted trips published a 0.0% expired
    share.** `expired_trips_pct` returned 0.0 on a zero denominator, one line
    above `weighted_average_score`, which returns `None` on the same
    denominator. 0.0% reads as the best possible answer — none of these trips
    ride on an expired feed — where the truth was that there were no trips to
    take a share of. Both are absent together now.

  - **An empty findings corpus reported 100% plain-language coverage.**
    `plain_language_coverage` returned 100.0 for a share with no denominator and
    called it vacuously fully covered. 100.0 is the number a fully curated
    corpus earns, and `scorecard coverage --save` writes this figure to
    `coverage-baseline.json` as the bar every later week is measured against, so
    the first real reading would land as a drop from a number nobody took. Both
    shares are `None` when there is nothing to divide by, `--save` refuses to
    overwrite a real baseline with an unmeasured one, and the regression check
    reports nothing when either side has no reading.

- **The release-tag ruleset locked everyone out, including the owner.**
  `.github/rulesets/tags.json` shipped with `"bypass_actors": []` while
  `.github/rulesets/main.json`, in the same directory, carried the repository-admin
  bypass. An empty list is not a stricter version of the rule; it is a different one.
  Applied, nobody can move or delete a tag matching `refs/tags/v*.*.*` — not the owner,
  not with an admin token, not from the web UI. That is live rather than theoretical here:
  `v1.4.0` matches the pattern and points at a 2026-07-25 commit `main` has since left
  hundreds of commits behind, so a mistagged release has no remedy short of burning the
  version number or opening a support ticket. The floating `v1` tag is unaffected either
  way — the glob needs two literal dots and never matched it. `tags.json` now carries the
  same admin bypass `main.json` has, ADR 0033 records the correction, and
  `pipeline/tests/test_ruleset_bypass.py` fails the build if either file loses its bypass
  or if the two stop agreeing. **The committed file is not the live ruleset:** applying it
  is `gh api repos/ChelseaKR/gtfs-scorecard/rulesets/{id} -X PUT`, an owner action, the
  same as for `main.json`'s required-checks list.

- **The scoring path no longer loads `stop_times.txt` into memory, which is
  what killed the OVapi Netherlands shard for three weeks.** The
  `score (ovapi-netherlands)` job had been dying with "The runner has received
  a shutdown signal" since 2026-08-07, after the validator had already
  succeeded and the JVM had already exited. With no JVM on the box, memory
  climbed from about 2 GB to 15.9 GB in roughly 45 seconds, swap filled,
  available memory reached 88 MB, and the runner was killed. Disk was flat at
  86 GB free the whole time.

  The trigger was the whole-table reader's per-table cap, and specifically the
  side of it the feed landed on. `MAX_MEMBER_BYTES` is 1 GiB: above it a table
  is skipped, below it the table is read into `list[dict[str, str]]`. OVapi's
  `stop_times.txt` is 1,011,976,627 bytes — 62 MB **under** the cap — and
  17,099,889 rows. Measured on the live archive, a row of that table costs 754
  bytes as a Python dict, so reading it whole comes to about 12.9 GB on a 15.6
  GiB runner. Every earlier export had been *over* the cap and was therefore
  skipped; the feed oscillates across the line, and the day it came in under,
  the shard died. A bigger feed was safer.

  So the fix is not a different number. Bytes on disk do not predict bytes in
  memory, the multiplier moves with row width, and any fixed byte cap is a
  cliff a feed can cross between exports. Lowering it would only skip more
  tables, which buys safety by measuring less. Both whole-table consumers of
  `stop_times.txt` on the daily scoring path now stream it instead, because
  what each one takes from the table is a bounded aggregate rather than the
  table: `routability` folds it into the trips with at least two serviced
  locations plus the served stop and location-group ids (855 thousand trips and
  57 thousand stops on OVapi, against 17 million rows), and `ferry_profile`
  folds it into the stop ids the ferry trips call at — and, being handed a lazy
  reader, returns without opening the table at all for a feed with no ferry
  route. `iter_table_rows` now accepts `max_member_bytes=None` for exactly this
  case: the cap is not lowered, it is inapplicable, because there is no whole
  table in memory for it to bound. Archive-shape safety — entry count,
  compression ratio, per-entry and whole-archive size — was always enforced in
  `fetch.py` before any reader opens the bytes, and remains the real zip-bomb
  guard and the ceiling on how much there can be to stream.

  `MAX_MEMBER_BYTES` itself is unchanged and still governs every table read
  whole, including these two modules' reads of `trips.txt` and `stops.txt`. If
  one of those trips it, routability still publishes `measured: false` with
  reason `table_too_large`; an unread table never reaches the artifact as a
  count of zero.

  Both checks now run to completion on the live OVapi archive in 68.6 seconds
  at a peak of 1.38 GB resident — against roughly 13 GB and a killed runner —
  and report what three weeks of shutdown signals could not: 854,910 trips, 35
  of them with fewer than two stops, 58,953 boardable stops, 1,981 of them
  served by no trip, and a ferry profile over 11,532 ferry trips.

  **This changes published output for four feeds, and no grade.** OVapi
  Netherlands, the Swiss national timetable, gtfs.de local transit and Carris
  Metropolitana have all been publishing `routability: {"measured": false,
  "reason": "table_too_large"}` and no `ferry_profile`. They will now publish
  real routability counts, and a ferry profile where the feed has ferry routes.
  Both blocks are zero-deduction, so no category score, overall score, grade,
  or conformance verdict moves for any feed. Output for feeds under the cap is
  byte-identical: verified by running the old and new readers over a
  300-feed synthetic corpus covering flex location groups, the GeoJSON
  `location_id` header typo, ferry and non-ferry routes, missing and
  header-only tables, and trips with zero, one and many stops.

  `gtfs.py` also logs any table of 64 MiB or more, with its uncompressed size
  and whether it was read whole, streamed, or skipped. The three-week diagnosis
  needed an instrumented re-run to learn which table was being read and how big
  it was; the next incident carries that evidence in its own log.

- **A validator report nobody could read is no longer scored as a clean feed.**
  The upward twin of the fabricated F above, and the one that lasted longer,
  because a flattering number invites no complaint. `ValidationReport` had one
  shape for "the validator found nothing wrong" and the same shape for "there
  was no report to read": an empty list of notices. Correctness starts at 100
  and deducts per notice, so the second case scored `Correctness 100.0 / 100`
  and published "The validator found no problems in this feed. That is rare and
  worth celebrating." about a feed whose report had never been read.

  Four payloads reached that sentence through `validate.parse_report_data` or
  `vcache._report_from_json`, the only two functions in the package that build a
  `ValidationReport`: an empty JSON object, a dict of an entirely different
  shape, a report truncated after its `summary`, and a report whose `notices`
  were null. Correctness was also the only scored category with no way to say
  "not measured" at all: freshness and rider experience return no category and
  are dropped, realtime is never appended for an agency that publishes none, and
  all three render as "Not yet measured" with no number.

  Both builders now refuse. A gtfs-validator report always carries `notices` as
  a list, empty when the feed is clean, so the list's presence is what separates
  the two cases; a payload without one raises `UnreadableValidatorReportError`,
  a `ValueError` that travels the path a non-zip response body already travels.
  A report with `"notices": []` is a real measurement of a genuinely clean feed
  and still scores 100.

  Where the same report can be obtained another way, the refusal is a miss
  rather than a stop. An unreadable validator-cache entry re-validates, because
  the honest cost of a cache entry we cannot read is one Java run. An unreadable
  hosted report from the Mobility Feed API falls back to a local validator run,
  which is what every other mismatch there already does. Only our own
  `report.json` has no second source, and that one raises: the agency is not
  re-scored that day and the run reports it, which is what "we could not read
  it" looks like from outside.

- **A feed with no stops and no trips is no longer given a letter grade.**
  Reported downstream against the published `gtfs-scorecard@v1.4.0` Action: a
  well-formed zip containing no GTFS files was scored `F (31.3/100)` with
  `Freshness 0.0` and `Rider experience 0.0` beside `Realtime -- not yet
  measured`, and `scorecard try` exited 0, so the Action reported
  `passed=true`.

  Two of those categories printed a floor for a measurement nobody made; the
  third, in the same table, printed the honest thing. A 0.0 says a real feed was
  read and found to leave riders with nothing, and no reader could tell it from
  an archive that had nothing to read. `freshness` now returns no category when
  the archive carries no table that can hold a service date, or describes no
  service at all, and `completeness` returns none when there are no stops and no
  trips.

  Withdrawing those two is necessary but not sufficient, and shipping it alone
  would have been worse than the bug. Correctness starts at 100 and deducts per
  distinct validator notice code, and an empty archive raises very few, so with
  the other two categories gone correctness alone becomes the whole overall and
  every such grade *rises*. Measured against the 2,515 committed artifacts: 22
  published scorecards score a feed with zero stops and zero trips, all 22 would
  have risen and 20 crossed a letter boundary -- `beloit-transit` F to B,
  `boxcar` C to A. Today's F is fabricated and that B is fabricated too.

  So the scorer now refuses. `score_feed_content` raises `UnreadableFeedError`
  when neither feed-content category could be measured, and no scorecard is
  built at all. This is the same refusal a response body that is not a zip
  already gets -- the error subclasses `ValueError` and travels the same path,
  so `scorecard try` reports `could not score <url>: ...` and exits 1 with no
  new handling, and the daily run records the feed as not scored rather than
  publishing a letter for it. One refusal, two causes.

  The rule is deliberately narrow, and both directions are pinned by tests. A
  feed that ships `calendar.txt` with no usable end date is still measured and
  still scores 0 with its finding; an empty-but-present `calendar.txt` is still
  a claim the feed made; and a feed with stops and trips but no calendar at all
  is still graded on its rider experience. Only the total absence of every
  stop and every trip is refused.

  The prose went the same way as the number. `boxcar` published "Service data
  covers the next 365 days" and "0% of stops state wheelchair accessibility"
  about an archive whose `stops.txt` and `trips.txt` hold a header row and
  nothing else (verified against the live feed, not inferred). Freshness read
  that 365 out of a `feed_info.txt` end date, which is a claim about data that
  is not in the archive; with no service to be the end of, the sentence and the
  100.0 were both about nothing, and both are now withheld.

  **The published Action still carries the old behaviour.** This fix is
  unreleased. `v1.4.0` and the floating `v1` both point at `d800e0b4`
  (2026-07-25), which predates the refusal, so a workflow on
  `uses: ChelseaKR/gtfs-scorecard@v1` -- the form the README and
  `docs/ci-action.md` recommend -- still scores a well-formed zip with no GTFS
  files as `F (31.3/100)` and still reports `passed=true`. `main` refuses it,
  and `pipeline/tests/test_action_v2.py` pins the composite action's outputs for
  a refused feed as well as the scorer's own refusal. Closing the gap for
  callers is a release, not a code change.

  **Not done here, and it needs an owner decision.** The 22 already-published
  scorecards still carry their old letters. The scorer can no longer refresh
  them -- each daily run now refuses and keeps the last artifact -- and it
  cannot rewrite them either, because publishing "could not be read" in place of
  a grade means `overall` without a `score` or `grade`, which 5 JSON schemas
  require and roughly 17 load-bearing call sites read unguarded. Three of those
  would actively misreport: `web/src/app.js` renders a missing grade as a large
  split-flap **F** (`String(grade || "F")`), `publish._history_entry` would
  abort the whole reindex, and `feeddiff` defaults a missing score to `0.0` and
  would publish a fabricated 73-point regression to Atom subscribers.
  Withdrawing the 22 instead -- removing the current pointers and keeping the
  dated evidence, the way a retired feed is handled today
  (`artifact_lifecycle.MUTABLE_PUBLIC_ARTIFACT_NAMES`) -- is a listing-policy
  call, not a scoring one. Until then the set is named and ratcheted by
  `test_no_new_scorecard_grades_a_feed_with_no_stops_and_no_trips`, which may
  only shrink.

- **The weekly discovery job no longer overwrites a curator's pinned feed
  host.** `city-of-wasco` is tracked on the Caltrans DDS ZIP; its
  `license_note` names that index and its `operating_note` records that the DDS
  packaging is "stale and noncanonical as packaged" and that we track it
  anyway. `scorecard discover --apply` proposed the calitp.org listing the
  catalog holds for the same `mdb_id`, and had no way to see that a person had
  already compared the two. PR #312 was closed on 2026-08-29 for exactly this,
  with `docs/PR-TRIAGE.md` recording that it "reverts a deliberate curatorial
  decision, and in the same diff deletes the paragraph that recorded why".
  Closing the pull request did not change the job, so the next scheduled run
  opened #327 with the same edit, it merged, and `main`'s CI went red on
  2026-09-01 with `test_repo_registry_tracks_calitp_hosting_migration` as the
  only surviving trace of the decision. The URL is restored, and `discover` now
  holds any replacement whose agency notes name the host already tracked
  instead of applying it. Held is not dropped: the report gives them their own
  section, with the note that pinned each one and the URL that was not applied,
  and counts them separately from the replacements it did apply, so the report
  never implies an edit it did not make.

### Changed

- **The structural SEO gate now measures title and description length, and the
  heading outline.** `check_site_seo.py` has been merge-blocking in `a11y.yml`
  and `pages.yml` since it landed, and it checked that a title, a description
  and a canonical were present, unique and self-referencing. It never checked
  how long they were, so 27 generated titles and 9 descriptions were running
  past the length a search result shows without anything noticing: the worst
  title was 91 characters on `/ntd/shapes/`, the worst description 192 on
  `/guide/disappeared-from-trip-planners/`. Nearly all the long titles were
  `/fix/<code>/` pages, where a 17-character site suffix was appended to a
  notice name that was already a full sentence.

  `site-seo.json` now carries `title_length` and `description_length`, and
  `site_shell.fit_seo_title` drops the site suffix instead of the page's own
  name when a title would overrun the bound, so the notice a practitioner is
  scanning for stays legible. Three fix headings and the `/ntd/shapes/` title
  were still too long with the suffix gone and were shortened at the source.
  Eight descriptions were trimmed; every published claim in them was kept and
  none was added, including the scoping words on `/adoption/`, `/data/` and
  `/status/`. `html.heading_level_skipped` reports an outline that jumps a
  level. Headings inside a hidden subtree stay out of it, matching axe.

  The agency-page `Dataset` omission found alongside these was checked and is
  correct: the 173 agency paths without JSON-LD are all retained redirect
  stubs, which should not advertise a dataset they only point at.

- **The plain-language gate now reads every finding the scorecard publishes.**
  `make verify` has run `scripts/check_readability.py` since FIX-08 landed on
  2026-07-02, and it measured `notices.TRANSLATIONS` only. That is one of two
  families of finding copy. The other is written inline at each `Finding(...)`
  site in the scorers themselves, reaches the same paragraph of the same agency
  page, and had never been measured: 40 construction sites, 118 strings, 23 of
  which missed the bars the gate already enforced. The two worst were the
  seasonal-boundary sentence shipped the same week (a 32-word sentence at Flesch
  36.9) and the step-free-route finding a wheelchair user's agency reads.
  `scorecard_pipeline.reader_copy` now enumerates both families, reading the
  `Finding(...)` sites from source rather than from a fixture run, and refuses a
  site whose copy it cannot account for instead of skipping it. Deferred fields
  are printed with their reason. No threshold moved: every breaching string was
  rewritten (ADR 0048).
- **A render failure now says which feed it happened to.** A TypeError in
  `_accessibility_score` took down four pipeline runs over roughly 20 hours, and
  every traceback named the function, the line and the type without naming the
  agency whose artifact was being rendered (#308). `render_site` logs nothing per
  agency, so the diagnosis had to be reasoned backwards from `completeness.py`.
  The per-feed body of the render loop now runs inside a context manager that
  re-raises with the slug attached, so the failure notification carries it. The
  exception is not swallowed: a feed that cannot be rendered still fails the run,
  and whether one bad artifact should abort the whole site render stays a
  separate product call, deliberately not made here.
- **Two controls that read as enforcement can now fail.** The complexity
  register in `docs/lint-complexity-ratchet.md` was maintained by hand and
  drifted twice in seven days (#309); it is now compared with ruff on every run,
  and a failure prints the regenerated table. Its first run found the file's own
  prose still calling `render_site` complexity 54 against a table corrected to
  55 the same day. And the published weight-sensitivity study graded the raw
  weighted average, outside the `publish._validate_published_overall` guard that
  exists to stop exactly that (#310): for a feed renormalizing to 79.96875, which
  publishes as 80.0/B, both perturbations were counted the wrong way round. Every
  letter outside `score.py` now comes from `published_score(...)`, and a
  structural check keeps it that way (ADR 0050).
- **The corpus average now says it excludes the feeds that publish realtime.**
  The cohort rule picks the largest homogeneous measured-category set, which is
  the one without realtime, so 145 of 1,783 comparable feeds sat outside the
  `/pulse/` average, `api/v1/trend.json` and the change lists, and zero of the 24
  agencies linked from `/pulse/` on 2026-08-06 had measured realtime (#248). The
  rule is right; the disclosure was missing, and it pointed against this
  project's reader: an agency that adds a realtime feed disappears from the
  headline number on the day they do it. `/pulse/` and `comparison-policy.md` now
  state it, derived from the comparison block rather than hardcoded, and say a
  feed leaves the average by publishing realtime rather than by getting worse.
  Re-basing the aggregates stays an owner decision on the methodology path
  (ADR 0051).
- **`/ntd/` publishes the reporter denominator, not only the feed one.** The
  page answered "45.0% of 1,125 tracked feeds", over this project's registry,
  and could not answer the question an FTA reviewer asks first: how many
  obligated reporters have nothing discoverable at all (#278). The inverted join
  and its RY2024 snapshot had existed since 2026-08-15, and
  `data/ntd/PROVENANCE.md` recorded that nothing read them. They are now
  published, in reporter units, stating that 1,253 reporters and 1,125 feed
  records are different denominators that are never added, and giving the
  no-discoverable-feed range at both ends (473 to 641) rather than averaging a
  name-based join. A reporter with no discoverable feed is shown as a limit of
  what open catalogues can see, never as a zero and never as a finding about
  that agency. The section publishes nothing at all if the snapshot does not
  declare its unit, if its tiers do not sum to its own denominator, or if it
  cannot say which report year it is from and when it was retrieved -- the fine
  print dates the denominator, and an undated one rendered "Report Year ,
  retrieved " beside counts that were real (ADR 0052).

- **An alert about a seasonal feed now says what its scorecard page says.**
  `metrics.freshness` has read a feed's own calendars since EXP-04 landed on
  2026-07-02: when a feed encodes distinct service periods and its expiry falls
  on one of those boundaries, the page calls it a planned transition and asks
  the agency to publish the next period. The alert stack never read that
  signal. So on the morning after a university system's term ended, its page
  said "confirm your next service period is published" and the email sent the
  same morning said "the schedule stopped covering service 12 day(s) ago. Trip
  planners may have already dropped this agency." The weekly cohort digest told
  a liaison the same feed "expired this week".

  A new `service_periods` module answers that question once for every alert
  surface, from what the published artifact already states, and `alerts` and
  `portfolio_digest` both read it. The daily digest, the subscriber email, the
  webhook payload, and the weekly cohort digest now describe a planned boundary
  as one, name a registry-declared seasonal or on-demand service in its own
  words, and ask for the next period's calendar instead of a longer one.

  Wording is all that changes. The lead-time tier, the sort order, the
  `days_until_expiry`, the alert kind, the scorecard link, and whether an
  agency or a liaison is told anything at all are identical either way, and the
  item still says riders cannot plan a trip until the next period is published.
  Four limits keep the softer sentence from becoming a hiding place: after a
  calendar closes it requires the finding the scoring path already published;
  before it closes it uses only the artifact's own `service_type` and
  `seasonal_boundary` values; a feed lapsed a year or more is never softened
  (the `STALE_FEED_DAYS` floor, applied first); and a feed with no readable end
  date never is either. Anything unreadable falls through to the existing lapse
  wording. See [ADR 0047](docs/decisions/0047-seasonal-boundary-alert-wording.md);
  this closes the "RR:R3 alert-tier wiring remains open" note EXP-04 left behind.

  No score, grade, category, weight, threshold, or public page moved.

## [1.5.0] - 2026-08-18

### Added

- **The repository now says how to support the project.** A root `SUPPORT.md`
  populates GitHub's community-health Support surface and separates getting
  help with a feed from funding the project; the homepage footer gains the
  `/support/` link it alone lacked (it carries its own footer rather than the
  shared one); and the README points at both near the top instead of from
  line 278 of about 390. The live GitHub Sponsors rail is wired through
  `.github/FUNDING.yml`, which now states the rule that a channel is listed
  only once the account behind it actually exists. The consulting offer
  hidden on 2026-07-14 is restored on `/support/`, the README, and
  `docs/support.md` — the link target was verified live before restoring —
  and the guard test now asserts the offer is present in all three rather
  than absent, because a paid offer that quietly disappears from every entry
  point is the failure worth guarding against now. Support copy no longer
  implies agencies embed the badges or submit receipts. Paid help sits
  alongside the free tool, never replaces it, and never changes a grade.
- **Continuous realtime health for the California cohort.** Realtime is a
  compliance area in the California Transit Data Guidelines, and the state's
  monthly reports check realtime presence at most twice a month; the monitor
  here already samples reachability, header freshness, and trip coverage on
  a schedule, but almost no Californian record outside the pilots had a
  realtime endpoint configured, so there was nothing for it to sample.
  Endpoints are taken from each agency's own monthly report and attached
  only to registry records whose organization match the crosswalk confirms,
  and every candidate had to answer with a parseable GTFS-Realtime message
  before being configured. Of 362 listed endpoints, 179 verified across 63
  agencies; the 183 excluded are recorded per endpoint with their reason in
  `data/california-realtime-sources.yaml` — 90 behind a Bay Area 511 API
  key, 71 behind a Swiftly key, and 22 that did not answer with a readable
  message. The program page renders the rollup least reliable first, reusing
  the national reliability bands rather than inventing a second model. A
  feed publishing no header timestamp is described that way instead of being
  scored stale, and nothing here changes a grade.
- **Findings now carry what they cost, not only what is wrong.** A pure
  consequence layer computes reach, rider-trips (National Transit Database,
  US-scoped per ADR 0026), and served-area need (North America, ADRs 0015
  and 0027) for published findings. Denominators are derived from each
  producer's arithmetic and checked against the published corpus —
  `orphan_stops` must divide by boardable stops, not all stops — and a
  finding with no honest denominator says so with the reason instead of
  printing a share. Reach is never multiplied into rider-trips, because
  boardings are not spread evenly across stops and the product would read as
  a measurement while being an invention. Across 3,547 published top fixes
  nothing came back unmapped, and a test fails if a new finding arrives
  without a reviewed basis. Nothing reads the layer yet: no artifact field
  changes and `SCHEMA_VERSION` is untouched.
- **`/focus/` groups the checks a validator does not run** — the four-week
  Maps availability bar, whether sampled trips complete, whether the
  realtime feed answers, and whether the feed URL still resolves — and
  `/how-to-read/` and the homepage workflow step now point at that group,
  which previously existed as one phrase inside the routability lede.
  Presentation only: no rule, weight, score, or grade moves.
- **The fresh site must pass a blocking structural quality gate before it
  deploys**: local links and fragments, duplicate IDs, metadata, canonical
  aliases, sitemap and robots parity, required structured-data identity and
  dates, and representative-page performance budgets. The same pass repaired
  what the gate and a production crawl then surfaced — glossary fragment
  links, fragments in redirect canonicals, overlong location metadata,
  curated agency identity, published article dates, and bounded rendering
  for the largest directory pages.
- **`check_doc_stats.py` now also reads the documents backwards**, so a corpus
  figure nobody registered cannot enter a live-facing doc unnoticed. The rule
  list only ever checked claims someone remembered to register, which is
  precisely why CLAUDE.md's 1,286 survived the registry doubling while every
  registered claim stayed correct. The sweep finds corpus-shaped figures across
  66 live-facing documents and fails on any that no rule covers and no
  `POINT_IN_TIME` declaration excuses; each declaration states its reason and
  must still match, so an exemption cannot outlive the figure it excuses.
  Deliberately not a completeness claim: it matches "<number> <corpus noun>",
  so a figure separated from its noun by an unexpected word slips through, and
  it is a net under the registration discipline rather than a replacement for
  it. Dated records (`CHANGELOG.md`, the `docs/` subdirectories) are not swept,
  and `*.local.md` private notes are never read.
- Gate `AGENTS.md`'s corpus figures. The file is excluded from the repo, so a
  normal rule naming it would fail every clean CI checkout, which is exactly why
  it went ungated and carried the same stale 1,286 CLAUDE.md did. `OPTIONAL_RULES`
  enforces it when the file is present and skips it when it is not, so a local
  `make verify` catches drift at the moment someone edits it.
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

- **The California cohort is reconciled against the Caltrans report
  directory.** The program page counted feed records, and a feed record is
  not an agency, so one operator with two feed URLs could be listed as two
  expired agencies. Every California registry record is now crosswalked
  against a committed, dated snapshot of the state's monthly GTFS quality
  report directory, strongest evidence first; a case the evidence does not
  settle is recorded as uncertain and never counted as agreement. Of the 133
  feed records the page carries, 112 match an agency in that directory, 3
  are uncertain, and 18 have no counterpart there, mostly park, campus, and
  private shuttles; they describe 108 distinct organizations, and 29
  agencies in the state's directory have no feed record here yet. Five exact
  duplicates retire as aliases, and remaining repeats group under
  `organization_id` with labeled variants. Nothing is deleted.
- **Re-materialize the committed artifact fallback snapshot from the live S3
  corpus (2026-08-07), moving the doc-stats denominator instead of weakening the
  gate.** The previous entry made `check_doc_stats.py` name its frozen snapshot
  honestly; this one refreshes the snapshot itself, using the same bounded flow
  the Pages build runs (`aws s3 sync` of the documented public set, then
  `scripts/materialize_current_artifacts.py` to validate index/latest parity).
  `data/artifacts/index.json` now carries the corpus the service actually
  publishes — 2,182 pages with 2,182 numeric latest scores, newest scoring date
  2026-08-07, schema 1.17 — against the cutover snapshot's 1,128 pages frozen at
  2026-07-10. With the denominator refreshed, the unchanged `floor` gate itself
  forced every "more than 1,100" claim up to "more than 2,100" (README,
  CLAUDE.md, `docs/roadmap.md`, `docs/product-roadmap.md`,
  `docs/feature-roadmap.md`) and the landing page's static "1,100+" published
  count up to "2,100+". The snapshot still only moves when it is deliberately
  re-materialized — automation stopped committing generated data at the S3
  cutover and still does not — so the gate's output keeps printing the
  snapshot's own date beside the counts.
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
- Move the `feeds/` reproducibility archive to S3 Glacier Instant Retrieval
  after 30 days. Retrieval stays millisecond-class, so
  `scorecard reproduce <agency> <date>` is unchanged, at roughly a sixth of
  the storage price; the recent tail stays in Standard, where a fresh grade
  is most likely to be questioned.
- Run the intraday refresh every three hours instead of hourly, stop
  re-downloading the artifact corpus every build, and publish only artifacts
  whose content actually changed.
- Stop shipping the whole registry inside `/compare/`. The page
  interpolated one option per catalog record into both selects — 399,514
  bytes raw at 2,176 records, growing with every coverage wave — and had
  fallen below the Lighthouse performance floor. It now ships a bounded
  window and fetches `compare/agencies.json`, the shape `/map/` already
  uses, only when someone reaches for the picker.

### Fixed

- **Nine agencies were published with a letter grade that contradicted their own
  printed score.** The overall score is published rounded to one decimal, but
  the letter and the band margins were computed from the unrounded value behind
  it, so a raw 79.96875 printed as `80.0` and was graded **C** against a
  published rubric that says 80 is a B. Bus Eireann, Express Bus IE, Slieve
  Bloom Coach Tours, Cape Ann Transportation Authority and Sandy Area Metro read
  `Grade C - 80.0 / 100`; Regional Transportation Commission read D at 70.0; and
  Reseau Stan (Nancy), Ukmerge and Vilnius District read **F** at 60.0 - each
  with a `margin_to_next_band` of `0.0`. A consumer joining the published
  `scoring.json` bands to a published artifact got a different letter than the
  artifact carried. The grade, the margins, and the score now all come from
  `published_score()`, the one place the published number is produced. The grade
  bands are unchanged, so this is a defect fix rather than a rubric change; the
  nine move up to the letter their published score already earned.
  A sweep of all 36,121 committed JSON files then found the same contradiction
  on 111 published letters across the rewritable current surfaces, not nine:
  `index.json`'s trend points (82), `directory.json` (8), five rollups (14), and
  `web/catalog.json`, `web/dataset.json`, `web/api/v1/agencies.json` and
  `web/api/v1/features.json` (3 each). All are corrected in place. The letter is
  now re-derived on the way out to every current surface, the way the
  conformance credential already was, so a `latest.json` rebuilt from a dated
  snapshot written before the fix still shows the right letter. The 82
  contradicting letters inside `<agency>/<date>.json` are left alone: `docs/api.md`
  promises dated artifacts are immutable once written.
  `validate_artifact` now refuses to write an `overall` block that contradicts
  its own score, and two new gates check the committed corpus, because
  `artifact.schema.json` can require the grade to be one of A-F but cannot
  require it to be the right one — the existing conformance test walked all nine
  wrong artifacts and passed.
- **325 embeddable badges disagreed with the artifact beside them.** `badge.json`
  and `badge.svg` are pure functions of `latest.json`, written next to it, and
  nothing compared the two. 268 showed a score `latest.json` no longer carried
  and 20 showed a different letter: Anchorage People Mover's artifact read
  `C 73.5` next to a badge reading `D 65.8`. All regenerated from the artifacts
  through the pipeline's own badge writer, and now gated.
- **Three checks the site's positioning depends on were measuring the wrong
  thing.** The Maps availability gate read `last_service_date`, the calendar
  tail, while every other surface uses `effective_expiry_date`; the two
  disagree on 136 published feeds, and one scorecard published
  `days_until_expiry: -1135` beside a passing gate. 48 of 2,515 feeds change
  verdict. Realtime drift anchored stop times to local midnight instead of
  the GTFS service day (noon minus twelve hours), so on the two
  daylight-saving transition days a punctual bus read 3,600 seconds off and
  every realtime agency in a transition zone could receive a false
  implausible-predictions finding. And the anomaly detector compared
  adjacent history rows as if they were adjacent days — 1,114 published
  steps span 27 days — so a month-long regression could be labeled a
  one-day glitch and both the dip and its recovery suppressed; neighbouring
  rows must now be within two days. No grade moves in any of the three: the
  gate is advisory, drift is not a score component, and no published
  history contained a gap-spanning dip.
- **A screen reader is told which page it is on, not which section.** The
  primary nav put `aria-current="page"` on a section's hub link from every
  page inside that section, so a screen-reader user on `/ntd/` heard
  "Coverage, current page" about a link that navigates elsewhere — wrong on
  17 of 26 top-level pages and on every agency page. `page` is now emitted
  only for the page being rendered and `true` for the containing hub, per
  ARIA 1.2's distinction between the two.
- **Published dates come from UTC, not from whichever machine runs the
  job.** A sweep found every remaining bare `date.today()` — nineteen of
  them deciding something that outlives the process, including snapshot
  dates, the as-of date expiry alerts are graded against, and dates stamped
  into committed files — and routed them through `config.utc_today()`, the
  aware clock the rest of the pipeline already read. The publisher-snapshot
  script's `retrieved_on` stamp follows the same rule.
- Repair the apex `gtfsscorecard.com` redirect and serve
  `www.gtfsscorecard.com` from its own redirect bucket, so both spellings
  reach `gtfsscorecard.org` again.
- **A StatCan outage could unpublish every Canadian need tier under a green
  run.** Each per-agency failure in `scorecard canada-equity` is a `continue`
  and the command then returned 0 and wrote whatever it had, so a total outage
  wrote `{"agencies": {}}` and the monthly workflow committed and pushed it. The
  command now refuses to write an overlay that has no tiers at all, or that
  drops an agency the current overlay already publishes and the registry still
  tracks - the same rule `equity.yml` already states for the ACS path - with
  `--allow-empty` as the deliberate override.
- **`web/llms.txt` described the project as US-only and quoted a stale count.**
  It said it scores "2,083 US transit agencies" while 1,030 of the committed
  artifacts are non-US across 45 declared countries. It now reads as a gated
  floor against the same denominator the README uses, and it is swept by
  `check_doc_stats.py`, which had missed it because it is neither Markdown nor a
  nav page.
- **The AAA contrast gate measured its own copy of the palette.**
  `check_contrast.py` never read `web/src/styles.css`, and axe's `color-contrast`
  rule is disabled on the grounds that this gate owns contrast, so a token could
  be darkened below AAA with every gate green. A new test ties the gate's
  `THEMES` table to the shipped CSS in all three themes.
- **Fix requests named the company hosting a feed rather than the one that built
  it.** Producing-tool detection read the host out of the feed URL, so a feed
  served from a vendor's delivery host was credited to that vendor. Every
  `rapid.nationalrtap.org` feed URL is a file-upload path, and
  `data.trilliumtransit.com` carries feeds whose own `feed_info.txt` names GMV
  Syncromatics or Optibus as publisher. Attribution now reads each feed's own
  publisher declaration, kept in `data/feed-publishers.json`, and falls back to
  the host only where the URL is a tool's own generated export. Where the
  producer cannot be established the copy stays generic instead of naming
  anyone. 70 of 2,515 published scorecards change tool: 57 stop naming a vendor
  the evidence does not support and 13 gain one the host could not see. Vendor
  regression cohorts follow the same evidence, so a host's cohort no longer
  mixes feeds it built with feeds it only serves. No score, grade, or metric
  reads this. See [ADR 0045](docs/decisions/0046-producer-attribution-from-the-feed.md).
- **Conformance guidance called every non-awarded feed “close,” including feeds
  meeting none of the three requirements (#246).** Summaries now state progress
  from the actual 0/1/2/3 criteria met. The machine-readable credential carries
  an independent version, publication always re-derives it from scored facts,
  and reindex migrates mutable `latest.json`/`conformance.json` views without
  rewriting dated historical evidence, so unchanged or unreachable feeds do
  not preserve the old wording indefinitely.
- **Retiring a feed alias removed it from the catalog but left its mutable
  artifact URLs live.** Reindex skipped noncanonical directories without
  removing `latest.json`, badges, conformance credentials, or route geometry;
  the additive S3 publisher then preserved those objects, and an explicit
  historical rescore could refresh them. Retirement now keeps only
  date-shaped score evidence, removes every current-looking file locally, and
  emits an id-only deletion manifest that all three production publishers
  apply. The S3 cleanup expands only the fixed public filename allowlist, rejects
  canonical ids and conflicting local files, and cannot delete dated history.
  Targeted activation also rejects retired ids before scoring.
- **Scorecard provenance copy inferred agency ownership from a successful
  configured-URL fetch (#245).** The registry already records `is_official` as
  true, false, or unknown, but artifact publication dropped it and both page
  renderers said "the agency's own URL" or "the feed this agency publishes"
  based only on `fetch.source == "origin"`. Schema 1.18 now carries the
  conservative `feed.source_provenance` classification (`official`, `archive`,
  `third_party`, or `unverified`). TransitFeeds is recognized as an archive;
  every other unknown remains unverified. Confidence notes, the static agency
  page, and the interactive view compose that evidence with the separate
  origin/mirror/local retrieval record and never claim agency ownership when
  the registry has not established it. Board and printable-report scope copy
  now refers to the feed scored here, not data the agency publishes. Legacy
  artifacts also render with unverified wording until the published corpus is
  regenerated.
- **The published rollup schema never learned the country identity fields the
  pipeline has emitted since the country program pages shipped (#121).**
  `rollups.py`'s `_rollup_identity` adds `country_code` and `country_name` to
  every country rollup, but `web/schemas/rollup.schema.json` still closed the
  `rollup` block over `id` and `name` alone — so every published
  `rollups/country-*.json` violated its own advertised contract.
  `test_every_published_rollup_conforms` could not catch it because the
  committed artifact snapshot predated country rollups entirely; the first
  re-materialized snapshot (below) put one in front of the test and it failed
  immediately. The schema now declares both fields as optional, per its own
  "additive within a major schema_version" rule; the top level and the
  `rollup` block stay closed.
- **The gate that exists to stop corpus figures going stale was itself reading
  a frozen number.** `check_doc_stats.py` measures its `pages` and `scored`
  denominators from `data/artifacts/index.json`, and automation stopped writing
  that file at the S3 cutover (`docs/follow-ups.md`, "Stop committing generated
  data and pages"). What git carries is the fallback snapshot taken that day —
  1,128 pages, newest scoring date 2026-07-10 — while the deployed service kept
  growing. Every claim gated on those two denominators was therefore a claim
  about the snapshot, read by everyone as a claim about gtfsscorecard.org. On
  2026-08-06 the live `/api/v1/stats.json` reported 2,182 scored feed records
  against the snapshot's 1,128, so the README understated the service by
  roughly half, and `floor` mode's `quoted + FLOOR_BUCKET` ceiling would have
  *rejected* the true figure had anyone tried to write it. The mechanism is
  unchanged and still correct for what it can see: an offline `make verify`
  cannot read the live corpus. What changed is that it now says so. Both output
  branches print one shared line naming the snapshot and its date, the module
  docstring states the blind spot next to the CLAUDE.md failure that motivated
  the sweep, and the README no longer presents the snapshot count as the
  service's scale — it points at `/status/` for the live number, which is where
  the exact count has always actually lived. `registry`, `europe_records`, and
  `europe_countries` read the registry YAML and were never affected.
- **The README claimed an MCP registry entry the registry does not have.** The
  Versioning section listed "an MCP registry entry (`server.json`)" among the
  releases this repo produces, and the standards table repeated it. `server.json`
  is written and version-checked, but publishing it needs an interactive
  operator login that has not been run, and it still carries no `packages[]`
  entry (removed 2026-07-05 rather than leave a false `registryType: pypi`
  standing). A search of `registry.modelcontextprotocol.io` on 2026-08-06
  returns nothing for `gtfs-scorecard` or `io.github.chelseakr`, while
  `scorecard` returns 17 other servers — so the name does not resolve there.
  `docs/mcp.md` was already accurate about this; the README was not, and now
  says the manifest is written but unpublished and links to the install recipe
  that does work.
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
- **A published registry figure that would have gone stale, corrected before it
  did.** `docs/global-coverage-roadmap.md` said "The current registry contains
  2,185 feed records" in the present tense and the next paragraph multiplied
  that exact figure by 100 to reach 218,500. Both were accurate when written and
  neither was gated, so both would have decayed on the next curation wave — the
  identical shape of the CLAUDE.md 1,286 error. Both are now floors ("more than
  2,100", "more than 200,000"), which is all the surrounding order-of-magnitude
  argument needs, and the first is gated.
- Date the planning figures that are legitimately fixed in time rather than
  refreshing them, which would falsify the reasoning they support, or leaving
  them bare, which invites a reader to take them as current.
  `docs/global-expansion.md`'s "Current baseline" is now "Baseline as of
  2026-07-18" and says outright that it is frozen and where the generated counts
  live; its 2x/5x storage model names 2026-07-18 as the measurement date and
  labels 2,300 and 5,800 as projections, not counts.
  `docs/global-coverage-roadmap.md`'s phase-3 outcome now carries its date.
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

### Security

- **Both Lambda worker images now delete the AWS Runtime Interface Emulator.**
  `/usr/local/bin/aws-lambda-rie` is a local-testing shim the base image ships,
  it is the only Go binary in either image, and its vendored Go standard library
  carried eight fixable HIGH CVEs with no rebuilt base image available. Both
  images deploy only as `package_type = "Image"` Lambdas, where the managed
  runtime never invokes it. The delete is gated on the base entrypoint still
  testing `AWS_LAMBDA_RUNTIME_API`, so a base image that changes that fails the
  build rather than shipping an image with no entrypoint. `docker run` of these
  images no longer emulates the Lambda API locally.
- **CVE-2026-54399 and CVE-2026-54428** (Apache HttpComponents Core, inside the
  shaded MobilityData gtfs-validator 8.0.1 jar) are recorded in `vex.json` as
  `code_not_reachable` on measured grounds: in the built image the validator
  loads no `org.apache.hc.*` class when given a local zip, and 140 of them when
  given `-u`. The pipeline only ever gives it a local zip, and
  `test_validator_is_never_handed_a_url` fails if that changes. `CVE-2026-39822`
  drops out with the binary it was about.
- **The container CVE scan now runs on every change that alters an image** -
  the handlers, the schema, and all of `pipeline/`, not just the Dockerfiles and
  the lockfile the images never read.
- **`web/src/` is scanned again.** ~6,600 lines of hand-written browser
  JavaScript, including 24 `innerHTML` assignment sites, were excluded from
  Semgrep (`.semgrepignore`) and gitleaks (`.gitleaks.toml`) and never analysed
  by CodeQL, which covers python and actions only — so the only code in this
  repository that runs in a rider's browser had no SAST and no secret scanning
  from any of the three. Both exclusions existed for the public GTFS feed-URL
  keys that appear in *generated* pages under `web/`, and both now name the
  generated trees instead of the whole directory. Measured first: with `^web/`
  removed, gitleaks reports 77 findings and every one is a feed-URL key under
  `web/agency/`, `web/api/` or `web/catalog.json`, none in `web/src/`. Semgrep
  now also runs `p/javascript`, since `p/python` over browser code was running
  almost no rules on it. Adding `javascript` to CodeQL remains open (#288).
- **Five pull-request checks could not block a merge**, contrary to ADR 0033's
  rule that a new gate joins the ruleset "in the same change that adds the
  workflow": both `Trivy image CVE scan` matrix jobs, `terraform fmt + validate`,
  `zizmor (workflow security lint)` and `Dependency review (PRs only)`.
  `container-scan` caught ten HIGH CVEs in the shipped Lambda images this month
  because it happened to run, not because anything required it to pass. All five
  are added to `.github/rulesets/main.json`, and a new test compares the
  workflows to the ruleset so a job can no longer run while blocking nothing.
  **The live ruleset is the enforcement source and still needs
  `gh api .../rulesets/{id} -X PUT`; this change only updates the file.**

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

[Unreleased]: https://github.com/ChelseaKR/gtfs-scorecard/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/ChelseaKR/gtfs-scorecard/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ChelseaKR/gtfs-scorecard/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.3.0
[1.2.1]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.2.1
[1.2.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.2.0
[1.1.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.1.0
[1.0.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.0.0
