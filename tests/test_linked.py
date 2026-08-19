"""`linked` / `linked_current` / `backlinked`: the traversals the grammar lacked.

#46: graph domains (mindmap's contradictions, epure's observability) grew parallel
Python checkers or demoted relations to child nodes because no rule could range
over a node's links. These verbs are the answer: what a node points at over any
link as paths a rule can count, the current-only form for open-tension rules, and
the symmetric read. Each test drives the verb through `run_rules`, because a verb
the grammar cannot reach is not an answer to #46.
"""

from quern import Quern, Rule, linked, linked_current, run_rules, set_node


def sample() -> Quern:
    """Two claims in tension, a question one of them answers, and a revision."""
    tree = Quern()
    set_node(tree, "coffee-helps", {"kind": "claim"})
    set_node(tree, "coffee-harms", {
        "kind": "claim", "links": {"contradicts": ["coffee-helps"]}})
    set_node(tree, "how-much-coffee", {"kind": "question"})
    set_node(tree, "dose-decides", {
        "kind": "claim", "links": {"answers": ["how-much-coffee"]}})
    return tree


def test_linked_returns_the_targets_that_resolve():
    tree = sample()
    assert linked(tree, "coffee-harms", "contradicts") == ["coffee-helps"]
    assert linked(tree, "coffee-helps", "contradicts") == []


def test_a_dangling_target_is_dropped_not_raised():
    """The dangling half is `unsupported`'s finding; this verb answers what is
    actually there, so a rule over it cannot crash on a hole."""
    tree = sample()
    set_node(tree, "wild", {
        "kind": "claim", "links": {"contradicts": ["nothing-there"]}})
    assert linked(tree, "wild", "contradicts") == []


def test_linked_current_drops_a_superseded_target():
    """A `contradicts` link to a superseded node is a tension somebody worked;
    only a link to a CURRENT node is still open."""
    tree = sample()
    assert linked_current(tree, "coffee-harms", "contradicts") == ["coffee-helps"]
    set_node(tree, "coffee-is-dose-dependent", {
        "kind": "claim", "links": {"supersedes": ["coffee-helps"]}})
    assert linked_current(tree, "coffee-harms", "contradicts") == []
    # the plain traversal still sees it: the node exists, only its currency went
    assert linked(tree, "coffee-harms", "contradicts") == ["coffee-helps"]


def test_an_open_tension_rule_fires_through_the_grammar():
    """The mindmap rule #46 could not carry: a current node holding a contradicts
    link to a current node is an open tension. Red while both stand, green once
    one is superseded — the false-to-green edge is the revision being worked."""
    tree = sample()
    tree.rules = [Rule(
        name="an-open-tension-is-worked", kind="claim",
        expr="superseded(self) or len(linked_current(self, 'contradicts')) == 0")]

    red = [r for r in run_rules(tree) if not r.ok]
    assert [r.node for r in red] == ["coffee-harms"]

    set_node(tree, "coffee-is-dose-dependent", {
        "kind": "claim", "links": {"supersedes": ["coffee-helps"]}})
    assert all(r.ok for r in run_rules(tree))


def test_backlinked_reads_the_symmetric_and_reaches_the_grammar():
    """An answered question knows it is answered without holding a link itself."""
    tree = sample()
    tree.rules = [Rule(
        name="a-question-with-an-answer-is-answered", kind="question",
        expr="len(backlinked(self, 'answers')) >= 1")]
    assert all(r.ok for r in run_rules(tree))

    set_node(tree, "why-mornings", {"kind": "question"})
    red = [r for r in run_rules(tree) if not r.ok]
    assert [r.node for r in red] == ["why-mornings"]
