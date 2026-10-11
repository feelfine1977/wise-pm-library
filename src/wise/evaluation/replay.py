"""Replay of the three applications and the numerical checks of the paper (Section 5.6, Appendix B.1).

The replay runs a domain adapter on its verified public log and loads the
prepared assessment through the scoring and prioritisation interfaces of the
library (:mod:`wise.evaluation.native`). The consistency check then repeats
the scoring and prioritisation calculations with the reference arithmetic of
:mod:`wise.evaluation.reference` on the same prepared inputs and compares

* applicability and evidence availability (exactly),
* case scores, effective weights, criterion contributions and coverage,
* group counts, means, gaps and priorities with γ = 0 and γ = 20,
* signed layer contributions,

under flat and layer-balanced scoring. The largest absolute difference must
be below the declared tolerance of 1e-8.

The comparison covers three views in each of the three applications: nine
primary view evaluations and eighteen mode-view combinations, each at γ = 0
and γ = 20.

Section 5.6 further names constructed tests that compare deviation values
after the rows of the event table are shuffled and case scores after a norm
is serialised and reloaded (``tests/test_invariants.py``). Beyond the text,
:func:`further_checks` makes three checks of this kind on each application:
it scores the same prepared assessment again and requires unchanged scores

* when the complete cases are put into another order,
* when the norm is serialised and read back,
* when the whole-case context of the application (:data:`CONTEXT`) is attached
  to the cases.

All checks begin with prepared deviation values. How those values are derived
from the event log is the adapter's responsibility and is checked against the
original records separately.

Command line::

    python -m wise.evaluation.replay --data <folder> [--application bpic2019 ...]

prints one line per application with the number of cases, criteria, views
and mode-view combinations, the values of γ, the largest absolute difference
against the reference arithmetic, the largest score difference of the three
further checks, and ``passed`` or ``failed``; then one line with the totals
over the applications. With ``--output`` it writes a verification file
``<application>.json`` with every residual for each application.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import wise

from . import data as _data
from . import native, reference
from .adapters import Assessment, bpic2013, bpic2017, bpic2019

__all__ = ["ADAPTERS", "APPLICATIONS", "CONTEXT", "GAMMAS", "MODES", "TOLERANCE", "assess", "consistency", "further_checks", "main"]

TOLERANCE = 1e-8
MODES = ("flat", "layer_balanced")
GAMMAS = (0.0, 20.0)
ADAPTERS = {
    bpic2019.APPLICATION: bpic2019,
    bpic2013.APPLICATION: bpic2013,
    bpic2017.APPLICATION: bpic2017,
}
APPLICATIONS = tuple(ADAPTERS)
CONTEXT = {
    bpic2019.APPLICATION: ("document", "vendor", "flow"),
    bpic2013.APPLICATION: ("product_group",),
    bpic2017.APPLICATION: ("application_type", "loan_goal"),
}
"""The whole-case context of each application: the attributes of the adapter's case table that describe the
complete case and by which the same scored cases can be grouped in another way."""
_GROUP_COLUMNS = ["n_cases", "volume", "mean_score", "gap", "PI", "stable_mean", "stable_gap", "stable_PI"]


def assess(application: str, data: str | Path | None = None) -> Assessment:
    """Run the adapter of ``application`` on its verified log in the data folder."""
    if application not in ADAPTERS:
        raise KeyError(f"unknown application {application!r}; known: {list(ADAPTERS)}")
    return ADAPTERS[application].assess(_data.locate(application, data))


def _same_labels(actual: pd.Index, expected: pd.Index, label: str) -> None:
    """Reject missing, extra, duplicate or type-changed labels before alignment."""
    if not actual.is_unique or not expected.is_unique:
        raise AssertionError(f"{label}: duplicate identities")
    actual_keys = {(type(value).__name__, repr(value)) for value in actual.tolist()}
    expected_keys = {(type(value).__name__, repr(value)) for value in expected.tolist()}
    if len(actual) != len(expected) or actual_keys != expected_keys:
        raise AssertionError(f"{label}: exact identity mismatch")


def residual(actual: pd.Series | pd.DataFrame, expected: pd.Series | pd.DataFrame) -> float:
    """Largest absolute difference of two aligned tables; their identities and missing values must match exactly."""
    if isinstance(actual, pd.DataFrame) != isinstance(expected, pd.DataFrame):
        raise AssertionError("comparison container mismatch")
    _same_labels(actual.index, expected.index, "comparison rows")
    if isinstance(actual, pd.DataFrame):
        _same_labels(actual.columns, expected.columns, "comparison columns")
        expected = expected.reindex(index=actual.index, columns=actual.columns)
    else:
        expected = expected.reindex(actual.index)
    x = actual.to_numpy(dtype=float)
    y = expected.to_numpy(dtype=float)
    if x.shape != y.shape or not np.array_equal(np.isnan(x), np.isnan(y)):
        raise AssertionError("missingness or shape mismatch")
    if not np.isfinite(x[~np.isnan(x)]).all() or not np.isfinite(y[~np.isnan(y)]).all():
        raise AssertionError("non-finite observed value")
    delta = np.abs(x - y)
    return float(np.nanmax(delta)) if np.isfinite(delta).any() else 0.0


def _group_residuals(native_table: pd.DataFrame, expected: pd.DataFrame) -> dict[str, float]:
    _same_labels(native_table.index, expected.index, "group population")
    return {c: residual(native_table[c], expected[c]) for c in _GROUP_COLUMNS}


def consistency(assessment: Assessment, result: wise.ScoreResult | None = None) -> dict[str, Any]:
    """Compare the library with the reference arithmetic on one prepared assessment.

    Returns the application, its numbers of cases, criteria and views, whether
    scope and evidence availability match exactly, every residual, the
    largest of them and ``passed`` (largest residual below :data:`TOLERANCE`).
    """
    v, scope, layers, views = assessment.severity, assessment.in_scope, dict(assessment.layers), assessment.views
    groups = assessment.groups.rename(native.GROUP)
    log, norm, _ = native.norm_from_assessment(assessment)
    primary = result if result is not None and result.mode == "flat" else wise.score(log, norm, mode="flat")
    checks: dict[str, Any] = {}

    # applicability and evidence availability: exact
    _same_labels(primary.in_scope.index, scope.index, "scope rows")
    _same_labels(primary.in_scope.columns, scope.columns, "scope columns")
    scope_identical = bool(primary.in_scope.equals(scope.reindex(primary.in_scope.index)))
    evidence_identical = bool(primary.violations.notna().equals(v.notna().reindex(primary.violations.index)))
    if not scope_identical or not evidence_identical:
        raise AssertionError("business scope or evidence availability differs between the library and the prepared assessment")
    checks["severity"] = residual(primary.violations, v)
    checks["layer_decomposition"] = primary.check_decomposition(atol=1e-10)

    primary_signed: dict[str, pd.DataFrame] = {}
    for view in views:
        backlog = wise.prioritize(primary, by=native.GROUP, view=view)
        signed = wise.layer_contributions(primary, backlog)
        primary_signed[view] = signed
        checks[f"{view}: layer contributions sum to the Priority Index"] = residual(
            signed.sum(axis=1).clip(lower=0), backlog.table["PI"]
        )

    differential: list[dict[str, Any]] = []
    for mode in MODES:
        scored = primary if mode == "flat" else wise.score(log, norm, mode=mode)
        for view, weights in views.items():
            ref = reference.score_assessments(v, scope, pd.Series(weights).reindex(v.columns).astype(float), layers, mode=mode)
            is_scored = scored.scores[view].notna()
            rr = {
                "scores": residual(scored.scores[view], ref["score"]),
                "weights": residual(scored.effective_weights(view).where(is_scored), ref["effective_weights"]),
                "components": residual(scored.penalties(view).where(is_scored), ref["penalties"]),
                "coverage": residual(scored.coverage(view), ref["coverage"]),
            }
            if mode == "flat":
                layer_penalties = pd.DataFrame(
                    {
                        layer: ref["penalties"][[c for c in v if layers[c] == layer]].sum(axis=1, min_count=1)
                        for layer in norm.layer_ids
                    }
                )
                rr["signed_layer_contributions"] = residual(primary_signed[view], reference.signed_components(layer_penalties, groups))
            for gamma in GAMMAS:
                ranked = wise.prioritize(scored, by=native.GROUP, view=view, gamma=gamma)
                expected = reference.group_priorities(ref["score"], groups, gamma=gamma)
                rr.update({f"gamma{gamma:g}_{c}": z for c, z in _group_residuals(ranked.table, expected).items()})
            differential.append({"mode": mode, "view": view, "residuals": rr})

    values = [float(x) for x in checks.values()] + [float(z) for r in differential for z in r["residuals"].values()]
    maximum = max(values)
    return {
        "application": assessment.application,
        "cases": len(v),
        "criteria": len(v.columns),
        "views": len(views),
        "mode_view_combinations": len(differential),
        "gammas": list(GAMMAS),
        "scope_identical": scope_identical,
        "evidence_identical": evidence_identical,
        "max_residual": maximum,
        "tolerance": TOLERANCE,
        "passed": bool(maximum < TOLERANCE),
        "norm_fingerprint": norm.fingerprint(),
        "checks": checks,
        "differential_checks": differential,
    }


def _reordered(assessment: Assessment, seed: int = 0) -> Assessment:
    """The same assessment with its cases in another order; every case keeps all its values."""
    order = np.random.default_rng(seed).permutation(len(assessment.severity))
    tables = {
        name: getattr(assessment, name).iloc[order] for name in ("features", "severity", "in_scope", "state", "raw", "groups")
    }
    return dataclasses.replace(assessment, **tables)


def further_checks(assessment: Assessment) -> dict[str, Any]:
    """Three further checks on one prepared assessment, of the kind Section 5.6 names for constructed tests.

    The assessment is scored with the shipped native norm, under flat and
    layer-balanced scoring, and scored again

    * ``reordered``: with the complete cases in another (fixed pseudo-random)
      order. A case is one record of the prepared assessment, so all values
      of a case move together;
    * ``norm_read_back``: with the norm serialised to its JSON document and
      read back; the fingerprint must be unchanged as well;
    * ``context_attached``: with the whole-case context of the application
      (:data:`CONTEXT`) attached to the cases as further case attributes.
      No criterion reads these attributes; they only allow other groupings.

    Returns per check the largest absolute difference of the case scores over
    all views and both modes (cases are matched by identifier; a case scored
    in one run and unscored in the other is an error), the largest of the
    three and ``passed`` (largest difference below :data:`TOLERANCE`).
    """
    context = list(CONTEXT[assessment.application])
    attributes = assessment.features[context]
    reordered = _reordered(assessment)
    residuals = {"reordered": 0.0, "norm_read_back": 0.0, "context_attached": 0.0}
    fingerprint_unchanged = True
    for mode in MODES:
        base = native.replay(assessment, mode=mode)
        again = native.replay(reordered, mode=mode)
        residuals["reordered"] = max(residuals["reordered"], residual(again.scores, base.scores))
        read_back = wise.Norm.loads(base.norm.dumps())
        fingerprint_unchanged &= read_back.fingerprint() == base.norm.fingerprint()
        residuals["norm_read_back"] = max(residuals["norm_read_back"], residual(wise.score(base.log, read_back, mode=mode).scores, base.scores))
        with_context = native.replay(assessment, attributes=attributes, mode=mode)
        residuals["context_attached"] = max(residuals["context_attached"], residual(with_context.scores, base.scores))
    maximum = max(residuals.values())
    return {
        "application": assessment.application,
        "cases": len(assessment.severity),
        "views": len(assessment.views),
        "modes": list(MODES),
        "context": context,
        "residuals": residuals,
        "fingerprint_unchanged": bool(fingerprint_unchanged),
        "max_residual": maximum,
        "tolerance": TOLERANCE,
        "passed": bool(maximum < TOLERANCE and fingerprint_unchanged),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the applications of the paper through the library, check them against the reference arithmetic "
        "and make the three further checks (cases reordered, norm read back, whole-case context attached)."
    )
    parser.add_argument("--data", type=Path, default=None, help=f"folder with the public logs (default: ${_data.DATA_ENVIRONMENT})")
    parser.add_argument("--application", action="append", choices=APPLICATIONS, help="repeatable; default: all three")
    parser.add_argument("--output", type=Path, default=None, help="folder for one verification file per application")
    parser.add_argument("--write-norms", type=Path, default=None, help="folder to write the native norm of each application to")
    args = parser.parse_args(argv)
    failed = False
    totals: dict[str, Any] = {"applications": 0, "primary_views": 0, "mode_view_combinations": 0, "gammas": list(GAMMAS), "max_residual": 0.0}
    for application in args.application or APPLICATIONS:
        try:
            assessment = assess(application, args.data)
        except _data.DataNotAvailable as exc:
            print(json.dumps({"application": application, "status": "not run", "reason": str(exc)}))
            failed = True
            continue
        if args.write_norms is not None:
            _, norm, _ = native.norm_from_assessment(assessment)
            native.write_norm(norm, args.write_norms, application)
        report = consistency(assessment)
        further = further_checks(assessment)
        line = {k: report[k] for k in ["application", "cases", "criteria", "views", "mode_view_combinations", "gammas", "max_residual"]}
        line["further_checks"] = further["residuals"]
        passed = report["passed"] and further["passed"]
        line["status"] = "passed" if passed else "failed"
        print(json.dumps(line), flush=True)
        totals["applications"] += 1
        totals["primary_views"] += report["views"]
        totals["mode_view_combinations"] += report["mode_view_combinations"]
        totals["max_residual"] = max(totals["max_residual"], report["max_residual"])
        if args.output is not None:
            args.output.mkdir(parents=True, exist_ok=True)
            report["further_checks"] = further
            (args.output / f"{application}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        failed |= not passed
    totals["tolerance"] = TOLERANCE
    totals["status"] = "failed" if failed else "passed"
    print(json.dumps(totals), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
