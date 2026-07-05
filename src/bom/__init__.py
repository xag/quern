"""bom — the generic backend substrate.

A BOM-like tree where semantics are data: nodes carry free-text kinds, params
whose every number states its unit and provenance, named links, and a generic
`payload` the core assigns no meaning to. What kinds mean lives in vocabulary,
what must hold in rules, what computes in solvers — all registered at runtime,
all discovered at each node, all capitalizable as versioned packages. The rule
grammar is structural and reaches meaning through one bridge, solve(); domains
(geometry first) are packages whose contracts may have first-class native
implementations behind the same names.

Canonical repository: xag/bom (private while it hardens; built to be published).
Consumers: home (twin + robots), invest (research notebook), your next domain.
"""

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
from .tree import (
    KindDef,
    Node,
    PackageRef,
    Rule,
    RuleResult,
    Tree,
    delete_node,
    find_nodes,
    get_node,
    register_native,
    run_rules,
    semantics_at,
    set_node,
)
from .library import Library, Package, solver_blob, validate_package
from .geometry import (
    GEOMETRY_PACKAGE,
    Shape,
    SolidView,
    Transform,
    bbox,
    clearance,
    realize,
    register_standard,
    render_perspective_png,
    render_png,
    volume,
)

register_standard()  # geometry contracts get their native implementations

__all__ = [
    "Provenance", "Quantity", "design_target", "inferred", "measured",
    "KindDef", "Library", "Node", "Package", "PackageRef", "Rule", "RuleResult",
    "Tree", "SolverDef", "SolverError",
    "GEOMETRY_PACKAGE", "Shape", "SolidView", "Transform", "register_standard",
    "solver_blob", "validate_package",
    "bbox", "clearance", "delete_node", "find_nodes", "get_node", "load_blob",
    "path_allowed", "realize", "register_native", "render_perspective_png",
    "render_png", "run_rules", "run_solver", "save_blob", "semantics_at",
    "set_node", "stamp", "volume",
]
