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
The substrate knows nothing of its consumers: a domain is a package plus the code
that embeds this library — never a reference from inside it.
"""

from .provenance import (
    Provenance,
    Quantity,
    derived,
    design_target,
    inferred,
    measured,
)
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
    DERIVED_FROM,
    SUPERSEDES,
    KindDef,
    Node,
    PackageRef,
    Rule,
    RuleResult,
    Bom,
    delete_node,
    find_nodes,
    get_node,
    is_superseded,
    lineage,
    register_native,
    run_rules,
    semantics_at,
    set_node,
    superseders,
)
from .library import Library, Package, solver_blob, validate_package

# geometry is NOT re-exported here: it is a domain package, reached as `bom.geometry`,
# not a citizen of the substrate's surface. Importing that submodule installs its
# geometry/* natives; `import bom` alone pulls in no domain, no Pillow, no registration.

__all__ = [
    "Provenance", "Quantity", "derived", "design_target", "inferred", "measured",
    "KindDef", "Library", "Node", "Package", "PackageRef", "Rule", "RuleResult",
    "Bom", "SolverDef", "SolverError", "DERIVED_FROM", "SUPERSEDES",
    "solver_blob", "validate_package",
    "delete_node", "find_nodes", "get_node", "is_superseded",
    "lineage", "load_blob", "path_allowed", "register_native",
    "run_rules", "run_solver", "save_blob",
    "semantics_at", "set_node", "stamp", "superseders",
]
