"""Prepared assessments scored by the library: the carrier log and the native norm (paper Sections 4.2 and 5.6).

A domain adapter produces, for every case and criterion, a deviation value in
``[0, 1]``, a business-scope flag and an evidence state. This module loads
such a prepared assessment through the public scoring and prioritisation
interfaces of :mod:`wise`:

* each prepared deviation value becomes a numeric case attribute and is
  preserved by an identity :class:`~wise.Metric` constraint with threshold
  zero and width one;
* each scope flag becomes the applicability of that constraint, so a
  criterion outside business scope stays outside it, and a missing value
  inside scope stays unavailable;
* the carrier log has one assessment record per case and a placeholder
  timestamp. It transports case attributes; it does not reconstruct the
  original process trace.

The norm built here for an application is also shipped as a serialised file
(``norms/native/<application>.json``); :func:`native_norm` loads the file and
:func:`replay` checks that it is the norm of the adapter's configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

import wise

from .adapters import Assessment

__all__ = [
    "GROUP",
    "SCOPE_PREFIX",
    "VALUE_PREFIX",
    "carrier_log",
    "native_norm",
    "norm_from_assessment",
    "prepare_native",
    "replay",
]

GROUP = "assessment_group"
VALUE_PREFIX = "assessment_value__"
SCOPE_PREFIX = "assessment_scope__"
_DESCRIPTION = "Identity mapping of an externally evaluated bounded severity; source evidence remains with the adapter."


def prepare_native(
    severity: pd.DataFrame,
    in_scope: pd.DataFrame,
    layers: Mapping[str, str],
    views: Mapping[str, Mapping[str, float]],
    groups: pd.Series,
    *,
    name: str,
    version: str = "1",
    mode: str = "flat",
    attributes: pd.DataFrame | None = None,
    metadata: Mapping[str, object] | None = None,
) -> tuple[wise.EventLog, wise.Norm, pd.DataFrame]:
    """Return a carrier log, a serialisable norm and the prepared case attributes.

    Missing severity inside scope remains unavailable. Finite severity outside
    scope is rejected. Views contain raw per-criterion weights, not layer
    totals. ``attributes`` adds further case attributes to the carrier (other
    groupings of the same cases).
    """
    if severity.empty or not severity.index.is_unique or not severity.columns.is_unique:
        raise ValueError("severity requires non-empty unique case and criterion indices")
    if not severity.index.equals(in_scope.index) or not severity.columns.equals(in_scope.columns):
        raise ValueError("scope must have exactly the severity index and column order")
    if in_scope.isna().any().any() or not all(pd.api.types.is_bool_dtype(d) for d in in_scope.dtypes):
        raise ValueError("scope must be boolean without missing values")
    if not groups.index.equals(severity.index):
        raise ValueError("group index must exactly match assessments")
    if set(layers) != set(severity):
        raise ValueError("every criterion needs exactly one layer")
    if any(not isinstance(c, str) or not c for c in severity):
        raise ValueError("criterion ids must be non-empty strings")
    if any(not isinstance(layer, str) or not layer for layer in layers.values()):
        raise ValueError("layer ids must be non-empty strings")
    a = severity.to_numpy(dtype=float)
    if np.isinf(a).any() or ((a < 0) | (a > 1)).any():
        raise ValueError("finite severity must be in [0, 1]")
    if (severity.notna() & ~in_scope).any().any():
        raise ValueError("out-of-scope severity must be missing, not zero")
    for view, w in views.items():
        if set(w) != set(severity):
            raise ValueError(f"view {view} must name every criterion")
        x = np.array([w[c] for c in severity], float)
        if not np.isfinite(x).all() or (x < 0).any() or not (x > 0).any():
            raise ValueError("each view needs finite non-negative weights and positive mass")
    cases = pd.DataFrame(index=severity.index.copy())
    cases.index.name = "case_id"
    cases[GROUP] = groups
    if attributes is not None:
        if not attributes.index.equals(severity.index):
            raise ValueError("further attributes must have exactly the case index of the assessments")
        for column in attributes:
            cases[str(column)] = attributes[column]
    entries = []
    for cid in severity:
        value = f"{VALUE_PREFIX}{cid}"
        scope = f"{SCOPE_PREFIX}{cid}"
        cases[value] = severity[cid].astype(float)
        cases[scope] = in_scope[cid].astype(bool)
        entries.append(
            wise.NormConstraint(
                cid,
                layers[cid],
                wise.Metric(value, threshold=0, width=1),
                applicability={"attr": scope, "eq": True},
                description=_DESCRIPTION,
            )
        )
    norm = wise.Norm(
        tuple(entries),
        tuple(wise.Layer(layer) for layer in dict.fromkeys(layers[c] for c in severity)),
        tuple(wise.View(v, constraint_weights={c: float(w[c]) for c in severity}) for v, w in views.items()),
        name=name,
        version=version,
        scoring_mode=mode,
        description="Prepared-assessment norm: identity metric constraints preserve the declared severities and scope.",
        metadata={
            "input_kind": "prepared_assessment_matrix",
            "carrier": "One non-process assessment record per case; source traces are separate.",
            "raw_operator_equivalence_claimed": False,
            **dict(metadata or {}),
        },
    )
    return carrier_log(cases), norm, cases


def carrier_log(cases: pd.DataFrame) -> wise.EventLog:
    """The carrier log of prepared case attributes: one assessment record per case, placeholder timestamp."""
    if not cases.index.is_unique:
        raise ValueError("case identifiers must be unique")
    ev = cases.copy()
    ev["case_id"] = cases.index
    ev["activity"] = "prepared assessment"
    ev["timestamp"] = pd.Timestamp("1970-01-01")
    return wise.EventLog(
        ev, case_col="case_id", activity_col="activity", timestamp_col="timestamp", case_attributes=list(cases.columns)
    )


def norm_from_assessment(assessment: Assessment, *, attributes: pd.DataFrame | None = None) -> tuple[wise.EventLog, wise.Norm, pd.DataFrame]:
    """The carrier log and the native norm of an adapter's assessment.

    The norm carries the identifier and version of the adapter configuration
    and names the configuration file that holds the criteria definitions.
    """
    cfg = assessment.configuration
    return prepare_native(
        assessment.severity,
        assessment.in_scope,
        assessment.layers,
        assessment.views,
        assessment.groups.rename(GROUP),
        name=str(cfg["id"]),
        version=str(cfg.get("version", "1")),
        mode="flat",
        attributes=attributes,
        metadata={
            "application": assessment.application,
            "criteria_defined_in": f"adapters/{_configuration_name(assessment.application)}.json",
        },
    )


def _configuration_name(application: str) -> str:
    return "bpic2013" if application == "bpic2013_incidents" else application


def native_norm(application: str) -> wise.Norm:
    """The serialised native norm of an application (``norms/native/<application>.json``), loaded by the library."""
    source = resources.files(__package__).joinpath("norms", "native", f"{application}.json")
    return wise.Norm.loads(source.read_text(encoding="utf-8"))


def replay(assessment: Assessment, *, attributes: pd.DataFrame | None = None, mode: str | None = None) -> wise.ScoreResult:
    """Score a prepared assessment with the shipped native norm of its application.

    The norm file is loaded with :meth:`wise.Norm.loads`; it must have the
    fingerprint of the norm that the adapter's configuration defines, so a
    configuration and a norm file that drifted apart are refused.
    """
    log, built, _ = norm_from_assessment(assessment, attributes=attributes)
    norm = native_norm(assessment.application)
    if norm.fingerprint() != built.fingerprint():
        raise ValueError(
            f"the native norm file of {assessment.application!r} is not the norm of its adapter configuration; "
            "regenerate it with python -m wise.evaluation.replay --write-norms"
        )
    return wise.score(log, norm, mode=mode)


def write_norm(norm: wise.Norm, directory: str | Path, application: str) -> Path:
    """Write a native norm file and return its path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return norm.dump(directory / f"{application}.json")
