"""Reference arithmetic for prepared assessments, independent of the library (paper Section 5.6).

This module repeats the scoring and prioritisation calculations of the paper
on prepared inputs (deviation values, business scope, view weights, layer
membership, group membership) without using :mod:`wise`. The consistency
check of :mod:`wise.evaluation.replay` compares its results with those of the
library: case scores, effective weights, criterion contributions, coverage,
group priorities and signed layer contributions, in both scoring modes and
with and without the small-slice adjustment.

It does not infer business scope, valid evidence, causes or monetary benefit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["group_priorities", "score_assessments", "signed_components"]


def _aligned(value: Any, index: pd.Index, name: str) -> Any:
    if not value.index.is_unique or not index.is_unique:
        raise ValueError(f"{name}: duplicate case identifiers")
    if not value.index.equals(index):
        raise ValueError(f"{name}: case index/order must exactly match")
    return value


def _finite_nonnegative(x: np.ndarray, name: str) -> None:
    if not np.isfinite(x).all() or (x < 0).any():
        raise ValueError(f"{name} must be finite and nonnegative")


def _stable_mean(series: pd.Series) -> float:
    observed = series.dropna()
    if observed.empty:
        return float("nan")
    anchor = float(observed.iloc[0])
    return anchor + float((observed - anchor).mean())


def score_assessments(
    violations: pd.DataFrame, in_scope: pd.DataFrame, weights: pd.Series, layers: Mapping[str, str], *, mode: str
) -> dict[str, Any]:
    """Score explicit assessments; undefined violations use NaN.

    Finite values outside scope are rejected rather than interpreted as zeros.
    NaN inside scope is unavailable evidence. Coverage uses raw weights before
    renormalisation. In the layer-balanced mode a layer's weight is the sum of
    the supplied raw criterion weights of its criteria.
    """
    if mode not in {"flat", "layer_balanced"}:
        raise ValueError("mode must explicitly be flat or layer_balanced")
    if not isinstance(violations, pd.DataFrame) or violations.empty:
        raise ValueError("violations must be a nonempty DataFrame")
    if not violations.columns.is_unique or not violations.index.is_unique:
        raise ValueError("duplicate case or criterion identifiers")
    if not isinstance(in_scope, pd.DataFrame):
        raise ValueError("in_scope must be a boolean DataFrame")
    _aligned(in_scope, violations.index, "in_scope")
    if not in_scope.columns.equals(violations.columns):
        raise ValueError("in_scope columns/order must exactly match")
    if in_scope.isna().any().any() or not all(pd.api.types.is_bool_dtype(t) for t in in_scope.dtypes):
        raise ValueError("in_scope must contain booleans without missing values")
    if not isinstance(weights, pd.Series) or not weights.index.equals(violations.columns):
        raise ValueError("weights must have the exact criterion index/order")
    v = violations.to_numpy(dtype=float)
    a = in_scope.to_numpy(dtype=bool)
    w = weights.to_numpy(dtype=float)
    _finite_nonnegative(w, "weights")
    if not np.any(w > 0):
        raise ValueError("at least one criterion weight must be positive")
    if np.isinf(v).any() or ((v < 0) | (v > 1)).any():
        raise ValueError("evaluated severities must be finite in [0,1]")
    m = ~np.isnan(v)
    if (m & ~a).any():
        raise ValueError("out-of-scope severity must be NaN, not zero")
    if not isinstance(layers, Mapping) or set(layers) != set(violations.columns):
        raise ValueError("layers must map each criterion exactly once")
    layer_names = list(dict.fromkeys(layers[c] for c in violations.columns))
    if any(not isinstance(layer, str) or not layer for layer in layer_names):
        raise ValueError("layer names must be nonempty strings")
    available = m @ w
    scoped = a @ w
    scored = available > 0
    eff = np.zeros_like(v)
    if mode == "flat":
        np.divide(m * w, available[:, None], out=eff, where=available[:, None] > 0)
    else:
        active_layer_weight = np.zeros(len(v))
        for layer in layer_names:
            ix = np.array([layers[c] == layer for c in violations.columns])
            alpha = w[ix].sum()
            bw = m[:, ix] * w[ix]
            bw_sum = bw.sum(axis=1)
            within = np.zeros_like(bw)
            np.divide(bw, bw_sum[:, None], out=within, where=bw_sum[:, None] > 0)
            eff[:, ix] = within * alpha
            active_layer_weight += (bw_sum > 0) * alpha
        np.divide(eff, active_layer_weight[:, None], out=eff, where=active_layer_weight[:, None] > 0)
    penalties = eff * np.nan_to_num(v, nan=0.0)
    # Roundoff at the endpoints must not make the score invalid downstream.
    # Raw evaluated inputs were already range-checked; this is not data repair.
    q = np.clip(penalties.sum(axis=1), 0.0, 1.0)
    q[~scored] = np.nan
    penalties[~scored] = np.nan
    eff[~scored] = np.nan
    coverage = np.full(len(v), np.nan)
    np.divide(available, scoped, out=coverage, where=scoped > 0)
    idx, cols = violations.index, violations.columns

    def series(x: np.ndarray, name: str) -> pd.Series:
        return pd.Series(x, index=idx, name=name)

    return {
        "score": series(1 - q, "score"),
        "penalty": series(q, "penalty"),
        "effective_weights": pd.DataFrame(eff, index=idx, columns=cols),
        "penalties": pd.DataFrame(penalties, index=idx, columns=cols),
        "coverage": series(coverage, "coverage"),
        "in_scope": in_scope.copy(),
        "evaluated": pd.DataFrame(m, index=idx, columns=cols),
        "weights": weights.copy(),
        "layers": dict(layers),
        "mode": mode,
    }


def _grouped_frame(data: pd.DataFrame, group_keys: pd.Series | pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[Any]]:
    if isinstance(group_keys, pd.Series):
        group_keys = group_keys.to_frame()
    if not isinstance(group_keys, pd.DataFrame) or group_keys.shape[1] == 0:
        raise ValueError("group_keys must be a Series or nonempty-column DataFrame")
    _aligned(group_keys, data.index, "group_keys")
    if not group_keys.columns.is_unique:
        raise ValueError("group key names must be unique")
    names = list(group_keys.columns)
    internal = [f"__reference_group_{i}" for i in range(len(names))]
    if set(internal) & set(data.columns):
        raise ValueError("reserved group key column")
    keys = group_keys.copy()
    keys.columns = internal
    return pd.concat([keys, data], axis=1), internal, names


def _score_series(score: pd.Series) -> pd.Series:
    if not isinstance(score, pd.Series) or not score.index.is_unique:
        raise ValueError("score must be a Series with unique case identifiers")
    x = score.to_numpy(dtype=float)
    if np.isinf(x).any() or ((x < 0) | (x > 1)).any():
        raise ValueError("score must be in [0,1] or NaN")
    return score.astype(float)


def _check_gamma(gamma: float) -> None:
    if not np.isfinite(gamma) or gamma < 0:
        raise ValueError("gamma must be finite and nonnegative")


def group_priorities(score: pd.Series, group_keys: pd.Series | pd.DataFrame, *, gamma: float = 0.0) -> pd.DataFrame:
    """Rank groups; the reference is the mean of all scored cases.

    Unscored cases do not enter means, counts or the reference. Groups with no
    scored cases are absent from the ranked output. Missing grouping values
    remain an explicit group. Ties: larger n, then key order.
    """
    _check_gamma(gamma)
    score = _score_series(score)
    data = pd.DataFrame({"score": score, "volume": pd.Series(1.0, index=score.index)})
    frame, keys, names = _grouped_frame(data, group_keys)
    d = frame.loc[score.notna()]
    if d.empty:
        raise ValueError("no scored cases to aggregate")
    reference = _stable_mean(score)
    g = d.groupby(keys, dropna=False, observed=True, sort=True)
    out = g["score"].agg(n_cases="size", mean_score="mean")
    out["volume"] = g["volume"].sum()
    out["mean_penalty"] = 1 - out["mean_score"]
    out["total_penalty"] = out["n_cases"] * out["mean_penalty"]
    out["gap"] = (reference - out["mean_score"]).clip(lower=0)
    if score.dropna().nunique() == 1:
        out["gap"] = 0.0
    out["PI"] = out["volume"] * out["gap"]
    shrink = out["n_cases"] / (out["n_cases"] + gamma)
    out["stable_mean"] = shrink * out["mean_score"] + (1 - shrink) * reference
    out["stable_gap"] = shrink * out["gap"]
    out["stable_PI"] = shrink * out["PI"]
    out["reference"] = reference
    out = out.sort_index().sort_values(["stable_PI", "n_cases"], ascending=False, kind="stable")
    out.index.names = names
    return out


def signed_components(penalties: pd.DataFrame, group_keys: pd.Series | pd.DataFrame, *, gamma: float = 0.0) -> pd.DataFrame:
    """Signed amounts per group and component that sum to the priority excess before clipping.

    Clip the row sum, never individual components. This is algebraic
    accounting, not causal attribution.
    """
    _check_gamma(gamma)
    if not isinstance(penalties, pd.DataFrame) or not penalties.columns.is_unique:
        raise ValueError("penalties must have unique component columns")
    x = penalties.to_numpy(dtype=float)
    partial = np.isnan(x).any(axis=1) & ~np.isnan(x).all(axis=1)
    if partial.any() or np.isinf(x).any() or (x < 0).any():
        raise ValueError("penalty rows must be finite nonnegative or entirely NaN")
    q = penalties.sum(axis=1, min_count=1)
    if (q > 1 + 1e-12).any():
        raise ValueError("component penalties cannot sum above 1")
    if not q.notna().any():
        raise ValueError("no scored cases to explain")
    ref = penalties.mean(axis=0)
    frame, keys, names = _grouped_frame(penalties, group_keys)
    frame = frame.loc[q.notna()]
    g = frame.groupby(keys, dropna=False, observed=True, sort=True)
    n = g.size()
    means = g[list(penalties.columns)].mean()
    multiplier = n * n / (n + gamma)
    out = (means - ref).mul(multiplier, axis=0)
    out.index.names = names
    return out
