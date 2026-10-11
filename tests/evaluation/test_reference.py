"""The library against the reference arithmetic on constructed prepared assessments (paper Section 5.6).

The same comparison is made on the three applications of the paper when their
logs are supplied (``tests/test_paper_evaluation.py``).
"""

import numpy as np
import pandas as pd
import pytest

from wise.evaluation import reference, replay
from wise.evaluation.adapters import EVALUATED, OUT_OF_SCOPE, Assessment


def constructed_assessment(seed: int, n: int = 400) -> Assessment:
    rng = np.random.default_rng(seed)
    index = pd.Index([f"case{i:04d}" for i in range(n)], name="case_id")
    criteria = [f"C{i:02d}" for i in range(1, 8)]
    layers = dict(zip(criteria, ["L1", "L1", "L1", "L2", "L2", "L3", "L4"], strict=True))
    scope = pd.DataFrame(rng.uniform(size=(n, len(criteria))) > 0.15, index=index, columns=criteria)
    available = pd.DataFrame(rng.uniform(size=scope.shape) > 0.25, index=index, columns=criteria)
    values = pd.DataFrame(rng.uniform(size=scope.shape), index=index, columns=criteria)
    values = values.where(rng.uniform(size=scope.shape) > 0.3, 0.0).where(rng.uniform(size=scope.shape) > 0.1, 1.0)
    severity = values.where(scope & available)
    severity.iloc[:5] = np.nan  # some cases without any evaluated criterion
    state = pd.DataFrame("unavailable", index=index, columns=criteria).where(severity.isna(), EVALUATED).mask(~scope, OUT_OF_SCOPE)
    groups = pd.Series(rng.choice([f"g{i}" for i in range(12)], size=n, p=np.r_[0.5, np.full(11, 0.5 / 11)]), index=index, name="group")
    views = {
        "Balanced": dict.fromkeys(criteria, 1.0),
        "Skewed": dict(zip(criteria, [3.0, 3.0, 3.0, 2.0, 2.0, 1.0, 0.5], strict=True)),
        "Sparse": dict(zip(criteria, [0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 0.0], strict=True)),
    }
    cfg = {"id": f"constructed-{seed}", "version": "1"}
    return Assessment("constructed", cfg, pd.DataFrame(index=index), severity, scope, state, values, groups, layers, views)


@pytest.mark.parametrize("seed", range(3))
def test_library_agrees_with_the_reference_arithmetic(seed):
    report = replay.consistency(constructed_assessment(seed))
    assert report["scope_identical"] and report["evidence_identical"]
    assert report["views"] == 3
    assert report["mode_view_combinations"] == 6  # three views under flat and layer-balanced scoring
    assert report["max_residual"] < 1e-12
    assert report["passed"]
    assert {r["mode"] for r in report["differential_checks"]} == {"flat", "layer_balanced"}
    names = set(report["differential_checks"][0]["residuals"])
    assert {"scores", "weights", "components", "coverage", "signed_layer_contributions", "gamma0_PI", "gamma20_stable_PI"} <= names


def test_reference_refuses_inconsistent_input():
    a = constructed_assessment(0, n=20)
    weights = pd.Series(a.views["Balanced"])
    with pytest.raises(ValueError, match="mode"):
        reference.score_assessments(a.severity, a.in_scope, weights, a.layers, mode="other")
    with pytest.raises(ValueError, match="NaN, not zero"):
        reference.score_assessments(a.severity.fillna(0.0), a.in_scope, weights, a.layers, mode="flat")
    with pytest.raises(ValueError, match="positive"):
        reference.score_assessments(a.severity, a.in_scope, weights * 0, a.layers, mode="flat")
    with pytest.raises(ValueError, match="gamma"):
        reference.group_priorities(pd.Series([0.5], index=["a"]), pd.Series(["g"], index=["a"]), gamma=-1)


def test_reference_worked_example():
    index = pd.Index(["a1", "a2", "b1", "b2"], name="case_id")
    v = pd.DataFrame({"delay": [0.8, 0.6, 0.1, 0.1], "approval": [0, 0, 1, 0.8], "control": [0.2, np.nan, 0.2, np.nan]}, index=index)
    scope = pd.DataFrame(True, index=index, columns=v.columns)
    weights = pd.Series({"delay": 0.5, "approval": 0.25, "control": 0.25})
    layers = {"delay": "Timeliness", "approval": "Controls", "control": "Controls"}
    flat = reference.score_assessments(v, scope, weights, layers, mode="flat")
    assert flat["penalty"]["a1"] == pytest.approx(0.5 * 0.8 + 0.25 * 0.2)
    assert flat["penalty"]["a2"] == pytest.approx(0.5 * 0.6 / 0.75)
    assert flat["coverage"].tolist() == pytest.approx([1.0, 0.75, 1.0, 0.75])
    balanced = reference.score_assessments(v, scope, weights, layers, mode="layer_balanced")
    assert balanced["penalty"]["b2"] == pytest.approx(0.5 * 0.1 + 0.5 * 0.8)  # Controls keeps its weight on approval alone
    groups = pd.Series(["A", "A", "B", "B"], index=index)
    table = reference.group_priorities(flat["score"], groups)
    assert table["PI"].sum() == pytest.approx(table.loc[table["PI"] > 0, "n_cases"].iloc[0] * table["gap"].max())
    signed = reference.signed_components(flat["penalties"], groups)
    np.testing.assert_allclose(signed.sum(axis=1).clip(lower=0).to_numpy(), table["PI"].reindex(signed.index).to_numpy(), atol=1e-12)
