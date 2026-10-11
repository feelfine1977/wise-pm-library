"""Applicability rules: one rule grammar, parsed once, evaluated three-valued over the case table.

A rule states the business scope of a constraint (paper Section 4.4). It is
written in one of two forms. The short form maps case attributes to allowed
values, combined with AND::

    {"flow_type": ["DF1", "DF2"], "document_type": ["Standard PO"]}

The rule form allows ``all`` / ``any`` combinations of leaves::

    {"all": [{"attr": "flow_type", "in": ["DF1"]},
             {"attr": "exposure", "gte": 1000}]}

Leaf operators on a case attribute: ``in``, ``eq``, ``gt``, ``gte``, ``lt``,
``lte``.

:func:`parse` turns a rule into a :class:`Selection`: a small tree that states
the attributes it reads. :meth:`Selection.evaluate` evaluates the tree over a
case table and returns a nullable boolean Series: ``True`` in scope, ``False``
out of scope, ``<NA>`` unknown.

Missing values
--------------
A case whose attribute is missing is unknown under every operator. ``all``
and ``any`` combine by Kleene logic: ``all`` is out of scope when one part is
out of scope, else unknown when one part is unknown; ``any`` is in scope when
one part is in scope, else unknown when one part is unknown. Scoring treats a
case of unknown scope as not in scope and records the reason.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

import pandas as pd

from ._frozen import freeze
from ._json import jsonable
from .errors import NormError

LEAF_OPERATORS = ("in", "eq", "gt", "gte", "lt", "lte")
_RULE_KEYS = {"all", "any", "attr"}
#: Keys of the rule grammar of the full library ``wise-pm`` that this library does not implement.
_UNSUPPORTED_KEYS = {"not", "has", "lacks"}
#: The name of the missing-value policy, as norm documents state it.
THREE_VALUED = "three_valued"


# ----------------------------------------------------------------------------- tree
@dataclass(frozen=True)
class Compare:
    """Leaf ``{"attr": attr, op: value}`` on one case attribute."""

    attr: str
    op: str
    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze(self.value))


@dataclass(frozen=True)
class AllOf:
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class AnyOf:
    rules: tuple[Rule, ...]


Rule: TypeAlias = Compare | AllOf | AnyOf


def _walk(rule: Rule) -> Iterator[Rule]:
    yield rule
    if isinstance(rule, AllOf | AnyOf):
        for r in rule.rules:
            yield from _walk(r)


# ----------------------------------------------------------------------------- selection
@dataclass(frozen=True)
class Selection:
    """A parsed rule. ``rule is None`` selects every case; ``document`` is the normalised source."""

    rule: Rule | None
    document: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "document", freeze(self.document))

    @property
    def columns(self) -> tuple[str, ...]:
        """Case attributes the rule reads, in order of first use."""
        if self.rule is None:
            return ()
        return tuple(dict.fromkeys(r.attr for r in _walk(self.rule) if isinstance(r, Compare)))

    def evaluate(self, cases: pd.DataFrame) -> pd.Series:
        """Nullable boolean Series over ``cases.index``: in scope, out of scope, ``<NA>`` unknown."""
        if self.rule is None:
            return pd.Series(True, index=cases.index, dtype="boolean")
        return _evaluate(self.rule, cases)


def _evaluate(rule: Rule, cases: pd.DataFrame) -> pd.Series:
    if isinstance(rule, AllOf):
        out = pd.Series(True, index=cases.index, dtype="boolean")
        for r in rule.rules:
            out &= _evaluate(r, cases)
        return out
    if isinstance(rule, AnyOf):
        out = pd.Series(False, index=cases.index, dtype="boolean")
        for r in rule.rules:
            out |= _evaluate(r, cases)
        return out
    if rule.attr not in cases.columns:
        raise NormError(f"selection refers to case attribute {rule.attr!r}, which is missing from the case table")
    s = cases[rule.attr]
    known = _compare(s, rule.op, rule.value).astype("boolean")
    return known.mask(s.isna().to_numpy(), pd.NA)


def _compare(s: pd.Series, op: str, v: Any) -> pd.Series:
    if op == "in":
        return s.isin(list(v))
    if op == "eq":
        out: pd.Series = s == v
        return out.fillna(False)
    num = pd.to_numeric(s, errors="coerce")
    compared: dict[str, pd.Series] = {"gt": num > v, "gte": num >= v, "lt": num < v, "lte": num <= v}
    return compared[op].fillna(False)


# ----------------------------------------------------------------------------- parsing
def parse(rule: Any, *, what: str = "selection") -> Selection:
    """Parse the short form or the rule form; raise :class:`NormError` naming ``what`` if malformed.

    ``None`` and ``{}`` select every case.
    """
    if rule is None:
        return Selection(None, {})
    if not isinstance(rule, Mapping):
        raise NormError(f"{what} must be a mapping, got {type(rule).__name__}")
    if not rule:
        return Selection(None, {})
    if set(rule) & (_RULE_KEYS | _UNSUPPORTED_KEYS):
        return Selection(_parse_rule(rule, what), copy.deepcopy(dict(rule)))
    short: dict[str, Any] = {}
    leaves: list[Rule] = []
    for attr, values in rule.items():
        if isinstance(values, str | bytes) or not isinstance(values, Iterable):
            values = [values]
        short[str(attr)] = [jsonable(v) for v in values]
        if not short[str(attr)]:
            raise NormError(f"{what} for {attr!r} is an empty list (nothing would apply)")
        leaves.append(Compare(str(attr), "in", list(short[str(attr)])))
    return Selection(AllOf(tuple(leaves)), short)


def _parse_rule(rule: Any, what: str) -> Rule:
    if not isinstance(rule, Mapping):
        raise NormError(f"{what} rule must be a mapping, got {rule!r}")
    keys = set(rule)
    unsupported = sorted(keys & _UNSUPPORTED_KEYS)
    if unsupported:
        raise NormError(f"{what} rule {dict(rule)}: {unsupported} is not part of this library's rule grammar")
    if "all" in keys or "any" in keys:
        if len(keys) != 1:
            raise NormError(f"{what} rule {dict(rule)}: 'all'/'any' must be the only key")
        items = rule["all"] if "all" in keys else rule["any"]
        if not isinstance(items, list) or not items:
            raise NormError(f"{what} 'all'/'any' must be a non-empty list of rules")
        parts = tuple(_parse_rule(r, what) for r in items)
        return AllOf(parts) if "all" in keys else AnyOf(parts)
    if "attr" in keys:
        ops = keys - {"attr"}
        if len(ops) != 1 or not ops <= set(LEAF_OPERATORS):
            raise NormError(f"{what} leaf {dict(rule)} needs exactly one operator from {sorted(LEAF_OPERATORS)}")
        (op,) = ops
        return Compare(str(rule["attr"]), op, copy.deepcopy(rule[op]))
    raise NormError(f"{what} rule {dict(rule)} is neither a short form nor a rule")


__all__ = ["LEAF_OPERATORS", "THREE_VALUED", "AllOf", "AnyOf", "Compare", "Rule", "Selection", "parse"]
