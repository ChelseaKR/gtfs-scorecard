from enum import StrEnum


class CatalogAgencyGoogleGate(StrEnum):
    AT_RISK = "at_risk"
    FAIL = "fail"
    PASS = "pass"

    def __str__(self) -> str:
        return str(self.value)
