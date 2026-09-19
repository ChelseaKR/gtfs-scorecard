from enum import StrEnum


class RollupComparisonRequiredMeasuredCategoriesItem(StrEnum):
    COMPLETENESS = "completeness"
    CORRECTNESS = "correctness"
    FRESHNESS = "freshness"
    REALTIME = "realtime"

    def __str__(self) -> str:
        return str(self.value)
