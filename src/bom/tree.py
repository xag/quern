"""The generic backend substrate: a BOM-like tree where semantics are data.

One structural concept — the node. A node has a free-text `kind` (an étiquette, not
a class: nothing in this module branches on it), parameters whose every number is a
unit- and provenance-carrying Quantity, named `links` to other nodes, a generic
`payload` for domain-typed content (a geometry package puts shapes there; another
domain puts whatever it defines), free-form `meta`, and children. What a kind
*means* lives in the tree's `vocabulary`, what must hold in its `rules`, what
computes in its `solvers` — all written and read through the same API as the tree.

The core interprets none of the payload: shapes, rendering and geometric checks
live entirely in the `bom.geometry` package, reached — like any domain — through
the rule language's one bridge, solve('geometry/…', …). Nodes are addressed by
slash paths ("parent/child/leaf"), so a client edits a branch without
resending the tree.

Every verb here runs against the `TreeStore` protocol — the structural contract
`Bom` satisfies in memory and `bom.store.SqliteStore` satisfies with indexes on
disk — so the same model serves a hundred-node design and a hundred-thousand-line
bill without changing a call site.
"""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from pydantic import BaseModel, Field, model_validator

from .provenance import Quantity
from .solver import SolverDef, path_allowed

# Payload keys that predate the generic `payload` field; folded in for back-compat,
# exactly like Quantity.tolerance_mm. The core still assigns them no meaning.
_LEGACY_PAYLOAD_KEYS = ("shape", "transform")

# The reserved structural verbs: link names the core reads (unlike every other link
# name, whose meaning is domain data). They are *verbs a consumer branches on*, not
# nouns a domain names — the only kind of meaning the substrate is allowed to fix.
SUPERSEDES = "supersedes"      # A links supersedes->[B]: A replaces B; B is not current
DERIVED_FROM = "derived_from"  # A links derived_from->[B]: A was computed from B (lineage)
USES = "uses"                  # A links uses->[D]: A is a usage of definition D; A
#                                resolves through D (params, kind); first target is
#                                the primary definition, later targets are alternates


class Node(BaseModel):
    """One BOM line: a component, an assembly, or anything the vocabulary defines."""

    id: str
    kind: str = ""   # free label — meaning lives in the tree vocabulary, not here
    name: str = ""
    params: dict[str, Quantity] = Field(default_factory=dict)
    links: dict[str, list[str]] = Field(default_factory=dict)  # name -> node paths
    meta: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)  # domain content, opaque here
    children: list[Node] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_payload(cls, data: Any) -> Any:
        """Pre-`payload` nodes carried `shape`/`transform` as top-level fields; move
        them into `payload` so old stores load and the core stays payload-agnostic."""
        if isinstance(data, dict) and any(k in data for k in _LEGACY_PAYLOAD_KEYS):
            data = dict(data)
            payload = dict(data.get("payload") or {})
            for k in _LEGACY_PAYLOAD_KEYS:
                if k in data:
                    payload[k] = data.pop(k)
            data["payload"] = payload
        return data

    def child(self, cid: str) -> Node | None:
        return next((c for c in self.children if c.id == cid), None)


class OperationDef(BaseModel):
    """One capability a kind affords: a name bound to a solver contract that makes
    sense on nodes of that kind. Pure data — the core stores, validates and serves
    it; only hosts and agents interpret it (resolve `contract` against the
    effective solvers and execute through the existing verbs, e.g. tree_solve).
    `medium` names how the capability is carried — 'wasm' compute today; a free
    label so richer media stay data too. The moment the core branches on an
    operation name, a noun has leaked back in."""

    contract: str                  # the solver name the operation resolves to
    description: str = ""
    params_doc: dict[str, str] = Field(default_factory=dict)
    medium: str = "wasm"


class KindDef(BaseModel):
    """One vocabulary entry: what a `kind` means, in prose the next client reads.

    This is where semantics live — registered at runtime, per tree, by whoever
    designs there. `params` and `links` document the names a node of this kind is
    expected to carry ("depth: how deep, in mm", "separates: the two it divides").
    `operations` binds the kind to capabilities — what can be computed wherever a
    node means this, discovered with the slice like the rest of the vocabulary.
    """

    kind: str
    description: str
    params: dict[str, str] = Field(default_factory=dict)
    links: dict[str, str] = Field(default_factory=dict)
    operations: dict[str, OperationDef] = Field(default_factory=dict)


class Rule(BaseModel):
    """A solver defined at runtime and capitalized in the store, like vocabulary.

    `expr` is a boolean expression in the safe rule language (arithmetic,
    comparisons, and/or/not, and geometry functions over realized branches:
    volume(p), bbox_w/d/h(p), z_min/z_max(p), clearance(a, b), param(p, name)).
    Scope: `kind` runs the rule once per node of that kind (its params are in
    scope, `self` is its path); `path` pins it to one branch; neither = global.
    No predefined semantics: the rule carries its own meaning in `description`.
    """

    name: str
    expr: str
    description: str = ""
    kind: str | None = None
    path: str | None = None


class PackageRef(BaseModel):
    """A pin on a library package: this tree uses `name` at exactly `version`.
    Frozen deployments stay coherent because the pin, not the library head,
    decides what semantics apply here — a lockfile, one line at a time."""

    name: str
    version: str


class Bom(BaseModel):
    """A design tree plus the semantics that give it meaning — vocabulary
    (what kinds are), rules (what must hold) and solvers (code that computes over
    branches, sandboxed), all data, all written through the same API as the tree.
    `packages` pins library packages whose semantics apply here too; the tree's
    own entries always win over package ones.

    A Bom is also the in-memory `TreeStore`: the methods below are the structural
    protocol a scaled store (`bom.store.SqliteStore`) implements with indexes on
    disk. The free functions further down delegate here, so every call site works
    over either — scale is a choice of store, never a change of model."""

    vocabulary: list[KindDef] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    solvers: list["SolverDef"] = Field(default_factory=list)
    packages: list[PackageRef] = Field(default_factory=list)
    root: Node = Field(default_factory=lambda: Node(id="tree"))

    def get(self, path: str, depth: int | None = None) -> Node | None:
        """The live node at `path` (mutations stick). `depth` is a hydration hint
        for stores that load lazily; live in-memory nodes are already whole."""
        node = self.root
        for seg in _segs(path):
            node = node.child(seg)
            if node is None:
                return None
        return node

    def set(self, path: str, data: dict[str, Any]) -> Node:
        """Create or update the node at `path`. Given fields replace those fields
        (children included — edit a child by addressing it, not by resending
        lists); missing intermediate nodes are created as bare groups."""
        segs = _segs(path)
        if not segs:
            raise ValueError("the root is not editable — address a child path")
        node = self.root
        for seg in segs[:-1]:
            nxt = node.child(seg)
            if nxt is None:
                nxt = Node(id=seg)
                node.children.append(nxt)
            node = nxt
        leaf = node.child(segs[-1])
        data = _fold_payload(data, leaf.payload if leaf is not None else {})
        if leaf is None:
            leaf = Node(id=segs[-1], **data)
            node.children.append(leaf)
        else:
            patched = leaf.model_copy(update={
                k: _coerce(Node, k, v) for k, v in data.items()})
            node.children[node.children.index(leaf)] = patched
            leaf = patched
        return leaf

    def delete(self, path: str) -> Node:
        segs = _segs(path)
        if not segs:
            raise ValueError("the root is not deletable")
        parent = self.get("/".join(segs[:-1]))
        target = parent.child(segs[-1]) if parent is not None else None
        if target is None:
            raise ValueError(f"no node at '{path}'")
        parent.children.remove(target)
        return target

    def walk(self, under: str = ""):
        """(path, node) for the node at `under` (when it is not the root — the
        root is an anchor, not a result) and every node beneath it."""
        start = self.get(under)
        if start is None:
            return
        anchor = "/".join(_segs(under))
        if anchor:
            yield anchor, start
        yield from _iter_paths(start, anchor)

    def children(self, path: str) -> list[str]:
        """Ids of the direct children at `path`, in order ([] when absent)."""
        node = self.get(path)
        return [c.id for c in node.children] if node is not None else []

    def backlinks(self, name: str, target: str) -> list[str]:
        """Paths of every node whose link `name` names `target` — the reverse
        index behind supersession, where-used and lineage invalidation."""
        return sorted(p for p, n in _iter_paths(self.root, "")
                      if target in n.links.get(name, []))

    def find(self, query: str | None = None, kind: str | None = None,
             has_param: str | None = None, links_to: str | None = None,
             under: str = "", current_only: bool = False,
             limit: int = 20) -> list[tuple[str, Node]]:
        """Search the tree instead of walking it — see `find_nodes`."""
        start = self.get(under)
        if start is None:
            return []
        q = query.lower() if query else None
        stale = _superseded_set(self) if current_only else None
        out: list[tuple[str, Node]] = []

        def visit(node: Node, path: str) -> None:
            if len(out) >= limit:
                return
            if path:  # the root is an anchor, not a result
                hay = " ".join([node.id, node.name, node.kind,
                                *node.meta.values()]).lower()
                if ((q is None or q in hay)
                        and (kind is None or node.kind == kind)
                        and (has_param is None or has_param in node.params)
                        and (links_to is None
                             or any(links_to in v for v in node.links.values()))
                        and (stale is None or path not in stale)):
                    out.append((path, node))
            for c in node.children:
                visit(c, f"{path}/{c.id}" if path else c.id)

        visit(start, under.strip("/"))
        return out


class TreeStore(Protocol):
    """The structural contract behind every tree verb: what a thing must expose to
    be navigated, edited, searched and rule-checked. `Bom` satisfies it in memory;
    `bom.store.SqliteStore` satisfies it with indexes on disk. Every free function
    in this module takes either — pass whichever fits the tree's size."""

    vocabulary: list[KindDef]
    rules: list[Rule]
    solvers: list["SolverDef"]
    packages: list[PackageRef]

    def get(self, path: str, depth: int | None = None) -> Node | None: ...
    def set(self, path: str, data: dict[str, Any]) -> Node: ...
    def delete(self, path: str) -> Node: ...
    def walk(self, under: str = "") -> Iterator[tuple[str, Node]]: ...
    def children(self, path: str) -> list[str]: ...
    def backlinks(self, name: str, target: str) -> list[str]: ...
    def find(self, query: str | None = None, kind: str | None = None,
             has_param: str | None = None, links_to: str | None = None,
             under: str = "", current_only: bool = False,
             limit: int = 20) -> list[tuple[str, Node]]: ...


# --- path addressing ----------------------------------------------------------
#
# The free functions are the historical (and still canonical) surface; each
# delegates to the TreeStore protocol, so they serve a Bom and a scaled store
# alike. New code may call the methods directly; nothing forces either style.

def get_node(tree: Bom | TreeStore, path: str) -> Node | None:
    return tree.get(path)


def find_nodes(tree: Bom | TreeStore, query: str | None = None, kind: str | None = None,
               has_param: str | None = None, links_to: str | None = None,
               under: str = "", current_only: bool = False,
               limit: int = 20) -> list[tuple[str, Node]]:
    """Search the tree instead of walking it: (path, node) pairs matching every
    given filter. `query` is a case-insensitive substring over id, name, kind and
    meta values; `kind` and `has_param` match exactly; `links_to` matches any link
    target (a path, exact); `under` scopes the search to a branch; `current_only`
    drops nodes some other node supersedes — the "what do we hold now?" query.
    Purely structural — the search knows no more about kinds than the tree does."""
    return tree.find(query=query, kind=kind, has_param=has_param,
                     links_to=links_to, under=under, current_only=current_only,
                     limit=limit)


# --- the reserved structural verbs: supersession, lineage and reuse -------------
#
# Three relations the core reads by name, where every other link is opaque data.
# Each answers a question a flat, append-only record cannot without being re-read
# whole: "what do we currently hold?" (supersession), "where did this come from?"
# (lineage) and "what is this an instance of?" (reuse). A node declares them like
# any link; these readers, the `current_only` filter above, and the rule builtins
# (superseded, uses, where_used, rollup, tally) are what make them load-bearing.

def _superseded_set(tree: Bom) -> set[str]:
    stale: set[str] = set()
    for _, n in _iter_paths(tree.root, ""):
        stale.update(n.links.get(SUPERSEDES, []))
    return stale


def superseders(tree: Bom | TreeStore, path: str) -> list[str]:
    """Paths of nodes that declare (via the reserved `supersedes` link) that they
    replace `path`. Non-empty ⇒ `path` is superseded — no longer current belief."""
    return sorted(tree.backlinks(SUPERSEDES, path))


def is_superseded(tree: Bom | TreeStore, path: str) -> bool:
    """True iff some node supersedes `path`. The current-belief predicate a check or
    query keys on to keep only what still stands."""
    return bool(tree.backlinks(SUPERSEDES, path))


def lineage(tree: Bom | TreeStore, path: str) -> list[str]:
    """What `path` was derived from: the union of its node-level `derived_from` link
    and the `derived_from` of every value it carries. The traversable half of
    provenance — walk it to find what a change upstream should invalidate."""
    node = tree.get(path)
    if node is None:
        return []
    refs = set(node.links.get(DERIVED_FROM, []))
    for q in node.params.values():
        refs.update(q.derived_from)
    return sorted(refs)


# --- the reuse verb: definitions and usages --------------------------------------
#
# A node that links uses->[D] is a *usage* of the definition D: it resolves through
# D (params it does not carry itself, its kind when it has none), and expanding the
# tree descends into D's children in its place. This is the relation a bill of
# materials calls part reuse — one definition, many occurrences — kept a verb: the
# core fixes only *that* resolution reads through the link. What the multiplier
# param is called ('qty', 'strands'), what a definition is ('part', 'detail') stays
# the domain's, passed in as data.

def definition(tree: Bom | TreeStore, path: str) -> str | None:
    """The path `path` resolves through: the first target of its reserved `uses`
    link that exists in the tree (later targets are alternates). None when the node
    has no `uses` link — or none of its targets exist, a dangling reference
    `explode(strict=True)` refuses and a rule can flag."""
    node = tree.get(path, depth=0)
    if node is None:
        return None
    for target in node.links.get(USES, []):
        if tree.get(target, depth=0) is not None:
            return "/".join(_segs(target))
    return None


def users(tree: Bom | TreeStore, path: str) -> list[str]:
    """Paths of every usage of the definition at `path` — where-used, the symmetric
    of `definition`, exactly as `superseders` is the symmetric of a supersession."""
    return sorted(tree.backlinks(USES, path))


def resolve_params(tree: Bom | TreeStore, path: str) -> dict[str, Quantity]:
    """The effective params of a node: its own, then — for names it does not
    carry — its definition's, following `uses` chains cycle-safely. Usage always
    overrides definition: precedence, never merge magic."""
    out: dict[str, Quantity] = {}
    seen: set[str] = set()
    p: str | None = "/".join(_segs(path))
    while p is not None and p not in seen:
        seen.add(p)
        node = tree.get(p, depth=0)
        if node is None:
            break
        for name, q in node.params.items():
            out.setdefault(name, q)
        p = definition(tree, p)
    return out


def _resolved_kind(tree: Bom | TreeStore, path: str) -> str:
    """A node's kind, read through its definition when it declares none itself."""
    seen: set[str] = set()
    p: str | None = "/".join(_segs(path))
    while p and p not in seen:
        seen.add(p)
        node = tree.get(p, depth=0)
        if node is None:
            return ""
        if node.kind:
            return node.kind
        p = definition(tree, p)
    return ""


class Occurrence(BaseModel):
    """One line of the instantiated tree: `node` occurring at the virtual position
    `path`, `factor` deep in multiplicity. The occurrence path is a display/grouping
    key, not an addressable node — usages graft their definition's children under
    their own path, so it names a position that exists only in the expansion."""

    path: str
    node: str
    factor: float = 1.0


def explode(tree: Bom | TreeStore, under: str = "", mult: str | None = None,
            strict: bool = True) -> list[Occurrence]:
    """The instantiated tree: every occurrence at or under `under`, usages expanded
    into their definition's children (after their own — local additions stay).

    `mult` names the multiplier param — the domain's noun ('qty', 'strands'),
    passed as data — whose product down the chain is each occurrence's `factor`;
    a node not carrying it counts 1. Params read through `uses` (usage overrides
    definition). A definition that occurs inside its own expansion is a cycle and
    raises; `strict` also refuses a `uses` link none of whose targets exist —
    a silent hole in the structure is worse than an error (pass False to skip
    the hole and keep going)."""
    out: list[Occurrence] = []

    def visit(node_path: str, occ_path: str, factor: float,
              chain: tuple[str, ...]) -> None:
        node = tree.get(node_path, depth=0)
        if node is None:
            return
        if mult is not None:
            q = resolve_params(tree, node_path).get(mult)
            if q is not None:
                factor *= q.value
        out.append(Occurrence(path=occ_path, node=node_path, factor=factor))
        for cid in tree.children(node_path):
            visit(f"{node_path}/{cid}", f"{occ_path}/{cid}", factor, chain)
        d = definition(tree, node_path)
        if d is None:
            if strict and node.links.get(USES):
                raise ValueError(
                    f"'{node_path}' uses {node.links[USES]} but no target exists — "
                    "fix the reference or explode with strict=False")
            return
        if d in chain:
            raise ValueError(
                "cycle: '" + d + "' occurs inside its own expansion ("
                + " -> ".join((*chain, d)) + ")")
        for cid in tree.children(d):
            visit(f"{d}/{cid}", f"{occ_path}/{cid}", factor, (*chain, d))

    anchor = "/".join(_segs(under))
    if anchor:
        visit(anchor, anchor, 1.0, ())
    else:
        for cid in tree.children(""):
            visit(cid, cid, 1.0, ())
    return out


def rollup(tree: Bom | TreeStore, under: str, mult: str, value: str,
           strict: bool = True) -> float:
    """Σ over the expansion of factor × `value`: each occurrence carrying the
    `value` param (through its definition) contributes it, weighted by the product
    of `mult` down its chain. Both names are the domain's — 'qty' × 'cost' is a
    costed bill, 'qty' × 'mass' a mass rollup. The fold is the verb; the nouns
    are arguments."""
    total = 0.0
    for occ in explode(tree, under, mult=mult, strict=strict):
        q = resolve_params(tree, occ.node).get(value)
        if q is not None:
            total += occ.factor * q.value
    return total


def tally(tree: Bom | TreeStore, under: str, kind: str, mult: str,
          strict: bool = True) -> float:
    """Σ of factor over every occurrence of `kind` (read through definitions) in
    the expansion — "how many of these does the product take?", multiplicities
    multiplied through."""
    total = 0.0
    for occ in explode(tree, under, mult=mult, strict=strict):
        if _resolved_kind(tree, occ.node) == kind:
            total += occ.factor
    return total


# --- traces as data: ordering over event subtrees --------------------------------
#
# A scenario is a subtree whose children are events, and rules quantify over it
# like any other slice — so a behavioral claim ("after checkout, the confirmation
# email precedes the charge") is a rule, its exercising scenario is an example,
# and tree_check is the model checker. These are the ordering verbs that make
# such predicates expressible: structural only — document order and sibling
# order. What an 'event' or a 'scenario' *is* stays vocabulary; the grammar never
# grows a domain noun.

def is_before(tree: Bom | TreeStore, a: str, b: str) -> bool:
    """True iff `a` precedes `b` in document order (pre-order walk) — the trace
    predicate. Sibling events compare by child order; nested ones by the walk.
    A path that names nothing raises: an ordering claim over a hole is a broken
    rule, not a passing one."""
    order = {p: n for n, (p, _) in enumerate(tree.walk(""))}
    for p in (a, b):
        if "/".join(_segs(p)) not in order:
            raise ValueError(f"no node at '{p}'")
    return order["/".join(_segs(a))] < order["/".join(_segs(b))]


def _sibling_paths(tree: Bom | TreeStore, path: str) -> tuple[list[str], int]:
    segs = _segs(path)
    if not segs:
        raise ValueError("the root has no siblings")
    pp = "/".join(segs[:-1])
    sibs = [f"{pp}/{cid}" if pp else cid for cid in tree.children(pp)]
    norm = "/".join(segs)
    if norm not in sibs:
        raise ValueError(f"no node at '{path}'")
    return sibs, sibs.index(norm)


def preceding(tree: Bom | TreeStore, path: str, kind: str | None = None) -> list[str]:
    """The sibling paths before `path`, in order — what already happened when it
    occurred, when the parent is a scenario. `kind` filters, read through
    definitions like `tally` reads it."""
    sibs, i = _sibling_paths(tree, path)
    out = sibs[:i]
    return out if kind is None else [s for s in out
                                     if _resolved_kind(tree, s) == kind]


def following(tree: Bom | TreeStore, path: str, kind: str | None = None) -> list[str]:
    """The sibling paths after `path`, in order — the symmetric of `preceding`."""
    sibs, i = _sibling_paths(tree, path)
    out = sibs[i + 1:]
    return out if kind is None else [s for s in out
                                     if _resolved_kind(tree, s) == kind]


def child_index(tree: Bom | TreeStore, path: str) -> int:
    """`path`'s position among its parent's children — sequence indexing."""
    return _sibling_paths(tree, path)[1]


def child_at(tree: Bom | TreeStore, parent: str, i: int) -> str:
    """The path of the `i`-th child of `parent` — the inverse of `child_index`.
    Out of range raises: indexing past the trace is a broken rule."""
    ids = tree.children(parent)
    i = int(i)
    if not 0 <= i < len(ids):
        raise ValueError(f"no child {i} at '{parent}' ({len(ids)} children)")
    pp = "/".join(_segs(parent))
    return f"{pp}/{ids[i]}" if pp else ids[i]


def semantics_at(tree: Bom | TreeStore, path: str, depth: int | None = None) -> dict[str, Any]:
    """The meaning of a slice of the tree, discovered with the slice itself.

    Returns the vocabulary entries for every kind present at `path` (down to
    `depth`) — operations included, so every read answers "what is this, what
    must hold, what can be computed here" — the rules that apply there, and the
    solvers whose declared `reads` cover the slice. A client learns what it is
    looking at exactly as it navigates, the way an MCP tool carries its own
    description. Nothing global to fetch, nothing to know in advance.
    """
    node = tree.get(path, depth)
    if node is None:
        return {}
    kinds: set[str] = set()

    def collect(n: Node, d: int | None) -> None:
        if n.kind:
            kinds.add(n.kind)
        if d is not None and d <= 0:
            return
        for c in n.children:
            collect(c, None if d is None else d - 1)

    collect(node, depth)
    voc = {k.kind: k.model_dump(exclude_defaults=True)
           for k in tree.vocabulary if k.kind in kinds}
    rules = [r.model_dump(exclude_none=True) for r in tree.rules
             if (r.kind in kinds if r.kind is not None else
                 (r.path or "").startswith(path) or path.startswith(r.path or ""))]
    out: dict[str, Any] = {}
    if voc:
        out["kinds"] = voc
    if rules:
        out["rules"] = rules
    solvers = [{"name": s.name,
                **({"description": s.description} if s.description else {})}
               for s in tree.solvers if path_allowed(s.reads, path)]
    if solvers:
        out["solvers"] = solvers
    undefined = sorted(k for k in kinds if k not in voc)
    if undefined:
        out["undefined_kinds"] = undefined  # meaning nobody wrote down yet
    return out


def set_node(tree: Bom | TreeStore, path: str, data: dict[str, Any]) -> Node:
    """Create or update the node at `path`. Given fields replace those fields
    (children included — edit a child by addressing it, not by resending lists);
    missing intermediate nodes are created as bare groups."""
    return tree.set(path, data)


def _fold_payload(data: dict[str, Any], base_payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a set_node body: drop id, and fold legacy top-level payload keys
    (shape/transform) into `payload`, merged over the node's existing payload so a
    partial edit never wipes a sibling key."""
    data = dict(data)
    data.pop("id", None)  # the path names the node; ids inside payloads are noise
    payload = {**base_payload, **(data.pop("payload", None) or {})}
    for k in _LEGACY_PAYLOAD_KEYS:
        if k in data:
            v = data.pop(k)
            if v is None:
                payload.pop(k, None)
            else:
                payload[k] = v
    if payload:
        data["payload"] = payload
    return data


def delete_node(tree: Bom | TreeStore, path: str) -> Node:
    return tree.delete(path)


def _segs(path: str) -> list[str]:
    return [s for s in (path or "").split("/") if s]


def _coerce(model: type[BaseModel], field: str, value: Any) -> Any:
    """Validate one field's payload through the model so dicts become models."""
    if value is None:
        return None
    return model.__pydantic_validator__.validate_assignment(
        model.model_construct(), field, value).__dict__[field]


# --- the rule language: solvers as data, evaluated safely -----------------------
#
# A tiny recursive-descent evaluator instead of eval(): rules come from clients at
# runtime on a multi-tenant server, so they get arithmetic, comparisons, booleans,
# string literals and STRUCTURAL builtins only — path/param/children lookups,
# aggregation over lists, and one bridge to meaning: solve('name', ...). Everything
# that interprets content (geometry included) lives behind solve(), as a solver —
# content in the library, or a registered native implementation of a standard
# contract. The grammar never grows a domain function again.

NATIVE: dict[str, Any] = {}  # name -> callable(tree, *args): standard implementations


def register_native(name: str, fn) -> None:
    """Install a first-class implementation of a solver contract. The name is the
    contract (e.g. 'geometry/volume'); the callable takes (tree, *args). Natives
    are an optimisation of content, never a semantics of their own: if a native
    disagrees with the contract's reference module, the native is wrong."""
    NATIVE[name] = fn


class RuleResult(BaseModel):
    rule: str
    node: str  # the path the rule ran against ("" = global)
    ok: bool
    detail: str = ""


def run_rules(tree: Bom | TreeStore, path: str = "",
              context: dict[str, Any] | None = None,
              solver_runner=None) -> list[RuleResult]:
    """Evaluate every rule that applies at or under `path`.

    `context` is the caller-supplied evaluation payload (feeds, series windows,
    anything) exposed through ctx('key') — the rules see it and nothing else,
    which is what makes an evaluation deterministic and replayable. solve() runs
    against the NATIVE registry first, then `solver_runner(name, args)` if the
    caller wires one (e.g. to the sandboxed WASM machinery)."""
    out: list[RuleResult] = []
    env = _env(tree, context or {}, solver_runner)
    for rule in tree.rules:
        for node_path, variables in _rule_bindings(tree, rule, path):
            try:
                value = _eval_expr(rule.expr, env, variables)
                out.append(RuleResult(rule=rule.name, node=node_path, ok=bool(value)))
            except Exception as e:  # a broken rule must report, not crash the check
                out.append(RuleResult(rule=rule.name, node=node_path, ok=False,
                                      detail=str(e)))
    return out


def _rule_bindings(tree: Bom | TreeStore, rule: Rule, under: str):
    """(path, variables) pairs the rule evaluates against."""
    if rule.kind is not None:
        for node_path, node in tree.walk(""):
            if node.kind == rule.kind and node_path.startswith(under):
                variables = {k: q.value for k, q in node.params.items()}
                variables["self"] = node_path
                yield node_path, variables
    else:
        target = rule.path or ""
        if target.startswith(under) or under.startswith(target):
            node = tree.get(target)
            variables = ({k: q.value for k, q in node.params.items()}
                         if node is not None else {})
            variables["self"] = target
            yield target, variables


def _iter_paths(node: Node, path: str):
    for c in node.children:
        cpath = f"{path}/{c.id}" if path else c.id
        yield cpath, c
        yield from _iter_paths(c, cpath)


def _env(tree: Bom | TreeStore, context: dict[str, Any] | None = None,
         solver_runner=None) -> dict[str, Any]:
    """Structural builtins + the solve() bridge. Nothing here interprets content."""
    context = context or {}

    def solve(name: str, *args):
        fn = NATIVE.get(name)
        if fn is not None:
            return fn(tree, *args)
        if solver_runner is not None:
            return solver_runner(name, list(args))
        raise ValueError(f"no implementation for solver '{name}' — register a "
                         "native or install a package that carries it")

    def nodes(kind: str | None = None, under: str = "") -> list[str]:
        anchor = "/".join(_segs(under))
        return [p for p, n in tree.walk(under)
                if p != anchor and (kind is None or n.kind == kind)]

    def params_of(paths, name: str) -> list[float]:
        return [_param_of(tree, p, name) for p in paths]

    def ctx(name: str):
        if name not in context:
            raise ValueError(f"nothing named '{name}' in the evaluation context")
        return context[name]

    return {
        "solve": solve,                       # the one bridge to content
        "param": lambda p, name: _param_of(tree, p, name),
        "count": lambda p: len(tree.children(p)),
        "nodes": nodes,                       # structural query: paths by kind/branch
        "params_of": params_of,               # a param across many nodes -> list
        "superseded": lambda p: is_superseded(tree, p),  # current-belief verb
        "uses": lambda p: definition(tree, p) or "",     # reuse verb: the definition
        "where_used": lambda p: users(tree, p),          # ...and its symmetric
        "rollup": lambda under, mult, value: rollup(tree, under, mult, value),
        "tally": lambda under, kind, mult: tally(tree, under, kind, mult),
        # the trace verbs: ordering over event subtrees, structural only
        "before": lambda a, b: is_before(tree, a, b),
        "preceding": lambda p, kind=None: preceding(tree, p, kind),
        "following": lambda p, kind=None: following(tree, p, kind),
        "index": lambda p: child_index(tree, p),
        "at": lambda parent, i: child_at(tree, parent, i),
        "parent": lambda p: "/".join(_segs(p)[:-1]),
        "ctx": ctx,                           # caller-supplied evaluation payload
        "abs": abs, "min": min, "max": max,
        "sum": lambda xs: sum(xs), "len": lambda xs: len(xs),
    }


def _param_of(tree: Bom | TreeStore, path: str, name: str) -> float:
    # a usage resolves params through its definition: own value first, then the
    # `uses` chain — the read half of the reuse verb
    q = resolve_params(tree, path).get(name)
    if q is None:
        raise ValueError(f"no param '{name}' at '{path}'")
    return q.value


def _eval_expr(src: str, env: dict[str, Any], variables: dict[str, Any]) -> Any:
    tokens = _tokenize(src)
    value, pos = _parse_or(tokens, 0, env, variables)
    if pos != len(tokens):
        raise ValueError(f"unexpected '{tokens[pos][1]}'")
    return value


def _tokenize(src: str) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    i = 0
    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1
        elif c.isdigit() or (c == "." and i + 1 < len(src) and src[i + 1].isdigit()):
            j = i
            while j < len(src) and (src[j].isdigit() or src[j] == "."):
                j += 1
            out.append(("num", float(src[i:j])))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] == "_"):
                j += 1
            out.append(("name", src[i:j]))
            i = j
        elif c in "'\"":
            j = src.find(c, i + 1)
            if j < 0:
                raise ValueError("unterminated string")
            out.append(("str", src[i + 1:j]))
            i = j + 1
        elif src[i:i + 2] in ("<=", ">=", "==", "!="):
            out.append(("op", src[i:i + 2]))
            i += 2
        elif c in "+-*/<>(),":
            out.append(("op", c))
            i += 1
        else:
            raise ValueError(f"bad character '{c}'")
    return out


def _parse_or(toks, i, env, var):
    v, i = _parse_and(toks, i, env, var)
    while i < len(toks) and toks[i] == ("name", "or"):
        r, i = _parse_and(toks, i + 1, env, var)
        v = bool(v) or bool(r)
    return v, i


def _parse_and(toks, i, env, var):
    v, i = _parse_not(toks, i, env, var)
    while i < len(toks) and toks[i] == ("name", "and"):
        r, i = _parse_not(toks, i + 1, env, var)
        v = bool(v) and bool(r)
    return v, i


def _parse_not(toks, i, env, var):
    if i < len(toks) and toks[i] == ("name", "not"):
        v, i = _parse_not(toks, i + 1, env, var)
        return not bool(v), i
    return _parse_cmp(toks, i, env, var)


def _parse_cmp(toks, i, env, var):
    v, i = _parse_sum(toks, i, env, var)
    if i < len(toks) and toks[i][0] == "op" and toks[i][1] in ("<", "<=", ">", ">=", "==", "!="):
        op = toks[i][1]
        r, i = _parse_sum(toks, i + 1, env, var)
        v = {"<": v < r, "<=": v <= r, ">": v > r, ">=": v >= r,
             "==": v == r, "!=": v != r}[op]
    return v, i


def _parse_sum(toks, i, env, var):
    v, i = _parse_term(toks, i, env, var)
    while i < len(toks) and toks[i][0] == "op" and toks[i][1] in "+-":
        op = toks[i][1]
        r, i = _parse_term(toks, i + 1, env, var)
        v = v + r if op == "+" else v - r
    return v, i


def _parse_term(toks, i, env, var):
    v, i = _parse_unary(toks, i, env, var)
    while i < len(toks) and toks[i][0] == "op" and toks[i][1] in "*/":
        op = toks[i][1]
        r, i = _parse_unary(toks, i + 1, env, var)
        v = v * r if op == "*" else v / r
    return v, i


def _parse_unary(toks, i, env, var):
    if i < len(toks) and toks[i] == ("op", "-"):
        v, i = _parse_unary(toks, i + 1, env, var)
        return -v, i
    return _parse_atom(toks, i, env, var)


def _parse_atom(toks, i, env, var):
    if i >= len(toks):
        raise ValueError("unexpected end of expression")
    kind, val = toks[i]
    if kind in ("num", "str"):
        return val, i + 1
    if kind == "op" and val == "(":
        v, i = _parse_or(toks, i + 1, env, var)
        if i >= len(toks) or toks[i] != ("op", ")"):
            raise ValueError("missing ')'")
        return v, i + 1
    if kind == "name":
        if i + 1 < len(toks) and toks[i + 1] == ("op", "("):
            fn = env.get(val)
            if fn is None:
                raise ValueError(f"unknown function '{val}'")
            args = []
            i += 2
            if toks[i] != ("op", ")"):
                while True:
                    a, i = _parse_or(toks, i, env, var)
                    args.append(a)
                    if i < len(toks) and toks[i] == ("op", ","):
                        i += 1
                        continue
                    break
            if i >= len(toks) or toks[i] != ("op", ")"):
                raise ValueError("missing ')'")
            return fn(*args), i + 1
        if val in var:
            return var[val], i + 1
        raise ValueError(f"unknown name '{val}'")
    raise ValueError(f"unexpected '{val}'")
