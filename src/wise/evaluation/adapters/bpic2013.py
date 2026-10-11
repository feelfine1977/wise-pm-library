"""BPI Challenge 2013, incidents: the six-criterion assessment (paper Section 5.5).

The adapter reads the XES log of incidents, orders the observations of every
incident by timestamp and original position, and evaluates the six criteria
of the configuration ``wise-bpic2013-transfer-six-v1`` (``bpic2013.json``).

Evidence rules: sequence criteria (team changes, returns, reactivation) need
usable values and timestamps throughout the incident, and conflicting values
at tied timestamps make them unavailable; a missing team observation is not
dropped to join the surrounding observations. The observed span needs at
least two events and usable timestamps throughout. Groups are the constant
product of an incident, with explicit categories for a missing or changing
product.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data import sha256
from . import EVALUATED, Assessment, configuration
from .xes import iter_traces, local

__all__ = ["APPLICATION", "assess", "assessment_matrices", "features", "read_events", "sequence_values"]

APPLICATION = "bpic2013_incidents"
_VALUE_TAGS = {"string", "date", "int", "float", "boolean", "id"}


def _attributes(node: Any) -> dict[str, str]:
    """The direct attributes of a trace or event; a nested or repeated attribute is refused."""
    out: dict[str, str] = {}
    for child in node:
        tag = local(child.tag)
        if tag == "event":
            continue
        if tag not in _VALUE_TAGS or len(child):
            raise ValueError("unsupported nested XES attribute; map it explicitly")
        key = child.attrib["key"]
        if key in out:
            raise ValueError(f"duplicate XES key {key}")
        out[key] = child.attrib.get("value", "")
    return out


def read_events(path: str | Path, cfg: dict[str, Any], *, digest: str | None = None) -> pd.DataFrame:
    """One row per event of the verified incident log, with the fields the criteria read."""
    path = Path(path)
    if (digest or sha256(path)) != cfg["expected"]["sha256"]:
        raise ValueError("the file does not have the checksum of the audited BPI Challenge 2013 incident log")
    mapping = cfg["field_mapping"]
    rows = []
    cases: set[str] = set()
    for trace in iter_traces(path):
        case_id = _attributes(trace).get("concept:name")
        if not case_id:
            raise ValueError("a trace has no case identifier")
        if case_id in cases:
            raise ValueError("duplicate trace identifiers are never merged silently")
        cases.add(case_id)
        position = -1
        for position, event in enumerate(e for e in trace if local(e.tag) == "event"):
            a = _attributes(event)
            rows.append(
                {
                    "case_id": case_id,
                    "event_position": position,
                    "team": a.get(mapping["team"]),
                    "status": a.get(mapping["status"]),
                    "substatus": a.get(mapping["substatus"]),
                    "product": a.get(mapping["product"]),
                    "time": a.get("time:timestamp"),
                }
            )
        if position < 0:
            raise ValueError("a trace has no event")
    d = pd.DataFrame(rows)
    if len(cases) != cfg["expected"]["cases"] or len(d) != cfg["expected"]["events"]:
        raise ValueError("unexpected number of incidents or events")
    d["timestamp"] = pd.to_datetime(d["time"], format="ISO8601", utc=True, errors="coerce")
    return d.drop(columns="time")


def _usable(s: pd.Series, cfg: dict[str, Any]) -> pd.Series:
    return s.notna() & ~s.astype(str).str.strip().str.lower().isin(cfg["missing_markers"])


def _stable(s: pd.Series, cfg: dict[str, Any]) -> str:
    if not _usable(s, cfg).all():
        return str(cfg["missing_group_labels"]["missing"])
    return str(s.iloc[0]) if s.nunique() == 1 else str(cfg["missing_group_labels"]["multiple"])


def sequence_values(values: list[Any]) -> tuple[int, int]:
    """Changes and immediate A–B–A returns in a sequence after consecutive equal values are compressed."""
    compressed = [v for i, v in enumerate(values) if i == 0 or v != values[i - 1]]
    returns = sum(compressed[i] == compressed[i - 2] for i in range(2, len(compressed)))
    return max(0, len(compressed) - 1), returns


def features(d: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """One row per incident: the recorded quantities of the six criteria and their evidence states."""
    active_statuses = set(cfg["active_statuses"])
    rows = []
    for case_id, g in d.groupby("case_id", sort=True):
        valid = bool(g.timestamp.notna().all())
        g = g.sort_values(["timestamp", "event_position"], kind="stable", na_position="last")

        def tied_differently(column: str, frame: pd.DataFrame = g) -> bool:
            return bool(
                any(z[column].drop_duplicates().shape[0] > 1 for _, z in frame.groupby("timestamp", dropna=False) if len(z) > 1)
            )

        team_ok = bool(_usable(g.team, cfg).all())
        sub_ok = bool(_usable(g.substatus, cfg).all())
        status_ok = bool(_usable(g.status, cfg).all())
        team_tie = tied_differently("team")
        status_tie = tied_differently("status")
        changes, returns = sequence_values(g.team.tolist()) if team_ok and valid and not team_tie else (np.nan, np.nan)
        state_team = (
            EVALUATED
            if team_ok and valid and not team_tie
            else "missing_team_value"
            if not team_ok
            else "invalid_timestamp"
            if not valid
            else "ambiguous_timestamp_tie"
        )
        active = np.nan
        if status_ok and valid and not status_tie:
            seen = False
            active = 0
            for status in g.status:
                if seen and status in active_statuses:
                    active = 1
                if status == cfg["completed_status"]:
                    seen = True
        span = (g.timestamp.max() - g.timestamp.min()).total_seconds() / 86400 if valid and len(g) >= 2 else np.nan
        rows.append(
            {
                "case_id": case_id,
                "n_events": len(g),
                "product_group": _stable(g["product"], cfg),
                "team_changes": changes,
                "team_returns": returns,
                "state_team": state_team,
                "repeated_substatus": len(g) - g.substatus.nunique() if sub_ok else np.nan,
                "wait_user_count": int(g.substatus.eq(cfg["wait_user_substatus"]).sum()) if sub_ok else np.nan,
                "state_substatus": EVALUATED if sub_ok else "missing_substatus",
                "span_days": span,
                "state_span": EVALUATED if np.isfinite(span) else "invalid_timestamp" if not valid else "insufficient_endpoints",
                "post_completed_active": active,
                "state_active": EVALUATED
                if np.isfinite(active)
                else "missing_status"
                if not status_ok
                else "invalid_timestamp"
                if not valid
                else "ambiguous_timestamp_tie",
            }
        )
    return pd.DataFrame(rows).set_index("case_id")


_STATE_OF = {
    "C01": "state_team",
    "C02": "state_team",
    "C03": "state_substatus",
    "C04": "state_substatus",
    "C05": "state_span",
    "C06": "state_active",
}


def assessment_matrices(f: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Deviation values ``r(x; t, b) = min{1, max{0, (x − t)/b}}``, scope, evidence states and recorded quantities."""
    ids = [c["id"] for c in cfg["criteria"]]
    V = pd.DataFrame(np.nan, index=f.index, columns=ids)
    scope = pd.DataFrame(True, index=f.index, columns=ids)
    state = pd.DataFrame("", index=f.index, columns=ids)
    raw = pd.DataFrame(index=f.index)
    for c in cfg["criteria"]:
        cid = c["id"]
        raw[cid] = f[c["feature"]].astype(float)
        state[cid] = f[_STATE_OF[cid]]
        V[cid] = ((raw[cid] - c["threshold"]) / c["width"]).clip(0, 1)
    return V, scope, state, raw


def weights_for(cfg: dict[str, Any], view: str) -> dict[str, float]:
    """Raw weight per criterion under a view: the multiplier of the criterion's layer."""
    return {c["id"]: float(cfg["views"][view][c["layer"]]) for c in cfg["criteria"]}


def assess(path: str | Path) -> Assessment:
    """Read the verified incident log and prepare the assessment of all incidents."""
    cfg = configuration("bpic2013")
    path = Path(path)
    digest = sha256(path)
    events = read_events(path, cfg, digest=digest)
    f = features(events, cfg)
    severity, scope, state, raw = assessment_matrices(f, cfg)
    source = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "events": len(events),
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
        groups=f["product_group"].rename("group"),
        layers={c["id"]: c["layer"] for c in cfg["criteria"]},
        views={view: weights_for(cfg, view) for view in cfg["views"]},
        source=source,
    )
