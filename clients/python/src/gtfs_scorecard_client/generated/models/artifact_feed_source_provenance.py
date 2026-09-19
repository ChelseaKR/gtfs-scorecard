from enum import StrEnum


class ArtifactFeedSourceProvenance(StrEnum):
    ARCHIVE = "archive"
    OFFICIAL = "official"
    THIRD_PARTY = "third_party"
    UNVERIFIED = "unverified"

    def __str__(self) -> str:
        return str(self.value)
