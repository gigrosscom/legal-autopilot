"""Tiny, safe DSL for ``when:`` conditions in scenarios.

Grammar (no eval, no attribute access beyond ``<action>.response``)::

    expr   := clause ( "or" clause )*
    clause := term ( "and" term )*
    term   := ACTION ".response" ( "==" | "!=" ) WORD
            | ACTION ".response" ( "in" | "not in" ) "[" WORD ( "," WORD )* "]"
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TERM = re.compile(
    r"^\s*(?P<action>[a-z][a-z0-9_]*)\.response\s*"
    r"(?P<op>==|!=|not\s+in|in)\s*"
    r"(?P<rhs>\[[^\]]*\]|[a-z_]+)\s*$"
)


class ConditionError(ValueError):
    pass


@dataclass(frozen=True)
class Term:
    action: str
    op: str  # "in" | "not in"
    values: frozenset[str]

    def evaluate(self, responses: dict[str, str | None]) -> bool:
        value = responses.get(self.action)
        if value is None:
            return False  # action not answered yet → condition cannot hold
        inside = value in self.values
        return inside if self.op == "in" else not inside


@dataclass(frozen=True)
class Condition:
    source: str
    clauses: tuple[tuple[Term, ...], ...]  # OR of ANDs

    def evaluate(self, responses: dict[str, str | None]) -> bool:
        return any(all(t.evaluate(responses) for t in clause) for clause in self.clauses)

    @property
    def actions(self) -> set[str]:
        return {t.action for clause in self.clauses for t in clause}

    @property
    def values(self) -> set[str]:
        return {v for clause in self.clauses for t in clause for v in t.values}


def _parse_term(text: str) -> Term:
    m = _TERM.match(text)
    if not m:
        raise ConditionError(
            f"cannot parse condition term {text.strip()!r}; expected e.g. "
            "'claim.response in [none, refusal]' or 'claim.response == refusal'"
        )
    op = re.sub(r"\s+", " ", m["op"])
    rhs = m["rhs"]
    if rhs.startswith("["):
        items = [v.strip() for v in rhs[1:-1].split(",") if v.strip()]
        if not items:
            raise ConditionError(f"empty list in condition {text.strip()!r}")
        if op in ("==", "!="):
            raise ConditionError(f"use 'in'/'not in' with a list: {text.strip()!r}")
    else:
        if op in ("in", "not in"):
            raise ConditionError(f"'{op}' needs a [list]: {text.strip()!r}")
        items = [rhs]
    for item in items:
        if not re.fullmatch(r"[a-z_]+", item):
            raise ConditionError(f"bad value {item!r} in condition {text.strip()!r}")
    norm_op = "in" if op in ("==", "in") else "not in"
    return Term(action=m["action"], op=norm_op, values=frozenset(items))


def parse_condition(source: str) -> Condition:
    if not isinstance(source, str) or not source.strip():
        raise ConditionError("condition must be a non-empty string")
    clauses = []
    for or_part in re.split(r"\s+or\s+", source.strip()):
        terms = tuple(_parse_term(p) for p in re.split(r"\s+and\s+", or_part))
        clauses.append(terms)
    return Condition(source=source, clauses=tuple(clauses))
