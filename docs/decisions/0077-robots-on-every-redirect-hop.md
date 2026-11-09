# ADR 0077: robots.txt is read before every redirect hop of a feed request

**Status:** Accepted (2026-11-08). Decided by the maintainer. 0075 is taken by
`fix/gtfs-honest-fetching` and 0076 by `feat/score-current-feed`.

## Context

ADR 0070 reads robots.txt "before any feed request", and the code did that for the
URL on file only. A redirect was then followed to wherever it led. On 2026-11-08
that was measured from the published artifacts. 740 fetched records end on a
different host from the one on file, and 70 of them end on a path that host's
robots.txt disallows, 58 on `static.data.gouv.fr` by way of
`transport.data.gouv.fr/resources/N/download`.

The daily liveness check had a wider gap. `scorecard liveness` read no robots.txt
at all, so it sent a conditional GET to feeds the schedule fetch refuses.

## Decision

1. **Every hop is checked before it is requested.** `safe_get` and `safe_download`
   take a `hop_guard`, called with each URL before its request. `require_robots`
   is that guard, under ADR 0070's rules without change: a disallowed path, a
   refused or unreadable robots.txt, and a redirect off `/robots.txt` all stop the
   fetch. The one allowlist of object stores still applies.
2. **It applies to every path that downloads a feed:** the schedule fetch, including
   credentialed feeds and scratch scoring; realtime sampling; the liveness check and
   the refresh's skip check; the catalog CSV read; the publisher sweep; and the OTP
   QA workflow, which used plain `curl`.
3. **A refusal on a later hop is the same "not fetched" state as one on the first.**
   The run records the existing reason, the page prints it beside the last measured
   grade with that grade's date, and the record ages through the existing freshness
   rules. A refusal is not retried and does not fall back to a mirror.
4. **A liveness refusal is not a check.** The result is `not_fetched`. The last record
   stands, including its date and failure streak, and it does not count as an outage
   or a recovery.
5. **robots.txt stays cached per scheme and host within a process.**

6. **One object store joins the allowlist, for one status.** On 2026-11-08
   `dataodpt.blob.core.windows.net` answered `/robots.txt` and a random root path the
   same way: 400 with `OutOfRangeInput` XML. We infer this is the host's generic reply
   for a path with no container, so that exact host and status read as "no file".
   This admits 27 records in Japan. No wildcard or other status is added.
7. **Two other object stores stay stopped.** `min01rg96sablob01.blob.core.windows.net`
   answers 409 `PublicAccessNotPermitted`, and
   `83025b28472d6aa2bf5ae59f3724aa78.eu.r2.cloudflarestorage.com` answers 400
   `InvalidArgument` naming Authorization. "Not permitted" and an authorization refusal
   do not count as having no robots file.

## Paths not changed

These do not download feeds, or use a rule already decided:

- `catalog_api.py`, the Mobility Database API, exempt from robots.txt by ADR 0070.
- `feedapi.py`, validator reports through that API.
- `gbfs.py`, equity, NTD and map sources, the validator jar, and IndexNow.
- `cli.py` artifact references, and `otp.py` calls to a trip planner.

## Consequences

- 86 records stop refreshing until a permitted address is found: 70 disallowed
  and 16 with robots.txt refused or unreadable. Counted on 2026-11-08 from each
  published artifact's final URL. 64 more change path on the same host and were
  not rechecked. They keep their last grade and page.
- France's Access Point download link stops being a way to read those files. The
  maintainer can ask the Access Point team whether bots may use it.
- About one more robots.txt read per new host per shard, and fewer feed downloads.
