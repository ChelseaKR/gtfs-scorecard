from enum import StrEnum


class DirectoryAgenciesItemGoogleGate(StrEnum):
    AT_RISK = "at_risk"
    FAIL = "fail"
    PASS = "pass"

    def __str__(self) -> str:
        return str(self.value)
