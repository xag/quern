"""Contracts over the provenance atom: is this number safe to act on?

`Quantity` already carries the whole answer — `grounded` (an observation, not a
guess) and `tolerance` (how tight, or how tight it must be), and `trusted_within`
folds the two into the one predicate a consumer branches on. Nothing reached for
it. These are the contracts that do, so a *rule* can ask the question:

    solve('grounding/untrusted_via', self, 'fits_against', 2) == 0

"nothing this design is fitted against is a guess, or measured more loosely than
2mm". A domain that cuts material, a domain that commits capital, a domain that
publishes a claim — all three ask exactly this, and none of them should have to
write it themselves.

Counts, not booleans: a rule wants `== 0`, and a diagnostic wants to know how many.
"""

from __future__ import annotations

from .library import Package
from .provenance import Quantity
from .solver import SolverDef
from .tree import Bom, KindDef, Node, get_node, register_native


def _params_under(node: Node, path: str) -> list[tuple[str, str, Quantity]]:
    """Every (node path, param name, quantity) at or under `node`."""
    out: list[tuple[str, str, Quantity]] = []

    def walk(n: Node, p: str) -> None:
        for name, q in n.params.items():
            out.append((p, name, q))
        for c in n.children:
            walk(c, f"{p}/{c.id}" if p else c.id)

    walk(node, path)
    return out


def _node(tree: Bom, path: str) -> Node:
    n = get_node(tree, path)
    if n is None:
        raise ValueError(f"no node at '{path}'")
    return n


def untrusted(tree: Bom, path: str = "", tolerance: float | None = None) -> float:
    """How many params at or under `path` are NOT safe to act on — not grounded, or
    grounded more loosely than `tolerance` (omit it to ask only about grounding)."""
    return float(sum(1 for _, _, q in _params_under(_node(tree, path), path)
                     if not q.trusted_within(tolerance)))


def untrusted_via(tree: Bom, path: str, rel: str,
                  tolerance: float | None = None) -> float:
    """The same question asked of the reality a node is fitted against: follow the
    `rel` link from `path` (one hop) and count the untrusted params in the targets.

    This is the gate a design passes before it is acted on. The link says what the
    design depends on; this says whether those dependencies are observations.
    """
    node = _node(tree, path)
    return float(sum(untrusted(tree, target, tolerance)
                     for target in node.links.get(rel, [])))


def depends_untrusted(tree: Bom, path: str = "",
                      tolerance: float | None = None) -> float:
    """Follow `derived_from` lineage transitively from every param at or under
    `path`, and count the upstream params that are untrusted.

    A derived value is never grounded — it is exactly as good as its inputs, and
    this is what says how good that is. A computed number resting on a guess is a
    guess wearing a number's clothes.
    """
    seen: set[str] = set()
    bad: set[tuple[str, str]] = set()  # (node path, param) — a set, so a diamond counts once

    def visit(owner: str, name: str, q: Quantity) -> None:
        if not q.trusted_within(tolerance):
            bad.add((owner, name))
        for up in q.derived_from:
            follow(up)

    def follow(ref: str) -> None:
        """A lineage ref is either a node path or 'path/param'."""
        if ref in seen:
            return
        seen.add(ref)
        node = get_node(tree, ref)
        if node is not None:  # the whole node was the input
            for owner, name, q in _params_under(node, ref):
                visit(owner, name, q)
            return
        head, _, name = ref.rpartition("/")
        owner_node = get_node(tree, head)
        if owner_node is None or name not in owner_node.params:
            return  # dangling lineage: a broken ref, not a grounding claim to answer
        visit(head, name, owner_node.params[name])

    for _, _, q in _params_under(_node(tree, path), path):
        for up in q.derived_from:
            follow(up)
    return float(len(bad))


GROUNDING_NATIVES = {
    "grounding/untrusted": untrusted,
    "grounding/untrusted_via": untrusted_via,
    "grounding/depends_untrusted": depends_untrusted,
}


def register_standard() -> None:
    for name, fn in GROUNDING_NATIVES.items():
        register_native(name, fn)


GROUNDING_PACKAGE = Package(
    name="grounding",
    version="1.0.0",
    description="Contracts over the provenance atom, so a rule can ask whether a "
                "number is safe to act on: untrusted(path, tol) counts the params "
                "that are not grounded (or grounded too loosely); untrusted_via("
                "path, rel, tol) asks it of whatever a node links to — the reality a "
                "design is fitted against; depends_untrusted(path, tol) follows "
                "derived_from lineage, because a computed value is only as good as "
                "its inputs. Grounding is the substrate's one fixed epistemic verb; "
                "the provenance *label* stays a domain's own word.",
    publisher="standard library",
    vocabulary=[
        KindDef(kind="grounding", description="Convention pack, not a node kind: "
                "every Quantity already carries `grounded` and `tolerance`. These "
                "contracts only read them — count what a branch, its links, or its "
                "lineage rests on that is not an observation."),
    ],
    solvers=[
        SolverDef(name=name, native=True,
                  description="standard grounding contract; see the package description",
                  reads=[""])
        for name in GROUNDING_NATIVES
    ],
)


register_standard()
