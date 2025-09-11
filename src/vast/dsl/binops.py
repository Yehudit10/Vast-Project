# dsl/binops.py (new)
from enum import Enum

# Works on Python 3.8+; on 3.11+ you can import from enum import StrEnum
class StrEnum(str, Enum):
    pass

class BinOp(StrEnum):
    EQ  = "="
    NE  = "!="
    LT  = "<"
    LE  = "<="
    GT  = ">"
    GE  = ">="

    def __str__(self) -> str:
        return self.value
