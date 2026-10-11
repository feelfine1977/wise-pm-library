"""BPI Challenge 2017: the five-criterion assessment of loan applications (paper Section 5.5).

The adapter reads the XES log of applications and evaluates the five criteria
of the configuration ``loan_application_recorded_concerns_v1``
(``bpic2017.json``). The scored unit is an application trace; the primary
groups combine application type with loan goal.

Evidence rules: work observations keep their lifecycle distinctions, and
repeated starts are not inferred from repeated appearances of an activity in
different lifecycle states. C04 is in scope when an offer activity is
recorded; it needs exact reconciliation of creation-event identifiers with
created-offer identifiers and consistent references in other offer states.
C02 to C05 need usable activity and lifecycle labels throughout the case;
C03 needs every relevant resource identifier. C01 needs at least two events
and usable timestamps throughout.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data import sha256
from . import EVALUATED, OUT_OF_SCOPE, Assessment, configuration
from .xes import iter_traces, local

__all__ = ["APPLICATION", "assess", "assessment_matrices", "feature_row", "read_features"]

APPLICATION = "bpic2017"


def _attributes(element: Any) -> dict[str, Any]:
    """The direct attributes of a trace or event; a repeated key is refused."""
    children = [x for x in element if x.get("key") is not None]
    keys = [x.get("key") for x in children]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate direct XES attribute keys are ambiguous")
    return {x.get("key"): x.get("value") for x in children}


def _instant(value: Any) -> datetime | None:
    """A timezone-aware ISO timestamp as a UTC instant; ``None`` when it is not one."""
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d.astimezone(UTC) if d.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _present(value: Any, cfg: dict[str, Any]) -> bool:
    return value is not None and str(value).strip().upper() not in cfg["missing_markers"]


def _is(event: dict[str, Any], lifecycle: str) -> bool:
    return str(event.get("lifecycle:transition", "")).lower() == lifecycle


def feature_row(trace: dict[str, Any], events: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """The recorded quantities of one application."""
    names = [e.get("concept:name") for e in events]
    labels_ok = all(_present(x, cfg) for x in names) and all(_present(e.get("lifecycle:transition"), cfg) for e in events)
    starts = [e for e in events if str(e.get("concept:name", "")).startswith("W_") and _is(e, "start")]
    start_counts = Counter(e["concept:name"] for e in starts)
    stamps = [_instant(e.get("time:timestamp")) for e in events]
    time_ok = len(stamps) >= 2 and all(x is not None for x in stamps)
    offer_events = [e for e in events if str(e.get("concept:name", "")).startswith("O_")]
    creation = [e for e in events if e.get("concept:name") == cfg["offer_creation_activity"] and _is(e, "complete")]
    created = [e for e in events if e.get("concept:name") == cfg["offer_created_activity"] and _is(e, "complete")]
    ids = [e.get("EventID") for e in creation]
    state_ids = [e.get("OfferID") for e in created]
    other_ids = [e.get("OfferID") for e in offer_events if e.get("concept:name") != cfg["offer_creation_activity"]]
    offers_ok = (
        bool(ids)
        and all(_present(i, cfg) for i in ids + state_ids + other_ids)
        and len(ids) == len(set(ids))
        and len(state_ids) == len(set(state_ids))
        and set(ids) == set(state_ids)
        and set(other_ids) <= set(ids)
    )
    resources_ok = all(_present(e.get("org:resource"), cfg) for e in starts)
    return {
        "case_id": str(trace["concept:name"]),
        "event_count": len(events),
        "labels_complete": labels_ok,
        "observed_span_days": (max(stamps) - min(stamps)).total_seconds() / 86400 if time_ok else np.nan,  # type: ignore[type-var,operator]
        "work_start_records": len(starts),
        "repeated_work_starts": sum(max(n - 1, 0) for n in start_counts.values()) if labels_ok else np.nan,
        "work_start_resource_breadth": len({e["org:resource"] for e in starts}) if labels_ok and resources_ok else np.nan,
        "has_offer_records": bool(offer_events),
        "offer_identity_consistent": offers_ok if offer_events else False,
        "offer_multiplicity": len(set(ids)) if labels_ok and offers_ok else np.nan,
        "incomplete_state_records": sum(e.get("concept:name") == "A_Incomplete" and _is(e, "complete") for e in events)
        if labels_ok
        else np.nan,
        "application_type": trace.get("ApplicationType", "<not supplied>"),
        "loan_goal": trace.get("LoanGoal", "<not supplied>"),
    }


def read_features(path: str | Path, cfg: dict[str, Any], *, digest: str | None = None) -> pd.DataFrame:
    """One row per application of the verified log."""
    path = Path(path)
    if (digest or sha256(path)) != cfg["expected"]["sha256"]:
        raise ValueError("the file does not have the checksum of the audited BPI Challenge 2017 log")
    rows = []
    seen: set[str] = set()
    for element in iter_traces(path):
        trace = _attributes(element)
        case_id = trace.get("concept:name")
        if not _present(case_id, cfg) or case_id in seen:
            raise ValueError("missing or duplicate trace identity")
        seen.add(case_id)
        events = [_attributes(child) for child in element if local(child.tag) == "event"]
        rows.append(feature_row(trace, events, cfg))
    f = pd.DataFrame(rows).set_index("case_id")
    f.index = f.index.astype(str)
    if len(f) != cfg["expected"]["cases"] or int(f.event_count.sum()) != cfg["expected"]["events"]:
        raise ValueError("unexpected number of applications or events")
    return f


def assessment_matrices(f: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Deviation values ``r(x; t, b) = min{1, max{0, (x − t)/b}}``, scope, evidence states and recorded quantities."""
    V = pd.DataFrame(index=f.index)
    scope = pd.DataFrame(index=f.index)
    state = pd.DataFrame(index=f.index)
    raw = pd.DataFrame(index=f.index)
    for cid, c in cfg["criteria"].items():
        in_scope = f["has_offer_records"].astype(bool) if cid == "C04" else pd.Series(True, index=f.index)
        x = f[c["feature"]].astype(float)
        raw[cid] = x
        V[cid] = ((x - c["threshold"]) / c["width"]).clip(0, 1).where(in_scope)
        scope[cid] = in_scope
        state[cid] = np.where(~in_scope, OUT_OF_SCOPE, np.where(x.notna(), EVALUATED, "unevaluable"))
    return V, scope, state, raw


def assess(path: str | Path) -> Assessment:
    """Read the verified application log and prepare the assessment of all applications."""
    cfg = configuration("bpic2017")
    path = Path(path)
    digest = sha256(path)
    f = read_features(path, cfg, digest=digest)
    severity, scope, state, raw = assessment_matrices(f, cfg)
    groups = f[cfg["primary_group"]].fillna("<unknown>").astype(str).agg(cfg["group_separator"].join, axis=1).rename("group")
    source = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "events": int(f.event_count.sum()),
        "cases": len(f),
    }
    return Assessment(
        application=APPLICATION,
        configuration=cfg,
        features=f,
        severity=severity,
        in_scope=scope,
        state=state,
        raw=raw,
        groups=groups,
        layers={cid: c["layer"] for cid, c in cfg["criteria"].items()},
        views={view: {c: float(w) for c, w in weights.items()} for view, weights in cfg["views"].items()},
        source=source,
    )
