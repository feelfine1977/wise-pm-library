"""Process norm ``N = (C, Λ, lay)``, views, and applicability (paper Section 4.3).

A :class:`Norm` holds the constraint catalogue, the layer partition, the
stakeholder views, per-constraint applicability rules and the scoring mode.
It is a versioned artefact: its objects are frozen, their inputs are copied on
construction into read-only containers (a value read from a norm cannot be
written into), and its structure is checked once, on construction.

This module holds the model only. The document format (reading and writing
JSON documents, the fingerprint) is :mod:`wise.norm_document`;
:meth:`Norm.load`, :meth:`Norm.dump` and the other serialisation methods
delegate to it.

Views
-----
A view ``p`` is a non-negative raw weight vector ``w_c^(p)`` over the shared
constraint set, given either directly (``constraint_weights``) or through the
optional two-stage rule ``w_c = a_λ · b_c / Σ_{d∈C_λ} b_d`` with
``layer_weights`` and each constraint's within-layer ``weight``. Only relative
magnitudes matter; scoring renormalises over the evaluated constraints of
each case.

Applicability
-------------
The business scope of a constraint is stated as a selection rule over the
case table (short form or rule form, see :mod:`wise.selection`). A case whose
rule reads a missing attribute has unknown scope and is not scored on the
constraint.

Scoring mode
------------
``"flat"`` (default) is the primary mode of the paper: the raw weights are
renormalised over the evaluated constraints. ``"layer_balanced"`` is the
optional mode of Section 4.4. The mode is recorded with the norm.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import pandas as pd

from ._frozen import freeze
from ._json import jsonable as _jsonable
from .constraints import Constraint
from .errors import NormError
from .family import Inputs, family_of
from .selection import Selection, parse

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from .log import EventLog

#: The schema version of the norm document format this library reads and writes.
SCHEMA_VERSION = 3
SCORING_MODES = ("flat", "layer_balanced")
DEFAULT_SCORING_MODE = "flat"


# ----------------------------------------------------------------------------- layers, views
@dataclass(frozen=True)
class Layer:
    """A business-facing group of constraints (``λ ∈ Λ``)."""

    id: str
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.id):
            raise NormError("layer id must be a non-empty string")
        object.__setattr__(self, "id", str(self.id))


@dataclass(frozen=True)
class View:
    """A stakeholder perspective: raw weights over the shared constraint set.

    Give exactly one of ``constraint_weights`` (``{constraint_id: w}``) or
    ``layer_weights`` (``{layer_id: a_λ}``, combined with the constraints'
    within-layer weights).
    """

    name: str
    layer_weights: dict[str, float] | None = None
    constraint_weights: dict[str, float] | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.name):
            raise NormError("view name must be a non-empty string")
        if (self.layer_weights is None) == (self.constraint_weights is None):
            raise NormError(f"view {self.name!r}: give exactly one of layer_weights or constraint_weights")
        which = "layer_weights" if self.layer_weights is not None else "constraint_weights"
        raw = getattr(self, which)
        clean: dict[str, float] = {}
        for k, v in dict(raw).items():
            try:
                fv = float(v)
            except (TypeError, ValueError) as exc:
                raise NormError(f"view {self.name!r}: weight {k}={v!r} is not numeric") from exc
            if not np.isfinite(fv) or fv < 0:
                raise NormError(f"view {self.name!r}: weight {k}={v!r} must be finite and >= 0")
            clean[str(k)] = fv
        if not clean:
            raise NormError(f"view {self.name!r}: {which} is empty")
        object.__setattr__(self, which, freeze(clean))

    @property
    def weights(self) -> dict[str, float]:
        return self.layer_weights if self.layer_weights is not None else self.constraint_weights  # type: ignore[return-value]


# ----------------------------------------------------------------------------- constraints
@dataclass(frozen=True)
class NormConstraint:
    """One catalogue entry: a constraint, its layer, within-layer weight, and applicability."""

    id: str
    layer: str
    constraint: Constraint
    weight: float = 1.0
    applicability: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    if TYPE_CHECKING:  # pragma: no cover
        _selection: ClassVar[Selection]  # set per instance in __post_init__, not a dataclass field

    def __post_init__(self) -> None:
        if not str(self.id):
            raise NormError("constraint id must be a non-empty string")
        object.__setattr__(self, "id", str(self.id))
        object.__setattr__(self, "layer", str(self.layer))
        if not isinstance(self.constraint, Constraint):
            raise NormError(f"constraint {self.id!r}: constraint must be a wise Constraint, got {type(self.constraint).__name__}")
        try:
            w = float(self.weight)
        except (TypeError, ValueError) as exc:
            raise NormError(f"constraint {self.id!r}: weight {self.weight!r} is not numeric") from exc
        if not np.isfinite(w) or w < 0:
            raise NormError(f"constraint {self.id!r}: within-layer weight must be finite and >= 0")
        object.__setattr__(self, "weight", w)
        selection = parse(self.applicability, what="applicability")
        object.__setattr__(self, "applicability", selection.document)
        object.__setattr__(self, "_selection", selection)

    def scope(self, cases: pd.DataFrame) -> pd.Series:
        """Nullable boolean Series over ``cases`` (one row per case): in scope, out of scope, ``<NA>`` unknown."""
        if not self.applicability:
            return pd.Series(True, index=cases.index, dtype="boolean")
        for attr in self._selection.columns:
            if attr not in cases.columns:
                raise NormError(
                    f"constraint {self.id!r} is conditioned on case attribute {attr!r}, which is missing from the case table"
                )
        return self._selection.evaluate(cases)

    def applies_to(self, cases: pd.DataFrame) -> pd.Series:
        """Boolean mask over ``cases``: the constraint is known to apply (a case of unknown scope is not in the mask)."""
        return self.scope(cases).fillna(False).astype(bool)

    def replace(self, **changes: Any) -> NormConstraint:
        """A copy with the given fields changed (constraints are immutable)."""
        return dataclasses.replace(self, **changes)

    @property
    def type(self) -> str:
        return self.constraint.type

    def to_dict(self) -> dict[str, Any]:
        """The constraint's entry in a norm document (:func:`wise.norm_document.write_constraint`)."""
        from . import norm_document

        return norm_document.write_constraint(self)


def _inputs(nc: NormConstraint) -> Inputs:
    """What a constraint reads from a log, as its family states it (applicability not included)."""
    needs: Inputs = family_of(nc.constraint).requires(nc.constraint)
    return needs


# ----------------------------------------------------------------------------- norm
@dataclass(frozen=True)
class Norm:
    """The versioned process norm: constraints, layers, views and the scoring mode."""

    constraints: tuple[NormConstraint, ...]
    layers: tuple[Layer, ...]
    views: tuple[View, ...]
    name: str = "norm"
    version: str = "1"
    description: str = ""
    scoring_mode: str = DEFAULT_SCORING_MODE
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "layers", tuple(self.layers))
        object.__setattr__(self, "views", tuple(self.views))
        object.__setattr__(self, "metadata", freeze(dict(self.metadata)))
        object.__setattr__(self, "version", str(self.version))
        _check_structure(self)

    # ------------------------------------------------------------ lookups
    @property
    def constraint_ids(self) -> list[str]:
        return [c.id for c in self.constraints]

    @property
    def layer_ids(self) -> list[str]:
        return [layer.id for layer in self.layers]

    @property
    def view_names(self) -> list[str]:
        return [v.name for v in self.views]

    @cached_property
    def _constraints_by_id(self) -> dict[str, NormConstraint]:
        return {c.id: c for c in self.constraints}

    @cached_property
    def _views_by_name(self) -> dict[str, View]:
        return {v.name: v for v in self.views}

    def get_view(self, name: str) -> View:
        try:
            return self._views_by_name[name]
        except KeyError:
            raise NormError(f"unknown view {name!r}; available: {self.view_names}") from None

    def get_constraint(self, cid: str) -> NormConstraint:
        try:
            return self._constraints_by_id[cid]
        except KeyError:
            raise NormError(f"unknown constraint {cid!r}") from None

    @cached_property
    def _layer_of(self) -> pd.Series:
        return pd.Series({c.id: c.layer for c in self.constraints}, name="layer", dtype=object)

    @property
    def layer_of(self) -> pd.Series:
        """``lay: C → Λ`` as a Series indexed by constraint id (a copy on every call)."""
        return self._layer_of.copy()

    def constraints_in_layer(self, layer_id: str) -> list[NormConstraint]:
        return [c for c in self.constraints if c.layer == layer_id]

    def activities(self) -> list[str]:
        acts: set[str] = set()
        for c in self.constraints:
            acts.update(_inputs(c).activities)
        return sorted(acts)

    def attributes(self) -> list[str]:
        """Case attributes referenced by applicability rules and read by constraints (e.g. Metric)."""
        attrs: set[str] = set()
        for c in self.constraints:
            attrs.update(c._selection.columns)
            attrs.update(_inputs(c).case_attributes)
        return sorted(attrs)

    # ---------------------------------------------------------- validation
    def check(self, log: EventLog) -> list[str]:
        """Check the norm against a log. Returns human-readable issues (empty
        list = fine); nothing is raised.

        Reports activities that never occur in the log, case attributes that
        are missing, and event columns that a constraint reads but the log
        lacks (e.g. balance attributes). What a constraint reads is stated by
        its family (:mod:`wise.family`).
        """
        issues: list[str] = []
        labels = set(log.activity_labels)
        case_columns = log.cases.columns
        event_columns = log.events.columns
        for c in self.constraints:
            needs = _inputs(c)
            for a in needs.activities:
                if a not in labels:
                    issues.append(f"constraint {c.id!r}: activity {a!r} never occurs in the log")
            for attr in c._selection.columns:
                if attr not in case_columns:
                    issues.append(f"constraint {c.id!r}: applicability attribute {attr!r} is not a case attribute")
            for attr in needs.case_attributes:
                if attr not in case_columns:
                    issues.append(f"constraint {c.id!r}: {c.type} attribute {attr!r} is not a case attribute")
            for attr in needs.event_columns:
                if attr not in event_columns:
                    issues.append(f"constraint {c.id!r}: {c.type} attribute {attr!r} is not an event column")
        return issues

    # ------------------------------------------------------------- weights
    def _raw_weights(self, v: View) -> dict[str, float]:
        if v.constraint_weights is not None:
            return {c.id: float(v.constraint_weights.get(c.id, 0.0)) for c in self.constraints}
        out: dict[str, float] = {}
        for layer in self.layer_ids:
            members = self.constraints_in_layer(layer)
            total_b = sum(c.weight for c in members)
            a = float(v.layer_weights.get(layer, 0.0))  # type: ignore[union-attr]
            for c in members:
                out[c.id] = a * ((c.weight / total_b) if total_b > 0 else 0.0)
        return out

    def raw_weights(self, view: str | View) -> dict[str, float]:
        """Raw constraint weights ``w_c^(p)`` for a view (paper Section 4.3)."""
        v = view if isinstance(view, View) else self.get_view(view)
        return self._raw_weights(v)

    def weight_vector(self, view: str | View) -> pd.Series:
        """Raw weights as a Series in constraint order."""
        w = self.raw_weights(view)
        return pd.Series(
            [w[c] for c in self.constraint_ids], index=self.constraint_ids, name=view if isinstance(view, str) else view.name
        )

    def weight_table(self) -> pd.DataFrame:
        """Constraints × views table of raw weights plus layer, for review."""
        tab = pd.DataFrame({v.name: self.raw_weights(v) for v in self.views}).reindex(self.constraint_ids)
        tab.insert(0, "layer", self.layer_of)
        tab.index.name = "constraint"
        return tab

    def layer_weight_table(self) -> pd.DataFrame:
        """Layers × views table of ``a_λ^(p)`` (sum of raw weights per layer)."""
        tab = self.weight_table()
        return tab.groupby("layer")[self.view_names].sum().reindex(self.layer_ids)

    # ---------------------------------------------------------- editing
    def replace(self, **changes: Any) -> Norm:
        """A copy of the norm with the given top-level fields changed."""
        return dataclasses.replace(self, **changes)

    def replace_constraint(self, cid: str, **changes: Any) -> Norm:
        """A copy with one constraint's fields changed (e.g. ``applicability={}``)."""
        self.get_constraint(cid)
        return self.replace(constraints=tuple(c.replace(**changes) if c.id == cid else c for c in self.constraints))

    def map_constraints(self, fn: Any) -> Norm:
        """A copy with every constraint replaced by ``fn(constraint)``."""
        return self.replace(constraints=tuple(fn(c) for c in self.constraints))

    # ----------------------------------------------------------- serialise
    # The document format lives in :mod:`wise.norm_document`; these methods delegate to it.
    def to_dict(self) -> dict[str, Any]:
        """The norm document (plain containers, independent of the norm)."""
        from . import norm_document

        return norm_document.write(self)

    def dumps(self, indent: int = 2) -> str:
        from . import norm_document

        return norm_document.dumps(self, indent)

    def dump(self, path: str | Path, indent: int = 2) -> Path:
        from . import norm_document

        return norm_document.dump(self, path, indent)

    @classmethod
    def loads(cls, text: str) -> Norm:
        from . import norm_document

        return norm_document.loads(text)

    @classmethod
    def load(cls, path: str | Path) -> Norm:
        from . import norm_document

        return norm_document.load(path)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Norm:
        """Build from a norm document, the dictionary form of :meth:`to_dict`.

        The document must give its ``schema_version``. Unknown keys and
        malformed structures raise :class:`NormError` so that a typo cannot
        silently change the meaning of a norm.
        """
        from . import norm_document

        return norm_document.read(d)

    def fingerprint(self) -> str:
        """SHA-256 of the norm's document without metadata and descriptions (:func:`wise.norm_document.fingerprint`)."""
        from . import norm_document

        return norm_document.fingerprint(self)

    def describe(self) -> pd.DataFrame:
        """One row per constraint: layer, type, params, weight, applicability."""
        rows = []
        for c in self.constraints:
            rows.append(
                {
                    "id": c.id,
                    "layer": c.layer,
                    "type": c.constraint.type,
                    "params": _jsonable(c.constraint.params()),
                    "weight": c.weight,
                    "applicability": c.applicability or "always",
                    "description": c.description,
                }
            )
        return pd.DataFrame(rows).set_index("id")

    def __repr__(self) -> str:
        return (
            f"Norm({self.name!r} v{self.version}: {len(self.constraints)} constraints, "
            f"{len(self.layers)} layers, views={self.view_names}, scoring_mode={self.scoring_mode!r})"
        )


def _check_structure(norm: Norm) -> None:
    """The structural check of a norm, run once on construction.

    Each layer, view and constraint checks its own fields when it is built; this checks what only the norm as a
    whole can: unique ids and names, references between constraints, layers and views, a non-zero weight in every
    view, and the scoring mode.
    """
    ids = norm.constraint_ids
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise NormError(f"duplicate constraint ids: {dup}")
    if not norm.constraints:
        raise NormError("a norm needs at least one constraint")
    for c in norm.constraints:
        if not isinstance(c, NormConstraint):
            raise NormError(f"a norm's constraints must be NormConstraint entries, got {type(c).__name__}")
    layer_ids = norm.layer_ids
    if len(set(layer_ids)) != len(layer_ids):
        raise NormError("duplicate layer ids")
    for c in norm.constraints:
        if c.layer not in layer_ids:
            raise NormError(f"constraint {c.id!r} refers to unknown layer {c.layer!r}; layers: {layer_ids}")
    names = norm.view_names
    if len(set(names)) != len(names):
        raise NormError("duplicate view names")
    if not norm.views:
        raise NormError("a norm needs at least one view")
    for v in norm.views:
        if v.layer_weights is not None:
            unknown = set(v.layer_weights) - set(layer_ids)
            if unknown:
                raise NormError(f"view {v.name!r}: unknown layers {sorted(unknown)}")
        else:
            unknown = set(v.constraint_weights or {}) - set(ids)
            if unknown:
                raise NormError(f"view {v.name!r}: unknown constraints {sorted(unknown)}")
        if not any(w > 0 for w in norm.raw_weights(v).values()):
            raise NormError(f"view {v.name!r}: all constraint weights are zero")
    if norm.scoring_mode not in SCORING_MODES:
        raise NormError(f"scoring_mode must be one of {SCORING_MODES}, got {norm.scoring_mode!r}")


__all__ = [
    "DEFAULT_SCORING_MODE",
    "SCHEMA_VERSION",
    "SCORING_MODES",
    "Layer",
    "Norm",
    "NormConstraint",
    "View",
]
