# ADR 0046: The producing tool comes from the feed's own declaration, not its host

**Status:** Accepted (2026-08-10)

## Context

`tool_profiles.detect_tool` names the tool that produces an agency's GTFS so the
fix surfaces can say who makes the change: the "Send your vendor a fix request"
block, the outreach note, the guided fix loop, the board packet, and the cohorts
the vendor-regression radar groups by. Until now it answered that question from
the host in the feed URL. A feed served from `data.trilliumtransit.com` was
credited to Trillium; one served from `rapid.nationalrtap.org` was credited to
National RTAP's GTFS Builder.

Hosting is not producing, and in this registry the two come apart.

Every `rapid.nationalrtap.org` feed URL in the registry sits under
`/GTFSFileManagement/UserUploadFiles/<id>/`, with user-chosen filenames
(`BATA_GTFS.zip`, `T.zip`, `ats_albany_ga_us(2).zip`). That is a file-upload
path: it carries whatever an agency uploaded. Reading feed_info.txt from all 21
of them, 2 name National RTAP as publisher and one names Connexionz Ltd. An
agency whose feed was built by Connexionz was being told to make the change in
GTFS Builder's spreadsheets.

`data.trilliumtransit.com` is closer to its claim but not equal to it. Across a
155-feed sample, 148 declare `Trillium Solutions, Inc.` as publisher, 3 ship no
`feed_info.txt`, 2 name the agency, and 2 name **GMV Syncromatics**. Those last
two were being handed a fix request addressed to a company that did not build
their feed.

A prior investigation had joined `data/caltrans-report-directory.json`'s
`schedule_vendors` against detected tools and read the disagreements as
misattribution. They are not: that field lists the agency's own scheduling
software (Excel, Trapeze, Via/Remix), which is a different question from who
produces the GTFS. Reading the feeds themselves is what separated the two.

## Decision

Producer attribution reads the feed's own `feed_info.txt` declaration first, and
the host only where the URL is a tool's generated-export endpoint.

1. A URL that is itself the finding is answered first. The TransitFeeds archive
   profile describes the URL, not a producer, and "publish from a live URL you
   control" stays true whoever built the bytes.
2. `feed_publisher_name` and `feed_publisher_url` decide. When they resolve to a
   producer this project documents a fix path for, that profile is returned even
   if the host says otherwise. When they resolve to a producer with no documented
   fix path (GMV Syncromatics, Connexionz, Optibus, MTI UMD), the answer is no
   named vendor: knowing it was somebody else is enough to keep the host's name
   out of the copy. A declaration naming the agency resolves to nothing, because
   most tools write the agency there and it says nothing about the tool.
3. The host decides only where the match is itself producer evidence.
   `passio3.com/<tenant>/passioTransit/gtfs/` and `gtfs.remix.com` are the tools'
   own generated exports. `trilliumtransit.com` and `rapid.nationalrtap.org` are
   marked `serves`: they carry other producers' feeds, so on their own they name
   nobody. The `produces` marking is falsifiable rather than assumed. A feed on
   one of those endpoints whose declaration names another producer still loses
   the endpoint's name, which is how a wrong marking would be caught.

Anything unresolved returns `None`, and every fix surface keeps its existing
generic wording ("whoever runs your scheduling software export"). An honest
unknown is better than a confident wrong name; naming the wrong company wastes
the one email a manager sends.

The declarations live in `data/feed-publishers.json`, read once by
`pipeline/scripts/fetch_feed_publishers.py`. Like the Caltrans directory
snapshot, that script reaches the network and no test or daily build runs it, so
attribution stays reproducible offline. Entries are keyed on the feed URL they
were read from: a feed that moves simply has no evidence at its new URL rather
than inheriting a stale one.

## Consequences

Attribution is now evidence-led in both directions. Feeds hosted by a service
that did not build them lose a name they should never have carried. Feeds whose
declaration names a documented producer gain one even when they are served from
an agency's own bucket, which the host-only rule could never see.

Feeds on a hosting service with no readable declaration keep generic copy. That
is a real cost, and it is the intended one: no evidence, no name.

This changes attribution and copy only. No score, grade, category, weight, or
metric reads `tool_profiles`, and none moved.

The producer identity tables are short and will stay incomplete. A third-party
producer this project has never seen still reads as "no producer declared", and
a feed on a `serves` host then keeps generic copy rather than a wrong name,
which is the safe direction to be incomplete in.

The snapshot is a point-in-time read. A feed that changes producer between
refreshes carries the old declaration until the script is run again, so the
refresh belongs with the other periodic snapshot refreshes rather than with the
daily build.
