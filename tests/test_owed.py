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


def test_the_generator_is_held_complete_against_the_metamodel():
    """The only honest answer to 'how do you know the generator is complete':
    every field a KindDef can carry is either mapped to a predicate family or
    exempted with its reason, and a new field arriving in the metamodel fails
    this test until somebody decides which it is — out loud."""
    from quern.owed import KINDDEF_FIELDS_EXEMPT, KINDDEF_FIELDS_MAPPED
    fields = set(KindDef.model_fields)
    mapped, exempt = set(KINDDEF_FIELDS_MAPPED), set(KINDDEF_FIELDS_EXEMPT)
    assert mapped | exempt == fields, (
        f"unaccounted KindDef field(s): {sorted(fields - mapped - exempt)} — "
        "map each to a predicate family in KINDDEF_FIELDS_MAPPED, or exempt it "
        "with its reason in KINDDEF_FIELDS_EXEMPT. Never let a blind spot in "
        "silently.")
    assert not (mapped & exempt), "a field cannot be both mapped and exempted"


def test_the_floor_generates_only_the_owed_cells_and_each_rule_refutes():
    """The generated tier emits for the OWED cells only, so an authored rule
    retires its floor at regeneration; and each generated rule rejects its own
    refuting node, because a rule that cannot reject anything cannot be
    published."""
    from quern import Quern, run_rules, set_node
    from quern.owed import floor

    gen, refuters = floor(VOCAB, RULES)
    names = {r.name for r in gen}
    # covered cells emit nothing — the author's rule stands alone
    assert "a-claim-states-its-confidence" not in names
    assert names == {"a-claim-supports-link-resolves"}
    assert len(refuters) == len(gen)

    # the generated rule convicts its refuting node...
    stage = Quern(vocabulary=list(VOCAB), rules=gen)
    stage.root.children = [n for _, n in refuters]
    red = [r for r in run_rules(stage) if not r.ok]
    assert {r.rule for r in red} == names

    # ...and passes a sound node: a claim whose supports target exists
    sound = Quern(vocabulary=list(VOCAB), rules=gen)
    set_node(sound, "ground", {"kind": "claim"})
    set_node(sound, "leaner", {"kind": "claim",
                               "links": {"supports": ["ground"]}})
    assert all(r.ok for r in run_rules(sound))


def test_the_floor_presence_rule_convicts_and_passes_through_the_grammar():
    from quern import Quern, run_rules, set_node
    from quern.owed import floor

    bare = [KindDef(kind="band", description="a band",
                    params={"k": "multiples of vol"})]
    gen, refuters = floor(bare, [])
    assert [r.expr for r in gen] == ["states(self, 'k')"]

    stage = Quern(vocabulary=bare, rules=gen)
    set_node(stage, "silent", {"kind": "band"})
    set_node(stage, "stated", {"kind": "band",
                               "params": {"k": {"value": 2.0, "unit": ""}}})
    verdicts = {r.node: r.ok for r in run_rules(stage)}
    assert verdicts == {"silent": False, "stated": True}
