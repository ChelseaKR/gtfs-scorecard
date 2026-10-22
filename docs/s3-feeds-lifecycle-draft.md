# Draft: expire only non-receipt bytes in the artifacts bucket

Status: DRAFT. OWNER-APPLIES. Nothing in this file is applied, and nothing in
this branch changes `infra/artifacts/main.tf`. Applying it means a Terraform
apply against the shared AWS account and, before that, one tagging pass over the
bucket. Both are the owner's to run.

Measured on 2026-10-21 (read-only):

- Standard storage 131 GB, Glacier Instant Retrieval 203 GB. September's S3
  storage lines were $2.29 (Standard) and $0.31 (Glacier IR), so the whole
  storage bill is about $2.60 a month.
- `feeds/` holds 38,800 objects and 322.7 GB (content-addressed zips named
  `feeds/<sha256>.zip`). `data/` holds 308,751 objects and 10.4 GB. `quarantine/`
  holds 5,145 objects and 1.1 GB (`quarantine/2026-07-11-orphan-dupes/`).
- The bucket already has rules for: dated artifacts tagged
  `artifact-class=dated` (400 days), noncurrent versions (1 day), program
  bundles and requests (30 days), `history/` (400 days), `cache/structure-staging/`
  (7 days), and `feeds/` to Glacier IR at 30 days. `feeds/` never expires, on
  purpose (see the comment above that rule in `infra/artifacts/main.tf`).

So the ceiling for any expiry rule on storage is under $2.60 a month. This
draft exists because the roadmap asked for it, not because it is where the AWS
bill is. The AWS bill is data transfer out (see the PR that carries this file).

## What counts as a receipt

A receipt names a feed by its SHA-256 (`feed.sha256` in a dated artifact, in an
evidence packet, in a retest record, in a `scorecard reproduce` output). To
reproduce a receipt, the zip at `feeds/<that sha256>.zip` has to exist.
Receipts are held by other people as well as by this repository, so the set of
hashes some receipt names cannot be enumerated from inside the bucket. There is
no S3 prefix or object named "receipt" today (top-level prefixes on 2026-10-21:
`cache/`, `data/`, `feeds/`, `history/`, `lambda-packages/`, `quarantine/`).

The rule below therefore never selects by age or prefix alone. It selects only
objects that carry an explicit tag, and the tag is applied only by the
selection procedure in the next section.

## Selection logic

An object under `feeds/` is a candidate only if all of these hold. Anything
uncertain is not a candidate.

1. Its hash appears in no `feed.sha256` of any artifact still in the bucket:
   every `data/artifacts/<id>/latest.json`, every dated
   `data/artifacts/<id>/<date>.json` still present (up to 400 days), and every
   month under `history/`.
2. Its hash appears in no committed receipt, evidence packet or retest record
   in this repository (search the whole git history, not just the tip), and in
   no file under `docs/` or `data/`.
3. Its last-modified time is more than 400 days old, which is past the longest
   retention of any artifact that could name it.
4. It is not under any other prefix. Only `feeds/<64 lowercase hex>.zip` keys
   are considered; any key that does not match that pattern is skipped and
   reported.

The procedure is a read-only listing that produces a candidate file, a human
review of that file, and then a tagging pass that sets
`retention=unreferenced-feed` on exactly the reviewed keys. The tagging pass is
the only write, and it is the owner's.

## Terraform (not applied)

The rule filters on the prefix and the tag together, so an untagged object can
never match, and removing the tag takes an object out of scope before the rule
fires. The 30-day delay after tagging is the window to notice a mistake.

<!-- OWNER-APPLIES: add inside aws_s3_bucket_lifecycle_configuration.artifacts -->

    rule {
      id     = "expire-reviewed-unreferenced-feeds"
      status = "Enabled"

      filter {
        and {
          prefix = "feeds/"
          tags = {
            retention = "unreferenced-feed"
          }
        }
      }

      expiration {
        days = 30
      }
    }

The same rule as the JSON the CLI takes (`aws s3api put-bucket-lifecycle-configuration`
replaces the whole configuration, so merge it into the existing rule list first;
do not apply it alone):

    {
      "ID": "expire-reviewed-unreferenced-feeds",
      "Status": "Enabled",
      "Filter": {
        "And": {
          "Prefix": "feeds/",
          "Tags": [{ "Key": "retention", "Value": "unreferenced-feed" }]
        }
      },
      "Expiration": { "Days": 30 }
    }

Expiration of a current object in a versioned bucket writes a delete marker; the
existing `expire-noncurrent-versions` rule then removes the bytes after one day.
That makes the real undo window shorter than 30 days: the tag is the control,
and 30 days is the time to find a mistake before the delete marker is written.
Count the one extra day before relying on the window.

## The risk, stated plainly

A receipt-named object must never be expired. If a feed zip that some receipt
names is deleted, `scorecard reproduce` for that receipt fails with
`ArchiveMiss`, the receipt can no longer be independently reproduced, and the
bytes cannot be recovered (the archive is the only copy; the agency's own feed
has since changed). That loses the property the product sells.

What keeps it from happening:

- The rule matches only an explicit tag, never a prefix or an age.
- The tag is applied only to reviewed keys that pass all four checks above.
- A hash named by a receipt held outside this repository cannot be seen. That
  is why check 3 uses 400 days, and why the honest answer to "is this safe for
  every receipt anyone holds" is no. If that matters, do not apply this rule.
- Do not widen the filter to `feeds/` alone, and do not add an age-only
  transition-then-expire rule on that prefix.

Expected saving if every Glacier IR byte were expired: about $0.80 a month
(203 GB at $0.004). The realistic figure depends on how many hashes pass the
checks, which has not been measured (it needs a read of every retained
artifact, which is itself about 10 GB of transfer).
