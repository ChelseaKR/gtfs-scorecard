"""Scoring pipeline for the small-agency GTFS quality scorecard."""

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
SCHEMA_VERSION = "1.6"

# The license the public scorecard data is offered under. Carried on the catalog
# and directory documents so a consumer (OSS project, consultant, researcher)
# has an unambiguous reuse grant, which several of them treat as a hard blocker.
DATA_LICENSE = "CC-BY-4.0"
DATA_ATTRIBUTION = (
    "GTFS Scorecard (gtfsscorecard.org), scored on top of the MobilityData gtfs-validator"
)

# Bump when the rubric (weights, deductions, grade bands, or what is measured)
# changes, so a trend can tell a feed change apart from a methodology change.
RUBRIC_VERSION = "1.1"
