from enum import StrEnum


class GlobalCoverageExceptionKey(StrEnum):
    FEATURE_DENOMINATOR_NOT_DISCLOSED = "feature_denominator_not_disclosed"
    FUTURE_RETRIEVED_AT = "future_retrieved_at"
    IDENTITY_NOT_REVIEWED = "identity_not_reviewed"
    INVALID_PORTABLE_LOCATION = "invalid_portable_location"
    MALFORMED_RETRIEVED_AT = "malformed_retrieved_at"
    MISSING_DIRECTORY_RECORD = "missing_directory_record"
    MISSING_FEATURE_RECORD = "missing_feature_record"
    MISSING_RETRIEVED_AT = "missing_retrieved_at"
    STALE_SCORECARD = "stale_scorecard"
    TRANSLATIONS_NOT_MEASURED = "translations_not_measured"

    def __str__(self) -> str:
        return str(self.value)
