"""The expected-values file and the comparison of computed with printed values, without any log."""

import json
from importlib import resources

import pandas as pd
import pytest

from wise.evaluation import DataNotAvailable, data, paper


NUMBERS = [*range(1, 23), 24, 25, 26, 29, 30, 31, 32, 33, *range(35, 43)]  # 23, 27, 28 and 34 are not in use


def test_expected_values_list_every_result_item():
    items = paper.expected_values()
    assert [item["item"] for item in items] == NUMBERS
    assert len(items) == 38
    assert {item["item"] for item in items if item["kind"] == "figure"} == {11, 18, 25}
    assert sorted(paper.ITEMS) == NUMBERS
    for item in items:
        assert item["place"] and item["title"]
        assert item["data"] in (None, "bpic2019", "bpic2013_incidents", "bpic2017", "all")
        keys = [value["key"] for value in item["values"]]
        assert len(keys) == len(set(keys)) > 0
        for value in item["values"]:
            assert value["kind"] in ("number", "count", "text", "flag", "order")
            assert value["printed"] != "" and value["quantity"]
            if value["kind"] == "number":
                assert isinstance(value["decimals"], int)
    values = [(item["item"], value) for item in items for value in item["values"]]
    assert len(values) == 259
    # the one machine-dependent residual is compared by its order of magnitude
    assert [(number, value["key"]) for number, value in values if value["kind"] == "order"] == [(33, "largest_difference")]
    # the counts that the adapters enforce before anything is computed
    assert [(number, value["key"]) for number, value in values if value.get("input_check")] == [
        (3, "events"), (3, "po_items"), (3, "documents"), (26, "events"), (26, "incidents"), (31, "applications"),
    ]  # fmt: skip


@pytest.mark.paper
def test_items_without_data_agree_with_the_paper():
    comparison = paper.compare(items=[1, 2, 40, 41, 42])
    assert comparison.groupby("item").size().to_dict() == {1: 17, 2: 12, 40: 17, 41: 60, 42: 2}
    assert comparison["agrees"].all()
    assert (comparison["status"] == "agrees").all()
    table = paper.item_01_table_4()
    assert table.loc["σB", "S(Finance)"] == 0.9667
    assert table.loc["σE", "non-zero violations"] == "ν_c1 = 1, ν_c2 = 1, ν_c3 = 1"
    worked = paper.item_02_worked_arithmetic()
    assert worked["computed"].tolist() == pytest.approx([0, 0.25, 0.5, 1, 0, 0.5, 1, 1 / 3, 2 / 3, 1, 0.14, 33.6])
    assert paper.table_4().equals(table)
    # Section 5.1 and Appendix B.1: the weights of the purchase-to-pay norm
    weights = paper.item_40_view_weights()
    assert weights["layer share under Balanced"].tolist() == pytest.approx([0.3, 0.2, 0.3, 0.2])
    assert weights["raw weight per criterion, Completion"].tolist() == [3, 2, 1, 1]
    assert weights["raw weight per criterion, Operations"].tolist() == [1, 1, 2, 3]
    # Section 3, Figure 2: the illustrative assessment
    illustration = paper.item_41_illustration()
    assert illustration.loc[("case", "A1"), ["score, Processing effort", "score, Financial control"]].tolist() == pytest.approx([0.2, 0.8])
    slices = illustration.loc["slice"]
    assert slices.loc["Plant A · Type X, Processing effort", ["mean score", "reference mean", "Priority Index"]].tolist() == pytest.approx([0.4, 0.6, 0.4])
    assert slices.loc["Plant B · Type X, Financial control", ["mean score", "reference mean", "Priority Index"]].tolist() == pytest.approx([0.2, 0.525, 0.65])
    assert slices.loc["Plant B · Type X, Processing effort", "Priority Index"] == 0
    # Section 5.6: the two constructed checks, made on the bundled examples
    checks = paper.item_42_constructed_checks()
    assert checks["deviation values preserved"] and checks["case scores preserved"]
    assert checks["deviation values after shuffling the event rows: largest difference"] == 0.0


def test_without_a_data_folder_the_other_items_are_reported_as_not_computed(monkeypatch, tmp_path):
    monkeypatch.delenv(data.DATA_ENVIRONMENT, raising=False)
    comparison = paper.compare()
    assert list(comparison.columns) == ["item", "place", "quantity", "printed", "computed", "agrees", "status", "note"]
    assert len(comparison) == 259
    with_data = comparison[~comparison["item"].isin([1, 2, 40, 41, 42])]
    assert (with_data["status"] == "not computed").all()
    assert with_data["agrees"].isna().all()
    assert with_data["note"].str.contains("data folder").all()
    summary = paper.summary(comparison)
    assert len(summary) == 38
    assert list(summary.columns) == ["place", "title", "kind", "values", "agree", "differ", "not_computed", "agrees"]
    assert summary["agrees"].sum() == 5
    assert summary.loc[14, "not_computed"] == 3
    with pytest.raises(DataNotAvailable):
        paper.item_03_log_size()
    empty = paper.compare(tmp_path, items=[3, 26, 31, 33])
    assert (empty["status"] == "not computed").all()
    assert empty["note"].str.contains("not in the data folder").all()


def test_agreement_is_judged_at_the_printed_precision():
    agrees = paper._agrees
    assert agrees("number", 1776.19, 1776.191039808452, 2)
    assert agrees("number", 1776.19, 1776.1949999, 2)
    assert not agrees("number", 1776.19, 1776.1951, 2)
    assert agrees("number", 0.25, 0.25, 3) and agrees("number", 0.7, 0.70004, 4)
    assert not agrees("number", 0.7, 0.70006, 4)
    assert agrees("count", 30, 30.0, None) and not agrees("count", 30, 31, None)
    assert agrees("flag", False, False, None) and not agrees("flag", True, False, None)
    assert agrees("text", "PROD542", "PROD542", None) and not agrees("text", "PROD542", "PROD424", None)
    # a machine-dependent residual: the order of magnitude is compared, the digits are not
    assert agrees("order", 1.73e-11, 1.7280399333685637e-11, None) and agrees("order", 1.73e-11, 2.0463630789890885e-11, None)
    assert agrees("order", 1.73e-11, 9.1e-12, None)
    assert not agrees("order", 1.73e-11, 1.2e-13, None) and not agrees("order", 1.73e-11, 3e-9, None)


def test_input_identity_is_the_catalogued_one_whatever_the_letter_case_of_the_file():
    """A log is found by name without regard to letter case; the record names it as the catalogue does."""
    catalogued = data.entry("bpic2013_incidents")["file"]
    found = {"file": catalogued["name"].lower(), "bytes": catalogued["bytes"], "sha256": catalogued["sha256"], "events": 65533, "cases": 7554}
    assert found["file"] != catalogued["name"]
    identity = paper._source_identity("bpic2013_incidents", found)
    assert (identity["file"], identity["bytes"], identity["sha256"]) == (catalogued["name"], catalogued["bytes"], catalogued["sha256"])
    assert identity["file_as_found"] == found["file"] and (identity["events"], identity["cases"]) == (65533, 7554)
    assert list(identity) == ["file", "bytes", "sha256", "events", "cases", "file_as_found"]
    with pytest.raises(data.DataMismatch):
        paper._source_identity("bpic2013_incidents", {**found, "sha256": "0" * 64})


def test_configuration_checksum_is_of_the_canonical_form():
    import hashlib

    assert paper.configuration_sha256({"b": 1, "a": [1, 2]}) == hashlib.sha256(b'{"a":[1,2],"b":1}').hexdigest()
    assert paper.configuration_sha256({"a": [1, 2], "b": 1}) == paper.configuration_sha256({"b": 1, "a": [1, 2]})
    assert paper.RECORD_PARTS == (
        "source_export", "adapter_configuration", "norm", "tested_settings", "evidence_summaries", "ordered_results", "numerical_checks",
    )  # fmt: skip


def test_reference_tables_are_shipped_with_the_package():
    folder = resources.files("wise.evaluation").joinpath("expected")
    names = {entry.name for entry in folder.iterdir()}
    assert names == {"paper_values.json", "view_summary.csv", "group_rankings.csv", "layer_contributions.csv"}
    document = json.loads(folder.joinpath("paper_values.json").read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    with folder.joinpath("group_rankings.csv").open(encoding="utf-8") as stream:
        rankings = pd.read_csv(stream)
    assert set(rankings["application"]) == {"bpic2019", "bpic2013_incidents", "bpic2017"}
    assert len(rankings[rankings["application"] == "bpic2019"]) == 90  # 30 groups under three views
