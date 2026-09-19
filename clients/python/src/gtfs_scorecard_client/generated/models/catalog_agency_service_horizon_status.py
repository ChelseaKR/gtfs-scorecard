from enum import StrEnum


class CatalogAgencyServiceHorizonStatus(StrEnum):
    UNKNOWN = "unknown"
    UNUSUALLY_DISTANT = "unusually_distant"
    WITHIN_REVIEW_THRESHOLD = "within_review_threshold"

    def __str__(self) -> str:
        return str(self.value)
