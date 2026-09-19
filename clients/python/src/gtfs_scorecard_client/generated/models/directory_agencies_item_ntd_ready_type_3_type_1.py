from enum import StrEnum


class DirectoryAgenciesItemNtdReadyType3Type1(StrEnum):
    AT_RISK = "at_risk"
    NOT_READY = "not_ready"
    READY = "ready"

    def __str__(self) -> str:
        return str(self.value)
