"""Priority Index, shrinkage, exposure scaling, the backlog record and the signed layer contributions."""

import copy
import pickle

import numpy as np
import pandas as pd
import pytest

import wise
from wise.errors import NormError, NotScoredError


def _frame(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s, (n, mean) in enumerate([(240, 0.80), (30, 0.70), (5, 0.60)]):
        for _ in range(n):
            rows.append({"slice": f"s{s}", "score": float(np.clip(rng.normal(mean, 0.02), 0, 1)), "exposure": 10.0 * (s + 1)})
    return pd.DataFrame(rows)


@pytest.mark.paper
def test_pi_illustration_from_the_paper():
    # μ̄ = 0.94, μ_s = 0.80, n_s = 240 → gap 0.14, PI = 33.6
    df = pd.DataFrame({"slice": ["big"] * 240 + ["rest"] * 760, "score": [0.80] * 240 + [0.94 + 0.14 * 240 / 760] * 760})
    backlog = wise.prioritize(df, "slice")
    table = backlog.table
    assert table.index.name == "slice"
    assert table.loc["big", "global_mean"] == pytest.approx(0.94)
    assert table.loc["big", "gap"] == pytest.approx(0.14)
    assert table.loc["big", "PI"] == pytest.approx(33.6)
    assert table.loc["rest", "PI"] == 0.0  # at or above the reference: zero priority
    assert list(table.columns) == ["n_cases", "mean_score", "volume", "gap", "PI", "stable_mean", "stable_gap", "stable_PI", "global_mean"]
    assert "slice" in wise.prioritize(df, ["slice"], as_index=False).table.columns


@pytest.mark.paper
@pytest.mark.paper
def test_illustrative_invoice_assessment_of_figure_2():
    """Section 3: four invoice cases, three constraints in two layers, two views; each view puts another slice first."""
    log, norm = wise.illustrative_invoice_log(), wise.illustrative_invoice_norm()
    assert [layer.name for layer in norm.layers] == ["Invoice handling", "Required records"]
    assert norm.layer_of.to_dict() == {"release_limit": "handling", "no_forwarding": "handling", "release_record": "records"}
    result = wise.score(log, norm)
    assert result.mode == "flat" and result.evaluated.all().all()
    assert result.violations.loc[["A1", "A2", "B1", "B2"]].to_numpy().tolist() == [[1, 1, 0], [1, 0, 0], [0, 0, 1], [0, 0, 1]]
    assert result.scores["Processing effort"].tolist() == pytest.approx([0.20, 0.60, 0.80, 0.80])
    assert result.scores["Financial control"].tolist() == pytest.approx([0.80, 0.90, 0.20, 0.20])
    effort = wise.prioritize(result, by=["plant", "document_type"], view="Processing effort").table
    control = wise.prioritize(result, by=["plant", "document_type"], view="Financial control").table
    assert effort.index[0] == ("Plant A", "Type X") and control.index[0] == ("Plant B", "Type X")
    assert effort["global_mean"].iloc[0] == pytest.approx(0.600) and control["global_mean"].iloc[0] == pytest.approx(0.525)
    assert effort["PI"].tolist() == pytest.approx([0.40, 0.0]) and control["PI"].tolist() == pytest.approx([0.65, 0.0])
    assert effort["n_cases"].tolist() == [2, 2]


def test_shrinkage_closed_form():
    df = _frame()
    raw = wise.prioritize(df, ["slice"]).table
    stable = wise.prioritize(df, ["slice"], gamma=30).table
    for s in raw.index:
        n = raw.loc[s, "n_cases"]
        assert stable.loc[s, "stable_gap"] == pytest.approx(n / (n + 30) * raw.loc[s, "gap"])
        assert stable.loc[s, "stable_PI"] == pytest.approx(n * n / (n + 30) * raw.loc[s, "gap"])
        assert stable.loc[s, "stable_mean"] == pytest.approx(
            n / (n + 30) * raw.loc[s, "mean_score"] + 30 / (n + 30) * raw.loc[s, "global_mean"]
        )
    pd.testing.assert_series_equal(raw["stable_PI"], raw["PI"], check_names=False)  # γ = 0 gives the basic index
    pd.testing.assert_series_equal(stable["PI"], raw["PI"])  # the observed gap stays visible
    for bad in (-1, np.nan, None, "five", np.inf):
        with pytest.raises(NormError, match="gamma"):
            wise.prioritize(df, ["slice"], gamma=bad)


@pytest.mark.paper
def test_exposure_scaled_pi_keeps_unweighted_means():
    df = _frame()
    by_cases = wise.prioritize(df, ["slice"]).table
    by_exposure = wise.prioritize(df, ["slice"], volume="exposure").table
    assert by_exposure.loc["s1", "volume"] == pytest.approx(30 * 20.0)
    assert by_exposure.loc["s1", "PI"] == pytest.approx(600 * by_exposure.loc["s1", "gap"])
    pd.testing.assert_series_equal(by_exposure["mean_score"], by_cases["mean_score"].reindex(by_exposure.index))
    assert by_exposure["global_mean"].iloc[0] == by_cases["global_mean"].iloc[0]
    with pytest.raises(NormError, match="volume column"):
        wise.prioritize(df, ["slice"], volume="nope")
    with pytest.raises(NormError, match="negative"):
        wise.prioritize(df.assign(exposure=-1.0), ["slice"], volume="exposure")


@pytest.mark.paper
def test_tie_order_is_index_then_scored_cases_then_key():
    df = pd.DataFrame({"slice": list("bbbaacd"), "score": [0.5] * 7})  # every slice at the reference → all PI 0
    first = wise.prioritize(df, ["slice"]).table
    second = wise.prioritize(df.iloc[::-1], ["slice"]).table
    assert list(first.index) == ["b", "a", "c", "d"] == list(second.index)
    assert wise.TIE_POLICY.startswith("Priority Index descending")


def test_only_scored_cases_enter_and_unscored_slices_are_not_ranked():
    df = pd.DataFrame({"slice": ["a", "a", "b", "c"], "score": [0.2, np.nan, 0.8, np.nan]})
    table = wise.prioritize(df, "slice").table
    assert list(table.index) == ["a", "b"]
    assert table.loc["a", "n_cases"] == 1
    assert table.loc["a", "global_mean"] == pytest.approx(0.5)
    with pytest.raises(NotScoredError):
        wise.prioritize(df.assign(score=np.nan), "slice")
    with pytest.raises(NormError, match="score column"):
        wise.prioritize(df.rename(columns={"score": "s"}), "slice")
    with pytest.raises(NormError, match="slice columns"):
        wise.prioritize(df, "nope")


def test_a_missing_slice_key_is_an_explicit_slice():
    df = pd.DataFrame({"slice": ["a", None, None, "b"], "score": [0.9, 0.1, 0.3, 0.9]})
    table = wise.prioritize(df, "slice").table
    assert wise.MISSING_KEY == "(missing)"
    assert table.index[0] == wise.MISSING_KEY
    assert table.loc[wise.MISSING_KEY, "n_cases"] == 2
    tied = pd.DataFrame({"slice": [None, "z", "a"], "score": [0.5, 0.5, 0.5]})
    assert list(wise.prioritize(tied, "slice").table.index) == ["a", "z", wise.MISSING_KEY]  # the label ranks last on a tie
    with pytest.raises(NormError, match="labels them"):
        wise.prioritize(pd.DataFrame({"slice": [None, "(missing)"], "score": [0.5, 0.5]}), "slice")
    categorical = df.assign(slice=df["slice"].astype("category"))
    assert wise.MISSING_KEY in wise.prioritize(categorical, "slice").table.index


def test_backlog_record_carries_its_specification(p2p_result):
    backlog = wise.prioritize(p2p_result, ["company", "vendor"], view="Logistics", gamma=2)
    assert isinstance(backlog, wise.Backlog)
    spec = backlog.spec
    assert spec == wise.BacklogSpec(
        by=("company", "vendor"),
        view="Logistics",
        gamma=2.0,
        volume="cases",
        global_mean=float(p2p_result.scores["Logistics"].mean()),
        norm_fingerprint=wise.running_p2p_norm().fingerprint(),
    )
    assert spec.to_dict()["by"] == ["company", "vendor"]
    assert spec.to_dict()["tie_policy"] == wise.TIE_POLICY
    assert backlog.table.attrs == {}
    for clone in (copy.deepcopy(backlog), pickle.loads(pickle.dumps(backlog))):
        assert clone.spec == spec
        pd.testing.assert_frame_equal(clone.table, backlog.table)
    assert repr(backlog).startswith("Backlog(")
    frame_backlog = wise.prioritize(pd.DataFrame({"slice": ["a", "b"], "score": [0.2, 0.8]}), "slice")
    assert (frame_backlog.spec.view, frame_backlog.spec.norm_fingerprint) == (None, None)
    with pytest.raises(NormError, match="specify view"):
        wise.prioritize(p2p_result, "company")


def test_running_example_backlog_and_drivers(p2p_result):
    backlog = wise.prioritize(p2p_result, ["company"], view="Finance")
    table = backlog.table
    assert table.loc["B", "PI"] > 0
    assert table.loc["A", "PI"] == 0.0
    drivers = wise.layer_drivers(p2p_result, backlog)
    assert drivers.loc["B", "completeness__delta"] > 0
    assert drivers.loc["B", "dominant_layer"] == "match"
    assert drivers.loc["A", "dominant_layer"] == "timing"
    assert list(drivers.index) == ["A", "B"]
    only = wise.layer_drivers(p2p_result, "company", view="Finance", layers=["match"])
    assert "match" in only.columns and "timing" not in only.columns
    other_norm = wise.score(wise.running_p2p_log(), wise.running_p2p_norm().replace(name="other"))
    with pytest.raises(NormError, match="another norm"):
        wise.layer_drivers(other_norm, backlog)
    with pytest.raises(NormError, match="differs from the backlog's view"):
        wise.layer_drivers(p2p_result, backlog, view="Logistics")


@pytest.mark.paper
def test_signed_layer_contributions_sum_to_the_priority_index(p2p_result):
    for view in ("Finance", "Logistics"):
        for by in ("company", "vendor", "case"):
            backlog = wise.prioritize(p2p_result, by, view=view)
            signed = wise.layer_contributions(p2p_result, backlog)
            assert list(signed.columns) == wise.running_p2p_norm().layer_ids
            total = signed.sum(axis=1).reindex(backlog.table.index)
            np.testing.assert_allclose(total.clip(lower=0).to_numpy(), backlog.table["PI"].to_numpy(), atol=1e-12)
            # the signed excesses of a partition of the scored population sum to zero
            assert signed.to_numpy().sum() == pytest.approx(0.0, abs=1e-12)
    # clipping each layer separately removes offsets and overstates the index
    backlog = wise.prioritize(p2p_result, "company", view="Finance")
    signed = wise.layer_contributions(p2p_result, backlog)
    assert signed.loc["B"].clip(lower=0).sum() > backlog.table.loc["B", "PI"]
    assert signed.loc["B", "timing"] < 0  # an offset


@pytest.mark.paper
def test_signed_layer_contributions_with_shrinkage_and_exposure():
    rng = np.random.default_rng(3)
    n = 400
    frame = pd.DataFrame(
        {
            "case": [f"c{i:03d}" for i in range(n)],
            "activity": "X",
            "time": pd.Timestamp("2024-01-01"),
            "group": rng.choice(list("ABCDE"), size=n, p=[0.5, 0.3, 0.1, 0.07, 0.03]),
            "amount": rng.uniform(1, 100, size=n),
            "a": rng.uniform(0, 1, size=n),
            "b": rng.uniform(0, 1, size=n),
            "c": rng.uniform(0, 1, size=n),
        }
    )
    log = wise.EventLog(
        frame, case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["group", "a", "b", "c"],
        exposure_col="amount", exposure_agg="sum",
    )  # fmt: skip
    norm = wise.Norm(
        [wise.NormConstraint(k, layer, wise.Metric(k)) for k, layer in (("a", "L1"), ("b", "L1"), ("c", "L2"))],
        [wise.Layer("L1"), wise.Layer("L2")],
        [wise.View("v", constraint_weights={"a": 1, "b": 2, "c": 3})],
    )
    result = wise.score(log, norm)
    for gamma in (0.0, 20.0):
        for volume in ("cases", "exposure"):
            backlog = wise.prioritize(result, "group", view="v", gamma=gamma, volume=volume)
            signed = wise.layer_contributions(result, backlog)
            direct = wise.layer_contributions(result, "group", view="v", gamma=gamma, volume=volume)
            pd.testing.assert_frame_equal(signed, direct)
            total = signed.sum(axis=1).reindex(backlog.table.index).clip(lower=0)
            np.testing.assert_allclose(total.to_numpy(), backlog.table["stable_PI"].to_numpy(), atol=1e-9)
    # with γ = 0 and case counts: H = n · (slice mean layer contribution − population mean)
    drivers = wise.layer_drivers(result, "group", view="v")
    h = wise.layer_contributions(result, "group", view="v")
    np.testing.assert_allclose(h["L1"].to_numpy(), (drivers["L1__delta"] * drivers["n_cases"]).to_numpy(), atol=1e-12)


@pytest.mark.paper
def test_top_k_overlap_is_the_jaccard_similarity_of_positive_shortlists():
    first = wise.prioritize(pd.DataFrame({"slice": list("abcd"), "score": [0.1, 0.2, 0.9, 0.9]}), "slice")
    second = wise.prioritize(pd.DataFrame({"slice": list("abcd"), "score": [0.1, 0.9, 0.2, 0.9]}), "slice")
    assert wise.top_k_overlap(first, first, k=2) == 1.0
    assert wise.top_k_overlap(first, second, k=2) == pytest.approx(1 / 3)  # {a, b} and {a, c}
    assert wise.top_k_overlap(first, second, k=1) == 1.0
    assert wise.top_k_overlap(first.table, second.table, k=2) == pytest.approx(1 / 3)
    # slices without positive priority are not part of a shortlist
    zero = pd.DataFrame({"slice": list("xyzw"), "score": [0.9, 0.9, 0.9, 0.1]})
    assert wise.top_k_overlap(wise.prioritize(zero, "slice"), wise.prioritize(zero.iloc[::-1], "slice"), k=3) == 1.0
    other_keys = wise.prioritize(pd.DataFrame({"other": list("ab"), "score": [0.1, 0.9]}), "other")
    with pytest.raises(NormError, match="different slice keys"):
        wise.top_k_overlap(first, other_keys)
    flat = wise.prioritize(pd.DataFrame({"slice": list("ab"), "score": [0.5, 0.5]}), "slice")
    assert np.isnan(wise.top_k_overlap(flat, flat))


def test_slices_by_case_id_and_by_several_keys(p2p_result):
    by_case = wise.prioritize(p2p_result, "case", view="Finance").table
    assert by_case.loc["E", "PI"] > by_case.loc["A", "PI"] > 0
    assert by_case.loc["B", "PI"] == 0.0
    both = wise.prioritize(p2p_result, ["company", "vendor"], view="Finance").table
    assert both.index.names == ["company", "vendor"]
    assert int(both["n_cases"].sum()) == 5
    frame = p2p_result.frame("Finance").assign(case=lambda d: d.index)
    assert wise.prioritize(frame, "case").table.loc["E", "PI"] > 0
