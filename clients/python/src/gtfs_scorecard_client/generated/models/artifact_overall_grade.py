from enum import StrEnum


class ArtifactOverallGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"

    def __str__(self) -> str:
        return str(self.value)
