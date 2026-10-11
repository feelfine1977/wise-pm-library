"""The adapter configurations and native norms against the specification of the paper (Appendix B.1, Table B1)."""

import numpy as np
import pandas as pd
import pytest

import wise
from wise.evaluation import native, paper
from wise.evaluation.adapters import bpic2013, bpic2017, bpic2019, configuration


def _criteria(cfg):
    return {c["id"]: c for c in cfg["criteria"]}


@pytest.mark.paper
def test_bpic19_configuration_is_table_b1():
    cfg = configuration("bpic2019")
    assert cfg["id"] == "wise-bpic19-transparent-ten-v1"  # the norm named in Section 5.1
    rules = _criteria(cfg)
    assert list(rules) == [f"C{i:02d}" for i in range(1, 11)]
    # graded checks: zero at the threshold, one at threshold + width
    endpoints = {cid: (r["threshold"], r["threshold"] + r["width"]) for cid, r in rules.items() if "threshold" in r}
    assert endpoints == {"C04": (30, 90), "C07": (0, 3), "C08": (1, 4), "C09": (5, 15), "C10": (2, 7)}
    assert {cid: r["scope"] for cid, r in rules.items()} == {
        "C01": "non-consignment", "C02": "non-consignment", "C03": "DF1 or DF2", "C04": "non-consignment", "C05": "DF1",
        "C06": "all", "C07": "all", "C08": "non-consignment", "C09": "all", "C10": "all",
    }  # fmt: skip
    layers = {cid: r["layer"] for cid, r in rules.items()}
    assert [cid for cid, layer in layers.items() if layer == "Completion"] == ["C01", "C02", "C03"]
    assert [cid for cid, layer in layers.items() if layer == "Timing"] == ["C04", "C05"]
    assert [cid for cid, layer in layers.items() if layer == "Rework"] == ["C06", "C07", "C08"]
    assert [cid for cid, layer in layers.items() if layer == "Effort proxy"] == ["C09", "C10"]
    order = ["Completion", "Timing", "Rework", "Effort proxy"]
    assert [cfg["views"]["Balanced"][layer] for layer in order] == [1, 1, 1, 1]
    assert [cfg["views"]["Completion"][layer] for layer in order] == [3, 2, 1, 1]
    assert [cfg["views"]["Operations"][layer] for layer in order] == [1, 1, 2, 3]
    assert (cfg["timing_plausibility_start"], cfg["timing_plausibility_end_exclusive"]) == ("2017-01-01", "2020-01-01")
    assert (cfg["primary_scoring_mode"], cfg["primary_gamma"]) == ("flat", 0)
    # with all ten criteria evaluated, the layers carry (0.3, 0.2, 0.3, 0.2) of the Balanced weight
    weights = pd.Series(bpic2019.weights_for(cfg, "Balanced"))
    shares = weights.groupby(pd.Series(layers)).sum() / weights.sum()
    assert shares.reindex(order).tolist() == pytest.approx([0.3, 0.2, 0.3, 0.2])
    assert list(paper.table_b1().index) == list(rules)
    assert paper.table_b1().loc["C04", "deviation scale"] == "0 at 30; 1 at 90"
    assert paper.table_b1().loc["C01", "deviation scale"] == "binary"


@pytest.mark.paper
def test_bpic13_configuration():
    cfg = configuration("bpic2013")
    rules = _criteria(cfg)
    assert {cid: (r["threshold"], r["width"]) for cid, r in rules.items()} == {
        "C01": (2, 4), "C02": (0, 2), "C03": (2, 8), "C04": (0, 1), "C05": (7, 23), "C06": (0, 1),
    }  # fmt: skip
    assert [r["layer"] for r in rules.values()] == ["Routing", "Routing", "Recorded patterns", "Recorded patterns", "Timing", "Reactivation"]
    order = ["Routing", "Recorded patterns", "Timing", "Reactivation"]
    assert [cfg["views"]["Balanced"][layer] for layer in order] == [1, 1, 1, 1]
    assert [cfg["views"]["Routing"][layer] for layer in order] == [3, 1, 1, 1]
    assert [cfg["views"]["Timing"][layer] for layer in order] == [1, 1, 3, 2]
    assert bpic2013.weights_for(cfg, "Timing") == {"C01": 1.0, "C02": 1.0, "C03": 1.0, "C04": 1.0, "C05": 3.0, "C06": 2.0}
    assert paper.incident_criteria().loc["C02", "deviation scale"] == "r(x; 0, 2)"
    assert paper.incident_criteria().loc["C04", "deviation scale"] == "binary"


@pytest.mark.paper
def test_bpic17_configuration():
    cfg = configuration("bpic2017")
    rules = cfg["criteria"]
    assert {cid: (r["threshold"], r["width"]) for cid, r in rules.items()} == {
        "C01": (30, 30), "C02": (0, 5), "C03": (2, 5), "C04": (1, 3), "C05": (0, 3),
    }  # fmt: skip
    assert {cid: r["layer"] for cid, r in rules.items()} == {
        "C01": "Timing", "C02": "Interaction", "C03": "Interaction", "C04": "Offer", "C05": "Interaction",
    }  # fmt: skip
    assert list(cfg["views"]["Balanced"].values()) == [1, 1, 1, 1, 1]
    assert list(cfg["views"]["Timeliness"].values()) == [4, 1, 1, 1, 1]
    assert list(cfg["views"]["Interaction"].values()) == [1, 3, 3, 1, 3]
    assert cfg["primary_group"] == ["application_type", "loan_goal"]
    assert paper.lending_criteria().loc["C01", "deviation scale"] == "r(x; 30, 30)"
    assert bpic2017.APPLICATION == "bpic2017"


@pytest.mark.parametrize(
    ("application", "name", "criteria", "views"),
    [
        ("bpic2019", "wise-bpic19-transparent-ten-v1", 10, ["Balanced", "Completion", "Operations"]),
        ("bpic2013_incidents", "wise-bpic2013-transfer-six-v1", 6, ["Balanced", "Routing", "Timing"]),
        ("bpic2017", "loan_application_recorded_concerns_v1", 5, ["Balanced", "Timeliness", "Interaction"]),
    ],
)
def test_native_norm_files_are_the_norms_of_the_configurations(application, name, criteria, views):
    norm = native.native_norm(application)
    assert norm.name == name
    assert len(norm.constraints) == criteria
    assert norm.view_names == views
    assert norm.scoring_mode == "flat"
    assert all(isinstance(nc.constraint, wise.Metric) for nc in norm.constraints)
    cfg = configuration("bpic2013" if application == "bpic2013_incidents" else application)
    if isinstance(cfg["criteria"], dict):
        layers = {cid: c["layer"] for cid, c in cfg["criteria"].items()}
        weights = {view: {c: float(w) for c, w in ws.items()} for view, ws in cfg["views"].items()}
    else:
        layers = {c["id"]: c["layer"] for c in cfg["criteria"]}
        weights = {view: {c["id"]: float(ws[c["layer"]]) for c in cfg["criteria"]} for view, ws in cfg["views"].items()}
    assert norm.layer_of.to_dict() == layers
    assert {view: norm.raw_weights(view) for view in views} == weights
    # the same norm is built from the configuration alone, on a one-case placeholder assessment
    index = pd.Index(["case"], name="case_id")
    severity = pd.DataFrame(np.zeros((1, len(layers))), index=index, columns=list(layers))
    scope = pd.DataFrame(True, index=index, columns=list(layers))
    _, built, _ = native.prepare_native(
        severity, scope, layers, weights, pd.Series(["g"], index=index), name=str(cfg["id"]), version=str(cfg["version"])
    )
    assert built.fingerprint() == norm.fingerprint()


def test_running_norm_table():
    table = paper.table_3()
    assert list(table.index) == ["c1", "c2", "c3", "c4", "c5", "c6"]
    assert table.loc["c2", "Finance"] == 0.45 and table.loc["c5", "Logistics"] == 0.45
    assert table.loc["c1", "layer"] == "Core completeness"
