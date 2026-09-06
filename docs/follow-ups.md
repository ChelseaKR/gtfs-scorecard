# Follow-ups

Deferred work with enough context to pick up later. Each item says why it is
not done yet and the concrete steps to finish it. Strategic framing for the two
big ones lives in `docs/roadmap.md`; this file is the operational checklist.

## S3 as the artifact source of truth (roadmap Year 1)

**Status: complete as of 2026-07-10.** The original
driver was the daily run losing refreshes to git push races. That is now
fixed in code — shards publish only the agencies they scored (no cross-shard
clobber), and a rejected push replays the generated files onto the latest
`main` instead of rebasing (which conflicted on binary artifacts like
`web/api/v1/agencies.parquet`). With reliability handled, moving artifacts
off git is now just cleanup (keeping the repo from growing by a few thousand
JSON files a day) and is not urgent.

The validator cache already supports this move: `vcache.py` has an S3 tier
(`VALIDATOR_CACHE_BUCKET` / `ARTIFACTS_BUCKET`) so the cache survives once
`data/artifacts` stops being committed.

Steps, in order:

1. **Pages read role — done.** `aws_iam_role.pages_read` in
   `infra/artifacts/github_oidc.tf` grants only `s3:GetObject` +
   `s3:ListBucket` on the artifacts bucket, trusted for both
   `repo:ChelseaKR/gtfs-scorecard:ref:refs/heads/main` and
   `repo:ChelseaKR/gtfs-scorecard:environment:github-pages`. Its output
   `pages_read_role_arn` was applied on 2026-07-10 and stored as the
   `PAGES_AWS_ROLE_ARN` Actions secret.
2. **Assemble from S3 in `pages.yml` — done.** A live Pages job successfully
   assumed the read-only role. Pages hydrates the compact index, current agency
   artifacts, and today/yesterday dated snapshots before rendering. It validates
   each index/latest pair and materializes a missing current dated record from
   those same bytes, so stale-but-current citations still resolve after bounded
   hydration or lifecycle retention. Complete trends live in `index.json`;
   older records and corrected ZIPs remain on the artifact CDN, keeping
   deployments bounded as the archive grows.
3. **Stop committing generated data and pages — done.** Daily and intraday jobs
   publish score artifacts to S3. Pages renders the public tree in CI. Git keeps
   the cutover snapshot as an outage/fork fallback. The intraday job publishes
   `liveness.json` to S3, so no scheduled automation writes generated data to
   `main`. `publish.rebuild_index()` preserves compact
   S3-only trend points that are absent from a clean checkout.
4. **Lifecycle policy — done.** `aws_s3_bucket_lifecycle_configuration.artifacts`
   in `infra/artifacts/main.tf` expires objects tagged `artifact-class=dated`
   after 400 days, plus a 30-day noncurrent-version expiration now that
   versioning is on. The collect job's "Tag today's dated artifacts" step
   (`scorecard.yml`) applies the tag to each day's `<agency>/<date>.json` as
   it's synced; `latest.json`, `badge.json`, `directory.json`, and the
   validator cache never match that filename pattern, so they're never tagged
   and never expire. The lifecycle configuration was applied on 2026-07-10.
   Artifact history synced to the bucket before this step
   existed stays untagged (and therefore un-expiring) until something
   re-touches it, which fails open rather than deleting unclassified history.

The web app's runtime source remains same-origin Pages. The committed artifacts
and prerendered pages are the final cutover snapshot; future generated changes
deploy from CI without growing git history. ADR 0030 records why the existing
history is not rewritten.

## Fan-out compute (`infra/compute`, roadmap Year 2)

**Status: deferred, and not a plain `terraform apply`.** At ~2,643 configured feeds the
GitHub Actions matrix handles the daily run in well under an hour, so this is
premature. More importantly, applying `infra/compute` stands up an EventBridge
schedule that would run the pipeline **in addition to** the Actions cron — two
schedulers, double runs, double cost — until the Actions schedule is removed. So
activating it is a migration, not an apply.

When the registry outgrows the Actions matrix, the cutover is:

1. Build the worker image from `pipeline/` and push it to ECR.
2. `terraform apply infra/compute` (EventBridge + SQS + container Lambda).
3. Wire the enqueue/worker path (`infra/compute/enqueue.py`, `worker.py`) and
   confirm a run end to end against the SQS queue.
4. **Remove the `schedule:` trigger from `.github/workflows/scorecard.yml`** so
   only one scheduler runs. Keep `workflow_dispatch` for manual runs.

See `docs/decisions/0003-fan-out-compute.md` for the original design.

## Streaming reader for national-scale feeds

**Status: done 2026-09-05 for the scoring path, after the deferral caused an
outage.** Both whole-table consumers of `stop_times.txt` in the daily scoring
path now stream it.

The deferral rested on an assumption that turned out to be backwards. The note
below used to say the cap kept a national feed safe by skipping its
`stop_times.txt`. It did — right up until a feed came in *under* it. The OVapi
Netherlands aggregate's `stop_times.txt` was 1,011,976,627 bytes, 62 MB under
the 1 GiB cap, and 17,099,889 rows. Measured on the live archive, those rows
cost 754 bytes each as `dict[str, str]`: about 12.9 GB on a 15.6 GiB runner.
The `score (ovapi-netherlands)` shard was killed with "The runner has received
a shutdown signal" for three weeks, after the validator had already succeeded
and the JVM had already exited. A bigger feed was safer, because a bigger feed
was skipped.

That is the property of a fixed byte cap, not a mistake in where it was set:
bytes on disk do not predict bytes in memory, the multiplier moves with row
width, and the feed oscillates across whatever line is drawn. Lowering the cap
buys safety by measuring less, which is the wrong trade for a tool whose product
is measurement.

What each consumer actually needed from the table was a bounded aggregate, not
the table:

- `routability` needs the trips that have at least two serviced locations, the
  stop ids some trip calls at, and the location group ids some trip calls at —
  three sets keyed by trip and stop. On OVapi that is 855 thousand trips and 57
  thousand stops, and it does not grow with the 17 million rows.
- `ferry_profile` needs the stop ids the *ferry* trips call at, and returns
  before reading a row at all when the feed has no ferry route.

Both now call `iter_table_rows` with `max_member_bytes=None`. The size check is
not lowered, it is inapplicable: there is no whole table in memory for it to
bound. Archive-shape safety (entry count, compression ratio, per-entry and
whole-archive size) was always enforced upstream in `fetch.py` before any reader
opens the bytes, and still is — that, not `MAX_MEMBER_BYTES`, is the zip-bomb
guard and the ceiling on how much there can be to stream.

`MAX_MEMBER_BYTES` is unchanged and still governs every table read whole,
including `routability`'s and `ferry_profile`'s reads of `trips.txt` and
`stops.txt`. When one of those trips it, routability still publishes
`measured: false` with reason `table_too_large` rather than a count of zero.

Remaining, and deliberately not done here:

1. **The realtime readers.** `rt._trip_time_spans` and `rt_drift._schedule_lookup`
   still read `stop_times.txt` whole. Neither is reachable for any large feed
   today — none of the 15 `large_feed: true` records publishes realtime — and
   `_schedule_lookup`'s index is one entry per stop time, so streaming alone
   would not bound it. Fix them when a large feed first publishes realtime.
2. **`scorecard otp`.** The manual routing-QA command reads the table whole to
   sample stop pairs. It is interactive and not on the daily path.

## Reduce `/compare/`, then tighten its Lighthouse aggregation

**Status: open, opened 2026-08-10.** [ADR 0045](decisions/0045-lighthouse-lcp-budget-and-warmup-run.md)
left `lighthouserc.routes.json` untouched rather than lowering its performance
floor to 0.75 to make a real regression pass. `/compare/` slowed measurably on 2026-08-07: median LCP
went from 3077 ms to 3454 ms and median performance from 0.895 to 0.850, between
runs 31139147660 and 31139709133. About a fifth of `/compare/` runs now land near
4053 ms, a mode absent before that date. The old floor kept passing only because
`aggregationMethod: "median-run"` silently asserts category scores as best-of-N;
switching the routes floor to a true median would fail 5 of 50 recent jobs until
the page is reduced. Both configs run in the same required `axe` job, so
tightening before fixing would block every merge rather than flag one page.

Steps:

1. Diff what `/compare/` loads across those two commits. The step coincides with
   the artifacts snapshot refresh to the live corpus, so the first suspect is
   payload growth in the data the page carries, not the page's own code. The
   page currently ships about 94 KB of HTML against the home page's 8 KB, and
   that payload grows with the registry, so the number will keep moving.
2. Reduce the payload, then confirm median `/compare/` performance clears 0.80
   over several `a11y.yml` jobs.
3. Only then switch the routes config to `aggregationMethod: "median"`, keeping
   the floor at 0.80, and update ADR 0045 and the
   [conformance gaps](standards-conformance-gaps.md) entry.

The floor stays at 0.80 throughout. What is deferred is the tightening, not the
standard.

## Decide the share-alike question for records already listed

**Status: open, opened 2026-09-01.** Two findings from the 2026-09-01 coverage
pass are the same question, and neither is safe to settle inside a wave whose
job was adding records.

**France and ODbL.** 158 French records in the registry cite ODbL in their
`license_note`, including entries in `registry/fr/idf.yaml`, while
[`docs/feeds.md`](feeds.md) records ODbL French datasets as *excluded* and names
Île-de-France as an example of the exclusion. Both cannot be right. The records
arrived in the 2026-07-23 National Access Point pass; the exclusion predates it.

**Estonia and CC BY-SA 3.0.** Estonia's national Public Transport Register is
published under CC BY-SA 3.0 on the national open-data portal, and the
`terms_url` carried by `estonia-public-transport-register` and
`tallinn-public-transport-tlt` now returns 404.

The 2026-09-01 pass applied the strict reading to new admissions and changed
nothing already listed. That cost roughly 84 ODbL French datasets (Tisséo
Toulouse, STAR Rennes, TAG Grenoble among them) and 19 Estonian county feeds,
all of which pass every other gate.

What has to be decided, once, for both:

1. Does this project redistribute share-alike GTFS? The gates say no. The
   registry says yes for 160 records.
2. If yes, `docs/feeds.md` and the admission gates need amending, and the ~103
   deferred datasets become admissible.
3. If no, the 160 existing records need retiring, which reduces published
   coverage and unpublishes live scorecards. That is a listing-policy action,
   not a curation one, and the affected agencies should be handled under
   [`listing-policy.md`](listing-policy.md).

Do not resolve this by editing one side quietly to match the other.

## Teach `discover` to check its own replacement candidate

**Status: open, opened 2026-09-01.** All five feeds that
[`feed-discovery.md`](feed-discovery.md) lists under "Likely replaced" were
re-checked on 2026-09-01: every tracked URL the repo uses is live and serving a
zip, and two of the proposed replacements are not (MVV München's candidate
returns 404, Rockford's refuses the connection). Applying that report
unreviewed, or running `scorecard discover --apply` against it, would swap two
working feeds for dead links.

The report is already written as suggestions to verify by hand, which is what
saved it. A HEAD check on the candidate before listing it under "Likely
replaced" would stop a dead replacement being proposed at all.

## Feed sources blocked by the pipeline's HTTP client, not by policy

**Status: open, opened 2026-09-01.** Several feeds pass source, licence,
identity and calendar and fail only on how this pipeline fetches. Two of them
were diagnosed exactly on 2026-09-01 against OpenSSL 3.5.7, whose default
security level is 2:

- **`yamaguchi-opendata.jp`** — the server sends
  `TLSV1_ALERT_INSUFFICIENT_SECURITY`. At `DEFAULT@SECLEVEL=1` it negotiates
  TLS 1.2 with `AES256-SHA256`: static-RSA key exchange, so **no forward
  secrecy**. This host carries Iwakuni City and Hikari City, both official
  municipal CKAN datasets, both CC BY, both keyless, calendars to 2027-03-26
  and 2027-03-31. They are the only route into **JP-35 Yamaguchi**, one of the
  two Japanese prefectures still empty.
- **`webapps.regionofwaterloo.ca`** — `DH_KEY_TOO_SMALL`. At
  `DEFAULT@SECLEVEL=1` it negotiates TLS 1.2 with `DHE-RSA-AES256-GCM-SHA384`,
  which does have forward secrecy; the server's Diffie-Hellman parameters are
  simply under 2048 bits. This host carries Grand River Transit (CA-ON).
- **`transport.act.gov.au`** (Canberra) is a different problem, not TLS: it
  answers every non-browser client with a Cloudflare interstitial, including
  with full browser headers. The licence is fine and `data.act.gov.au` names
  the exact archives.

**The recommendation is not to weaken the client.** Lowering the security level
globally would degrade every one of the 2,575 fetches to accommodate two
servers, and this tool's standing rests on the trustworthiness of what it
publishes: a grade is derived from bytes fetched over that connection. A
per-record opt-in (the shape `large_feed` already uses, e.g. a curator-set
`legacy_tls: true`) is the only version worth considering, and even that buys
one prefecture and one Ontario operator.

The cheaper and more useful action is upstream: tell Yamaguchi Prefecture their
open-data portal offers no forward-secrecy cipher, and tell the Region of
Waterloo their DH parameters are undersized. Both are ordinary server
misconfigurations their operators would likely want to know about, and fixing
them helps every consumer of those portals, not just this project.

Until then these are worth separating from licence and freshness rejections
when reading coverage gaps: no amount of sourcing effort closes them.

## Coverage blocked on a credential or an email, not on curation

**Status: open, opened 2026-09-01.** Four cases where the licence is already the
right shape and the only obstacle is access. Each is one action away.

**Austria's regional feeds — a registration wall.** All seven Verkehrsverbünde
plus Linz AG publish on `data.mobilitaetsverbuende.at`: 17 GTFS datasets
refreshed weekly, VOR at 262.8 MB down to Linz AG at 5.4 MB. The API enumerates
anonymously (`GET /api/public/v1/data-sets`) but the file endpoint returns 401,
and the platform's own documentation says accounts are created manually and
cannot be scripted. MVO's terms already permit commercial reuse with
attribution. One project account would unlock eight fixed-route feeds covering
all nine Bundesländer plus six Flex feeds. This also needs code:
`static_gtfs_url` assumes a keyless URL, so authenticated fetching does not
exist in the pipeline.

**ESHOT İzmir — a host that is down.** 19 MB, on `acikveri.bizizmir.com`, under
the same CC BY 4.0 terms already approved for two registered İzmir records. TCP
timeout on 443 and 80 across two passes, while sibling `izdeniz.com.tr`
answered 200 in the same batch, so it is per-host rather than a network path.

**TRANSTU Tunis — a host that is down.** Tunisia's catalog confirms nine
OTL-licensed datasets and the OTL grants commercial reuse with attribution, but
every resource URL points at `data.transport.tn`, which refuses on 443, on 80,
and by IP. Tunisia would be a new country code.

**Yellowknife (CA-NT) — a missing listing.** The open-data terms are live at
`yellowknife.ca/open-data-terms-use` and are exactly the right shape ("exploit
the Datasets commercially", attribution only). The City's portal holds 60 items,
none transit, and no City page names the `passio3.com` endpoint that serves the
feed. CA-NT has no shard.

Also worth an upstream note: Mobility Database source 2138 still points at a
stale ÖBB resource (`GTFS_OP_2024_obb.zip`).

## Existing records whose evidence did not survive re-reading

**Status: open, opened 2026-09-01.** Separate from the share-alike question
above, three records already in the registry were found to rest on evidence that
does not hold. None was edited; all need a curator decision.

- **`donan-bus`** (`registry/jp/01.yaml`, admitted 2026-07-17) is sourced from
  the `ckan.hoda.jp` dataset the 2026-09-01 pass rejected, so its evidence is
  the CKAN licence field that gate 2 excludes. Its calendar now ends 2026-09-30
  and no alternative URL exists.
- **CUMTD** carries no `reuse_evidence` and would fail gate 2 today: its terms
  restrict use to purposes that "assist mass transportation riders", require an
  embedded key, and are revocable at will.
- **`st-lawrence-county-public-transit`** (`registry/us/ny.yaml`) has a
  `license_note` citing a data.ny.gov (OPEN-NY) licence PDF, but the feed is
  served from the `datatools-511ny` bucket, which is governed by NYSDOT's
  Developer's Access Agreement and requires registration. Low impact, since the
  record claims no `reuse_evidence`, but the note misleads a reader.

**Abashiri Bus** is the opposite case and worth a recheck: source and licence
are clean, and only `feed_info.feed_end_date` (2026-07-31) blocks it while its
`calendar_dates` run to 2026-11-23.
