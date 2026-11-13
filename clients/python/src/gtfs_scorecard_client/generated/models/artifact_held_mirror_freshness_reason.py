from enum import StrEnum


class ArtifactHeldMirrorFreshnessReason(StrEnum):
    MIRROR_COPY = "mirror_copy"
    MIRROR_COPY_EXPIRED = "mirror_copy_expired"

    def __str__(self) -> str:
        return str(self.value)
