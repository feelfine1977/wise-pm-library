"""The three figures: drawn from given values, in the printed design."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("matplotlib")

from wise.evaluation import figures  # noqa: E402


def _texts(fig):
    import matplotlib.text

    return [t.get_text() for t in fig.findobj(matplotlib.text.Text) if t.get_text()]


def test_lag_distribution_figure():
    rng = np.random.default_rng(0)
    lags = {"Packaging": pd.Series(rng.gamma(4, 18, size=500)), "Remaining groups": pd.Series(rng.gamma(2, 15, size=800))}
    fig = figures.lag_distribution(lags, threshold=30, saturation=90)
    texts = _texts(fig)
    assert f"Packaging: n = 500; median = {np.median(lags['Packaging']):.2f} days" in texts
    assert f"Remaining groups: n = 800; median = {np.median(lags['Remaining groups']):.2f} days" in texts
    assert "First invoice receipt to first clearing (days)" in texts
    assert "Cumulative share of C04-evaluable PO items" in texts
    assert "C04 markers: 30 days (threshold); 90 days (deviation value = 1)." in texts
    ax = fig.axes[0]
    assert ax.get_xlim() == (0.0, 360.0)
    assert [int(t) for t in ax.get_xticks()] == [0, 30, 90, 180, 270, 360]
    assert fig.get_size_inches()[0] == pytest.approx(124 / 25.4)
    # the curve is the empirical distribution of every observed lag
    x, y = ax.lines[0].get_data()
    assert y[-1] == 1.0 and np.all(np.diff(y) >= 0)
    assert len(x) == len(np.unique(lags["Packaging"])) + 2


def test_layer_contribution_figure():
    panels = [
        {"group": "Packaging", "scored_cases": 109199, "priority_index": 1776.191,
         "components": {"Completion": -332.421, "Timing": 2365.436, "Rework": -267.950, "Effort proxy": 11.126}},
        {"group": "Logistics", "scored_cases": 5242, "priority_index": 664.607,
         "components": {"Completion": 811.133, "Timing": -154.248, "Rework": 10.535, "Effort proxy": -2.813}},
    ]  # fmt: skip
    fig = figures.layer_contributions(panels, note="Balanced view; both groups belong to companyID_0000.")
    texts = _texts(fig)
    for expected in (
        "A  Packaging", "B  Logistics", "109,199 scored PO items; Priority Index = 1,776.19", "5,242 scored PO items; Priority Index = 664.61",
        "-332.42", "+2,365.44", "-267.95", "+11.13", "+811.13", "-154.25", "+10.54", "-2.81",
        "Layer contribution to the aggregate penalty gap", "Unit: case penalty × scored case count",
        "Balanced view; both groups belong to companyID_0000.",
    ):  # fmt: skip
        assert expected in texts
    assert len(fig.axes) == 2
    assert fig.axes[0].get_xlim() == fig.axes[1].get_xlim() == (-900.0, 2900.0)  # a common scale


def test_shortlist_figure():
    pairs = [
        {"left": "Balanced", "right": "Completion", "shared": 18},
        {"left": "Balanced", "right": "Operations", "shared": 10},
        {"left": "Completion", "right": "Operations", "shared": 8},
    ]
    fig = figures.shortlists(pairs, [6, 4, 10])
    texts = _texts(fig)
    for expected in (
        "18/20", "10/20", "8/20", "6/10", "4/10", "10/10",
        "A  Purchasing documents: different views", "B  Company-by-spend-area groups: ranking policies",
        "Number of shared purchasing documents", "Number of shared company-by-spend-area groups",
        "Membership shared between top-20 positive-priority lists", "Membership shared with the primary PI top ten",
    ):  # fmt: skip
        assert expected in texts


def test_a_figure_displays_as_an_image_and_opens_no_window():
    import matplotlib.figure

    fig = figures.shortlists([{"left": "A", "right": "B", "shared": 3}], [1, 2, 3])
    assert isinstance(fig, matplotlib.figure.Figure)
    assert fig._repr_png_().startswith(b"\x89PNG")
    assert fig.canvas.manager is None  # not registered with an interactive backend


def test_save_writes_the_named_files(tmp_path):
    fig = figures.shortlists([{"left": "A", "right": "B", "shared": 3}], [1, 2, 3])
    assert figures.save(fig, "fig5", tmp_path / "out") == ["fig5.pdf", "fig5.png"]
    assert (tmp_path / "out" / "fig5.pdf").stat().st_size > 0
