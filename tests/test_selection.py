"""Applicability rules: grammar, parsing and three-valued evaluation."""

import pandas as pd
import pytest

from wise.errors import NormError
from wise.selection import AllOf, AnyOf, Compare, parse


def _cases():
    return pd.DataFrame(
        {"flow": ["DF1", "DF2", None, "DF1"], "amount": [500, 2000, 3000, None], "flag": [True, False, True, None]},
        index=pd.Index(list("abcd"), name="case"),
    )


def _evaluate(rule):
    """True, False or None (unknown) per case."""
    return [None if value is pd.NA else bool(value) for value in parse(rule).evaluate(_cases())]


def test_empty_rule_selects_every_case():
    assert parse(None).rule is None
    assert parse({}).document == {}
    assert _evaluate({}) == [True, True, True, True]


def test_short_form_is_membership_combined_with_and():
    selection = parse({"flow": ["DF1"], "amount": 500})
    assert isinstance(selection.rule, AllOf)
    assert selection.columns == ("flow", "amount")
    assert selection.document == {"flow": ["DF1"], "amount": [500]}
    assert _evaluate({"flow": ["DF1"], "amount": 500}) == [True, False, False, None]
    assert _evaluate({"flow": "DF1"}) == [True, False, None, True]  # a bare string is one value


def test_leaf_operators():
    assert _evaluate({"attr": "flow", "in": ["DF2", "DF3"]}) == [False, True, None, False]
    assert _evaluate({"attr": "flow", "eq": "DF1"}) == [True, False, None, True]
    assert _evaluate({"attr": "flag", "eq": True}) == [True, False, True, None]
    assert _evaluate({"attr": "amount", "gt": 2000}) == [False, False, True, None]
    assert _evaluate({"attr": "amount", "gte": 2000}) == [False, True, True, None]
    assert _evaluate({"attr": "amount", "lt": 2000}) == [True, False, False, None]
    assert _evaluate({"attr": "amount", "lte": 2000}) == [True, True, False, None]


def test_a_missing_attribute_is_unknown_and_combines_by_kleene_logic():
    both = {"all": [{"attr": "flow", "eq": "DF1"}, {"attr": "amount", "gte": 1000}]}
    assert _evaluate(both) == [False, False, None, None]  # a: amount too small; c, d: one part unknown, none false
    either = {"any": [{"attr": "flow", "eq": "DF1"}, {"attr": "amount", "gte": 1000}]}
    assert _evaluate(either) == [True, True, True, True]  # c: amount known and large; d: flow known and DF1
    neither = {"any": [{"attr": "flow", "eq": "DF9"}, {"attr": "amount", "gte": 9999}]}
    assert _evaluate(neither) == [False, False, None, None]
    nested = parse({"all": [{"any": [{"attr": "flow", "in": ["DF1"]}]}, {"attr": "flag", "eq": True}]})
    assert isinstance(nested.rule, AllOf) and isinstance(nested.rule.rules[0], AnyOf)
    assert nested.columns == ("flow", "flag")


def test_parsed_rules_are_read_only_documents():
    selection = parse({"attr": "flow", "in": ["DF1"]})
    assert selection.rule == Compare("flow", "in", ["DF1"])
    with pytest.raises(TypeError):
        selection.document["attr"] = "other"
    with pytest.raises(TypeError):
        selection.rule.value.append("DF2")


@pytest.mark.parametrize(
    "rule",
    [
        ["flow"],
        {"flow": []},
        {"attr": "flow"},
        {"attr": "flow", "in": ["a"], "eq": "a"},
        {"attr": "flow", "regex": "D.*"},
        {"all": []},
        {"all": [{"attr": "flow", "eq": "a"}], "any": [{"attr": "flow", "eq": "b"}]},
        {"all": "flow"},
        {"not": {"attr": "flow", "eq": "DF1"}},
        {"attr": "flow", "ne": "DF1"},
        {"attr": "flow", "not_in": ["DF1"]},
        {"has": ["GR"]},
        {"lacks": ["GR"]},
    ],
)
def test_malformed_or_unsupported_rules_are_refused(rule):
    with pytest.raises(NormError):
        parse(rule, what="applicability")


def test_unknown_attribute_is_refused_on_evaluation():
    with pytest.raises(NormError, match="missing from the case table"):
        parse({"attr": "nope", "eq": 1}).evaluate(_cases())
