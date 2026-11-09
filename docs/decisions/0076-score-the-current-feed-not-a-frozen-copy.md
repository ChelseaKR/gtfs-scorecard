# ADR 0076: Move records to the feed agencies publish today, and keep the move out of history

**Status:** Accepted (2026-11-08) on the maintainer's goal: "i want to match what
feeds are publishing today." 0075 is taken by `fix/gtfs-honest-fetching`.

## Context

On 2026-11-08, 133 of 2,499 published grades (5.3%) were scored from a Mobility
Database mirror copy. None has refreshed since 2026-10-19, because ADR 0070 stopped
reading the host those copies live on, and ADR 0075 removes the fallback entirely.
So each of these pages holds its last copy until the URL on file works again.

Many of those agencies are publishing today at a different address. The weekly
catalog check does not fix this on its own. Its open pull request (#553) would
move 14 records onto dated `openmobilitydata-data` archive files, dated 2013 to 2024,
and that would present a frozen copy as the agency's own URL.

## Decision

1. **A record may move to a new URL only after that file is read.** The file must
   be a GTFS zip that robots.txt allows us to request, whose agency name and stop
   locations match the record. A URL can be found through the Mobility Database
   catalog and its redirects, Transitland Atlas (CC BY 4.0, used to find addresses;
   no feed bytes come from it), or the agency's own open data page. If the match is
   unclear, the record stays where it is and is listed for a person.
2. **The move is recorded on the record.** A dated `operating_note` names the host
   and where the address came from. Naming the host also holds the record against
   the weekly catalog check (`hold_pinned_hosts`).
3. **A record whose catalog successor is already published retires into it**
   rather than becoming a second page for the same feed.
4. **Discovery never moves a record onto a frozen archive** (`is_frozen_archive`).
5. **A move between a mirror copy and the agency's URL is not a comparable
   transition.** `same_producer_contract` is false across it, so it produces no
   improved-feed claim, no cleared-finding receipt, and no "what changed" diff.
   History points carry `fetch_source` only when it is "mirror".
6. **A liveness 304 does not reuse a mirror-scored grade**, because it describes
   the origin's bytes, not the copy's.
7. **The page names the day the copy was downloaded**, when that date is known.

## Consequences

- A moved feed's grade can change at the move. Its earlier points stay published
  and are not compared with the new one.
- Many moved feeds will grade worse or better for real reasons, and some of the
  files agencies publish have already ended. That is now the agency's own state,
  and the page says so.
- Hosts that refuse robots.txt, need a key, or have no findable current feed stay
  as they are, with the existing mirror wording.
