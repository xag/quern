"""The ledger package must publish, and its gate must actually stop things.

The publish gate already proves the rules pass on the examples and fire on the
counter-examples. What these add is the consumer's question: does a gate wired to real
content go red for the right reason, and green once a human has grounded it?
"""

from __future__ import annotations

import pytest

from bom import Bom, Library, Node, Quantity, run_rules
from bom.grounding import GROUNDING_PACKAGE
from bom.ledger import LEDGER_PACKAGE


@pytest.fixture
def library(tmp_path):
    lib = Library(tmp_path)
    lib.publish(GROUNDING_PACKAGE, {})
    return lib


def test_ledger_publishes_with_its_proofs(library):
    """The proof gate: every rule exercised by an example, every rule refuted by a
    counter-example. A guard ships the evidence that it guards."""
    log = library.publish(LEDGER_PACKAGE, {})
    assert any("4 rule(s) exercised" in line for line in log)
    assert any("refuted by their counter-example" in line for line in log)


def _staged(library, *nodes: Node) -> Bom:
    """A tree with the ledger's semantics beneath it and `nodes` as its content."""
    library.publish(LEDGER_PACKAGE, {})
    bom = Bom(packages=[{"name": "ledger", "version": "0.1.0"}])
    bom = library.effective(bom)
    bom.root.children = list(nodes)
    return bom


def _bundle(grounded: bool) -> Node:
    return Node(
        id="bundle", kind="debt", name="A generated bundle",
        params={"strings": Quantity(value=47, unit="string", grounded=grounded,
                                    provenance="verified" if grounded else "unverified")},
        children=[Node(id="read-it", kind="discharge", name="A native reader checks it")],
    )


def _gate() -> Node:
    return Node(id="release", kind="gate", name="Publication",
                links={"admits": ["bundle"]})


def _verdict(bom: Bom, rule: str) -> bool:
    results = [r for r in run_rules(bom) if r.rule == rule]
    assert results, f"rule '{rule}' never bound — the test proves nothing"
    return all(r.ok for r in results)


def test_a_gate_refuses_what_no_human_has_checked(library):
    """The whole point. An ungrounded value on the far side of a gate stops the gate."""
    bom = _staged(library, _bundle(grounded=False), _gate())
    assert not _verdict(bom, "nothing-unsound-passes-a-gate")


def test_a_gate_opens_once_the_debt_is_discharged(library):
    """And it opens again — discharging is grounding the params, not deleting the node.
    The debt stays in the record; what changes is that a human vouched for it."""
    bom = _staged(library, _bundle(grounded=True), _gate())
    assert _verdict(bom, "nothing-unsound-passes-a-gate")


def test_a_gate_that_admits_nothing_is_vacuously_open(library):
    """A gate with no `admits` link passes — it guards nothing, and says so. This is the
    honest failure mode to know about: an unwired gate is green, so wiring it is the act
    that matters, and a green gate is only worth what its links are worth."""
    bom = _staged(library, Node(id="release", kind="gate", name="Publication"))
    assert _verdict(bom, "nothing-unsound-passes-a-gate")
