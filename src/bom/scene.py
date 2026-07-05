"""The generic backend substrate: a BOM-like tree where semantics are data.

One structural concept — the node. A node has a free-text `kind` (an étiquette, not
a class: nothing in this module branches on it), parameters whose every number is a
unit- and provenance-carrying Quantity, named `links` to other nodes, a generic
`payload` for domain-typed content (a geometry package puts shapes there; another
domain puts whatever it defines), free-form `meta`, and children. What a kind
*means* lives in the scene's `vocabulary`, what must hold in its `rules`, what
computes in its `solvers` — all written and read through the same API as the tree.

The core interprets none of the payload: shapes, rendering and geometric checks
live entirely in the `bom.geometry` package, reached — like any domain — through
the rule language's one bridge, solve('geometry/…', …). Nodes are addressed by
slash paths ("wardrobe/frame/side-left"), so a client edits a branch without
resending the tree.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from .provenance import Quantity
from .solver import SolverDef

# Payload keys that predate the generic `payload` field; folded in for back-compat,
# exactly like Quantity.tolerance_mm. The core still assigns them no meaning.
_LEGACY_PAYLOAD_KEYS = ("shape", "transform")


class Node(BaseModel):
    """One BOM line: a component, an assembly, or anything the vocabulary defines."""

    id: str
    kind: str = ""   # free label — meaning lives in the scene vocabulary, not here
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


class KindDef(BaseModel):
    """One vocabulary entry: what a `kind` means, in prose the next client reads.

    This is where semantics live — registered at runtime, per home, by whoever
    designs there. `params` and `links` document the names a node of this kind is
    expected to carry ("depth: rail-to-front in mm", "separates: the two spaces").
    """

    kind: str
    description: str
    params: dict[str, str] = Field(default_factory=dict)
    links: dict[str, str] = Field(default_factory=dict)


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
    """A pin on a library package: this scene uses `name` at exactly `version`.
    Frozen deployments stay coherent because the pin, not the library head,
    decides what semantics apply here — a lockfile, one line at a time."""

    name: str
    version: str


class Scene(BaseModel):
    """A home's design tree plus the semantics that give it meaning — vocabulary
    (what kinds are), rules (what must hold) and solvers (code that computes over
    branches, sandboxed), all data, all written through the same API as the tree.
    `packages` pins library packages whose semantics apply here too; the scene's
    own entries always win over package ones."""

    vocabulary: list[KindDef] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    solvers: list["SolverDef"] = Field(default_factory=list)
    packages: list[PackageRef] = Field(default_factory=list)
    root: Node = Field(default_factory=lambda: Node(id="scene"))


# --- path addressing ----------------------------------------------------------

def get_node(scene: Scene, path: str) -> Node | None:
    node = scene.root
    for seg in _segs(path):
        node = node.child(seg)
        if node is None:
            return None
    return node


def find_nodes(scene: Scene, query: str | None = None, kind: str | None = None,
               has_param: str | None = None, links_to: str | None = None,
               under: str = "", limit: int = 20) -> list[tuple[str, Node]]:
    """Search the tree instead of walking it: (path, node) pairs matching every
    given filter. `query` is a case-insensitive substring over id, name, kind and
    meta values; `kind` and `has_param` match exactly; `links_to` matches any link
    target (a path, exact); `under` scopes the search to a branch. Purely
    structural — the search knows no more about kinds than the tree does."""
    start = get_node(scene, under)
    if start is None:
        return []
    q = query.lower() if query else None
    out: list[tuple[str, Node]] = []

    def visit(node: Node, path: str) -> None:
        if len(out) >= limit:
            return
        if path:  # the root is an anchor, not a result
            hay = " ".join([node.id, node.name, node.kind, *node.meta.values()]).lower()
            if ((q is None or q in hay)
                    and (kind is None or node.kind == kind)
                    and (has_param is None or has_param in node.params)
                    and (links_to is None
                         or any(links_to in v for v in node.links.values()))):
                out.append((path, node))
        for c in node.children:
            visit(c, f"{path}/{c.id}" if path else c.id)

    visit(start, under.strip("/"))
    return out


def semantics_at(scene: Scene, path: str, depth: int | None = None) -> dict[str, Any]:
    """The meaning of a slice of the tree, discovered with the slice itself.

    Returns the vocabulary entries for every kind present at `path` (down to
    `depth`) and the rules that apply there — so a client learns what it is
    looking at exactly as it navigates, the way an MCP tool carries its own
    description. Nothing global to fetch, nothing to know in advance.
    """
    node = get_node(scene, path)
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
           for k in scene.vocabulary if k.kind in kinds}
    rules = [r.model_dump(exclude_none=True) for r in scene.rules
             if (r.kind in kinds if r.kind is not None else
                 (r.path or "").startswith(path) or path.startswith(r.path or ""))]
    out: dict[str, Any] = {}
    if voc:
        out["kinds"] = voc
    if rules:
        out["rules"] = rules
    undefined = sorted(k for k in kinds if k not in voc)
    if undefined:
        out["undefined_kinds"] = undefined  # meaning nobody wrote down yet
    return out


def set_node(scene: Scene, path: str, data: dict[str, Any]) -> Node:
    """Create or update the node at `path`. Given fields replace those fields
    (children included — edit a child by addressing it, not by resending lists);
    missing intermediate nodes are created as bare groups."""
    segs = _segs(path)
    if not segs:
        raise ValueError("the root is not editable — address a child path")
    node = scene.root
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


def delete_node(scene: Scene, path: str) -> Node:
    segs = _segs(path)
    if not segs:
        raise ValueError("the root is not deletable")
    parent = get_node(scene, "/".join(segs[:-1]))
    target = parent.child(segs[-1]) if parent is not None else None
    if target is None:
        raise ValueError(f"no node at '{path}'")
    parent.children.remove(target)
    return target


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

NATIVE: dict[str, Any] = {}  # name -> callable(scene, *args): standard implementations


def register_native(name: str, fn) -> None:
    """Install a first-class implementation of a solver contract. The name is the
    contract (e.g. 'geometry/volume'); the callable takes (scene, *args). Natives
    are an optimisation of content, never a semantics of their own: if a native
    disagrees with the contract's reference module, the native is wrong."""
    NATIVE[name] = fn


class RuleResult(BaseModel):
    rule: str
    node: str  # the path the rule ran against ("" = global)
    ok: bool
    detail: str = ""


def run_rules(scene: Scene, path: str = "",
              context: dict[str, Any] | None = None,
              solver_runner=None) -> list[RuleResult]:
    """Evaluate every rule that applies at or under `path`.

    `context` is the caller-supplied evaluation payload (feeds, series windows,
    anything) exposed through ctx('key') — the rules see it and nothing else,
    which is what makes an evaluation deterministic and replayable. solve() runs
    against the NATIVE registry first, then `solver_runner(name, args)` if the
    caller wires one (e.g. to the sandboxed WASM machinery)."""
    out: list[RuleResult] = []
    env = _env(scene, context or {}, solver_runner)
    for rule in scene.rules:
        for node_path, variables in _rule_bindings(scene, rule, path):
            try:
                value = _eval_expr(rule.expr, env, variables)
                out.append(RuleResult(rule=rule.name, node=node_path, ok=bool(value)))
            except Exception as e:  # a broken rule must report, not crash the check
                out.append(RuleResult(rule=rule.name, node=node_path, ok=False,
                                      detail=str(e)))
    return out


def _rule_bindings(scene: Scene, rule: Rule, under: str):
    """(path, variables) pairs the rule evaluates against."""
    if rule.kind is not None:
        for node_path, node in _iter_paths(scene.root, ""):
            if node.kind == rule.kind and node_path.startswith(under):
                variables = {k: q.value for k, q in node.params.items()}
                variables["self"] = node_path
                yield node_path, variables
    else:
        target = rule.path or ""
        if target.startswith(under) or under.startswith(target):
            node = get_node(scene, target)
            variables = ({k: q.value for k, q in node.params.items()}
                         if node is not None else {})
            variables["self"] = target
            yield target, variables


def _iter_paths(node: Node, path: str):
    for c in node.children:
        cpath = f"{path}/{c.id}" if path else c.id
        yield cpath, c
        yield from _iter_paths(c, cpath)


def _env(scene: Scene, context: dict[str, Any] | None = None,
         solver_runner=None) -> dict[str, Any]:
    """Structural builtins + the solve() bridge. Nothing here interprets content."""
    context = context or {}

    def solve(name: str, *args):
        fn = NATIVE.get(name)
        if fn is not None:
            return fn(scene, *args)
        if solver_runner is not None:
            return solver_runner(name, list(args))
        raise ValueError(f"no implementation for solver '{name}' — register a "
                         "native or install a package that carries it")

    def nodes(kind: str | None = None, under: str = "") -> list[str]:
        start = get_node(scene, under)
        if start is None:
            return []
        return [p for p, n in _iter_paths(start, under.strip("/"))
                if kind is None or n.kind == kind]

    def params_of(paths, name: str) -> list[float]:
        return [_param_of(scene, p, name) for p in paths]

    def ctx(name: str):
        if name not in context:
            raise ValueError(f"nothing named '{name}' in the evaluation context")
        return context[name]

    return {
        "solve": solve,                       # the one bridge to content
        "param": lambda p, name: _param_of(scene, p, name),
        "count": lambda p: len((get_node(scene, p) or Node(id="_")).children),
        "nodes": nodes,                       # structural query: paths by kind/branch
        "params_of": params_of,               # a param across many nodes -> list
        "ctx": ctx,                           # caller-supplied evaluation payload
        "abs": abs, "min": min, "max": max,
        "sum": lambda xs: sum(xs), "len": lambda xs: len(xs),
    }


def _param_of(scene: Scene, path: str, name: str) -> float:
    node = get_node(scene, path)
    if node is None or name not in node.params:
        raise ValueError(f"no param '{name}' at '{path}'")
    return node.params[name].value


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
