---
date_published: "2026-08-07"
date_modified: "2026-08-07"
---

# California GTFS-Realtime health

Realtime is a compliance area in the California Transit Data Guidelines v4.0.
Agencies buy realtime systems off state master agreements, and Caltrans consumes
realtime internally. The published
[monthly reports](https://reports.dds.dot.ca.gov/) assess the schedule side;
their FAQ says the site displays a subset of the Guidelines, and realtime
appears there as a pass or fail presence check taken at most twice a month.

Nobody publishes continuous realtime quality for California feeds. This adds
that layer, using the realtime machinery this scorecard already has rather than
a second scoring model beside it. It is complementary to the state's reports,
not a substitute for them, and it is not a compliance determination. Realtime
reliability changes no grade.

## Where the endpoints came from

Each agency's own monthly report carries a "Show Source URLs" panel listing the
schedule and realtime feeds the state has on file for it. That panel is the
source for every endpoint configured here. The
[crosswalk](california-reconciliation.md) says which registry record each
agency's report belongs to, so an endpoint is only attached to a record whose
match to that organization is confirmed.

Provenance is recorded per endpoint in
`data/california-realtime-sources.yaml`: the agency, the feed kind, the URL, the
report it came from, and the date it was verified.

## Verification, and what was excluded

An endpoint was only configured after it was fetched once and the response
parsed as a GTFS-Realtime `FeedMessage` carrying a header version. Anything that
did not clear that bar is listed with its reason instead of being configured.
An exclusion is a finding, not a gap in the work.

Of 362 realtime endpoints listed across the matched California agencies,
**179 were verified and configured across 63 agencies**, and **183 were
excluded**:

| Reason | Endpoints |
|---|---|
| Needs a Bay Area 511 API key this project does not hold | 90 |
| Needs a Swiftly API key this project does not hold | 71 |
| Did not return a readable GTFS-Realtime message when fetched | 22 |

The two keyed groups are the larger share, and they are worth naming plainly.
Bay Area 511 aggregates realtime for most operators in the region behind a free
but registered API key, and Swiftly serves several California agencies the same
way. Both are legitimately reachable with a key; this project has not requested
one, so those feeds stay unmeasured rather than being guessed at. Getting keys
would be the single largest expansion of California realtime coverage available.

The 22 unreadable endpoints break down as authentication refusals (`HTTP 401`
from eTrans, Omnitrans, and San Diego International Airport), a certificate that
failed verification, a timeout, and a set of service-alert URLs that answered
with something other than a protobuf. Each is recorded individually in the
sources file. They are candidates to re-check rather than conclusions about the
agencies.

## What the view reports

The realtime monitor already samples every configured feed on a schedule and
appends one observation per agency to `data/rt-health` (ADR 0012). Each
observation records how many feed kinds answered, how far behind the feed's own
header timestamp was, and how much of the scheduled service appeared in it. The
California program page now rolls that record up for the whole cohort:

- **Reachability** as the share of monitor runs each feed answered, in the same
  reliable / mostly / spotty bands the national realtime view uses.
- **Freshness** as the median lag between the sample and the feed's own header
  timestamp. A feed that publishes no timestamp is said to publish none, not
  scored as stale.
- **Trip coverage** as the median share of scheduled trips seen in TripUpdates,
  where the schedule feed makes that measurable.

Least reliable first, because that is the order a support programme works in.
Agencies with a configured endpoint the monitor has not yet sampled are counted
as waiting, never shown as failing. Agencies with no realtime feed at all stay
neutral, exactly as they are on their own scorecards.

Every newly configured feed was sampled once when it was added, so the view
carries a real reading for each of them from the first publish rather than a
page of agencies waiting on their first sample. One reading is a thin basis for
a reliability percentage, and the view says how many checks each figure rests
on for exactly that reason. The three-hourly monitor takes it from there, and
the numbers settle over the following days as the record fills in. That
accumulate-across-runs shape is the serverless tier ADR 0012 chose on purpose.

## Refreshing this

Re-read the state's directory and rebuild the crosswalk first, then re-verify
the endpoints. Verification touches every endpoint once, so it is a manual step
rather than part of any scheduled run, and no test in this repository reaches
the network.

## What is not here yet

**Realtime validator notices.** This measures reachability, freshness, and trip
coverage. It does not run MobilityData's GTFS-Realtime validator, so it does not
report notices such as a stale vehicle timestamp or a trip update referencing an
unknown trip. That is a separate subsystem rather than a setting: the validator
is a Java tool that would need a process per sample, somewhere to keep the
notices, and a surface to show them, on the same footing as the schedule
validator this project already wraps. It is deliberately not attempted here.

The gap is narrower than it sounds. The state's monthly reports already run that
validator against each realtime feed twice a month and publish the pass or fail,
which is the assessment side. What was missing was the continuous side, and that
is what this adds. Doing the notices properly means wrapping the canonical tool
the way `validate.py` wraps the schedule validator, not reimplementing its rules
here.

**The keyed feeds.** Bay Area 511 and Swiftly cover most of the state's realtime
by ridership and both need an API key this project has not requested.

**Per-endpoint history.** The monitor's record is per agency, so one unreachable
feed kind shows up in the agency's reading without being separated out in this
view.
