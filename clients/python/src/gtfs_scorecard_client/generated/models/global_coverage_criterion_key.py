from enum import StrEnum


class GlobalCoverageCriterionKey(StrEnum):
    COUNTRIES = "countries"
    FEATURE_DENOMINATOR_DISCLOSED = "feature_denominator_disclosed"
    FRESH_SCORECARDS = "fresh_scorecards"
    IDENTITY_REVIEWED = "identity_reviewed"
    LARGEST_COUNTRY_SHARE = "largest_country_share"
    PORTABLE_LOCATION = "portable_location"
    REVIEWED_FEED_RECORDS = "reviewed_feed_records"
    TRANSLATIONS_MEASURED = "translations_measured"

    def __str__(self) -> str:
        return str(self.value)
