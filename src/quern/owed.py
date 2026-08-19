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
to predicates. It generates the EXPECTATION, deliberately not the rules: an
existence check is free, but a range («0..1»), a tolerance, or a link's meaning is
the domain's to state, and a generated rule would be a guess wearing a law's name.

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

from .tree import KindDef, Rule


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
