from enum import StrEnum


class ArtifactConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    PROVISIONAL = "provisional"

    def __str__(self) -> str:
        return str(self.value)
