"""Package composition: requires + proof-gating against the dependency closure."""

import pytest

from bom import Bom, PackageRef
from bom.library import Library, Package
from bom.tree import KindDef, Node, Rule


def bolt(id: str, mass: float = 10.0) -> Node:
    return Node(id=id, kind="bolt",
                params={"mass": {"value": mass, "unit": "g"}})


def fasteners(version: str = "1", min_mass: str = "0") -> Package:
    """The base layer: a kind, a rule over it, and the example that proves it."""
    return Package(
        name="fasteners", version=version,
        vocabulary=[KindDef(kind="bolt", description="a threaded fastener",
                            params={"mass": "grams"})],
        rules=[Rule(name="bolt-has-mass", kind="bolt",
                    expr=f"mass > {min_mass}")],
        examples=[bolt("proof-bolt")])


def assemblies(examples: list[Node]) -> Package:
    """The extending layer: its rule and examples lean on fasteners' kind."""
    return Package(
        name="assemblies", version="1",
        requires=[PackageRef(name="fasteners", version="1")],
        vocabulary=[KindDef(kind="pack", description="bolts sold together")],
        rules=[Rule(name="pack-of-two", kind="pack",
                    expr="tally(self, 'bolt', 'qty') == 2")],
        examples=examples)


def test_publish_with_requires_stages_the_closure(tmp_path):
    lib = Library(tmp_path)
    lib.publish(fasteners(), {})
    pack = Node(id="proof-pack", kind="pack", children=[bolt("b1"), bolt("b2")])
    log = lib.publish(assemblies([pack]), {})
    assert any("fasteners@1" in line for line in log)


def test_requires_must_already_be_published(tmp_path):
    lib = Library(tmp_path)
    with pytest.raises(ValueError, match="not in the library"):
        lib.publish(assemblies([Node(id="p", kind="pack",
                                     children=[bolt("b1"), bolt("b2")])]), {})


def test_examples_must_satisfy_the_dependency_rules_too(tmp_path):
    lib = Library(tmp_path)
    lib.publish(fasteners(), {})
    weightless = Node(id="p", kind="pack",
                      children=[bolt("b1", mass=0.0), bolt("b2")])
    with pytest.raises(ValueError, match="bolt-has-mass"):
        lib.publish(assemblies([weightless]), {})


def test_pin_pulls_the_whole_closure_nearer_winning(tmp_path):
    lib = Library(tmp_path)
    lib.publish(fasteners(), {})
    ext = assemblies([Node(id="p", kind="pack",
                           children=[bolt("b1"), bolt("b2")])])
    ext.vocabulary.append(KindDef(kind="bolt", description="a bolt, refined"))
    lib.publish(ext, {})

    tree = Bom(packages=[PackageRef(name="assemblies", version="1")])
    resolved = lib.resolve(tree)
    assert [(p.name, p.version) for p in resolved] == [
        ("assemblies", "1"), ("fasteners", "1")]
    eff = lib.effective(tree)
    bolt_def = next(k for k in eff.vocabulary if k.kind == "bolt")
    assert bolt_def.description == "a bolt, refined"  # the extender wins
    assert any(r.name == "bolt-has-mass" for r in eff.rules)  # base still applies


def test_shared_dependency_appears_once(tmp_path):
    lib = Library(tmp_path)
    lib.publish(fasteners(), {})
    for name in ("left", "right"):
        lib.publish(Package(name=name, version="1",
                            requires=[PackageRef(name="fasteners", version="1")]), {})
    tree = Bom(packages=[PackageRef(name="left", version="1"),
                         PackageRef(name="right", version="1")])
    assert [p.name for p in lib.resolve(tree)] == ["left", "fasteners", "right"]


def test_diamond_conflict_is_refused_loudly(tmp_path):
    lib = Library(tmp_path)
    lib.publish(fasteners("1"), {})
    lib.publish(fasteners("2", min_mass="1"), {})
    lib.publish(Package(name="left", version="1",
                        requires=[PackageRef(name="fasteners", version="1")]), {})
    lib.publish(Package(name="right", version="1",
                        requires=[PackageRef(name="fasteners", version="2")]), {})
    tree = Bom(packages=[PackageRef(name="left", version="1"),
                         PackageRef(name="right", version="1")])
    with pytest.raises(ValueError, match="diamond conflict"):
        lib.resolve(tree)
    # read paths keep serving: first version encountered wins
    lenient = lib.resolve(tree, strict=False)
    assert ("fasteners", "1") in [(p.name, p.version) for p in lenient]
    assert ("fasteners", "2") not in [(p.name, p.version) for p in lenient]


def test_requires_are_part_of_the_immutable_content(tmp_path):
    lib = Library(tmp_path)
    lib.publish(fasteners("1"), {})
    lib.publish(fasteners("2"), {})
    pkg = Package(name="ext", version="1",
                  requires=[PackageRef(name="fasteners", version="1")])
    lib.publish(pkg, {})
    repin = pkg.model_copy(deep=True)
    repin.requires = [PackageRef(name="fasteners", version="2")]
    with pytest.raises(ValueError, match="immutable"):
        lib.publish(repin, {})
