"""The predicates a judge needs: does it realize, do they adjoin, is it inside, do
they collide — and is any of it safe to act on."""

import pytest

from bom.geometry import GEOMETRY_NATIVES, realize
from bom.grounding import depends_untrusted, untrusted, untrusted_via
from bom.tree import Bom, Node, set_node


def solve(name: str, *args):
    """Reach the contract the way a rule does."""
    return GEOMETRY_NATIVES[f"geometry/{name}"](*args)


def room(id: str, x0: float, y0: float, x1: float, y1: float, h: float = 2500) -> Node:
    return Node(id=id, kind="space", payload={"shape": {
        "op": "prism", "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "height": h}})


def tree(*nodes: Node) -> Bom:
    b = Bom()
    b.root.children = list(nodes)
    return b


# --- adjacency: the mistake that got through a real survey ------------------------

def test_rooms_sharing_a_wall_share_an_edge():
    t = tree(room("a", 0, 0, 4000, 3000), room("b", 4000, 0, 7000, 3000))
    assert solve("shared_edge", t, "a", "b") == pytest.approx(3000)


def test_rooms_that_only_touch_at_a_CORNER_share_no_wall():
    """The bug this exists for. The two bounding boxes touch, so clearance is 0 and
    every bbox test calls them adjacent — but they meet at a single point and share
    no wall at all. A survey that claims they adjoin is wrong in exactly this way,
    and only shared_edge can say so."""
    t = tree(room("a", 0, 0, 4000, 3000), room("b", 4000, 3000, 8000, 6000))
    assert solve("clearance", t, "a", "b") == 0.0     # bbox: "touching"
    assert solve("shared_edge", t, "a", "b") == 0.0   # the truth: no shared boundary


def test_rooms_that_do_not_touch_at_all_share_no_wall():
    t = tree(room("a", 0, 0, 4000, 3000), room("b", 5000, 3000, 9000, 6000))
    assert solve("shared_edge", t, "a", "b") == 0.0


def test_a_partial_wall_shares_only_its_overlap():
    t = tree(room("a", 0, 0, 4000, 3000), room("b", 4000, 1000, 7000, 2500))
    assert solve("shared_edge", t, "a", "b") == pytest.approx(1500)


def test_different_storeys_share_nothing():
    a = room("a", 0, 0, 4000, 3000)
    b = room("b", 4000, 0, 7000, 3000)
    b.payload["transform"] = {"translate": [0, 0, 3000]}  # the floor above
    t = tree(a, b)
    assert solve("shared_edge", t, "a", "b") == 0.0


# --- realizes / contains / overlap ------------------------------------------------

def test_a_space_with_no_shape_does_not_realize():
    t = tree(Node(id="chambre", kind="space"))  # the degenerate survey node
    assert solve("realizes", t, "chambre") == 0.0
    assert solve("realizes", t, "") == 0.0


def test_a_space_with_a_shape_realizes():
    t = tree(room("salon", 0, 0, 4000, 3000))
    assert solve("realizes", t, "salon") == 1.0


def window(t: Bom, x: float, y: float) -> None:
    set_node(t, "salon/window", {"kind": "opening", "payload": {
        "shape": {"op": "box", "size": [1800, 100, 2100]},
        "transform": {"translate": [x, y, 400]}}})


def test_a_feature_on_a_face_still_counts_as_inside():
    """A window straddles the wall it sits in — half its thickness is outside the
    room. Without a tolerance it reads as 'not contained', which is not a defect."""
    t = tree(room("salon", 0, 0, 4000, 3000))
    window(t, 1200, -50)  # straddles the y=0 wall
    assert solve("contains", t, "salon", "salon/window") == 0.0
    assert solve("contains", t, "salon", "salon/window", 100) == 1.0


def test_a_feature_somewhere_else_entirely_is_caught():
    """And this is the defect worth catching: an opening the surveyor put nowhere
    near the room it claims to belong to."""
    t = tree(room("salon", 0, 0, 4000, 3000))
    window(t, 9000, 9000)
    assert solve("contains", t, "salon", "salon/window", 100) == 0.0


def test_rooms_in_the_same_air_overlap():
    t = tree(room("a", 0, 0, 4000, 3000), room("b", 3000, 0, 7000, 3000))
    assert solve("overlap", t, "a", "b") > 0
    t2 = tree(room("a", 0, 0, 4000, 3000), room("b", 4000, 0, 7000, 3000))
    assert solve("overlap", t2, "a", "b") == 0.0


def test_a_child_is_not_part_of_the_body_it_is_compared_against():
    """realize() flattens a subtree, so without care a window would be part of the
    room it is being tested against, and every question would answer itself."""
    t = tree(room("salon", 0, 0, 4000, 3000))
    window(t, 9000, 9000)  # far outside, but a CHILD of salon
    assert solve("overlap", t, "salon", "salon/window") == 0.0
    assert solve("contains", t, "salon", "salon/window", 100) == 0.0


# --- grounding: is any of it safe to act on --------------------------------------

MEASURED = {"value": 2500, "unit": "mm", "provenance": "measured", "tolerance": 2}
LOOSE = {"value": 2500, "unit": "mm", "provenance": "measured", "tolerance": 50}
GUESSED = {"value": 2500, "unit": "mm", "provenance": "inferred"}


def test_untrusted_counts_guesses_and_loose_measurements():
    t = tree(Node(id="wall", kind="boundary",
                  params={"height": MEASURED, "length": GUESSED}))
    assert untrusted(t, "wall") == 1                 # the guess
    assert untrusted(t, "wall", tolerance=1) == 2    # ...and 2mm is not tight enough for 1mm


def test_the_gate_a_design_passes_before_it_is_cut():
    """untrusted_via is the whole measured-before-cut idea: the design says what it
    is fitted against; this says whether those are observations."""
    t = tree(Node(id="wall", kind="boundary", params={"height": LOOSE}))
    set_node(t, "shelf", {"kind": "piece", "links": {"fits_against": ["wall"]}})
    assert untrusted_via(t, "shelf", "fits_against") == 0          # it IS measured...
    assert untrusted_via(t, "shelf", "fits_against", 2) == 1       # ...but to 50mm, not 2mm


def test_a_derived_value_resting_on_a_guess_is_a_guess():
    t = tree(Node(id="wall", kind="boundary", params={"height": GUESSED}))
    set_node(t, "shelf", {"kind": "piece", "params": {"cut_height": {
        "value": 2400, "unit": "mm", "provenance": "derived", "grounded": False,
        "derived_from": ["wall/height"]}}})
    assert untrusted(t, "wall") == 1
    assert depends_untrusted(t, "shelf") == 1  # followed the lineage to the guess
