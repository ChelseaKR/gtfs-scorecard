from enum import StrEnum


class ArtifactFetchAuthKind(StrEnum):
    BASIC = "basic"
    HEADER = "header"
    QUERY = "query"

    def __str__(self) -> str:
        return str(self.value)
