from enum import StrEnum


class GlobalCoverageCriterionUnit(StrEnum):
    BOOLEAN = "boolean"
    COUNTRIES = "countries"
    FEED_RECORDS = "feed_records"
    PERCENT = "percent"

    def __str__(self) -> str:
        return str(self.value)
