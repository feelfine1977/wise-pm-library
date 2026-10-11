"""Domain adapters: one module per application of the paper, each with its configuration file.

An adapter interprets the source records of one public log and produces an
:class:`Assessment`: for every case and criterion a deviation value in
``[0, 1]``, a business-scope flag and an evidence state, together with the
case features the values were derived from and the group of every case. In
the terms of Section 4.2 of the paper, it supplies bounded case-level
assessment functions with their business scope, input evidence, calculation
and treatment of missing observations. It does not score: scoring and
prioritisation are done by the library on these prepared assessments
(:mod:`wise.evaluation.native`).

The criteria, thresholds, scope and evidence rules and view weights of an
application are in its configuration file beside the module (``bpic2019.json``,
``bpic2013.json``, ``bpic2017.json``). They are illustrative choices made by
the researchers, not elicited organisational policies.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import pandas as pd

__all__ = ["EVALUATED", "OUT_OF_SCOPE", "Assessment", "configuration"]

EVALUATED = "evaluated"
OUT_OF_SCOPE = "out_of_scope"


def configuration(name: str) -> dict[str, Any]:
    """The configuration file of an adapter (``"bpic2019"``, ``"bpic2013"``, ``"bpic2017"``)."""
    text = resources.files(__package__).joinpath(f"{name}.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


@dataclass(frozen=True, eq=False)
class Assessment:
    """What a domain adapter prepares for scoring.

    Attributes
    ----------
    application
        ``"bpic2019"``, ``"bpic2013_incidents"`` or ``"bpic2017"``.
    configuration
        The adapter configuration the assessment was made with.
    features
        One row per case (index = case id): the recorded quantities the
        criteria are computed from and the context attributes of the case.
    severity
        Cases × criteria: the deviation value in ``[0, 1]``; missing where
        the criterion is out of scope or has no usable evidence.
    in_scope
        Cases × criteria, boolean: the criterion is in business scope.
    state
        Cases × criteria: ``"evaluated"``, ``"out_of_scope"`` or the reason
        the evidence is unavailable.
    raw
        Cases × criteria: the recorded quantity behind each deviation value.
    groups
        The investigation group of every case (the primary slicing).
    layers
        Criterion → layer.
    views
        View → criterion → raw weight.
    source
        Identity of the input: file name, size, checksum, counts.
    """

    application: str
    configuration: Mapping[str, Any]
    features: pd.DataFrame
    severity: pd.DataFrame
    in_scope: pd.DataFrame
    state: pd.DataFrame
    raw: pd.DataFrame
    groups: pd.Series
    layers: Mapping[str, str]
    views: Mapping[str, Mapping[str, float]]
    source: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        index = self.severity.index
        if not index.is_unique:
            raise ValueError("an assessment needs unique case identifiers")
        for name in ("features", "in_scope", "state", "raw", "groups"):
            if not getattr(self, name).index.equals(index):
                raise ValueError(f"{name} must have exactly the case index of the severities")
        if not self.in_scope.columns.equals(self.severity.columns) or not self.state.columns.equals(self.severity.columns):
            raise ValueError("scope and state must have exactly the criteria of the severities")
        if not self.severity.notna().equals(self.state.eq(EVALUATED)):
            raise ValueError("a severity must be present exactly where the state is 'evaluated'")
        if (self.severity.notna() & ~self.in_scope).any().any():
            raise ValueError("an out-of-scope severity must be missing, not zero")

    @property
    def criteria(self) -> list[str]:
        return list(self.severity.columns)
