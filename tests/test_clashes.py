"""Two packages that define one name: settled by a stated relation, or refused.

Pin order used to decide, silently: with two packages both defining kind `piece` and a
rule `sound`, the second package's meaning and its failing rule vanished and the run
stayed green. These are the laws that replace it.
"""

import pytest

from quern import Quern, Rule, run_rules, set_node
from quern.library import Library, Package, clashes, write_text
from quern.solver import SolverDef
from quern.tree import KindDef, PackageRef, register_native


def _pkg(name, *, desc="", expr="1 == 1", requires=(), solver=None):
    return Package(name=name, version="1.0.0",
                   vocabulary=[KindDef(kind="piece", description=desc or name)],
                   rules=[Rule(name="sound", kind="piece", expr=expr)],
                   solvers=[SolverDef(name=solver, native=True)] if solver else [],
                   requires=[PackageRef(name=r, version="1.0.0") for r in requires])


def _library(tmp_path, *packages) -> Library:
    lib = Library(tmp_path)
    for p in packages:
        write_text(tmp_path / "packages" / p.name / f"{p.version}.json", p.model_dump_json())
    return lib


def _tree(*names, prefer=None) -> Quern:
    return Quern(packages=[PackageRef(name=n, version="1.0.0") for n in names],
                 prefer=prefer or {})


def test_two_unrelated_packages_defining_one_name_are_refused(tmp_path):
    lib = _library(tmp_path, _pkg("home-fit"), _pkg("furniture-design", expr="1 == 0"))
    with pytest.raises(ValueError) as refused:
        lib.effective(_tree("home-fit", "furniture-design"))
    assert "kind 'piece' is defined by both home-fit and furniture-design" in str(refused.value)
    assert "rule 'sound'" in str(refused.value)


def test_an_extender_may_redefine_what_it_requires_and_wins(tmp_path):
    lib = _library(tmp_path, _pkg("furniture-design"),
                   _pkg("home-fit", desc="fitted to a room", requires=["furniture-design"]))
    eff = lib.effective(_tree("home-fit"))
    assert [k.description for k in eff.vocabulary] == ["fitted to a room"]


def test_the_relation_counts_through_a_chain_of_requires(tmp_path):
    lib = _library(tmp_path, _pkg("base"), _pkg("middle", requires=["base"]) .model_copy(
        update={"vocabulary": [], "rules": []}), _pkg("top", desc="top", requires=["middle"]))
    assert [k.description for k in lib.effective(_tree("top")).vocabulary] == ["top"]


def test_a_tree_that_prefers_one_package_gets_its_definitions(tmp_path):
    lib = _library(tmp_path, _pkg("home-fit"), _pkg("furniture-design", expr="1 == 0"))
    tree = _tree("home-fit", "furniture-design",
                 prefer={"piece": "furniture-design", "sound": "furniture-design"})
    eff = lib.effective(tree)
    assert [k.description for k in eff.vocabulary] == ["furniture-design"]
    set_node(eff, "chest", {"kind": "piece"})
    assert [r.ok for r in run_rules(eff)] == [False]   # the preferred, failing rule runs


def test_a_preference_that_settles_nothing_or_names_the_wrong_package_is_refused(tmp_path):
    lib = _library(tmp_path, _pkg("home-fit"), _pkg("furniture-design"))
    pkgs = lib.resolve(_tree("home-fit", "furniture-design"), strict=False)
    wrong = clashes(_tree(prefer={"piece": "lamello"}), pkgs)
    assert any("which lamello does not define" in p for p in wrong)
    alone = _library(tmp_path / "alone", _pkg("furniture-design"))
    with pytest.raises(ValueError, match="settles nothing"):
        alone.effective(_tree("furniture-design", prefer={"piece": "furniture-design"}))


def test_the_trees_own_definition_settles_the_name(tmp_path):
    lib = _library(tmp_path, _pkg("home-fit"), _pkg("furniture-design"))
    tree = _tree("home-fit", "furniture-design", prefer={"sound": "home-fit"})
    tree.vocabulary.append(KindDef(kind="piece", description="mine"))
    assert [k.description for k in lib.effective(tree).vocabulary] == ["mine"]


def test_a_read_path_keeps_serving_and_a_strict_one_reports(tmp_path):
    lib = _library(tmp_path, _pkg("home-fit"), _pkg("furniture-design"))
    tree = _tree("home-fit", "furniture-design")
    assert [k.description for k in lib.effective(tree, strict=False).vocabulary] == ["home-fit"]
    with pytest.raises(ValueError):
        lib.resolve(tree)


def test_locking_moves_bytes_and_leaves_the_clash_to_composition(tmp_path):
    from quern.library import lock_refs
    lib = _library(tmp_path, _pkg("home-fit"), _pkg("furniture-design"))
    refs = lock_refs(lib, _tree("home-fit", "furniture-design").packages)
    assert [r.name for r in refs] == ["home-fit", "furniture-design"]


def test_a_calculation_name_two_packages_declare_is_refused(tmp_path):
    a = _pkg("a", solver="shared/mass").model_copy(update={"vocabulary": [], "rules": []})
    b = _pkg("b", solver="shared/mass").model_copy(update={"vocabulary": [], "rules": []})
    with pytest.raises(ValueError, match="calculation 'shared/mass'"):
        _library(tmp_path, a, b).effective(_tree("a", "b"))


def _elsewhere(tree, *args):
    return 2.0


_elsewhere.__module__ = "another.package"


def test_a_native_taken_over_by_another_module_must_say_it_replaces_it():
    register_native("test-clash/mass", lambda tree, *a: 1.0)
    register_native("test-clash/mass", lambda tree, *a: 1.5)   # same module: allowed
    with pytest.raises(ValueError, match="replaces=True"):
        register_native("test-clash/mass", _elsewhere)
    register_native("test-clash/mass", _elsewhere, replaces=True)
