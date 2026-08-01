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

Only the IMPLEMENTATIONS live here — host safety code, registered by importing this
module, on the substrate's clock. Their meaning (the vocabulary entry and the solver
descriptors a tree pins) is the `grounding@` package, authored in its own repository
and pinned by digest from the registry like any other. Meaning is data, safety is
code; this module is the code half, and the substrate otherwise knows no domain.
"""

from __future__ import annotations

from .provenance import Quantity, derived, inferred, measured
from .tree import Demonstration, Quern, Node, get_node, register_native


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


def _node(tree: Quern, path: str) -> Node:
    n = get_node(tree, path)
    if n is None:
        raise ValueError(f"no node at '{path}'")
    return n


def untrusted(tree: Quern, path: str = "", tolerance: float | None = None) -> float:
    """How many params at or under `path` are NOT safe to act on — not grounded, or
    grounded more loosely than `tolerance` (omit it to ask only about grounding)."""
    return float(sum(1 for _, _, q in _params_under(_node(tree, path), path)
                     if not q.trusted_within(tolerance)))


def untrusted_via(tree: Quern, path: str, rel: str,
                  tolerance: float | None = None) -> float:
    """The same question asked of the reality a node is fitted against: follow the
    `rel` link from `path` (one hop) and count the untrusted params in the targets.

    This is the gate a design passes before it is acted on. The link says what the
    design depends on; this says whether those dependencies are observations.
    """
    node = _node(tree, path)
    return float(sum(untrusted(tree, target, tolerance)
                     for target in node.links.get(rel, [])))


def depends_untrusted(tree: Quern, path: str = "",
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


# --- the spec ----------------------------------------------------------------------
#
# These three run outside the sandbox, on the host's own clock, and they are what a
# gate asks before it calls work safe to act on. Prose said what they do; nothing said
# it twice in a form that could disagree with the code. Below is that second saying.
#
# It is written as SCENARIOS, not as coverage. The interesting cases are the ones where
# a wrong answer is still a plausible answer — an empty branch, a tolerance nobody
# stated, a link pointing at a node that was deleted — because those are the ones that
# turn a gate green while meaning nothing, and a green gate is exactly what nobody
# re-reads. Each entry says which scenario it is; the list is therefore also a record
# of what was anticipated, and the next reader can see what was not.

_SOUND_WALL = Node(id="wall", kind="wall", params={"width": measured(2400.0, 1.0)})
_GUESSED_WALL = Node(id="wall", kind="wall", params={"width": inferred(2400.0)})
_LOOSE_WALL = Node(id="wall", kind="wall", params={"width": measured(2400.0, 5.0)})
_UNTOLERANCED_WALL = Node(id="wall", kind="wall", params={
    "width": Quantity(value=2400.0, unit="mm", provenance="measured", grounded=True)})
_DESIGN = Node(id="shelf", kind="design", params={"depth": measured(300.0, 1.0)},
               links={"fits_against": ["wall"]})


UNTRUSTED_SPEC = [
    Demonstration(
        contract="grounding/untrusted", nodes=[_SOUND_WALL], args=["wall"], expect=0,
        because="a branch whose every number is an observation"),
    Demonstration(
        contract="grounding/untrusted", nodes=[_GUESSED_WALL], args=["wall"], expect=1,
        because="one guess in the branch is one count"),
    Demonstration(
        contract="grounding/untrusted", args=["wall"], expect=2,
        nodes=[Node(id="wall", kind="wall", params={"width": inferred(2400.0),
                                                    "height": inferred(2000.0)})],
        because="it counts, it does not flag: two guesses answer 2, so a rule may "
                "read the number and not only compare it to zero"),
    Demonstration(
        contract="grounding/untrusted", args=["wall"], expect=1,
        nodes=[Node(id="wall", kind="wall", params={"width": measured(2400.0, 1.0)},
                    children=[Node(id="recess", kind="recess",
                                   params={"depth": inferred(120.0)})])],
        because="a guess on a child is in its parent's branch — the question is asked "
                "of everything under the path, not of the node alone"),
    Demonstration(
        contract="grounding/untrusted", nodes=[_LOOSE_WALL], args=["wall", 2.0],
        expect=1,
        because="grounded, but measured looser than the work needs: trusted is a "
                "question about tightness too, not only about provenance"),
    Demonstration(
        contract="grounding/untrusted", nodes=[_LOOSE_WALL], args=["wall", 10.0],
        expect=0,
        because="the same observation against a tolerance it does meet"),
    Demonstration(
        contract="grounding/untrusted", nodes=[_LOOSE_WALL], args=["wall"], expect=0,
        because="omitting the tolerance asks only whether it is an observation at "
                "all — the loose wall passes, and a caller who meant to ask about "
                "tightness and forgot gets a green that is answering another question"),
    Demonstration(
        contract="grounding/untrusted", nodes=[_UNTOLERANCED_WALL], args=["wall", 2.0],
        expect=1,
        because="an observation that never said how tight it is cannot answer a "
                "tolerance: unstated is not zero, and is not 'good enough'"),
    Demonstration(
        contract="grounding/untrusted", args=["wall"], expect=0,
        nodes=[Node(id="wall", kind="wall")],
        because="an empty branch answers 0 — nothing to doubt is not the same as "
                "checked, and a gate reading `== 0` over an empty branch goes green "
                "on the absence of evidence. Recorded because it is the contract's "
                "sharpest edge, not because it is a defect"),
    Demonstration(
        contract="grounding/untrusted", nodes=[_SOUND_WALL], args=["ghost"],
        expect_error="no node at",
        because="a branch that is not there is refused, never answered 0 — the one "
                "way this contract could silently pass a gate over nothing"),
]

UNTRUSTED_VIA_SPEC = [
    Demonstration(
        contract="grounding/untrusted_via", nodes=[_DESIGN, _SOUND_WALL],
        args=["shelf", "fits_against"], expect=0,
        because="a design fitted against a wall somebody measured"),
    Demonstration(
        contract="grounding/untrusted_via", nodes=[_DESIGN, _GUESSED_WALL],
        args=["shelf", "fits_against"], expect=1,
        because="the same design fitted against a wall somebody eyeballed — the "
                "design's own numbers are sound and that is not the question"),
    Demonstration(
        contract="grounding/untrusted_via", nodes=[_DESIGN, _GUESSED_WALL],
        args=["shelf", "rests_on"], expect=0,
        because="no link of that name is nothing to doubt: the green that means "
                "least, and the one a typo in the link name produces"),
    Demonstration(
        contract="grounding/untrusted_via", args=["shelf", "fits_against"], expect=2,
        nodes=[Node(id="shelf", kind="design", links={"fits_against": ["wall", "floor"]}),
               _GUESSED_WALL,
               Node(id="floor", kind="floor", params={"level": inferred(0.0)})],
        because="every target of the link is counted, not just the first"),
    Demonstration(
        contract="grounding/untrusted_via", nodes=[_DESIGN, _LOOSE_WALL],
        args=["shelf", "fits_against", 2.0], expect=1,
        because="the tolerance asked reaches through the link to what it points at"),
    Demonstration(
        contract="grounding/untrusted_via", nodes=[_DESIGN],
        args=["shelf", "fits_against"], expect_error="no node at",
        because="fitted against a wall that no longer exists: refused, not passed. "
                "A design outlives the thing it was measured against, and this is "
                "the day that happens"),
]

DEPENDS_UNTRUSTED_SPEC = [
    Demonstration(
        contract="grounding/depends_untrusted", args=["cut"], expect=0,
        nodes=[Node(id="cut", kind="cut", params={
                    "length": derived(2380.0, "fit solver", ["wall/width"])}),
               _SOUND_WALL],
        because="a computed value whose input was measured"),
    Demonstration(
        contract="grounding/depends_untrusted", args=["cut"], expect=1,
        nodes=[Node(id="cut", kind="cut", params={
                    "length": derived(2380.0, "fit solver", ["wall/width"])}),
               _GUESSED_WALL],
        because="a computed value resting on a guess is a guess wearing a number's "
                "clothes — and it is the computed value that looks trustworthy"),
    Demonstration(
        contract="grounding/depends_untrusted", args=["cut"], expect=1,
        nodes=[Node(id="cut", kind="cut", params={
                    "length": derived(2380.0, "fit solver", ["wall/width"]),
                    "margin": derived(20.0, "fit solver", ["wall/width"])}),
               _GUESSED_WALL],
        because="two values computed from one guess: a diamond counts once, so the "
                "number is how many doubtful inputs there are and not how often they "
                "were used"),
    Demonstration(
        contract="grounding/depends_untrusted", args=["cut"], expect=2,
        nodes=[Node(id="cut", kind="cut", params={
                    "length": derived(2380.0, "fit solver", ["mid/length"])}),
               Node(id="mid", kind="cut", params={
                    "length": derived(2390.0, "rough solver", ["wall/width"])}),
               _GUESSED_WALL],
        because="lineage is followed all the way, and the intermediate counts too: a "
                "derived value is itself never grounded, so a two-step chain off one "
                "guess answers 2"),
    Demonstration(
        contract="grounding/depends_untrusted", args=["cut"], expect=0,
        nodes=[Node(id="cut", kind="cut", params={
                    "length": derived(2380.0, "fit solver", ["ghost/width"])})],
        because="a lineage ref pointing at nothing is a broken ref, not a grounding "
                "claim — deliberately the OPPOSITE of untrusted_via's dangling link, "
                "which refuses. Lineage is a record of what happened and may name "
                "what is gone; a link is a dependency that must still be there"),
    Demonstration(
        contract="grounding/depends_untrusted", nodes=[_SOUND_WALL], args=["wall"],
        expect=0,
        because="a value with no lineage claims nothing upstream"),
]

GROUNDING_SPEC = {
    "grounding/untrusted": UNTRUSTED_SPEC,
    "grounding/untrusted_via": UNTRUSTED_VIA_SPEC,
    "grounding/depends_untrusted": DEPENDS_UNTRUSTED_SPEC,
}


def register_standard() -> None:
    for name, fn in GROUNDING_NATIVES.items():
        register_native(name, fn, GROUNDING_SPEC[name])


register_standard()
