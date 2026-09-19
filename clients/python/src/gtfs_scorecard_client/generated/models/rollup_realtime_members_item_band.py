from enum import StrEnum


class RollupRealtimeMembersItemBand(StrEnum):
    MOSTLY = "mostly"
    RELIABLE = "reliable"
    SPOTTY = "spotty"

    def __str__(self) -> str:
        return str(self.value)
