# Convenience targets. CI runs the same commands directly (see .github/workflows);
# these just give them stable names. `uv` runs inside the pipeline/ project.

.PHONY: verify tiles tiles-geojsonl render-site render-constants test contrast readability sync-static-nav mutation mutation-results

# The merge-blocking gate: lint, format, types, tests, the AAA contrast check,
# and the plain-language readability check. Mirrors .github/workflows/ci.yml.
verify:
	cd pipeline && uv run ruff check src tests
	cd pipeline && uv run ruff format --check src tests
	cd pipeline && uv run mypy
	cd pipeline && uv run pytest -q --cov=scorecard_pipeline --cov-branch --cov-fail-under=92
	cd pipeline && uv run python scripts/check_contrast.py
	cd pipeline && uv run python scripts/check_readability.py

test:
	cd pipeline && uv run pytest -q --cov=scorecard_pipeline --cov-branch --cov-fail-under=92

contrast:
	cd pipeline && uv run python scripts/check_contrast.py

readability:
	cd pipeline && uv run python scripts/check_readability.py

render-site:
	cd pipeline && uv run scorecard render-site

# Regenerate web/src/generated/constants.js (grade bands and ranks, category and
# severity labels, rule links, thresholds) from the Python definitions in
# constants_export.py, the single source of truth. render-site runs this too;
# tests/test_generated_constants.py fails CI if the committed file drifts.
render-constants:
	cd pipeline && uv run scorecard render-constants

# Regenerate the primary nav in the hand-authored static pages (submit, subscribe,
# try, the app shell, about, data) from _NAV_ITEMS, the single source of truth.
# tests/test_static_nav.py fails CI if a static page's nav drifts from it.
sync-static-nav:
	cd pipeline && uv run python -c "from scorecard_pipeline.render_site import sync_static_navs; print('synced:', [str(p) for p in sync_static_navs()])"

# Rebuild the national all-routes vector tiles + PMTiles archive (web/tiles/).
# Requires tippecanoe on PATH (brew install tippecanoe). NOT part of `verify` or
# the daily build — tippecanoe is not in the daily image. See docs/decisions/0023.
tiles:
	cd pipeline && uv run python scripts/build_national_pmtiles.py

# Just the aggregated GeoJSONL, no tippecanoe needed (for inspecting the input).
tiles-geojsonl:
	cd pipeline && uv run python scripts/build_national_pmtiles.py --geojsonl-only

# ADVISORY mutation testing of the scoring math (src/scorecard_pipeline/score.py,
# metrics.py, and rt.py: the grade ladder, fix-priority tiers, deduction
# arithmetic, freshness slope, and realtime weighting — where a silent bug
# mis-grades an agency). Coverage there is already high, so this is the next
# signal: do the tests' assertions actually catch a regression? Scope + config
# live in pipeline/pyproject.toml [tool.mutmut]; the kill signal is the unit
# tests for those modules plus the property/corpus tests (about a minute).
#
# NOT part of `verify` and NEVER a per-PR blocker — REVIEW-GATE per
# CODE-QUALITY-STANDARD.md §10. Run it locally or via the weekly mutation.yml
# workflow. Baseline score + triaged survivors: docs/mutation-testing.md. Delete
# pipeline/mutants/ first for a clean-cache baseline; `mutation-results` reprints
# the last run's survivors without re-running.
mutation:
	cd pipeline && uv run mutmut run
	cd pipeline && uv run mutmut results

mutation-results:
	cd pipeline && uv run mutmut results
