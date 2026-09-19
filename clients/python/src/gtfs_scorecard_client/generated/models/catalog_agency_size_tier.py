from enum import StrEnum


class CatalogAgencySizeTier(StrEnum):
    LARGE = "large"
    MEDIUM = "medium"
    SMALL = "small"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
