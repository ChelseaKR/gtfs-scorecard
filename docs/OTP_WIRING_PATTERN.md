# Wiring OpenTripPlanner Routing QA Results to Agency Pages

**Status:** Implemented as an opt-in weekly QA path. National publishing remains
intentionally disabled because this project does not operate a hosted OTP service.

## Overview

The `scorecard otp` CLI command runs trip-plannability QA against an external OpenTripPlanner instance: sample origin-destination pairs, query the OTP endpoint, and fail if any trip returns no itinerary. This document outlines how to surface those results on agency pages once OTP is available.

## Current State

- **`pipeline/src/scorecard_pipeline/otp.py`**: Trip-plannability assessment (already built, serverless-compatible)
- **`scorecard otp` CLI**: Query OTP for sampled routes (registered, requires OTP endpoint URL)
- **`otp-qa.yml` workflow**: Weekly and manual sampling
- **Agency pages**: `_otp_section` in `render_site.py` renders a "Can a rider plan
  a trip?" section, gated on the artifact carrying a measured `routing_qa` block —
  pages are unchanged until the OTP job publishes results

## Wiring Pattern

### 1. Artifact Structure (if OTP is run)

```json
{
  "routing_qa": {
    "summary": "123 of 125 sampled trips returned an itinerary",
    "name": "Trip-plannability QA",
    "status": "measured",
    "score": 98.4,
    "details": {
      "total_sampled": 125,
      "routable_trips": 123,
      "unroutable_pct": 1.6,
      "notes": "Failures on 2 late-night trips outside service area."
    }
  }
}
```

### 2. Render-Site Gating (existing pattern from equity/adoption)

The renderer is implemented in `_otp_section()` and called by `_render_agency()`.
The example below documents the artifact contract rather than pending code.

```python
def _otp_section(artifact: dict[str, Any]) -> str:
    """Trip-plannability QA, when available (requires external OTP service)."""
    rq = artifact.get("routing_qa") or {}
    if not rq.get("status"):
        return ""  # OTP not run for this feed
    score = rq.get("score")
    pct = rq.get("details", {}).get("unroutable_pct", 0)
    return f"""
    <section aria-labelledby="otp-h" class="feed-details">
      <h2 class="section-title" id="otp-h">Can a rider actually plan a trip?</h2>
      <p class="page-lede">
        We sampled {rq['details']['total_sampled']} origin-destination pairs via 
        <a href="https://www.openplans.org/opentripplanner/">OpenTripPlanner</a>. 
        {pct:.1f}% returned no itinerary (typically outside service hours or area).
      </p>
    </section>
    """
```

### 3. CLI Integration

The `scorecard otp` command already exists:

```bash
# Requires a running OTP instance (e.g., locally or via Docker)
scorecard otp ./feed.zip --base http://localhost:8080
```

### 4. Workflow (Manual Sample)

The `otp-qa.yml` workflow can be adapted to run on demand:

```yaml
name: Route QA (OTP)
# Requires: OTP instance running, GTFS feed URL
# Usage: gh workflow run otp-qa.yml -f feed_url=...
```

## Implementation record

- [x] Build the OTP artifact structure in `otp.py` → `artifact["routing_qa"]`.
- [x] Add `_otp_section()` to `render_site.py` and call it in `_render_agency()`.
- [x] Provide weekly and manual execution in `.github/workflows/otp-qa.yml`.
- [x] Document local setup and command usage.
- National-map publishing is intentionally not applicable until a representative
  hosted run exists; publishing a partial opt-in sample would mislead readers.
- Daily scoring integration is intentionally not applicable without a hosted OTP
  service. The weekly/manual workflow preserves the serverless cost boundary.

## Decisions

1. **No national OTP by default.** OTP is a heavy Java service; the project remains serverless. OTP is always opt-in: users can run it locally or with their own instance.
2. **Gated like equity overlays.** If OTP data doesn't exist, the section is absent (no "not measured" note on pages where it wasn't run).
3. **Reuse the sampling pattern.** `sample_od_pairs()` is already in `otp.py`; just needs wiring to the render layer.

## Future

If the project adds a backend (a routing service, OTP instance, or integration with a third-party routing API), this becomes a fully automated, national feature. Until then, it's an available CLI tool for operators who want to check trip-plannability locally.
