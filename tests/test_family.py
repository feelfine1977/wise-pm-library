"""The constraint-family interface: evaluations with reasons, the registry, parsing from documents."""

import numpy as np
import pandas as pd
import pytest
from _support.builders import make_log

import wise
from wise import family as fam
from wise.errors import NormError


def test_evaluation_keeps_the_three_states_apart():
    rows = [("in_ok", "GR", 0, 1, "DF1"), ("in_ok", "INV", 3, 1, "DF1"), ("in_open", "GR", 0, 1, "DF1"), ("out", "X", 0, 1, "DF2")]
    log = make_log(rows)
    nc = wise.NormConstraint(
        "lag", "L", wise.Lag("GR", "INV", delta=1, width=4, missing_b="skip"), applicability={"flow_type": ["DF1"]}
    )
    ev = wise.evaluate(nc, log)
    assert isinstance(ev, wise.Evaluation)
    assert ev.value.name == ev.reason.name == "lag"
    assert ev.value["in_ok"] == pytest.approx(0.5)
    assert ev.reason.astype(str).to_dict() == {"in_ok": "evaluated", "in_open": "missing_response", "out": "out_of_scope"}
    assert ev.in_scope.to_dict() == {"in_ok": True, "in_open": True, "out": False}
    assert ev.evaluated.to_dict() == {"in_ok": True, "in_open": False, "out": False}


def test_reasons_of_lag_and_metric():
    log = make_log([("a", "GR", 0, 1, "F"), ("b", "INV", 0, 1, "F")])
    skip = wise.evaluate(wise.Lag("GR", "INV", delta=1, width=1, missing_a="skip", missing_b="skip"), log)
    assert skip.reason.astype(str).to_dict() == {"a": "missing_response", "b": "missing_activation"}
    violate = wise.evaluate(wise.Lag("GR", "INV", delta=1, width=1), log)
    assert violate.value.tolist() == [1.0, 1.0]
    assert (violate.reason == fam.EVALUATED).all()
    frame = pd.DataFrame({"case": ["a", "b"], "activity": "X", "time": pd.Timestamp("2024-01-01"), "m": [0.5, None]})
    carrier = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["m"])
    metric = wise.evaluate(wise.Metric("m"), carrier)
    assert metric.reason.astype(str).tolist() == ["evaluated", "missing_attribute"]


def test_unknown_scope_is_its_own_reason():
    frame = pd.DataFrame(
        {"case": ["a", "b", "c"], "activity": "X", "time": pd.Timestamp("2024-01-01"), "flow": ["DF1", None, "DF2"]}
    )
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["flow"])
    nc = wise.NormConstraint("p", "L", wise.Presence("X"), applicability={"flow": ["DF1"]})
    ev = wise.evaluate(nc, log)
    assert ev.reason.astype(str).tolist() == ["evaluated", "scope_unknown", "out_of_scope"]
    assert ev.in_scope.tolist() == [True, False, False]
    assert np.isnan(ev.value["b"])


def test_evaluation_consistency_is_checked():
    index = pd.Index(["a", "b"])
    with pytest.raises(NormError, match="exactly where"):
        wise.Evaluation(pd.Series([0.1, np.nan], index=index), pd.Series(["evaluated", "evaluated"], index=index))
    with pytest.raises(NormError, match="one index"):
        wise.Evaluation(pd.Series([0.1], index=["a"]), pd.Series(["evaluated"], index=["b"]))
    with pytest.raises(NormError):
        wise.Evaluation.of([np.nan], pd.Index(["a"]), why=[([True], "evaluated")])
    built = wise.Evaluation.of([0.2, np.nan, np.nan], pd.Index(list("abc")), why=[([False, True, False], fam.MISSING_VALUE)])
    assert built.reason.astype(str).tolist() == ["evaluated", "missing_value", "not_evaluable"]


def test_registry_and_family_lookup():
    assert [f.name for f in fam.families()] == list(wise.CONSTRAINT_TYPES)
    assert fam.family("pres") is fam.family("presence")
    assert fam.family_of(wise.Exclusion("a")).name == "exclusion"
    with pytest.raises(NormError, match="unknown constraint type"):
        fam.family("order")
    with pytest.raises(NormError, match="already registered"):
        fam.register(fam.family("lag"))
    inputs = fam.family_of(wise.Balance("x", "A", "y", "B")).requires(wise.Balance("x", "A", "y", "B"))
    assert inputs.activities == ("A", "B")
    assert inputs.event_columns == ("x", "y")
    assert fam.family_of(wise.Metric("m")).requires(wise.Metric("m")).case_attributes == ("m",)


def test_parse_refuses_what_is_not_a_parameter_mapping():
    with pytest.raises(NormError, match="mapping"):
        fam.family("presence").parse(["INV"])
    with pytest.raises(NormError, match="not numeric"):
        fam.family("lag").parse({"a": "A", "b": "B", "delta": "soon", "width": 1})
