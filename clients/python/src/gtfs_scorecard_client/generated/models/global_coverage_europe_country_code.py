from enum import StrEnum


class GlobalCoverageEuropeCountryCode(StrEnum):
    AT = "AT"
    BE = "BE"
    BG = "BG"
    CH = "CH"
    CY = "CY"
    CZ = "CZ"
    DE = "DE"
    DK = "DK"
    EE = "EE"
    ES = "ES"
    FI = "FI"
    FR = "FR"
    GB = "GB"
    GR = "GR"
    HR = "HR"
    HU = "HU"
    IE = "IE"
    IS = "IS"
    IT = "IT"
    LI = "LI"
    LT = "LT"
    LU = "LU"
    LV = "LV"
    MT = "MT"
    NL = "NL"
    NO = "NO"
    PL = "PL"
    PT = "PT"
    RO = "RO"
    SE = "SE"
    SI = "SI"
    SK = "SK"

    def __str__(self) -> str:
        return str(self.value)
