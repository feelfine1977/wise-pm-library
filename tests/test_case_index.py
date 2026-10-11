"""The immutable case index behind the event log."""

import numpy as np
import pandas as pd
import pytest

from wise.case_index import NAT, CaseIndex, event_order
from wise.errors import LogSchemaError


def _index():
    #        case 0: A@1, B@2, A@(no time)    case 1: B@5    case 2: (no events)
    codes = np.array([0, 0, 0, 1])
    ts = np.array([1, 2, NAT, 5])
    acts = np.array([0, 1, 0, 1])
    return CaseIndex(codes, ts, acts, ["A", "B"], n_cases=3)


def test_primitives():
    idx = _index()
    assert (idx.n_cases, idx.n_events) == (3, 4)
    assert idx.count().tolist() == [3, 1, 0]
    assert idx.count("A").tolist() == [2, 0, 0]  # an event without a timestamp counts
    assert idx.count(["A", "B"]).tolist() == [3, 1, 0]
    assert idx.count("unknown").tolist() == [0, 0, 0]
    assert idx.first("A").tolist() == [1, NAT, NAT]
    assert idx.last("A").tolist() == [1, NAT, NAT]  # the untimed A never defines a timestamp
    assert idx.first().tolist() == [1, 5, NAT]
    assert idx.last().tolist() == [2, 5, NAT]
    assert idx.count(np.array([True, False, False, True])).tolist() == [1, 1, 0]
    assert idx.starts.tolist() == [0, 3, 4]
    assert idx.sizes.tolist() == [3, 1, 0]
    assert idx.activity_labels == ("A", "B")


def test_total_keeps_empty_sums_at_zero_and_missing_values_missing():
    idx = _index()
    values = np.array([10.0, 5.0, np.nan, 7.0])
    assert idx.total(values, "B").tolist() == [5.0, 7.0, 0.0]
    total_a = idx.total(values, "A")
    assert np.isnan(total_a[0])  # one selected event has no number
    assert total_a[1:].tolist() == [0.0, 0.0]
    with pytest.raises(LogSchemaError):
        idx.total(values[:2])


def test_index_is_immutable():
    idx = _index()
    with pytest.raises(AttributeError):
        idx.n = 3
    with pytest.raises(AttributeError):
        del idx._codes
    for array in (idx.case_codes, idx.timestamps, idx.valid, idx.starts, idx.sizes):
        with pytest.raises(ValueError):
            array[0] = 0


def test_refuses_what_is_not_sorted_or_consistent():
    with pytest.raises(LogSchemaError, match="sorted by case"):
        CaseIndex([1, 0], [1, 2], [0, 0], ["A"])
    with pytest.raises(LogSchemaError, match="sorted by timestamp"):
        CaseIndex([0, 0], [2, 1], [0, 0], ["A"])
    with pytest.raises(LogSchemaError, match="timestamp"):
        CaseIndex([0, 0], [NAT, 1], [0, 0], ["A"])  # an untimed event sorts last
    with pytest.raises(LogSchemaError, match="same length"):
        CaseIndex([0, 0], [1], [0, 0], ["A"])
    with pytest.raises(LogSchemaError, match="activity codes"):
        CaseIndex([0], [1], [3], ["A"])
    with pytest.raises(LogSchemaError, match="labels"):
        _index().mask([1, 2])
    with pytest.raises(LogSchemaError, match="boolean"):
        _index().count(np.array([1, 0, 0, 1]))


def test_event_order_and_datetimes():
    order = event_order([1, 0, 0, 0], [5, NAT, 2, 2], tie=[0, 0, 9, 1])
    assert order.tolist() == [3, 2, 1, 0]  # case, then time (missing last), then the tie-break
    idx = CaseIndex([0], [0], [0], ["A"], tz="Europe/Amsterdam")
    converted = idx.to_datetime([0, NAT])
    assert str(converted.tz) == "Europe/Amsterdam"
    assert converted[0] == pd.Timestamp("1970-01-01 01:00", tz="Europe/Amsterdam")
    assert pd.isna(converted[1])
