"""The norm model, its structural checks and its document format."""

import json

import pandas as pd
import pytest
from _support.builders import make_log

import wise
from wise import norm_document
from wise.errors import NormError


def _norm(**kwargs):
    return wise.Norm(
        [
            wise.NormConstraint("p", "L1", wise.Presence("INV"), weight=1.0),
            wise.NormConstraint("l", "L2", wise.Lag("GR", "INV", delta=5, width=10), weight=3.0),
            wise.NormConstraint("s", "L2", wise.Singularity("GR", k=1, K=2), weight=1.0, applicability={"flow_type": ["DF1"]}),
        ],
        [wise.Layer("L1", "First"), wise.Layer("L2", "Second")],
        [wise.View("Layers", layer_weights={"L1": 0.2, "L2": 0.8}), wise.View("Direct", constraint_weights={"p": 1, "l": 2})],
        **kwargs,
    )


def test_lookups_and_weights():
    norm = _norm()
    assert norm.constraint_ids == ["p", "l", "s"]
    assert norm.layer_ids == ["L1", "L2"]
    assert norm.view_names == ["Layers", "Direct"]
    assert norm.layer_of.to_dict() == {"p": "L1", "l": "L2", "s": "L2"}
    assert norm.get_constraint("l").type == "lag"
    assert [c.id for c in norm.constraints_in_layer("L2")] == ["l", "s"]
    # two-stage weights: w_c = a_λ · b_c / Σ b
    assert norm.raw_weights("Layers") == pytest.approx({"p": 0.2, "l": 0.6, "s": 0.2})
    # direct weights: a constraint that the view does not name has weight zero
    assert norm.raw_weights("Direct") == {"p": 1.0, "l": 2.0, "s": 0.0}
    assert norm.weight_vector("Direct").tolist() == [1.0, 2.0, 0.0]
    assert norm.layer_weight_table().loc["L2", "Layers"] == pytest.approx(0.8)
    assert norm.weight_table().loc["s", "layer"] == "L2"
    assert norm.activities() == ["GR", "INV"]
    assert norm.attributes() == ["flow_type"]
    assert norm.describe().loc["s", "applicability"] == {"flow_type": ["DF1"]}
    with pytest.raises(NormError):
        norm.get_view("nope")
    with pytest.raises(NormError):
        norm.get_constraint("nope")


@pytest.mark.paper
def test_flat_is_the_default_scoring_mode():
    assert _norm().scoring_mode == "flat"
    assert wise.SCORING_MODES == ("flat", "layer_balanced")
    assert _norm(scoring_mode="layer_balanced").scoring_mode == "layer_balanced"
    with pytest.raises(NormError, match="scoring_mode"):
        _norm(scoring_mode="magic")


def test_structure_is_checked_on_construction():
    p = wise.NormConstraint("p", "L1", wise.Presence("INV"))
    layer, view = wise.Layer("L1"), wise.View("v", constraint_weights={"p": 1})
    with pytest.raises(NormError, match="duplicate constraint ids"):
        wise.Norm([p, p], [layer], [view])
    with pytest.raises(NormError, match="at least one constraint"):
        wise.Norm([], [layer], [view])
    with pytest.raises(NormError, match="unknown layer"):
        wise.Norm([p], [wise.Layer("other")], [view])
    with pytest.raises(NormError, match="duplicate layer ids"):
        wise.Norm([p], [layer, layer], [view])
    with pytest.raises(NormError, match="at least one view"):
        wise.Norm([p], [layer], [])
    with pytest.raises(NormError, match="duplicate view names"):
        wise.Norm([p], [layer], [view, view])
    with pytest.raises(NormError, match="unknown constraints"):
        wise.Norm([p], [layer], [wise.View("v", constraint_weights={"zzz": 1})])
    with pytest.raises(NormError, match="unknown layers"):
        wise.Norm([p], [layer], [wise.View("v", layer_weights={"zzz": 1})])
    with pytest.raises(NormError, match="all constraint weights are zero"):
        wise.Norm([p], [layer], [wise.View("v", constraint_weights={"p": 0})])
    for bad in (
        lambda: wise.View("v"),
        lambda: wise.View("v", layer_weights={"L1": 1}, constraint_weights={"p": 1}),
        lambda: wise.View("v", constraint_weights={"p": -1}),
        lambda: wise.View("v", constraint_weights={"p": "heavy"}),
        lambda: wise.View("v", constraint_weights={}),
        lambda: wise.View("", constraint_weights={"p": 1}),
        lambda: wise.Layer(""),
        lambda: wise.NormConstraint("", "L1", wise.Presence("INV")),
        lambda: wise.NormConstraint("p", "L1", "presence"),
        lambda: wise.NormConstraint("p", "L1", wise.Presence("INV"), weight=-1),
        lambda: wise.NormConstraint("p", "L1", wise.Presence("INV"), applicability={"attr": "x"}),
    ):
        with pytest.raises(NormError):
            bad()


def test_a_norm_cannot_be_changed_after_it_is_built():
    weights = {"p": 1.0, "l": 2.0}
    view = wise.View("Direct", constraint_weights=weights)
    weights["p"] = 99.0
    assert view.constraint_weights["p"] == 1.0  # inputs are copied
    norm = _norm(metadata={"owner": {"team": "audit"}})
    with pytest.raises(TypeError):
        norm.get_view("Direct").constraint_weights["p"] = 5.0
    with pytest.raises(TypeError):
        norm.get_constraint("s").applicability["flow_type"].append("DF2")
    with pytest.raises(TypeError):
        norm.metadata["owner"]["team"] = "other"
    layer_of = norm.layer_of
    layer_of["p"] = "L2"
    assert norm.layer_of["p"] == "L1"
    with pytest.raises(AttributeError):
        norm.name = "other"
    changed = norm.replace_constraint("s", applicability={})
    assert changed.get_constraint("s").applicability == {}
    assert norm.get_constraint("s").applicability == {"flow_type": ["DF1"]}
    assert norm.replace(name="renamed").name == "renamed"
    assert norm.map_constraints(lambda c: c.replace(weight=2.0)).get_constraint("p").weight == 2.0


def test_check_against_a_log_reports_without_raising():
    log = make_log([("a", "GR", 0, 1, "DF1")], attrs=())
    issues = _norm().check(log)
    assert any("activity 'INV' never occurs" in i for i in issues)
    assert any("applicability attribute 'flow_type' is not a case attribute" in i for i in issues)
    balance = wise.Norm(
        [wise.NormConstraint("b", "L", wise.Balance("net", "INV", "amount", "GR")), wise.NormConstraint("m", "L", wise.Metric("touches"))],
        [wise.Layer("L")],
        [wise.View("v", constraint_weights={"b": 1, "m": 1})],
    )
    issues = balance.check(log)
    assert any("'net' is not an event column" in i for i in issues)
    assert any("'touches' is not a case attribute" in i for i in issues)
    assert wise.running_p2p_norm().check(wise.running_p2p_log()) == []


# ----------------------------------------------------------------------------- document format
def test_document_round_trip_and_layout(tmp_path):
    norm = _norm(name="demo", version="3", description="d", metadata={"note": "free text"}, scoring_mode="layer_balanced")
    document = norm.to_dict()
    assert list(document) == [
        "schema_version", "name", "version", "description", "scoring_mode", "missing_values", "metadata", "layers", "views", "constraints",
    ]  # fmt: skip
    assert document["schema_version"] == wise.SCHEMA_VERSION == 3
    assert document["missing_values"] == "three_valued"
    assert document["constraints"][1]["params"] == {
        "a": ["GR"], "b": ["INV"], "delta": 5.0, "width": 10.0, "unit": "D", "missing_a": "violate", "missing_b": "violate",
    }  # fmt: skip
    again = wise.Norm.from_dict(document)
    assert again == norm
    assert again.scoring_mode == "layer_balanced"
    path = norm.dump(tmp_path / "norm.json")
    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert wise.Norm.load(path) == norm
    assert wise.Norm.loads(norm.dumps()) == norm
    assert json.loads(text) == document
    document["views"][0]["layer_weights"]["L1"] = 0.9  # the document is independent of the norm
    assert norm.get_view("Layers").layer_weights["L1"] == 0.2


def test_fingerprint_covers_what_the_norm_measures_not_its_notes():
    norm = _norm()
    assert norm.fingerprint() == _norm(description="other words", metadata={"x": 1}).fingerprint()
    assert norm.fingerprint() == norm.replace_constraint("p", description="note").fingerprint()
    assert norm.fingerprint() != norm.replace_constraint("p", weight=2.0).fingerprint()
    assert norm.fingerprint() != norm.replace(scoring_mode="layer_balanced").fingerprint()
    assert norm.fingerprint() != norm.replace(name="other").fingerprint()
    assert len(norm.fingerprint()) == 64


def test_documents_of_other_formats_are_refused():
    document = _norm().to_dict()
    for change, message in [
        ({"schema_version": 2}, "not supported"),
        ({"schema_version": 4}, "not supported"),
        ({"schema_version": True}, "not an integer"),
        ({"schema_version": "three"}, "not an integer"),
        ({"missing_values": "legacy"}, "missing_values"),
        ({"derived_attributes": [{"name": "x", "kind": "count", "activities": ["GR"]}]}, "derived attributes"),
        ({"bogus": 1}, "unknown top-level keys"),
    ]:
        with pytest.raises(NormError, match=message):
            wise.Norm.from_dict({**document, **change})
    for key in ("schema_version", "missing_values"):
        with pytest.raises(NormError, match=key):
            wise.Norm.from_dict({k: v for k, v in document.items() if k != key})
    assert wise.Norm.from_dict({**document, "schema_version": "3", "derived_attributes": []}) == _norm()
    with pytest.raises(NormError, match="not valid JSON"):
        wise.Norm.loads("{not json")
    with pytest.raises(NormError, match="mapping"):
        wise.Norm.from_dict([1, 2])


def test_malformed_entries_are_refused_with_the_entry_named():
    document = _norm().to_dict()

    def with_constraint(**change):
        entry = {**document["constraints"][0], **change}
        return {**document, "constraints": [entry, *document["constraints"][1:]]}

    with pytest.raises(NormError, match="constraint 'p'.*unknown keys"):
        wise.Norm.from_dict(with_constraint(bogus=1))
    with pytest.raises(NormError, match="unknown constraint type"):
        wise.Norm.from_dict(with_constraint(type="precedence"))
    with pytest.raises(NormError, match="constraint 'p'.*unknown parameters"):
        wise.Norm.from_dict(with_constraint(params={"activity": "INV", "after": "GR", "x": 1}))
    no_type = {k: v for k, v in document["constraints"][0].items() if k != "type"}
    with pytest.raises(NormError, match="missing 'type'"):
        wise.Norm.from_dict({**document, "constraints": [no_type]})
    with pytest.raises(NormError, match="view 'Layers': unknown keys"):
        wise.Norm.from_dict({**document, "views": [{**document["views"][0], "bogus": 1}]})
    with pytest.raises(NormError, match="malformed norm"):
        wise.Norm.from_dict({**document, "views": [{"description": "no name"}]})


def test_layers_and_views_may_be_given_as_mappings_and_layers_may_be_implied():
    document = _norm().to_dict()
    compact = {
        **document,
        "layers": {"L1": "First", "L2": {"name": "Second"}},
        "views": {"Layers": {"layer_weights": {"L1": 0.2, "L2": 0.8}}, "Direct": {"constraint_weights": {"p": 1, "l": 2}}},
    }
    assert wise.Norm.from_dict(compact).fingerprint() == _norm().fingerprint()
    implied = wise.Norm.from_dict({k: v for k, v in document.items() if k != "layers"})
    assert implied.layer_ids == ["L1", "L2"]


def test_metadata_must_be_serialisable():
    norm = _norm(metadata={"when": pd.Timestamp("2026-10-01"), "counts": (1, 2)})
    assert json.loads(norm.dumps())["metadata"] == {"when": "2026-10-01T00:00:00", "counts": [1, 2]}
    with pytest.raises(NormError, match="cannot be serialised"):
        _norm(metadata={"x": object()}).dumps()
    assert norm_document.identity(norm.to_dict()).get("metadata") is None


def test_running_example_norm_matches_table_3():
    norm = wise.running_p2p_norm()
    assert [c.type for c in norm.constraints] == ["presence", "lag", "balance", "balance", "singularity", "exclusion"]
    assert [layer.name for layer in norm.layers] == [
        "Core completeness", "Receipt-to-invoice timing", "Match consistency", "Handling discipline", "Exception discipline",
    ]  # fmt: skip
    assert norm.raw_weights("Finance") == {"c1": 0.20, "c2": 0.45, "c3": 0.20, "c4": 0.05, "c5": 0.05, "c6": 0.10}
    assert norm.raw_weights("Logistics") == {"c1": 0.25, "c2": 0.15, "c3": 0.05, "c4": 0.25, "c5": 0.45, "c6": 0.10}
    assert norm.get_constraint("c2").constraint == wise.Lag("Record Goods Receipt", "Record Invoice Receipt", delta=10, width=20)
    c3, c4 = norm.get_constraint("c3").constraint, norm.get_constraint("c4").constraint
    assert (c3.tau, c3.width, c4.tau, c4.width) == (0.05, 0.20, 0.01, 0.02)
    c5 = norm.get_constraint("c5").constraint
    assert (c5.k, c5.K) == (2, 3.0)
    for view in ("Finance", "Logistics"):  # without c4 the weights of Table 3 sum to one
        weights = norm.raw_weights(view)
        assert sum(w for c, w in weights.items() if c != "c4") == pytest.approx(1.0)
    assert wise.Norm.loads(norm.dumps()) == norm
