# ADR 0084: Agency pages offer the free alert under the grade, and help when the address fails

**Status:** Accepted (2026-11-21). The maintainer approved the recommended
wording for both lines on 2026-11-21. 0083 is taken by the alert-signup events
branch.

## Context

A traffic review on 2026-11-20 found that real searchers land almost only on
agency pages (50 sessions in 28 days, 42% engaged), and then leave. The free
alert, the lead list for the paid bundle and history tables, appears only as
one of six small links above the hero. Pages whose feed address on file had
failed did worst: 0 of 8 such search visits engaged. Those readers came for
the feed file, and the page opens with provenance notes and the dead address.

## Decision

- **Every agency page** carries one line right under the grade box:
  "Watch this feed for free: we email you before it expires or when its
  grade drops." The link opens `/subscribe.html?agency=<id>`, which the
  alerts form reads to choose the agency (ADR 0082). The link in the action
  row stays.
- **A page whose address on file failed** opens, above the agency name, with
  one sentence: "The feed address on file failed at our last check (HTTP
  404)." It shows only when the daily liveness check's last answer was an
  HTTP 4xx. A 5xx, a timeout or a certificate error can pass by the next
  check, so none of them shows it. The sentence then:
  - links "Download the newest saved copy" from the Mobility Database when
    the grade was scored from one (`fetch.source` is `mirror` and
    `fetch.final_url` is a `files.mobilitydatabase.org/<id>/latest.zip` or
    `mdb-latest` bucket address). The site never hosts a copy itself;
  - always links "send us the new address" to `/claim/?agency=<id>`, the
    existing correction route. There is no new form and no new email
    collection.

## Consequences

- On 2026-11-20 production data, 2,493 agency pages get the alert line. 85
  had a 4xx at their last check and get the note: 55 with the saved-copy
  link (45 on `files.mobilitydatabase.org`, 10 in the `mdb-latest` bucket)
  and 30 without one.
- `pipeline/tests/test_agency_feed_help.py` holds the wording, the 4xx-only
  rule, the two copy shapes and the placement. The agency goldens gained the
  alert line.
