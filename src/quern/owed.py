"""What the vocabulary implies and no rule states — the expected-predicate matrix.

A KindDef DECLARES shape: the params a node of the kind is expected to carry, and
the links it may hang. Each declaration implies an obvious predicate — *a K states
its p*, *what a K's L points at still stands* — and the obvious ones are exactly
the ones nobody writes down, because everybody can see them. Every adopter that
authored these did it by hand and stopped somewhere: a claim's confidence got its
rule, a thesis's conviction got its rule, and a noise-band's k got nothing, with no
record that anything was skipped.

This module derives the full matrix from a vocabulary and computes which cells the
rules actually cover, so "do we have the obvious laws?" has a computed answer with
a named remainder — the same move coverage made for surfaces and strings, applied
to predicates. And the tiers split (the founder's push, 2026-08-19): the FLOOR is
generated — presence for a declared param (`states`), no holes for a declared link
(`dangling == 0`) — because those need no domain knowledge, each ships with the
counter-example the publish gate demands, and `floor()` emits them as data any
package or tree can adopt. Only the SHARPENING stays the domain's: a range
(«0..1»), a tolerance, a link's meaning — a generated sharp rule would be a guess
wearing a law's name. An authored rule on a cell supersedes its floor: `floor()`
emits only the owed cells, so regeneration never fights the author.

The generator itself is held complete against the metamodel, mechanically: every
field a KindDef can carry is either MAPPED to a predicate family here or EXEMPTED
with its reason, and a test walks `KindDef.model_fields` and fails the moment a new
field arrives unmapped — a generator's blind spot cannot be added silently, which
is the only honest answer to "how do you know the generator is complete."

Coverage is by mention: a rule scoped to the kind (or unscoped, running everywhere)
whose expr names the param or the link covers the cell. The scan reads expr source —
the core owns its own grammar, so a string scan is legitimate HERE where an external
consumer's would be #44's workaround; the day exprs are first-class objects this
becomes an AST walk.

    python -m quern owed <project>                 # over ledger/tree.py:build
    python -m quern owed --module pkg.py:PACKAGE   # over a package's own vocabulary
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tree import KindDef, Node, Rule

# THE GENERATOR'S OWN DENOMINATOR. Every KindDef field is either mapped to a
# predicate family or exempted with its reason; tests/test_owed.py walks
# KindDef.model_fields against this and fails on any field neither names —
# so quern growing the metamodel breaks this generator loudly, never silently.
KINDDEF_FIELDS_MAPPED = {
    "params": "presence predicates (states) + the sharpening the hint describes",
    "links": "resolution predicates (dangling == 0) + the meaning the hint "
             "describes",
}
KINDDEF_FIELDS_EXEMPT = {
    "kind": "the scope itself — every cell is keyed by it",
    "description": "prose for the next designer; claims nothing checkable",
    "operations": "capabilities, not claims — each is gated at publish by its "
                  "own demonstrations",
    "convention": "names a namespace, never a node; the matrix skips it whole",
}

# THE SECOND DENOMINATOR: the verb table. The channel walk above proves the
# generator READS every declaration; it does not prove it emits every predicate
# a declaration implies. What a declaration can imply is bounded by what the
# grammar can ASK about it — the rule environment's verbs, an enumerable dict —
# so every verb is classified here: `floor` (a trivially-safe assertion this
# module emits), or an exemption with the reason no floor exists for it. A test
# walks the live env against this table, so a verb landing in the grammar
# (`linked` did, the day before this table) breaks the generator loudly until
# somebody decides its floor — out loud — instead of the schema set staying a
# judgment call nobody can audit.
GRAMMAR_VERBS = {
    # verb -> (disposition, why)
    "states": ("floor", "presence of a declared param — emitted per owed cell"),
    "dangling": ("floor", "no holes in a declared link — emitted per owed cell"),
    "param": ("sharpening", "reads the value; any assertion about it (a range, "
              "a bound) is the meaning the hint describes — the domain's"),
    "params_of": ("sharpening", "the aggregate read; same reason as param"),
    "linked": ("query", "returns paths and asserts nothing; assertions over it "
               "encode what the link MEANS, which is the domain's"),
    "linked_current": ("query", "same — currency-filtered traversal"),
    "backlinked": ("query", "same — the symmetric read"),
    "unsupported": ("domain-meaning", "whether a superseded target is a defect "
                    "depends on the link: rests_on legitimately convicts, "
                    "contradicts legitimately points at worked revisions — no "
                    "floor holds for every link name"),
    "superseded": ("covered-elsewhere", "current-belief hygiene is ledger@'s: "
                   "its supersession rules own this verb's obvious laws"),
    "uses": ("covered-elsewhere", "reuse hygiene is param resolution's own "
             "semantics; a dangling uses target already refuses at param()"),
    "where_used": ("query", "the symmetric read of uses; asserts nothing"),
    "nodes": ("query", "structural enumeration; a count claim over it is a "
              "domain cardinality, not a floor"),
    "count": ("query", "same — children arity is the domain's to bound"),
    "at": ("query", "positional read for trace rules"),
    "index": ("query", "same"),
    "parent": ("query", "path arithmetic"),
    "before": ("query", "trace ordering; which orderings MUST hold is the "
               "model's claim, generated from the semantic-model vocabulary "
               "once its actions declare fields — the named next build"),
    "preceding": ("query", "same"),
    "following": ("query", "same"),
    "rollup": ("query", "aggregation; what must roll up to what is a domain "
               "conservation law"),
    "tally": ("query", "same"),
    "said_words": ("covered-elsewhere", "the cost budgets are ledger@'s "
                   "fits-its-reader rules"),
    "solve": ("covered-elsewhere", "a contract's own laws travel as its "
              "demonstrations, re-proven at every publish and sync"),
    "ctx": ("covered-elsewhere", "runtime evidence windows are vigil's: "
            "a-criterion-is-watchable owns their hygiene"),
    "abs": ("combinator", "arithmetic; no subject of its own"),
    "min": ("combinator", "arithmetic; no subject of its own"),
    "max": ("combinator", "arithmetic; no subject of its own"),
    "sum": ("combinator", "arithmetic; no subject of its own"),
    "len": ("combinator", "arithmetic; no subject of its own"),
}


@dataclass
class Cell:
    """One implied predicate: a kind's declared param or link, and who covers it."""
    kind: str
    subject: str                       # "param:<name>" or "link:<name>"
    hint: str                          # the declaration's own prose
    covered_by: list[str] = field(default_factory=list)

    @property
    def owed(self) -> bool:
        return not self.covered_by


def _mentions(rule: Rule, name: str) -> bool:
    # the quoted name is how the grammar reaches both params and links:
    # param(self, 'p'), params_of(..., 'p'), unsupported/linked/linked_current/
    # backlinked(self, 'l')
    return f"'{name}'" in rule.expr or f'"{name}"' in rule.expr


def matrix(vocabulary: list[KindDef], rules: list[Rule]) -> list[Cell]:
    """Every implied cell, covered or owed. Convention kinds carry no nodes and
    imply nothing; a kind with neither params nor links contributes no cells —
    structure is not a claim."""
    cells: list[Cell] = []
    for kd in vocabulary:
        if kd.convention:
            continue
        in_scope = [r for r in rules
                    if r.kind == kd.kind or (r.kind is None and not r.path)]
        for p, hint in (kd.params or {}).items():
            cells.append(Cell(kd.kind, f"param:{p}", hint,
                              [r.name for r in in_scope if _mentions(r, p)]))
        for l, hint in (kd.links or {}).items():
            cells.append(Cell(kd.kind, f"link:{l}", hint,
                              [r.name for r in in_scope if _mentions(r, l)]))
    return cells


def floor(vocabulary: list[KindDef], rules: list[Rule]
          ) -> tuple[list[Rule], list[tuple[str, Node]]]:
    """The generated tier for every OWED cell, as data: a presence rule per unread
    param, a no-holes rule per unread link — each with the refuting node the
    publish gate demands (a rule that cannot reject anything cannot be published).
    Only owed cells emit, so an authored rule on a cell retires its floor at the
    next regeneration; the emitted descriptions say they are generated and what
    sharpening is still the domain's."""
    out_rules: list[Rule] = []
    refuters: list[tuple[str, Node]] = []
    for c in matrix(vocabulary, rules):
        if not c.owed:
            continue
        what, _, name = c.subject.partition(":")
        if what == "param":
            rule = Rule(
                name=f"a-{c.kind}-states-its-{name.replace('_', '-')}",
                kind=c.kind, expr=f"states(self, '{name}')",
                description=f"generated floor: the vocabulary declares "
                            f"'{name}' ({c.hint}) — presence is checked here; "
                            "the range or tolerance is the domain's to sharpen, "
                            "superseding this rule")
            refuters.append((rule.name, Node(
                id=f"a-{c.kind}-missing-{name.replace('_', '-')}", kind=c.kind,
                name=f"a {c.kind} that never states its {name}")))
        else:
            rule = Rule(
                name=f"a-{c.kind}-{name.replace('_', '-')}-link-resolves",
                kind=c.kind, expr=f"dangling(self, '{name}') == 0",
                description=f"generated floor: the vocabulary declares the "
                            f"'{name}' link ({c.hint}) — a stored target that "
                            "resolves to nothing is a broken record; what the "
                            "link MEANS is the domain's to state, superseding "
                            "this rule")
            refuters.append((rule.name, Node(
                id=f"a-{c.kind}-with-a-dangling-{name.replace('_', '-')}",
                kind=c.kind,
                name=f"a {c.kind} whose {name} link points at nothing",
                links={name: ["nowhere/that/exists"]})))
        out_rules.append(rule)
    return out_rules, refuters


def report(vocabulary: list[KindDef], rules: list[Rule]) -> str:
    cells = matrix(vocabulary, rules)
    lines: list[str] = []
    for c in cells:
        mark = "owed" if c.owed else "ok  "
        who = ("no rule reads it" if c.owed
               else ", ".join(sorted(set(c.covered_by))))
        lines.append(f"  {mark}  {c.kind:<18} {c.subject:<24} {who}")
    covered = sum(1 for c in cells if not c.owed)
    lines.append("")
    lines.append(f"{covered} of {len(cells)} implied predicate(s) covered by a "
                 "rule; the owed list is the worklist, computed from the "
                 "vocabulary itself.")
    if not cells:
        lines = ["  the vocabulary declares no params and no links - "
                 "nothing is implied, nothing is owed."]
    return "\n".join(lines)
