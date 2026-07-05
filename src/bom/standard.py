"""The standard library: content contracts with first-class implementations.

`geometry@1` is the first standard package. Its *meaning* is content — the
package below documents the shape conventions and the solver contracts — and the
Python in scene.py (realize, bbox, volume, clearance) is merely the server's
native implementation of those contracts, registered under the same names the
rule language reaches through solve(). A custom or shared WASM module could
implement the same contracts; if a native ever disagrees with the contract, the
native is the bug.

Nothing privileges geometry architecturally: this module is a consumer of
register_native() like any future standard domain, and the substrate's grammar
knows only solve().
"""

from __future__ import annotations

from .library import Package
from .scene import (
    KindDef,
    Scene,
    SolverDef,
    bbox,
    clearance_mm,
    realize,
    register_native,
    volume_mm3,
)


def _bb(scene: Scene, p: str) -> dict:
    b = bbox(realize(scene, p))
    if b is None:
        raise ValueError(f"'{p}' has no solids")
    return b


GEOMETRY_NATIVES = {
    "geometry/volume": lambda scene, p: volume_mm3(realize(scene, p)),
    "geometry/bbox_w": lambda scene, p: _bb(scene, p)["max"][0] - _bb(scene, p)["min"][0],
    "geometry/bbox_d": lambda scene, p: _bb(scene, p)["max"][1] - _bb(scene, p)["min"][1],
    "geometry/bbox_h": lambda scene, p: _bb(scene, p)["max"][2] - _bb(scene, p)["min"][2],
    "geometry/z_min": lambda scene, p: _bb(scene, p)["min"][2],
    "geometry/z_max": lambda scene, p: _bb(scene, p)["max"][2],
    "geometry/clearance": lambda scene, a, b: clearance_mm(realize(scene, a),
                                                           realize(scene, b)),
}


def register_standard() -> None:
    for name, fn in GEOMETRY_NATIVES.items():
        register_native(name, fn)


GEOMETRY_PACKAGE = Package(
    name="geometry",
    version="1.0.0",
    description="The shape conventions (box/prism/cylinder/mesh + booleans over "
                "children, mm, z-up) and the solver contracts the rule language "
                "reaches with solve('geometry/…', path): volume, bbox_w/d/h, "
                "z_min/z_max, clearance(a, b). Implemented natively by this server; "
                "any module honouring the same contracts may replace it.",
    publisher="standard library",
    vocabulary=[
        KindDef(kind="geometry", description="Convention pack, not a node kind: "
                "nodes get solids by carrying a shape payload — box {size [w,d,h]}, "
                "prism {polygon, height}, cylinder {diameter, height}, mesh {uri}, "
                "union/difference/intersection over children. Vertical extrusions, "
                "mm, z up."),
    ],
    solvers=[
        SolverDef(name=name, native=True,
                  description="standard geometry contract; see the package description",
                  reads=[""])
        for name in GEOMETRY_NATIVES
    ],
)
