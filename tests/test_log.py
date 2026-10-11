"""The event log: construction, refusals, primitives and the read-only contract."""

import numpy as np
import pandas as pd
import pytest
from _support.builders import make_log

import wise
from wise.errors import LogSchemaError


def _frame():
    return pd.DataFrame(
        {
            "case": ["b", "a", "a", "b", "a"],
            "activity": ["GR", "PO", "INV", "INV", "GR"],
            "time": pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-05", "2024-01-06", "2024-01-03"]),
            "amount": [5.0, 100.0, 60.0, 5.0, 40.0],
            "company": ["B", "A", "A", "B", "A"],
        }
    )


def _log(**kwargs):
    return wise.EventLog(_frame(), case_col="case", activity_col="activity", timestamp_col="time", **kwargs)


def test_case_table_and_primitives():
    log = _log(case_attributes=["company"], exposure_col="amount", exposure_agg="sum")
    assert len(log) == 2
    assert list(log.case_ids) == ["a", "b"]
    assert log.cases.index.name == "case"
    assert log.cases["n_events"].tolist() == [3, 2]
    assert log.cases["company"].tolist() == ["A", "B"]
    assert log.cases["exposure"].tolist() == [200.0, 10.0]
    assert log.cases["first_ts"]["a"] == pd.Timestamp("2024-01-01")
    assert log.cases["last_ts"]["a"] == pd.Timestamp("2024-01-05")
    assert log.count("GR").tolist() == [1.0, 1.0]
    assert log.count(["GR", "INV"]).tolist() == [2.0, 2.0]
    assert log.first_ts("INV")["b"] == pd.Timestamp("2024-01-06")
    assert pd.isna(log.first_ts("PO")["b"])
    t_a, t_b = log.first_after("GR", "INV")
    assert (t_b - t_a).dt.days.tolist() == [2, 4]
    assert log.total("amount", ["GR", "INV"]).tolist() == [100.0, 10.0]
    assert log.total("amount", "CLR").tolist() == [0.0, 0.0]  # the sum over an empty set
    assert log.activity_labels == ["PO", "GR", "INV"]
    assert list(log.trace("a")["activity"]) == ["PO", "GR", "INV"]
    assert "EventLog(5 events, 2 cases, 3 activities" in repr(log)
    with pytest.raises(LogSchemaError):
        log.trace("zzz")
    with pytest.raises(LogSchemaError):
        log.total("nope", "GR")
    with pytest.raises(LogSchemaError):
        log.attribute("nope")


def test_events_are_sorted_by_case_time_and_order_column():
    frame = pd.DataFrame(
        {"case": ["a", "a", "a"], "activity": ["second", "first", "third"], "time": pd.Timestamp("2024-01-01"), "seq": [2, 1, 3]}
    )
    by_row = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time")
    assert list(by_row.events["activity"]) == ["second", "first", "third"]
    by_seq = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", order_col="seq")
    assert list(by_seq.events["activity"]) == ["first", "second", "third"]


def test_the_input_frame_and_the_log_are_not_changed_by_their_users():
    frame = _frame()
    before = frame.copy()
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["company"])
    pd.testing.assert_frame_equal(frame, before)
    cases = log.cases
    cases["company"] = "changed"
    cases["extra"] = 1
    assert log.cases["company"].tolist() == ["A", "B"]
    assert "extra" not in log.cases.columns
    events = log.events
    events.loc[:, "activity"] = "changed"
    assert "changed" not in set(log.events["activity"])
    counts = log.count("GR")
    counts.iloc[:] = 99.0
    assert log.count("GR").tolist() == [1.0, 1.0]
    attributes = log.case_attributes
    attributes.append("x")
    assert log.case_attributes == ["company"]


def test_refusals_name_the_problem():
    with pytest.raises(LogSchemaError, match="missing columns"):
        wise.EventLog(_frame(), case_col="nope", activity_col="activity", timestamp_col="time")
    with pytest.raises(LogSchemaError, match="no rows"):
        wise.EventLog(_frame().iloc[:0], case_col="case", activity_col="activity", timestamp_col="time")
    null_case = _frame()
    null_case.loc[0, "case"] = None
    with pytest.raises(LogSchemaError, match="null case id"):
        wise.EventLog(null_case, case_col="case", activity_col="activity", timestamp_col="time")
    with pytest.raises(LogSchemaError, match="reserved"):
        wise.EventLog(_frame().assign(score=1), case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["score"])
    with pytest.raises(LogSchemaError, match="missing_timestamps"):
        _log(missing_timestamps="ignore")
    with pytest.raises(LogSchemaError, match="exposure_agg"):
        _log(exposure_col="amount", exposure_agg="idxmax")
    with pytest.raises(LogSchemaError, match="case_attribute_values"):
        _log(case_attribute_values="any")
    negative = _frame()
    negative["amount"] = -1.0
    with pytest.raises(LogSchemaError, match="negative case exposure"):
        wise.EventLog(negative, case_col="case", activity_col="activity", timestamp_col="time", exposure_col="amount")


def test_missing_timestamps_raise_drop_or_keep():
    frame = _frame()
    frame["time"] = frame["time"].astype(object)
    frame.loc[2, "time"] = None  # the INV of case a
    kwargs = {"case_col": "case", "activity_col": "activity", "timestamp_col": "time"}
    with pytest.raises(LogSchemaError, match="null or unparseable"):
        wise.EventLog(frame, **kwargs)
    dropped = wise.EventLog(frame, missing_timestamps="drop", **kwargs)
    assert dropped.count("INV").tolist() == [0.0, 1.0]
    assert dropped.n_missing_timestamps == 0
    kept = wise.EventLog(frame, missing_timestamps="keep", **kwargs)
    assert kept.n_missing_timestamps == 1
    assert kept.count("INV").tolist() == [1.0, 1.0]  # counted
    assert pd.isna(kept.first_ts("INV")["a"])  # but it defines no timestamp
    assert list(kept.trace("a")["activity"])[-1] == "INV"  # and sorts last in its case
    assert kept.cases["last_ts"]["a"] == pd.Timestamp("2024-01-03")
    _, t_b = kept.first_after("GR", "INV")
    assert pd.isna(t_b["a"])  # never a lag endpoint
    all_missing = frame.assign(time=None)
    with pytest.raises(LogSchemaError, match="would leave no event"):
        wise.EventLog(all_missing, missing_timestamps="drop", **kwargs)


def test_string_timestamps_time_zones_and_formats():
    frame = _frame().assign(time=["02-01-2024 10:00", "01-01-2024 09:00", "05-01-2024 09:00", "06-01-2024 09:00", "03-01-2024 09:00"])
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", timestamp_format="%d-%m-%Y %H:%M")
    assert log.cases["first_ts"]["b"] == pd.Timestamp("2024-01-02 10:00")
    dayfirst = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time", dayfirst=True)
    assert dayfirst.cases["first_ts"]["b"] == pd.Timestamp("2024-01-02 10:00")
    aware = _frame().assign(time=["2024-01-02T10:00+01:00", "2024-01-01T09:00+02:00", "2024-01-05T09:00+01:00", "2024-01-06T09:00+01:00", "2024-01-03T09:00+01:00"])
    utc = wise.EventLog(aware, case_col="case", activity_col="activity", timestamp_col="time", utc=True)
    assert str(utc.tz) == "UTC"
    assert utc.cases["first_ts"]["a"] == pd.Timestamp("2024-01-01 07:00", tz="UTC")


def test_varying_case_attributes_are_recorded_or_refused():
    frame = _frame()
    frame.loc[4, "company"] = "Z"  # case a now has two companies
    kwargs = {"case_col": "case", "activity_col": "activity", "timestamp_col": "time", "case_attributes": ["company"]}
    log = wise.EventLog(frame, **kwargs)
    assert dict(log.varying_case_attributes) == {"company": 1}
    assert log.cases["company"]["a"] == "A"  # the first non-null value in event order
    with pytest.raises(LogSchemaError, match="vary within a case"):
        wise.EventLog(frame, case_attribute_values="strict", **kwargs)
    assert dict(_log(case_attributes=["company"]).varying_case_attributes) == {}


def test_categorical_columns_and_null_activities():
    frame = _frame()
    frame["case"] = frame["case"].astype("category")
    frame["activity"] = frame["activity"].astype("category")
    log = wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time")
    assert log.count("INV").tolist() == [1.0, 1.0]
    with_null = _frame()
    with_null.loc[0, "activity"] = None
    log = wise.EventLog(with_null, case_col="case", activity_col="activity", timestamp_col="time")
    assert log.n_null_activities == 1
    assert log.count("GR").tolist() == [1.0, 0.0]
    assert log.cases["n_events"].tolist() == [3, 2]


def test_helper_log_builder():
    log = make_log([("a", "X", 0, 1, "F")])
    assert log.case_attributes == ["flow_type"]
    assert np.isclose(log.attribute("n_events")["a"], 1.0)
