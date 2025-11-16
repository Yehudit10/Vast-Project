"""Plan operations → SQLState mutations.

Ops transform high-level IR steps into concrete Clause objects and attach them
to the SQLState. A small registry maps 'op' strings to Op subclasses.
"""

from __future__ import annotations
from typing import Any, Dict, List, Type
from abc import ABC, abstractmethod
from .clauses import SelectClause, WhereClause,OrderByClause,LimitClause,HavingClause,OffsetClause,GroupByClause
from .expr import cond_from_ir
# from .builder import SQLState

class Op(ABC):
    registry: Dict[str, Type["Op"]] = {}
    def __init_subclass__(cls, **kwargs):
        """Automatically register subclasses that declare `op_type`."""
        super().__init_subclass__(**kwargs)
        op_type = getattr(cls, "op_type", None)
        if op_type: Op.registry[op_type] = cls
    def __init__(self, **payload: Any): self.payload = payload

    @abstractmethod
    def apply(self, st: "SQLState") -> None:
        """Mutate SQLState by adding clauses based on this operation."""
        ...

class SelectOp(Op):
    op_type = "select"
    def apply(self, st: "SQLState") -> None:
        cols = self.payload.get("columns")
        st.add_select(cols or [])
        
class WhereOp(Op):
    op_type = "where"
    def apply(self, st: "SQLState") -> None:
        cond_ir = self.payload.get("cond")
        if not isinstance(cond_ir, dict):
            raise TypeError(
                f"Invalid WHERE condition: expected dict, got {type(cond_ir).__name__} → {cond_ir}"
            )
        st.add_where(cond_from_ir(cond_ir))


class HavingOp(Op):
    op_type = "having"
    def apply(self, st):
        cond_ir = self.payload.get("cond")
        if not isinstance(cond_ir, dict):
            raise TypeError(
                f"Invalid HAVING condition: expected dict, got {type(cond_ir).__name__} → {cond_ir}"
            )
        st.add_clause(HavingClause(cond_from_ir(cond_ir)))



class OrderByOp(Op):
    op_type = "order_by"
    def apply(self, st):
        st.add_clause(OrderByClause(
            self.payload.get("columns", []),
            self.payload.get("directions", [])
        ))

class LimitOp(Op):
    op_type = "limit"
    def apply(self, st):
        st.add_clause(LimitClause(self.payload["limit"]))

class OffsetOp(Op):
    op_type = "offset"
    def apply(self, st):
        st.add_clause(OffsetClause(self.payload["offset"]))

class GroupByOp(Op):
    op_type = "group_by"
    def apply(self, st):
        st.add_clause(GroupByClause(self.payload.get("columns", [])))



