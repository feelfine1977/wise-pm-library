"""Staged BPIC'19 research profile over the audited purchase-to-pay export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data import sha256
from . import EVALUATED, OUT_OF_SCOPE, Assessment, bpic2019, configuration

APPLICATION = "bpic2019_staged"
CREATE = "Create Purchase Order Item"
DELETE = "Delete Purchase Order Item"
REVERSAL = "Cancel Goods Receipt"
MILESTONES = {
    key: bpic2019.ACTIVITY_SETS[key] for key in ("invoice", "receipt", "clear")
}
CHRONOLOGY_EXCLUSIONS = {
    REVERSAL, "Cancel Invoice Receipt", "Record Subsequent Invoice",
    "Cancel Subsequent Invoice", DELETE, "Vendor creates debit memo",
}
PENDING_CLEAR = "required_receipts_recorded_clearing_absent"


def _milestones(events: pd.DataFrame, features: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    start = pd.Timestamp(cfg["timing_plausibility_start"])
    end = pd.Timestamp(cfg["timing_plausibility_end_exclusive"])
    plausible = events.timestamp.ge(start) & events.timestamp.lt(end)
    creation = events.loc[events[bpic2019.ACT].eq(CREATE)].groupby(
        bpic2019.CASE, observed=True
    ).timestamp.min().reindex(features.index)
    creation = creation.where(creation.ge(start) & creation.lt(end))
    after_creation = events.timestamp.ge(events[bpic2019.CASE].map(creation))
    dated = events.loc[plausible & after_creation]
    markers = pd.DataFrame({"creation": creation})
    for name, labels in {**MILESTONES, "deletion": [DELETE]}.items():
        markers[name] = dated.loc[dated[bpic2019.ACT].isin(labels)].groupby(
            bpic2019.CASE, observed=True
        ).timestamp.min().reindex(features.index)
    return markers


def _completion(
    features: pd.DataFrame, markers: pd.DataFrame, cfg: dict[str, Any]
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    needs_receipt = features.flow.isin(["DF1", "DF2"])
    in_scope = features.flow.ne("Consignment")
    due = markers.creation + pd.Timedelta(days=cfg["horizon_days_from_creation"])
    boundary = pd.Timestamp(cfg["follow_up_boundary"])
    followed = due.le(boundary)
    invoice, receipt, clear = (markers[key].le(due) for key in ("invoice", "receipt", "clear"))
    has_required = invoice & (receipt | ~needs_receipt)
    chronology = clear & (~has_required | markers.clear.lt(markers.invoice) |
                          (needs_receipt & markers.clear.lt(markers.receipt)))
    unusable = ((features.n_invoice.gt(0) & markers.invoice.isna()) |
                (features.n_clear.gt(0) & markers.clear.isna()) |
                (needs_receipt & features.n_receipt.gt(0) & markers.receipt.isna()))
    reason = pd.Series(np.select(
        [~in_scope, markers.creation.isna(), ~followed, markers.deletion.le(due),
         unusable, chronology, clear, has_required, invoice, needs_receipt & receipt],
        [OUT_OF_SCOPE, "unusable_creation_timestamp", "insufficient_follow_up", "deletion_marker",
         "unusable_milestone_timestamp", "conflicting_clearing_chronology", "required_markers_recorded",
         PENDING_CLEAR, "invoice_recorded_required_receipt_absent", "goods_or_service_recorded_invoice_absent"],
        default="required_receipt_markers_absent",
    ), index=features.index)
    evaluable = reason.isin([
        "required_markers_recorded", PENDING_CLEAR, "invoice_recorded_required_receipt_absent",
        "goods_or_service_recorded_invoice_absent", "required_receipt_markers_absent",
    ])
    waiting = reason.eq(PENDING_CLEAR)
    later_marker = markers[["invoice", "receipt"]].max(axis=1, skipna=False).where(
        needs_receipt, markers.invoice
    )
    clearing_due = later_marker + pd.Timedelta(days=cfg["clearing_horizon_days_from_receipt_markers"])
    cleared_in_time = waiting & markers.clear.le(clearing_due) & markers.clear.le(boundary)
    insufficient_clearing_follow_up = waiting & ~cleared_in_time & clearing_due.gt(boundary)
    evaluable &= ~insufficient_clearing_follow_up
    timely = reason.eq("required_markers_recorded") | cleared_in_time
    assessment_reason = reason.mask(cleared_in_time, "cleared_within_post_receipt_horizon")
    assessment_reason = assessment_reason.mask(
        insufficient_clearing_follow_up, "insufficient_clearing_follow_up"
    )
    severity = (~timely).astype(float).where(evaluable)
    return severity, assessment_reason.mask(evaluable, EVALUATED), reason, assessment_reason


def prepare(
    events: pd.DataFrame, baseline: Assessment, *, cfg: dict[str, Any] | None = None
) -> Assessment:
    """Prepare the revised norm from the same raw rows and baseline assessment."""
    cfg = configuration(APPLICATION) if cfg is None else cfg
    features = baseline.features.copy()
    markers = _milestones(events, features, baseline.configuration)
    completion, completion_state, stage, completion_reason = _completion(
        features, markers, cfg["completion"]
    )
    features["completion_stage"] = stage
    features["completion_assessment_reason"] = completion_reason
    features["completion_creation_at"] = markers.creation
    for name in ("invoice", "receipt", "clear"):
        features[f"staged_first_{name}_at"] = markers[name]

    three_way = features.flow.isin(["DF1", "DF2"])
    two_way = features.flow.eq("2-way")
    single = features.n_invoice.eq(1) & features.n_clear.eq(1) & (
        (three_way & features.n_receipt.eq(1)) | (two_way & features.n_receipt.eq(0))
    )
    anchor = markers[["invoice", "receipt"]].max(axis=1, skipna=False).where(three_way, markers.invoice)
    valid_lag = single & anchor.notna() & markers.clear.ge(anchor)
    days = (markers.clear - anchor).dt.total_seconds() / 86400
    features["post_required_receipts_days"] = days.where(valid_lag)

    goods_reversals = events.loc[events[bpic2019.ACT].eq(REVERSAL)].groupby(
        bpic2019.CASE, observed=True
    )["eventID"]
    features["goods_reversal_records"] = goods_reversals.size().reindex(features.index, fill_value=0)
    features["goods_reversal_event_ids"] = goods_reversals.agg("|".join).reindex(features.index)
    features["repeat_invoice_review"] = features.n_invoice.gt(1) & features.flow.ne("Consignment")
    excluded = events.loc[events[bpic2019.ACT].isin(CHRONOLOGY_EXCLUSIONS), bpic2019.CASE]
    clear_date = markers.clear.dt.normalize()
    chronology_review = (
        features.flow.eq("DF2") & single & ~features.index.isin(excluded) &
        clear_date.ge(markers.invoice.dt.normalize()) & clear_date.lt(markers.receipt.dt.normalize())
    )
    features["df2_clearing_before_receipt_review"] = chronology_review
    for name, labels in MILESTONES.items():
        rows = events.loc[events[bpic2019.CASE].isin(features.index[chronology_review]) &
                          events[bpic2019.ACT].isin(labels)]
        features[f"chronology_{name}_event_id"] = rows.set_index(bpic2019.CASE)["eventID"]


    retained = ["C05", "C06", "C07"]
    severity = baseline.severity[retained].copy()
    scope = baseline.in_scope[retained].copy()
    state = baseline.state[retained].copy()
    raw = baseline.raw[retained].copy()
    scope["S01"] = features.flow.ne("Consignment")
    scope["C04"] = scope["S01"]
    severity["S01"] = completion
    state["S01"] = completion_state
    raw["S01"] = completion

    rules = {rule["id"]: rule for rule in cfg["criteria"]}
    rule = rules["C04"]
    suppress = stage.eq(PENDING_CLEAR) & completion.eq(1) & valid_lag
    evaluated = valid_lag & ~suppress
    severity["C04"] = ((days - rule["threshold"]) / rule["width"]).clip(0, 1).where(evaluated)
    missing = features.n_invoice.eq(0) | features.n_clear.eq(0) | (
        three_way & features.n_receipt.eq(0)
    )
    state["C04"] = np.select(
        [~scope["C04"], suppress, evaluated, missing, ~single],
        [OUT_OF_SCOPE, "clearing_absence_already_assessed", EVALUATED, "missing_prerequisite",
         "single_milestone_evidence_required"],
        default="invalid_temporal_evidence",
    )
    raw["C04"] = features["post_required_receipts_days"]
    ids = list(rules)
    layers = {cid: rules[cid]["layer"] for cid in ids}
    return Assessment(
        application=APPLICATION, configuration=cfg, features=features,
        severity=severity[ids], in_scope=scope[ids], state=state[ids], raw=raw[ids],
        groups=baseline.groups, layers=layers,
        views={view: {cid: weights[layer] for cid, layer in layers.items()}
               for view, weights in cfg["views"].items()}, source=baseline.source,
    )


def assess_both(path: str | Path) -> tuple[Assessment, Assessment]:
    """Read and verify the source once, returning the frozen and staged profiles."""
    path = Path(path)
    digest = sha256(path)
    cfg = configuration(bpic2019.APPLICATION)
    events = bpic2019.read_events(path, cfg, digest=digest)
    baseline = bpic2019.assess_events(events, cfg, path, digest)
    return baseline, prepare(events, baseline)


def assess(path: str | Path) -> Assessment:
    """Read the audited export and prepare the staged research profile."""
    return assess_both(path)[1]
