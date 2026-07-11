"""Counter-examples: the proof that a guard guards.

An example shows a rule does not fire on sound data. It cannot show the rule fires
on unsound data — so a rule rotted into vacuity publishes exactly like a real one.
A counter-example is the node the rule MUST reject.
"""

import pytest

from bom.library import CounterExample, Library, Package, validate_package
from bom.tree import KindDef, Node, Rule

BOLT = KindDef(kind="bolt", description="a threaded fastener", params={"mass": "grams"})


def bolt(id: str, **params) -> Node:
    return Node(id=id, kind="bolt",
                params={k: {"value": v, "unit": "g"} for k, v in params.items()})


def pkg(expr: str, counter=(), name="fasteners") -> Package:
    return Package(
        name=name, version="1", vocabulary=[BOLT],
        rules=[Rule(name="bolt-has-mass", kind="bolt", expr=expr,
                    description="a bolt must state a positive mass")],
        examples=[bolt("proof-bolt", mass=10.0)],
        counter_examples=list(counter))


MASSLESS = CounterExample(rule="bolt-has-mass", node=bolt("massless"),
                          because="a bolt with no mass at all")


def test_a_real_rule_is_proven_by_its_counter_example(tmp_path):
    log = validate_package(pkg("mass > 0", counter=[MASSLESS]), tmp_path,
                           Library(tmp_path))
    assert any("refuted by their counter-example" in line for line in log)
    assert any("a bolt with no mass at all" in line for line in log)


def test_a_vacuous_rule_cannot_be_proven(tmp_path):
    """The whole point. '1 == 1' passes every example a real rule passes; only the
    counter-example tells them apart."""
    vacuous = pkg("1 == 1", counter=[MASSLESS])
    with pytest.raises(ValueError, match="is not refuted"):
        validate_package(vacuous, tmp_path, Library(tmp_path))

    # ...and without the counter-example it still publishes, indistinguishably.
    log = validate_package(pkg("1 == 1"), tmp_path, Library(tmp_path))
    assert any("exercised by" in line for line in log)
    assert any("no counter-example" in line for line in log)  # but it is called out


def test_a_rule_that_does_not_bind_to_the_node_is_not_proven(tmp_path):
    """Refutation must come from the named rule reaching THAT node — not from the
    node being ignored."""
    wrong_kind = CounterExample(rule="bolt-has-mass", node=Node(id="nut", kind="nut"),
                                because="not a bolt at all")
    with pytest.raises(ValueError, match="does not even bind"):
        validate_package(pkg("mass > 0", counter=[wrong_kind]), tmp_path,
                         Library(tmp_path))


def test_a_counter_example_cannot_borrow_another_rules_failure(tmp_path):
    """Each counter-example is staged alone, so a defect elsewhere in the package
    cannot stand in for the proof."""
    p = Package(
        name="fasteners", version="1", vocabulary=[BOLT],
        rules=[Rule(name="bolt-has-mass", kind="bolt", expr="mass > 0"),
               Rule(name="always-true", kind="bolt", expr="1 == 1")],
        examples=[bolt("proof-bolt", mass=10.0)],
        # 'always-true' can never reject anything -- even staged with a defective node.
        counter_examples=[CounterExample(rule="always-true", node=bolt("massless"),
                                         because="a bolt with no mass")])
    with pytest.raises(ValueError, match="counter-example for rule 'always-true'"):
        validate_package(p, tmp_path, Library(tmp_path))


def test_counter_example_must_name_a_rule_the_package_defines(tmp_path):
    stray = CounterExample(rule="no-such-rule", node=bolt("massless"))
    with pytest.raises(ValueError, match="does not define"):
        validate_package(pkg("mass > 0", counter=[stray]), tmp_path, Library(tmp_path))


def test_a_relational_defect_can_stage_the_world_it_needs(tmp_path):
    """A defect is often relational: a design fitted against an unmeasured wall needs
    BOTH to exist. Stage only the design and the rule still trips — but on a dangling
    link, not an unmeasured one, and the proof would be a lie that reads like a proof.
    """
    import bom.grounding  # noqa: F401 -- registers grounding/*

    guessed = {"value": 2500, "unit": "mm", "provenance": "inferred"}
    measured = {"value": 2500, "unit": "mm", "provenance": "measured", "tolerance": 2}

    def world(wall_param) -> Node:
        return Node(id="wall", kind="boundary", params={"height": wall_param})

    def design() -> Node:
        return Node(id="shelf", kind="piece", links={"fits_against": ["wall"]})

    p = Package(
        name="fit", version="1", vocabulary=[KindDef(kind="piece", description="a design")],
        rules=[Rule(name="not-cut-against-guesses", kind="piece",
                    expr="solve('grounding/untrusted_via', self, 'fits_against') == 0",
                    description="never cut against a dimension nobody measured")],
        examples=[world(measured), design()],
        counter_examples=[CounterExample(
            rule="not-cut-against-guesses",
            nodes=[world(guessed), design()],   # the wall EXISTS; its height is a guess
            because="a piece scribed to a wall whose height was estimated from a photo")],
    )
    log = validate_package(p, tmp_path, Library(tmp_path))
    assert any("estimated from a photo" in line for line in log)


def test_packages_without_rules_are_unaffected(tmp_path):
    """geometry@1.0.0 ships kinds and solvers, no rules. It must still publish."""
    log = validate_package(
        Package(name="conventions", version="1", vocabulary=[BOLT]),
        tmp_path, Library(tmp_path))
    assert not any("counter-example" in line for line in log)
