"""Regression cases for stage scope, follow-up, and one clearing penalty."""

import csv
from datetime import datetime, timedelta

import pytest

from wise.evaluation import native
from wise.evaluation.adapters import OUT_OF_SCOPE, bpic2019, bpic2019_staged, configuration
from wise.evaluation.data import sha256
from .test_adapters import CONS, DF2, HEADER, TWO


def test_staged_norm_distinguishes_follow_up_and_reversal_evidence(tmp_path):
    flows = {1: DF2, 2: DF2, 3: DF2, 4: DF2, 5: DF2, 6: CONS, 7: TWO, 8: DF2}
    create = datetime(2018, 7, 1)
    late_create = datetime(2018, 10, 1)
    act = {
        1: [(15, "Record Goods Receipt"), (16, "Cancel Goods Receipt")],
        2: [(10, "Record Invoice Receipt"), (80, "Record Goods Receipt"), (110, "Clear Invoice")],
        3: [(10, "Record Goods Receipt"), (20, "Record Invoice Receipt"), (125, "Clear Invoice")],
        4: [(20, "Record Invoice Receipt"), (80, "Record Goods Receipt")],
        5: [(5, "Record Invoice Receipt"), (10, "Clear Invoice"), (15, "Record Goods Receipt")],
        6: [(10, "Record Goods Receipt")],
        7: [(5, "Record Invoice Receipt"), (65, "Clear Invoice")],
        8: [(10, "Record Goods Receipt"), (15, "Delete Purchase Order Item")],
    }
    path = tmp_path / "sample.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER.split(","))
        event_id = 0
        for item, flow in flows.items():
            anchor = late_create if item == 4 else create
            for day, label in [(0, "Create Purchase Order Item"), *act[item]]:
                stamp = (anchor + timedelta(days=day)).strftime("%d-%m-%Y %H:%M:%S.000")
                writer.writerow([event_id, "Packaging", "companyID_0000", "vendorID_1", flow,
                                 100, item, f"100_{item}", "user_001", label, stamp])
                event_id += 1
    digest = sha256(path)
    cfg = configuration("bpic2019")
    cfg.update(expected_csv_sha256=digest, expected_events=event_id, expected_cases=8, expected_documents=1)
    events = bpic2019.read_events(path, cfg)
    baseline = bpic2019.assess_events(events, cfg, path, digest)
    staged = bpic2019_staged.prepare(events, baseline)
    assert list(staged.views) == ["Cross-functional Review", "Finance & Accounts Payable", "Logistics & Operations"]
    assert staged.severity.loc["100_1", "S01"] == 1
    assert staged.features.loc["100_1", "goods_reversal_records"] == 1
    assert staged.severity.loc["100_2", "S01"] == 0
    assert staged.features.loc["100_2", "completion_assessment_reason"] == "cleared_within_post_receipt_horizon"
    assert staged.raw.loc["100_2", "C04"] == 30
    assert staged.severity.loc["100_3", "S01"] == 1
    assert staged.state.loc["100_3", "C04"] == "clearing_absence_already_assessed"
    assert staged.raw.loc["100_3", "C04"] == 105
    assert staged.state.loc["100_4", "S01"] == "insufficient_clearing_follow_up"
    assert staged.state.loc["100_5", "S01"] == "conflicting_clearing_chronology"
    assert staged.features.loc["100_5", "df2_clearing_before_receipt_review"]
    assert staged.state.loc["100_6", "S01"] == OUT_OF_SCOPE
    assert staged.severity.loc["100_7", "C04"] == pytest.approx(0.5)
    assert staged.state.loc["100_8", "S01"] == "deletion_marker"
    assert native.replay(staged).scores.notna().all().all()
