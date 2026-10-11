"""The domain adapters on constructed records: scope, evidence rules and deviation values."""

import gzip
import hashlib

import numpy as np
import pytest

from wise.evaluation.adapters import EVALUATED, OUT_OF_SCOPE, bpic2013, bpic2017, bpic2019, configuration, xes

DF1, DF2, CONS, TWO = "3-way match, invoice after GR", "3-way match, invoice before GR", "Consignment", "2-way match"
HEADER = (
    "eventID ,case Spend area text,case Company,case Vendor,case Item Category,case Purchasing Document,"
    "case Item,case concept:name,event org:resource,event concept:name,event time:timestamp"
)


def _bpic19_csv(tmp_path):
    """A constructed export in the layout of the challenge CSV; (document, item, category, resource, activity, time)."""
    events = [
        # a DF2 item: invoice 2 January, clearing 60 days later → C04 = (60 − 30) / 60 = 0.5
        ("100", "1", DF2, "user_001", "Create Purchase Order Item", "01-01-2018 08:00:00.000"),
        ("100", "1", DF2, "batch_02", "Record Goods Receipt", "01-01-2018 09:00:00.000"),
        ("100", "1", DF2, "user_002", "Record Invoice Receipt", "02-01-2018 00:00:00.000"),
        ("100", "1", DF2, "user_002", "Clear Invoice", "03-03-2018 00:00:00.000"),
        # a DF1 item: invoice before the goods receipt (C05 = 1), no clearing, two invoice receipts, one price change
        ("100", "2", DF1, " USER_003 ", "Record Invoice Receipt", "05-01-2018 00:00:00.000"),
        ("100", "2", DF1, "user_003", "Record Goods Receipt", "06-01-2018 00:00:00.000"),
        ("100", "2", DF1, "user_004", "Record Invoice Receipt", "07-01-2018 00:00:00.000"),
        ("100", "2", DF1, "user_004", "Change Price", "08-01-2018 00:00:00.000"),
        # a Consignment item: invoicing is outside the item's process
        ("200", "1", CONS, "user_005", "Record Goods Receipt", "01-02-2018 00:00:00.000"),
        # a two-way item: no goods receipt required; first invoice outside the plausibility interval; unusable resource
        ("200", "2", TWO, "NONE", "Record Invoice Receipt", "01-01-2008 00:00:00.000"),
        ("200", "2", TWO, "user_006", "Record Invoice Receipt", "01-03-2018 00:00:00.000"),
        ("200", "2", TWO, "user_006", "Clear Invoice", "01-04-2018 00:00:00.000"),
        ("200", "2", TWO, "user_006", "Cancel Invoice Receipt", "02-04-2018 00:00:00.000"),
        # a DF2 item whose clearing is recorded before its invoice: negative lag
        ("300", "1", DF2, "user_007", "Clear Invoice", "01-05-2018 00:00:00.000"),
        ("300", "1", DF2, "user_007", "Record Invoice Receipt", "02-05-2018 00:00:00.000"),
    ]
    lines = [HEADER]
    for i, (doc, item, category, resource, activity, time) in enumerate(events):
        area = "" if doc == "300" else "Packaging"
        lines.append(f"{i},{area},companyID_0000,vendorID_{doc},\"{category}\",{doc},{item},{doc}_{item},{resource},{activity},{time}")
    path = tmp_path / "BPI_Challenge_2019.csv"
    path.write_bytes(("\n".join(lines) + "\n").encode("cp1252"))
    cfg = dict(configuration("bpic2019"))
    cfg.update(
        expected_csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), expected_events=len(events), expected_cases=5, expected_documents=3
    )
    return path, cfg


def test_bpic19_scope_evidence_and_values(tmp_path):
    path, cfg = _bpic19_csv(tmp_path)
    events = bpic2019.read_events(path, cfg)
    f = bpic2019.features_from_events(events, cfg)
    V, scope, state, raw = bpic2019.assessment_matrices(f, cfg)
    assert f["flow"].to_dict() == {"100_1": "DF2", "100_2": "DF1", "200_1": "Consignment", "200_2": "2-way", "300_1": "DF2"}
    assert f.loc["300_1", "group"] == "companyID_0000 | (missing)"  # a missing spend area is an explicit category
    assert f.loc["100_1", "group"] == "companyID_0000 | Packaging"
    # business scope by flow category
    assert scope.loc["200_1"].to_dict() == {
        "C01": False, "C02": False, "C03": False, "C04": False, "C05": False, "C06": True, "C07": True, "C08": False, "C09": True, "C10": True,
    }  # fmt: skip
    assert scope.loc["200_2", ["C03", "C05"]].tolist() == [False, False]
    assert scope.loc["100_1", "C05"] == np.False_ and scope.loc["100_2", "C05"] == np.True_
    assert set(state.to_numpy()[~scope.to_numpy()]) == {OUT_OF_SCOPE}
    # the DF2 item
    assert raw.loc["100_1", "C04"] == pytest.approx(60.0)
    assert V.loc["100_1", "C04"] == pytest.approx(0.5)
    assert V.loc["100_1", ["C01", "C02", "C03", "C06", "C07", "C08"]].tolist() == [0.0] * 6
    assert raw.loc["100_1", "C09"] == 3.0 and raw.loc["100_1", "C10"] == 2.0  # batch_02 is usable but not a user
    assert V.loc["100_1", "C09"] == 0.0
    # the DF1 item
    assert V.loc["100_2", "C05"] == 1.0
    assert V.loc["100_2", "C02"] == 1.0
    assert state.loc["100_2", "C04"] == "missing_prerequisite"
    assert V.loc["100_2", "C08"] == pytest.approx(1 / 3)
    assert V.loc["100_2", "C07"] == pytest.approx(1 / 3)
    assert raw.loc["100_2", "C10"] == 2.0  # " USER_003 " and "user_003" are one identity: case and whitespace are ignored
    # the two-way item: the earliest invoice is out of range and is not replaced by the later, plausible one
    assert state.loc["200_2", "C04"] == "invalid_temporal_evidence"
    assert np.isnan(V.loc["200_2", "C04"])
    assert V.loc["200_2", "C06"] == 1.0
    assert state.loc["200_2", ["C09", "C10"]].tolist() == ["missing_resource_evidence"] * 2
    # a negative first-invoice-to-first-clearing lag is not evaluated
    assert raw.loc["300_1", "C04"] == pytest.approx(-1.0)
    assert state.loc["300_1", "C04"] == "invalid_temporal_evidence"
    assert V.notna().equals(state.eq(EVALUATED))


def test_bpic19_timestamp_selection_rules(tmp_path):
    """Appendix B.1: the earliest parsed timestamp is selected; an unparsable one is passed over when another exists;
    for C05, equal timestamps have zero deviation."""
    events = [
        # an invoice record without a usable timestamp, a second one on 2 January, clearing 60 days later
        ("100", "1", DF2, "user_001", "Record Invoice Receipt", "not a timestamp"),
        ("100", "1", DF2, "user_001", "Record Invoice Receipt", "02-01-2018 00:00:00.000"),
        ("100", "1", DF2, "user_001", "Clear Invoice", "03-03-2018 00:00:00.000"),
        # the only invoice record has no usable timestamp
        ("100", "2", DF2, "user_001", "Record Invoice Receipt", ""),
        ("100", "2", DF2, "user_001", "Clear Invoice", "03-03-2018 00:00:00.000"),
        # a DF1 item whose invoice and goods receipt carry the same timestamp
        ("100", "3", DF1, "user_001", "Record Invoice Receipt", "05-01-2018 10:00:00.000"),
        ("100", "3", DF1, "user_001", "Record Goods Receipt", "05-01-2018 10:00:00.000"),
    ]
    lines = [HEADER] + [
        f"{i},Packaging,companyID_0000,vendorID_1,\"{category}\",{doc},{item},{doc}_{item},{resource},{activity},{time}"
        for i, (doc, item, category, resource, activity, time) in enumerate(events)
    ]
    path = tmp_path / "BPI_Challenge_2019.csv"
    path.write_bytes(("\n".join(lines) + "\n").encode("cp1252"))
    cfg = dict(configuration("bpic2019"))
    cfg.update(expected_csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), expected_events=len(events), expected_cases=3, expected_documents=1)
    f = bpic2019.features_from_events(bpic2019.read_events(path, cfg), cfg)
    V, _, state, raw = bpic2019.assessment_matrices(f, cfg)
    assert f.loc["100_1", "n_invoice"] == 2 and raw.loc["100_1", "C04"] == pytest.approx(60.0)
    assert state.loc["100_1", "C04"] == EVALUATED and V.loc["100_1", "C04"] == pytest.approx(0.5)
    assert V.loc["100_1", "C08"] == pytest.approx(1 / 3)  # both invoice records count
    assert state.loc["100_2", "C04"] == "invalid_temporal_evidence" and np.isnan(V.loc["100_2", "C04"])
    assert V.loc["100_2", "C01"] == 0.0  # the invoice is recorded; only its timestamp is unusable
    assert state.loc["100_3", "C05"] == EVALUATED and raw.loc["100_3", "C05"] == 0.0 and V.loc["100_3", "C05"] == 0.0


def test_bpic19_assess_and_refusals(tmp_path, monkeypatch):
    path, cfg = _bpic19_csv(tmp_path)
    monkeypatch.setattr(bpic2019, "configuration", lambda name: cfg)
    assessment = bpic2019.assess(path)
    assert assessment.application == "bpic2019"
    assert assessment.source == {
        "file": "BPI_Challenge_2019.csv",
        "bytes": path.stat().st_size,
        "sha256": cfg["expected_csv_sha256"],
        "events": 15,
        "cases": 5,
        "documents": 3,
        "activities": 6,
    }
    assert assessment.views["Operations"]["C09"] == 3.0
    assert assessment.groups.nunique() == 2
    with pytest.raises(ValueError, match="checksum"):
        bpic2019.read_events(path, {**cfg, "expected_csv_sha256": "0" * 64})
    with pytest.raises(ValueError, match="number of events"):
        bpic2019.read_events(path, {**cfg, "expected_events": 99})
    with pytest.raises(FileNotFoundError):
        bpic2019.read_events(tmp_path / "missing.csv", cfg)


def _xes(tmp_path, name, traces):
    """Write a gzip-compressed XES file; traces = [(trace attributes, [event attributes])]."""

    def attributes(mapping, indent):
        return "".join(f'{indent}<string key="{k}" value="{v}"/>\n' for k, v in mapping.items() if v is not None)

    body = '<?xml version="1.0" encoding="UTF-8"?>\n<log xes.version="1.0" xmlns="http://www.xes-standard.org/">\n'
    for trace, events in traces:
        body += "  <trace>\n" + attributes(trace, "    ")
        for event in events:
            body += "    <event>\n" + attributes(event, "      ") + "    </event>\n"
        body += "  </trace>\n"
    body += "</log>\n"
    path = tmp_path / name
    path.write_bytes(gzip.compress(body.encode("utf-8")))
    return path


def test_sequence_values_compress_and_count_returns():
    assert bpic2013.sequence_values(["A", "A", "B", "B", "A"]) == (2, 1)
    assert bpic2013.sequence_values(["A", "B", "A", "B", "A", "C"]) == (5, 3)
    assert bpic2013.sequence_values(["A"]) == (0, 0)
    assert bpic2013.sequence_values(["A", "B", "C", "A"]) == (3, 0)  # a return is immediate: A–B–A


def _incident(team, status, substatus, time, product="PROD1"):
    return {"org:group": team, "concept:name": status, "lifecycle:transition": substatus, "product": product, "time:timestamp": time}


def test_bpic13_features_and_evidence_rules(tmp_path):
    traces = [
        (
            {"concept:name": "ping-pong"},
            [
                _incident("T1", "Accepted", "In Progress", "2012-01-01T00:00:00+00:00"),
                _incident("T2", "Queued", "Awaiting Assignment", "2012-01-02T00:00:00+00:00"),
                _incident("T1", "Accepted", "In Progress", "2012-01-03T00:00:00+00:00"),
                _incident("T1", "Accepted", "Wait - User", "2012-01-04T00:00:00+00:00"),
                _incident("T1", "Completed", "Closed", "2012-01-20T12:00:00+00:00"),
                _incident("T1", "Accepted", "In Progress", "2012-01-21T00:00:00+00:00"),
            ],
        ),
        (
            {"concept:name": "tie"},
            [
                _incident("T1", "Accepted", "In Progress", "2012-02-01T00:00:00+00:00"),
                _incident("T2", "Accepted", "In Progress", "2012-02-01T00:00:00+00:00"),  # two teams at one instant
                _incident("T2", "Completed", "Closed", "2012-02-02T00:00:00+00:00", product="PROD2"),
            ],
        ),
        ({"concept:name": "single"}, [_incident(None, "Accepted", "In Progress", "2012-03-01T00:00:00+00:00")]),
    ]
    path = _xes(tmp_path, "incidents.xes.gz", traces)
    cfg = dict(configuration("bpic2013"))
    cfg["expected"] = {"cases": 3, "events": 10, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    f = bpic2013.features(bpic2013.read_events(path, cfg), cfg)
    V, scope, state, raw = bpic2013.assessment_matrices(f, cfg)
    assert scope.all().all()  # all six criteria apply to incidents
    row = f.loc["ping-pong"]
    assert (row.team_changes, row.team_returns, row.repeated_substatus, row.wait_user_count, row.post_completed_active) == (2, 1, 2, 1, 1)
    assert row.span_days == pytest.approx(20.0)
    assert V.loc["ping-pong"].tolist() == pytest.approx([0.0, 0.5, 0.0, 1.0, 13 / 23, 1.0])
    assert f.loc["tie", "product_group"] == "(multiple values)"
    assert state.loc["tie", ["C01", "C02"]].tolist() == ["ambiguous_timestamp_tie"] * 2
    assert V.loc["tie", ["C01", "C02"]].isna().all()
    assert V.loc["tie", "C06"] == 0.0  # the statuses at the tied instant agree
    assert state.loc["single", ["C01", "C02"]].tolist() == ["missing_team_value"] * 2
    assert state.loc["single", "C05"] == "insufficient_endpoints"
    assert V.loc["single", ["C03", "C04", "C06"]].tolist() == [0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="checksum"):
        bpic2013.read_events(path, {**cfg, "expected": {**cfg["expected"], "sha256": "0" * 64}})


def _work(activity, lifecycle, resource, time, **more):
    return {"concept:name": activity, "lifecycle:transition": lifecycle, "org:resource": resource, "time:timestamp": time, **more}


def test_bpic17_features_and_evidence_rules(tmp_path):
    t = "2016-01-{:02d}T10:00:00.000+01:00"
    traces = [
        (
            {"concept:name": "App_1", "ApplicationType": "New credit", "LoanGoal": "Car"},
            [
                _work("A_Create Application", "complete", "User_1", t.format(1)),
                _work("W_Complete application", "start", "User_1", t.format(2)),
                _work("W_Complete application", "suspend", "User_1", t.format(2)),
                _work("W_Complete application", "start", "User_2", t.format(3)),
                _work("W_Complete application", "start", "User_3", t.format(4)),
                _work("O_Create Offer", "complete", "User_3", t.format(5), EventID="Offer_1"),
                _work("O_Created", "complete", "User_3", t.format(5), EventID="OfferState_1", OfferID="Offer_1"),
                _work("O_Create Offer", "complete", "User_3", t.format(6), EventID="Offer_2"),
                _work("O_Created", "complete", "User_3", t.format(6), EventID="OfferState_2", OfferID="Offer_2"),
                _work("A_Incomplete", "complete", "User_3", t.format(7)),
                _work("A_Incomplete", "complete", "User_3", t.format(31)),
            ],
        ),
        (
            {"concept:name": "App_2", "ApplicationType": "New credit", "LoanGoal": "Home improvement"},
            [_work("A_Create Application", "complete", "User_1", t.format(1)), _work("A_Cancelled", "complete", "User_1", t.format(2))],
        ),
        (
            {"concept:name": "App_3", "ApplicationType": "Limit raise", "LoanGoal": "Car"},
            [
                _work("A_Create Application", "complete", "User_1", t.format(1)),
                _work("O_Create Offer", "complete", "User_1", t.format(2), EventID="Offer_9"),
                _work("O_Created", "complete", "User_1", t.format(2), EventID="OfferState_9", OfferID="Offer_8"),
            ],
        ),
    ]
    path = _xes(tmp_path, "applications.xes.gz", traces)
    cfg = dict(configuration("bpic2017"))
    cfg["expected"] = {"cases": 3, "events": 16, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    f = bpic2017.read_features(path, cfg)
    V, scope, state, raw = bpic2017.assessment_matrices(f, cfg)
    first = f.loc["App_1"]
    assert first.observed_span_days == pytest.approx(30.0)
    assert (first.repeated_work_starts, first.work_start_resource_breadth, first.offer_multiplicity, first.incomplete_state_records) == (2, 3, 2, 2)
    assert V.loc["App_1"].tolist() == pytest.approx([0.0, 2 / 5, 1 / 5, 1 / 3, 2 / 3])
    # C04 is in scope only when an offer activity is recorded
    assert scope["C04"].to_dict() == {"App_1": True, "App_2": False, "App_3": True}
    assert state.loc["App_2", "C04"] == OUT_OF_SCOPE
    assert V.loc["App_2", ["C02", "C03", "C05"]].tolist() == [0.0, 0.0, 0.0]  # no work starts: an observed zero
    # creation identifiers that do not reconcile with the created offers make C04 unavailable
    assert state.loc["App_3", "C04"] == "unevaluable"
    assert np.isnan(V.loc["App_3", "C04"])


def test_xes_reader_refuses_declarations_and_streams_traces(tmp_path):
    good = _xes(tmp_path, "good.xes.gz", [({"concept:name": "a"}, [{"concept:name": "x"}]), ({"concept:name": "b"}, [])])
    traces = [[child.get("value") for child in trace if xes.local(child.tag) == "string"] for trace in xes.iter_traces(good)]
    assert traces == [["a"], ["b"]]
    bad = tmp_path / "bad.xes"
    bad.write_text('<?xml version="1.0"?>\n<!DOCTYPE log [<!ENTITY x "y">]>\n<log><trace/></log>\n', encoding="utf-8")
    with pytest.raises(ValueError, match="document type"):
        list(xes.iter_traces(bad))
    other = tmp_path / "other.xml"
    other.write_text('<?xml version="1.0"?>\n<data><trace/></data>\n', encoding="utf-8")
    with pytest.raises(ValueError, match="XES"):
        list(xes.iter_traces(other))
