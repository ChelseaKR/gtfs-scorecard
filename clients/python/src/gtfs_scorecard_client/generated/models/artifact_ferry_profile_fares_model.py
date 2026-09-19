from enum import StrEnum


class ArtifactFerryProfileFaresModel(StrEnum):
    LEGACY = "legacy"
    NONE = "none"
    V2 = "v2"

    def __str__(self) -> str:
        return str(self.value)
