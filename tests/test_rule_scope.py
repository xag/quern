"""run_rules(tree, path) judges the node at `path` and the nodes beneath it, and no other: a path
is a sequence of ids, so `a/b` is not under `a/bc`, however the strings start."""

from quern import KindDef, Quern, Rule, run_rules
from quern.tree import Node


def _tree() -> Quern:
    vocabulary = [KindDef(kind="part", description="a part")]
    rules = [Rule(name="a-part-is-judged", kind="part", expr="true")]
    t = Quern(vocabulary=vocabulary, rules=rules)
    t.root.children = [Node(id="pieces", kind="", children=[
        Node(id="bench", kind="part", children=[Node(id="seat", kind="part")]),
        Node(id="bench-side", kind="part", children=[Node(id="leg", kind="part")]),
        Node(id="benchmark", kind="part"),
    ])]
    return t


def test_a_run_under_a_path_judges_that_node_and_what_is_beneath_it_only():
    t = _tree()
    every = {r.node for r in run_rules(t)}
    for path in ("pieces/bench", "pieces/bench-side", "pieces/benchmark", "pieces", ""):
        under = {p for p in every if not path or p == path or p.startswith(path + "/")}
        assert {r.node for r in run_rules(t, path)} == under, path


def test_a_rule_on_one_path_runs_only_when_that_path_is_within_the_run_or_holds_it():
    t = _tree()
    t.rules.append(Rule(name="the-side-is-judged", path="pieces/bench-side", expr="true"))
    named = {r.node for r in run_rules(t, "pieces/bench") if r.rule == "the-side-is-judged"}
    assert named == set()
    assert {r.node for r in run_rules(t, "pieces") if r.rule == "the-side-is-judged"} == {"pieces/bench-side"}
    assert {r.node for r in run_rules(t, "pieces/bench-side/leg")
            if r.rule == "the-side-is-judged"} == {"pieces/bench-side"}
