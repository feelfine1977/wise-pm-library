"""The prioritised investigation list as a record: the table plus the specification that produced it.

:func:`wise.prioritize` returns a :class:`Backlog`. Its :attr:`~Backlog.table`
is the ranked frame (paper Section 4.5); its :attr:`~Backlog.spec` is a frozen
:class:`BacklogSpec` holding the comparison settings that belong to the
assessment record (Appendix A.4): the grouping attributes, the view, the
scale, the shrinkage constant, the comparison reference and the norm the
scores came from. The specification is a field of the record, so it survives
copying and pickling and is never lost in a pandas operation on the table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

__all__ = ["TIE_POLICY", "Backlog", "BacklogSpec"]

TIE_POLICY = "Priority Index descending, scored cases descending, slice key ascending"
"""How slices with equal priority are ordered (paper Appendix B.1)."""


@dataclass(frozen=True)
class BacklogSpec:
    """The settings a backlog was ranked with (paper Section 4.5 and Appendix A.4).

    Attributes
    ----------
    by
        Slice key column(s), in order.
    view
        The view whose scores were ranked; ``None`` when the input was a
        per-case frame rather than a :class:`~wise.scoring.ScoreResult`.
    gamma
        Shrinkage constant ``γ`` (0 = no adjustment for small slices).
    volume
        ``"cases"``, ``"exposure"`` or the per-case column summed as scale.
    global_mean
        The comparison reference ``μ̄``: the mean score of all scored cases.
    norm_fingerprint
        Fingerprint of the norm the scores came from; ``None`` for a per-case
        frame.
    score_col
        The score column ranked (``"score"`` for a result).
    """

    by: tuple[str, ...]
    view: str | None
    gamma: float
    volume: str
    global_mean: float
    norm_fingerprint: str | None
    score_col: str = "score"

    def to_dict(self) -> dict[str, Any]:
        """The specification as a JSON-ready mapping (``by`` as a list), with the tie policy."""
        return {
            "by": list(self.by),
            "view": self.view,
            "gamma": self.gamma,
            "volume": self.volume,
            "global_mean": self.global_mean,
            "norm_fingerprint": self.norm_fingerprint,
            "score_col": self.score_col,
            "tie_policy": TIE_POLICY,
        }


@dataclass(frozen=True, eq=False)
class Backlog:
    """A ranked slice backlog: :attr:`table` and the :attr:`spec` it was ranked with.

    ``table`` is indexed by the slice keys (unless ``prioritize(as_index=False)``),
    sorted by ``stable_PI``, with the columns documented in :func:`wise.prioritize`.
    """

    table: pd.DataFrame
    spec: BacklogSpec

    def __repr__(self) -> str:
        s = self.spec
        return (
            f"Backlog({len(self.table):,} slices by {list(s.by)}, view={s.view!r}, gamma={s.gamma:g}, "
            f"volume={s.volume!r}, global_mean={s.global_mean:.6g})"
        )
