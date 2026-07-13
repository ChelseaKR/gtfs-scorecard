# Run your own scorecard: a fork quickstart

This is for a state DOT, a national RTAP, a regional program, or a country
program that wants this tool for its own agencies, under its own name and
domain — not for adding one more agency to the maintainer's public instance at
gtfsscorecard.org (for that, see
[docs/add-your-agency.md](add-your-agency.md)).

Because the system is static artifacts plus a stateless pipeline (no
database, no backend server), standing up your own instance is a fork, a
config edit, and a deploy — not a rewrite. Budget half a day for the steps
below; the excellence bar this quickstart is written against (EXP-15,
`docs/ideation/03-expansions.md`) is a correctly-cited, branded instance in a
day.

## What you get, and what you don't

**You get:** your own domain, your own agency registry, your own branding
(site name, organization name, contact address) in every page's metadata and
feed, and a daily-refreshed static site you host and own.

**You don't get (yet):** a different scoring rubric. Every fork scores
against the same shared, versioned methodology (`docs/rubric.md`,
`RUBRIC_VERSION` in `pipeline/src/scorecard_pipeline/__init__.py`) that cites
the California Transit Data Guidelines v4.0 and the MobilityData validator's
own rule taxonomy. If your program has different quality guidance you want
scored against, that is real, larger follow-up work (a pluggable region
rubric — see `docs/decisions/0030-forkable-instance-config.md` and RR:E11 in
`docs/RESEARCH-ROADMAP.md`), not something you can configure today. Two
consequences worth knowing going in: (1) findings will cite Caltrans/Cal-ITP
guidance by name until that work lands — accurate as the origin of the
threshold, but not your program's own guidance; (2) because the rubric is
shared, your instance's grades stay comparable to every other instance's,
which is deliberate — the alternative is silent methodology drift.

## Steps

### 1. Fork and clone

Fork `ChelseaKR/gtfs-scorecard` on GitHub, then clone your fork.

### 2. Set your agency registry

Replace the contents of [`registry/intake.yaml`](../registry/intake.yaml) with
your own agencies. For a clean fork, also remove the existing country
subdirectories and reduce [`registry/index.yaml`](../registry/index.yaml) to
list only `registry/intake.yaml`; the loader deliberately rejects unlisted
shards. As your registry grows, add your own country/subdivision shards back to
the explicit manifest. Each entry is documented in
[docs/add-your-agency.md](add-your-agency.md); `scorecard sync --country <cc>
--state <state>` can propose entries for a whole state or country from the
Mobility Database catalog instead of hand-entering each one:

```sh
cd pipeline
uv run scorecard sync --country US --state Washington
```

Review and commit the proposed entries rather than trusting them blind — the
tool proposes, it does not curate.

### 3. Set your branding

```sh
cp instance.example.yaml instance.yaml
```

Edit `instance.yaml` at the repo root: `base_url` (your domain), `site_name`,
`org_name`, `contact_email`, and `tagline`. Every field is independently
optional — set only what you want to change and leave the rest to inherit the
maintainer's defaults, though for a real fork you will want at least
`base_url`, `site_name`, and `org_name` set. This one file drives:

- Canonical URLs, `robots.txt`, `sitemap.xml`, and JSON-LD across every
  rendered page.
- The Atom change feed's author, generator tag, and entry-id tag authority.
- The data attribution string embedded in every published JSON artifact.
- The MCP server's default data source (`docs/mcp.md`) and the CLI's
  offline-preview link rewriting.

Commit `instance.yaml`. It is meant to be checked into your fork (like the
`registry/` directory), not kept as a local override.

**What this does not yet rebrand.** Page `<title>` tags, on-page prose (the
board one-pager's footer line, the press and procurement pages), and the
hand-authored marketing pages in `web/*.html` (the home page, `try.html`,
`submit.html`, `subscribe.html`) still say "GTFS Scorecard" literally in
several dozen places — that sweep is real follow-up work, not done in this
pass (`docs/decisions/0030-forkable-instance-config.md`). Search for `"GTFS
Scorecard"` across `pipeline/src/scorecard_pipeline/render_site.py`,
`pages_tools.py`, and `web/*.html` if you want to rebrand those too; each is
a literal string, safe to edit directly, just not yet threaded through
`instance.yaml`.

### 4. Deploy

Follow [docs/deploy.md](deploy.md). The short version: GitHub Actions plus
GitHub Pages runs the whole pipeline for free, which is how the maintainer's
own instance runs day to day. The optional AWS pieces (artifacts CDN, the
feed-health email digest, self-serve submission) are independent stacks you
apply only if you want them; `deploy.md` already calls out the Actions
variables a fork sets differently from the upstream default (for example
`ARTIFACTS_CDN`, so a fork with its own CDN doesn't inherit the maintainer's).

Point your domain's DNS at GitHub Pages (or your CDN, if you applied
`infra/artifacts`) and you're live.

### 5. Verify

- Run the pipeline once locally (`uv run scorecard run --all` from
  `pipeline/`, see the main `README.md`) and check a rendered agency page's
  view-source: the JSON-LD `publisher`/`creator` block should show your
  `org_name`, and the canonical `<link>`, `og:url`, and sitemap entries
  should show your `base_url` — not the maintainer's.
- Check `web/changes/feed.xml` after a render for your `site_name` in the
  `<author>` and `<generator>` tags.
- Check `pipeline/tests/test_instance.py` passes against your
  `instance.yaml` (`uv run pytest tests/test_instance.py` from `pipeline/`)
  — it validates the config loader, not your specific values, but is a quick
  sanity check that the file parses.
- Open a scored agency page and confirm the findings correctly disclose which
  guideline they cite (Caltrans/Cal-ITP today, per the scope note above).

## Staying current with the shared rubric

Because the rubric is shared and versioned (`RUBRIC_VERSION`), pulling
upstream changes into your fork periodically keeps your instance's grades
comparable to the reference instance's and to any other fork's. A rubric
version bump is the signal a trend on your instance reflects a methodology
change, not a feed change — the same signal `docs/rubric.md`'s "Governed
upgrades" section describes for the maintainer's own instance.

## Getting help

This is young: you are likely the first or an early external adopter. Open an
issue on the upstream repo (`ChelseaKR/gtfs-scorecard`) if something in this
guide is wrong or missing — that feedback is exactly what turns "Later" work
like the pluggable region rubric into something worth prioritizing.
