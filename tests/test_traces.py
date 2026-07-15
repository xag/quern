"""Traces as data: scenarios are subtrees of events; rules order them."""

import pytest

from quern import (
    Quern,
    Rule,
    child_at,
    child_index,
    following,
    is_before,
    preceding,
    run_rules,
    set_node,
)
from quern.library import Library, Package
from quern.tree import KindDef, Node


def checkout_scenario() -> Quern:
    """One purchase, as it should unfold."""
    tree = Quern()
    for event, kind in (("browse", "pageview"), ("checkout", "checkout"),
                        ("email-conf", "email"), ("charge", "charge")):
        set_node(tree, f"scenarios/purchase/{event}", {"kind": kind})
    return tree


def test_before_is_document_order():
    tree = checkout_scenario()
    assert is_before(tree, "scenarios/purchase/checkout",
                     "scenarios/purchase/charge")
    assert not is_before(tree, "scenarios/purchase/charge",
                         "scenarios/purchase/email-conf")
    with pytest.raises(ValueError, match="no node"):
        is_before(tree, "scenarios/purchase/ghost", "scenarios/purchase/charge")


def test_sibling_order_verbs():
    tree = checkout_scenario()
    assert preceding(tree, "scenarios/purchase/charge", "email") == [
        "scenarios/purchase/email-conf"]
    assert following(tree, "scenarios/purchase/checkout") == [
        "scenarios/purchase/email-conf", "scenarios/purchase/charge"]
    assert child_index(tree, "scenarios/purchase/charge") == 3
    assert child_at(tree, "scenarios/purchase", 0) == "scenarios/purchase/browse"
    with pytest.raises(ValueError, match="no child 9"):
        child_at(tree, "scenarios/purchase", 9)


def test_trace_predicates_run_as_ordinary_rules():
    tree = checkout_scenario()
    tree.rules.append(Rule(
        name="email-before-charge", kind="charge",
        description="after checkout, the confirmation email precedes the charge",
        expr="len(preceding(self, 'email')) >= 1"))
    tree.rules.append(Rule(
        name="charge-ends-the-trace", kind="charge",
        expr="len(following(self)) == 0"))
    results = {r.rule: r for r in run_rules(tree)}
    assert results["email-before-charge"].ok
    assert results["charge-ends-the-trace"].ok

    # the violating trace: charged before any email went out
    bad = Quern(rules=list(tree.rules))
    for event, kind in (("checkout", "checkout"), ("charge", "charge"),
                        ("email-conf", "email")):
        set_node(bad, f"scenarios/purchase/{event}", {"kind": kind})
    results = {r.rule: r for r in run_rules(bad)}
    assert not results["email-before-charge"].ok
    assert not results["charge-ends-the-trace"].ok


def test_a_behavioral_spec_ships_as_a_proof_gated_package(tmp_path):
    lib = Library(tmp_path)
    scenario = Node(id="purchase", kind="scenario", children=[
        Node(id="checkout", kind="checkout"),
        Node(id="email-conf", kind="email"),
        Node(id="charge", kind="charge")])
    spec = Package(
        name="checkout-spec", version="1",
        vocabulary=[KindDef(kind="scenario", description="one trace of events"),
                    KindDef(kind="charge", description="money moves")],
        rules=[Rule(name="email-before-charge", kind="charge",
                    expr="len(preceding(self, 'email')) >= 1")],
        examples=[scenario])
    log = lib.publish(spec, {})
    assert any("all pass" in line for line in log)

    # the spec that cannot demonstrate itself is refused
    broken = spec.model_copy(deep=True)
    broken.version = "2"
    broken.examples[0].children.reverse()  # charge now precedes the email
    with pytest.raises(ValueError, match="email-before-charge"):
        lib.publish(broken, {})
