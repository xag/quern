"""The design ledger: decisions, hypotheses and debts, in a substrate that can check them.

A project's reasoning is normally written where nothing can read it — a README caveat,
a commit message, a comment above the function. That record is not worthless, but it is
inert: it states a condition and then cannot notice when the condition is violated. The
caveat "someone had better check this before launch" sits there being true while the
thing launches. Prose does not fire.

This package makes the ledger the same kind of thing as the rest of the tree: nodes with
kinds, params that carry their own grounding, and rules that go red. The claims it lets
you write are the three every project makes and then loses:

- a **decision** — a choice, and the alternatives it rejected. The alternatives are nodes,
  not a sentence, because "what did we already rule out, and why" is the question a later
  reader actually asks, and the one a rewrite silently discards.
- a **hypothesis** — a belief held provisionally, carrying the observation that would kill
  it. A belief with no falsification condition is not a hypothesis; it is a mood.
- a **debt** — something known-unsound that is being carried on purpose, with the condition
  that discharges it. This is the one the substrate was already equipped for: `Quantity`
  carries `grounded` ("is this an observation I may act on?"), so a debt is simply a node
  whose params are not yet grounded, and discharging it means a competent reader checked
  them and vouched. WHO is competent is the domain's business and never the substrate's:
  grounding asks whether the thing was checked, not what kind of thing did the checking.

The load-bearing rule is `nothing-unsound-passes-a-gate`. A **gate** is any point past
which unsound things must not travel — a release, a publication, a cut, a trade. It links
`admits` at what it lets through, and the rule counts the ungrounded params on the other
end via `grounding/untrusted_via`. That contract already exists and already named this
case: "a domain that cuts material, a domain that commits capital, a domain that publishes
a claim — all three ask exactly this, and none of them should have to write it themselves."

Version 0.1.0, deliberately: the vocabulary is hardening against real consumers. Pins are
exact, so a project on 0.1.0 is never surprised by 0.2.0 — refine by republishing.

The substrate knows nothing of its consumers, and neither does this package: every example
below is generic. A domain names its own provenance labels ("machine-authored",
"self-reported", "preprint") and maps them onto the one predicate the core enforces.

SITING, PROVISIONAL AND KNOWN-WRONG (issue #19). This module should not be here. A
package living in the substrate's source means refining its vocabulary needs a *bom
release* — semantics frozen into code, innovation waiting for the next version, which is
the exact pathology this substrate exists to dissolve. It sits here anyway, today, because
a package reaches another project by only two routes — code inside bom, or copy-paste —
and copy-paste is worse. The discharge condition is the capitalization layer of #19: a
channel packages travel on as data, pinned by rev, refined by republishing, on a clock
that is not bom's. When that exists, this file moves onto it and the substrate goes back
to knowing nothing about how anyone designs.
"""

from __future__ import annotations

from .grounding import GROUNDING_PACKAGE  # noqa: F401  — importing registers its natives
from .library import CounterExample, Package
from .provenance import Quantity
from .tree import KindDef, Node, PackageRef, Rule


# --- vocabulary: what a ledger's kinds mean ----------------------------------------

VOCABULARY = [
    KindDef(
        kind="decision",
        description="A choice made deliberately, kept so a later reader can tell it "
        "from an accident. Its children are the alternatives it rejected — as nodes, "
        "so 'what did we already rule out, and why' survives the rewrite that deletes "
        "the comment. A decision that is later reversed is not edited: the new decision "
        "`supersedes` it, and the core's supersession verb keeps both readable.",
        links={"supersedes": "the decision this one replaces, if any"},
    ),
    KindDef(
        kind="alternative",
        description="An option that was considered and NOT taken, and why not "
        "(payload.why). Its value is entirely in being findable later: most bad "
        "re-litigation is someone re-proposing a thing that was already rejected for a "
        "reason nobody wrote down.",
    ),
    KindDef(
        kind="hypothesis",
        description="A belief held provisionally — something believed but not yet "
        "established. It must carry at least one falsification child; a belief with no "
        "condition that would kill it is not a hypothesis, it is a mood.",
    ),
    KindDef(
        kind="falsification",
        description="The observation that would kill the hypothesis above it. Carries a "
        "prose payload.claim and, where the claim is mechanically checkable, a "
        "payload.expr in the rule grammar plus payload.cadence — the same shape a "
        "watched criterion takes, so a ledger entry can graduate into a live check "
        "without being rewritten.",
    ),
    KindDef(
        kind="debt",
        description="Something known-unsound, carried deliberately, with its cost stated "
        "rather than forgotten. Its params hold the unsound values and are NOT grounded "
        "— that is what makes the debt legible to `grounding/*` and therefore to a gate. "
        "Discharging a debt is not deleting the node: it is someone competent checking "
        "those params and grounding them, which is exactly the act the debt was waiting "
        "for. The substrate does not care who that is — only that it happened.",
    ),
    KindDef(
        kind="discharge",
        description="The condition under which a debt is cleared — who must do what, and "
        "by when. A debt without one is not a debt, it is a permanent defect that has "
        "been dressed up as a plan.",
    ),
    KindDef(
        kind="gate",
        description="A point past which unsound things must not travel: a release, a "
        "publication, a cut, a trade. It links `admits` at whatever it lets through, and "
        "the rule below counts the ungrounded params on the other end. A gate is the "
        "only place a ledger stops being a record and starts being a brake.",
        links={"admits": "the nodes this gate lets through — each must be sound"},
    ),
]


# --- rules: the structural invariants of a ledger worth keeping ---------------------

RULES = [
    Rule(
        name="a-decision-names-what-it-rejected",
        kind="decision",
        description="A choice with no stated alternative is indistinguishable from an "
        "accident, and cannot be re-examined — there is nothing to re-examine it against.",
        expr="len(nodes('alternative', self)) >= 1",
    ),
    Rule(
        name="a-hypothesis-is-falsifiable",
        kind="hypothesis",
        description="A belief that cannot be killed by any observation is not being "
        "tested by the project; it is being assumed by it.",
        expr="len(nodes('falsification', self)) >= 1",
    ),
    Rule(
        name="a-debt-states-how-it-is-discharged",
        kind="debt",
        description="An unsound thing carried with no discharge condition is not debt, "
        "it is decay. The condition is what lets anyone else finish it.",
        expr="len(nodes('discharge', self)) >= 1",
    ),
    Rule(
        name="nothing-unsound-passes-a-gate",
        kind="gate",
        description="The load-bearing one. Whatever this gate admits must rest on "
        "observations, not on guesses: no ungrounded param may travel through it. This "
        "is the rule that turns a written-down caveat into a thing that stops a release.",
        expr="solve('grounding/untrusted_via', self, 'admits') == 0",
    ),
]


# --- examples: a sound ledger, exercising every rule --------------------------------
# A domain names its own provenance labels; these are deliberately plain.

def _verified(value: float, unit: str, source: str) -> Quantity:
    """A value someone competent has actually checked — the discharged end of a debt."""
    return Quantity(value=value, unit=unit, provenance="verified", grounded=True,
                    source=source)


def _unverified(value: float, unit: str, source: str) -> Quantity:
    """A value produced but never checked — the carried end of a debt."""
    return Quantity(value=value, unit=unit, provenance="unverified", grounded=False,
                    source=source)


EXAMPLES = [
    Node(
        id="chose-strict-validation",
        kind="decision",
        name="Validate every translation bundle against the reference bundle, key for key",
        payload={
            "rationale": "A bundle silently missing a key ships a blank string to a "
                         "reader who cannot tell us, in a language we cannot read.",
            "consequence": "Every copy change becomes an all-bundles change. That cost "
                           "is real and was accepted with open eyes; it is recorded here "
                           "so the next person meets it as a decision, not a surprise.",
        },
        children=[
            Node(id="fall-back-to-reference", kind="alternative",
                 name="Fall back to the reference bundle for a missing key",
                 payload={"why": "Cheaper per edit, but a visible fallback in the wrong "
                                 "language is a bug a reader reports; an invisible one "
                                 "is a bug nobody ever reports. Rejected — for now: if "
                                 "the edit cost bites, this is the first thing to revisit."}),
        ],
    ),
    Node(
        id="bundles-are-good-enough",
        kind="hypothesis",
        name="The generated bundles are good enough to publish unreviewed",
        payload={"held_because": "spot checks in the two languages we can read looked fine"},
        children=[
            Node(id="a-reader-reports-nonsense", kind="falsification",
                 name="A reader of that language reports the copy as wrong or unidiomatic",
                 payload={"claim": "One credible report of broken copy in any generated "
                                   "bundle falsifies this and the bundles must be read.",
                          "cadence": "on-report"}),
        ],
    ),
    Node(
        id="reviewed-bundle",
        kind="debt",
        name="A bundle that WAS generated unchecked, and has since been read",
        # Discharged: someone who reads the language read it, so the value is grounded.
        # The node stays — the debt is part of the record, not something to delete once paid.
        params={"strings": _verified(47, "string", "checked by a reader of that language")},
        children=[
            Node(id="read-it", kind="discharge",
                 name="Someone who reads the language checks every string",
                 payload={"who": "any competent reader of it", "done": "2026-07"}),
        ],
    ),
    Node(
        id="release",
        kind="gate",
        name="Publication: nothing unsound reaches a reader",
        links={"admits": ["reviewed-bundle"]},
    ),
]


# --- counter-examples: each rule must be able to reject its own defect ---------------

COUNTER_EXAMPLES = [
    CounterExample(
        rule="a-decision-names-what-it-rejected",
        because="a choice with no rejected alternative",
        node=Node(id="just-did-it", kind="decision",
                  name="We went with the obvious thing",
                  payload={"rationale": "it seemed right at the time"}),
    ),
    CounterExample(
        rule="a-hypothesis-is-falsifiable",
        because="a belief nothing could disprove",
        node=Node(id="it-will-be-fine", kind="hypothesis",
                  name="It will probably be fine"),
    ),
    CounterExample(
        rule="a-debt-states-how-it-is-discharged",
        because="an unsound thing carried with no way to finish it",
        node=Node(id="fix-later", kind="debt", name="We'll clean this up at some point",
                  params={"strings": _unverified(47, "string", "generator")}),
    ),
    CounterExample(
        rule="nothing-unsound-passes-a-gate",
        because="a release that publishes a value nobody ever checked",
        # Both nodes are needed: the gate AND what it admits. Staging the gate alone
        # would trip the rule for the wrong reason — a dangling link, not an unsound
        # one — and the proof would be a lie that reads like a proof.
        nodes=[
            Node(id="unread-bundle", kind="debt",
                 name="A machine-generated bundle nobody has read",
                 params={"strings": _unverified(47, "string", "generator")},
                 children=[
                     Node(id="read-it", kind="discharge",
                          name="Someone who reads the language checks every string",
                          payload={"who": "any competent reader of it"}),
                 ]),
            Node(id="release", kind="gate", name="Publication",
                 links={"admits": ["unread-bundle"]}),
        ],
    ),
]


LEDGER_PACKAGE = Package(
    name="ledger",
    version="0.1.0",
    description="The design ledger as checkable data: decisions carrying the "
                "alternatives they rejected, hypotheses carrying what would kill them, "
                "and debts carrying the condition that discharges them. A debt's params "
                "are ungrounded by construction, so `grounding/untrusted_via` can ask a "
                "gate — a release, a publication, a cut, a trade — whether anything "
                "unsound is about to pass through it. The point is not to write the "
                "caveat down; a README already does that, and a README cannot fire. The "
                "point is that the caveat goes red.",
    publisher="standard library",
    requires=[PackageRef(name="grounding", version=GROUNDING_PACKAGE.version)],
    vocabulary=VOCABULARY,
    rules=RULES,
    examples=EXAMPLES,
    counter_examples=COUNTER_EXAMPLES,
)


def build() -> Package:
    return LEDGER_PACKAGE
