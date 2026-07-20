"""Operations on kinds: capabilities discovered with the slice, as data."""

from quern import Quern, KindDef, OperationDef, SolverDef, semantics_at, set_node


def test_operations_ride_with_the_slice():
    tree = Quern()
    tree.vocabulary.append(KindDef(
        kind="shelf", description="a horizontal board",
        operations={"fit": OperationDef(
            contract="geometry/fit", description="does it fit its bay?",
            params_doc={"clearance": "mm of slack required"})}))
    set_node(tree, "wardrobe/shelf1", {"kind": "shelf"})

    sem = semantics_at(tree, "wardrobe")
    ops = sem["kinds"]["shelf"]["operations"]
    assert ops["fit"]["contract"] == "geometry/fit"
    assert ops["fit"]["params_doc"] == {"clearance": "mm of slack required"}


def test_a_kind_without_operations_stays_as_before():
    tree = Quern()
    tree.vocabulary.append(KindDef(kind="shelf", description="a board"))
    set_node(tree, "wardrobe/shelf1", {"kind": "shelf"})
    assert "operations" not in semantics_at(tree, "wardrobe")["kinds"]["shelf"]


def test_solvers_whose_reads_cover_the_path_are_surfaced():
    tree = Quern()
    set_node(tree, "wardrobe/frame", {})
    set_node(tree, "garden/oak", {})
    tree.solvers.append(SolverDef(name="wardrobe-fit", reads=["wardrobe"],
                                  description="fits parts to the bay"))
    tree.solvers.append(SolverDef(name="whole-tree", reads=[""]))

    at_wardrobe = semantics_at(tree, "wardrobe")["solvers"]
    assert [s["name"] for s in at_wardrobe] == ["wardrobe-fit", "whole-tree"]
    assert at_wardrobe[0]["description"] == "fits parts to the bay"
    in_garden = semantics_at(tree, "garden").get("solvers", [])
    assert [s["name"] for s in in_garden] == ["whole-tree"]
    at_root = semantics_at(tree, "").get("solvers", [])
    assert [s["name"] for s in at_root] == ["whole-tree"]


def test_a_solver_carries_its_scope_and_how_it_runs_but_not_its_manual():
    """What identifies a solver rides with the slice; what documents it does not.

    This dict is on the hot path — every tree_get during navigation carries it — so the
    exclusions are the load-bearing half of the decision, not an oversight. `reads` and
    native-vs-wasm answer "what may this see, and where does it run"; `params_doc`, `fuel`
    and the blob sha answer "how do I call it", which is a tree_solver away and has no
    business being paid for on every click."""
    tree = Quern()
    set_node(tree, "wardrobe/frame", {})
    tree.solvers.append(SolverDef(name="native-fit", reads=["wardrobe"], native=True,
                                  params_doc={"clearance": "mm of slack at the top"},
                                  fuel=999, blob="deadbeef"))
    tree.solvers.append(SolverDef(name="wasm-fit", reads=["wardrobe", "garden"],
                                  medium="wasm"))

    by_name = {s["name"]: s for s in semantics_at(tree, "wardrobe")["solvers"]}
    assert by_name["native-fit"]["native"] is True
    assert by_name["wasm-fit"]["native"] is False
    assert by_name["wasm-fit"]["medium"] == "wasm"
    # The scope travels verbatim, every branch of it — the viewer shows what it may see.
    assert by_name["wasm-fit"]["reads"] == ["wardrobe", "garden"]

    for field in ("params_doc", "fuel", "blob"):
        assert field not in by_name["native-fit"], (
            f"'{field}' would ride on every tree_get — keep the navigation path lean")
