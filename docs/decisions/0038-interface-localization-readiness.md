# 0038. Interface-localization readiness without a production language

Date: 2026-07-17
Status: accepted

## Context

The roadmap gates full interface localization on a named language steward, and
that gate holds. But the engineering prerequisites named in
`docs/global-expansion.md` (externalized strings, a pseudolocale expansion
pass, a right-to-left pass) were still prose. The interactive app kept all of
its copy as inline literals, so a future steward would inherit a string hunt
before their first reviewed translation, and layout defects that only longer
translations expose stayed invisible.

## Decision

Build the readiness layer now, inside the existing catalog contract, and keep
production languages steward-gated:

- The interactive app's externalized strings live in
  `pipeline/src/scorecard_pipeline/locales/app.en.json`, a sibling of the
  reviewed rider catalog. `i18n.py` owns both contracts and fails closed on
  any other locale.
- `scorecard render-constants` renders the app catalog into
  `web/src/generated/strings.js`, the same generated-module pattern as
  `constants.js`, so production pages read catalog strings synchronously and
  the committed module cannot drift (drift test in
  `tests/test_generated_constants.py`).
- A deterministic `en-XA` pseudolocale is derived from the English catalog on
  demand (never stored, so it cannot drift): accented letters, placeholder
  tokens preserved, at least forty percent expansion inside visible ⟦…⟧
  markers. It is published only as `web/locales/app.en-XA.json` and loaded
  only when a page is opened with `?l10n=en-XA`. Any failure leaves the page
  in reviewed English.
- Browser tests (`tests/e2e/test_locale.py`) assert that the preview expands
  catalog-rendered strings without horizontal overflow, that an unsupported
  preview tag stays plain English, and that a rendered route holds
  right-to-left direction without overflow.
- Two exact-baseline ratchets (`tests/test_l10n_readiness.py`) keep the debt
  visible and shrinking: a count of English-looking string literals per
  `web/src` module, and a count of directional physical CSS properties in
  `styles.css`. Raising either number is a reviewed decision.

The first externalized surface is the app shell: loading state, fetch errors,
the error and not-found boxes, and the compare-picker validation message. The
remaining literals are enumerated by the ratchet baseline and move in bounded
follow-ups.

## Consequences

- A future language steward starts from a working catalog pipeline: add a
  reviewed `app.<locale>.json`, extend the loader's allow-list, and the
  existing parity, placeholder, and browser gates apply to it.
- The pseudolocale preview gives reviewers a one-URL check that new layouts
  survive longer strings before any translation exists.
- The ratchets add friction to new hardcoded copy in the app. That is the
  point; catalog-first is now the cheaper path.
- Nothing changes for readers: production pages render the same English,
  synchronously, with no new network request.
