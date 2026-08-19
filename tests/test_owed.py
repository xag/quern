"""`owed`: the expected-predicate matrix, computed from the vocabulary.

Every KindDef declaration implies an obvious predicate — a K states its p, what a
K's L points at still stands — and the obvious ones are the ones nobody writes
down. The matrix makes the omission computable: covered cells name their rules,
owed cells name nothing, and the answer to "do we have the obvious laws?" stops
being remembered. Guilty and clean cases per behavior, in the house style.
"""

from quern import KindDef, Rule
from quern.owed import matrix, report

VOCAB = [
    KindDef(kind="claim", description="an assertion",
            params={"confidence": "0..1"},
            links={"supports": "what it backs",
                   "contradicts": "what it tensions"}),
    KindDef(kind="topic", description="structure only"),
    KindDef(kind="observation", description="a journal word",
            convention=True, params={"seq": "never a node's"}),
]

RULES = [
    Rule(name="claim-confidence", kind="claim",
         expr="param(self, 'confidence') >= 0 and param(self, 'confidence') <= 1"),
    Rule(name="an-open-tension-is-worked", kind="claim",
         expr="superseded(self) or len(linked_current(self, 'contradicts')) == 0"),
]


def test_covered_cells_name_their_rules_and_owed_cells_name_nothing():
    cells = {(c.kind, c.subject): c for c in matrix(VOCAB, RULES)}
    assert cells[("claim", "param:confidence")].covered_by == ["claim-confidence"]
    assert cells[("claim", "link:contradicts")].covered_by == [
        "an-open-tension-is-worked"]
    # the omission the matrix exists to surface: declared, read by nothing
    assert cells[("claim", "link:supports")].owed


def test_structure_and_conventions_imply_nothing():
    kinds = {c.kind for c in matrix(VOCAB, RULES)}
    assert "topic" not in kinds        # no params, no links: not a claim
    assert "observation" not in kinds  # a convention names no nodes


def test_a_rule_on_another_kind_covers_nothing_here():
    """Mention without scope is coincidence, not coverage: a rule bound to a
    different kind never runs on this one, whatever names its expr contains."""
    stray = [Rule(name="elsewhere", kind="thesis",
                  expr="param(self, 'confidence') >= 0")]
    cells = {(c.kind, c.subject): c for c in matrix(VOCAB, stray)}
    assert cells[("claim", "param:confidence")].owed


def test_an_unscoped_rule_covers_because_it_runs_everywhere():
    everywhere = [Rule(name="global-confidence",
                       expr="param(self, 'confidence') >= 0")]
    cells = {(c.kind, c.subject): c for c in matrix(VOCAB, everywhere)}
    assert cells[("claim", "param:confidence")].covered_by == ["global-confidence"]


def test_the_report_counts_and_the_empty_vocabulary_says_so():
    out = report(VOCAB, RULES)
    assert "2 of 3 implied predicate(s) covered" in out
    assert "owed" in out and "link:supports" in out
    assert "nothing is implied, nothing is owed" in report([], [])
