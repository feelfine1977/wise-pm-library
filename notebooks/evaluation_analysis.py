"""Criterion attribution and parameter sensitivity for the BPIC19 evaluation.

Calculations use the current ten-criterion, flat-scoring ``paper.Application``.
The supplied assessment, source evidence and primary results remain unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


CRITERIA = [f"C{i:02d}" for i in range(1, 11)]
FOCAL_GROUPS = (
    "companyID_0000 | Packaging",
    "companyID_0000 | Logistics",
)
TOLERANCE = 1e-8


def _assessments(app):
    """Validate the criterion set, scoring mode, case identities and alignment."""
    a = app.assessment
    if list(a.severity.columns) != CRITERIA:
        raise ValueError(
            "These helpers require the current ten-criterion BPIC19 assessment."
        )
    if app.result.mode != "flat":
        raise ValueError("The primary application must use flat scoring.")
    index = a.severity.index
    for frame in (a.in_scope, a.state, a.features):
        if not frame.index.equals(index):
            raise ValueError(
                "Assessment, scope, evidence and features must be aligned."
            )
    scored_index = app.result.scores.index
    if (
        not scored_index.is_unique
        or len(scored_index) != len(index)
        or len(index.difference(scored_index))
    ):
        raise ValueError(
            "Native scores must contain exactly the assessed case identifiers."
        )
    if not a.groups.index.equals(index) or a.groups.isna().any():
        raise ValueError("Every assessment needs its explicit, aligned business group.")
    if not a.in_scope.columns.equals(a.severity.columns):
        raise ValueError("Scope and severity must have the same criterion order.")
    if (a.severity.notna() & ~a.in_scope).any().any():
        raise ValueError("An evaluated criterion cannot be outside business scope.")
    return a


def criterion_contributions(app, view="Balanced") -> pd.DataFrame:
    """Decompose each group's aggregate penalty gap into signed criterion terms.

    Each term is n_group * (group mean penalty - population mean penalty) for
    one criterion. Means include zero penalties for unavailable or out-of-scope
    criteria in scored cases. Negative contributions offset positive ones;
    clipping their sum at zero gives the native priority index for gamma=0.

    Rows follow the native backlog order and columns are C01..C10. Assertions
    check the total against native PI and layer sums against
    ``wise.layer_contributions``. Contributions explain the score arithmetic,
    not causal effects or financial losses.
    """
    import wise

    a = _assessments(app)
    scored = app.result.scores[view].notna()
    penalties = app.result.penalties(view).loc[scored, CRITERIA]
    groups = a.groups.reindex(penalties.index)
    if penalties.empty:
        raise ValueError("No scored cases are available under this view.")
    grouped = penalties.groupby(groups, dropna=False, observed=True, sort=True)
    counts = grouped.size()
    signed = (
        grouped.mean().sub(penalties.mean(), axis="columns").mul(counts, axis="index")
    )
    backlog = app.backlog(view, gamma=0.0)
    signed = signed.reindex(backlog.table.index)
    if signed.isna().any().any():
        raise AssertionError(
            "Criterion contributions and native backlog groups differ."
        )
    np.testing.assert_allclose(
        signed.sum(axis=1).clip(lower=0).to_numpy(),
        backlog.table["PI"].to_numpy(),
        rtol=0,
        atol=TOLERANCE,
        err_msg="Signed criterion totals do not reproduce the native gamma0 PI.",
    )
    native_layers = wise.layer_contributions(app.result, backlog).reindex(signed.index)
    for layer in native_layers.columns:
        ids = [cid for cid in CRITERIA if a.layers[cid] == layer]
        np.testing.assert_allclose(
            signed[ids].sum(axis=1).to_numpy(),
            native_layers[layer].to_numpy(),
            rtol=0,
            atol=TOLERANCE,
            err_msg=f"Criterion totals differ from native signed layer contribution: {layer}",
        )
    signed.attrs.update(
        view=view,
        gamma=0.0,
        scale="scored case count",
        interpretation="signed contribution to aggregate penalty gap; negative values offset positive values",
        validation_tolerance=TOLERANCE,
    )
    return signed


def _flat_assessment(severity, scope, groups, raw_weights):
    """Calculate flat scores, evidence coverage and group priorities directly."""
    weights = pd.Series(raw_weights, dtype=float).reindex(severity.columns)
    if (
        weights.isna().any()
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or weights.sum() <= 0
    ):
        raise ValueError(
            "Each criterion needs a finite non-negative raw weight with positive total."
        )
    evaluated = severity.notna()
    denominator = evaluated.mul(weights, axis="columns").sum(axis=1)
    effective = evaluated.mul(weights, axis="columns").div(
        denominator.where(denominator > 0), axis="index"
    )
    penalty = severity.fillna(0).mul(effective).sum(axis=1).where(denominator > 0)
    score = 1.0 - penalty
    in_scope_weight = scope.mul(weights, axis="columns").sum(axis=1)
    coverage = denominator.div(in_scope_weight.where(in_scope_weight > 0))
    frame = pd.DataFrame(
        {"group": groups, "score": score, "coverage": coverage}
    ).dropna(subset=["score"])
    if frame.empty:
        raise ValueError("Scenario leaves no scored cases.")
    reference = float(frame["score"].mean())
    table = frame.groupby("group", dropna=False, observed=True, sort=True).agg(
        scored_cases=("score", "size"),
        mean_score=("score", "mean"),
        mean_coverage=("coverage", "mean"),
    )
    table["reference_mean_score"] = reference
    table["gap"] = (reference - table["mean_score"]).clip(lower=0)
    table["PI"] = table["scored_cases"] * table["gap"]
    table = table.reset_index()
    table["_key"] = table["group"].astype(str)
    table = table.sort_values(
        ["PI", "scored_cases", "_key"], ascending=[False, False, True], kind="mergesort"
    )
    table = table.drop(columns="_key").set_index("group")
    table["rank"] = np.arange(1, len(table) + 1)
    return table, score, coverage


def _check_baseline(app, table, score, coverage):
    """Compare direct baseline calculations with native scores and priorities."""
    native = app.backlog("Balanced", gamma=0.0).table.reindex(table.index)
    if native["PI"].isna().any():
        raise AssertionError("Independent baseline and native backlog groups differ.")
    for actual, expected, label in (
        (score, app.result.scores["Balanced"].reindex(score.index), "case scores"),
        (
            coverage,
            app.result.coverage("Balanced").reindex(coverage.index),
            "weighted evidence coverage",
        ),
        (table["PI"], native["PI"], "group priorities"),
        (table["mean_score"], native["mean_score"], "group means"),
        (table["reference_mean_score"], native["global_mean"], "population reference"),
        (table["scored_cases"], native["n_cases"], "scored case counts"),
    ):
        np.testing.assert_allclose(
            actual.to_numpy(),
            expected.to_numpy(),
            rtol=0,
            atol=TOLERANCE,
            equal_nan=True,
            err_msg=f"Independent baseline differs from native {label}.",
        )
    if list(table.index) != list(app.backlog("Balanced", gamma=0.0).table.index):
        raise AssertionError(
            "Independent baseline tie order differs from native order."
        )


def _focal_rows(table, baseline, scenario, **parameters):
    """Select focal groups and compare top-ten membership, including zero PI."""
    missing = set(FOCAL_GROUPS) - set(table.index)
    if missing:
        raise ValueError(
            f"The current assessment lacks focal groups: {sorted(missing)}"
        )
    size = min(10, len(baseline))
    overlap = len(set(table.head(size).index) & set(baseline.head(size).index))
    rows = table.loc[list(FOCAL_GROUPS)].reset_index()
    rows.insert(0, "scenario", scenario)
    rows["top10_overlap_baseline"] = overlap
    rows["top10_denominator"] = size
    rows["top10_overlap_fraction"] = overlap / size
    rows["positive_priority_groups"] = int(table["PI"].gt(1e-12).sum())
    for key, value in parameters.items():
        rows[key] = value
    return rows


def sensitivity_tables(app) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vary C04 thresholds and Timing weights for Packaging and Logistics.

    C04 zero/full-deviation endpoints are (15, 75), (30, 90) and (45, 105) days:
    shifts of +/-15 days at a fixed 60-day width. Timing raw weights are scaled
    by 0.5, 1 and 2 relative to Balanced, leaving other weights unchanged.
    Scenarios recompute effective weights, scores, coverage, the population
    reference, PI and ranks while retaining prepared evidence and scope.

    These exploratory settings examine assessment choices, not log uncertainty
    or validated service standards. Group coverage averages scored cases.
    Top-ten membership includes zero-priority ties, ordered by descending PI,
    descending case count and ascending group identifier, as in the paper.
    The baseline must reproduce the native result before scenarios are returned.
    """
    a = _assessments(app)
    rule = next(c for c in a.configuration["criteria"] if c["id"] == "C04")
    if (float(rule["threshold"]), float(rule["width"])) != (30.0, 60.0):
        raise ValueError(
            "The declared baseline must be C04 threshold30 / saturation90 days."
        )
    weights = pd.Series(a.views["Balanced"], dtype=float).reindex(CRITERIA)
    severity = a.severity.loc[:, CRITERIA]
    scope = a.in_scope.loc[:, CRITERIA]
    baseline, baseline_scores, baseline_coverage = _flat_assessment(
        severity, scope, a.groups, weights
    )
    _check_baseline(app, baseline, baseline_scores, baseline_coverage)
    threshold_rows = []
    available_c04 = severity["C04"].notna()
    raw_days = a.features["invoice_clear_days"]
    for threshold, saturation in ((15.0, 75.0), (30.0, 90.0), (45.0, 105.0)):
        changed = severity.copy()
        changed.loc[available_c04, "C04"] = (
            (raw_days.loc[available_c04] - threshold) / (saturation - threshold)
        ).clip(lower=0, upper=1)
        if not changed.notna().equals(severity.notna()):
            raise AssertionError("Threshold sensitivity changed evaluability.")
        table, scores, coverage = _flat_assessment(changed, scope, a.groups, weights)
        if threshold == 30:
            np.testing.assert_allclose(
                changed.to_numpy(),
                severity.to_numpy(),
                rtol=0,
                atol=TOLERANCE,
                equal_nan=True,
            )
            _check_baseline(app, table, scores, coverage)
        threshold_rows.append(
            _focal_rows(
                table,
                baseline,
                f"C04 {threshold:g}–{saturation:g} days",
                threshold_days=threshold,
                saturation_days=saturation,
                width_days=saturation - threshold,
            )
        )
    timing = [cid for cid in CRITERIA if a.layers[cid] == "Timing"]
    if not timing:
        raise ValueError("No Timing criteria are defined.")
    weight_rows = []
    for multiplier in (0.5, 1.0, 2.0):
        changed_weights = weights.copy()
        changed_weights.loc[timing] *= multiplier
        table, scores, coverage = _flat_assessment(
            severity, scope, a.groups, changed_weights
        )
        if multiplier == 1:
            _check_baseline(app, table, scores, coverage)
        weight_rows.append(
            _focal_rows(
                table,
                baseline,
                f"Timing × {multiplier:g}",
                timing_multiplier=multiplier,
            )
        )
    threshold_df = pd.concat(threshold_rows, ignore_index=True)
    weight_df = pd.concat(weight_rows, ignore_index=True)
    note = "Exploratory parameter sensitivity; fixed prepared evidence and scope; gamma=0; case-count scale."
    for frame in (threshold_df, weight_df):
        frame.attrs.update(
            interpretation=note,
            top10_policy="all ranked groups, including zero-priority ties; descending PI, count, ascending key",
            baseline_validation_tolerance=TOLERANCE,
        )
    return threshold_df, weight_df
