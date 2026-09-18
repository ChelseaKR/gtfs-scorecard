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

Reuse terms are part of what is listed. `scorecard license-audit` reports the
licence each record's note names. When it shows a listed record whose terms
the project does not list, acting on that is a listing decision taken under
this policy, not a curation edit to the record's note.

## Privacy

The public scorecard uses two measurement tools. PostHog counts page views and
one further event, a click on a checkout link on the bundle page. It sets no
cookie, keeps no identifier past the current browser tab, reads nothing a
visitor types, and builds no rider or visitor profile. Google Analytics 4
records page views and how a page is used (time on page, scrolling, links
followed to other sites, file downloads), with the page's query string and the
referrer's path dropped. Outside the EEA, the UK and Switzerland it sets the
`_ga` cookies, which last up to two years; inside them it sets no cookie.
Google signals and ad features are off, and Google keeps the event-level data
for 14 months. The full statement of what is recorded, where it goes, how long it is
kept, and how to opt out is on the site at
[gtfsscorecard.org/about/#privacy](https://gtfsscorecard.org/about/#privacy).
The script that loads both is `web/src/measure.js`, the decisions are
[ADR 0055](decisions/0055-cookieless-site-measurement.md) and
[ADR 0056](decisions/0056-google-analytics-4.md), and Global Privacy Control or
Do Not Track switches both off. Site-quality checks use automated
synthetic visits instead of observing real visitor sessions.

Until 2026-09-13 the site recorded nothing about a visit at all. That rule
was withdrawn on that date, and Google Analytics 4 was added on 2026-09-17;
this section and the site say what replaced it.

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

## Grades we have taken back

A grade is only as good as the data behind it. When we find that a published
grade was computed from an archive we never actually read, we withdraw it and
say so, rather than replacing the number quietly or leaving the page to
disappear. The [corrections page](https://gtfsscorecard.org/corrections/) lists
every withdrawn grade with what it said, how long it was public, why it was
wrong, and what stands in its place. The machine-readable record is
`corrections.yaml` at the repository root, and it is reviewed in a pull request
like any other change.

Where the feed can be read, the next successful run publishes a real grade and
the correction stays on record beside it. Where it cannot, the answer is that
the feed is not measured; we do not substitute a different number for one we
could not compute. Dated score records from the affected days remain available
as the historical record of what this project published, including when it was
wrong. They are not presented as an agency's current condition.

Nothing is required of an agency on that list.

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

The registry is curated, so every entry can be reviewed, corrected, or removed
by a person. If something here is wrong or unwelcome, that is a bug, and we want
to fix it.
