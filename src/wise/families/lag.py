"""Lag ``(lag, a, b, δ, Δ)``: ``ν = sat(t_b − t_a; δ, Δ)`` (paper Section 4.2).

The activation is the first ``a`` of the case that has a timestamp, the
response the first ``b`` at or after it (an event at the same instant counts,
whatever its row order).

Reasons: a case without an activation under ``missing_a="skip"`` is
:data:`~wise.family.MISSING_ACTIVATION`, one whose activation has no response
under ``missing_b="skip"`` is :data:`~wise.family.MISSING_RESPONSE`. A missing
endpoint under ``"violate"`` gives ``ν = 1`` and is evaluated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..constraints import Lag, in_units, sat
from ..family import MISSING_ACTIVATION, MISSING_RESPONSE, Evaluation, Family, Inputs

if TYPE_CHECKING:  # pragma: no cover
    from ..log import EventLog


def requires(c: Lag) -> Inputs:
    return Inputs(activities=c.activities())


def evaluate(c: Lag, log: EventLog) -> Evaluation:
    t_a, t_b = log.first_after(c.a, c.b)
    lag = in_units(t_b - t_a, c.unit)
    activated = t_a.notna().to_numpy()
    values = sat(lag, c.delta, c.width).to_numpy(dtype=float, copy=True)
    open_ = activated & lag.isna().to_numpy()
    if c.missing_b == "violate":
        values[open_] = 1.0
    if c.missing_a == "violate":
        values[~activated] = 1.0
    return Evaluation.of(values, log.case_ids, why=((~activated, MISSING_ACTIVATION), (open_, MISSING_RESPONSE)))


FAMILY = Family(
    name="lag",
    constraint=Lag,
    requires=requires,
    evaluate=evaluate,
    numbers=frozenset({"delta", "width"}),
    fixed={"activation": "first", "response": "first_after"},
)
