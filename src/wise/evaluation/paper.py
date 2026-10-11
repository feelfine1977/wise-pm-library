"""Every result item of the paper as one function, and the comparison with the printed values.

``expected/paper_values.json`` lists the result items of the paper with their
printed values and the place where each appears; three of them are figures.
For every item this module has one function, ``item_NN_<name>``, that
computes it with the library (from the public logs where the item needs one)
and returns the value or table (for a figure item, a Matplotlib figure in the
design of the printed one). :func:`compare` sets every computed value beside
the printed one; :func:`summary` counts agreement per item. The item numbers
are stable: a number is not reused when the paper drops a result, so the
numbers have gaps.

The data folder that holds the public logs is the argument ``data`` of every
function, or the environment variable ``WISE_PAPER_DATA``. A log is read and
assessed once per session and folder; all functions share the result.

No function prints or returns a path of the machine it runs on.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import wise

from . import data as _data
from . import native, replay
from .adapters import EVALUATED, OUT_OF_SCOPE, Assessment, configuration

__all__ = [
    "ITEMS",
    "RECORD_PARTS",
    "calculation_record",
    "compare",
    "expected_values",
    "further_checks",
    "figure_4",
    "figure_5",
    "figure_6",
    "incident_criteria",
    "input_identity",
    "lending_criteria",
    "summary",
    "table_3",
    "table_4",
    "table_b1",
]

BPIC19 = "bpic2019"
BPIC13 = "bpic2013_incidents"
BPIC17 = "bpic2017"
GROUP = native.GROUP
PACKAGING = "companyID_0000 | Packaging"
LOGISTICS = "companyID_0000 | Logistics"
PROD542, PROD424 = "PROD542", "PROD424"
POSITIVE = 1e-12
"""A Priority Index counts as positive above this value."""

Data = str | Path | None


# ----------------------------------------------------------------------------- applications
@dataclass(eq=False)
class Application:
    """One application of the paper, assessed by its adapter and scored by the library."""

    assessment: Assessment
    result: wise.ScoreResult
    _backlogs: dict[tuple[str, str, float], wise.Backlog] = field(default_factory=dict, repr=False)

    @property
    def views(self) -> list[str]:
        return list(self.result.views)

    def backlog(self, view: str, by: str = GROUP, gamma: float = 0.0) -> wise.Backlog:
        """The prioritised investigation list of a view (case-count scale; reference = mean of all scored cases)."""
        key = (view, by, float(gamma))
        if key not in self._backlogs:
            self._backlogs[key] = wise.prioritize(self.result, by=by, view=view, gamma=gamma)
        return self._backlogs[key]

    def penalty(self, view: str) -> pd.Series:
        """Case penalty ``q = 1 − S`` under a view."""
        return (1.0 - self.result.scores[view]).rename("penalty")


_EXTRA_ATTRIBUTES = {BPIC19: ["document", "vendor", "flow"]}


@lru_cache(maxsize=8)
def _application(folder: str, name: str) -> Application:
    assessment = replay.assess(name, folder)
    extra = _EXTRA_ATTRIBUTES.get(name)
    attributes = assessment.features[extra] if extra else None
    return Application(assessment, native.replay(assessment, attributes=attributes))


def application(name: str, data: Data = None) -> Application:
    """The assessed and scored application ``"bpic2019"``, ``"bpic2013_incidents"`` or ``"bpic2017"``."""
    _data.locate(name, data)  # verifies the input and raises DataNotAvailable with a clear message
    return _application(str(_data.data_folder(data)), name)


def _label(group: Any) -> str:
    """A group key in the notation of the paper (``company / spend area``)."""
    return str(group).replace(" | ", " / ")


def _top(table: pd.DataFrame, column: str, k: int) -> list[str]:
    """The first ``k`` slice keys by ``column`` (descending), then scored cases (descending), then key (ascending)."""
    t = table.reset_index()
    key = t.columns[0]
    t["_key"] = t[key].astype(str)
    t = t.sort_values([column, "n_cases", "_key"], ascending=[False, False, True], kind="mergesort")
    return t["_key"].head(min(k, len(t))).tolist()


# ----------------------------------------------------------------------------- items 1 and 2: Section 4
def _values_01(data: Data = None) -> dict[str, Any]:
    result = wise.score(wise.running_p2p_log(), wise.running_p2p_norm())
    v = result.violations
    out: dict[str, Any] = {
        "A.violation.c2": v.loc["A", "c2"],
        "B.violation.c5": v.loc["B", "c5"],
        "C.violation.c3": v.loc["C", "c3"],
        "D.violation.c6": v.loc["D", "c6"],
        "E.violation.c1": v.loc["E", "c1"],
        "E.violation.c2": v.loc["E", "c2"],
        "E.violation.c3": v.loc["E", "c3"],
    }
    for case in "ABCDE":
        for view in ("Finance", "Logistics"):
            out[f"{case}.{view}"] = result.scores.loc[case, view]
    return {k: float(x) for k, x in out.items()}


def item_01_table_4() -> pd.DataFrame:
    """Table 4: the five illustrative cases, their non-zero violations and their scores under both views."""
    result = wise.score(wise.running_p2p_log(), wise.running_p2p_norm())
    rows = []
    for case in result.scores.index:
        violations = result.violations.loc[case].dropna()
        nonzero = {c: round(float(x), 4) for c, x in violations.items() if x > 0}
        rows.append(
            {
                "case": f"σ{case}",
                "non-zero violations": ", ".join(f"ν_{c} = {x:g}" for c, x in nonzero.items()),
                "S(Finance)": result.scores.loc[case, "Finance"],
                "S(Logistics)": result.scores.loc[case, "Logistics"],
            }
        )
    return pd.DataFrame(rows).set_index("case").round(4)


def _single_case_log(events: list[tuple[str, float]]) -> wise.EventLog:
    start = pd.Timestamp("2024-01-01")
    frame = pd.DataFrame(
        {"case": "σ", "activity": [a for a, _ in events], "time": [start + pd.Timedelta(days=d) for _, d in events]}
    )
    return wise.EventLog(frame, case_col="case", activity_col="activity", timestamp_col="time")


def _values_02(data: Data = None) -> dict[str, Any]:
    norm = wise.running_p2p_norm()
    lag, limit = norm.get_constraint("c2").constraint, norm.get_constraint("c5").constraint
    gr, inv = "Record Goods Receipt", "Record Invoice Receipt"
    out: dict[str, Any] = {f"sat.{z}": wise.sat(z, 10, 20) for z in (8, 15, 20, 30)}
    for days in (10, 20, 30):
        out[f"lag.{days}"] = float(wise.evaluate(lag, _single_case_log([(gr, 0), (inv, days)])).value.iloc[0])
    for count in (3, 4, 5):
        log = _single_case_log([(gr, float(i)) for i in range(count)])
        out[f"occurrence.{count}"] = float(wise.evaluate(limit, log).value.iloc[0])
    # a slice of 240 cases with mean score 0.80 in a population whose mean score is 0.94
    frame = pd.DataFrame({"slice": ["A"] * 240 + ["B"] * 760, "score": [0.80] * 240 + [0.94 + 0.14 * 240 / 760] * 760})
    table = wise.prioritize(frame, "slice").table
    out["pi.gap"] = float(table.loc["A", "gap"])
    out["pi.value"] = float(table.loc["A", "PI"])
    return out


def item_02_worked_arithmetic() -> pd.DataFrame:
    """The worked arithmetic of Sections 4.2 and 4.5, computed with the library's own functions."""
    values = _values_02()
    names = {
        "sat": "sat(z; 10, 20) at z =",
        "lag": "lag constraint c2 (δ = 10 d, Δ = 20 d) at a lag in days of",
        "occurrence": "occurrence limit c5 (k = 2, K = 3) at a count of",
    }
    rows = []
    for key, value in values.items():
        kind, _, argument = key.partition(".")
        what = f"{names[kind]} {argument}" if kind in names else {"gap": "gap: 0.94 − 0.80", "value": "Priority Index: 240 × gap"}[argument]
        rows.append({"quantity": what, "computed": value})
    return pd.DataFrame(rows).set_index("quantity")


# ----------------------------------------------------------------------------- items 3 to 25: BPIC'19
def _values_03(data: Data = None) -> dict[str, Any]:
    source = application(BPIC19, data).assessment.source
    return {"events": source["events"], "po_items": source["cases"], "documents": source["documents"]}


def item_03_log_size(data: Data = None) -> pd.Series:
    """Events, purchase-order items and purchasing documents of the BPIC'19 log."""
    return pd.Series(_values_03(data), name="BPIC'19")


def _values_04(data: Data = None) -> dict[str, Any]:
    counts = application(BPIC19, data).assessment.features["flow"].value_counts()
    return {"DF2": int(counts["DF2"]), "DF1": int(counts["DF1"]), "Consignment": int(counts["Consignment"]), "two_way": int(counts["2-way"])}


def item_04_flow_categories(data: Data = None) -> pd.Series:
    """Purchase-order items per flow category."""
    return pd.Series(_values_04(data), name="PO items")


def _values_05(data: Data = None) -> dict[str, Any]:
    return {"groups": int(application(BPIC19, data).assessment.groups.nunique())}


def item_05_slices(data: Data = None) -> int:
    """Number of company-by-spend-area groups (missing spend-area labels kept as explicit categories)."""
    return int(_values_05(data)["groups"])


def _values_06(data: Data = None) -> dict[str, Any]:
    scores = application(BPIC19, data).result.scores
    return {f"scored.{view}": int(scores[view].notna().sum()) for view in scores}


def item_06_scored_cases(data: Data = None) -> pd.Series:
    """Scored purchase-order items per view."""
    scores = application(BPIC19, data).result.scores
    return scores.notna().sum().rename("scored PO items")


def _values_07(data: Data = None) -> dict[str, Any]:
    app = application(BPIC19, data)
    return {f"coverage.{view}": float(app.result.coverage(view).mean()) for view in app.views}


def item_07_mean_coverage(data: Data = None) -> pd.Series:
    """Mean weighted evidence coverage over all purchase-order items, per view."""
    app = application(BPIC19, data)
    return pd.Series({view: float(app.result.coverage(view).mean()) for view in app.views}, name="mean coverage")


def _c04(app: Application) -> pd.DataFrame:
    """The C04-evaluable items with their group, flow, lag and deviation value."""
    a = app.assessment
    evaluable = a.state["C04"].eq(EVALUATED)
    out = a.features.loc[evaluable, ["group", "flow", "invoice_clear_days"]].copy()
    out["deviation"] = a.severity.loc[evaluable, "C04"]
    return out


def _values_08(data: Data = None) -> dict[str, Any]:
    lags = _c04(application(BPIC19, data))
    packaging = lags[lags.group.eq(PACKAGING)]
    return {"evaluable": len(packaging), "positive": int(packaging.deviation.gt(0).sum())}


def item_08_c04_evaluable(data: Data = None) -> pd.Series:
    """Packaging: items for which C04 can be evaluated, and those with a positive deviation value."""
    return pd.Series(_values_08(data), name="Packaging, C04")


def _lag_medians(data: Data, flow: str | None) -> pd.DataFrame:
    lags = _c04(application(BPIC19, data))
    if flow is not None:
        lags = lags[lags.flow.eq(flow)]
    packaging = lags.group.eq(PACKAGING)
    rows = {
        "Packaging": {"n": int(packaging.sum()), "median_days": float(lags.loc[packaging, "invoice_clear_days"].median())},
        "Remaining groups": {"n": int((~packaging).sum()), "median_days": float(lags.loc[~packaging, "invoice_clear_days"].median())},
    }
    return pd.DataFrame(rows).T.astype({"n": int})


def _values_09(data: Data = None) -> dict[str, Any]:
    t = _lag_medians(data, None)
    return {
        "packaging.n": int(t.loc["Packaging", "n"]),
        "packaging.median": float(t.loc["Packaging", "median_days"]),
        "remaining.n": int(t.loc["Remaining groups", "n"]),
        "remaining.median": float(t.loc["Remaining groups", "median_days"]),
    }


def item_09_lag_medians(data: Data = None) -> pd.DataFrame:
    """Median first-invoice-to-first-clearing lag over the C04-evaluable items, Packaging and remaining groups."""
    return _lag_medians(data, None)


def _values_10(data: Data = None) -> dict[str, Any]:
    t = _lag_medians(data, "DF2")
    return {"packaging.median": float(t.loc["Packaging", "median_days"]), "remaining.median": float(t.loc["Remaining groups", "median_days"])}


def item_10_lag_medians_df2(data: Data = None) -> pd.DataFrame:
    """The same medians within the DF2 flow."""
    return _lag_medians(data, "DF2")


def lag_distributions(data: Data = None) -> dict[str, pd.Series]:
    """The C04 lags in days of Packaging and of the remaining groups (the data of Figure 5)."""
    lags = _c04(application(BPIC19, data))
    packaging = lags.group.eq(PACKAGING)
    return {
        "Packaging": lags.loc[packaging, "invoice_clear_days"].reset_index(drop=True),
        "Remaining groups": lags.loc[~packaging, "invoice_clear_days"].reset_index(drop=True),
    }


def _values_11(data: Data = None) -> dict[str, Any]:
    rule = next(c for c in configuration("bpic2019")["criteria"] if c["id"] == "C04")
    return {**_values_09(data), "marker.threshold": float(rule["threshold"]), "marker.saturation": float(rule["threshold"] + rule["width"])}


def item_11_figure_5(data: Data = None) -> Any:
    """Figure 5: cumulative distributions of the C04 lag in Packaging and the remaining groups."""
    from . import figures

    rule = next(c for c in configuration("bpic2019")["criteria"] if c["id"] == "C04")
    return figures.lag_distribution(lag_distributions(data), threshold=rule["threshold"], saturation=rule["threshold"] + rule["width"])


def _worked_po_item(data: Data = None) -> dict[str, Any]:
    app = application(BPIC19, data)
    a, result = app.assessment, app.result
    lags = _c04(app)
    packaging = lags[lags.group.eq(PACKAGING)]
    median = float(packaging.invoice_clear_days.median())
    candidates = packaging.loc[packaging.deviation.gt(0), ["invoice_clear_days"]].copy()
    candidates["case_id"] = candidates.index.astype(str)
    candidates.index.name = None
    candidates["distance"] = (candidates.invoice_clear_days - median).abs()
    case = candidates.sort_values(["distance", "case_id"], kind="mergesort").iloc[0].case_id
    severity, state = a.severity.loc[case], a.state.loc[case]
    contributions = result.penalties("Balanced").loc[case]
    return {
        "item": case,
        "first_invoice_receipt": a.features.loc[case, "first_invoice"].strftime("%Y-%m-%d %H:%M"),
        "first_clearing": a.features.loc[case, "first_clear"].strftime("%Y-%m-%d %H:%M"),
        "lag_days": float(a.features.loc[case, "invoice_clear_days"]),
        "deviation": float(severity["C04"]),
        "evaluable_criteria": int(severity.notna().sum()),
        "contribution": float(contributions["C04"]),
        "other_nonzero": int(severity.drop("C04").gt(0).sum()),
        "state.C05": str(state["C05"]),
        "state.C09": str(state["C09"]),
        "state.C10": str(state["C10"]),
        "score": float(result.scores.loc[case, "Balanced"]),
        "in_scope_criteria": int(a.in_scope.loc[case].sum()),
        "coverage": float(result.coverage("Balanced").loc[case]),
        "group_median_days": median,
    }


def _values_12(data: Data = None) -> dict[str, Any]:
    return _worked_po_item(data)


def item_12_worked_po_item(data: Data = None) -> pd.Series:
    """The worked PO item: the Packaging item with a positive C04 deviation value whose lag is closest to the
    median over all evaluable Packaging items (ties by ascending item identifier), and its assessment
    (``coverage`` is the share of in-scope weight with usable evidence, here seven ninths)."""
    return pd.Series(_worked_po_item(data), name="worked PO item")


def _values_13(data: Data = None) -> dict[str, Any]:
    return {"mean_penalty": float(application(BPIC19, data).penalty("Balanced").mean())}


def item_13_population_mean_penalty(data: Data = None) -> float:
    """Mean case penalty of all scored purchase-order items under Balanced."""
    return float(_values_13(data)["mean_penalty"])


def _slice_values(app: Application, view: str, group: str) -> dict[str, Any]:
    row = app.backlog(view).table.loc[group]
    return {
        "mean_penalty": float(1.0 - row["mean_score"]),
        "scored": int(row["n_cases"]),
        "gap": float(row["gap"]),
        "pi": float(row["PI"]),
    }


def _values_14(data: Data = None) -> dict[str, Any]:
    return _slice_values(application(BPIC19, data), "Balanced", PACKAGING)


def item_14_packaging(data: Data = None) -> pd.Series:
    """Packaging under Balanced: mean case penalty, scored items, gap above the population mean, Priority Index."""
    return pd.Series(_values_14(data), name=_label(PACKAGING))


def _values_15(data: Data = None) -> dict[str, Any]:
    return _slice_values(application(BPIC19, data), "Balanced", LOGISTICS)


def item_15_logistics(data: Data = None) -> pd.Series:
    """Logistics under Balanced: mean case penalty, scored items, gap above the population mean, Priority Index."""
    return pd.Series(_values_15(data), name=_label(LOGISTICS))


def _values_16(data: Data = None) -> dict[str, Any]:
    app = application(BPIC19, data)
    coverage = app.result.coverage("Balanced").groupby(app.assessment.groups).mean()
    return {"packaging": float(coverage[PACKAGING]), "logistics": float(coverage[LOGISTICS])}


def item_16_slice_coverage(data: Data = None) -> pd.Series:
    """Mean Balanced weighted evidence coverage of Packaging and Logistics."""
    values = _values_16(data)
    return pd.Series({_label(PACKAGING): values["packaging"], _label(LOGISTICS): values["logistics"]}, name="mean coverage")


def _layer_table(data: Data = None) -> pd.DataFrame:
    app = application(BPIC19, data)
    signed = wise.layer_contributions(app.result, app.backlog("Balanced"))
    return signed.loc[[PACKAGING, LOGISTICS]]


def _values_17(data: Data = None) -> dict[str, Any]:
    t = _layer_table(data)
    out = {f"packaging.{layer}": float(t.loc[PACKAGING, layer]) for layer in t.columns}
    out.update({f"logistics.{layer}": float(t.loc[LOGISTICS, layer]) for layer in t.columns})
    return out


def item_17_layer_contributions(data: Data = None) -> pd.DataFrame:
    """Signed layer contributions to the aggregate penalty gap under Balanced, for Packaging and Logistics.

    The last two columns show that the contributions, summed and then clipped at zero, give the Priority Index.
    """
    app = application(BPIC19, data)
    t = _layer_table(data)
    out = t.copy()
    out["sum"] = t.sum(axis=1)
    out["Priority Index"] = app.backlog("Balanced").table.loc[t.index, "PI"]
    out.index = [_label(g) for g in out.index]
    return out


def _values_18(data: Data = None) -> dict[str, Any]:
    app = application(BPIC19, data)
    out = _values_17(data)
    for name, group in (("packaging", PACKAGING), ("logistics", LOGISTICS)):
        values = _slice_values(app, "Balanced", group)
        out[f"{name}.scored"], out[f"{name}.pi"] = values["scored"], values["pi"]
    return out


def item_18_figure_4(data: Data = None) -> Any:
    """Figure 4: layer contributions to the aggregate penalty gap under Balanced, Packaging and Logistics."""
    from . import figures

    app = application(BPIC19, data)
    t = _layer_table(data)
    panels = []
    for group in (PACKAGING, LOGISTICS):
        values = _slice_values(app, "Balanced", group)
        panels.append(
            {
                "group": group.split(" | ", 1)[1],
                "scored_cases": values["scored"],
                "priority_index": values["pi"],
                "components": {layer: float(t.loc[group, layer]) for layer in t.columns},
            }
        )
    return figures.layer_contributions(panels, note=f"Balanced view; both groups belong to {PACKAGING.split(' | ', 1)[0]}.")


def _values_19(data: Data = None) -> dict[str, Any]:
    a = application(BPIC19, data).assessment
    logistics = a.groups.eq(LOGISTICS)
    return {
        "no_invoice_receipt": int(a.severity.loc[logistics, "C01"].gt(0).sum()),
        "no_clearing": int(a.severity.loc[logistics, "C02"].gt(0).sum()),
    }


def item_19_logistics_absences(data: Data = None) -> pd.Series:
    """Logistics: items without a recorded invoice receipt (C01) and without a recorded clearing (C02)."""
    return pd.Series(_values_19(data), name=_label(LOGISTICS))


def vendor_penalties(data: Data = None, view: str = "Balanced", group: str = PACKAGING) -> pd.DataFrame:
    """Per vendor of a group: scored items, total and mean case penalty, cumulative share of the group's total."""
    app = application(BPIC19, data)
    members = app.assessment.groups.eq(group)
    frame = pd.DataFrame({"vendor": app.assessment.features.loc[members, "vendor"], "q": app.penalty(view)[members]})
    t = frame.groupby("vendor").agg(cases=("q", "size"), total_penalty=("q", "sum"), mean_penalty=("q", "mean")).reset_index()
    t = t.sort_values(["total_penalty", "cases", "vendor"], ascending=[False, False, True], kind="mergesort")
    total = float(t.total_penalty.sum())
    t["cumulative_share"] = t.total_penalty.cumsum() / total if total else np.nan
    return t.set_index("vendor")


def _values_20(data: Data = None) -> dict[str, Any]:
    t = vendor_penalties(data)
    total = float(t.total_penalty.sum())
    needed = min(len(t), int(np.searchsorted(t.total_penalty.cumsum().to_numpy(), 0.8 * total, side="left")) + 1) if total else 0
    return {"vendors": len(t), "vendors_for_80_percent": needed}


def item_20_vendor_concentration(data: Data = None) -> pd.Series:
    """Packaging: number of vendors, and of vendors that together carry at least 80 % of the group's total
    case penalty under Balanced (the sum of case penalties, not the Priority Index)."""
    return pd.Series(_values_20(data), name=_label(PACKAGING))


VIEW_PAIRS = (("Balanced", "Completion"), ("Balanced", "Operations"), ("Completion", "Operations"))


def document_shortlist(data: Data = None, view: str = "Balanced", k: int = 20) -> tuple[list[str], bool]:
    """The top-``k`` purchasing documents with a positive Priority Index under a view, and whether a tied
    Priority Index extends across the selection boundary.

    A slice is a purchasing document with its PO items; the case count and the comparison reference stay
    defined at PO-item level.
    """
    table = application(BPIC19, data).backlog(view, by="document").table
    positive = table[table["PI"] > POSITIVE]
    selected = positive.head(k)
    tie = bool(len(positive) > len(selected) and np.isclose(positive["PI"].iloc[len(selected)], selected["PI"].iloc[-1], atol=POSITIVE, rtol=0))
    return [str(key) for key in selected.index], tie


def _shortlist_table(data: Data = None) -> pd.DataFrame:
    lists = {view: document_shortlist(data, view) for view in dict.fromkeys(v for pair in VIEW_PAIRS for v in pair)}
    rows = []
    for a, b in VIEW_PAIRS:
        left, right = set(lists[a][0]), set(lists[b][0])
        rows.append(
            {
                "views": f"{a} / {b}",
                "shared": len(left & right),
                "distinct": len(left | right),
                "jaccard": len(left & right) / len(left | right) if left | right else float("nan"),
                "length_first": len(left),
                "length_second": len(right),
                "tie_across_cut": lists[a][1] or lists[b][1],
            }
        )
    return pd.DataFrame(rows).set_index("views")


def _values_21(data: Data = None) -> dict[str, Any]:
    t = _shortlist_table(data)
    out: dict[str, Any] = {}
    for a, b in VIEW_PAIRS:
        out[f"shared.{a}-{b}"] = int(t.loc[f"{a} / {b}", "shared"])
        out[f"jaccard.{a}-{b}"] = float(t.loc[f"{a} / {b}", "jaccard"])
    for view in dict.fromkeys(v for pair in VIEW_PAIRS for v in pair):
        keys, tie = document_shortlist(data, view)
        out[f"list_length.{view}"] = len(keys)
        out[f"tie_across_cut.{view}"] = tie
    return out


def item_21_document_shortlists(data: Data = None) -> pd.DataFrame:
    """Top-20 positive-priority purchasing documents shared between views: shared documents, Jaccard similarity
    (shared divided by distinct documents across both lists), list lengths and ties at the cut."""
    return _shortlist_table(data)


def _values_22(data: Data = None) -> dict[str, Any]:
    app = application(BPIC19, data)
    out: dict[str, Any] = {}
    for view in app.views:
        first, second = _top(app.backlog(view).table, "PI", 2)
        out[f"first.{view}"], out[f"second.{view}"] = _label(first), _label(second)
    return out


def item_22_first_two_slices(data: Data = None) -> pd.DataFrame:
    """The first two company-by-spend-area groups under every view, with their Priority Index."""
    app = application(BPIC19, data)
    rows = []
    for view in app.views:
        table = app.backlog(view).table
        first, second = _top(table, "PI", 2)
        rows.append(
            {
                "view": view,
                "first": _label(first),
                "PI first": float(table.loc[first, "PI"]),
                "second": _label(second),
                "PI second": float(table.loc[second, "PI"]),
            }
        )
    return pd.DataFrame(rows).set_index("view")


def ranking_policies(data: Data = None) -> pd.DataFrame:
    """The 30 groups under Balanced with the quantities of the four ranking policies.

    The Balanced case penalties, the scored population and the group definitions are the same for every
    policy: ``PI`` (primary), ``mean_penalty``, ``total_penalty`` and ``PI_gamma20`` (small-slice adjustment).
    """
    app = application(BPIC19, data)
    table = app.backlog("Balanced").table.copy()
    table["mean_penalty"] = 1.0 - table["mean_score"]
    table["total_penalty"] = table["n_cases"] * table["mean_penalty"]
    table["PI_gamma20"] = app.backlog("Balanced", gamma=20).table["stable_PI"].reindex(table.index)
    return table[["n_cases", "mean_penalty", "total_penalty", "PI", "PI_gamma20"]]


def _values_24(data: Data = None) -> dict[str, Any]:
    table = ranking_policies(data)
    primary = set(_top(table, "PI", 10))
    return {
        "mean_penalty": len(primary & set(_top(table, "mean_penalty", 10))),
        "total_penalty": len(primary & set(_top(table, "total_penalty", 10))),
        "gamma20": len(primary & set(_top(table, "PI_gamma20", 10))),
    }


def item_24_ranking_policies(data: Data = None) -> pd.Series:
    """Groups that the top ten of each ranking policy share with the primary PI top ten."""
    return pd.Series(_values_24(data), name="shared with the primary PI top ten")


def _values_25(data: Data = None) -> dict[str, Any]:
    shortlists, policies = _values_21(data), _values_24(data)
    out = {f"A.{a}-{b}": shortlists[f"shared.{a}-{b}"] for a, b in VIEW_PAIRS}
    out.update({f"B.{key}": value for key, value in policies.items()})
    return out


def item_25_figure_6(data: Data = None) -> Any:
    """Figure 6: shortlist membership under declared assessment choices (A: views, B: ranking policies)."""
    from . import figures

    shortlists, policies = _values_21(data), _values_24(data)
    view_pairs = [{"left": a, "right": b, "shared": shortlists[f"shared.{a}-{b}"]} for a, b in VIEW_PAIRS]
    return figures.shortlists(view_pairs, [policies["mean_penalty"], policies["total_penalty"], policies["gamma20"]])


# ----------------------------------------------------------------------------- items 26, 29, 30: BPIC'13 incidents
def _values_26(data: Data = None) -> dict[str, Any]:
    a = application(BPIC13, data).assessment
    return {"incidents": a.source["cases"], "events": a.source["events"], "groups": int(a.groups.nunique()), "criteria": len(a.severity.columns)}


def item_26_incident_log_size(data: Data = None) -> pd.Series:
    """Incidents, events, product groups and criteria of the BPIC'13 incident application."""
    return pd.Series(_values_26(data), name="BPIC'13 incidents")


def _lead_group(app: Application, view: str) -> str:
    table = app.backlog(view).table
    positive = table[table["PI"] > POSITIVE]
    return str(_top(positive, "PI", 1)[0])


def _product_values(data: Data, product: str) -> dict[str, Any]:
    app = application(BPIC13, data)
    signed = wise.layer_contributions(app.result, app.backlog("Balanced")).loc[product]
    out = _slice_values(app, "Balanced", product)
    del out["gap"]
    out.update({f"layer.{layer}": float(value) for layer, value in signed.items()})
    return out


def _values_29(data: Data = None) -> dict[str, Any]:
    return _product_values(data, PROD542)


def item_29_prod542(data: Data = None) -> pd.Series:
    """Product group PROD542 under Balanced: incidents, mean case penalty, Priority Index and the signed
    layer contributions to its aggregate penalty gap (the paper prints the one of Routing)."""
    return pd.Series(_values_29(data), name=PROD542)


def _values_30(data: Data = None) -> dict[str, Any]:
    return _product_values(data, PROD424)


def item_30_prod424(data: Data = None) -> pd.Series:
    """Product group PROD424 under Balanced: incidents, mean case penalty, Priority Index and the signed
    layer contributions to its aggregate penalty gap (see item 37)."""
    return pd.Series(_values_30(data), name=PROD424)


# ----------------------------------------------------------------------------- items 31 and 32: BPIC'17
def _values_31(data: Data = None) -> dict[str, Any]:
    a = application(BPIC17, data).assessment
    unavailable = a.in_scope & a.severity.isna()
    return {"applications": a.source["cases"], "groups": int(a.groups.nunique()), "unavailable_in_scope": int(unavailable.sum().sum())}


def item_31_lending_log_size(data: Data = None) -> pd.Series:
    """Loan applications, groups by application type and loan goal, and in-scope criteria without usable evidence."""
    return pd.Series(_values_31(data), name="BPIC'17")


def _values_32(data: Data = None) -> dict[str, Any]:
    app = application(BPIC17, data)
    return {f"first.{view}": _label(_lead_group(app, view)) for view in app.views}


def item_32_lending_first_slices(data: Data = None) -> pd.Series:
    """The group with the highest Priority Index under each view of the lending application."""
    values = _values_32(data)
    return pd.Series({key.split(".", 1)[1]: v for key, v in values.items()}, name="highest Priority Index")


# ----------------------------------------------------------------------------- item 33: consistency check
@lru_cache(maxsize=8)
def _consistency(folder: str, name: str) -> dict[str, Any]:
    app = _application(folder, name)
    return replay.consistency(app.assessment, app.result)


def _values_33(data: Data = None) -> dict[str, Any]:
    folder = str(_data.data_folder(data))
    reports = [_consistency(folder, name) for name in replay.APPLICATIONS if _data.locate(name, data)]
    largest = max(r["max_residual"] for r in reports)
    return {
        "applications": len(reports),
        "views_per_application": min(r["views"] for r in reports),
        "primary_views": sum(r["views"] for r in reports),
        "scoring_modes": len(replay.MODES),
        "gammas": " and ".join(f"{g:g}" for g in replay.GAMMAS) if all(r["gammas"] == list(replay.GAMMAS) for r in reports) else "",
        "largest_difference": largest,
        "tolerance": replay.TOLERANCE,
        "below_tolerance": bool(largest < replay.TOLERANCE),
        "scope_and_evidence_identical": all(r["scope_identical"] and r["evidence_identical"] for r in reports),
        "mode_view_combinations": sum(r["mode_view_combinations"] for r in reports),
        "largest_difference_by_application": {r["application"]: r["max_residual"] for r in reports},
    }


def item_33_consistency_check(data: Data = None) -> pd.Series:
    """The numerical check of Section 5.6: the library's scoring and aggregation against the reference
    arithmetic on the same prepared criterion assessments, for three views in each of the three applications
    (nine primary view evaluations, eighteen mode-view combinations across flat and layer-balanced scoring),
    each at γ = 0 and γ = 20.

    The largest absolute difference is a floating-point residual; its digits depend on the machine and on
    the versions of NumPy and pandas, its order of magnitude and the bound of 1e-8 do not.
    """
    values = _values_33(data)
    by_application = values.pop("largest_difference_by_application")
    out = {
        "applications": values["applications"],
        "views per application": values["views_per_application"],
        "primary view evaluations": values["primary_views"],
        "scoring modes": values["scoring_modes"],
        "mode-view combinations": values["mode_view_combinations"],
        "each checked at γ": values["gammas"],
        "largest absolute difference": values["largest_difference"],
        "declared tolerance": values["tolerance"],
        "below tolerance": values["below_tolerance"],
        "scope and evidence states identical": values["scope_and_evidence_identical"],
    }
    out.update({f"largest absolute difference, {name}": value for name, value in by_application.items()})
    return pd.Series(out, name="consistency check")


# ----------------------------------------------------------------------------- items 35 and 36: BPIC'19
def _values_35(data: Data = None) -> dict[str, Any]:
    a = application(BPIC19, data).assessment
    out: dict[str, Any] = {}
    for name, group in (("logistics", LOGISTICS), ("packaging", PACKAGING)):
        members = a.groups.eq(group)
        out[f"{name}.evaluable"] = int(a.state.loc[members, "C04"].eq(EVALUATED).sum())
        out[f"{name}.applicable"] = int(a.in_scope.loc[members, "C04"].sum())
    return out


def item_35_c04_endpoints(data: Data = None) -> pd.DataFrame:
    """Logistics and Packaging: items for which C04 applies, and those of them with usable endpoints
    (both selected timestamps usable and a non-negative interval)."""
    values = _values_35(data)
    rows = {
        _label(group): {"applicable": values[f"{name}.applicable"], "usable endpoints": values[f"{name}.evaluable"]}
        for name, group in (("logistics", LOGISTICS), ("packaging", PACKAGING))
    }
    return pd.DataFrame(rows).T


def _values_36(data: Data = None) -> dict[str, Any]:
    return {f"first.{view}": document_shortlist(data, view, k=1)[0][0] for view in application(BPIC19, data).views}


def item_36_first_documents(data: Data = None) -> pd.Series:
    """The purchasing document with the highest Priority Index under each view."""
    values = _values_36(data)
    return pd.Series({key.split(".", 1)[1]: v for key, v in values.items()}, name="first purchasing document")


# ----------------------------------------------------------------------------- items 37 and 38: BPIC'13 incidents
def _values_37(data: Data = None) -> dict[str, Any]:
    return {key: value for key, value in _product_values(data, PROD424).items() if key.startswith("layer.")}


def item_37_prod424_layers(data: Data = None) -> pd.Series:
    """Product group PROD424 under Balanced: the signed layer contributions to its aggregate penalty gap."""
    values = _values_37(data)
    return pd.Series({key.split(".", 1)[1]: v for key, v in values.items()}, name=PROD424)


def _positive(table: pd.DataFrame, column: str, k: int | None = None) -> list[str]:
    """The slice keys with a positive value of ``column``, in ranked order, at most ``k`` of them."""
    positive = table[table[column] > POSITIVE]
    return _top(positive, column, len(positive) if k is None else k)


def _values_38(data: Data = None) -> dict[str, Any]:
    app = application(BPIC13, data)
    primary, adjusted = app.backlog("Balanced"), app.backlog("Balanced", gamma=20)
    first, with_gamma = _positive(primary.table, "PI", 10), _positive(adjusted.table, "stable_PI", 10)
    return {
        "first.gamma0": first[0],
        "first.gamma20": with_gamma[0],
        f"pi.gamma20.{PROD424}": float(adjusted.table.loc[PROD424, "stable_PI"]),
        f"pi.gamma20.{PROD542}": float(adjusted.table.loc[PROD542, "stable_PI"]),
        "positive_in_top_ten": len(with_gamma),
        "shared_top_ten": len(set(first) & set(with_gamma)),
        "jaccard": float(wise.top_k_overlap(primary, adjusted, k=10)),
    }


def item_38_incident_adjustment(data: Data = None) -> pd.Series:
    """The incident groups under Balanced with the small-slice adjustment at γ = 20: the first group without
    and with the adjustment, the adjusted Priority Index of PROD424 and PROD542, and the membership of the
    ten positive-priority products (shared members and Jaccard similarity)."""
    return pd.Series(_values_38(data), name="Balanced, γ = 20")


# ----------------------------------------------------------------------------- item 39: BPIC'17
def _values_39(data: Data = None) -> dict[str, Any]:
    app = application(BPIC17, data)
    layers = pd.Series(dict(app.assessment.layers))
    out: dict[str, Any] = {"criteria": len(layers), "criteria.Interaction": int(layers.eq("Interaction").sum())}
    for view in app.views:
        primary, adjusted = app.backlog(view).table, app.backlog(view, gamma=20).table
        positive, with_gamma = _positive(primary, "PI"), _positive(adjusted, "stable_PI")
        out[f"first.gamma20.{view}"] = _label(with_gamma[0])
        out[f"membership_retained.{view}"] = set(positive) == set(with_gamma)
        out[f"positive_at_ten.{view}"] = len(_positive(primary, "PI", 10))
    return out


def item_39_lending_adjustment(data: Data = None) -> pd.DataFrame:
    """The lending groups per view: the first group without and with the small-slice adjustment at γ = 20,
    whether the groups with a positive priority stay the same, and how many groups with a positive priority
    a list of capacity ten contains."""
    app = application(BPIC17, data)
    values = _values_39(data)
    rows = {
        view: {
            "first, γ = 0": _label(_lead_group(app, view)),
            "first, γ = 20": values[f"first.gamma20.{view}"],
            "positive membership retained": values[f"membership_retained.{view}"],
            "positive groups at capacity ten": values[f"positive_at_ten.{view}"],
        }
        for view in app.views
    }
    return pd.DataFrame(rows).T


# ----------------------------------------------------------------------------- item 40: weights of the BPIC'19 norm
P2P_LAYERS = ("Completion", "Timing", "Rework", "Effort proxy")


def _values_40(data: Data = None) -> dict[str, Any]:
    weights = native.native_norm(BPIC19).weight_table()
    out: dict[str, Any] = {"criteria": len(weights)}
    for layer in P2P_LAYERS:
        members = weights[weights["layer"].eq(layer)]
        out[f"share.Balanced.{layer}"] = float(members["Balanced"].sum() / weights["Balanced"].sum())
        for view in ("Balanced", "Completion", "Operations"):
            values = set(members[view])
            out[f"raw.{view}.{layer}"] = float(values.pop()) if len(values) == 1 else float("nan")
    return out


def item_40_view_weights() -> pd.DataFrame:
    """The purchase-to-pay norm: per layer the raw weight of each of its criteria under the three views, and
    the share of the total weight that Balanced gives the layer when all ten criteria are in scope and evaluable."""
    values = _values_40()
    rows = {
        layer: {
            **{f"raw weight per criterion, {view}": values[f"raw.{view}.{layer}"] for view in ("Balanced", "Completion", "Operations")},
            "layer share under Balanced": values[f"share.Balanced.{layer}"],
        }
        for layer in P2P_LAYERS
    }
    return pd.DataFrame(rows).T


# ----------------------------------------------------------------------------- item 41: the illustration of Section 3
ILLUSTRATION_VIEWS = ("Processing effort", "Financial control")


def _illustration() -> tuple[wise.ScoreResult, dict[str, pd.DataFrame]]:
    result = wise.score(wise.illustrative_invoice_log(), wise.illustrative_invoice_norm())
    tables = {view: wise.prioritize(result, by=["plant", "document_type"], view=view, as_index=False).table for view in ILLUSTRATION_VIEWS}
    return result, tables


def _values_41(data: Data = None) -> dict[str, Any]:
    result, tables = _illustration()
    out: dict[str, Any] = {}
    for case in result.violations.index:
        for constraint in result.violations.columns:
            out[f"deviation.{case}.{constraint}"] = float(result.violations.loc[case, constraint])
    for view in ILLUSTRATION_VIEWS:
        table = tables[view].set_index("plant")
        weights, weighted = result.norm.raw_weights(view), result.penalties(view)
        for constraint in result.violations.columns:
            out[f"weight.{view}.{constraint}"] = float(weights[constraint])
            for case in result.scores.index:
                out[f"weighted.{view}.{case}.{constraint}"] = float(weighted.loc[case, constraint])
        for case in result.scores.index:
            out[f"score.{view}.{case}"] = float(result.scores.loc[case, view])
        out[f"reference.{view}"] = float(table["global_mean"].iloc[0])
        for plant in ("Plant A", "Plant B"):
            out[f"mean.{view}.{plant}"] = float(table.loc[plant, "mean_score"])
            out[f"pi.{view}.{plant}"] = float(table.loc[plant, "PI"])
        out[f"first.{view}"] = str(tables[view]["plant"].iloc[0])
    return out


def item_41_illustration() -> pd.DataFrame:
    """The illustrative assessment of Section 3 (Figure 2): the shared deviation values of the four invoice
    cases, the weights of both views, the scores, and per view the reference mean, the slice means and the
    Priority Index. The weighted deviations of the figure are ``wise.score(...).penalties(view)``."""
    result, tables = _illustration()
    cases = result.violations.join(result.scores.add_prefix("score, "))
    cases.insert(0, "plant", result.cases["plant"])
    weights = pd.DataFrame({view: result.norm.raw_weights(view) for view in ILLUSTRATION_VIEWS}).T
    rows = [
        cases.reset_index().rename(columns={"case": "row"}).assign(kind="case"),
        weights.rename_axis("row").reset_index().assign(kind="view weights"),
    ]
    for view in ILLUSTRATION_VIEWS:
        table = tables[view]
        rows.append(
            pd.DataFrame(
                {
                    "row": table["plant"] + " · " + table["document_type"] + f", {view}",
                    "plant": table["plant"],
                    "scored cases": table["n_cases"],
                    "mean score": table["mean_score"],
                    "reference mean": table["global_mean"],
                    "Priority Index": table["PI"],
                    "kind": "slice",
                }
            )
        )
    return pd.concat(rows, ignore_index=True).set_index(["kind", "row"])


# ----------------------------------------------------------------------------- item 42: constructed checks
def _constructed_checks() -> dict[str, float]:
    """Largest absolute differences of the two constructed checks, on the two bundled examples and in both modes."""
    out = {"shuffled_events": 0.0, "norm_reloaded": 0.0}
    examples = (
        (wise.running_p2p_log(), wise.running_p2p_norm()),
        (wise.illustrative_invoice_log(), wise.illustrative_invoice_norm()),
    )
    for log, norm in examples:
        shuffled = wise.EventLog(
            log.events.sample(frac=1, random_state=0),
            case_col=log.case_col,
            activity_col=log.activity_col,
            timestamp_col=log.timestamp_col,
            case_attributes=log.case_attributes,
        )
        reloaded = wise.Norm.loads(norm.dumps())
        for mode in replay.MODES:
            base = wise.score(log, norm, mode=mode)
            out["shuffled_events"] = max(out["shuffled_events"], replay.residual(wise.score(shuffled, norm, mode=mode).violations, base.violations))
            out["norm_reloaded"] = max(out["norm_reloaded"], replay.residual(wise.score(log, reloaded, mode=mode).scores, base.scores))
    return out


def _values_42(data: Data = None) -> dict[str, Any]:
    checks = _constructed_checks()
    return {
        "shuffled_events.preserved": checks["shuffled_events"] == 0.0,
        "norm_reloaded.preserved": checks["norm_reloaded"] == 0.0,
        **{f"{name}.largest_difference": value for name, value in checks.items()},
    }


def item_42_constructed_checks() -> pd.Series:
    """The two constructed checks that Section 5.6 names, made on the two bundled examples: the deviation values
    after the rows of the event table are shuffled, and the case scores after the norm is serialised and
    reloaded. The same checks on generated logs are in ``tests/test_invariants.py``; :func:`further_checks`
    makes checks of this kind on the three applications."""
    checks = _constructed_checks()
    return pd.Series(
        {
            "deviation values after shuffling the event rows: largest difference": checks["shuffled_events"],
            "deviation values preserved": checks["shuffled_events"] == 0.0,
            "case scores after serialising and reloading the norm: largest difference": checks["norm_reloaded"],
            "case scores preserved": checks["norm_reloaded"] == 0.0,
        },
        name="constructed checks",
    )


@lru_cache(maxsize=8)
def _further_checks(folder: str, name: str) -> dict[str, Any]:
    return replay.further_checks(_application(folder, name).assessment)


def further_checks(data: Data = None) -> pd.DataFrame:
    """Three further checks on each application, beyond what the paper states: the case scores of all views, under
    flat and layer-balanced scoring, when the complete cases are reordered, when the norm is serialised and
    read back, and when the whole-case context is attached (largest absolute score difference per check)."""
    folder = str(_data.data_folder(data))
    rows = {}
    for name in replay.APPLICATIONS:
        _data.locate(name, data)
        report = _further_checks(folder, name)
        rows[name] = {
            "cases reordered": report["residuals"]["reordered"],
            "norm serialised and read back": report["residuals"]["norm_read_back"],
            "whole-case context attached": report["residuals"]["context_attached"],
            "context": ", ".join(report["context"]),
            "norm fingerprint unchanged": report["fingerprint_unchanged"],
            "scores preserved": report["passed"],
        }
    return pd.DataFrame(rows).T


# ----------------------------------------------------------------------------- input identity and calculation record
def input_identity(name: str = BPIC19, data: Data = None) -> pd.Series:
    """Identity of the input that was read for an application: file name, events, cases, bytes and SHA-256."""
    source = application(name, data).assessment.source
    keys = ("file", "events", "cases", "documents", "bytes", "sha256")
    return pd.Series({key: source[key] for key in keys if key in source}, name=name)


def configuration_sha256(configuration: Any) -> str:
    """SHA-256 of an adapter configuration in canonical form (JSON with sorted keys and no white space)."""
    canonical = json.dumps(dict(configuration), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


GROUPINGS = {BPIC19: "company by spend area", BPIC13: "product", BPIC17: "application type by loan goal"}
"""The primary grouping of each application."""

RECORD_PARTS = (
    "source_export",
    "adapter_configuration",
    "norm",
    "tested_settings",
    "evidence_summaries",
    "ordered_results",
    "numerical_checks",
)
"""The parts of a calculation record, in the order in which Appendix B.2 of the paper lists what a record identifies."""


def calculation_record(name: str, data: Data = None) -> dict[str, Any]:
    """The calculation record of one application (paper Appendix B.2).

    A JSON-serialisable mapping that identifies

    * ``source_export``: the file that was read, its size and SHA-256, and its numbers of events and cases;
    * ``adapter_configuration``: identifier, version, file and SHA-256 (canonical form) of the configuration;
    * ``norm``: name, version, file and fingerprint of the native norm, and its criteria with their layers;
    * ``tested_settings``: views with their raw weights, scoring modes, values of γ, grouping, scale,
      comparison reference and tie order;
    * ``evidence_summaries``: per criterion the cases in scope, evaluated, outside scope and unavailable by reason;
    * ``ordered_results``: per view the reference mean and the ranked groups under the primary settings;
    * ``numerical_checks``: the comparison with the reference arithmetic (every residual, scope and evidence
      equality) and the three further checks (cases reordered, norm read back, whole-case context attached).

    It holds aggregates and identities only: no case of a log and no path of the machine.
    """
    app = application(name, data)
    a, result = app.assessment, app.result
    folder = str(_data.data_folder(data))
    consistency, further = _consistency(folder, name), _further_checks(folder, name)
    configuration_name = "bpic2013" if name == BPIC13 else name
    cases = len(a.state)
    states: dict[str, Any] = {}
    for criterion in a.severity.columns:
        counts = a.state[criterion].value_counts()
        in_scope = int(a.in_scope[criterion].sum())
        states[criterion] = {
            "layer": a.layers[criterion],
            "cases": cases,
            "in_scope": in_scope,
            "outside_scope": cases - in_scope,
            "evaluated": int(counts.get(EVALUATED, 0)),
            "unavailable": {str(reason): int(n) for reason, n in counts.items() if reason not in (EVALUATED, OUT_OF_SCOPE)},
        }
    ordered: dict[str, Any] = {}
    for view in app.views:
        table = app.backlog(view).table
        ordered[view] = {
            "scored_cases": int(table["n_cases"].sum()),
            "reference_mean_score": float(table["global_mean"].iloc[0]),
            "groups": [
                {
                    "rank": rank,
                    "group": _label(key),
                    "scored_cases": int(row.n_cases),
                    "mean_score": float(row.mean_score),
                    "gap": float(row.gap),
                    "priority_index": float(row.PI),
                }
                for rank, (key, row) in enumerate(table.iterrows(), start=1)
            ],
        }
    return {
        "schema_version": 1,
        "kind": "calculation record",
        "application": name,
        "library": {
            "name": "wise-pm-library",
            "version": wise.__version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "source_export": dict(a.source),
        "adapter_configuration": {
            "id": str(a.configuration["id"]),
            "version": str(a.configuration.get("version", "1")),
            "file": f"adapters/{configuration_name}.json",
            "sha256": configuration_sha256(a.configuration),
        },
        "norm": {
            "name": result.norm.name,
            "version": result.norm.version,
            "file": f"norms/native/{name}.json",
            "fingerprint": result.norm.fingerprint(),
            "criteria": {criterion: a.layers[criterion] for criterion in a.severity.columns},
        },
        "tested_settings": {
            "views": {view: {c: float(w) for c, w in weights.items()} for view, weights in a.views.items()},
            "scoring_modes": list(replay.MODES),
            "primary_scoring_mode": result.mode,
            "gammas": list(replay.GAMMAS),
            "primary_gamma": 0.0,
            "grouping": GROUPINGS[name],
            "groups": int(a.groups.nunique()),
            "scale": "scored cases",
            "comparison_reference": "mean score of all scored cases under the view",
            "tie_order": wise.TIE_POLICY,
            "whole_case_context": list(replay.CONTEXT[name]),
        },
        "evidence_summaries": states,
        "ordered_results": ordered,
        "numerical_checks": {
            "tolerance": replay.TOLERANCE,
            "reference_arithmetic": {
                key: consistency[key]
                for key in (
                    "cases", "criteria", "views", "mode_view_combinations", "scope_identical", "evidence_identical",
                    "max_residual", "passed", "checks", "differential_checks",
                )
            },
            "further_checks": {key: further[key] for key in ("modes", "context", "residuals", "fingerprint_unchanged", "max_residual", "passed")},
        },
    }


# ----------------------------------------------------------------------------- tables
def table_3() -> pd.DataFrame:
    """Table 3: the running P2P norm, with layers, constraint types, parameters and the weights of both views."""
    norm = wise.running_p2p_norm()
    names = {layer.id: layer.name for layer in norm.layers}
    table = norm.describe()[["layer", "type", "description", "params", "applicability"]]
    table["layer"] = table["layer"].map(names)
    return table.join(norm.weight_table().drop(columns="layer"))


def table_4() -> pd.DataFrame:
    """Table 4 (the same as :func:`item_01_table_4`)."""
    return item_01_table_4()


def _criteria_table(cfg: dict[str, Any], criteria: list[dict[str, Any]], scale: Callable[[dict[str, Any]], str]) -> pd.DataFrame:
    rows = []
    for c in criteria:
        row = {"criterion": c["id"], "recorded condition": c["name"], "deviation scale": scale(c), "layer": c["layer"]}
        if "scope" in c:
            row["scope"] = c["scope"]
        if c.get("evidence_policy") or c.get("evidence"):
            row["evidence"] = c.get("evidence_policy") or c.get("evidence")
        for view, weights in cfg["views"].items():
            row[f"w({view})"] = weights[c["layer"]] if c["layer"] in weights else weights[c["id"]]
        rows.append(row)
    return pd.DataFrame(rows).set_index("criterion").fillna("")


def _ramp(c: dict[str, Any]) -> str:
    if "threshold" not in c:
        return "binary"
    if c["threshold"] == 0 and c["width"] == 1:
        return "binary"
    return f"0 at {c['threshold']:g}; 1 at {c['threshold'] + c['width']:g}"


def table_b1() -> pd.DataFrame:
    """Table B1: the ten criteria of the purchase-to-pay norm with deviation scale, scope, evidence rule, layer
    and the raw weights of the three views."""
    cfg = configuration("bpic2019")
    return _criteria_table(cfg, cfg["criteria"], _ramp)


def incident_criteria() -> pd.DataFrame:
    """The six criteria of the incident norm; ``r(x; t, b) = min{1, max{0, (x − t)/b}}``."""
    cfg = configuration("bpic2013")
    return _criteria_table(cfg, cfg["criteria"], lambda c: "binary" if (c["threshold"], c["width"]) == (0, 1) else f"r(x; {c['threshold']:g}, {c['width']:g})")


def lending_criteria() -> pd.DataFrame:
    """The five criteria of the lending norm; ``r(x; t, b) = min{1, max{0, (x − t)/b}}``."""
    cfg = configuration("bpic2017")
    criteria = [{"id": cid, "name": c["meaning"], **c} for cid, c in cfg["criteria"].items()]
    return _criteria_table(cfg, criteria, lambda c: f"r(x; {c['threshold']:g}, {c['width']:g})")


def figure_4(data: Data = None) -> Any:
    """Figure 4 (the same as :func:`item_18_figure_4`)."""
    return item_18_figure_4(data)


def figure_5(data: Data = None) -> Any:
    """Figure 5 (the same as :func:`item_11_figure_5`)."""
    return item_11_figure_5(data)


def figure_6(data: Data = None) -> Any:
    """Figure 6 (the same as :func:`item_25_figure_6`)."""
    return item_25_figure_6(data)


# ----------------------------------------------------------------------------- comparison
ITEMS: dict[int, Callable[..., Any]] = {
    1: item_01_table_4,
    2: item_02_worked_arithmetic,
    3: item_03_log_size,
    4: item_04_flow_categories,
    5: item_05_slices,
    6: item_06_scored_cases,
    7: item_07_mean_coverage,
    8: item_08_c04_evaluable,
    9: item_09_lag_medians,
    10: item_10_lag_medians_df2,
    11: item_11_figure_5,
    12: item_12_worked_po_item,
    13: item_13_population_mean_penalty,
    14: item_14_packaging,
    15: item_15_logistics,
    16: item_16_slice_coverage,
    17: item_17_layer_contributions,
    18: item_18_figure_4,
    19: item_19_logistics_absences,
    20: item_20_vendor_concentration,
    21: item_21_document_shortlists,
    22: item_22_first_two_slices,
    24: item_24_ranking_policies,
    25: item_25_figure_6,
    26: item_26_incident_log_size,
    29: item_29_prod542,
    30: item_30_prod424,
    31: item_31_lending_log_size,
    32: item_32_lending_first_slices,
    33: item_33_consistency_check,
    35: item_35_c04_endpoints,
    36: item_36_first_documents,
    37: item_37_prod424_layers,
    38: item_38_incident_adjustment,
    39: item_39_lending_adjustment,
    40: item_40_view_weights,
    41: item_41_illustration,
    42: item_42_constructed_checks,
}
"""Item number → the function that computes the item. Numbers 23, 27, 28 and 34 are not in use."""

_VALUES: dict[int, Callable[..., dict[str, Any]]] = {
    1: _values_01,
    2: _values_02,
    3: _values_03,
    4: _values_04,
    5: _values_05,
    6: _values_06,
    7: _values_07,
    8: _values_08,
    9: _values_09,
    10: _values_10,
    11: _values_11,
    12: _values_12,
    13: _values_13,
    14: _values_14,
    15: _values_15,
    16: _values_16,
    17: _values_17,
    18: _values_18,
    19: _values_19,
    20: _values_20,
    21: _values_21,
    22: _values_22,
    24: _values_24,
    25: _values_25,
    26: _values_26,
    29: _values_29,
    30: _values_30,
    31: _values_31,
    32: _values_32,
    33: _values_33,
    35: _values_35,
    36: _values_36,
    37: _values_37,
    38: _values_38,
    39: _values_39,
    40: _values_40,
    41: _values_41,
    42: _values_42,
}

AGREES, DIFFERS, NOT_COMPUTED = "agrees", "differs", "not computed"


def expected_values() -> list[dict[str, Any]]:
    """The expected-values file: every result item with its printed values and where they appear."""
    text = resources.files(__package__).joinpath("expected", "paper_values.json").read_text(encoding="utf-8")
    items: list[dict[str, Any]] = json.loads(text)["items"]
    return items


def computed_values(item: int, data: Data = None) -> dict[str, Any]:
    """The computed values of one item, keyed as in the expected-values file."""
    return _VALUES[item](data)


def _agrees(kind: str, expected: Any, computed: Any, decimals: int | None) -> bool:
    if kind == "number":
        half_unit = Decimal(5) * Decimal(10) ** (-(int(decimals or 0) + 1))
        return abs(Decimal(repr(float(computed))) - Decimal(str(expected))) <= half_unit
    if kind == "order":  # the same order of magnitude: within a factor of ten of the printed value
        return bool(float(expected) / 10 <= float(computed) <= float(expected) * 10)
    if kind == "count":
        return int(computed) == int(expected)
    if kind == "flag":
        return bool(computed) is bool(expected)
    return str(computed) == str(expected)


def compare(data: Data = None, items: list[int] | None = None) -> pd.DataFrame:
    """Every printed value beside the computed one.

    One row per printed value with the columns ``item``, ``place``,
    ``quantity``, ``printed``, ``computed``, ``agrees`` (``True``, ``False``,
    or ``None`` where the value was not computed), ``status`` and ``note``.
    The status is ``"agrees"``, ``"differs"`` or ``"not computed"`` (the log
    of the item is not in the data folder). A number agrees when it rounds to
    the printed value at the printed number of decimals. One printed value,
    the largest difference of the consistency check, is a floating-point
    residual whose digits depend on the machine and on library versions: it
    is compared by its order of magnitude, and that it is below the declared
    tolerance is a value of its own.
    """
    rows = []
    for entry in expected_values():
        number = int(entry["item"])
        if items is not None and number not in items:
            continue
        note = ""
        try:
            computed: dict[str, Any] | None = _VALUES[number](data)
        except _data.DataNotAvailable as exc:
            computed, note = None, str(exc)
        for value in entry["values"]:
            row = {
                "item": number,
                "place": entry["place"],
                "quantity": value["quantity"],
                "printed": value["printed"],
                "computed": None,
                "agrees": None,
                "status": NOT_COMPUTED,
                "note": note,
            }
            if computed is not None:
                got = computed[value["key"]]
                row["computed"] = got.item() if isinstance(got, np.generic) else got
                ok = _agrees(value["kind"], value["value"], got, value.get("decimals"))
                row["agrees"], row["status"], row["note"] = ok, AGREES if ok else DIFFERS, value.get("note", "")
            rows.append(row)
    return pd.DataFrame(rows, columns=["item", "place", "quantity", "printed", "computed", "agrees", "status", "note"])


def summary(comparison: pd.DataFrame) -> pd.DataFrame:
    """One row per result item: its place, the number of printed values, how many agree, differ or were not
    computed, and ``agrees`` (every value agrees)."""
    titles = {int(e["item"]): (e["title"], e["kind"]) for e in expected_values()}
    rows = []
    for number, group in comparison.groupby("item", sort=True):
        counts = group["status"].value_counts()
        rows.append(
            {
                "item": int(number),
                "place": group["place"].iloc[0],
                "title": titles[int(number)][0],
                "kind": titles[int(number)][1],
                "values": len(group),
                "agree": int(counts.get(AGREES, 0)),
                "differ": int(counts.get(DIFFERS, 0)),
                "not_computed": int(counts.get(NOT_COMPUTED, 0)),
                "agrees": bool(counts.get(AGREES, 0) == len(group)),
            }
        )
    return pd.DataFrame(rows).set_index("item")
