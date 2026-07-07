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
    ArtifactDef,
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
    USES,
    KindDef,
    Node,
    Occurrence,
    OperationDef,
    PackageRef,
    Rule,
    RuleResult,
    Bom,
    TreeStore,
    child_at,
    child_index,
    definition,
    delete_node,
    explode,
    find_nodes,
    following,
    get_node,
    is_before,
    is_superseded,
    lineage,
    preceding,
    register_native,
    resolve_params,
    rollup,
    run_rules,
    semantics_at,
    set_node,
    superseders,
    tally,
    users,
)
from .library import Library, Package, solver_blob, validate_package
from .store import SqliteStore

# geometry is NOT re-exported here: it is a domain package, reached as `bom.geometry`,
# not a citizen of the substrate's surface. Importing that submodule installs its
# geometry/* natives; `import bom` alone pulls in no domain, no Pillow, no registration.

__all__ = [
    "Provenance", "Quantity", "derived", "design_target", "inferred", "measured",
    "KindDef", "Library", "Node", "Occurrence", "OperationDef", "Package",
    "PackageRef", "Rule",
    "RuleResult", "Bom", "ArtifactDef", "SolverDef", "SolverError", "SqliteStore",
    "TreeStore",
    "DERIVED_FROM", "SUPERSEDES", "USES",
    "solver_blob", "validate_package",
    "child_at", "child_index", "definition", "delete_node", "explode",
    "find_nodes", "following", "get_node", "is_before", "is_superseded",
    "lineage", "load_blob", "path_allowed", "preceding", "register_native",
    "resolve_params", "rollup", "run_rules", "run_solver", "save_blob",
    "semantics_at", "set_node", "stamp", "superseders", "tally", "users",
]
