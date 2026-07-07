"""Operations on kinds: capabilities discovered with the slice, as data."""

from bom import Bom, KindDef, OperationDef, SolverDef, semantics_at, set_node


def test_operations_ride_with_the_slice():
    tree = Bom()
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
    tree = Bom()
    tree.vocabulary.append(KindDef(kind="shelf", description="a board"))
    set_node(tree, "wardrobe/shelf1", {"kind": "shelf"})
    assert "operations" not in semantics_at(tree, "wardrobe")["kinds"]["shelf"]


def test_solvers_whose_reads_cover_the_path_are_surfaced():
    tree = Bom()
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
