# Listing policy

This is a short, plain statement of what the scorecard lists, why, and how an
agency can correct or remove its listing. It exists because the tool grades
public agencies by name, and the people it is built for deserve to know the
rules.

## What is listed, and why

The scorecard checks **public GTFS feeds** that an agency already publishes
openly, and grades the data quality. We list an agency to help it (and the
people who support it) see how the feed is doing and what to fix first. The
sources are public feed catalogs (the Mobility Database, transit.land) and
agency-submitted feeds.

## Privacy

The public scorecard does not use analytics or track visitors. It sets no
tracking cookies, sends no page-view beacons, and does not build rider or
visitor profiles. Site-quality checks use automated synthetic visits instead
of observing real visitor sessions.

The domain owner may verify ownership through DNS and submit the public sitemap
to Search Console outside this project. The repository contains no Search
Console credentials, API configuration, or automated submission workflow.

## What the grade is, and is not

The grade is a **data-quality and completeness lens** meant to help an agency
improve its feed. It is **not** the official Caltrans or Cal-ITP compliance
determination, and it is not a verdict on the agency's service. A low grade
usually means the feed is expiring or missing optional fields, not that the
buses are bad. Findings are framed as fixes, never as failures, and an agency
that does not publish realtime is shown neutrally, never penalized for it.

## How to correct or remove a listing

We will act on these quickly and without argument:

- **Correct a name, URL, or detail** that is wrong: use the
  [correction and claim form](https://gtfsscorecard.org/claim/), open a pull
  request against the [`registry`](../registry/README.md), or email the address in
  the repository. A correction only needs a public source that supports it.
- **Request removal**: an agency that does not want to be listed can ask to be
  removed, by the same channels. We honor removal requests; the entry is deleted
  and the agency is excluded from future runs.
- **Report a feed that has moved or broken**: tell us and we will update or drop
  the URL.

## Agency claims and verification

Agency staff can ask to become the verified contact for a listing. Opening a
request does not prove ownership or employment. A maintainer verifies one of
three evidence paths before marking a contact as verified:

- confirmation on an agency-controlled public webpage;
- a one-time proof file or text at the public feed host; or
- a private reply from an official agency email domain.

Do not publish private email addresses, access tokens, or credentials in an
issue. Until evidence has been reviewed, the request remains **unverified**.
Verification confirms the contact's relationship to the listing. It does not
endorse the grade, override the rubric, or prevent other people from reporting
errors. Registry changes still go through a reviewed pull request so the public
record shows what changed and why.

## Long-expired feeds

A feed whose calendar ran out over a year ago is shown in its own group on the
directory, separate from the recently lapsed ones. Two cases hide in that group,
and we tell them apart by hand rather than by the grade:

- **The agency still runs and the export lapsed.** A curator can record this with
  an `operating_note` in the relevant [registry shard](../registry/README.md)
  after confirming the
  service still operates. The scorecard and directory then show the verified note,
  so the feed reads as recoverable rather than defunct.
- **The service genuinely ended.** When an agency has stopped operating, the entry
  is retired or retained only as a noncurrent alias, and is excluded from
  future catalog runs. Its current scorecard, badge, conformance files, and map
  are removed. Date-stamped score records may remain as historical evidence;
  they are not presented as the agency's current condition. We do not leave a
  permanent failing grade on an agency that no longer exists.

## Feeds we could not read

The rules above are about agencies. This one is about the tool.

Sometimes a feed downloads fine and still cannot be measured: its `stops.txt`
and `trips.txt` hold a header row and nothing else, the archive contains no GTFS
tables at all, or our own reader cannot find the tables inside it. There is no
grade to give in that case. A letter would be a claim about data nobody read.

So we do not publish one. The listing is **withdrawn**: its current scorecard,
badge, conformance file, and map are removed, and the agency drops out of the
directory, the rollups, and the change feed. Its dated score records stay
exactly where they are, because they are evidence of what we published and when.
The registry entry stays too, marked `feed_status: inactive`, with a comment
naming what we measured, on what date, and what would restore the listing.

Three things this is not:

- **It is not a judgment about the agency.** These agencies mostly still run
  buses. Only the feed could not be read, and sometimes the reason is a bug on
  our side, in which case the comment says so and names the issue.
- **It is not a failing grade, and it is not a zero.** A withdrawn listing has
  no letter and no score. The published page is gone rather than emptied, so
  nothing downstream can read a missing grade as an F or a missing score as a
  regression.
- **It is not permanent.** Withdrawal is one line in the registry. When the feed
  reads again, a curator deletes that line and the next run publishes a real
  grade from real data.

A feed whose data we *can* read is never withdrawn on this rule, however bad it
looks. A feed with stops and trips whose calendar lapsed years ago still scores
zero on freshness and still says so: that is a measurement, and hiding it would
defeat the point of the tool.

The registry is curated, so every entry can be reviewed, corrected, or removed
by a person. If something here is wrong or unwelcome, that is a bug, and we want
to fix it.
