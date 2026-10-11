"""Phase 3: slice-first prioritisation and the Priority Index (paper Section 4.5).

For a view ``p`` and slicing function ``g`` (a list of case-attribute
columns), over the scored cases only:

* slice mean ``μ_s`` and the comparison reference ``μ̄``, the unweighted mean
  score of the full scored population,
* Priority Index ``PI_s = n_s · (μ̄ − μ_s)_+`` (or ``E_s`` for exposure),
* shrinkage-stabilised mean ``μ̃_s = n_s/(n_s+γ) μ_s + γ/(n_s+γ) μ̄`` and the
  stabilised index ``PĨ_s = v_s · (μ̄ − μ̃_s)_+``,
* the signed layer contributions to the aggregate penalty gap,
  ``J_λ,s = v_s ρ_s (Δ̄_λ,s − Δ̄_λ)`` with ``ρ_s = n_s/(n_s+γ)``, whose sum
  clipped at zero is the stabilised index (Appendix A.3).

Because ``μ̄ − μ̃_s = n_s/(n_s+γ) · (μ̄ − μ_s)``, the stabilised gap is the raw
gap scaled by ``n_s/(n_s+γ)``: a slice with ``n_s = γ`` keeps half of its
observed gap.

:func:`prioritize` returns a :class:`~wise.backlog.Backlog`: the ranked table
plus the specification it was ranked with. All aggregations are indexed by the
slice key(s) so they can be joined with ``.loc``. A case without a value for a
slice key falls in the slice labelled :data:`MISSING_KEY`, which ranks after
every keyed slice on a tie.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

import numpy as np
import pandas as pd

from .backlog import Backlog, BacklogSpec
from .constraints import as_list
from .errors import NormError, NotScoredError
from .scoring import ScoreResult

__all__ = ["MISSING_KEY", "layer_contributions", "layer_drivers", "prioritize", "top_k_overlap"]


def _keys(by: str | Sequence[str]) -> list[str]:
    return [by] if isinstance(by, str) else list(by)


def _frame(data: ScoreResult | pd.DataFrame, view: str | None, score_col: str, by: Sequence[str]) -> tuple[pd.DataFrame, str]:
    if isinstance(data, ScoreResult):
        if view is None:
            if len(data.views) != 1:
                raise NormError(f"specify view=...; available: {data.views}")
            view = data.views[0]
        df, score_col = data.frame(view), "score"
    else:
        if score_col not in data.columns:
            raise NormError(f"score column {score_col!r} not in frame")
        df = data
    index_names = [n for n in df.index.names if n]
    clash = [n for n in index_names if n in df.columns]
    if any(c not in df.columns and c in index_names for c in by):
        df = df.drop(columns=clash).reset_index() if clash else df.reset_index()
    elif any(c in clash for c in by):
        df = df.reset_index(drop=True)
    missing = [c for c in by if c not in df.columns]
    if missing:
        raise NormError(f"slice columns not in frame: {missing}")
    return df, score_col


MISSING_KEY = "(missing)"
"""The label of a slice key a case has no value for; a slice key never becomes a NaN index entry."""


def _label_missing(df: pd.DataFrame, by: Sequence[str]) -> tuple[pd.DataFrame, bool]:
    """``df`` with every missing value of a slice key replaced by :data:`MISSING_KEY`, and whether a key was labelled.

    A categorical key gains the label as its last category; another key column becomes ``object``
    unless it holds strings. A key that already has the value :data:`MISSING_KEY` next to missing
    values is refused, since the two slices could not be told apart.
    """
    labelled: dict[str, pd.Series] = {}
    for col in by:
        values = df[col]
        if not values.isna().any():
            continue
        categorical = isinstance(values.dtype, pd.CategoricalDtype)
        if (MISSING_KEY in values.cat.categories) if categorical else (values == MISSING_KEY).any():
            raise NormError(f"slice column {col!r} has missing values and the value {MISSING_KEY!r}, which labels them")
        if categorical:
            labelled[col] = values.cat.add_categories([MISSING_KEY]).fillna(MISSING_KEY)
        else:
            base = values if pd.api.types.is_string_dtype(values.dtype) else values.astype(object)
            labelled[col] = base.where(values.notna(), MISSING_KEY)
    return (df.assign(**labelled), True) if labelled else (df, False)


def _missing_last(level: pd.Index) -> pd.Index:
    """Sort key of one slice-key level: key order, the missing label last (categories keep their order)."""
    if isinstance(level.dtype, pd.CategoricalDtype):
        return level
    return pd.Index([(isinstance(v, str) and v == MISSING_KEY, v) for v in level], tupleize_cols=False)


_Table = TypeVar("_Table", pd.DataFrame, "pd.Series[Any]")


def _sort_slices(frame: _Table, labelled: bool) -> _Table:
    """``frame`` in slice-key order; with a labelled missing key that slice comes last."""
    return frame.sort_index(key=_missing_last) if labelled else frame.sort_index()


def _check_gamma(gamma: Any) -> float:
    try:
        value = float(gamma)
    except (TypeError, ValueError) as exc:
        raise NormError(f"gamma must be a finite number >= 0, got {gamma!r}") from exc
    if not np.isfinite(value) or value < 0:
        raise NormError(f"gamma must be a finite number >= 0, got {gamma!r}")
    return value


def _volume_column(volume: str, frame: pd.DataFrame) -> str | None:
    column = None if volume == "cases" else ("exposure" if volume == "exposure" else volume)
    if column is not None and column not in frame.columns:
        raise NormError(f"volume column {column!r} not in frame")
    return column


def prioritize(
    data: ScoreResult | pd.DataFrame,
    by: str | Sequence[str],
    view: str | None = None,
    gamma: float = 0.0,
    volume: str = "cases",
    score_col: str = "score",
    as_index: bool = True,
) -> Backlog:
    """Aggregate scored cases into a ranked slice backlog (the prioritised investigation list).

    Parameters
    ----------
    data
        A :class:`~wise.scoring.ScoreResult` (then ``view`` selects the score)
        or a per-case DataFrame with the slice columns and ``score_col``.
    by
        Slice key column(s), e.g. ``["company", "spend_area"]``. A single
        column such as the purchasing document gives the document backlog;
        the case id (the frame's index) is allowed too.
    gamma
        Shrinkage constant ``γ ≥ 0``; 0 applies no adjustment for small slices.
    volume
        ``"cases"`` (``v_s = n_s``), ``"exposure"`` (``v_s = E_s``, needs an
        ``exposure`` column), or the name of a numeric per-case column to sum.

    Only cases with a score enter the slice means, the counts and the
    comparison reference; a slice without a scored case is not ranked.

    Returns
    -------
    A :class:`~wise.backlog.Backlog`. Its ``table`` is a DataFrame indexed by
    ``by`` (unless ``as_index=False``), sorted by ``stable_PI`` (ties: larger
    ``n_cases`` first, then key order, the :data:`MISSING_KEY` slice last),
    with ``n_cases, mean_score, volume, [exposure], gap, PI, stable_mean,
    stable_gap, stable_PI, global_mean``. Its ``spec`` holds the slice keys,
    the view, ``gamma``, ``volume``, the comparison reference, the score
    column and the norm fingerprint.
    """
    by = _keys(by)
    gamma = _check_gamma(gamma)
    df, score_col = _frame(data, view, score_col, by)
    df, labelled = _label_missing(df, by)
    if isinstance(data, ScoreResult):
        view = view if view is not None else data.views[0]
        fingerprint: str | None = data.norm_fingerprint or None
    else:
        view, fingerprint = None, None
    d = df.dropna(subset=[score_col])
    if d.empty:
        raise NotScoredError("no scored cases to aggregate")
    mu_bar = float(d[score_col].mean())
    vol_col = _volume_column(volume, d)

    g = d.groupby(by, dropna=False, observed=True, sort=True)
    agg = g[score_col].agg(n_cases="size", mean_score="mean")
    agg["volume"] = g[vol_col].sum().astype(float) if vol_col is not None else agg["n_cases"].astype(float)
    if "exposure" in d.columns:
        agg["exposure"] = g["exposure"].sum().astype(float)
    if vol_col is not None and (agg["volume"] < 0).any():
        raise NormError(f"volume column {vol_col!r} sums to a negative value for some slices")

    n = agg["n_cases"].astype(float)
    agg["gap"] = (mu_bar - agg["mean_score"]).clip(lower=0.0)
    agg["PI"] = agg["volume"] * agg["gap"]
    shrink = n / (n + gamma) if gamma > 0 else pd.Series(1.0, index=agg.index)
    agg["stable_mean"] = shrink * agg["mean_score"] + (1.0 - shrink) * mu_bar
    agg["stable_gap"] = (mu_bar - agg["stable_mean"]).clip(lower=0.0)
    agg["stable_PI"] = agg["volume"] * agg["stable_gap"]
    agg["global_mean"] = mu_bar

    agg = _sort_slices(agg, labelled).sort_values(["stable_PI", "n_cases"], ascending=[False, False], kind="mergesort")
    spec = BacklogSpec(
        by=tuple(by),
        view=view,
        gamma=gamma,
        volume=volume,
        global_mean=mu_bar,
        norm_fingerprint=fingerprint,
        score_col=score_col,
    )
    return Backlog(agg if as_index else agg.reset_index(), spec)


def _from_backlog(data: ScoreResult | pd.DataFrame, backlog: Backlog, view: str | None) -> tuple[list[str], str | None]:
    """Slice keys and view of a backlog record, checked against the scores they are used with.

    A record ranked on another norm, or a view given that is not the record's, is refused.
    """
    spec = backlog.spec
    if view is not None and spec.view is not None and view != spec.view:
        raise NormError(f"view {view!r} differs from the backlog's view {spec.view!r}")
    if (
        isinstance(data, ScoreResult)
        and spec.norm_fingerprint is not None
        and data.norm_fingerprint
        and spec.norm_fingerprint != data.norm_fingerprint
    ):
        raise NormError(
            f"the backlog was ranked on another norm (fingerprint {spec.norm_fingerprint[:12]}…, "
            f"result {data.norm_fingerprint[:12]}…)"
        )
    return list(spec.by), view if spec.view is None else spec.view


def _layer_means(
    data: ScoreResult | pd.DataFrame, by: Sequence[str], view: str | None, layers: Sequence[str] | None
) -> tuple[pd.DataFrame, pd.Series, list[str], Any]:
    """Per slice (in slice-key order) the mean layer contributions of its scored cases, the population means, the
    layer columns, and the grouped scored cases."""
    df, score_col = _frame(data, view, "score", by)
    df, labelled = _label_missing(df, by)
    prefix = "contrib__"
    if isinstance(data, ScoreResult):
        layer_cols = [f"{prefix}{layer}" for layer in (as_list(layers) or data.norm.layer_ids)]
    else:
        layer_cols = [c for c in df.columns if c.startswith(prefix)]
    if not layer_cols:
        raise NormError("no contrib__<layer> columns in frame")
    unknown = [c for c in layer_cols if c not in df.columns]
    if unknown:
        raise NormError(f"unknown layers: {[c[len(prefix) :] for c in unknown]}")
    d = df.dropna(subset=[score_col])
    if d.empty:
        raise NotScoredError("no scored cases to aggregate")
    global_mean = d[layer_cols].mean()
    g = d.groupby(list(by), dropna=False, observed=True, sort=True)
    out = g[layer_cols].mean()
    out.insert(0, "n_cases", g.size())
    if labelled:
        out = _sort_slices(out, labelled)
    return out, global_mean, layer_cols, g


def layer_drivers(
    data: ScoreResult | pd.DataFrame,
    by: str | Sequence[str] | Backlog,
    view: str | None = None,
    layers: Sequence[str] | None = None,
    as_index: bool = True,
) -> pd.DataFrame:
    """Mean layer contribution ``Δ̄_λ,s`` per slice and its difference to the population mean ``Δ̄_λ``.

    ``by`` is the slice key(s) or a backlog record from :func:`prioritize`,
    whose slice keys and view are used (a record ranked on another norm is
    refused). Returns a DataFrame indexed by slice with ``n_cases``, per layer
    ``<layer>`` (mean contribution) and ``<layer>__delta`` (minus the
    population mean), and ``dominant_layer`` (the largest positive
    difference). Both means include every scored case of their population,
    zero contributions included.
    """
    by, view = _from_backlog(data, by, view) if isinstance(by, Backlog) else (_keys(by), view)
    out, global_mean, layer_cols, _ = _layer_means(data, by, view, layers)
    prefix = "contrib__"
    deltas = out[layer_cols] - global_mean
    for col in layer_cols:
        out[f"{col[len(prefix) :]}__delta"] = deltas[col]
    out = out.rename(columns={c: c[len(prefix) :] for c in layer_cols})
    delta_cols = [f"{c[len(prefix) :]}__delta" for c in layer_cols]
    best = out[delta_cols].idxmax(axis=1).astype(str).str.replace("__delta", "", regex=False)
    out["dominant_layer"] = best.where(out[delta_cols].max(axis=1) > 0, None)
    return out if as_index else out.reset_index()


def layer_contributions(
    data: ScoreResult | pd.DataFrame,
    by: str | Sequence[str] | Backlog,
    view: str | None = None,
    gamma: float = 0.0,
    volume: str = "cases",
) -> pd.DataFrame:
    """Signed contribution of every layer to the aggregate penalty gap of every slice.

    ``J_λ,s = v_s · ρ_s · (Δ̄_λ,s − Δ̄_λ)`` with ``ρ_s = n_s / (n_s + γ)`` and the
    scale ``v_s`` (the scored case count, or the exposure or column total
    named by ``volume``); Eq. (A2) of the paper. With ``gamma=0`` and
    ``volume="cases"`` this is ``H_λ,s = n_s (Δ̄_λ,s − Δ̄_λ)`` of Section 4.5.
    Positive contributions increase the aggregate penalty gap, negative ones
    offset it. The row sum, clipped at zero *after* summing, equals the
    (stabilised) Priority Index of the slice; clipping each layer separately
    would remove the offsets and overstate it.

    ``by`` is the slice key(s) or a backlog record from :func:`prioritize`,
    whose slice keys, view, ``gamma`` and ``volume`` are then used. Returns a
    DataFrame indexed by slice with one column per layer, in the order of the
    norm's layers.
    """
    if isinstance(by, Backlog):
        gamma, volume = by.spec.gamma, by.spec.volume
        by, view = _from_backlog(data, by, view)
    else:
        by = _keys(by)
    gamma = _check_gamma(gamma)
    out, global_mean, layer_cols, g = _layer_means(data, by, view, None)
    prefix = "contrib__"
    n = out["n_cases"].astype(float)
    vol_col = _volume_column(volume, g.obj)
    scale = g[vol_col].sum().astype(float).reindex(out.index) if vol_col is not None else n
    rho = n / (n + gamma) if gamma > 0 else pd.Series(1.0, index=out.index)
    signed = (out[layer_cols] - global_mean).mul(scale * rho, axis=0)
    return signed.rename(columns={c: c[len(prefix) :] for c in layer_cols})


def _top_keys(backlog: pd.DataFrame, k: int, metric: str, by: Sequence[str] | None) -> set[tuple[str, ...]]:
    pos = backlog[backlog[metric] > 0].sort_values(metric, ascending=False, kind="mergesort").head(k)
    if by:
        return set(map(tuple, pos.reset_index()[list(by)].astype(str).to_numpy()))
    idx = pos.index
    return {tuple(map(str, key if isinstance(key, tuple) else (key,))) for key in idx}


def top_k_overlap(
    backlog_a: Backlog | pd.DataFrame,
    backlog_b: Backlog | pd.DataFrame,
    k: int = 20,
    metric: str = "stable_PI",
    by: Sequence[str] | None = None,
) -> float:
    """Jaccard similarity of the top-``k`` positive-priority slices of two backlogs.

    The number of shared slices divided by the number of distinct slices
    across both lists (paper Section 5.4). Slices are matched on ``by``, by
    default on the slice keys of the backlog records (two records sliced by
    different keys are refused) or else on the index of the frames."""
    table_a, spec_a = (backlog_a.table, backlog_a.spec) if isinstance(backlog_a, Backlog) else (backlog_a, None)
    table_b, spec_b = (backlog_b.table, backlog_b.spec) if isinstance(backlog_b, Backlog) else (backlog_b, None)
    if by is None and spec_a is not None and spec_b is not None:
        if spec_a.by != spec_b.by:
            raise NormError(f"the backlogs have different slice keys: {list(spec_a.by)} and {list(spec_b.by)}")
        by = list(spec_a.by)
    a, b = _top_keys(table_a, k, metric, by), _top_keys(table_b, k, metric, by)
    return len(a & b) / len(a | b) if (a | b) else float("nan")
