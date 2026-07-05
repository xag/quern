"""bom — the generic backend substrate.

A BOM-like tree where semantics are data: nodes carry free-text kinds, params
whose every number states its unit and provenance, and named links; what kinds
mean lives in the scene's vocabulary, what must hold in its rules, what computes
in its solvers — all registered at runtime through the same API as the tree, all
*discovered at each node*, all capitalizable as versioned packages. The rule
grammar is structural and reaches meaning through one bridge, solve(); standard
contracts (geometry first) get first-class native implementations behind the
same names.

Canonical repository: xag/bom (private while it hardens; built to be published).
"""

from .library import Library, Package, solver_blob, validate_package
from .provenance import Provenance, Quantity, design_target, inferred, measured
from .solver import (
    SolverDef,
    SolverError,
    load_blob,
    path_allowed,
    run_solver,
    save_blob,
    stamp,
)
from .scene import (
    KindDef,
    Node,
    PackageRef,
    Rule,
    RuleResult,
    Scene,
    Shape,
    SolidView,
    Transform,
    bbox,
    clearance_mm,
    delete_node,
    find_nodes,
    get_node,
    realize,
    register_native,
    render_png,
    run_rules,
    semantics_at,
    set_node,
    volume_mm3,
)
from .standard import GEOMETRY_PACKAGE, register_standard

register_standard()  # the standard library is available wherever bom is imported

__all__ = [
    "Provenance", "Quantity", "design_target", "inferred", "measured",
    "KindDef", "Library", "Node", "Package", "PackageRef", "Rule", "RuleResult",
    "Scene", "Shape", "SolidView", "SolverDef", "SolverError", "Transform",
    "GEOMETRY_PACKAGE", "register_standard", "solver_blob", "validate_package",
    "bbox", "clearance_mm", "delete_node", "find_nodes", "get_node", "load_blob",
    "path_allowed", "realize", "register_native", "render_png", "run_rules",
    "run_solver", "save_blob", "semantics_at", "set_node", "stamp", "volume_mm3",
]
