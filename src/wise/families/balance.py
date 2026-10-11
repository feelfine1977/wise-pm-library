"""Balance ``(bal, α_x, A_x, α_y, A_y, τ, Γ)`` (paper Section 4.2).

``d = |tot_x − tot_y| / max(tot_x, tot_y, ε)``, ``ν = sat(d; τ, Γ)``. The two
attributes are event columns; totals must be non-negative (Section 4.1). A
case in which a selected event has no usable number has no total and cannot
be evaluated (:data:`~wise.family.MISSING_VALUE`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..constraints import Balance, sat
from ..errors import NormError
from ..family import MISSING_VALUE, Evaluation, Family, Inputs

if TYPE_CHECKING:  # pragma: no cover
    from ..log import EventLog


def requires(c: Balance) -> Inputs:
    return Inputs(activities=c.activities(), event_columns=(c.attr_x, c.attr_y))


def evaluate(c: Balance, log: EventLog) -> Evaluation:
    tot_x = log.total(c.attr_x, c.activities_x)
    tot_y = log.total(c.attr_y, c.activities_y)
    if (tot_x < 0).any() or (tot_y < 0).any():
        raise NormError(
            "balance totals must be non-negative (paper Section 4.1); net credit notes first or take absolute values"
        )
    unavailable = (tot_x.isna() | tot_y.isna()).to_numpy()
    denom = np.maximum(np.maximum(tot_x.to_numpy(), tot_y.to_numpy()), c.eps)
    d = pd.Series((tot_x - tot_y).abs().to_numpy() / denom, index=log.case_ids)
    return Evaluation.of(sat(d, c.tau, c.width), log.case_ids, why=[(unavailable, MISSING_VALUE)])


FAMILY = Family(
    name="balance",
    constraint=Balance,
    requires=requires,
    evaluate=evaluate,
    numbers=frozenset({"tau", "width", "eps"}),
    aliases=("bal",),
    fixed={"agg": "sum"},
)
