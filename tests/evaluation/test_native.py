"""Contract tests for the transport of prepared assessments into the library (paper Sections 4.2 and 5.6)."""

import numpy as np
import pandas as pd
import pytest

import wise
from wise.evaluation import native
from wise.evaluation.replay import _same_labels, residual


def example_assessments():
    index = pd.Index(["complete", "partial", "outside", "unscored"], name="case_id")
    severity = pd.DataFrame(
        {"a": [1.0, 1.0, np.nan, np.nan], "b": [0.0, np.nan, 0.0, np.nan], "c": [0.0, 0.0, 1.0, np.nan]}, index=index
    )
    scope = pd.DataFrame(True, index=index, columns=severity.columns)
    scope.loc["outside", "a"] = False
    groups = pd.Series(["x", "x", "y", "y"], index=index)
    return severity, scope, {"a": "L1", "b": "L1", "c": "L2"}, {"Equal": {"a": 1.0, "b": 1.0, "c": 1.0}}, groups


def test_carrier_has_one_record_per_case_and_a_placeholder_timestamp():
    severity, scope, layers, weights, groups = example_assessments()
    log, norm, cases = native.prepare_native(severity, scope, layers, weights, groups, name="contract")
    assert len(log.events) == len(severity) == len(log)
    assert set(log.events["activity"]) == {"prepared assessment"}
    assert set(log.events["timestamp"]) == {pd.Timestamp("1970-01-01")}
    assert list(cases.columns)[0] == native.GROUP
    for nc in norm.constraints:  # identity metric constraints with threshold zero and width one
        assert nc.constraint == wise.Metric(f"{native.VALUE_PREFIX}{nc.id}", threshold=0, width=1)
        assert nc.applicability == {"attr": f"{native.SCOPE_PREFIX}{nc.id}", "eq": True}
    assert norm.scoring_mode == "flat"
    assert norm.metadata["raw_operator_equivalence_claimed"] is False


def test_scope_missingness_modes_and_round_trip(tmp_path):
    severity, scope, layers, weights, groups = example_assessments()
    log, norm, cases = native.prepare_native(severity, scope, layers, weights, groups, name="contract")
    loaded = wise.Norm.load(native.write_norm(norm, tmp_path, "contract"))
    assert norm.fingerprint() == loaded.fingerprint()
    result = wise.score(native.carrier_log(cases), loaded)
    pd.testing.assert_frame_equal(result.in_scope, scope.reindex(result.in_scope.index))
    # every prepared severity is preserved
    pd.testing.assert_frame_equal(result.violations, severity.reindex(result.violations.index), check_names=False)
    assert np.isnan(result.scores.loc["unscored", "Equal"])
    assert result.scores.loc["complete", "Equal"] == pytest.approx(2 / 3)
    assert result.scores.loc["partial", "Equal"] == pytest.approx(0.5)
    assert result.coverage("Equal")["partial"] == pytest.approx(2 / 3)
    assert result.coverage("Equal")["outside"] == 1.0
    layered = wise.score(log, norm, mode="layer_balanced")
    assert layered.scores.loc["partial", "Equal"] == pytest.approx(1 / 3)
    backlog = wise.prioritize(result, by=native.GROUP, view="Equal", gamma=20).table
    assert int(backlog.n_cases.sum()) == 3
    assert result.check_decomposition() < 1e-12


def test_finite_outside_scope_is_rejected():
    severity, scope, layers, weights, groups = example_assessments()
    severity.loc["outside", "a"] = 0
    with pytest.raises(ValueError, match="out-of-scope"):
        native.prepare_native(severity, scope, layers, weights, groups, name="invalid")


@pytest.mark.parametrize("value", [np.inf, -0.1, 1.1])
def test_nonfinite_or_out_of_range_severity_is_rejected(value):
    severity, scope, layers, weights, groups = example_assessments()
    severity.iloc[0, 0] = value
    with pytest.raises(ValueError, match="finite severity"):
        native.prepare_native(severity, scope, layers, weights, groups, name="invalid")


def test_misalignment_and_nonboolean_scope_are_rejected():
    severity, scope, layers, weights, groups = example_assessments()
    with pytest.raises(ValueError, match="exactly the severity index"):
        native.prepare_native(severity, scope.iloc[::-1], layers, weights, groups, name="invalid")
    with pytest.raises(ValueError, match="boolean"):
        native.prepare_native(severity, scope.astype(int), layers, weights, groups, name="invalid")
    with pytest.raises(ValueError, match="group index"):
        native.prepare_native(severity, scope, layers, weights, groups.iloc[::-1], name="invalid")
    with pytest.raises(ValueError, match="every criterion"):
        native.prepare_native(severity, scope, layers, {"Equal": {"a": 1.0}}, groups, name="invalid")
    with pytest.raises(ValueError, match="exactly one layer"):
        native.prepare_native(severity, scope, {"a": "L1"}, weights, groups, name="invalid")


def test_zero_view_weight_makes_missingness_view_specific():
    severity, scope, layers, weights, groups = example_assessments()
    weights["OnlyB"] = {"a": 0.0, "b": 1.0, "c": 0.0}
    log, norm, _ = native.prepare_native(severity, scope, layers, weights, groups, name="zero-weight")
    result = wise.score(log, norm)
    assert np.isnan(result.scores.loc["partial", "OnlyB"])
    assert result.scores.loc["outside", "OnlyB"] == 1.0
    assert result.coverage("OnlyB")["partial"] == 0.0


def test_layer_contributions_retain_negative_offsets():
    index = pd.Index(["a1", "a2", "b1"], name="case_id")
    severity = pd.DataFrame({"c1": [1.0, 1.0, 0.0], "c2": [0.0, 0.0, 0.8]}, index=index)
    scope = pd.DataFrame(True, index=index, columns=severity.columns)
    layers = {"c1": "L1", "c2": "L2"}
    views = {"Equal": {"c1": 1.0, "c2": 1.0}}
    groups = pd.Series(["A", "A", "B"], index=index)
    log, norm, _ = native.prepare_native(severity, scope, layers, views, groups, name="offsets")
    result = wise.score(log, norm)
    backlog = wise.prioritize(result, by=native.GROUP, view="Equal")
    signed = wise.layer_contributions(result, backlog).loc["A"]
    assert signed["L1"] == pytest.approx(1 / 3)
    assert signed["L2"] == pytest.approx(-4 / 15)
    priority = backlog.table.loc["A", "PI"]
    assert max(float(signed.sum()), 0) == pytest.approx(priority)
    assert signed.clip(lower=0).sum() > priority


def test_further_case_attributes_travel_with_the_carrier():
    severity, scope, layers, weights, groups = example_assessments()
    extra = pd.DataFrame({"document": ["d1", "d1", "d2", "d2"]}, index=severity.index)
    log, norm, _ = native.prepare_native(severity, scope, layers, weights, groups, name="extra", attributes=extra)
    result = wise.score(log, norm)
    assert sorted(wise.prioritize(result, "document", view="Equal").table.index) == ["d1", "d2"]
    with pytest.raises(ValueError, match="further attributes"):
        native.prepare_native(severity, scope, layers, weights, groups, name="extra", attributes=extra.iloc[::-1])


@pytest.mark.parametrize("mode", ["flat", "layer_balanced"])
def test_scores_do_not_depend_on_case_order_serialisation_or_attached_context(mode):
    """Checks of the kind Section 5.6 names, on a constructed assessment: case order, a reloaded norm, attached context."""
    severity, scope, layers, weights, groups = example_assessments()
    log, norm, _ = native.prepare_native(severity, scope, layers, weights, groups, name="checks")
    base = wise.score(log, norm, mode=mode).scores
    order = [2, 0, 3, 1]  # complete cases in another order
    moved, norm_moved, _ = native.prepare_native(
        severity.iloc[order], scope.iloc[order], layers, weights, groups.iloc[order], name="checks"
    )
    assert norm_moved.fingerprint() == norm.fingerprint()
    assert residual(wise.score(moved, norm_moved, mode=mode).scores, base) == 0.0
    read_back = wise.Norm.loads(norm.dumps())  # the norm serialised and read back
    assert read_back.fingerprint() == norm.fingerprint()
    assert residual(wise.score(log, read_back, mode=mode).scores, base) == 0.0
    context = pd.DataFrame({"document": ["d1", "d1", "d2", "d2"], "vendor": ["v", None, "v", "w"]}, index=severity.index)
    with_context, norm_context, cases = native.prepare_native(severity, scope, layers, weights, groups, name="checks", attributes=context)
    assert norm_context.fingerprint() == norm.fingerprint() and {"document", "vendor"} <= set(cases.columns)
    assert residual(wise.score(with_context, norm_context, mode=mode).scores, base) == 0.0


@pytest.mark.parametrize("extra_axis", ["rows", "columns"])
def test_comparison_rejects_an_extra_expected_identity(extra_axis):
    actual = pd.DataFrame({"c1": [0.2]}, index=["case1"])
    expected = actual.copy()
    if extra_axis == "rows":
        expected.loc["case2"] = 0.3
    else:
        expected["c2"] = 0.3
    with pytest.raises(AssertionError, match="exact identity mismatch"):
        residual(actual, expected)


def test_comparison_rejects_duplicate_and_mismatched_identities():
    with pytest.raises(AssertionError, match="duplicate identities"):
        residual(pd.Series([0.2], index=["case1"]), pd.Series([0.2, 0.2], index=["case1", "case1"]))
    with pytest.raises(AssertionError, match="exact identity mismatch"):
        _same_labels(pd.Index(["case1"]), pd.Index(["case1", "extra"]), "scope rows")
    with pytest.raises(AssertionError, match="exact identity mismatch"):
        residual(pd.Series([0.2], index=pd.Index([np.nan])), pd.Series([0.2], index=["nan"]))
    with pytest.raises(AssertionError, match="missingness"):
        residual(pd.Series([0.2, np.nan], index=["a", "b"]), pd.Series([0.2, 0.1], index=["a", "b"]))


def test_comparison_allows_only_order_changes():
    actual = pd.DataFrame({"c1": [0.2, np.nan], "c2": [0.1, 0.3]}, index=["a", "b"])
    expected = actual.loc[["b", "a"], ["c2", "c1"]]
    assert residual(actual, expected) == 0
