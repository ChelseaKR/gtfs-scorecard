"""Scoring pipeline for the small-agency GTFS quality scorecard."""

from .instance import BASE_URL as _BASE_URL
from .instance import SITE_NAME as _SITE_NAME

# 1.9: country fields accept every assigned ISO 3166-1 alpha-2 jurisdiction;
# schemas describe that portable shape while the generated ISO vocabulary is
# the stricter write boundary. No score or rubric field changed.
# 1.8: additive scoring_profile metadata on every per-agency artifact. The
# profile identifies the project-authored scoring contract independently from
# the artifact schema and states its provenance and limits explicitly.
# 1.7: additive state_percentile on per-state rollup payloads (None on "all"
# and named-cohort rollups, which are not peers of a 50-state comparison), so a
# program page can say how its average score compares to other states'
# programs -- framed as a neutral distribution read, never a rank.
# 1.6: additive measurement-confidence read on every artifact (a confidence
# block: level, measured vs total categories, fetch source, realtime sampling
# depth, snapshot age, plain-language notes), so a reader can tell a
# fully-measured grade from a provisional one (EXP-01).
# 1.5: shapes_readiness on every US agency artifact (shapes.txt coverage of
# trips), mapping the feed onto FTA's July 2025 shapes.txt requirement (Full
# Reporters RY2025; Reduced, Rural, and Tribal Reporters RY2026).
# 1.4: provenance and identity carried on every catalog/directory row
# (validator_version, rubric_version, retrieved_at, feed_sha256, mdb_id) and an
# explicit data license on the catalog and directory documents, so a grade is
# reproducible, joinable to the Mobility Database, and reusable.
# 1.3: additive freshness fields exposed to consumers (days_until_expiry in
# index history, expiry_status in the catalog and rollup members).
SCHEMA_VERSION = "1.9"

# The license the public scorecard data is offered under. Carried on the catalog
# and directory documents so a consumer (OSS project, consultant, researcher)
# has an unambiguous reuse grant, which several of them treat as a hard blocker.
DATA_LICENSE = "CC-BY-4.0"
DATA_ATTRIBUTION = (
    f"{_SITE_NAME} ({_BASE_URL.split('://', 1)[-1].rstrip('/')}), "
    "scored on top of the MobilityData gtfs-validator"
)

# Bump when the rubric (weights, deductions, grade bands, or what is measured)
# changes, so a trend can tell a feed change apart from a methodology change.
RUBRIC_VERSION = "1.1"

# Stable identity for the scoring contract. This is deliberately distinct from
# SCHEMA_VERSION: adding an API field must not imply a methodology change.
SCORING_PROFILE_ID = f"gtfs-scorecard-{RUBRIC_VERSION}"
SCORING_PROFILE_PROVENANCE = (
    "GTFS Scorecard's project-authored weights, deductions, thresholds, grade bands, "
    "and fix ranking, informed by the California Transit Data Guidelines and the "
    "MobilityData gtfs-validator. It is not a worldwide standard or a compliance "
    "determination."
)
