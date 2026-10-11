"""Exclusion ``(excl, a)``: ``ν = 1[cnt(a, σ) > 0]`` (paper Section 4.2).

Every case is evaluated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..constraints import Exclusion
from ..family import Evaluation, Family, Inputs

if TYPE_CHECKING:  # pragma: no cover
    from ..log import EventLog


def requires(c: Exclusion) -> Inputs:
    return Inputs(activities=c.activities())


def evaluate(c: Exclusion, log: EventLog) -> Evaluation:
    cnt = log.count(c.activity)
    return Evaluation.of((cnt > 0).astype(float), log.case_ids)


FAMILY = Family(
    name="exclusion",
    constraint=Exclusion,
    requires=requires,
    evaluate=evaluate,
    aliases=("excl",),
    fixed={"after": None, "before": None},
)
