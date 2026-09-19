from enum import StrEnum


class ArtifactFindingSeverity(StrEnum):
    ERROR = "ERROR"
    INFO = "INFO"
    WARNING = "WARNING"

    def __str__(self) -> str:
        return str(self.value)
