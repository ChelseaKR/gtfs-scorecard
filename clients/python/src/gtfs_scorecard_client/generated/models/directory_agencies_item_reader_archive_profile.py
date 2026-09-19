from enum import StrEnum


class DirectoryAgenciesItemReaderArchiveProfile(StrEnum):
    FLAT_SINGLE_ROOT_V1 = "flat-single-root-v1"
    RAW_V1 = "raw-v1"

    def __str__(self) -> str:
        return str(self.value)
