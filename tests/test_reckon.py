"""Telling an intended red from a new one.

A ledger with a permanent red cannot gate on red. Several in this estate ship red BY
DECISION — a debt is a red carried on purpose, and a gate that admits an ungrounded param
is a gate doing its job — so `exit 1 if any red` fails on every run the check will ever
have. quern's own `ledger-gate` had failed on every run in its recorded history when this
was written (issue #42), and the cost is not the noise: it is that nobody can distinguish
a newly-broken ledger from the usual one. The flight-recorder README shipped red on
2026-08-03 and stayed red for ten days because the new red arrived into noise.

So the question is not "is anything red" but "is anything red that nobody accounted for",
and the accounting is a note on the node that is red, naming the rule.

These tests pin the three answers `reckon` owes and the one property that keeps the note
from rotting into a standing licence.
"""

from __future__ import annotations

from quern import Quantity, Quern, Rule, expectations, reckon, run_rules, set_node

_RULE = "nothing-unsound-passes-a-gate"


def tree(*, expect: dict[str, str] | None = None, sound: bool = False) -> Quern:
    """One gate, one rule, and a note only when the caller asks for it."""
    q = Quern(rules=[Rule(name=_RULE, kind="gate", expr="unsound == 0")])
    meta = {f"expected:{rule}": why for rule, why in (expect or {}).items()}
    set_node(q, "the-surface", {"kind": "gate", "name": "a surface",
                                "params": {"unsound": Quantity(value=0 if sound else 2,
                                                               unit="param")},
                                "meta": meta})
    return q


def judge(q: Quern):
    return reckon(q, run_rules(q))


def test_an_unaccounted_red_is_news():
    """The default, and the one that must never soften: nobody said this was expected."""
    news, carried, stale = judge(tree())
    assert [r.rule for r in news] == [_RULE]
    assert not carried and not stale


def test_a_red_the_node_expects_by_name_is_carried_not_news():
    news, carried, stale = judge(tree(expect={_RULE: "the debts it admits are ungrounded"}))
    assert not news, "a red the ledger accounts for is not what a gate should fail on"
    assert [r.node for r in carried] == ["the-surface"]
    assert not stale


def test_the_note_excuses_only_the_rule_it_names():
    """The point of naming the rule. A blanket 'this node is allowed to be red' would
    hide the next, different failure at the same node — which is the wolf-crying it
    exists to end, moved one level down."""
    q = tree(expect={_RULE: "accounted for"})
    q.rules.append(Rule(name="some-other-rule", kind="gate", expr="unsound < 0"))
    news, carried, _ = judge(q)
    assert [r.rule for r in news] == ["some-other-rule"]
    assert [r.rule for r in carried] == [_RULE]


def test_an_expectation_whose_red_is_gone_is_stale_and_fatal():
    """Self-closing, and this is the property that makes the note safe to grant. A
    permission fails by outliving its reason; discharge the debt and the check asks you
    to withdraw the note, so it cannot be left behind as a standing licence."""
    news, carried, stale = judge(tree(expect={_RULE: "accounted for"}, sound=True))
    assert not news and not carried
    assert len(stale) == 1 and "the-surface" in stale[0] and _RULE in stale[0]


def test_a_node_may_stand_under_more_than_one_red():
    q = tree(expect={_RULE: "one", "second-rule": "two"})
    q.rules.append(Rule(name="second-rule", kind="gate", expr="unsound > 99"))
    news, carried, stale = judge(q)
    assert not news and not stale
    assert sorted(r.rule for r in carried) == [_RULE, "second-rule"]


def test_expectations_reads_the_rule_and_keeps_the_prose():
    node = tree(expect={_RULE: "because the work is not done"}).get("the-surface")
    assert expectations(node) == {_RULE: "because the work is not done"}


def test_a_node_with_no_note_expects_nothing():
    assert expectations(tree().get("the-surface")) == {}


def test_a_note_with_no_prose_is_still_a_note():
    """The prose is for the reader; the check needs only the rule, and a note that
    arrives without a reason has still been written down by somebody — silently
    ignoring it would be the worse failure."""
    news, carried, _ = judge(tree(expect={_RULE: ""}))
    assert not news and len(carried) == 1
