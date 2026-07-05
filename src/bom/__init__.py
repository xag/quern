"""bom — the generic design substrate.

A BOM-like tree where semantics are data: nodes carry free-text kinds, params
whose every number states its provenance, and named links; what kinds mean lives
in the scene's vocabulary and what must hold in its rules — both registered at
runtime through the same API as the tree, and both *discovered at each node*:
reading a slice of the tree returns the semantics of that slice.

Private while it hardens; built to be published on its own.
"""

from .provenance import Provenance, Quantity
from .scene import (
    KindDef,
    Node,
    Rule,
    RuleResult,
    Scene,
    Shape,
    SolidView,
    Transform,
    bbox,
    clearance_mm,
    delete_node,
    get_node,
    realize,
    render_png,
    run_rules,
    semantics_at,
    set_node,
    volume_mm3,
)

__all__ = [
    "Provenance", "Quantity",
    "KindDef", "Node", "Rule", "RuleResult", "Scene", "Shape", "SolidView",
    "Transform",
    "bbox", "clearance_mm", "delete_node", "get_node", "realize", "render_png",
    "run_rules", "semantics_at", "set_node", "volume_mm3",
]
