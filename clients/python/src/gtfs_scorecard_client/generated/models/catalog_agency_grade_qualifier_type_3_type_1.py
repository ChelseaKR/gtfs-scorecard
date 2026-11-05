from enum import StrEnum


class CatalogAgencyGradeQualifierType3Type1(StrEnum):
    PARTIAL_FRESHNESS_NOT_MEASURED = "partial: freshness not measured"

    def __str__(self) -> str:
        return str(self.value)
