"""WISE — Weighted Insights for Evaluating Efficiency.

The method of the paper *WISE: Actionable Norm-Based Scoring for Process
Mining* (Jessen, Fahland, Zerbato): a process norm states expected execution
as constraints grouped into layers, views weight those constraints, cases are
scored from bounded violation signals, and slices of cases are ranked by the
Priority Index.

Typical use::

    import wise

    log = wise.EventLog(df, case_col="case", activity_col="activity",
                        timestamp_col="time", case_attributes=["company", "flow_type"])
    norm = wise.Norm.load("norm.json")
    result = wise.score(log, norm)                        # Phase 2: assess cases
    backlog = wise.prioritize(result, by=["company"],     # Phase 3: compare slices
                              view="Finance")
    explained = wise.layer_contributions(result, backlog)

The evaluation of the paper (the three applications of Section 5 and the
comparison with the printed values) is the subpackage :mod:`wise.evaluation`.
"""

from . import families as families
from ._version import __version__
from .backlog import TIE_POLICY, Backlog, BacklogSpec
from .constraints import (
    CONSTRAINT_TYPES,
    Balance,
    Constraint,
    Exclusion,
    Lag,
    Metric,
    Presence,
    Singularity,
    constraint_from_dict,
    sat,
)
from .datasets import illustrative_invoice_log, illustrative_invoice_norm, running_p2p_events, running_p2p_log, running_p2p_norm
from .errors import LogSchemaError, NormError, NotScoredError, WiseError
from .family import Evaluation
from .log import EventLog
from .norm import SCHEMA_VERSION, SCORING_MODES, Layer, Norm, NormConstraint, View
from .prioritization import MISSING_KEY, layer_contributions, layer_drivers, prioritize, top_k_overlap
from .scoring import ScoreResult, evaluate, evaluate_constraint, score, violation_matrix

__all__ = [
    "CONSTRAINT_TYPES",
    "MISSING_KEY",
    "SCHEMA_VERSION",
    "SCORING_MODES",
    "TIE_POLICY",
    "Backlog",
    "BacklogSpec",
    "Balance",
    "Constraint",
    "Evaluation",
    "EventLog",
    "Exclusion",
    "Lag",
    "Layer",
    "LogSchemaError",
    "Metric",
    "Norm",
    "NormConstraint",
    "NormError",
    "NotScoredError",
    "Presence",
    "ScoreResult",
    "Singularity",
    "View",
    "WiseError",
    "__version__",
    "constraint_from_dict",
    "evaluate",
    "evaluate_constraint",
    "illustrative_invoice_log",
    "illustrative_invoice_norm",
    "layer_contributions",
    "layer_drivers",
    "prioritize",
    "running_p2p_events",
    "running_p2p_log",
    "running_p2p_norm",
    "sat",
    "score",
    "top_k_overlap",
    "violation_matrix",
]
