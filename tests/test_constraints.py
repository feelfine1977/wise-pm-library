"""Constraint semantics, checked against the worked examples of paper Section 4.2."""

import numpy as np
import pandas as pd
import pytest
from _support.builders import evaluate, make_log

import wise
from wise.constraints import as_labels, constraint_from_dict
from wise.errors import NormError


@pytest.mark.paper
def test_sat_paper_examples():
    assert wise.sat(8, 10, 20) == 0.0
    assert wise.sat(15, 10, 20) == pytest.approx(0.25)
    assert wise.sat(20, 10, 20) == pytest.approx(0.5)
    assert wise.sat(30, 10, 20) == 1.0
    s = wise.sat(pd.Series([8, 15, np.nan, 30]), 10, 20)
    assert s.tolist()[:2] == [0.0, 0.25]
    assert np.isnan(s.iloc[2])
    assert s.iloc[3] == 1.0
    assert wise.sat(np.array([0, 40]), 10, 20).tolist() == [0.0, 1.0]
    assert isinstance(wise.sat(np.int64(15), 10, 20), float)


@pytest.mark.parametrize("width", [0, -1, float("nan"), float("inf")])
def test_sat_needs_a_positive_width(width):
    with pytest.raises(NormError, match="width"):
        wise.sat(1.0, 0.0, width)


def test_as_labels_accepts_a_single_string():
    assert as_labels("Record Goods Receipt") == ("Record Goods Receipt",)
    assert as_labels(["a", "b"]) == ("a", "b")
    with pytest.raises(NormError):
        as_labels([])
    with pytest.raises(NormError):
        as_labels(None)
    assert wise.Presence("abc").activity == ("abc",)


@pytest.mark.paper
def test_presence_indicator_and_partial():
    log = make_log([("a", "INV", 0, 1, "F"), ("a", "INV", 1, 1, "F"), ("b", "GR", 0, 1, "F")])
    v = evaluate(log, wise.Presence("INV"))
    assert v["a"] == 0.0
    assert v["b"] == 1.0
    v = evaluate(log, wise.Presence("INV", m=4))  # 1 − min(2/4, 1)
    assert v["a"] == pytest.approx(0.5)
    assert v["b"] == 1.0


@pytest.mark.paper
def test_exclusion_is_binary():
    log = make_log([("a", "CINV", 0, 1, "F"), ("a", "CINV", 1, 1, "F"), ("b", "GR", 0, 1, "F")])
    v = evaluate(log, wise.Exclusion("CINV"))
    assert v["a"] == 1.0
    assert v["b"] == 0.0


@pytest.mark.paper
def test_occurrence_limit_paper_example():
    rows = []
    for case, n in [("c2", 2), ("c3", 3), ("c4", 4), ("c5", 5), ("c6", 6)]:
        rows += [(case, "GR", d, 1, "F") for d in range(n)]
    v = evaluate(make_log(rows), wise.Singularity("GR", k=2, K=3))
    assert v["c2"] == 0.0
    assert v["c3"] == pytest.approx(1 / 3)
    assert v["c4"] == pytest.approx(2 / 3)
    assert v["c5"] == 1.0
    assert v["c6"] == 1.0


@pytest.mark.paper
def test_lag_paper_example_and_first_b_after_a():
    rows = [
        ("l10", "GR", 0, 1, "F"),
        ("l10", "INV", 10, 1, "F"),
        ("l20", "GR", 0, 1, "F"),
        ("l20", "INV", 20, 1, "F"),
        ("l30", "GR", 0, 1, "F"),
        ("l30", "INV", 30, 1, "F"),
        ("pre", "INV", -3, 1, "F"),
        ("pre", "GR", 0, 1, "F"),
        ("pre", "INV", 5, 1, "F"),
        ("only_pre", "INV", -3, 1, "F"),
        ("only_pre", "GR", 0, 1, "F"),
        ("same_instant", "GR", 0, 1, "F"),
        ("same_instant", "INV", 0, 1, "F"),
        ("no_a", "INV", 0, 1, "F"),
        ("no_b", "GR", 0, 1, "F"),
    ]
    log = make_log(rows)
    v = evaluate(log, wise.Lag("GR", "INV", delta=10, width=20))
    assert v["l10"] == 0.0
    assert v["l20"] == pytest.approx(0.5)
    assert v["l30"] == 1.0
    assert v["pre"] == 0.0  # the first INV at or after the first GR counts; an earlier INV is not forbidden
    assert v["only_pre"] == 1.0  # no INV follows the GR
    assert v["same_instant"] == 0.0  # "at or after"
    assert v["no_b"] == 1.0
    assert v["no_a"] == 1.0
    skip_a = evaluate(log, wise.Lag("GR", "INV", delta=10, width=20, missing_a="skip"))
    assert np.isnan(skip_a["no_a"])
    assert skip_a["no_b"] == 1.0
    skip = evaluate(log, wise.Lag("GR", "INV", delta=10, width=20, missing_b="skip"))
    assert np.isnan(skip["no_b"])
    assert np.isnan(skip["only_pre"])
    assert skip["l20"] == pytest.approx(0.5)


def test_lag_units():
    log = make_log([("h", "A", 0, 1, "F"), ("h", "B", 0.5, 1, "F")])  # 12 hours
    assert evaluate(log, wise.Lag("A", "B", delta=6, width=12, unit="h"))["h"] == pytest.approx(0.5)
    assert evaluate(log, wise.Lag("A", "B", delta=360, width=720, unit="min"))["h"] == pytest.approx(0.5)
    assert wise.Lag("A", "B", delta=1, width=1, unit="H").unit == "h"
    assert wise.Lag("A", "B", delta=1, width=1, unit="T").unit == "min"
    with pytest.raises(NormError):
        wise.Lag("A", "B", delta=1, width=1, unit="fortnight")


def test_a_lag_states_its_bound():
    with pytest.raises(TypeError):
        wise.Lag("A", "B")  # delta and width have no default
    with pytest.raises(NormError, match="lag"):
        constraint_from_dict("lag", {"a": "A", "b": "B"})
    with pytest.raises(NormError):
        wise.Lag("A", "B", delta=None, width=1)
    with pytest.raises(NormError):
        wise.Lag("A", "B", delta=1, width=0)


@pytest.mark.paper
def test_balance_paper_semantics():
    rows = [
        ("exact", "GR", 0, 100, "F"),
        ("exact", "INV", 1, 100, "F"),
        ("mis", "GR", 0, 100, "F"),
        ("mis", "INV", 1, 82, "F"),
        ("multi", "GR", 0, 40, "F"),
        ("multi", "GR", 1, 60, "F"),
        ("multi", "INV", 2, 100, "F"),
        ("missing", "GR", 0, 100, "F"),
        ("empty", "CLR", 0, 5, "F"),
    ]
    log = make_log(rows)
    v = evaluate(log, wise.Balance("amount", "INV", "amount", "GR", tau=0.05, width=0.20))
    assert v["exact"] == 0.0
    assert v["mis"] == pytest.approx((0.18 - 0.05) / 0.20)  # 0.65 as in Table 4
    assert v["multi"] == 0.0
    assert v["missing"] == 1.0  # the sum over an empty set of invoice events is 0
    assert v["empty"] == 0.0
    neg = make_log([("n", "GR", 0, -100, "F"), ("n", "INV", 1, 100, "F")])
    with pytest.raises(NormError, match="non-negative"):
        evaluate(neg, wise.Balance("amount", "INV", "amount", "GR"))


def test_balance_does_not_replace_a_missing_amount_by_zero():
    rows = [
        ("known", "GR", 0, 100, "F"),
        ("known", "INV", 1, 100, "F"),
        ("unknown", "GR", 0, 100, "F"),
        ("unknown", "INV", 1, None, "F"),
        ("partly", "GR", 0, 40, "F"),
        ("partly", "GR", 1, None, "F"),
        ("partly", "INV", 2, 40, "F"),
    ]
    log = make_log(rows)
    nc = wise.NormConstraint("c", "L", wise.Balance("amount", "INV", "amount", "GR"))
    ev = wise.evaluate(nc, log)
    assert ev.value["known"] == 0.0
    assert np.isnan(ev.value["unknown"])
    assert np.isnan(ev.value["partly"])
    assert ev.reason.astype(str).to_dict() == {"known": "evaluated", "partly": "missing_value", "unknown": "missing_value"}
    assert ev.in_scope.all()  # in business scope, evidence unavailable


def test_metric_on_a_case_attribute():
    frame = pd.DataFrame(
        {
            "case": ["a", "b", "c", "d"],
            "activity": "X",
            "time": pd.Timestamp("2024-01-01"),
            "touches": [2, 8, None, "many"],
        }
    )
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["touches"])
    v = evaluate(log, wise.Metric("touches", threshold=4, width=8))
    assert v["a"] == 0.0
    assert v["b"] == pytest.approx(0.5)
    assert np.isnan(v["c"])
    assert np.isnan(v["d"])
    identity = evaluate(log, wise.Metric("touches"))
    assert identity["a"] == 1.0  # sat(2; 0, 1) is clipped at 1


def test_identity_metric_preserves_a_bounded_value():
    frame = pd.DataFrame({"case": list("abc"), "activity": "X", "time": pd.Timestamp("2024-01-01"), "v": [0.0, 0.37, 1.0]})
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["v"])
    assert evaluate(log, wise.Metric("v", threshold=0, width=1)).tolist() == [0.0, 0.37, 1.0]


def test_applicability_masks_to_nan():
    log = make_log([("a", "INV", 0, 1, "DF1"), ("b", "GR", 0, 1, "DF2")])
    v = evaluate(log, wise.Presence("INV"), applicability={"flow_type": ["DF1"]})
    assert v["a"] == 0.0
    assert np.isnan(v["b"])
    v = evaluate(log, wise.Presence("INV"), applicability={"flow_type": "DF1"})  # bare string, not characters
    assert v["a"] == 0.0
    assert np.isnan(v["b"])
    with pytest.raises(NormError):
        evaluate(log, wise.Presence("INV"), applicability={"nope": ["x"]})


def test_activity_lists_merge_labels():
    log = make_log([("a", "Vendor creates invoice", 0, 1, "F"), ("b", "GR", 0, 1, "F")])
    v = evaluate(log, wise.Presence(["Record Invoice Receipt", "Vendor creates invoice"]))
    assert v["a"] == 0.0
    assert v["b"] == 1.0


def test_constraint_from_dict_aliases_conversion_and_validation():
    c = constraint_from_dict("pres", {"activity": "INV", "m": "2"})
    assert isinstance(c, wise.Presence)
    assert c.m == 2
    assert isinstance(constraint_from_dict("sing", {"activity": "GR", "k": 1, "K": "2"}), wise.Singularity)
    assert isinstance(constraint_from_dict("excl", {"activity": "CINV"}), wise.Exclusion)
    assert isinstance(constraint_from_dict("bal", {"attr_x": "x", "activities_x": "A", "attr_y": "y", "activities_y": "B"}), wise.Balance)
    with pytest.raises(NormError):
        constraint_from_dict("presence", {"activity": "INV", "bogus": 1})
    with pytest.raises(NormError):
        constraint_from_dict("unknown_type", {})
    with pytest.raises(NormError, match="integer"):
        constraint_from_dict("presence", {"activity": "INV", "m": 2.7})  # a count is not truncated
    with pytest.raises(NormError, match="integer"):
        constraint_from_dict("singularity", {"activity": "GR", "k": 0.9})
    for bad in (
        lambda: wise.Lag("A", "B", delta=-1, width=1),
        lambda: wise.Lag("A", "B", delta=1, width=-5),
        lambda: wise.Lag("A", "B", delta=1, width=1, missing_a="maybe"),
        lambda: wise.Lag("A", "B", delta=1, width=1, missing_b="censor"),
        lambda: wise.Lag("A", "B", delta="1", width=1),
        lambda: wise.Singularity("A", k=-1),
        lambda: wise.Singularity("A", K=0),
        lambda: wise.Presence("A", m=0),
        lambda: wise.Presence("A", m=True),
        lambda: wise.Balance("x", "A", "y", "B", tau=2.0),
        lambda: wise.Balance("x", "A", "y", "B", width=0),
        lambda: wise.Metric("x", width=-1),
        lambda: wise.Metric("", 1, 1),
        lambda: wise.Metric("x", threshold=float("nan")),
    ):
        with pytest.raises(NormError):
            bad()


def test_options_of_the_full_library_are_read_only_at_their_default():
    c = constraint_from_dict("metric", {"attribute": "x", "threshold": 0, "width": 1, "direction": "high"})
    assert c == wise.Metric("x")
    with pytest.raises(NormError, match="direction"):
        constraint_from_dict("metric", {"attribute": "x", "direction": "low"})
    lag = {"a": "A", "b": "B", "delta": 1, "width": 2, "activation": "first", "response": "first_after"}
    assert constraint_from_dict("lag", lag) == wise.Lag("A", "B", delta=1, width=2)
    with pytest.raises(NormError, match="activation"):
        constraint_from_dict("lag", {**lag, "activation": "each"})
    assert constraint_from_dict("exclusion", {"activity": "A", "after": None, "before": None}) == wise.Exclusion("A")
    with pytest.raises(NormError, match="after"):
        constraint_from_dict("singularity", {"activity": "A", "after": "B"})
    with pytest.raises(NormError, match="agg"):
        constraint_from_dict("balance", {"attr_x": "x", "activities_x": "A", "attr_y": "y", "activities_y": "B", "agg": "max"})


def test_constraints_are_hashable_and_comparable():
    assert wise.Presence("a") == wise.Presence(["a"])
    assert hash(wise.Presence("a")) == hash(wise.Presence(["a"]))
    assert wise.Lag("a", "b", delta=1, width=2).params()["a"] == ["a"]
    assert wise.Exclusion("a").describe().startswith("exclusion(")
    assert list(wise.CONSTRAINT_TYPES) == ["presence", "exclusion", "singularity", "lag", "balance", "metric"]
