# Self-hosted interface fonts

The public site serves three Latin variable-font subsets locally so the roadway-signage
identity does not depend on a third-party font request:

- `overpass-latin.woff2` — Overpass 400–900
- `overpass-mono-latin.woff2` — Overpass Mono 400–700
- `public-sans-latin.woff2` — Public Sans 400–700

The WOFF2 files are the Google Fonts web builds of the upstream open fonts. Overpass is
maintained by Red Hat; Public Sans is maintained by the U.S. Web Design System. Both are
used under the SIL Open Font License 1.1. The applicable upstream license texts are kept
beside the font files.

The subsets cover Latin and common punctuation. CSS fallbacks remain in place for any
character outside that range.
