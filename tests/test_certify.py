"""A certificate is what the standards a tree holds say of one node (quern.certify):
criteria name the rules, levels name the criteria, and the runner knows neither."""

import pytest

import quern.grounding  # noqa: F401 - registers the grounding natives and their explainers
from quern.certify import certificate
from quern.provenance import derived, inferred, measured
from quern.tree import Node, Quern, Rule

RULES = [
    Rule(name="a-tool-names-its-maker", kind="tool", expr="len(payload(self, 'maker', '')) > 0",
         description="A tool names its maker."),
    Rule(name="a-figure-rests-on-two-witnesses", kind="tool",
         expr="solve('grounding/thinly_witnessed', self) == 0",
         description="Every figure of a tool rests on two independent observations that agree."),
    Rule(name="a-figure-agrees-with-what-it-is-read-from", kind="tool",
         expr="solve('grounding/disagreeing', self) == 0",
         description="No document a figure is read from prints another value."),
    Rule(name="a-source-names-its-publisher", kind="source", expr="len(payload(self, 'publisher', '')) > 0"),
]


def standard(*, complete=("a-tool-names-its-maker",),
             reliable=("a-figure-rests-on-two-witnesses", "a-figure-agrees-with-what-it-is-read-from")) -> Node:
    return Node(id="standards", children=[
        Node(id="complete", kind="criterion", name="The entry is complete",
             payload={"applies_to": "tool", "measures": "completeness", "rules": list(complete)}),
        Node(id="reliable", kind="criterion", name="Its figures are reliable",
             payload={"applies_to": ["tool"], "measures": "reliability", "rules": list(reliable)}),
        Node(id="listed", kind="level", name="Shown in a list", payload={"of": "tool"},
             links={"requires": ["standards/complete"]}),
        Node(id="shared", kind="level", name="Taken into the shared packages", payload={"of": "tool"},
             links={"requires": ["standards/complete", "standards/reliable"]}),
        Node(id="other", kind="level", name="A level of another kind", payload={"of": "piece"},
             links={"requires": ["standards/complete"]}),
    ])


SOURCES = Node(id="sources", children=[
    Node(id="manual", kind="source", payload={"publisher": "A maker"}, children=[
        Node(id="data", kind="clause", params={"pad": measured(125.0, 0.0, "p. 13")})]),
    Node(id="page", kind="source", payload={"publisher": "A maker"}, children=[
        Node(id="specs", kind="clause", params={"pad": measured(125.0, 0.0, "page")})]),
    Node(id="other", kind="source", children=[
        Node(id="specs", kind="clause", params={"pad": inferred(150.0, "a post")})]),
])


def tree(tool: Node, std: Node | None = None, rules=RULES) -> Quern:
    t = Quern(rules=list(rules))
    t.root.children = [std or standard(), SOURCES, tool]
    return t


def sander(*refs, maker="A maker", value=125.0) -> Node:
    return Node(id="sander", kind="tool", payload={"maker": maker} if maker else {},
                params={"pad": derived(value, "read", list(refs))})


def test_a_subject_reaches_the_levels_whose_criteria_all_hold():
    cert = certificate(tree(sander("sources/manual/data/pad", "sources/page/specs/pad")), "sander")
    assert cert["kind"] == "tool" and all(c["held"] for c in cert["criteria"])
    assert cert["reached"] == ["standards/listed", "standards/shared"]  # the piece's level is not a tool's


def test_a_level_is_blocked_by_the_criteria_that_do_not_hold_and_the_red_says_what_it_saw():
    cert = certificate(tree(sander("sources/manual/data/pad")), "sander")
    assert cert["reached"] == ["standards/listed"]
    [shared] = [lv for lv in cert["levels"] if lv["level"] == "standards/shared"]
    assert shared["blocked_by"] == ["standards/reliable"]
    [reliable] = [c for c in cert["criteria"] if c["criterion"] == "standards/reliable"]
    [red] = reliable["reds"]
    assert red["rule"] == "a-figure-rests-on-two-witnesses" and red["verdict"] == "broken"
    assert red["says"].startswith("Every figure") and red["why"] == ["pad: 1 of 2 (sources/manual)"]


def test_a_disagreement_is_named_with_both_values():
    cert = certificate(tree(sander("sources/manual/data/pad", "sources/other/specs/pad")), "sander")
    whys = [w for c in cert["criteria"] for r in c["reds"] for w in r["why"]]
    assert "pad: 125 here, 150 at sources/other/specs/pad" in whys


def test_a_better_standard_changes_the_certificate_and_nothing_else():
    """The same tool and the same runner: the standard asks one witness where it asked two."""
    easier = [r if r.name != "a-figure-rests-on-two-witnesses"
              else Rule(name=r.name, kind="tool", expr="solve('grounding/thinly_witnessed', self, 1) == 0") for r in RULES]
    tool = sander("sources/manual/data/pad")
    assert "standards/shared" not in certificate(tree(tool), "sander")["reached"]
    assert "standards/shared" in certificate(tree(tool, rules=easier), "sander")["reached"]


def test_a_criterion_that_names_no_rule_of_the_subject_is_not_held():
    """A standard that names a rule nobody carries, or one that judges another kind, certifies nothing."""
    cert = certificate(tree(sander(), std=standard(complete=("a-rule-nobody-wrote", "a-source-names-its-publisher"))),
                       "sander")
    [complete] = [c for c in cert["criteria"] if c["criterion"] == "standards/complete"]
    assert complete["held"] is False
    assert {(r["rule"], r["detail"]) for r in complete["reds"]} == {
        ("a-rule-nobody-wrote", "no rule of that name"),
        ("a-source-names-its-publisher", "the rule judges nothing at or under the subject")}
    assert cert["reached"] == []


def test_a_missing_subject_is_refused():
    with pytest.raises(ValueError, match="no node at"):
        certificate(tree(sander()), "ghost")
