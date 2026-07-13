# 0030: Extract site identity into `instance.yaml`; ship a fork quickstart

Status: accepted (2026-07)

## Context

EXP-15 (`docs/ideation/03-expansions.md`) asks for the scorecard to be a
reproducible "stand up your own scorecard" template: a state DOT, a national
RTAP, or a country program should be able to run its own branded instance from
config and a deploy, without a code change, converting the single-maintainer
sustainability risk `docs/roadmap.md`'s Year 3 white-label plan names into a
distributed one.

The registry half of that is already done: the manifest-backed `registry/`
(Phase 4) lets any
agency be added with a YAML block, and `docs/deploy.md` already documents
fork-specific infrastructure variables (`ARTIFACTS_CDN` vs. the maintainer's
default CDN, for example). What was still hardcoded was the site's public
identity: the canonical base URL (`https://gtfsscorecard.org`), used in over
80 call sites across `render_site.py`, `atomfeed.py`, `alerts.py`,
`liveness.py`, `mcp_server.py`, `notify.py`, and `onboard.py`; the display
name and organization name embedded in JSON-LD, the Atom feed author, and the
data attribution string; and the contact address.

EXP-15's own write-up names a real prerequisite this decision does not
attempt: making the *rubric* pluggable per region (RR:E11) is a separate,
larger piece of work, because the Caltrans v4.0 realtime thresholds in
`rt.py` and the freshness lead time in `metrics.py` are woven into the
scoring math itself, not surface-level config. Treating that as done here
would either be a shallow stub (a config field nothing reads) or a risky,
undertested rewrite of the scoring core in the same change as a branding
extraction. Both are worse than being honest about the boundary.

## Decision

Extract *identity*, not the rubric, in this pass:

- `pipeline/src/scorecard_pipeline/instance.py` defines `InstanceConfig`
  (`base_url`, `site_name`, `org_name`, `contact_email`, `tagline`) loaded
  from `instance.yaml` at the repo root, field-by-field, with every field
  defaulting to the maintainer's production value when the file or field is
  absent. The upstream repo ships with no `instance.yaml`, so its behavior is
  byte-for-byte unchanged.
- Every module that previously hardcoded `"https://gtfsscorecard.org"` or
  `"GTFS Scorecard"` for a URL, generator tag, user agent, or JSON-LD
  publisher name now imports from `instance.py` instead (`site_shell.py`
  re-exports `BASE_URL` so `render_site.py`'s existing import keeps working).
- `instance.example.yaml` is the fork's copy-and-edit template.
- `docs/fork-quickstart.md` is the "run your own" guide EXP-15's Shape section
  asks for: fork, edit `registry/` and `instance.yaml`, deploy via the
  existing `docs/deploy.md` runbook, with an explicit section on what stays
  shared (the rubric) and why.

Rubric pluggability (RR:E11) stays a named follow-up, not a silent gap: both
`instance.py`'s module docstring and the quickstart guide say directly that a
fork is scored on the same shared rubric today, and point at this ADR and
EXP-15 for the work that would change that.

## Consequences

- A fork can rebrand the site's canonical URLs, feed metadata, and JSON-LD
  publisher fields by editing one YAML file, no code change, satisfying the
  core of EXP-15's excellence bar for identity.
- The rubric stays a single shared, versioned methodology
  (`RUBRIC_VERSION`) across every instance until RR:E11 ships, which is the
  conservative default EXP-15 itself argues for: "must not fragment the
  methodology."
- `docs/deploy.md`'s existing fork-awareness (`ARTIFACTS_CDN`, etc.) and this
  identity layer are two independent pieces a fork configures; the quickstart
  guide is the single entry point that sequences both.
- Not done here, left for a follow-up if an external adopter actually
  materializes (this item's own priority is "Later — needs external
  adopters"): a pluggable region rubric profile, translating the remaining
  narrative UI copy that says "GTFS Scorecard" inline in page prose (as
  opposed to the JSON-LD/feed metadata this change wires), and any billing or
  multi-tenant concerns a real white-label offering would raise.
