# Side-by-Side Scorecard Compare — Design & Implementation Path

**Status:** Phase 1 (MVP) implemented — `/compare/` ships from `render_site.py`
(`_render_compare_page`), with entry points on every agency page and in the site
footer. Implementation notes against this design: the pickers are plain selects in
a GET form (shareable URLs, no JS needed to choose), and the layout is one
accessible table (measure rows, one column per agency) rather than a CSS-grid
split, so the comparison reads correctly in a screen reader. Phases 2–3 below
remain future work.

## Motivation

Users want to compare two transit agencies side-by-side: "How does Agency A's realtime quality stack up against Agency B?" or "Which has better fare data, X or Y?" A user-selected comparison highlights actionable differences without publishing an absolute ranking.

## Design

### URL & Entry Points

- **URL:** `/compare/?a=agency-id-1&b=agency-id-2`
- **Entry points:**
  - Coverage or directory row: "Compare with …" context menu (select another agency)
  - Agency page: "Compare with another agency" link
  - Direct link (e.g., `/compare/?a=whitehorse-transit&b=barrie-transit`)

### Layout (Desktop-first, mobile-friendly)

```
┌─────────────────────────────────────────────────────────┐
│ Compare: Agency A vs. Agency B                    [←Back] │
├──────────────────────┬──────────────────────────────────┤
│   AGENCY A           │          AGENCY B                 │
│   Location: AK       │          Location: ON             │
│   Grade: A           │          Grade: B                 │
│   Score: 85.3        │          Score: 72.1              │
├──────────────────────┼──────────────────────────────────┤
│ CORRECTNESS     80   │  CORRECTNESS     60               │
│ • 200 notices   (B)  │  • 450 notices  (F)               │
│ • Top 3 fixes: ...   │  • Top 3 fixes: ...               │
├──────────────────────┼──────────────────────────────────┤
│ FRESHNESS      100   │  FRESHNESS       85               │
│ • Expires in 45d     │  • Expires in 15d                 │
├──────────────────────┼──────────────────────────────────┤
│ COMPLETENESS    70   │  COMPLETENESS    60               │
│ • Fares: YES         │  • Fares: NO                      │
│ • Flex: NO           │  • Flex: NO                       │
│ • Pathways: YES      │  • Pathways: NO                   │
├──────────────────────┼──────────────────────────────────┤
│ REALTIME (if pub)    │  REALTIME (if pub)                │
│ • Feed lag: 8s       │  • Feed lag: —                    │
│ • Trip coverage: 90% │  • Not published                  │
└──────────────────────┴──────────────────────────────────┘
```

### Content Per Category

Each rubric category shows:
- **Numeric score** (for easy comparison)
- **Key metric** (e.g., "Expires in X days", "Feed lag Y seconds")
- **Top difference** (if one is notably better, highlight it)
- **Adoption flags** (Fares, Flex, Pathways as yes/no)

### Mobile Layout

- Stack columns vertically: Agency A full section, then Agency B
- Or: Swipe between Agency A / Agency B (if interaction budget allows)
- Keep the header sticky (which agencies are being compared)

## Implementation Path

### Phase 1: Static Compare (MVP)

1. **Route:** `/compare/?a=<id>&b=<id>` → new page template `compare.html`
2. **Data source:** Load both agencies' `latest.json` artifacts via JS, render side-by-side
3. **No backend:** Pure static HTML + JS (matches the scorecard's model)
4. **Scope:**
   - Display categories + numeric scores
   - Show adoption flags (fares, flex, pathways)
   - Link back to full agency pages for details
   - Validate both agency IDs exist; show error if one is 404

### Phase 2: Enhanced Compare (future)

- Highlight the "winner" for each category (subtle color/border)
- Show trend arrows (is Agency A's score improving vs. B's?)
- Compare realtime trends (if both have RT history)
- Diff the top-3 fixes: which findings are unique to each?

### Phase 3: Search/Suggestion (if demanded)

- "Compare agencies" search UI on the homepage (not required MVP)
- Auto-suggest peers (same state/region, similar size)

## Technical

### File Structure

```
web/
  compare/
    index.html        # compare page template
    compare.js        # load artifacts, render side-by-side
    compare.css       # layout + styling
  
pipeline/
  # No pipeline changes; artifacts already exist
```

### Artifact Loading (Client-Side)

```javascript
async function loadComparison(agencyA, agencyB) {
  const [artA, artB] = await Promise.all([
    fetch(`/data/artifacts/${agencyA}/latest.json`).then(r => r.json()),
    fetch(`/data/artifacts/${agencyB}/latest.json`).then(r => r.json()),
  ]);
  renderComparison(artA, artB);
}
```

### Styling

- Reuse the existing scorecard color tokens (grades A–F)
- Use CSS Grid for side-by-side layout (mobile: 1 column, desktop: 2 columns)
- Focus on contrast: make differences visually obvious (bold score if > 10 pts diff)

## Scope Boundaries

**In scope:**
- Side-by-side display of scores, metrics, adoption flags
- Link to full agency pages
- Works on all browsers (no JS framework required)

**Out of scope (future):**
- Comparing more than 2 agencies at once
- Historical comparison (Agency A's score vs. Agency B's score 3 months ago)
- Diff-level deep-dives (show exact notices that differ)

## Acceptance Criteria (MVP)

Verified in the render, keyboard, route, mobile, contrast, axe, and Lighthouse
test suites as of 2026-07-10.

- [x] `/compare/?a=whitehorse-transit&b=barrie-transit` accepts and displays both agencies.
- [x] Scores, categories, and adoption flags are visible and drawn from the same artifacts.
- [x] The 320 CSS-pixel layout remains readable without page-level horizontal overflow.
- [x] Agency names link back to the individual scorecards.
- [x] Unknown or duplicate agency IDs produce a plain status message instead of a broken table.
- [x] Semantic table, labels, status region, keyboard operation, and AAA contrast are gated.
- [x] Lighthouse budgets require at least 90 performance and 95 accessibility.

## Future Enhancements

Once MVP is live:
- Add to the scorecard directory: "Compare this agency" option
- Add to homepage: "Start a comparison" link + search
- Track usage: which comparisons are made most? (informs future features)
- Highlight deltas: "Agency A is 15 points higher on Correctness"
