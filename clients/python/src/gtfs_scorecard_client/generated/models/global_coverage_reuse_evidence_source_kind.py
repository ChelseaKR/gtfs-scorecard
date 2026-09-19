from enum import StrEnum


class GlobalCoverageReuseEvidenceSourceKind(StrEnum):
    OFFICIAL_PORTAL = "official_portal"
    PROVIDER = "provider"

    def __str__(self) -> str:
        return str(self.value)
