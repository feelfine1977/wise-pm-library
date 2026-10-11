"""BPI Challenge 2019: the ten-criterion assessment of purchase-order items (paper Sections 5.1 to 5.4, Appendix B.1, Table B1).

The adapter reads the CSV export of the challenge, derives one feature row
per purchase-order item, and evaluates the ten criteria of the configuration
``wise-bpic19-transparent-ten-v1`` (``bpic2019.json``) with their business
scope and evidence rules:

* business scope follows the four flow categories of the log (the item
  category of the purchase-order item);
* for a timing criterion the earliest parsed timestamp of each activity set
  is selected (a timestamp that cannot be parsed is passed over when another
  one exists); a selected timestamp outside the declared plausibility
  interval makes the criterion unavailable and is not replaced by a later
  one, as does a negative interval for C04. C04 does not pair invoice
  instances and does not look for the next clearing after the invoice;
* C09 and C10 need a usable resource identity on every event of the case.

Recorded absence is an observation about the available history; it does not
establish that a step was not completed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data import sha256
from . import EVALUATED, OUT_OF_SCOPE, Assessment, configuration

__all__ = ["APPLICATION", "assess", "assessment_matrices", "features_from_events", "read_events", "weights_for"]

APPLICATION = "bpic2019"

CASE = "case concept:name"
ACT = "event concept:name"
TS = "event time:timestamp"
DOC = "case Purchasing Document"
RESOURCE = "event org:resource"
COLS = [
    "eventID",
    CASE,
    ACT,
    TS,
    DOC,
    RESOURCE,
    "case Item",
    "case Company",
    "case Spend area text",
    "case Vendor",
    "case Item Category",
]
ACTIVITY_SETS = {
    "invoice": ["Record Invoice Receipt"],
    "clear": ["Clear Invoice"],
    "receipt": ["Record Goods Receipt", "Record Service Entry Sheet"],
    "cancel_invoice": ["Cancel Invoice Receipt"],
    "edits": ["Change Price", "Change Quantity"],
}


def read_events(path: str | Path, cfg: dict[str, Any], *, digest: str | None = None) -> pd.DataFrame:
    """The events of the audited CSV export, with parsed timestamps and resource evidence flags.

    The file is refused unless its SHA-256 is the one of the configuration;
    the counts of events, cases and purchasing documents are asserted.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("the BPI Challenge 2019 CSV is required; no substitute or sample is used")
    if (digest or sha256(path)) != cfg["expected_csv_sha256"]:
        raise ValueError(
            "the CSV does not have the checksum of the audited BPI Challenge 2019 export; "
            "another export needs its own reviewed configuration"
        )
    d = pd.read_csv(
        path,
        encoding=cfg["csv_encoding"],
        dtype=str,
        usecols=lambda c: c.strip() in COLS,
        keep_default_na=False,
    )
    d.columns = d.columns.str.strip()
    if sorted(d.columns) != sorted(COLS):
        raise ValueError("required BPI Challenge 2019 fields are not available")
    d["timestamp"] = pd.to_datetime(d[TS], format=cfg["timestamp_format"], errors="coerce")
    # The export uses anonymised user_### and batch_## identities. An identity is
    # read ignoring letter case and surrounding whitespace; any other label is
    # not assumed to stand for a person or for automation.
    identity = d[RESOURCE].str.strip().str.lower()
    d["resource_identity"] = identity
    d["user_record"] = identity.str.fullmatch(r"user_[0-9]+").astype(bool)
    d["resource_usable"] = d["user_record"] | identity.str.fullmatch(r"batch_[0-9]+").astype(bool)
    if len(d) != cfg["expected_events"]:
        raise ValueError("unexpected number of events")
    if d[CASE].nunique() != cfg["expected_cases"] or d[DOC].nunique() != cfg["expected_documents"]:
        raise ValueError("unexpected number of purchase-order items or purchasing documents")
    if d["eventID"].nunique() != len(d):
        raise ValueError("event identifiers are not unique")
    if not (d[CASE] == d[DOC] + "_" + d["case Item"]).all():
        raise ValueError("a case identifier is not the purchasing document and item")
    for col in [CASE, DOC, ACT, RESOURCE, "case Company", "case Spend area text", "case Vendor", "case Item Category"]:
        d[col] = d[col].astype("category")
    return d


def features_from_events(d: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """One row per purchase-order item: context attributes, flow category, counts and first timestamps."""
    gb = d.groupby(CASE, observed=True, sort=False)
    attrs = [DOC, "case Company", "case Spend area text", "case Vendor", "case Item Category"]
    f = gb[attrs].first().astype(str)
    for col in attrs:
        if (gb[col].nunique(dropna=False) > 1).any():
            raise ValueError(f"case-level attribute varies within a case: {col}")
    f.index = f.index.astype(str)
    f.index.name = "case_id"
    f["flow"] = f["case Item Category"].map(cfg["flow_map"])
    if f["flow"].isna().any():
        raise ValueError("unmapped item category: business scope is never assigned silently")
    f["n_events"] = gb.size().to_numpy()
    f["all_resources_usable"] = gb.resource_usable.all().to_numpy()
    f["user_events"] = gb.user_record.sum().to_numpy()
    users = d.loc[d.user_record].groupby(CASE, observed=True)["resource_identity"].nunique()
    f["user_identities"] = users.reindex(f.index, fill_value=0)
    start = pd.Timestamp(cfg["timing_plausibility_start"])
    end = pd.Timestamp(cfg["timing_plausibility_end_exclusive"])
    for key, labels in ACTIVITY_SETS.items():
        sub = d.loc[d[ACT].isin(labels)]
        sg = sub.groupby(CASE, observed=True)
        f[f"n_{key}"] = sg.size().reindex(f.index, fill_value=0)
        # The first recorded timestamp is selected before the plausibility check:
        # a first endpoint outside the interval is not replaced by a later event.
        first = sg.timestamp.min().reindex(f.index)
        f[f"first_{key}"] = first
        f[f"usable_{key}"] = first.ge(start) & first.lt(end)
    f["invoice_clear_days"] = (f.first_clear - f.first_invoice).dt.total_seconds() / 86400
    f["group"] = f[cfg["group_columns"]].replace("", cfg["missing_group_label"]).agg(" | ".join, axis=1)
    f["vendor"] = f["case Vendor"].replace("", cfg["missing_group_label"])
    f["document"] = f[DOC]
    return f


def assessment_matrices(f: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Deviation values, business scope, evidence states and recorded quantities of the ten criteria."""
    ids = [c["id"] for c in cfg["criteria"]]
    rules = {c["id"]: c for c in cfg["criteria"]}
    for cid in ["C04", "C07", "C08", "C09", "C10"]:
        if not np.isfinite(rules[cid]["threshold"]) or not np.isfinite(rules[cid]["width"]) or rules[cid]["width"] <= 0:
            raise ValueError(f"{cid}: the threshold must be finite and the width positive")
    scope = pd.DataFrame(True, index=f.index, columns=ids)
    nonconsign = f.flow.ne("Consignment")
    scope.loc[:, ["C01", "C02", "C04", "C08"]] = np.broadcast_to(nonconsign.to_numpy()[:, None], (len(f), 4))
    scope["C03"] = f.flow.isin(["DF1", "DF2"])
    scope["C05"] = f.flow.eq("DF1")
    V = pd.DataFrame(np.nan, index=f.index, columns=ids)
    reason = pd.DataFrame(EVALUATED, index=f.index, columns=ids)
    raw = pd.DataFrame(index=f.index)
    raw["C01"] = f.n_invoice.eq(0).astype(float)
    raw["C02"] = f.n_clear.eq(0).astype(float)
    raw["C03"] = f.n_receipt.eq(0).astype(float)
    raw["C04"] = f.invoice_clear_days
    raw["C05"] = (f.first_invoice - f.first_receipt).dt.total_seconds() / 86400
    raw["C06"] = f.n_cancel_invoice.astype(float)
    raw["C07"] = f.n_edits.astype(float)
    raw["C08"] = f.n_invoice.astype(float)
    raw["C09"] = f.user_events.astype(float)
    raw["C10"] = f.user_identities.astype(float)
    V["C01"], V["C02"], V["C03"] = raw.C01, raw.C02, raw.C03
    V["C04"] = ((raw.C04 - rules["C04"]["threshold"]) / rules["C04"]["width"]).clip(0, 1)
    V["C05"] = raw.C05.lt(0).astype(float)
    V["C06"] = raw.C06.gt(0).astype(float)
    for cid in ["C07", "C08", "C09", "C10"]:
        V[cid] = ((raw[cid] - rules[cid]["threshold"]) / rules[cid]["width"]).clip(0, 1)
    for criterion, endpoints in {"C04": ("invoice", "clear"), "C05": ("invoice", "receipt")}.items():
        missing = f[f"n_{endpoints[0]}"].eq(0) | f[f"n_{endpoints[1]}"].eq(0)
        invalid = f[f"first_{endpoints[0]}"].isna() | f[f"first_{endpoints[1]}"].isna()
        invalid |= ~f[f"usable_{endpoints[0]}"] | ~f[f"usable_{endpoints[1]}"]
        if criterion == "C04":
            invalid |= f.invoice_clear_days.lt(0)
        reason.loc[invalid, criterion] = "invalid_temporal_evidence"
        reason.loc[missing, criterion] = "missing_prerequisite"
        V.loc[missing | invalid, criterion] = np.nan
    reason.loc[~f.all_resources_usable, ["C09", "C10"]] = "missing_resource_evidence"
    V.loc[~f.all_resources_usable, ["C09", "C10"]] = np.nan
    V = V.where(scope)
    reason = reason.mask(~scope, OUT_OF_SCOPE)
    return V, scope, reason, raw


def weights_for(cfg: dict[str, Any], view: str) -> dict[str, float]:
    """Raw weight per criterion under a view: the multiplier of the criterion's layer."""
    return {c["id"]: float(cfg["views"][view][c["layer"]]) for c in cfg["criteria"]}


def assess(path: str | Path) -> Assessment:
    """Read the verified CSV and prepare the assessment of all purchase-order items."""
    cfg = configuration("bpic2019")
    path = Path(path)
    digest = sha256(path)
    events = read_events(path, cfg, digest=digest)
    features = features_from_events(events, cfg)
    severity, scope, state, raw = assessment_matrices(features, cfg)
    source = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "events": len(events),
        "cases": len(features),
        "documents": int(features["document"].nunique()),
        "activities": int(events[ACT].nunique()),
    }
    return Assessment(
        application=APPLICATION,
        configuration=cfg,
        features=features,
        severity=severity,
        in_scope=scope,
        state=state,
        raw=raw,
        groups=features["group"].rename("group"),
        layers={c["id"]: c["layer"] for c in cfg["criteria"]},
        views={view: weights_for(cfg, view) for view in cfg["views"]},
        source=source,
    )
