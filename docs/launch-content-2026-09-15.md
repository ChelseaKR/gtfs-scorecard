# Launch content — Product Hunt, Show HN, subreddits (drafted 2026-09-15)

Status: **draft only**. Nothing here has been posted anywhere, and no account
was created on any platform to write it. See "How to post" at the end for
what a human still has to do.

## Why this file exists (and why it isn't the old one)

A prior draft (`docs/launch-content-2026-09.md`, PR #440) was written on
2026-09-14. Its PR was closed without merging. This is a fresh draft, not a
copy — three real things shipped to `main` *after* that draft was written and
change what's worth saying:

- **Real branding** (PR #443, merged 03:47 UTC): the site had a two-tone
  inline-SVG placeholder favicon and no `apple-touch-icon` at all. It now has
  a real mark (a route line with two stops, bent into a checkmark), a proper
  favicon set, and a `/bundle/`-specific OG/Twitter card
  (`bundle-og.png`, 1200×630) instead of sharing the homepage's image.
- **Trust and refund terms on the purchase path** (PR #444, merged 03:46
  UTC): `/bundle/`'s FAQ now states the delivery commitment and the refund
  condition as terms, not marketing copy — quoted exactly below. This is not
  a separate "trust" page; it lives in `/bundle/`'s own FAQ block.
- **A CLI command that shows the exact arithmetic behind a grade** (PR #381,
  `scorecard explain`, merged 03:47 UTC): this is new since the last draft
  and is a genuinely good Show HN hook — see §2.
- **A reliability fix to the daily pipeline** (PR #445, merged 03:46 UTC):
  the nightly refresh job could lose an entire cycle's worth of already-
  completed rescoring to its own timeout; that's fixed, and the diagnosis
  is public in the PR.
- **The feed registry grew to 2,671 records** (reviewed 2026-09-14 sync
  pass, 28 new US feeds across 20 states, including Wyoming's first tracked
  feed). This is a live, verified number, not carried over from the old
  draft — see the grounding note below.

Grounding for every number and claim below: `web/bundle/index.html`,
`web/bundle/plan.json`, `README.md`, `CHANGELOG.md`'s `[Unreleased]` section,
the relevant merged PRs (#381, #443, #444, #445), and the **live site**,
checked 2026-09-15 including a direct fetch of
`https://gtfsscorecard.org/api/v1/coverage.json` (the same endpoint the
homepage's own JS reads for its counters):

```json
{
  "configured_feed_records": 2671,
  "published_scorecard_pages": 2451,
  "country_count": 48,
  "active_canonical_feed_records": 2498
}
```

This draft uses **"2,671 curated feed records"** (exact — it's tonight's
actual number and the newsworthy one), **"2,400+ published scorecards"**
(rounded down from the live 2,451 so the claim stays true as the pipeline
runs daily and the count moves), and **"48 countries"** (the live, exact
figure — up from the "40+" figure the previous draft used, which was
already stale by the time it was written; the checked-in HTML's static
fallback text still says "2,100+"/"40+", but that's a pre-JS fallback, not
what a visitor's browser actually renders). Nothing here states a GitHub
star count, a user count, a revenue number, or a testimonial — none of
those exist yet (the repo has 1 star; the bundle has zero recorded sales),
so none are claimed.

---

## 1. Product Hunt listing

**Tagline** (57 chars):
> Free GTFS grades that show their work. Paid board bundle.

**Gallery images** (5 — specify only, nothing generated here; two of these
are new assets that didn't exist for the last draft):

1. **The hero shot: one agency's live scorecard.** Screenshot of
   `gtfsscorecard.org/agency/unitrans/board/` (the real, public Unitrans
   board one-pager) — overall grade, the four category scores, and the
   "top 3 things to fix" list in plain language. Still the single image
   that has to sell the free tool in one glance.
2. **The math, not just the grade.** Terminal screenshot of
   `scorecard explain data/artifacts/<agency>/<date>.json` output — the
   per-notice deduction list, the weighted sum, and the line that either
   confirms the published number reconciles or says exactly how far off a
   naive recomputation lands and why. This is new since the last draft and
   is the single best "we're not hiding anything" image the project has.
3. **The bundle page, now with its own identity.** Screenshot of
   `gtfsscorecard.org/bundle/` showing the four plans ($149 / $349
   one-time, $49/mo or $490/yr refresh) and the FAQ's delivery/refund
   terms ("normally within the hour, always within two business days; if
   it's later, the purchase is refunded"). Use the page itself, not the new
   `bundle-og.png` card, so the real FAQ text is legible.
4. **Coverage, not a toy.** Screenshot of `/pulse/` or `/status/` showing
   registry scale (2,671 curated feed records, 48 countries) and the
   public run history — establishes this runs on real, current data on a
   visible cadence, not a demo dataset that quietly stopped updating.
5. **The real mark, in context.** Browser-tab screenshot showing the new
   favicon/tab title next to a couple of other tabs, or the new
   `bundle-og.png` card as it renders in a link preview (e.g., pasted into
   Slack or iMessage). Small detail, but "does this look like a real,
   finished product" is exactly the first-impression question a PH visitor
   is unconsciously asking, and until tonight the honest answer was "not
   quite."

**Full description:**

> GTFS Scorecard grades a transit agency's published GTFS feed — the data
> file that powers Google Maps, Transit App, and every other trip planner —
> for quality and rider-information gaps. It's free, for any agency, at
> gtfsscorecard.org.
>
> A small transit agency usually gets its GTFS export from a scheduling
> vendor and has no way to know if it's any good. The most common failure
> is quiet: the feed silently expires and trip planners drop the agency, so
> riders are told the service doesn't exist. GTFS Scorecard runs the
> canonical MobilityData validator against a feed, then turns the result
> into an overall grade, four category scores (correctness, freshness,
> rider-experience completeness, realtime quality), and a "top 3 things to
> fix" list in plain language — not a wall of validator error codes.
>
> New tonight: a `scorecard explain` command that prints the exact,
> deduction-by-deduction arithmetic behind any published grade — every
> point lost, every weight applied, and an honest accounting of anything
> that doesn't perfectly add up rather than a number that's quietly
> rounded away. "Reproduce or contest the grade" has been the project's
> stated ethos since the rubric doc was written; now there's a command
> that actually lets a reader do the second half.
>
> It currently tracks 2,671 curated feed records and 2,400+ published
> scorecards across 48 countries, rescored daily, with a public status
> page showing exactly what ran and when. It's open source (Apache 2.0),
> has a read API, a GitHub Action that can gate a build on a feed's grade,
> and an MCP server for agent-based workflows. None of that costs anything,
> and it stays that way — nothing was carved out of the free tier to make
> room for a price.
>
> The one thing that is paid: a **Program Report Bundle** for the people
> who support *many* agencies at once — state DOT programs, technical
> assistance centers, feed vendors, consultancies — who need every agency's
> board-ready report packaged into one branded archive instead of opening
> each agency's page by hand. $149 for up to 25 agencies, $349 for up to
> 100, one time, with an optional $49/mo or $490/yr refresh once you've
> bought a bundle. Delivery is normally within the hour and always within
> two business days — if it's later than that, the purchase is refunded,
> as a stated term, not a best-effort promise. A purchase changes nothing
> about how an agency is scored: methodology, weights, and which agencies
> are listed aren't for sale, and an agency's own report is always free.

**"What's new" hook** (for the first-launch post itself, not a follow-up
update — PH expects this field to say why *today*):

> First public launch. The scorecard itself has been running and scoring
> real feeds daily for months; today's the first time it's being shown
> outside GitHub and search traffic. In the last day: real branding
> replaced a placeholder favicon, the purchase page got explicit refund
> terms, the registry grew by 28 reviewed feeds (2,671 total, 20 states,
> Wyoming's first), and a new `scorecard explain` command started printing
> the exact arithmetic behind every published grade. The paid program
> bundle is new too — built, live, and taking its first orders.

**First comment (maker's comment, post immediately after launch):**

> Hi — I'm the solo builder here (Chelsea). A quick honest note on why this
> exists and how it's put together, since PH is usually the first time
> anyone outside GitHub sees it.
>
> I built the scorecard starting from the transit systems in Davis, CA
> (Unitrans and Yolobus), because I kept noticing that "is our GTFS feed
> okay" is a question small agencies genuinely can't answer for themselves.
> They get an export from whatever scheduling software they use, and the
> official validators are thorough but built for engineers, not for a
> transit manager at a 20-bus agency. So the tool runs MobilityData's
> canonical validator (I'm not reimplementing GTFS validation — that would
> be a waste of everyone's time) and translates the result into a grade and
> three plain-language things to fix, the way you'd explain it to someone
> during a five-minute call.
>
> The thing I'm most glad landed before this launch: a command
> (`scorecard explain`) that shows the exact math behind any grade this
> tool publishes — every deduction, every weight, and a plain statement
> when something doesn't perfectly reconcile instead of a number that
> quietly gets rounded into place. A published grade someone can't check
> for themselves isn't worth much more than an opinion.
>
> Everything above the fold — every agency's scorecard, the board one-pager,
> the fix list, the API, the GitHub Action, the open dataset — is free and
> stays free. The only thing I'm charging for is a packaging convenience:
> a state program or vendor who supports 25–100 agencies can buy one branded
> archive of everyone's board report instead of opening each agency page by
> hand. It doesn't touch scoring in any way — I was deliberate about that,
> because the moment paying changes a grade, the whole project stops being
> trustworthy.
>
> It's a side project I maintain alone, it's Apache-2.0, and corrections /
> agency additions go through a public repo. Happy to answer anything about
> the rubric, the validator integration, the explain command, or why a
> paid tier exists on top of an open-source tool at all — genuinely welcome
> the skepticism on that last one.

---

## 2. Show HN

**Title** (HN format, terse, 68 chars incl. "Show HN: ", under HN's 80-char
limit):
> Show HN: GTFS Scorecard – grades transit feeds, shows its arithmetic

**Body:**

> GTFS Scorecard runs the canonical MobilityData `gtfs-validator` against a
> transit agency's published GTFS feed and turns the result into a grade,
> four category scores, and a "top 3 things to fix" list in plain language,
> instead of a raw list of validator notices. Free, no login, live at
> https://gtfsscorecard.org.
>
> Why I built it: GTFS (the format behind Google Maps transit directions,
> Transit App, etc.) is usually exported by a scheduling vendor, and small
> agencies have no real way to tell if their export is any good. The
> classic failure mode is silent — a feed's service calendar expires and
> trip planners just stop showing the agency, with no error visible to
> anyone at the agency. Started from the two transit systems in my own
> town (Davis, CA — Unitrans and Yolobus) and it grew from there; it now
> tracks 2,671 curated feed records and 2,400+ published scorecards across
> 48 countries, rescored daily.
>
> What might be interesting to this audience:
>
> - **`scorecard explain <artifact.json>`** is the thing I'd most want
>   feedback on. It reads one published scorecard artifact and reconstructs
>   the exact deduction-by-deduction arithmetic behind its grade — every
>   point lost, every category weight, the weighted sum. It refuses
>   (exit code 2, not 1) rather than approximate: handed an artifact scored
>   under an older rubric version, it won't apply today's weights to
>   yesterday's score. And it reports residuals honestly — on the current
>   corpus, ~1.66% of artifacts have a published overall score that a
>   reader can't reconstruct to the last decimal from the published category
>   scores (rounding — each category is published to one decimal, so the
>   sum can drift by half a step), and it says so rather than silently
>   reconciling. One older-rubric artifact even crosses a letter-grade band
>   under naive recomputation — the tool correctly refuses to touch it
>   rather than report a wrong "fix." Writing the module to admit this
>   instead of hiding it felt like the actual interesting engineering
>   problem, more than the arithmetic itself.
> - It deliberately doesn't reimplement GTFS validation. It shells out to
>   MobilityData's validator (the same one transit agencies and state DOTs
>   already use) and adds the scoring/trend/plain-language/explain layer on
>   top — the validator is the ground truth, this project is a lens on it.
> - The whole pipeline runs on a daily sharded GitHub Actions matrix rather
>   than a persistent server: no Lambda, no Fargate, no always-on compute.
>   The frontend is static and reads only precomputed JSON artifacts — no
>   API server, no database. It's boring on purpose; an ADR in the repo
>   (`docs/decisions/0001-validator-runtime.md`) has the reasoning. I also
>   just finished diagnosing and fixing a real reliability bug in that
>   pipeline (a shared concurrency group was silently evicting a queued job
>   under load) — the PR with the full incident writeup is public, because
>   I'd rather show the debugging than pretend it never broke.
> - There's a public `/status/` page that reports what the last run
>   actually did — shard outcomes, which feeds it couldn't reach, how stale
>   the catalog is — rather than just asserting "refreshed daily" and
>   hoping nobody checks.
> - It's WCAG 2.2 AAA by rule, not aspiration — the audience (state transit
>   staff, accessibility reviewers) actually checks, so it has to hold up.
> - There's a read API, a GitHub Action that can fail a CI build on a
>   feed's grade or an approaching expiry, and an MCP server, all
>   documented in the repo.
>
> It's open source (Apache 2.0): https://github.com/ChelseaKR/gtfs-scorecard
>
> I'll say upfront: there's a small paid add-on for state programs and
> vendors that support many agencies at once (a branded archive of every
> agency's board report, instead of opening each agency's page one at a
> time) — everything a single agency or a rider touches stays free, and
> the paid tier has zero influence over scoring. Mentioning it here because
> I'd rather be upfront about it than have someone find it and wonder why
> it wasn't disclosed.
>
> Happy to talk about the scoring rubric, the explain command's residual
> handling, the validator integration, the Actions-based architecture, or
> where the accessibility work has and hasn't held up. It's a solo side
> project, so there's plenty still rough — feedback and "this is wrong"
> reports both welcome.

---

## 3. Subreddits

Reddit's live site was unreachable to this session's fetch tooling
(`www.reddit.com/r/*/about/rules.json` returned a tool-level fetch error,
same as the previous drafting attempt), and web search turned up only
third-party SEO/marketing aggregator pages rather than the subreddits' own
current sidebar or wiki text — none of them treated as authoritative here.
So, as before, the rules below are drawn from each community's
long-standing, well-documented norms, not a same-day rules pull.
**Before posting, reread each subreddit's current rules/wiki directly —
they can and do change, and a stale rules-read is the #1 way an honest
post gets removed as spam.**

Ranked by risk, lowest first:

### 1. r/SideProject — **low risk**

General maker community; self-promotion is the stated purpose of the sub.
Draft:

> **GTFS Scorecard — free, open-source quality grades for transit data
> feeds, now showing the exact arithmetic behind every grade**
>
> What it is: a tool that grades a transit agency's published GTFS feed
> (the data format behind Google Maps transit directions) for data quality
> and turns the result into a plain-language grade and "top 3 things to
> fix." Free for any agency, no login. New this week: a CLI command that
> prints the deduction-by-deduction math behind any published grade,
> including an honest "this doesn't perfectly reconcile, here's why"
> instead of quietly rounding a gap away.
>
> Why I built it: started from the two transit agencies in my own town
> (Davis, CA), because small agencies get a GTFS export from a vendor and
> have no way to check if it's good — the failure mode is silent, the feed
> just expires and trip planners quietly drop the agency.
>
> Stack/build notes: Python pipeline that shells out to MobilityData's
> canonical validator rather than reimplementing it, runs daily on a
> sharded GitHub Actions matrix (no server), static frontend that reads
> precomputed JSON. Apache 2.0, open repo.
>
> What's paid: one add-on aimed at state DOT programs / vendors who
> support many agencies — a branded archive of every agency's board report
> in one purchase instead of visiting each agency page. $149–$349
> one-time, with clear delivery/refund terms on the purchase page. Doesn't
> touch scoring. Zero recorded sales so far — it launched quietly and this
> is genuinely the first time I'm showing it anywhere.
>
> Live: gtfsscorecard.org. Feedback very welcome, especially "here's a
> transit-data thing you got wrong."

### 2. r/opensource — **low-medium risk**

Dedicated OSS-project community; self-promo tolerated for genuine, licensed
open-source projects. Draft:

> **GTFS Scorecard (Apache 2.0) — turns transit agencies' raw GTFS data
> quality into plain-language grades, with a command that shows its work**
>
> Open-sourced under Apache 2.0: https://github.com/ChelseaKR/gtfs-scorecard
>
> It wraps MobilityData's canonical `gtfs-validator` (doesn't reimplement
> GTFS validation) and adds scoring, trend history, and a plain-language
> "top 3 things to fix" layer aimed at transit agency staff who aren't
> developers. A new `scorecard explain` command reconstructs the exact
> arithmetic behind a published grade from the artifact alone, and refuses
> (rather than guesses) when handed a score from a rubric version it
> doesn't carry constants for.
>
> Runs entirely on a daily GitHub Actions matrix — no server, static
> frontend reading precomputed JSON artifacts only. Ships a read API, a
> GitHub Action, and an MCP server.
>
> There's one paid add-on layered on top (a branded multi-agency report
> archive for state transit programs) that doesn't touch any of the core
> tool or its output — mentioning it here for transparency, not as the
> pitch. Looking for feedback on the codebase, the rubric, and the explain
> command's approach to unreconciled scores more than anything else.

### 3. r/transit — **medium risk — frame as findings, not a pitch**

Transit enthusiasts, advocates, some professional planners; large,
topically perfect audience, but the mods are known to remove anything that
reads as a pure ad rather than a discussion. Lead with something the
scoring surfaced, not with "check out my tool," and don't mention the paid
bundle at all in this one — it's aimed at planners/vendors, not this
audience, and bringing up a price here raises the ad-read risk for no
benefit. Draft:

> **I scored 2,671 transit agencies' published GTFS feeds for data
> quality — here's what silently breaks most often**
>
> Side project: I built a scorecard that runs MobilityData's GTFS validator
> against public transit feeds and grades them on correctness, freshness,
> rider-experience completeness (wheelchair boarding data, fares, stop
> names), and realtime quality where available. It started from the two
> agencies in my hometown (Unitrans and Yolobus, Davis CA) and grew into
> tracking 2,671 curated feed records across 48 countries, rescored daily
> (most concentrated in the US and Canada; it's not a census).
>
> The most common failure I see isn't a malformed file — it's a feed whose
> service calendar quietly expires, so Google Maps and other trip planners
> just stop showing the agency's service with no visible error to anyone
> at the agency. Small agencies running on a vendor export have basically
> no way to catch this themselves.
>
> It's free, open source, and I'd genuinely like this community's eyes on
> the rubric (`docs/rubric.md` in the repo) since a lot of you either work
> in this space or ride the systems being graded. gtfsscorecard.org if
> you want to look up your own agency.

### Consider only via the subreddit's own low-risk mechanism

**r/webdev** — has a long-running weekly **"Self-Promo Saturday"**
megathread; post as a comment there rather than a standalone submission.
Fit is weaker (this reads as a data/civic-tech tool more than a web-dev
tool), so treat as optional/lower-priority, but the megathread format
makes it essentially risk-free if used correctly (comment only, on the
right day, not a new post). Comment draft (short, matches thread norms):

> **GTFS Scorecard** — gtfsscorecard.org. Open-source (Apache 2.0) tool
> that grades transit agencies' published GTFS data feeds for quality and
> turns validator output into plain-language fixes, now with a CLI command
> that shows the exact arithmetic behind any published grade. Static
> frontend, no backend server — daily GitHub Actions pipeline writes
> precomputed JSON, site just reads it. Read API + GitHub Action + MCP
> server if anyone's curious about the integration side. Feedback welcome.

### Considered and dropped

- **r/urbanplanning** — dropped. It's a professional/academic community
  with a track record of removing unsolicited tool or product posts,
  including free ones, unless they're framed as research or come from an
  established contributor. The topic fit is real (GTFS quality is a
  planning concern), but the risk of a fast removal — and of it reading as
  spam from a first-time poster — outweighs the upside. If Chelsea wants
  this audience, the safer path is answering an existing thread about GTFS
  or transit data quality with a genuine, tool-mentioned-in-passing answer,
  not a submission.
- **r/OpenTransit** — does not appear to exist as an active subreddit (no
  hits in search, and a third-party subreddit-stats lookup returned a
  clean 404 rather than a page). Dropped rather than guessed at.
- **r/SaaS / r/microsaas** — considered and dropped for this launch. Both
  skew toward SaaS-growth/marketing discussion rather than the civic-data
  or open-source angle, the audience has near-zero transit-agency overlap,
  and the entire point of this product is that it's a niche B2G/B2B tool —
  a generic SaaS-growth audience is unlikely to be a real buyer and more
  likely to read the "$149 one-time" framing as a toy compared to what
  that sub usually discusses. Not worth the post.

---

## 4. How to post (none of this has been done)

I did not create an account anywhere, and did not submit or post anything.
Before any of the above can go live, a human (Chelsea) needs to, in roughly
this order:

1. **Product Hunt**: create an account (email or GitHub/Google sign-in),
   verify the email. New PH accounts can self-launch (no "hunter" required
   any more), but a completely fresh account with zero history reads as
   lower-trust to PH's own ranking — if there's an existing PH account
   already, use it. Launches typically go live at 12:01 AM PT, and PH
   expects the maker to be present in the comments for the first several
   hours, so pick a day Chelsea can actually be online.
2. **Hacker News**: create an account, verify email if prompted. No
   minimum karma is required to submit a Show HN, but a brand-new account's
   first post can sit unseen in the `/newest` queue if it gets no early
   upvotes — worth having 2–3 people who'd genuinely be interested know the
   post is going up, so it isn't purely relying on cold discovery. Submit
   as Show HN with the title/body above.
3. **Reddit**: create or use an existing account. Several of the
   subreddits above (notably r/transit) are more forgiving of accounts
   with some pre-existing genuine post/comment history than of a
   brand-new account's first-ever post being self-promotional — if
   starting from scratch, spend a little time commenting genuinely in
   r/transit or r/SideProject before posting, rather than posting cold.
   Re-verify each subreddit's current rules immediately before posting,
   per the note in §3.
4. Decide a **posting order and spacing** — these channels' audiences
   overlap (HN and PH both get cross-posted by aggregators, and
   r/SideProject regulars often also read PH), so launching all of them in
   one day is fine, but note that a Show HN and a PH launch on the exact
   same day can look like they're feeding off each other's momentum.
   Either is normal; just make it a deliberate choice, not an accident.
5. None of this needs anything from the gtfs-scorecard repo itself — no PR
   from this doc has to merge before posting starts. This file is a
   drafting artifact, not a dependency.

## Note on the prior draft (PR #440)

For the record, since it's directly relevant to why this file exists: the
branch behind PR #440 (`docs/launch-content-2026-09`) is **not actually
gone**. `git ls-remote origin refs/heads/docs/launch-content-2026-09` still
resolves, and the PR (closed, not merged, 2026-09-14 23:44 UTC) is still
viewable at github.com/ChelseaKR/gtfs-scorecard/pull/440. Its content
predates all five of the changes listed at the top of this file, which is
the substantive reason this is a fresh draft rather than a resurrection of
that one — not the (incorrect) premise that the old content had been
deleted. Worth closing the loop on whether that branch should be deleted
now that this one supersedes it.
