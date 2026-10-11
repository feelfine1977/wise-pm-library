"""Occurrence limit ``(sing, a, k, K)``: ``ν = sat(cnt(a, σ); k, K)`` (paper Section 4.2).

Every case is evaluated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..constraints import Singularity, sat
from ..family import Evaluation, Family, Inputs

if TYPE_CHECKING:  # pragma: no cover
    from ..log import EventLog


def requires(c: Singularity) -> Inputs:
    return Inputs(activities=c.activities())


def evaluate(c: Singularity, log: EventLog) -> Evaluation:
    return Evaluation.of(sat(log.count(c.activity), c.k, c.K), log.case_ids)


FAMILY = Family(
    name="singularity",
    constraint=Singularity,
    requires=requires,
    evaluate=evaluate,
    numbers=frozenset({"k", "K"}),
    aliases=("sing",),
    fixed={"after": None, "before": None},
)
