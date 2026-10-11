"""Evaluation checks on the public logs.

These tests need the logs. Put them in one folder (see the README for where
each is obtained) and name the folder in the environment variable
``WISE_PAPER_DATA``; without it, or without a log, the tests of that log are
skipped with a message that says so.

    WISE_PAPER_DATA=<folder> python -m pytest tests/test_paper_evaluation.py
"""

import json
import os
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wise.evaluation import data, evaluate, native, paper, replay

pytestmark = [pytest.mark.data, pytest.mark.paper]

EXPECTED = {int(item["item"]): item for item in paper.expected_values()}
LOG_OF = {"bpic2019": "BPI Challenge 2019", "bpic2013_incidents": "BPI Challenge 2013 (incidents)", "bpic2017": "BPI Challenge 2017"}


def _require(*datasets: str) -> None:
    if not os.environ.get(data.DATA_ENVIRONMENT):
        pytest.skip(f"the public logs are not supplied: set {data.DATA_ENVIRONMENT} to the folder that holds them (see README)")
    for dataset in datasets:
        if not data.available(dataset):
            pytest.skip(f"{LOG_OF[dataset]} is not in the folder named by {data.DATA_ENVIRONMENT}: {data.entry(dataset)['file']['name']}")


def _datasets(item: int) -> tuple[str, ...]:
    needed = EXPECTED[item]["data"]
    if needed is None:
        return ()
    return tuple(replay.APPLICATIONS) if needed == "all" else (needed,)


@pytest.mark.parametrize("item", sorted(EXPECTED))
def test_computed_values_agree_with_reported_values(item):
    """Each result item of the paper: every computed value agrees with the printed one at the printed precision."""
    _require(*_datasets(item))
    comparison = paper.compare(items=[item])
    differing = comparison[comparison["status"] != paper.AGREES]
    assert differing.empty, "\n" + differing[["quantity", "printed", "computed", "status"]].to_string(index=False)
    assert len(comparison) == len(EXPECTED[item]["values"])


@pytest.mark.parametrize("application", replay.APPLICATIONS)
def test_consistency_with_the_reference_arithmetic(application):
    """Section 5.6 for one application: scope and evidence identical, every difference below the tolerance of 1e-8."""
    _require(application)
    app = paper.application(application)
    report = replay.consistency(app.assessment, app.result)
    assert report["scope_identical"] and report["evidence_identical"]
    # three views, six mode-view combinations (flat and layer-balanced), each checked at γ = 0 and γ = 20
    assert report["views"] == 3 and report["mode_view_combinations"] == 6 and report["gammas"] == [0.0, 20.0]
    combinations = {(check["mode"], check["view"]) for check in report["differential_checks"]}
    assert combinations == {(mode, view) for mode in ("flat", "layer_balanced") for view in app.views}
    for check in report["differential_checks"]:
        assert {"gamma0_PI", "gamma20_PI", "gamma0_stable_PI", "gamma20_stable_PI"} <= set(check["residuals"]), check["mode"]
    # the digits of the residual depend on the machine and on library versions: the bound is asserted, not the digits
    assert report["max_residual"] < replay.TOLERANCE
    assert report["passed"]


@pytest.mark.parametrize("application", replay.APPLICATIONS)
def test_further_checks_preserve_the_scores(application):
    """For one application, beyond the constructed tests that Section 5.6 names: the scores of all views, under
    flat and layer-balanced scoring, are preserved when complete cases are reordered, when the norm is
    serialised and read back, and when the whole-case context is attached."""
    _require(application)
    assessment = paper.application(application).assessment
    report = replay.further_checks(assessment)
    assert set(report["residuals"]) == {"reordered", "norm_read_back", "context_attached"}
    for check, largest in report["residuals"].items():
        assert largest < replay.TOLERANCE, check
    assert report["fingerprint_unchanged"] and report["passed"]
    assert report["modes"] == ["flat", "layer_balanced"] and report["views"] == 3
    # the context is made of attributes of the whole case; attaching it adds them to the scored cases and to nothing else
    context = list(replay.CONTEXT[application])
    assert report["context"] == context and set(context) <= set(assessment.features.columns)
    plain = native.replay(assessment)
    attached = native.replay(assessment, attributes=assessment.features[context])
    assert set(attached.cases.columns) - set(plain.cases.columns) == set(context)
    # the reordering really changes the order of the cases and keeps every case whole
    reordered = replay._reordered(assessment)
    assert list(reordered.severity.index) != list(assessment.severity.index)
    assert sorted(reordered.severity.index) == sorted(assessment.severity.index)
    pd.testing.assert_frame_equal(reordered.severity.loc[assessment.severity.index], assessment.severity)
    pd.testing.assert_series_equal(reordered.groups.loc[assessment.groups.index], assessment.groups)


@pytest.mark.parametrize("application", replay.APPLICATIONS)
def test_calculation_record_identifies_what_appendix_b_names(application, tmp_path):
    """Appendix B.2: a record identifies the source export and checksum, the adapter configuration and checksum, the
    norm fingerprint, the tested settings, evidence summaries, the ordered results and the numerical checks."""
    _require(application)
    record = paper.calculation_record(application)
    assert set(paper.RECORD_PARTS) <= set(record)
    assert (record["kind"], record["application"]) == ("calculation record", application)
    # the identity of the input is the catalogued one; the file is found by name without regard to letter case
    catalogued = data.entry(application)["file"]
    source = record["source_export"]
    assert (source["file"], source["bytes"], source["sha256"]) == (catalogued["name"], catalogued["bytes"], catalogued["sha256"])
    assert source["file_as_found"].lower() == catalogued["name"].lower() == data.locate(application).name.lower()
    assert source["events"] > source["cases"] > 0
    assert paper.input_identity(application).to_dict() == source
    app = paper.application(application)
    configuration = record["adapter_configuration"]
    assert configuration["sha256"] == paper.configuration_sha256(app.assessment.configuration)
    assert len(configuration["sha256"]) == 64 and configuration["id"] == app.assessment.configuration["id"]
    assert record["norm"]["fingerprint"] == native.native_norm(application).fingerprint()
    settings = record["tested_settings"]
    assert list(settings["views"]) == app.views and len(settings["views"]) == 3
    assert settings["scoring_modes"] == ["flat", "layer_balanced"] and settings["gammas"] == [0.0, 20.0]
    assert settings["primary_scoring_mode"] == "flat" and "descending" in settings["tie_order"]
    cases = source["cases"]
    assert list(record["evidence_summaries"]) == list(app.assessment.severity.columns)
    for criterion, states in record["evidence_summaries"].items():
        assert states["cases"] == cases == states["in_scope"] + states["outside_scope"], criterion
        assert states["in_scope"] == states["evaluated"] + sum(states["unavailable"].values()), criterion
    for view, ranked in record["ordered_results"].items():
        groups = ranked["groups"]
        assert len(groups) == settings["groups"] and [g["rank"] for g in groups] == list(range(1, len(groups) + 1))
        assert sum(g["scored_cases"] for g in groups) == ranked["scored_cases"]
        order = [(-g["priority_index"], -g["scored_cases"], g["group"]) for g in groups]
        assert order == sorted(order), view  # Priority Index descending, scored cases descending, group ascending
        assert groups[0]["group"] == paper._label(paper._lead_group(app, view))
    checks = record["numerical_checks"]
    assert checks["reference_arithmetic"]["passed"] and checks["reference_arithmetic"]["max_residual"] < checks["tolerance"] == 1e-8
    assert checks["reference_arithmetic"]["scope_identical"] and checks["reference_arithmetic"]["evidence_identical"]
    assert checks["further_checks"]["passed"] and set(checks["further_checks"]["residuals"]) == {"reordered", "norm_read_back", "context_attached"}
    # it is plain JSON, holds no case of the log and no path of this machine
    text = json.dumps(record, allow_nan=False)
    assert str(data.data_folder()) not in text and str(Path.home()) not in text
    assert not set(map(str, app.assessment.severity.index[:200])) & set(text.replace('"', " ").split())
    written, passed = evaluate.write_records(tmp_path)
    assert passed and f"calculation_record_{application}.json" in written
    assert json.loads((tmp_path / f"calculation_record_{application}.json").read_text(encoding="utf-8"))["application"] == application


def _reference(name: str) -> pd.DataFrame:
    with resources.files("wise.evaluation").joinpath("expected", name).open(encoding="utf-8") as stream:
        return pd.read_csv(stream)


@pytest.mark.parametrize("application", replay.APPLICATIONS)
def test_computed_tables_agree_with_reference_tables(application):
    """The shipped aggregate reference results: per view the summary, the ranked groups and the layer contributions."""
    _require(application)
    from wise.evaluation import reference_tables

    computed = reference_tables.build(applications=[application])
    for name, frame in computed.items():
        expected = _reference(f"{name}.csv")
        expected = expected[expected["application"] == application].reset_index(drop=True)
        assert list(frame.columns) == list(expected.columns), name
        assert len(frame) == len(expected), name
        for column in frame.columns:
            if pd.api.types.is_float_dtype(expected[column]):
                np.testing.assert_allclose(frame[column].to_numpy(float), expected[column].to_numpy(float), rtol=0, atol=1e-9, err_msg=f"{name}.{column}")
            else:
                assert frame[column].astype(str).tolist() == expected[column].astype(str).tolist(), f"{name}.{column}"


def test_figures_are_drawn_with_the_computed_values():
    _require("bpic2019")
    pytest.importorskip("matplotlib")
    import matplotlib.text

    for draw, expected in (
        (paper.figure_5, ["Packaging: n = 76,608; median = 69.04 days", "Remaining groups: n = 106,661; median = 28.93 days"]),
        (paper.figure_4, ["109,199 scored PO items; Priority Index = 1,776.19", "+2,365.44", "-332.42", "-267.95", "+11.13",
                          "5,242 scored PO items; Priority Index = 664.61", "+811.13", "-154.25", "+10.54", "-2.81"]),
        (paper.figure_6, ["18/20", "10/20", "8/20", "6/10", "4/10", "10/10"]),
    ):  # fmt: skip
        fig = draw()
        texts = [t.get_text() for t in fig.findobj(matplotlib.text.Text)]
        for text in expected:
            assert text in texts, text
