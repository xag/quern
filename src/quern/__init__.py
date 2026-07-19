"""quern — the generic backend substrate.

A generic node tree where semantics are data: nodes carry free-text kinds, params
whose every number states its unit and provenance, named links, and a generic
`payload` the core assigns no meaning to. What kinds mean lives in vocabulary,
what must hold in rules, what computes in solvers — all registered at runtime,
all discovered at each node, all capitalizable as versioned packages. The rule
grammar is structural and reaches meaning through one bridge, solve(); a domain
is a package pinned from a registry, whose contracts may have first-class native
implementations behind the same names.

Canonical repository: xag/quern.
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
    Quern,
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
    linked_from,
    preceding,
    register_native,
    resolve_params,
    rollup,
    run_rules,
    said_words,
    semantics_at,
    set_node,
    superseded_paths,
    superseders,
    tally,
    unsupported,
    users,
)
from .library import Library, Package, solver_blob, validate_package
from .store import SqliteStore

# No domain lives in this source tree anymore: every domain is authored in its own
# repository and travels the registry as data — the substrate knows them only as
# packages a tree pins.
#
# `quern.grounding` is the one survivor, and only its code half. Its subject *is* the
# substrate — the
# grounded/tolerance/derived_from fields every Quantity already carries — but the
# contracts that read them (grounding/untrusted, untrusted_via, depends_untrusted) are
# still a capability a consumer opts into, and still register natives on import. The
# atom is core; asking questions of it is a package.

__all__ = [
    "Provenance", "Quantity", "derived", "design_target", "inferred", "measured",
    "KindDef", "Library", "Node", "Occurrence", "OperationDef", "Package",
    "PackageRef", "Rule",
    "RuleResult", "Quern", "ArtifactDef", "SolverDef", "SolverError", "SqliteStore",
    "TreeStore",
    "DERIVED_FROM", "SUPERSEDES", "USES",
    "solver_blob", "validate_package",
    "child_at", "child_index", "definition", "delete_node", "explode",
    "find_nodes", "following", "get_node", "is_before", "is_superseded",
    "linked_from", "superseded_paths",
    "lineage", "load_blob", "path_allowed", "preceding", "register_native",
    "resolve_params", "rollup", "run_rules", "run_solver", "save_blob",
    "said_words", "semantics_at", "set_node", "stamp", "superseders", "tally",
    "unsupported",
    "users",
]
