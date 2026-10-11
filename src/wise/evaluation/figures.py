"""The three result figures of the paper (Figures 4, 5 and 6), drawn with Matplotlib.

Each function takes computed values and returns a Matplotlib figure in the
design of the printed figure: 124 mm wide, serif type of 9 pt, the same axes,
ticks, labels, legend wording and number formats. A figure is returned, not
shown, and is independent of the interactive backend: display it in a
notebook (``display(fig)`` or as the last expression of a cell) or write it
with :func:`save`. The functions of :mod:`wise.evaluation.paper` supply the
values. Matplotlib is an optional dependency
(``pip install "wise-pm-library[figures]"``).

Nothing is estimated or smoothed: the cumulative curves are drawn from every
observed lag.
"""

from __future__ import annotations

import functools
import io
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["lag_distribution", "layer_contributions", "save", "shortlists"]

WIDTH_MM = 124.0
BLUE, GREY, GRID = "#365D7D", "#555D63", "#DFE3E6"
LAYER_COLOURS = ("#365D7D", "#9B6D35", "#5A756C", "#837486")
FONTS = ["Times New Roman", "STIXGeneral", "DejaVu Serif"]
"""Type of the printed figures, with fallbacks that Matplotlib ships. The names are concrete, so that a figure
keeps its type when it is drawn or saved later, outside the style context it was built in."""
_STYLE = {
    "font.family": FONTS,
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 9.5,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "axes.linewidth": 0.55,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "text.color": "#20262B",
    "axes.labelcolor": "#20262B",
    "xtick.color": "#20262B",
    "ytick.color": "#20262B",
    "savefig.facecolor": "white",
    "mathtext.fontset": "stix",
    "path.simplify": False,
}


def _matplotlib() -> Any:
    try:
        import matplotlib
        import matplotlib.figure
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('the figures need Matplotlib: pip install "wise-pm-library[figures]"') from exc
    return matplotlib


@functools.cache
def _figure_class() -> Any:
    """A Matplotlib figure that a notebook displays as an image, whatever backend is active."""
    matplotlib = _matplotlib()

    class PaperFigure(matplotlib.figure.Figure):  # type: ignore[misc, name-defined]
        def _repr_png_(self) -> bytes:
            buffer = io.BytesIO()
            with matplotlib.rc_context(_STYLE):
                self.savefig(buffer, format="png", dpi=200)
            return buffer.getvalue()

    return PaperFigure


def _figure(height_mm: float) -> Any:
    return _figure_class()(figsize=(WIDTH_MM / 25.4, height_mm / 25.4), facecolor="white")


def _grid(ax: Any) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, lw=0.45)
    ax.tick_params(length=3, width=0.55)


def lag_distribution(distributions: Mapping[str, pd.Series], *, threshold: float = 30, saturation: float = 90) -> Any:
    """Figure 5: cumulative share of C04-evaluable PO items against the first-invoice-to-first-clearing lag.

    ``distributions`` maps a label (``"Packaging"``, ``"Remaining groups"``)
    to the observed lags in days. The legend gives ``n`` and the median of
    each; dashed vertical lines mark the threshold and the lag at which the
    deviation value reaches one.
    """
    matplotlib = _matplotlib()
    from matplotlib.ticker import PercentFormatter

    with matplotlib.rc_context(_STYLE):
        fig = _figure(90)
        ax = fig.add_axes([0.14, 0.27, 0.83, 0.66])
        styles = [(BLUE, "solid"), (GREY, (0, (4, 2)))]
        for (label, lags), (colour, line) in zip(distributions.items(), styles, strict=False):
            values = np.sort(np.asarray(lags, dtype=float))
            x, counts = np.unique(values, return_counts=True)
            y = np.cumsum(counts) / len(values)
            ax.step(
                np.r_[0, x, 360],
                np.r_[0, y, 1],
                where="post",
                color=colour,
                lw=1.25,
                ls=line,
                label=f"{label}: n = {len(values):,}; median = {np.median(values):.2f} days",
            )
        for marker in (threshold, saturation):
            ax.axvline(marker, color="#858B90", lw=0.65, ls=(0, (2.5, 2.5)), zorder=0)
        ax.set(xlim=(0, 360), ylim=(0, 1.02), xticks=[0, 30, 90, 180, 270, 360], yticks=[0, 0.25, 0.5, 0.75, 1])
        ax.set_xlabel("First invoice receipt to first clearing (days)", labelpad=5)
        ax.set_ylabel("Cumulative share of C04-evaluable PO items", labelpad=6)
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        _grid(ax)
        ax.legend(loc="lower right", frameon=False, bbox_to_anchor=(1.015, 0.03), fontsize=9, handlelength=2.2, labelspacing=0.6)
        fig.text(
            0.14,
            0.065,
            f"C04 markers: {threshold:g} days (threshold); {saturation:g} days (deviation value = 1).",
            fontsize=9,
        )
    return fig


def layer_contributions(panels: Sequence[Mapping[str, Any]], *, note: str = "") -> Any:
    """Figure 4: signed layer contributions to the aggregate penalty gap of two groups on a common scale.

    Each panel is a mapping with ``group``, ``scored_cases``,
    ``priority_index`` and ``components`` (layer → signed contribution, in
    the order to draw).
    """
    matplotlib = _matplotlib()
    from matplotlib.ticker import FuncFormatter

    with matplotlib.rc_context(_STYLE):
        fig = _figure(130)
        rectangles = [[0.225, 0.625, 0.74, 0.245], [0.225, 0.22, 0.74, 0.24]]
        for i, (panel, rect) in enumerate(zip(panels, rectangles, strict=False)):
            ax = fig.add_axes(rect)
            layers = list(panel["components"])
            values = [float(panel["components"][layer]) for layer in layers]
            y = np.arange(len(layers))
            ax.barh(y, values, color=LAYER_COLOURS[: len(layers)], height=0.59, zorder=3)
            ax.set_yticks(y, layers)
            ax.invert_yaxis()
            ax.set_ylim(len(layers) - 0.4, -0.6)
            ax.set_xlim(-900, 2900)
            ax.set_xticks([-500, 0, 1000, 2000])
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))
            ax.axvline(0, color="#747B80", lw=0.6, zorder=1)
            _grid(ax)
            ax.spines["left"].set_visible(False)
            ax.tick_params(axis="y", length=0, pad=7)
            for y0, value in zip(y, values, strict=True):
                ax.text(
                    value + (32 if value >= 0 else -32),
                    y0,
                    f"{value:+,.2f}",
                    ha="left" if value >= 0 else "right",
                    va="center",
                    fontsize=9,
                )
            top = rect[1] + rect[3]
            fig.text(0.225, top + 0.055, f"{'AB'[i]}  {panel['group']}", fontweight="bold", fontsize=9.5)
            fig.text(
                0.225,
                top + 0.017,
                f"{panel['scored_cases']:,} scored PO items; Priority Index = {panel['priority_index']:,.2f}",
                fontsize=9,
            )
        fig.text(0.225, 0.125, "Layer contribution to the aggregate penalty gap", fontsize=9)
        fig.text(0.225, 0.087, "Unit: case penalty × scored case count", fontsize=9)
        if note:
            fig.text(0.225, 0.043, note, fontsize=9)
    return fig


def shortlists(view_pairs: Sequence[Mapping[str, Any]], policies: Sequence[int]) -> Any:
    """Figure 6: shortlist membership under declared assessment choices.

    Panel A: per pair of views (``left``, ``right``, ``shared``) the
    purchasing documents shared between the top-20 positive-priority lists.
    Panel B: the company-by-spend-area groups that the top ten by mean case
    penalty, by total case penalty and by PI with the small-slice adjustment
    (γ = 20) share with the primary PI top ten, in that order.
    """
    matplotlib = _matplotlib()
    with matplotlib.rc_context(_STYLE):
        fig = _figure(142)
        ax = fig.add_axes([0.36, 0.635, 0.60, 0.245])
        shared = [int(pair["shared"]) for pair in view_pairs]
        y = np.arange(len(shared))
        ax.barh(y, shared, color=BLUE, height=0.53, zorder=3)
        ax.set_yticks(y, [f"{pair['left']} /\n{pair['right']}" for pair in view_pairs])
        ax.invert_yaxis()
        ax.set_ylim(len(shared) - 0.4, -0.6)
        ax.set_xlim(0, 23)
        ax.set_xticks([0, 5, 10, 15, 20])
        _grid(ax)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_bounds(0, 20)
        ax.tick_params(axis="y", length=0, pad=8)
        for i, n in enumerate(shared):
            ax.text(n + 0.35, i, f"{n}/20", va="center", fontsize=9)
        ax.set_xlabel("Number of shared purchasing documents", labelpad=5)
        fig.text(0.04, 0.967, "A  Purchasing documents: different views", fontweight="bold", fontsize=9.5)
        fig.text(0.04, 0.934, "Membership shared between top-20 positive-priority lists", fontsize=9)

        bx = fig.add_axes([0.36, 0.19, 0.60, 0.245])
        counts = [int(n) for n in policies]
        yb = np.arange(len(counts))
        bx.barh(yb, counts, color=BLUE, height=0.53, zorder=3)
        bx.set_yticks(yb, ["Mean case\npenalty", "Total case\npenalty", "PI with small-slice\nadjustment ($\\gamma=20$)"])
        for tick in bx.get_yticklabels():
            tick.set_math_fontfamily("stix")
        bx.invert_yaxis()
        bx.set_ylim(len(counts) - 0.4, -0.6)
        bx.set_xlim(0, 11.5)
        bx.set_xticks([0, 2, 4, 6, 8, 10])
        _grid(bx)
        bx.spines["left"].set_visible(False)
        bx.spines["bottom"].set_bounds(0, 10)
        bx.tick_params(axis="y", length=0, pad=8)
        for i, n in enumerate(counts):
            bx.text(n + 0.18, i, f"{n}/10", va="center", fontsize=9)
        bx.set_xlabel("Number of shared company-by-spend-area groups", labelpad=5)
        fig.text(0.04, 0.514, "B  Company-by-spend-area groups: ranking policies", fontweight="bold", fontsize=9.5)
        fig.text(0.04, 0.481, "Membership shared with the primary PI top ten", fontsize=9)
        fig.text(0.04, 0.068, "Panel B holds the Balanced case penalties, scored population", fontsize=9)
        fig.text(0.04, 0.037, "and 30 group definitions fixed.", fontsize=9)
    return fig


def save(fig: Any, stem: str, directory: Any = ".", formats: Sequence[str] = ("pdf", "png")) -> list[str]:
    """Save a figure as ``<stem>.<format>`` in ``directory`` and return the file names written."""
    from pathlib import Path

    matplotlib = _matplotlib()
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    names = []
    with matplotlib.rc_context(_STYLE):
        for extension in formats:
            fig.savefig(target / f"{stem}.{extension}", dpi=400 if extension == "png" else None)
            names.append(f"{stem}.{extension}")
    return names
