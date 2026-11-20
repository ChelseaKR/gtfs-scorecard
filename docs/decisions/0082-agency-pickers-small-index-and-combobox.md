# ADR 0082: Agency pickers read a small index and open the agency page

**Status:** Proposed (2026-11-19). Built on a branch; the new reader-facing
wording waits for the maintainer's approval before merge.

## Context

Two places ask a reader to pick an agency by name.

- The home page search ("Find a published feed") listed matches as buttons,
  and choosing one loaded that agency into the example card further down the
  home page. People who searched for their agency expected to land on its
  page. The search read `api/v1/ids.json`, which carries every feed URL the
  picker never shows.
- The alerts form (`/subscribe.html`) filled a `<select>` from
  `data/artifacts/index.json`, the full per-agency history index: 2.8 MB
  compressed and 84 MB unpacked in production, parsed in the browser to list
  about 2,500 names. Its first option, and so its default, was "All agencies",
  so a form sent before the list finished loading followed every feed.

## Decision

- **One small index.** The site render writes `data/agency-index.json` from the
  same catalog records as the directory and `ids.json`
  (`pipeline/src/scorecard_pipeline/agency_index.py`). Each row is
  `[id, name, slug, place]`, compact, sorted by id. `slug` is the page path
  segment (`/agency/<slug>/`, today always the id); `place` is the
  subdivision name, else the country code, and tells apart feeds that share a
  name. It carries no score, so it cannot be misread as a grade. The full
  corpus comes to about 250 KB, roughly 50 KB gzipped. It is fetched the first
  time someone types, not with the page, and the HTTP cache and the service
  worker keep it after that.
- **One combobox.** `web/src/agency-combobox.js` implements the WAI-ARIA 1.2
  combobox pattern with a listbox popup: focus stays in the text field,
  `aria-activedescendant` names the active option, Up and Down move, Enter
  chooses, Escape closes, and a polite live region says how many agencies
  match. Both pages use it. It holds no English of its own: every message
  comes from `data-msg-*` attributes on the page, so wording is reviewed with
  the rest of each page.
- **Matching.** Case, accents, apostrophes and other punctuation are ignored,
  and "&" reads as "and". Abbreviations agencies carry in parentheses count
  as exact names, so "BART" ranks Bay Area Rapid Transit above BARTA. Words
  match by prefix in any order, and the feed id matches too.
- **The home search goes to the agency page** when the reader chooses a
  suggestion, or presses Enter on text that clearly names one agency: its full
  name, its name without the parenthetical, its abbreviation, its feed id, or
  the only agency that matches at all. A name two feeds share is never a clear
  match. Everything else keeps going to the results list at `/app/#/?q=`, and
  without JavaScript the form submits to `/app/` as before. Arrow keys never
  navigate; only Enter, a click or the Find button does (WCAG 3.2.2).
- **The alerts form has no default agency.** "All agencies" is still offered,
  as the first suggestion when the field is empty or the reader types "all",
  but sending with nothing chosen is an error that moves focus to the field.
  Text that clearly names one agency counts as choosing it. A link with
  `?agency=<id>` (the "Watch this feed" link on each agency page) opens with
  that agency chosen.

## Consequences

- The alerts page no longer downloads the history index, and the home page no
  longer downloads the feed-URL crosswalk to suggest names.
- One more generated file. It is rebuilt on every render, so it can only list
  agencies that have a page, and `test_agency_index.py` holds the committed
  copy to the committed catalog.
- Without JavaScript the alerts form still cannot send (the API takes JSON
  only); the agency field degrades to a labeled text box. A server-side form
  post is a separate infrastructure change and is not part of this decision.
