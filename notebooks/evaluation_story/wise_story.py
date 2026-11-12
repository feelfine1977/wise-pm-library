"""Functions used by the notebook WISE_BPIC19_Evaluation_Story.ipynb.

Needs pandas, numpy and matplotlib. The module reads the event log, derives one row of features per
purchase order item, and provides the WISE assessment, score and Priority Index:
case score = 1 - weighted mean deviation score of the evaluated constraints; Priority Index = n x positive underperformance gap.
The norms themselves are defined in the notebook.
"""
import hashlib
import textwrap
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

SHA256 = "7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00"
T_MIN, T_MAX = pd.Timestamp("2017-01-01"), pd.Timestamp("2020-01-01")   # plausible timestamps
END = pd.Timestamp("2019-01-28")                                       # publication of the log: observation boundary
COLS = {
    "case concept:name": "case", "case Purchasing Document": "po", "case Item Category": "flowtxt",
    "case Spend area text": "spend", "case Sub spend area text": "subspend", "case Company": "company",
    "case Vendor": "vendor", "case Item Type": "itemtype", "case Document Type": "doctype",
    "event concept:name": "act", "event Cumulative net worth (EUR)": "val", "event time:timestamp": "ts",
}
FLOW = {"3-way match, invoice after GR": "DF1", "3-way match, invoice before GR": "DF2", "2-way match": "2W", "Consignment": "CON"}
GR = ["Record Goods Receipt", "Record Service Entry Sheet"]

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8983", "#e4e3df", "#ffffff"
GRAY1, GRAY2 = "#b9b8b2", "#d9d8d3"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f4f7fb", "#cfe0f5", "#7fb0e8", BLUE, "#174a8a"])
W = 7.0


def style():
    plt.rcParams.update({"font.size": 8.5, "font.family": "DejaVu Sans", "axes.edgecolor": MUTED, "axes.linewidth": 0.6,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                         "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
                         "figure.dpi": 110, "savefig.facecolor": SURFACE})


# ---------------------------------------------------------------------------------------------- data
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def load(src):
    """Read the BPIC'19 CSV and derive one row of features per purchase order item."""
    df = pd.read_csv(src, encoding="cp1252", usecols=list(COLS), dtype={"case Purchasing Document": str}).rename(columns=COLS)
    df["ts"] = pd.to_datetime(df["ts"], format="%d-%m-%Y %H:%M:%S.%f")
    df["row"] = np.arange(len(df))
    df = df.sort_values(["case", "ts", "row"], kind="stable").reset_index(drop=True)
    df["ok"] = (df.ts >= T_MIN) & (df.ts < T_MAX)
    cases = df.drop_duplicates("case").set_index("case")[["po", "flowtxt", "spend", "subspend", "company", "vendor", "itemtype", "doctype"]].copy()
    cases["flow"] = cases.flowtxt.map(FLOW)
    idx = cases.index

    def cnt(*acts):
        return df[df.act.isin(acts)].groupby("case").size().reindex(idx, fill_value=0)

    def first_ts(*acts):
        return df[df.act.isin(acts) & df.ok].groupby("case").ts.min().reindex(idx)

    def first_val(*acts):
        return df[df.act.isin(acts)].drop_duplicates("case").set_index("case").val.reindex(idx)

    def sum_val(*acts):
        return df[df.act.isin(acts)].groupby("case").val.sum().reindex(idx)

    F = SimpleNamespace(df=df, cases=cases, idx=idx, cnt=cnt, first_ts=first_ts, first_val=first_val, sum_val=sum_val)
    F.n_gr, F.n_ir, F.n_clr = cnt(*GR), cnt("Record Invoice Receipt"), cnt("Clear Invoice")
    F.t_gr, F.t_ir, F.t_clr = first_ts(*GR), first_ts("Record Invoice Receipt"), first_ts("Clear Invoice")
    F.t_cre = first_ts("Create Purchase Order Item")
    F.v_gr, F.v_ir, F.v_clr = first_val(*GR), first_val("Record Invoice Receipt"), first_val("Clear Invoice")
    F.v_cre = first_val("Create Purchase Order Item")
    F.n_canc = cnt("Cancel Invoice Receipt")
    F.n_memo = cnt("Vendor creates debit memo", "Record Subsequent Invoice", "Cancel Subsequent Invoice")
    F.n_edit, F.n_rev = cnt("Change Price", "Change Quantity"), cnt("Cancel Goods Receipt")
    F.deleted = cnt("Delete Purchase Order Item") > 0
    fl = cases.flow
    F.df1, F.df2, F.two_way, F.con = fl == "DF1", fl == "DF2", fl == "2W", fl == "CON"
    F.invoiced, F.threeway = F.df1 | F.df2 | F.two_way, F.df1 | F.df2
    F.family = np.where(F.con, "CON", "INV")
    cases["quarter"] = F.t_cre.dt.to_period("Q").astype(str)
    F.month = F.t_cre.dt.to_period("M").astype(str)
    # readiness: first invoice (2-way) or the later of first invoice and first receipt; then the first clearing at or after it
    F.ready = F.t_ir.where(F.two_way, np.maximum(F.t_ir, F.t_gr)).where(F.t_ir.notna() & (F.two_way | F.t_gr.notna()))
    c = df[(df.act == "Clear Invoice") & df.ok][["case", "ts"]].merge(F.ready.rename("a"), left_on="case", right_index=True)
    F.days = ((c[c.ts >= c.a].groupby("case").ts.min().reindex(idx)) - F.ready).dt.total_seconds() / 86400
    F.key = {"spend_flow": (cases.spend + " | " + cases.flow).to_numpy(), "company_spend": (cases.company + " | " + cases.spend).to_numpy(),
             "vendor": cases.vendor.str.replace("vendorID_", "").to_numpy(), "document": cases.po.to_numpy()}
    return F


def rel(x, y):
    """Relative mismatch of two values."""
    return (x - y).abs() / np.maximum(np.maximum(x.abs(), y.abs()), 1e-9)


def ramp(z, lo, hi):
    """Threshold-saturation rule: 0 up to lo, linear, 1 from hi."""
    return ((z - lo) / (hi - lo)).clip(0, 1)


# ---------------------------------------------------------------------------------------------- assessment
def assess(constraints):
    """constraints: {id: (layer, business scope, evidence available or None, deviation score)}. Keeps the three states apart:
    outside business scope; in scope, evidence unavailable; evaluated (deviation score in [0, 1])."""
    names = list(constraints)
    lay = np.array([constraints[k][0] for k in names])
    S = np.column_stack([np.asarray(constraints[k][1]) for k in names])
    E = np.column_stack([np.asarray(constraints[k][1] & (constraints[k][2] if constraints[k][2] is not None else True)) for k in names])
    NU = np.column_stack([np.asarray(pd.Series(constraints[k][3]).fillna(0)) for k in names]) * E
    table = pd.DataFrame({"layer": lay, "in scope": S.sum(0), "evaluated": E.sum(0), "violated": (NU > 0).sum(0)}, index=names)
    table["share of evaluated"] = (table.violated / table.evaluated.clip(lower=1)).round(4)
    return SimpleNamespace(names=names, lay=lay, S=S, E=E, NU=NU, table=table, layers=list(dict.fromkeys(lay)))


def share(A, cid, mask):
    j = A.names.index(cid)
    e = A.E[:, j] & np.asarray(mask)
    v = int((A.NU[e, j] > 0).sum())
    return v, int(e.sum()), (v / e.sum() if e.sum() else np.nan)


def case_deviation(A, layer_weights):
    """Case deviation score under a view: weighted mean deviation score over the evaluated constraints. Raw weight of a constraint = layer weight / constraints in the layer."""
    w = np.array([layer_weights[l] / (A.lay == l).sum() for l in A.lay])
    Z = (A.E * w).sum(1)
    return np.where(Z > 0, (A.E * w * A.NU).sum(1) / np.where(Z > 0, Z, 1), np.nan)


def layer_deviation(A):
    """Layer deviation score: mean deviation score over the evaluated constraints of each layer; NaN where no constraint of the layer is evaluated for the case."""
    return pd.DataFrame({l: np.where(A.E[:, A.lay == l].any(1), A.NU[:, A.lay == l].sum(1) / np.maximum(A.E[:, A.lay == l].sum(1), 1), np.nan)
                         for l in A.layers})


def view_deviation(P, weights):
    """Case deviation score under a view given as layer weights: weighted mean of the layer deviation scores over the layers that are evaluated and have positive weight."""
    w = np.array([weights.get(l, 0) for l in P.columns], float)
    X = P.to_numpy()
    ok = ~np.isnan(X) & (w > 0)
    Z = (ok * w).sum(1)
    return np.where(Z > 0, np.where(ok, X * w, 0).sum(1) / np.where(Z > 0, Z, 1), np.nan)


def priority(pen, key, family=None, gamma=0.0, mask=None):
    """Priority Index per slice: n x positive underperformance gap. `pen` is the case deviation score (1 - case score).
    Comparison reference: all scored cases, or the scored cases of the same flow family when `family` is given."""
    g = pd.DataFrame({"pen": np.asarray(pen), "key": np.asarray(key), "fam": "all" if family is None else np.asarray(family)})
    g = g[g.pen.notna()]
    g["gap"] = g.pen - g.groupby("fam").pen.transform("mean")
    if mask is not None:
        g = g[np.asarray(mask)[g.index]]
    t = g.groupby("key").agg(n=("pen", "size"), mean_deviation=("pen", "mean"), signed=("gap", "sum"))
    t["PI"] = t.signed.clip(lower=0) * (t.n / (t.n + gamma))
    return t.sort_values("PI", ascending=False)


def concentration(t):
    p = t.PI[t.PI > 0]
    return {"assessed": len(t), "positive": len(p), "cover 80%": int(((p.cumsum() / p.sum()) < .8).sum() + 1)}


# ---------------------------------------------------------------------------------------------- figures
def nice(s):
    return s.replace(" | ", ", ").replace("2W", "2-way").replace("CON", "consignment")


def _bare(ax, left=True):
    if left:
        ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)


def fig_maturity(mt):
    fig, ax = plt.subplots(figsize=(W, 2.8))
    x = np.arange(len(mt))
    ax.axvspan(9.5, 11.5, color=GRAY2, alpha=.45, lw=0)
    ax.text(10.5, 1.02, "created after 30 Oct 2018:\nless than 90 days observed", ha="center", va="bottom", fontsize=7.5, color=INK2)
    for col, c in [("no clearing", BLUE), ("no invoice", ORANGE)]:
        ax.plot(x, mt[col], color=c, lw=2, marker="o", ms=4, mec=SURFACE, mew=1)
        ax.text(10.82, mt[col].iloc[11], f"{mt[col].iloc[11]:.1%}", ha="right", va="center", fontsize=8)
    ax.annotate("No clearing\n(items with an invoice)", (9, mt["no clearing"].iloc[9]), xytext=(6.2, 0.52), fontsize=8, arrowprops=dict(arrowstyle="-", color=MUTED, lw=.6))
    ax.annotate("No invoice receipt", (10, mt["no invoice"].iloc[10]), xytext=(6.6, 0.25), fontsize=8, arrowprops=dict(arrowstyle="-", color=MUTED, lw=.6))
    ax.set_xticks(x, [m[5:] for m in mt.index])
    ax.set_xlabel("Creation month of the purchase order item, 2018")
    ax.set_ylabel("Share of cases without the record")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.grid(axis="y", color=GRID, lw=.6)
    ax.set_axisbelow(True)
    return fig


def fig_composition(rows):
    """rows: [(label, {'deleted': n, 'recent': n, 'remaining': n})]"""
    fig, ax = plt.subplots(figsize=(W, 1.8))
    parts = [("deleted", "Deleted items", GRAY1), ("recent", "Created from Sept 2018", GRAY2), ("remaining", "Remaining", BLUE)]
    for y, (lab, d) in enumerate(rows):
        left = 0
        for k, _, c in parts:
            ax.barh(y, d[k], left=left, color=c, height=.55, edgecolor=SURFACE, lw=1.5)
            if d[k] > 1500:
                ax.text(left + d[k] / 2, y, f"{d[k]:,}", ha="center", va="center", fontsize=8, color=SURFACE if c == BLUE else INK)
            left += d[k]
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlabel("Cases violating the constraint in the first norm")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in parts], labels=[p[1] for p in parts], ncol=3, frameon=False,
              loc="lower center", bbox_to_anchor=(.5, 1.0), fontsize=8, handlelength=1.2)
    _bare(ax)
    return fig


def fig_throughput(tp, lo, hi):
    """tp: index spend area, columns p25, median, p75, n."""
    fig, ax = plt.subplots(figsize=(W, 0.28 * len(tp) + 1.1))
    ax.axvspan(lo, hi, color=GRAY2, alpha=.45, lw=0)
    for x, t, ha in [((lo + hi) / 2, "graded", "center"), (hi + 1.5, "deviation score 1", "left"), (lo - 1.5, "deviation score 0", "right")]:
        ax.text(x, -0.95, t, ha=ha, fontsize=7.5, color=INK2)
    for y, (k, r) in enumerate(tp.iterrows()):
        ax.plot([r.p25, r.p75], [y, y], color=BLUE, lw=5, solid_capstyle="round", alpha=.35)
        ax.scatter([r["median"]], [y], s=34, color=BLUE, edgecolor=SURFACE, lw=1, zorder=3)
        ax.text(r.p75 + 2.5, y, f"{r['median']:.0f}", va="center", fontsize=8)
    ax.set_yticks(range(len(tp)), [f"{k}  ({int(r.n):,})" for k, r in tp.iterrows()])
    ax.set_ylim(len(tp) - .5, -1.3)
    ax.set_xlim(0, max(115, hi + 16))
    ax.set_xlabel("Days from readiness to clearing: quartile range and median\n(readiness = later of first invoice receipt and first receipt)")
    ax.grid(axis="x", color=GRID, lw=.6)
    ax.set_axisbelow(True)
    _bare(ax)
    return fig


def fig_priority_table(M, rows, cols, group_at, n_col):
    """Table of Priority Index values; shading = share of the column total. `group_at` = index of the first combined view."""
    vals = M.loc[rows, cols].fillna(0).to_numpy()
    sh = vals / np.maximum(M[cols].fillna(0).sum(0).to_numpy(), 1e-9)
    fig, ax = plt.subplots(figsize=(W, 0.38 * len(rows) + 1.1))
    xpos = [j + (0.35 if j >= group_at else 0) for j in range(len(cols))]
    for i in range(len(rows)):
        for j, xj in enumerate(xpos):
            ax.add_patch(plt.Rectangle((xj - .48, i - .46), .96, .92, color=SEQ(min(sh[i, j] / .8, 1.0)), lw=0))
            ax.text(xj, i, f"{vals[i, j]:,.0f}" if vals[i, j] >= .5 else "0", ha="center", va="center", fontsize=8.5, color=SURFACE if sh[i, j] > .45 else INK)
    ax.set_xlim(-.55, xpos[-1] + .55)
    ax.set_ylim(len(rows) - .5, -.5)
    ax.set_xticks(xpos, [c.replace(" ", "\n") for c in cols])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)), [f"{nice(r)}  ({int(M.loc[r, n_col]):,})" for r in rows])
    if group_at < len(cols):
        ax.text((xpos[0] + xpos[group_at - 1]) / 2, -1.5, "Single-layer views", ha="center", fontsize=8.5, color=INK2)
        ax.text((xpos[group_at] + xpos[-1]) / 2, -1.5, "Combined views", ha="center", fontsize=8.5, color=INK2)
        ax.plot([xpos[0] - .48, xpos[group_at - 1] + .48], [-1.3, -1.3], color=MUTED, lw=.6, clip_on=False)
        ax.plot([xpos[group_at] - .48, xpos[-1] + .48], [-1.3, -1.3], color=MUTED, lw=.6, clip_on=False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    return fig


def fig_cells(rows):
    """rows: [(label, violated, evaluated, rate in the slice, rate among the others)]"""
    fig, ax = plt.subplots(figsize=(W, 0.55 * len(rows) + .6))
    for y, (lab, v, n, a, b) in enumerate(rows):
        ax.plot([b, a], [y, y], color=GRAY1, lw=2, zorder=1)
        ax.scatter([b], [y], s=42, color=MUTED, edgecolor=SURFACE, lw=1.2, zorder=2)
        ax.scatter([a], [y], s=42, color=BLUE, edgecolor=SURFACE, lw=1.2, zorder=3)
        ax.text(a + .02, y, f"{a:.1%}  ({v:,} of {n:,})", va="center", fontsize=8)
        ax.text(b - .015, y, f"{b:.1%}", va="center", ha="right", fontsize=8, color=INK2)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(-.09, 1.22)
    ax.set_xticks([0, .25, .5, .75, 1])
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Share of evaluated cases with a deviation")
    ax.grid(axis="x", color=GRID, lw=.6)
    ax.set_axisbelow(True)
    _bare(ax)
    ax.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=BLUE, ms=6), plt.Line2D([], [], marker="o", ls="", color=MUTED, ms=6)],
              labels=["Slice", "All other evaluated cases"], frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(.5, 1.0), fontsize=8)
    return fig


def fig_bars(tables, n=6, label=nice, xlabel="Priority Index", height=2.4):
    """tables: {title: Series of PI}"""
    fig, axes = plt.subplots(1, len(tables), figsize=(W, height))
    for ax, (title, s) in zip(np.atleast_1d(axes), tables.items()):
        t = s.sort_values(ascending=False).head(n)
        ax.barh(range(len(t)), t.values, color=BLUE, height=.6)
        for i, v in enumerate(t.values):
            ax.text(v + t.max() * .03, i, f"{v:,.0f}", va="center", fontsize=7.5)
        ax.set_yticks(range(len(t)), [label(str(k)) for k in t.index], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, t.max() * 1.3)
        ax.set_title(title, fontsize=9, loc="left")
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        _bare(ax)
    fig.supxlabel(xlabel, fontsize=8.5, color=INK2)
    fig.tight_layout(w_pad=1.5)
    return fig


def fig_search(ss, layers):
    fig, axes = plt.subplots(1, len(layers), figsize=(W, 2.3), sharey=True)
    for ax, L in zip(axes, layers):
        s = ss[ss.view == L]
        ax.scatter(s.slices, s.concentration, s=10, color=GRAY1, lw=0, zorder=1)
        for part, c in [("spend x company", ORANGE), ("spend x flow", BLUE)]:
            r = s[s.scheme == part].iloc[0]
            ax.scatter([r.slices], [r.concentration], s=38, color=c, edgecolor=SURFACE, lw=1, zorder=3)
        ax.set_xscale("log")
        ax.set_title(L, fontsize=9, loc="left")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color=GRID, lw=.6)
        ax.set_axisbelow(True)
        ax.set_xlabel("Slices")
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    axes[0].set_ylabel("Concentration: Priority Index of the five\nleading slices / attainable priority")
    fig.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=BLUE, ms=6), plt.Line2D([], [], marker="o", ls="", color=ORANGE, ms=6),
                        plt.Line2D([], [], marker="o", ls="", color=GRAY1, ms=4)],
               labels=["Spend area × flow", "Spend area × company", "Other slicing schemes"], frameon=False, ncol=3,
               loc="lower center", bbox_to_anchor=(.5, .98), fontsize=8)
    fig.tight_layout()
    return fig


def fig_grid(g, star, rows, cols, note):
    fig, ax = plt.subplots(figsize=(W, 0.36 * len(rows) + 1.0))
    for i in range(g.shape[0]):
        for j in range(g.shape[1]):
            ax.add_patch(plt.Rectangle((j - .47, i - .44), .94, .88, color=SEQ(g[i, j] / 5 * .75), lw=0))
            ax.text(j, i, f"{g[i, j]}" + ("*" if star[i, j] else ""), ha="center", va="center", fontsize=8.5, color=SURFACE if g[i, j] >= 4 else INK)
    ax.set_xlim(-.5, len(cols) - .5)
    ax.set_ylim(g.shape[0] - .5, -.5)
    ax.set_xticks(range(len(cols)), [c.replace(" ", "\n") for c in cols])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)), rows)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.text(-.5, g.shape[0] - .25, note, fontsize=7.5, color=INK2, va="top")
    return fig


def story_graph():
    """Outline of the evaluation as a graph. The numbers quoted here are compared with the computed results in the last cell of the notebook."""
    fig, ax = plt.subplots(figsize=(7.6, 10.4))
    ax.set_xlim(0, 104)
    ax.set_ylim(-3, 138)
    ax.axis("off")
    FS, FQ, FF = "#e8f0fb", "#f3f2ee", "#ffffff"

    def box(x, y, w, h, title, body, fill, edge=MUTED, wrap=42, tag=None, lw=.8):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc=fill, ec=edge, lw=lw))
        ax.text(x + 1.6, y + h - 1.7, title, fontsize=8.2, fontweight="bold", va="top", color=INK)
        lines = []
        for para in body:
            lines += textwrap.wrap(para, wrap) or [""]
        ax.text(x + 1.6, y + h - 5.0, "\n".join(lines), fontsize=7.2, va="top", color=INK2, linespacing=1.35)
        if tag:
            ax.text(x + w - 1.4, y + 1.2, tag, fontsize=6.8, va="bottom", ha="right", color=BLUE, fontweight="bold")

    def arrow(x1, y1, x2, y2, color=MUTED, lw=1.0, style="-|>"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=9, color=color, lw=lw, shrinkA=0, shrinkB=0))

    def note(x, y, lines):
        ax.text(x, y, "\n".join(lines), fontsize=7, va="center", color=INK, linespacing=1.4, style="italic")

    for y, lab in [(127.5, "QUESTION"), (85, "NORM, STEP BY STEP"), (21.5, "ANSWERS TO Q3")]:
        ax.text(0.5, y, lab, fontsize=7, color=MUTED, rotation=90, va="center", ha="center")
    box(4, 119, 44, 17, "What the process owner asks", ["Goal: compliance. Amounts \"have to match\".",
        "Q3: which documents stand out, where, how severe, in flow and in values, and who causes rework."], FQ, tag="Section 1")
    box(54, 119, 44, 17, "What we ask about WISE", ["EQ1 can the requirements become a norm", "EQ2 do priorities point at the problems",
        "EQ3 can each priority be traced", "EQ4 do perspectives differ", "EQ5 are priorities stable"], FQ, wrap=40, tag="Section 1")
    arrow(48, 127.5, 54, 127.5)
    arrow(26, 119, 26, 111.5)
    box(4, 92.5, 44, 19, "Step 1  Norm from the owner's words", ["12 constraints taken sentence by sentence from the challenge text.",
        "3 layers: Flow, Value, Invoice rework. All 251,734 cases scored."], FS, edge=BLUE, tag="Section 4", lw=1.1)
    box(54, 92.5, 44, 19, "First assessment", ["Logistics DF1 is first in every view.",
        "Below it, 16 of the 20 leading documents and the leading vendor are deleted or recent items."], FF)
    arrow(48, 102, 54, 102)
    arrow(26, 92.5, 26, 77.5, color=ORANGE, lw=1.3)
    note(29, 85, ["What the assessment shows about the norm:", "missing clearing 1.5% (Jan) to 90.4% (Dec) by creation month",
                  "95.8% of deleted items have no receipt (others 3.1%)", "1,331 of 1,498 value violations counted three times",
                  "no constraint covers payment time or order changes"])
    box(4, 58.5, 44, 19, "Step 2  Refined norm", ["Deleted items outside scope; evidence after 90 days.",
        "One value constraint. Timeliness added as a declared assumption. Order changes and reversals join Rework.",
        "4 layers; 242,895 cases scored."], FS, edge=BLUE, tag="Section 5", lw=1.1)
    box(54, 58.5, 44, 19, "Second assessment", ["Missing invoice 25,857 to 7,931; missing clearing 28,086 to 3,153.",
        "Every problem is visible in a constraint, but one combined ranking puts Packaging DF2 first in all five views."], FF)
    arrow(48, 68, 54, 68)
    arrow(26, 58.5, 26, 47.5, color=ORANGE, lw=1.3)
    note(29, 53, ["What the assessment shows about the ranking:", "Timeliness contributes 0.046 of the 0.066 mean deviation score",
                  "the three leading slices are identical in all five views"])
    box(4, 33.5, 94, 14, "Step 3  One Priority Index per layer: the slice × layer table", [
        "Priority Index under single-layer views. Slices: spend area × flow type. Two combined views: "
        "Compliance (Flow, Value, Rework) ranks Logistics DF1 first; Payment performance (adds Timeliness) ranks Packaging DF2 first."],
        FS, edge=BLUE, wrap=92, tag="Section 6", lw=1.1)
    finds = [("Flow", ["Logistics DF1", "invoice missing", "after receipt", "55.6% vs 3.1%"]), ("Value", ["Logistics DF1", "recorded values", "disagree", "76.3% vs 0.1%"]),
             ("Timeliness", ["Packaging DF2", "slower than the", "log median", "75.5% vs 31.3%"]),
             ("Rework", ["Trading & End", "Products DF2: price or", "quantity changed", "24.3% vs 9.6%"])]
    for x, (t, b) in zip([4, 28, 52, 76], finds):
        arrow(x + 11, 33.5, x + 11, 29.5)
        box(x, 13.5, 22, 16, t, b, FF, wrap=30)
        arrow(x + 11, 13.5, x + 11, 11.8, style="-")
    ax.plot([15, 87], [11.8, 11.8], color=MUTED, lw=1.0)
    arrow(26, 11.8, 26, 10.0)
    ax.text(99.5, 21.5, "Section\n7", fontsize=6.8, ha="left", va="center", color=BLUE, fontweight="bold")
    box(4, -1.5, 44, 11.5, "Checks", ["63 slicing schemes per layer; 8 settings; one case traced to its recorded events."], FQ, wrap=40, tag="Section 8")
    box(54, -1.5, 44, 11.5, "Close", ["Answers to the five parts of the question, next steps for the company, and what stays open."], FQ, wrap=40, tag="Section 9")
    arrow(48, 4.2, 54, 4.2)
    return fig
