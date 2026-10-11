"""The norm document format: a :class:`~wise.norm.Norm` as a JSON document and back.

A document is an object with the top-level keys ``schema_version``, ``name``,
``version``, ``description``, ``scoring_mode``, ``missing_values``,
``metadata``, ``layers``, ``views`` and ``constraints``. It names its format
in ``schema_version``, which is required and must be 3, and its missing-value
policy in ``missing_values``, which is required and must be
``"three_valued"`` (:mod:`wise.selection`). Layers and views may also be given
as mappings keyed by id and name; without ``layers`` the layers are those
named by the constraints, in order of first use. Unknown keys are refused so
that a typo cannot silently change the meaning of a norm.

The layout is schema version 3 of the full library ``wise-pm``. A version 3
document written by ``wise-pm`` is read when it uses only what this library
implements: its ``derived_attributes`` list must be empty, and the options of
a constraint that this library does not have must hold their default value.

The fingerprint of a norm is defined here, beside the format: the SHA-256 of
the canonical JSON (sorted keys, no whitespace) of the written document
without its free-form parts, the ``metadata`` and the descriptions. Two norms
that measure the same thing have the same fingerprint, whatever their notes
say.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._frozen import thaw
from ._json import jsonable
from .constraints import constraint_from_dict
from .errors import NormError
from .norm import DEFAULT_SCORING_MODE, SCHEMA_VERSION, Layer, Norm, NormConstraint, View
from .selection import THREE_VALUED

TOP_KEYS = frozenset(
    {
        "schema_version",
        "name",
        "version",
        "description",
        "scoring_mode",
        "missing_values",
        "metadata",
        "layers",
        "views",
        "constraints",
        "derived_attributes",
    }
)
VIEW_KEYS = frozenset({"name", "description", "layer_weights", "constraint_weights"})
CONSTRAINT_KEYS = frozenset({"id", "layer", "type", "params", "weight", "applicability", "description"})
#: Free-form text and annotations: written to the document, left out of its fingerprint.
FREE_FORM_KEYS = frozenset({"metadata", "description"})


# ----------------------------------------------------------------------------- read
def schema_version_of(document: Mapping[str, Any]) -> int:
    """The ``schema_version`` of a document; refused when absent, not an integer, or not the supported one."""
    if "schema_version" not in document:
        raise NormError(f"norm document has no 'schema_version'; this library reads schema version {SCHEMA_VERSION}")
    raw = document["schema_version"]
    if isinstance(raw, bool) or not isinstance(raw, int | str):
        raise NormError(f"norm schema_version {raw!r} is not an integer; supported: [{SCHEMA_VERSION}]")
    try:
        version = int(raw)
    except ValueError:
        raise NormError(f"norm schema_version {raw!r} is not an integer; supported: [{SCHEMA_VERSION}]") from None
    if version != SCHEMA_VERSION:
        raise NormError(
            f"norm schema_version {version} is not supported; this library reads schema version {SCHEMA_VERSION} "
            "(a document of an earlier version is migrated with the full library wise-pm)"
        )
    return version


def read(document: Mapping[str, Any]) -> Norm:
    """The norm a document describes. Malformed documents raise :class:`NormError`."""
    if not isinstance(document, Mapping):
        raise NormError(f"a norm must be a mapping, got {type(document).__name__}")
    schema_version_of(document)
    try:
        return _read(document)
    except NormError:
        raise
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        raise NormError(f"malformed norm: {exc}") from exc


def _read(document: Mapping[str, Any]) -> Norm:
    unknown = set(document) - TOP_KEYS
    if unknown:
        raise NormError(f"unknown top-level keys in norm: {sorted(unknown)}")
    if "missing_values" not in document:
        raise NormError(f"a norm document names its missing-value policy: 'missing_values': {THREE_VALUED!r}")
    if document["missing_values"] != THREE_VALUED:
        raise NormError(f"missing_values must be {THREE_VALUED!r}, got {document['missing_values']!r}")
    if document.get("derived_attributes"):
        raise NormError("this library has no derived attributes; the norm's 'derived_attributes' must be empty or absent")
    layers = tuple(_layers(document.get("layers", [])))
    views = tuple(_view(v) for v in _views(document.get("views", [])))
    constraints = tuple(_constraint(c) for c in document.get("constraints", []))
    if not layers:
        layers = tuple(Layer(id=lid) for lid in dict.fromkeys(c.layer for c in constraints))
    return Norm(
        constraints=constraints,
        layers=layers,
        views=views,
        name=str(document.get("name", "norm")),
        version=str(document.get("version", "1")),
        description=str(document.get("description", "")),
        scoring_mode=str(document.get("scoring_mode", DEFAULT_SCORING_MODE)),
        metadata=dict(document.get("metadata", {}) or {}),
    )


def _layers(raw: Any) -> list[Layer]:
    if isinstance(raw, Mapping):
        raw = [{"id": k, **(v if isinstance(v, Mapping) else {"name": str(v)})} for k, v in raw.items()]
    return [Layer(id=str(lay["id"]), name=str(lay.get("name", "")), description=str(lay.get("description", ""))) for lay in raw]


def _views(raw: Any) -> list[Any]:
    if isinstance(raw, Mapping):
        return [{"name": k, **v} for k, v in raw.items()]
    return list(raw)


def _view(v: Mapping[str, Any]) -> View:
    unknown = set(v) - VIEW_KEYS
    if unknown:
        raise NormError(f"view {v.get('name')!r}: unknown keys {sorted(unknown)}")
    return View(
        name=str(v["name"]),
        layer_weights=v.get("layer_weights"),
        constraint_weights=v.get("constraint_weights"),
        description=str(v.get("description", "")),
    )


def _constraint(c: Mapping[str, Any]) -> NormConstraint:
    unknown = set(c) - CONSTRAINT_KEYS
    if unknown:
        raise NormError(f"constraint {c.get('id')!r}: unknown keys {sorted(unknown)}; allowed {sorted(CONSTRAINT_KEYS)}")
    if "type" not in c:
        raise NormError(f"constraint {c.get('id')!r}: missing 'type'")
    if "layer" not in c:
        raise NormError(f"constraint {c.get('id')!r}: missing 'layer'")
    try:
        constraint = constraint_from_dict(str(c["type"]), c.get("params", {}) or {})
    except NormError as exc:
        raise NormError(f"constraint {c.get('id')!r}: {exc}") from exc
    return NormConstraint(
        id=str(c["id"]),
        layer=str(c["layer"]),
        constraint=constraint,
        weight=c.get("weight", 1.0),
        applicability=c.get("applicability", {}) or {},
        description=str(c.get("description", "")),
    )


# ----------------------------------------------------------------------------- write
def write(norm: Norm) -> dict[str, Any]:
    """The document of ``norm``: plain containers, independent of the norm."""
    return {
        "schema_version": SCHEMA_VERSION,
        "name": norm.name,
        "version": norm.version,
        "description": norm.description,
        "scoring_mode": norm.scoring_mode,
        "missing_values": THREE_VALUED,
        "metadata": jsonable(norm.metadata),
        "layers": [{"id": layer.id, "name": layer.name, "description": layer.description} for layer in norm.layers],
        "views": [
            {
                "name": v.name,
                "description": v.description,
                **({"layer_weights": dict(v.layer_weights)} if v.layer_weights is not None else {}),
                **({"constraint_weights": dict(v.constraint_weights)} if v.constraint_weights is not None else {}),
            }
            for v in norm.views
        ],
        "constraints": [write_constraint(c) for c in norm.constraints],
    }


def write_constraint(nc: NormConstraint) -> dict[str, Any]:
    """One entry of the ``constraints`` list."""
    return {
        "id": nc.id,
        "layer": nc.layer,
        "type": nc.constraint.type,
        "params": jsonable(nc.constraint.params()),
        "weight": nc.weight,
        "applicability": thaw(nc.applicability),
        "description": nc.description,
    }


def identity(document: Mapping[str, Any]) -> dict[str, Any]:
    """The part of a written document that defines what the norm measures: the document without the free-form
    ``metadata`` and the ``description`` of the norm, its layers, views and constraints."""
    out = {k: v for k, v in document.items() if k not in FREE_FORM_KEYS}
    for part in ("layers", "views", "constraints"):
        out[part] = [{k: v for k, v in entry.items() if k not in FREE_FORM_KEYS} for entry in document[part]]
    return out


# ----------------------------------------------------------------------------- text and files
def _json_default(obj: Any) -> Any:
    out = jsonable(obj)
    if out is obj:
        raise NormError(f"norm metadata holds a value of type {type(obj).__name__} that cannot be serialised to JSON")
    return out


def _parse_json(text: str, source: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise NormError(f"{source} is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc


def dumps(norm: Norm, indent: int = 2) -> str:
    """The document as JSON text."""
    return json.dumps(write(norm), indent=indent, ensure_ascii=False, default=_json_default)


def dump(norm: Norm, path: str | Path, indent: int = 2) -> Path:
    """Write the JSON text and a final newline to ``path``."""
    p = Path(path)
    p.write_text(dumps(norm, indent) + "\n", encoding="utf-8")
    return p


def loads(text: str, *, source: str = "norm text") -> Norm:
    """The norm of a JSON text."""
    return read(_parse_json(text, source))


def load(path: str | Path) -> Norm:
    """The norm of a JSON file."""
    p = Path(path)
    return loads(p.read_text(encoding="utf-8"), source=p.name)


# ----------------------------------------------------------------------------- fingerprint
def fingerprint(norm: Norm) -> str:
    """SHA-256 of the canonical JSON of the document without its free-form parts (metadata, descriptions)."""
    canonical = json.dumps(identity(write(norm)), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "dump",
    "dumps",
    "fingerprint",
    "identity",
    "load",
    "loads",
    "read",
    "schema_version_of",
    "write",
    "write_constraint",
]
