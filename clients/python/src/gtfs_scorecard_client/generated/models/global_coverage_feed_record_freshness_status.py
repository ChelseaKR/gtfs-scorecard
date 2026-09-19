from enum import StrEnum


class GlobalCoverageFeedRecordFreshnessStatus(StrEnum):
    FRESH = "fresh"
    FUTURE_RETRIEVED_AT = "future_retrieved_at"
    MALFORMED_RETRIEVED_AT = "malformed_retrieved_at"
    MISSING_DIRECTORY_RECORD = "missing_directory_record"
    MISSING_RETRIEVED_AT = "missing_retrieved_at"
    STALE_SCORECARD = "stale_scorecard"

    def __str__(self) -> str:
        return str(self.value)
