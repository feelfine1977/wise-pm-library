"""Constraint catalogue: bounded violation signals ``ν_c(σ) ∈ [0, 1]`` (paper Section 4.2).

Every constraint maps a case ``σ`` to a violation in ``[0, 1]``, where 0 means
satisfied and 1 is the upper limit of the declared deviation scale. Graded
constraints share the threshold–saturation rule::

    sat(z; ϑ, W) = 0                     if z ≤ ϑ
                 = min((z − ϑ) / W, 1)   if z > ϑ        (W > 0)

Constraint objects are frozen dataclasses holding parameters only. Each type
belongs to a constraint family (:mod:`wise.family`, built-ins in
:mod:`wise.families`) that parses its parameters from a norm document, states
the inputs it reads and evaluates it on an :class:`~wise.log.EventLog`.

The five types of Section 4.2 are :class:`Presence`, :class:`Lag`,
:class:`Balance`, :class:`Singularity` (the occurrence limit) and
:class:`Exclusion`. :class:`Metric` applies the saturation rule to a numeric
case attribute; with threshold zero and width one it is the identity
constraint that carries a bounded case-level assessment supplied by an
application into a norm (end of Section 4.2).

An activity parameter accepts one label or a list of labels. A list is
treated as *one* merged activity: counts are summed and first timestamps are
taken as the minimum over the alternatives.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd

from .errors import NormError
from .family import CONSTRAINT_TYPES as CONSTRAINT_TYPES
from .family import TYPE_ALIASES as TYPE_ALIASES
from .family import family

Labels = tuple[str, ...]
Activities = str | Sequence[str]

TIME_UNITS: Mapping[str, str] = MappingProxyType(
    {
        "D": "D",
        "d": "D",
        "h": "h",
        "H": "h",
        "min": "min",
        "T": "min",
        "s": "s",
        "S": "s",
        "ms": "ms",
        "W": "W",
        "w": "W",
    }
)
"""Accepted spellings of a time unit, each mapped to its pandas unit (``"d"`` → ``"D"``)."""


def as_labels(x: str | Iterable[str] | None, *, what: str = "activities") -> Labels:
    """Normalise one label or an iterable of labels to a tuple of strings.

    A bare string is one label (it is *not* iterated character by character).
    """
    if x is None:
        raise NormError(f"{what} must be given")
    if isinstance(x, str):
        return (x,)
    try:
        out = tuple(str(v) for v in x)
    except TypeError as exc:
        raise NormError(f"{what} must be a label or a list of labels, got {x!r}") from exc
    if not out:
        raise NormError(f"empty {what}")
    return out


def as_list(x: Any) -> list[Any]:
    """A bare string or scalar becomes a one-element list; iterables become lists."""
    if x is None:
        return []
    if isinstance(x, str | bytes) or not isinstance(x, Iterable):
        return [x]
    return list(x)


def sat(z: Any, threshold: float, width: float) -> Any:
    """Threshold–saturation rule ``sat(z; ϑ, W)`` with ``W > 0`` (paper Section 4.2).

    Works on scalars, numpy arrays and pandas Series; NaN stays NaN.

    >>> sat(8, 10, 20), sat(15, 10, 20), sat(20, 10, 20), sat(30, 10, 20)
    (0.0, 0.25, 0.5, 1.0)
    """
    if isinstance(width, bool) or not np.isfinite(width) or width <= 0:
        raise NormError(f"sat: the saturation width must be a finite number > 0, got {width!r}")
    if isinstance(z, pd.Series):
        ser = pd.to_numeric(z, errors="coerce").astype(float)
        res = ((ser - threshold) / width).clip(0.0, 1.0)
        return res.where(ser.notna(), np.nan)
    arr = np.asarray(z, dtype=float)
    out = np.where(np.isnan(arr), np.nan, np.clip((arr - threshold) / width, 0.0, 1.0))
    return float(out) if np.ndim(out) == 0 else out


def in_units(delta: pd.Series, unit: str) -> pd.Series:
    """Express a Series of time differences in ``unit`` (NaT → NaN)."""
    seconds: pd.Series = delta.dt.total_seconds()
    return seconds / pd.Timedelta(f"1{TIME_UNITS[unit]}").total_seconds()


def _plain(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    return value


def _num(name: str, value: Any) -> float:
    """Coerce a constructor parameter once; strings and booleans are refused (a norm document's numeric strings are
    converted by its family before construction) so a mistyped value cannot pass as a number."""
    if value is None or isinstance(value, bool | str | bytes):
        raise NormError(f"{name} must be a number, got {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise NormError(f"{name} must be a number, got {value!r}") from exc


def _nonneg(name: str, value: Any) -> float:
    number = _num(name, value)
    if not np.isfinite(number) or number < 0:
        raise NormError(f"{name} must be a finite number >= 0, got {value!r}")
    return number


def _pos(name: str, value: Any) -> float:
    number = _num(name, value)
    if not np.isfinite(number) or number <= 0:
        raise NormError(f"{name} must be a finite number > 0, got {value!r}")
    return number


def _count(name: str, value: Any, minimum: int) -> int:
    number = _num(name, value)
    if not np.isfinite(number) or number != int(number) or number < minimum:
        raise NormError(f"{name} must be an integer >= {minimum}, got {value!r}")
    return int(number)


@dataclass(frozen=True)
class Constraint:
    """Base class. Subclasses define ``type`` and their parameters."""

    type: ClassVar[str] = "abstract"

    def params(self) -> dict[str, Any]:
        """Parameters as a JSON-friendly mapping (tuples become lists)."""
        return {f.name: _plain(getattr(self, f.name)) for f in fields(self)}

    def activities(self) -> Labels:
        """All activity labels referenced by this constraint."""
        return ()

    def describe(self) -> str:
        return f"{self.type}({', '.join(f'{k}={v!r}' for k, v in self.params().items())})"


@dataclass(frozen=True)
class Presence(Constraint):
    """``(pres, a, m)``: activity ``a`` must occur at least ``m`` times.

    ``ν = 1 − min(cnt(a, σ) / m, 1)``; for ``m = 1`` an indicator.
    """

    type: ClassVar[str] = "presence"
    activity: Activities
    m: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "activity", as_labels(self.activity, what="activity"))
        object.__setattr__(self, "m", _count("presence: m", self.m, 1))

    def activities(self) -> Labels:
        return as_labels(self.activity)


@dataclass(frozen=True)
class Exclusion(Constraint):
    """``(excl, a)``: activity ``a`` must not occur. ``ν = 1[cnt(a, σ) > 0]``."""

    type: ClassVar[str] = "exclusion"
    activity: Activities

    def __post_init__(self) -> None:
        object.__setattr__(self, "activity", as_labels(self.activity, what="activity"))

    def activities(self) -> Labels:
        return as_labels(self.activity)


@dataclass(frozen=True)
class Singularity(Constraint):
    """Occurrence limit ``(sing, a, k, K)``: up to ``k`` occurrences are tolerated.

    ``ν = min(max(0, cnt(a, σ) − k) / K, 1)``, i.e. ``sat(cnt; k, K)``.
    """

    type: ClassVar[str] = "singularity"
    activity: Activities
    k: int = 1
    K: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "activity", as_labels(self.activity, what="activity"))
        object.__setattr__(self, "k", _count("singularity: k", self.k, 0))
        object.__setattr__(self, "K", _pos("singularity: K", self.K))

    def activities(self) -> Labels:
        return as_labels(self.activity)


@dataclass(frozen=True)
class Lag(Constraint):
    """``(lag, a, b, δ, Δ)``: after the first ``a``, the first subsequent ``b``
    should occur within ``delta`` time units; the violation saturates once the
    lag reaches ``delta + width``.

    ``t_a = t1(a, σ)`` (first ``a``), ``t_b = min{ts(e) | act(e) = b, ts(e) ≥ t_a}``
    (first ``b`` at or after it), ``ν = sat(t_b − t_a; δ, Δ)``. The rule checks
    the earliest ``a`` and the earliest ``b`` at or after it; it neither
    forbids earlier occurrences of ``b`` nor checks every occurrence pair.

    A lag states its bound: ``delta`` and ``width`` have no default.

    Parameters
    ----------
    delta, width, unit
        Threshold ``δ ≥ 0`` and saturation width ``Δ > 0`` in ``unit``
        (``"D"`` days, ``"h"``, ``"min"``, ``"s"``, ``"ms"``, ``"W"``).
    missing_a
        ``"violate"`` (default): ν = 1 when ``a`` never occurs, which holds
        where the declared observation scope makes absence assessable.
        ``"skip"``: the constraint has no value for such a case (evidence
        unavailable).
    missing_b
        ``"violate"`` (default): ν = 1 when ``a`` occurs but no ``b`` follows
        it. ``"skip"``: the constraint has no value for such a case.
    """

    type: ClassVar[str] = "lag"
    a: Activities
    b: Activities
    delta: float
    width: float
    unit: str = "D"
    missing_a: Literal["violate", "skip"] = "violate"
    missing_b: Literal["violate", "skip"] = "violate"

    def __post_init__(self) -> None:
        object.__setattr__(self, "a", as_labels(self.a, what="a"))
        object.__setattr__(self, "b", as_labels(self.b, what="b"))
        object.__setattr__(self, "delta", _nonneg("lag: delta", self.delta))
        object.__setattr__(self, "width", _pos("lag: width", self.width))
        if self.unit not in TIME_UNITS:
            raise NormError(f"lag: unit must be one of {sorted(set(TIME_UNITS.values()))}, got {self.unit!r}")
        object.__setattr__(self, "unit", TIME_UNITS[self.unit])
        if self.missing_a not in ("violate", "skip"):
            raise NormError("lag: missing_a must be 'violate' or 'skip'")
        if self.missing_b not in ("violate", "skip"):
            raise NormError("lag: missing_b must be 'violate' or 'skip'")

    def activities(self) -> Labels:
        return as_labels(self.a) + as_labels(self.b)


@dataclass(frozen=True)
class Balance(Constraint):
    """``(bal, α_x, A_x, α_y, A_y, τ, Γ)``: two non-negative case-level totals must agree.

    ``tot_x = Σ attr_x over events with act ∈ A_x`` (likewise ``tot_y``),
    ``d = |tot_x − tot_y| / max(tot_x, tot_y, ε)``, ``ν = sat(d; τ, Γ)``.

    The sum over an empty set of events is 0, so a side without events yields
    ``d = 1`` unless both sides are empty (then ``d = 0``). A selected event
    whose value is missing or not numeric makes that total, and so the
    constraint, unavailable for the case: a missing value is never replaced
    by zero (Section 4.1). Scoring refuses negative totals.
    """

    type: ClassVar[str] = "balance"
    attr_x: str
    activities_x: Activities
    attr_y: str
    activities_y: Activities
    tau: float = 0.0
    width: float = 1.0
    eps: float = 1e-9

    def __post_init__(self) -> None:
        object.__setattr__(self, "activities_x", as_labels(self.activities_x, what="activities_x"))
        object.__setattr__(self, "activities_y", as_labels(self.activities_y, what="activities_y"))
        tau = _num("balance: tau", self.tau)
        if not (0.0 <= tau <= 1.0):
            raise NormError(f"balance: tau must be in [0, 1], got {self.tau!r}")
        object.__setattr__(self, "tau", tau)
        object.__setattr__(self, "width", _pos("balance: width", self.width))
        object.__setattr__(self, "eps", _pos("balance: eps", self.eps))

    def activities(self) -> Labels:
        return as_labels(self.activities_x) + as_labels(self.activities_y)


@dataclass(frozen=True)
class Metric(Constraint):
    """The saturation rule on a numeric case attribute: ``ν = sat(att(σ); ϑ, W)``.

    A case whose attribute is missing or not numeric has no value. With
    ``threshold=0`` and ``width=1`` the constraint preserves a deviation value
    in ``[0, 1]`` that an application supplies (end of Section 4.2).
    """

    type: ClassVar[str] = "metric"
    attribute: str
    threshold: float = 0.0
    width: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.attribute, str) or not self.attribute:
            raise NormError("metric: attribute must be the name of a case attribute")
        threshold = _num("metric: threshold", self.threshold)
        if not np.isfinite(threshold):
            raise NormError("metric: threshold must be finite")
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(self, "width", _pos("metric: width", self.width))


def constraint_from_dict(type_name: str, params: Mapping[str, Any]) -> Constraint:
    """Build a constraint from its type name and a parameter mapping.

    The family registered under ``type_name`` (or one of its aliases, see
    :mod:`wise.family`) parses the parameters. Unknown types and unknown
    parameters raise :class:`NormError`; numeric parameters given as strings
    are converted, and the constructor then refuses what is out of range,
    including a non-integer count such as ``m=1.5``.
    """
    constraint: Constraint = family(type_name).parse(params)
    return constraint
