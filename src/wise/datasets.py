"""Bundled example data: the two illustrations of the paper.

Section 4. :func:`running_p2p_norm` builds the norm of Table 3 (six
constraints in five layers, views Finance and Logistics).
:func:`running_p2p_log` builds an event log whose five cases σA … σE have the
key facts of Table 4, so that scoring them yields the scores printed there.

Section 3. :func:`illustrative_invoice_norm` and
:func:`illustrative_invoice_log` build the assessment of Figure 2: three
constraints in two layers, the views Processing effort and Financial control,
and four invoice cases in two slices.
"""

from __future__ import annotations

import pandas as pd

from .constraints import Balance, Exclusion, Lag, Presence, Singularity
from .log import EventLog
from .norm import Layer, Norm, NormConstraint, View

GR = "Record Goods Receipt"
INV = "Record Invoice Receipt"
CLR = "Clear Invoice"
CINV = "Cancel Invoice Receipt"
PO = "Create Purchase Order Item"


def running_p2p_norm() -> Norm:
    """Norm ``N`` of Table 3 with the Finance and Logistics views.

    Constraint ``c4`` (ordered against received amount) is declared applicable
    to flow type ``DF1`` only; the illustrative cases are ``DF2`` items, for
    which Table 4 assumes ``c4`` not applicable. The scoring mode is ``flat``.
    """
    layers = (
        Layer("completeness", "Core completeness"),
        Layer("timing", "Receipt-to-invoice timing"),
        Layer("match", "Match consistency"),
        Layer("handling", "Handling discipline"),
        Layer("exceptions", "Exception discipline"),
    )
    constraints = (
        NormConstraint("c1", "completeness", Presence(INV, m=1), description="Require an invoice receipt"),
        NormConstraint(
            "c2",
            "timing",
            Lag(GR, INV, delta=10, width=20, unit="D"),
            description="Invoice timeliness: GR → INV within 10 days",
        ),
        NormConstraint(
            "c3",
            "match",
            Balance("amount", INV, "amount", GR, tau=0.05, width=0.20),
            description="Amount consistency: invoiced amount matches received amount",
        ),
        NormConstraint(
            "c4",
            "match",
            Balance("amount", PO, "amount", GR, tau=0.01, width=0.02),
            applicability={"flow_type": ["DF1"]},
            description="GR amount consistency: ordered amount matches received amount",
        ),
        NormConstraint("c5", "handling", Singularity(GR, k=2, K=3), description="Limit delivery fragmentation"),
        NormConstraint("c6", "exceptions", Exclusion(CINV), description="Avoid invoice cancellations"),
    )
    views = (
        View("Finance", constraint_weights={"c1": 0.20, "c2": 0.45, "c3": 0.20, "c4": 0.05, "c5": 0.05, "c6": 0.10}),
        View("Logistics", constraint_weights={"c1": 0.25, "c2": 0.15, "c3": 0.05, "c4": 0.25, "c5": 0.45, "c6": 0.10}),
    )
    return Norm(constraints, layers, views, name="Running P2P example (paper Table 3)", version="1", scoring_mode="flat")


def running_p2p_events() -> pd.DataFrame:
    """Events of the five illustrative cases of Table 4."""
    t0 = pd.Timestamp("2024-01-01")
    rows: list[dict[str, object]] = []

    def ev(case: str, act: str, day: float, amount: float | None = None, company: str = "A", vendor: str = "V1") -> None:
        rows.append(
            {
                "case": case,
                "activity": act,
                "time": t0 + pd.Timedelta(days=day),
                "amount": amount,
                "flow_type": "DF2",
                "company": company,
                "vendor": vendor,
            }
        )

    for case, company, vendor in [("A", "A", "V1"), ("B", "A", "V2"), ("C", "B", "V1"), ("D", "B", "V1"), ("E", "B", "V2")]:
        ev(case, PO, -1, 100, company=company, vendor=vendor)
    # σA: lag GR→INV 25 days, one GR, amounts match, no cancellation
    ev("A", GR, 0, 100)
    ev("A", INV, 25, 100)
    ev("A", CLR, 30)
    # σB: lag 8 days, four goods receipts (fragmentation), amounts match
    for d in range(4):
        ev("B", GR, d, 25, vendor="V2")
    ev("B", INV, 8, 100, vendor="V2")
    ev("B", CLR, 12, vendor="V2")
    # σC: lag 7 days, one GR, invoiced 82 against received 100 → mismatch 0.18
    ev("C", GR, 0, 100, company="B")
    ev("C", INV, 7, 82, company="B")
    ev("C", CLR, 9, company="B")
    # σD: lag 5 days, one GR, amounts match, invoice cancelled
    ev("D", GR, 0, 100, company="B")
    ev("D", INV, 5, 100, company="B")
    ev("D", CINV, 6, company="B")
    # σE: invoice missing → lag undefined, mismatch 1
    ev("E", GR, 0, 100, company="B", vendor="V2")
    return pd.DataFrame(rows)


def running_p2p_log() -> EventLog:
    return EventLog(
        running_p2p_events(),
        case_col="case",
        activity_col="activity",
        timestamp_col="time",
        case_attributes=["flow_type", "company", "vendor"],
    )


REL = "Release Invoice"
FWD = "Forward Invoice"
RCV = "Receive Invoice"


def illustrative_invoice_norm() -> Norm:
    """The process norm of Figure 2 with the views Processing effort and Financial control.

    An invoice is released at most once (two releases reach the cap of the
    deviation scale), is not forwarded to another team, and has a release
    record. The first two constraints form the layer Invoice handling, the
    third the layer Required records. The scoring mode is ``flat``.
    """
    layers = (Layer("handling", "Invoice handling"), Layer("records", "Required records"))
    constraints = (
        NormConstraint("release_limit", "handling", Singularity(REL, k=1, K=1), description="Release limit (at most once)"),
        NormConstraint("no_forwarding", "handling", Exclusion(FWD), description="No forwarding"),
        NormConstraint("release_record", "records", Presence(REL, m=1), description="Required release record"),
    )
    views = (
        View("Processing effort", constraint_weights={"release_limit": 0.40, "no_forwarding": 0.40, "release_record": 0.20}),
        View("Financial control", constraint_weights={"release_limit": 0.10, "no_forwarding": 0.10, "release_record": 0.80}),
    )
    return Norm(constraints, layers, views, name="Illustrative invoice assessment (paper Figure 2)", version="1", scoring_mode="flat")


def illustrative_invoice_log() -> EventLog:
    """The four invoice cases of Figure 2: A1 and A2 of Plant A, B1 and B2 of Plant B, all of document type X.

    A1 and A2 each record two releases, A1 also a forwarding; B1 and B2 have no release record.
    """
    t0 = pd.Timestamp("2024-01-01")
    histories = {
        "A1": ("Plant A", [RCV, REL, FWD, REL]),
        "A2": ("Plant A", [RCV, REL, REL]),
        "B1": ("Plant B", [RCV]),
        "B2": ("Plant B", [RCV]),
    }
    rows = [
        {"case": case, "activity": activity, "time": t0 + pd.Timedelta(days=day), "plant": plant, "document_type": "Type X"}
        for case, (plant, activities) in histories.items()
        for day, activity in enumerate(activities)
    ]
    return EventLog(pd.DataFrame(rows), case_col="case", activity_col="activity", timestamp_col="time", case_attributes=["plant", "document_type"])
