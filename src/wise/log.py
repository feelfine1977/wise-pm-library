"""Event log wrapper and vectorised case-level primitives (paper Section 4.1).

:class:`EventLog` validates a case-based log held in a pandas DataFrame,
parses timestamps, fixes the case notion, and exposes the primitives the
constraint semantics are written in:

* ``cnt(a, σ)``                  → :meth:`EventLog.count`
* ``t1(a, σ)``                   → :meth:`EventLog.first_ts`
* first ``b`` at or after the first ``a`` → :meth:`EventLog.first_after`
* ``tot_α(A, σ)``                → :meth:`EventLog.total`
* ``att_β(σ)``, ``exp(σ)``       → :attr:`EventLog.cases`

Internally the log is held by an immutable :class:`~wise.case_index.CaseIndex`
(:attr:`EventLog.case_index`): integer case codes and activity codes sorted
by ``(case, timestamp, order)``; every primitive is a numpy operation on
those codes.

Input that cannot form a log is refused with a
:class:`~wise.errors.LogSchemaError` that names the problem: a missing column,
a frame without rows, a null case id, unparseable timestamps under the
``"raise"`` policy, negative exposure, a log whose missing-timestamp filter
leaves no event, and case attributes that vary within a case under the
``"strict"`` policy.

Column names default to the XES conventions ``case:concept:name``,
``concept:name`` and ``time:timestamp``.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, Literal, TypeVar

import numpy as np
import pandas as pd

from .case_index import NAT, CaseIndex, event_order
from .constraints import Labels, as_labels, as_list
from .errors import LogSchemaError

__all__ = ["ACTIVITY_COL", "CASE_COL", "EXPOSURE_AGGREGATIONS", "TIMESTAMP_COL", "EventLog"]

CASE_COL = "case:concept:name"
ACTIVITY_COL = "concept:name"
TIMESTAMP_COL = "time:timestamp"

EXPOSURE_AGGREGATIONS: tuple[str, ...] = ("max", "sum", "first", "last", "min", "mean", "median")
"""How the exposure column may be aggregated per case: ``"max"`` (default) suits
cumulative amounts, ``"sum"`` per-event amounts and ``"first"`` constant attributes."""

_RESERVED = {"n_events", "first_ts", "last_ts", "exposure", "score"}
_INT_MAX = np.iinfo(np.int64).max
_PANDAS_3 = int(pd.__version__.split(".")[0]) >= 3

_Pandas = TypeVar("_Pandas", pd.DataFrame, pd.Series)


def _copy(frame: _Pandas) -> _Pandas:
    """A copy of ``frame`` whose changes do not reach ``frame``: shallow under
    copy-on-write (always on from pandas 3), which copies no data until it is
    written to; a full copy otherwise, since pandas 2 shares the data."""
    return frame.copy(deep=not (_PANDAS_3 or pd.options.mode.copy_on_write is True))


def _check_attribute_name(name: str) -> None:
    """Refuse a case attribute name that collides with a computed column."""
    if name in _RESERVED or name.startswith(("contrib__", "score__")):
        raise LogSchemaError(
            f"{name!r} is reserved for computed columns; rename the attribute "
            f"(reserved: {sorted(_RESERVED)}, prefixes 'contrib__' and 'score__')"
        )


def _parse_timestamps(raw: pd.Series, column: str, *, utc: bool, timestamp_format: str | None, dayfirst: bool) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(raw):
        if not utc:
            return raw
        return raw.dt.tz_convert("UTC") if raw.dt.tz is not None else raw.dt.tz_localize("UTC")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        warnings.simplefilter("ignore", UserWarning)
        ts = pd.to_datetime(raw, errors="coerce", utc=utc, format=timestamp_format, dayfirst=dayfirst)
        retry = ts.isna() & raw.notna()
        if retry.any() and pd.api.types.is_datetime64_any_dtype(ts):
            again = pd.to_datetime(raw[retry], errors="coerce", utc=utc, format="mixed", dayfirst=dayfirst)
            if pd.api.types.is_datetime64_any_dtype(again) and (again.dt.tz is None) == (ts.dt.tz is None):
                ts = ts.copy()
                ts[retry] = again
    if not pd.api.types.is_datetime64_any_dtype(ts):
        raise LogSchemaError(f"timestamp column {column!r} has mixed time zones or types; pass utc=True")
    return ts


class EventLog:
    """A case-based event log.

    Parameters
    ----------
    events
        One row per event. The frame is not modified.
    case_col, activity_col, timestamp_col
        Column names (XES defaults).
    case_attributes
        Case-level attribute columns (company, spend area, flow type, ...).
        These become the slice keys and the applicability attributes.
    exposure_col, exposure_agg
        Optional numeric column recording business exposure ``exp(σ) ≥ 0``,
        aggregated per case with ``exposure_agg`` (one of
        :data:`EXPOSURE_AGGREGATIONS`). Cases without a numeric value get
        exposure 0.
    order_col
        Column that orders events sharing a timestamp (an event id or a
        sequence number); it determines the order of traces. Constraint
        semantics compare timestamps, so events with equal timestamps are
        simultaneous for them. Default: the input row order.
    utc
        Convert timestamps to UTC (required for strings with mixed offsets).
    timestamp_format, dayfirst
        Passed to :func:`pandas.to_datetime` when the column holds strings
        (e.g. ``timestamp_format="%d-%m-%Y %H:%M:%S"`` or ``dayfirst=True``).
    missing_timestamps
        ``"raise"`` (default) if any timestamp is null or unparseable,
        ``"drop"`` those events, or ``"keep"`` them without a timestamp. A
        kept event counts for presence, exclusion and occurrence-limit
        constraints and for totals; it never defines a first or last
        timestamp or a lag, and sorts last in its case.
    case_attribute_values
        ``"first_non_null"`` (default): the value of a case attribute is its
        first non-null value in event order; the attributes that vary within
        a case are recorded in :attr:`varying_case_attributes`. ``"strict"``:
        a log in which an attribute takes two values within one case is
        refused with the attributes named.

    :attr:`events` and :attr:`cases` hand out copies: what is done to them
    changes no later answer of the log.
    """

    def __init__(
        self,
        events: pd.DataFrame,
        *,
        case_col: str = CASE_COL,
        activity_col: str = ACTIVITY_COL,
        timestamp_col: str = TIMESTAMP_COL,
        case_attributes: str | Iterable[str] = (),
        exposure_col: str | None = None,
        exposure_agg: str = "max",
        order_col: str | None = None,
        utc: bool = False,
        timestamp_format: str | None = None,
        dayfirst: bool = False,
        missing_timestamps: Literal["raise", "drop", "keep"] = "raise",
        case_attribute_values: Literal["first_non_null", "strict"] = "first_non_null",
    ):
        attributes = [str(a) for a in as_list(case_attributes)]
        for attr in attributes:
            _check_attribute_name(attr)
        if missing_timestamps not in ("raise", "drop", "keep"):
            raise LogSchemaError(f"missing_timestamps must be one of ['raise', 'drop', 'keep'], got {missing_timestamps!r}")
        if case_attribute_values not in ("first_non_null", "strict"):
            raise LogSchemaError(
                f"case_attribute_values must be one of ['first_non_null', 'strict'], got {case_attribute_values!r}"
            )
        if exposure_agg not in EXPOSURE_AGGREGATIONS:
            raise LogSchemaError(f"exposure_agg must be one of {list(EXPOSURE_AGGREGATIONS)}, got {exposure_agg!r}")
        required = [case_col, activity_col, timestamp_col, *attributes, *(c for c in (exposure_col, order_col) if c is not None)]
        missing = [c for c in required if c not in events.columns]
        if missing:
            raise LogSchemaError(
                f"event log is missing columns {missing}; available: {list(events.columns)[:30]}"
                + (" ..." if events.shape[1] > 30 else "")
            )
        if len(events) == 0:
            raise LogSchemaError("the event frame has no rows; an event log needs at least one event")

        df = events
        # ---- case ids -------------------------------------------------------------------
        case_series = df[case_col]
        n_null_case = int(case_series.isna().sum())
        if n_null_case:
            raise LogSchemaError(f"{n_null_case} events have a null case id; drop or fill them first")
        if isinstance(case_series.dtype, pd.CategoricalDtype):
            case_series = case_series.astype(case_series.cat.categories.dtype)
        codes, uniques = pd.factorize(case_series, sort=True)
        codes = codes.astype(np.int64)

        # ---- timestamps -----------------------------------------------------------------
        ts_raw = df[timestamp_col]
        ts = _parse_timestamps(ts_raw, timestamp_col, utc=utc, timestamp_format=timestamp_format, dayfirst=dayfirst)
        n_missing_ts = int(ts.isna().sum())
        if n_missing_ts and missing_timestamps == "raise":
            first_bad = ts_raw[ts.isna()].iloc[0]
            raise LogSchemaError(
                f"{n_missing_ts} timestamps are null or unparseable (first: {first_bad!r}); "
                "pass missing_timestamps='drop' or 'keep', or utc=True for mixed offsets"
            )
        if n_missing_ts and missing_timestamps == "drop":
            if n_missing_ts == len(ts):
                raise LogSchemaError(
                    f"every event has a null or unparseable timestamp in column {timestamp_col!r}; "
                    "missing_timestamps='drop' would leave no event"
                )
            keep_mask = ts.notna().to_numpy()
            df, ts, codes = df[keep_mask], ts[keep_mask], codes[keep_mask]
            codes, uniques = pd.factorize(pd.Series(uniques[codes]), sort=True)
            codes = codes.astype(np.int64)
            n_missing_ts = 0
        tz = ts.dt.tz
        ts_int = (
            ts.to_numpy("datetime64[ns]").view("int64")
            if tz is None
            else ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy("datetime64[ns]").view("int64")
        )

        # ---- order: (case, timestamp, tie-break) ------------------------------------------
        tie = pd.factorize(df[order_col], sort=True)[0] if order_col is not None else None
        order = event_order(codes, ts_int, tie)
        n_cases = len(uniques)

        ev = df.iloc[order].reset_index(drop=True)
        ev[timestamp_col] = ts.to_numpy()[order] if tz is None else ts.iloc[order].reset_index(drop=True)

        act = ev[activity_col]
        n_null_activities = int(act.isna().sum())
        if isinstance(act.dtype, pd.CategoricalDtype):
            act_codes = act.cat.codes.to_numpy().astype(np.int64)
            act_labels = pd.Index(act.cat.categories.astype(str))
        else:
            act_codes, act_uniques = pd.factorize(act, sort=False)
            act_codes = act_codes.astype(np.int64)
            act_labels = pd.Index(pd.Index(act_uniques).astype(str))
        sorted_codes, sorted_ts = codes[order], ts_int[order]
        sorted_codes.flags.writeable = sorted_ts.flags.writeable = False  # the index keeps views of them
        index = CaseIndex(sorted_codes, sorted_ts, act_codes, act_labels, n_cases=n_cases, tz=tz)

        # ---- case table -----------------------------------------------------------------
        cases = pd.DataFrame(index=pd.Index(uniques, name=case_col))
        cases["n_events"] = index.count()
        cases["first_ts"] = index.to_datetime(index.first())
        cases["last_ts"] = index.to_datetime(index.last())
        varying: dict[str, int] = {}
        for attr in attributes:
            by_case = ev[attr].groupby(index.case_codes)
            n_varying = int((by_case.nunique(dropna=True) > 1).sum())
            if n_varying:
                varying[attr] = n_varying
            cases[attr] = by_case.first().reindex(range(n_cases)).to_numpy()
        if varying and case_attribute_values == "strict":
            named = ", ".join(f"{attr!r} ({n} case{'s' if n > 1 else ''})" for attr, n in varying.items())
            raise LogSchemaError(
                f"case attributes vary within a case: {named}; clean them first, or set "
                "case_attribute_values='first_non_null' to take the first non-null value"
            )
        if exposure_col is not None:
            vals = pd.to_numeric(ev[exposure_col], errors="coerce")
            per_case = vals.groupby(index.case_codes).agg(exposure_agg)
            exp = per_case.reindex(range(n_cases)).fillna(0.0).to_numpy()
            if (exp < 0).any():
                raise LogSchemaError(
                    f"exposure column {exposure_col!r} yields negative case exposure for "
                    f"{int((exp < 0).sum())} cases; the method assumes exp(σ) >= 0"
                )
            cases["exposure"] = exp.astype(float)

        self._events = ev
        self._index = index
        self._cases = cases
        self._case_attributes = attributes
        self.tz = tz
        self.case_col, self.activity_col, self.timestamp_col = case_col, activity_col, timestamp_col
        self.exposure_col, self.order_col = exposure_col, order_col
        self.n_missing_timestamps = n_missing_ts
        self.n_null_activities = n_null_activities
        self._varying: Mapping[str, int] = MappingProxyType(varying)
        self._count_cache: dict[Labels, pd.Series] = {}
        self._first_cache: dict[Labels, pd.Series] = {}

    # ------------------------------------------------------------------ basics
    def __len__(self) -> int:
        return self._index.n_cases

    def __repr__(self) -> str:
        return (
            f"EventLog({len(self._events):,} events, {len(self):,} cases, "
            f"{len(self._index.activity_labels)} activities, attributes={self._case_attributes})"
        )

    @property
    def events(self) -> pd.DataFrame:
        """The events in the order of :attr:`case_index` (by case, timestamp and
        order). A copy: changing it does not change the log."""
        return _copy(self._events)

    @property
    def cases(self) -> pd.DataFrame:
        """The case table (index = case id): ``n_events``, ``first_ts``,
        ``last_ts``, the case attributes, then ``exposure`` if the log has
        one. A copy: changing it does not change the log."""
        return _copy(self._cases)

    @property
    def case_attributes(self) -> list[str]:
        """Names of the case attributes. A copy."""
        return list(self._case_attributes)

    @property
    def varying_case_attributes(self) -> Mapping[str, int]:
        """Each case attribute that takes more than one non-null value within a
        case, with the number of such cases (read-only)."""
        return self._varying

    @property
    def case_index(self) -> CaseIndex:
        """The immutable per-case index the primitives are computed on; its
        events are in the row order of :attr:`events`."""
        return self._index

    @property
    def case_ids(self) -> pd.Index:
        return self._cases.index

    @property
    def activity_labels(self) -> list[str]:
        return list(self._index.activity_labels)

    def _series_dt(self, values: np.ndarray) -> pd.Series:
        return pd.Series(self._index.to_datetime(values), index=self.case_ids)

    def _series(self, values: np.ndarray) -> pd.Series:
        return pd.Series(values, index=self.case_ids)

    # ------------------------------------------------------------------ primitives
    def count(self, activities: str | Iterable[str]) -> pd.Series:
        """``cnt(a, σ)``: occurrences of any of ``activities`` per case."""
        labels = as_labels(activities)
        key = tuple(sorted(labels))
        if key not in self._count_cache:
            self._count_cache[key] = self._series(self._index.count(labels).astype(float))
        return _copy(self._count_cache[key])

    def first_ts(self, activities: str | Iterable[str]) -> pd.Series:
        """``t1(a, σ)``: timestamp of the first occurrence, NaT if none."""
        labels = as_labels(activities)
        key = tuple(sorted(labels))
        if key not in self._first_cache:
            self._first_cache[key] = self._series_dt(self._index.first(labels))
        return _copy(self._first_cache[key])

    def first_after(self, a: str | Iterable[str], b: str | Iterable[str]) -> tuple[pd.Series, pd.Series]:
        """``t_a`` (the first ``a``) and ``t_b`` (the first ``b`` at or after it).

        ``t_b`` is NaT when ``a`` never occurs or no ``b`` follows it.
        """
        idx = self._index
        la, lb = as_labels(a, what="a"), as_labels(b, what="b")
        t_a_int = idx.first(la)
        anchor = np.where(t_a_int == NAT, _INT_MAX, t_a_int)
        mask_b = idx.mask(lb) & (idx.timestamps >= anchor[idx.case_codes])
        return self._series_dt(t_a_int), self._series_dt(idx.first(mask_b))

    def total(self, attribute: str, activities: str | Iterable[str]) -> pd.Series:
        """``tot_α(A, σ)``: sum of ``attribute`` over the events with act ∈ A.

        The sum over an empty set of events is 0. If a selected event has a
        missing or non-numeric value, the total of its case is unavailable
        (NaN); a missing value is not replaced by zero (Section 4.1).
        """
        if attribute not in self._events.columns:
            raise LogSchemaError(f"event attribute {attribute!r} not in log")
        vals = pd.to_numeric(self._events[attribute], errors="coerce").to_numpy(dtype=float)
        return self._series(self._index.total(vals, as_labels(activities)))

    def attribute(self, name: str) -> pd.Series:
        """Numeric case attribute from :attr:`cases`, NaN where missing or not numeric."""
        if name not in self._cases.columns:
            raise LogSchemaError(f"case attribute {name!r} not available; pass it via case_attributes")
        return pd.to_numeric(self._cases[name], errors="coerce")

    def trace(self, case_id: Any) -> pd.DataFrame:
        """Events of one case in timestamp order (for drill-down). A copy, as
        :attr:`events` is."""
        if case_id not in self.case_ids:
            raise LogSchemaError(f"unknown case id {case_id!r}")
        pos = self.case_ids.get_loc(case_id)
        i = int(pos)
        start = int(self._index.starts[i])
        return _copy(self._events.iloc[start : start + int(self._index.sizes[i])])
