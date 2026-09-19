# Agency registry

The scorecard loads the shards listed, in order, by [`index.yaml`](index.yaml).
The manifest is authoritative: every listed file must exist, every YAML shard
under this directory must be listed, and agency ids must be unique across the
merged registry. This explicit list prevents a stray or partially generated
YAML file from silently entering production.

New agency submissions go to [`intake.yaml`](intake.yaml). Once a curator has
verified the agency's primary location, move its complete YAML block to the
matching `registry/<country>/<subdivision>.yaml` shard and add a new shard to
`index.yaml` when necessary. Move the block textually so comments and field
ordering survive. A submission and a routine feed-URL update should each touch
only the relevant small shard.

## Required fields

- `id`: stable lowercase slug containing letters, digits, `-`, or `_`.
- `name`: public agency or service name.
- `static_gtfs_url`: direct `http(s)` URL for the GTFS Schedule feed.

## Location fields

- `country`: assigned ISO 3166-1 alpha-2 code. State it on every new entry;
  omitted legacy entries default to `US` for compatibility.
- `subdivision_code` and `subdivision_name`: portable primary jurisdiction,
  normally an ISO 3166-2 code and its canonical name. Supply them together.
- `state`: deprecated US-only compatibility input retained on older records.
  Do not add it to new entries; portable location fields are canonical.

An agency that cannot yet be located honestly stays in `intake.yaml`; location
must not be guessed merely to choose a shard.

## Optional feed and curation fields

- `rt_urls`: mapping whose supported keys are `trip_updates`,
  `vehicle_positions`, and `service_alerts`; every value is an `http(s)` URL.
- `rt_note`, `license_note`, `operating_note`, `ntd_note`: curator-facing
  explanatory text shown on the relevant scorecard surfaces. `scorecard
  license-audit` reads `license_note` as data, so name the one licence that
  applies by its usual name or SPDX id. A note that names a second licence,
  even to say it does not apply, is reported as `unknown` for a curator to read.
- `mdb_id`: Mobility Database source id used for exact feed rediscovery.
- `ntd_id`: four- or five-digit US National Transit Database id.
- `organization_id`: stable operator slug shared by related feeds.
- `alias_of`: id of another registry entry when this is a retained alias.
- `feed_variant`: descriptive variant label for one operator's multiple feeds.
- `feed_status`: `active`, `deprecated`, `inactive`, or `development`.
- `is_official`: `true` or `false` when catalog provenance establishes it.
- `service_type`: `fixed` (default), `seasonal`, or `demand_response`.
- `fare_free`: `true` only when fare-free operation is a verified policy.
- `own_shard`: `true` gives the record a Daily scoring shard to itself. Use it
  only for a source measured to take many minutes to serve one ordinary-sized
  feed, such as a server that builds the archive on each request, so that its
  wait cannot use up the time budget of the records that would share its shard.
  It changes nothing about how the feed is fetched, validated, or scored, and
  unlike `large_feed` it does not raise any size ceiling. Say in a YAML comment
  what was measured and when.
- `fetch_auth`: a credential reference for a feed behind a registration wall;
  see [Credentialed feeds](#credentialed-feeds-fetch_auth) below.

A replaced endpoint may remain in the registry as `feed_status: deprecated`
with `alias_of` pointing to its active successor. It is then excluded from
batch scoring and the current catalog, while its dated artifacts remain
available for reproducibility and its former scorecard URL redirects to the
successor. Do not infer this relationship from similar names; record it only
from a reviewed catalog redirect or provider evidence.

`scorecard supersessions` reads that catalog redirect for you. The Mobility
Database marks a replaced feed record `deprecated` and names its successor in
`redirect.id`; the command pairs the two, writes `alias_of` and
`feed_status: deprecated` on the retired record with a comment naming the
catalog ids, and lists what it could not resolve in
`docs/feed-supersessions.md`. It reports on its own and only edits with
`--apply`, and the weekly `discover` workflow runs it into a review pull
request. A retirement whose successor publishes under a different agency name
is called out separately in that report: the catalog is usually right about it,
and it is still the case to read before merging.

Two of those cases are not left to a reader noticing them. A retirement whose
successor sits in a **different state or country**, or whose successor's name
does not read as a rename of the record retiring into it, is **held**: the
command will not write it, and `pipeline/scripts/check_supersession_review.py`
fails the build if it is written by hand, until the decision is recorded in
`supersession-review.yaml` at the repository root. A decision there is either
`retire` (one agency, or a real merger) or `keep_separate` (not the same
agency, and the automation must not re-apply the redirect), and each one states
its evidence. See `docs/supersession-flagging.md`.

### Reviewed reuse evidence

`reuse_evidence` is an optional, curator-approved record used by bounded
coverage gates. It is deliberately separate from `license_note`, catalog
`is_official` flags, and Mobility Database metadata. Those fields can point a
reviewer toward evidence, but they never grant permission by themselves.

```yaml
reuse_evidence:
  decision: approved
  source_kind: official_portal
  provider_source_url: https://provider.example/dataset
  terms_url: https://provider.example/terms
  scope: [gtfs_schedule]
  attribution: Provider name.
  reviewed_by: curator-handle
  reviewed_on: "2026-07-16"
  identity_reviewed: true
```

The parser accepts only an `approved` decision, `official_portal` or `provider`
source kind, HTTP(S) evidence links, the closed `gtfs_schedule` scope, a valid
review date that is not in the future, non-empty attribution and reviewer, and
an explicit identity review. Unknown keys or inferred evidence fail registry
loading. Absence means no approved evidence record is on file; it is not a
claim that the feed is unlicensed.

### Credentialed feeds (`fetch_auth`)

Some publishers put a feed whose licence already permits reuse behind a
registration wall: the file answers 401 until a registered account's key is
sent. `fetch_auth` lets a record name that key without containing it.

```yaml
fetch_auth:
  kind: header                         # header, query, or basic
  name: X-Api-Key                      # header or query-parameter name; omit for basic
  secret: SCORECARD_FEED_AUTH_EXAMPLE  # the NAME of an environment variable
```

- `kind: header` sends the variable's value in the header called `name`.
- `kind: query` appends `name=<value>` to `static_gtfs_url`. Leave the
  parameter out of the URL on file; `lint --strict` refuses a URL that already
  carries it.
- `kind: basic` sends HTTP basic authentication. The variable holds
  `user:password`, and `name` is not used.

`secret` is never the credential. It must be an environment variable name that
starts with `SCORECARD_FEED_AUTH_` and uses only capital letters, digits, and
underscores. `scorecard lint --strict` blocks anything else as
`literal_credential`, and the secret scan (`.gitleaks.toml`) blocks it too.
The prefix also stops a record from pointing the fetcher at another secret the
pipeline holds and sending it to the host the record names. A user name or
password written into any feed URL (`https://user:pass@host/`) is blocked the
same way; use `kind: basic` instead. A credentialed record needs an `https`
`static_gtfs_url`.

What happens at fetch time:

- **Variable unset or empty:** the feed is recorded as unreachable with the
  reason `credential not configured`, and nothing is requested. There is no
  keyless attempt and no fallback to the Mobility Database mirror, and no
  artifact is written, so no grade appears. The last published scorecard, if
  there is one, stays as it was.
- **Variable set:** the credential goes only to the feed URL's own host.
  If the publisher redirects to another host, the credential is not sent
  there. The artifact's `fetch` block records `auth: env-ref` and
  `auth_kind`, and never the credential or the variable's name. For a
  credentialed fetch, `fetch.final_url` is published without its query string.
- **Request fails:** the error names the exception and HTTP status only,
  because a full error message would quote a URL that can hold the credential.

The keyless liveness check skips credentialed records, so a gated URL's 401 is
never counted as an outage. The daily run scores them every day instead.

**A key is access, not a licence.** Registering for an account shows that we
can download the feed. It does not show that the scorecard may republish or
grade it. A credentialed record still needs `reuse_evidence` reviewed against
the publisher's terms, exactly like any other record, before it is admitted.

Where the value lives is up to whoever runs the pipeline, never this
repository. In GitHub Actions, store it as a repository secret and map it
into the scoring step's environment with
`SCORECARD_FEED_AUTH_EXAMPLE: ${{ secrets.SCORECARD_FEED_AUTH_EXAMPLE }}`.
Elsewhere, set it in that runtime's environment from its own secret store,
never in a committed file. Pull requests from forks get no secrets, so a
credentialed record reads as `credential not configured` there, which is the
intended result.

Unknown fields, malformed URLs or locations, duplicate ids, missing alias
targets, and alias cycles fail registry loading. Run the same gates as CI before
opening a pull request:

```sh
cd pipeline
uv run scorecard lint --strict
uv run pytest -q tests/test_agencies.py tests/test_submissions.py
```

The contributor walkthrough is in
[`docs/add-your-agency.md`](../docs/add-your-agency.md).
