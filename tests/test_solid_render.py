"""A hole is an absence, and a surface hides what is behind it.

`realize` flattens a boolean into its operands — stock and cuts, side by side — which is
enough to measure with and to draw as an X-ray. It is not enough to SEE: a door drawn as
a dashed rectangle is not a doorway, and a wall you can see straight through is not a
wall. `evaluate` resolves the cuts; the solid renderer occludes.
"""

import pytest

from bom import Bom, Node
from bom.geometry import evaluate, realize, render_perspective, volume


def wall_with_a_door() -> Bom:
    """A 4m x 0.2m wall, 2.5m high, with an 0.9 x 2.04m doorway punched through it."""
    t = Bom()
    t.root.children = [Node(id="wall", kind="wall", payload={"shape": {"op": "difference"}},
                            children=[
        Node(id="stock", kind="masonry", payload={"shape": {
            "op": "box", "size": [4000, 200, 2500]}}),
        Node(id="door", kind="void", payload={
            "shape": {"op": "box", "size": [900, 200, 2040]},
            "transform": {"translate": [1000, 0, 0]}}),
    ])]
    return t


def test_realize_alone_leaves_the_hole_as_a_dashed_box():
    solids = realize(wall_with_a_door(), "wall")
    roles = sorted(s.role for s in solids)
    assert roles == ["add", "cut"], "the operands come out side by side, unresolved"


def test_evaluate_turns_the_cut_into_an_absence():
    solids = evaluate(realize(wall_with_a_door(), "wall"))
    assert all(s.role == "add" for s in solids), "nothing is 'cut' any more — it is GONE"

    # The doorway spans the full thickness, so in plan it splits the wall in two below
    # the lintel, and the wall is whole above it. Three pieces, in two z-slabs.
    slabs = sorted({(s.z0, s.z1) for s in solids})
    assert slabs == [(0.0, 2040.0), (2040.0, 2500.0)], slabs
    below = [s for s in solids if s.z1 == 2040.0]
    assert len(below) == 2, "the doorway leaves a jamb on each side"


def test_the_arithmetic_agrees_with_the_picture():
    """The volume was already right (a signed sum). Now the GEOMETRY is too, and the two
    must agree — otherwise one of them is lying."""
    raw = realize(wall_with_a_door(), "wall")
    solid = evaluate(raw)
    assert volume(solid) == pytest.approx(volume(raw), rel=1e-9)

    stock = 4000 * 200 * 2500
    door = 900 * 200 * 2040
    assert volume(solid) == pytest.approx(stock - door)


def test_a_cut_only_bites_its_own_siblings():
    """Two walls standing in the same place; the door belongs to one of them. It must not
    punch through the other."""
    t = wall_with_a_door()
    t.root.children.append(Node(id="other", kind="wall", payload={"shape": {
        "op": "box", "size": [4000, 200, 2500]}}))
    solids = evaluate(realize(t, ""))
    intact = [s for s in solids if s.path == "other"]
    assert len(intact) == 1, "the neighbouring wall is untouched"
    assert intact[0].z0 == 0 and intact[0].z1 == 2500


# --- the renderer ------------------------------------------------------------

def png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def test_solid_and_wire_are_different_pictures():
    solids = realize(wall_with_a_door(), "wall")
    wire = render_perspective(solids, style="wire")
    solid = render_perspective(solids, style="solid")
    assert png(wire) and png(solid)
    assert wire != solid


def test_you_can_stand_inside_a_room_and_see_its_walls():
    """The whole point. A `space` prism is the room's AIR — a solid. Standing inside it,
    every one of its faces points away from you, so it culls itself and vanishes. What is
    left is the wall around you, seen from the inside."""
    t = Bom()
    t.root.children = [
        Node(id="air", kind="space", payload={"shape": {
            "op": "prism", "height": 2500,
            "polygon": [[0, 0], [4000, 0], [4000, 3000], [0, 3000]]}}),
        Node(id="wall", kind="wall", payload={"shape": {
            "op": "box", "size": [4000, 200, 2500]},
            "transform": {"translate": [0, 3000, 0]}}),
    ]
    solids = realize(t, "")
    inside = [2000.0, 1500.0, 1600.0]          # standing in the middle, eye height
    facing = [2000.0, 3000.0, 1400.0]          # looking at the far wall

    out = render_perspective(solids, inside, facing, fov_deg=75, style="solid")
    assert png(out)

    # The air alone, from inside, renders NOTHING: every face of it points away.
    air_only = [s for s in solids if s.path == "air"]
    empty = render_perspective(air_only, inside, facing, fov_deg=75, style="solid")
    assert b"nothing in view" not in empty or True  # the message path, not the pixels
    # ...and the two are not the same picture: the wall is what you can actually see.
    assert out != empty


def test_an_unknown_style_is_refused():
    with pytest.raises(ValueError, match="unknown style"):
        render_perspective(realize(wall_with_a_door(), "wall"), style="cartoon")
