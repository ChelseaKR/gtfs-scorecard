# ADR 0066: Redact credentials in published feed URLs, and do not rewrite history

**Status:** Accepted (2026-10-11).

## Context

Every scorecard artifact records two URLs: `feed.static_url`, the feed URL
configured in the registry, and `fetch.final_url`, the URL that actually served
the scored bytes after redirects. Both were published exactly as recorded, in
the per-agency `latest.json` and dated artifacts, and the configured URL also
reached the catalog, `directory.json`, the API files, the scorecard pages and
their JSON-LD `isBasedOn`.

A recorded URL can carry a credential:

- **Presigned redirects.** Some feed URLs redirect to a presigned object in a
  third party's bucket. The recorded `final_url` then carries the temporary
  credential and signature that object was signed with. In the committed
  fallback snapshot (`data/artifacts`, 2,494 `latest.json` files), 376 feeds
  redirect through one Japanese GTFS data repository's S3 bucket with
  `AWSAccessKeyId`, `Signature`, `x-amz-security-token` and `Expires`; a few
  more go through S3 or R2 with Signature Version 4 parameters, Azure Blob
  shared access signatures (`sig`) or GitHub release-asset links (`jwt`).
  These are short-lived, already expired, and were issued by those third
  parties for their own buckets. None was issued by this project's AWS
  account.
- **Publisher API keys.** Seven configured feed URLs carry a publisher's API
  key in the query (`apiKey` or `key`), and some redirects add one. These are
  the keys the publishers hand out for their open-data downloads. The seven
  configured URLs are also in the public registry shards, because the pipeline
  needs them to fetch.

The credentialed-fetch path (#371) already published only scheme, host and
path (`feed_auth.published_url`), because there the query is known to hold our
own credential. The plain path recorded the URL verbatim.

## Decision

1. **One rule.** `pipeline/src/scorecard_pipeline/url_redaction.py` holds the
   only list of credential-like query parameter names: an explicit,
   case-insensitive set (`AWSAccessKeyId`, `Signature`, `Expires`,
   `x-amz-security-token`, `sig`, `jwt`, `key`, `apiKey`, `api_key`, `token`,
   `access_token`, `auth`, `Authorization`, and the others listed there) plus
   the `X-Amz-` and `X-Goog-` prefixes that every Signature Version 4 or
   Google V4 parameter uses. A matching parameter keeps its name and its value
   becomes `REDACTED`, so a reader can still see that the download needed one.
   A `user:password@` part is dropped. Every other part of the URL is kept
   exactly, and a URL with nothing to redact is returned byte for byte. Every
   listed name has a test.
2. **Applied where URLs are published, never where they are fetched.** The
   registry, the fetch, and the private `provenance.json` sidecar are
   unchanged. The rule runs:
   - in `publish.py`, so every artifact written from now on, in the repo and in
     the S3 store, carries redacted URLs;
   - where `render_site` reads each `latest.json`, so the catalog, directory,
     API files, pages, and JSON-LD built from that in-memory record inherit it
     (including the source-feed link, which reads the same field);
   - in the dataset records (`cli._latest_records`) and global coverage, which
     emit the configured URL;
   - on every JSON file `assemble_public_artifacts.sh` copies into the
     deployed site. This is the boundary that covers artifacts written before
     this change, including the committed fallback snapshot and the dated
     records the deploy hydrates from S3. It rewrites only the URL strings it
     changes, so every other byte of a file is preserved.
3. **Consumers that compare URLs compare the published form.**
   `dataset_release` checks the catalog against the registry URL in its
   redacted form, and the tool-profile publisher snapshot answers to a feed's
   redacted URL as well as its raw one.
4. **The paid history export uses the same rule.** Its tables v1.1 redaction
   (branch `feat/data-marketplace-listing`) was the model for this one. When
   that branch lands, it should call `url_redaction.redact_url` instead of
   keeping a second list.

### Committed history is not rewritten

- **Git history stays as it is.** Rewriting it would break every clone, fork,
  tag, and signed release, and would not unpublish anything: the values have
  been public since the artifacts were first committed, and the Wayback
  Machine and other mirrors keep their own copies.
- **The committed artifact files are not regenerated in this change either.**
  The deployed site no longer serves their raw URLs, because the assembly step
  redacts every copy. Rewriting about 1,300 snapshot files would make a large
  data diff for no change on the site, and it would not remove the values from
  the repository, which still has them in history and, for the seven
  configured keys, in the registry shards the pipeline fetches from. The files
  are regenerated with redacted URLs whenever the snapshot is re-materialized,
  as any future write passes through `publish.py`. The same holds for the
  rendered files committed under `web/` (the catalog, `api/v1/` files and a
  few agency pages): every deploy re-renders them through the redacting
  reader before they are published, so the committed copies only matter to
  someone browsing the repository, and they change whenever they are next
  regenerated.
- **The S3 artifact store behind the CDN still holds older dated records with
  raw URLs.** The CloudFront origin serves `/data/artifacts/<agency>/<date>.json`
  directly from that store, so those records stay readable there until they
  are rewritten. The same module can do that as an owner-run step (sync the
  `data/artifacts` prefix down, run `python3 -I url_redaction.py <dir>` to
  count and again with `--write`, sync it back), which changes only the URL
  strings in records the project otherwise treats as immutable. That is a
  decision for the owner, not something a deploy does.

### What is not ours to fix

The expired presigned tokens belong to the third parties that issued them;
rotating or revoking them is their concern, and they expire by design. The
publisher API keys are the publishers' own open-data keys. Whether to tell a
publisher that its key appeared in a public URL is the owner's call; this
change does not contact anyone.

## Consequences

- A published URL that needed a key or signature no longer works when copied
  as is. It still names the host and path, and the `REDACTED` placeholder says
  why it will not download. A reader who wants the feed uses the publisher's
  own instructions or the Mobility Database record.
- A new URL-valued field in an artifact is covered without anyone remembering
  to add it: the renderer and the assembly step redact every http(s) string,
  not a named list of fields.
- A new credential parameter name needs one line in the list and one test.
