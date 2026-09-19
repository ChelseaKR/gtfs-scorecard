from enum import StrEnum


class RollupMembersItemExpiryStatus(StrEnum):
    CURRENT = "current"
    EXPIRING_SOON = "expiring_soon"
    LAPSED = "lapsed"
    STALE = "stale"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
