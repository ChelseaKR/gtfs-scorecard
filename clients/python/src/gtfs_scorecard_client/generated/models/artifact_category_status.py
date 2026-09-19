from enum import StrEnum


class ArtifactCategoryStatus(StrEnum):
    MEASURED = "measured"
    NOT_YET_MEASURED = "not_yet_measured"

    def __str__(self) -> str:
        return str(self.value)
