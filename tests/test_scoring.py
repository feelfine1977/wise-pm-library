"""Case scoring against Table 4 of the paper, the scoring modes, coverage and the three states."""

import numpy as np
import pandas as pd
import pytest
from _support.builders import make_log

import wise
from wise.errors import NormError, NotScoredError

TABLE_4 = {
    "A": (0.6625, 0.8875),
    "B": (0.9667, 0.7000),
    "C": (0.8700, 0.9675),
    "D": (0.9000, 0.9000),
    "E": (0.1500, 0.5500),
}


@pytest.mark.paper
def test_table_4_scores(p2p_result):
    for case, (finance, logistics) in TABLE_4.items():
        assert p2p_result.scores.loc[case, "Finance"] == pytest.approx(finance, abs=5e-5)
        assert p2p_result.scores.loc[case, "Logistics"] == pytest.approx(logistics, abs=5e-5)
    assert p2p_result.mode == "flat"


@pytest.mark.paper
def test_table_4_nonzero_violations(p2p_result):
    V = p2p_result.violations
    assert V.loc["A", "c2"] == pytest.approx(0.75)
    assert V.loc["B", "c5"] == pytest.approx(2 / 3)
    assert V.loc["C", "c3"] == pytest.approx(0.65)
    assert V.loc["D", "c6"] == 1.0
    assert V.loc["E", "c1"] == 1.0
    assert V.loc["E", "c2"] == 1.0
    assert V.loc["E", "c3"] == 1.0
    assert V["c4"].isna().all()
    assert not p2p_result.in_scope["c4"].any()
    assert V.drop(columns="c4").fillna(0.0).to_numpy().sum() == pytest.approx(0.75 + 2 / 3 + 0.65 + 1 + 3)


@pytest.mark.paper
def test_worked_scores_of_section_4_4(p2p_result):
    # S(Finance)(σA) = 1 − 0.45·0.75; S(Logistics)(σA) = 1 − 0.15·0.75; S(Finance)(σB) = 29/30
    assert p2p_result.scores.loc["A", "Finance"] == pytest.approx(1 - 0.45 * 0.75)
    assert p2p_result.scores.loc["A", "Logistics"] == pytest.approx(1 - 0.15 * 0.75)
    assert p2p_result.scores.loc["B", "Finance"] == pytest.approx(29 / 30)


@pytest.mark.paper
def test_layer_decomposition_exact(p2p_result):
    assert p2p_result.check_decomposition(atol=1e-12) < 1e-12
    contributions = p2p_result.contributions["Finance"]
    assert contributions.loc["A", "timing"] == pytest.approx(0.45 * 0.75)
    assert contributions.loc["A"].drop("timing").sum() == 0.0
    penalty = p2p_result.penalties("Logistics").sum(axis=1)
    pd.testing.assert_series_equal(penalty, 1 - p2p_result.scores["Logistics"], check_names=False)


def test_effective_weights_renormalise_over_the_evaluated_constraints(p2p_result):
    w = p2p_result.effective_weights("Finance").loc["A"]
    assert w["c4"] == 0.0
    assert w.sum() == pytest.approx(1.0)
    assert w["c2"] == pytest.approx(0.45)
    with pytest.raises(NormError):
        p2p_result.effective_weights("Nope")


def test_unscored_cases_are_nan_and_cannot_be_ranked(p2p_log, p2p_norm):
    norm = p2p_norm.map_constraints(lambda c: c.replace(applicability={"flow_type": ["DF1"]}))
    result = wise.score(p2p_log, norm)
    assert result.scores.isna().all().all()
    assert result.contributions["Finance"].isna().all().all()
    assert result.coverage("Finance").isna().all()  # no in-scope weight: coverage is undefined
    with pytest.raises(NotScoredError):
        wise.prioritize(result, ["flow_type"], view="Finance")


@pytest.mark.paper
def test_scoring_modes(p2p_log, p2p_norm):
    full = p2p_norm.map_constraints(lambda c: c.replace(applicability={}))
    flat = wise.score(p2p_log, full)
    balanced = wise.score(p2p_log, full, mode="layer_balanced")
    pd.testing.assert_frame_equal(flat.scores, balanced.scores)  # they coincide when everything is evaluated
    assert flat.violations["c4"].tolist() == [0.0] * 5  # ordered and received amounts agree
    result_flat = wise.score(p2p_log, p2p_norm)
    result_balanced = wise.score(p2p_log, p2p_norm, mode="layer_balanced")
    assert (result_flat.mode, result_balanced.mode) == ("flat", "layer_balanced")
    result_balanced.check_decomposition()
    assert result_flat.scores.loc["C", "Finance"] == pytest.approx(0.87, abs=1e-6)
    # layer-balanced: the layer "match" keeps its weight 0.20 + 0.05 on c3 alone; the layer weights sum to 1.05
    assert result_balanced.scores.loc["C", "Finance"] == pytest.approx(1 - 0.25 / 1.05 * 0.65, abs=1e-6)
    stored = p2p_norm.replace(scoring_mode="layer_balanced")
    pd.testing.assert_frame_equal(wise.score(p2p_log, stored).scores, result_balanced.scores)
    assert wise.Norm.loads(stored.dumps()).scoring_mode == "layer_balanced"
    with pytest.raises(NormError):
        wise.score(p2p_log, p2p_norm, mode="magic")


@pytest.mark.paper
def test_layer_balanced_keeps_the_weight_of_a_partly_evaluated_layer():
    # layers L1 = {a, b} with raw weights 1, 1 and L2 = {c} with raw weight 2; b cannot be evaluated
    frame = pd.DataFrame({"case": ["x"], "activity": "X", "time": pd.Timestamp("2024-01-01"), "a": [1.0], "b": [None], "c": [0.0]})
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["a", "b", "c"])
    norm = wise.Norm(
        [wise.NormConstraint(k, layer, wise.Metric(k)) for k, layer in (("a", "L1"), ("b", "L1"), ("c", "L2"))],
        [wise.Layer("L1"), wise.Layer("L2")],
        [wise.View("v", constraint_weights={"a": 1, "b": 1, "c": 2})],
    )
    flat = wise.score(log, norm, mode="flat")
    balanced = wise.score(log, norm, mode="layer_balanced")
    assert flat.scores.loc["x", "v"] == pytest.approx(1 - 1 / 3)  # a carries 1 of the evaluated weight 3
    assert balanced.scores.loc["x", "v"] == pytest.approx(1 - 1 / 2)  # L1 keeps 2 of 4, all of it on a
    assert balanced.effective_weights("v").loc["x"].tolist() == pytest.approx([0.5, 0.0, 0.5])
    assert flat.coverage("v")["x"] == pytest.approx(3 / 4)
    assert balanced.coverage("v")["x"] == pytest.approx(3 / 4)  # coverage uses raw weights in both modes


@pytest.mark.paper
def test_scope_evidence_and_coverage_are_kept_apart():
    rows = [("a", "GR", 0, 1, "DF1"), ("a", "INV", 3, 1, "DF1"), ("b", "GR", 0, 1, "DF1"), ("c", "X", 0, 1, "DF2")]
    log = make_log(rows)
    norm = wise.Norm(
        [
            wise.NormConstraint(
                "lag", "L", wise.Lag("GR", "INV", delta=1, width=1, missing_b="skip"), applicability={"flow_type": ["DF1"]}
            ),
            wise.NormConstraint("pres", "L", wise.Presence("GR")),
        ],
        [wise.Layer("L")],
        [wise.View("v", constraint_weights={"lag": 3, "pres": 1})],
    )
    result = wise.score(log, norm)
    assert result.in_scope["lag"].tolist() == [True, True, False]
    assert result.evaluated["lag"].tolist() == [True, False, False]  # no response for case b: evidence unavailable
    # coverage = raw weight evaluated / raw weight in scope
    assert result.coverage("v").tolist() == pytest.approx([1.0, 0.25, 1.0])
    # renormalisation gives case b a score from "pres" alone; coverage says how much of its scope that is
    assert result.scores["v"].tolist() == pytest.approx([0.25, 1.0, 0.0])
    assert result.coverage("v").name == "coverage"


@pytest.mark.paper
def test_bound_for_unavailable_severities():
    # Appendix A.1: with coverage c and penalty q, the complete-scope penalty lies in [c·q, c·q + (1 − c)]
    rng = np.random.default_rng(7)
    n = 200
    full = pd.DataFrame(rng.uniform(0, 1, size=(n, 4)), columns=list("abcd"))
    observed = full.mask(rng.uniform(size=full.shape) < 0.3)
    weights = {"a": 1.0, "b": 2.0, "c": 0.5, "d": 3.0}

    def scored(values):
        frame = values.assign(case=[f"c{i}" for i in range(n)], activity="X", time=pd.Timestamp("2024-01-01"))
        log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=list("abcd"))
        norm = wise.Norm(
            [wise.NormConstraint(k, "L", wise.Metric(k)) for k in "abcd"], [wise.Layer("L")], [wise.View("v", constraint_weights=weights)]
        )
        return wise.score(log, norm)

    partial, complete = scored(observed), scored(full)
    q, c = 1 - partial.scores["v"], partial.coverage("v")
    q_scope = 1 - complete.scores["v"]
    ok = q.notna()
    assert ((c * q)[ok] <= q_scope[ok] + 1e-12).all()
    assert (q_scope[ok] <= (c * q + (1 - c))[ok] + 1e-12).all()


def test_frame_views_and_provenance(p2p_result, p2p_log, p2p_norm):
    f = p2p_result.frame("Finance")
    assert {"score", "contrib__completeness", "company"} <= set(f.columns)
    wide = p2p_result.frame()
    assert "score__Logistics" in wide.columns
    assert "contrib__Finance__match" in wide.columns
    assert "ScoreResult(5 cases" in repr(p2p_result)
    assert p2p_result.norm_fingerprint == wise.running_p2p_norm().fingerprint()
    assert p2p_result.wise_version == wise.__version__
    assert len(p2p_result.trace("B")) == 7
    with pytest.raises(NormError):
        p2p_result.frame("Nope")
    result = wise.score(p2p_log, p2p_norm, views="Finance")
    assert result.views == ["Finance"]
    assert wise.score(p2p_log, p2p_norm, views=["Finance", "Finance"]).views == ["Finance"]
    with pytest.raises(NormError):
        wise.score(p2p_log, p2p_norm, views=["Nope"])


def test_scoring_does_not_change_the_log(p2p_log, p2p_norm):
    cases, events = p2p_log.cases, p2p_log.events
    result = wise.score(p2p_log, p2p_norm)
    result.cases["company"] = "changed"
    pd.testing.assert_frame_equal(p2p_log.cases, cases)
    pd.testing.assert_frame_equal(p2p_log.events, events)


@pytest.mark.paper
def test_two_stage_weights_agree_with_flat_raw_weights(p2p_norm, p2p_log):
    constraints = [c.replace(weight=(0.8 if c.id == "c3" else 0.2 if c.id == "c4" else 1.0), applicability={}) for c in p2p_norm.constraints]
    view = wise.View("Two", layer_weights={"completeness": 0.2, "timing": 0.45, "match": 0.25, "handling": 0.05, "exceptions": 0.05})
    norm = wise.Norm(constraints, p2p_norm.layers, [view])
    w = norm.raw_weights("Two")
    assert w["c3"] == pytest.approx(0.25 * 0.8)
    assert w["c4"] == pytest.approx(0.25 * 0.2)
    assert norm.layer_weight_table().loc["match", "Two"] == pytest.approx(0.25)
    # with every constraint evaluated, the layer-balanced mode agrees with flat scoring for two-stage weights
    pd.testing.assert_frame_equal(wise.score(p2p_log, norm, mode="flat").scores, wise.score(p2p_log, norm, mode="layer_balanced").scores)
