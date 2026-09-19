from enum import StrEnum


class ByLocationComparisonRequiredMeasuredCategoriesItem(StrEnum):
    COMPLETENESS = "completeness"
    CORRECTNESS = "correctness"
    FRESHNESS = "freshness"
    REALTIME = "realtime"

    def __str__(self) -> str:
        return str(self.value)
