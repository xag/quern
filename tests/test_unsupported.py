"""`unsupported`: does what a node leans on still stand?

The symmetric of `is_superseded`. That verb asks whether a node still holds;
this one follows an arbitrary domain link and asks whether its targets do. It
is what lets a rule fire on a claim whose grounds were withdrawn — the case a
flat record can only catch by someone remembering to re-read it.
"""

from quern import Quern, Rule, run_rules, set_node, unsupported


def sample() -> Quern:
    """Three claims resting on a decision that is about to be replaced."""
    tree = Quern()
    set_node(tree, "search-is-complete", {"kind": "decision"})
    set_node(tree, "cap-the-depth", {"kind": "decision"})
    # two claims lean on the first decision, one on the second
    set_node(tree, "last-word", {
        "kind": "decision", "links": {"rests_on": ["search-is-complete"]}})
    set_node(tree, "may-accuse", {
        "kind": "decision", "links": {"rests_on": ["search-is-complete"]}})
    set_node(tree, "depth-corrupts-proofs", {
        "kind": "hypothesis", "links": {"rests_on": ["cap-the-depth"]}})
    return tree


def test_nothing_is_unsupported_while_the_grounds_stand():
    tree = sample()
    assert unsupported(tree, "last-word", "rests_on") == []
    assert unsupported(tree, "depth-corrupts-proofs", "rests_on") == []


def test_superseding_the_grounds_unsupports_everything_resting_on_them():
    tree = sample()
    set_node(tree, "search-is-incremental", {
        "kind": "decision", "links": {"supersedes": ["search-is-complete"]}})

    assert unsupported(tree, "last-word", "rests_on") == ["search-is-complete"]
    assert unsupported(tree, "may-accuse", "rests_on") == ["search-is-complete"]
    # ...and only those: the third claim rests on a different decision
    assert unsupported(tree, "depth-corrupts-proofs", "rests_on") == []


def test_a_deleted_target_counts_as_unsupported():
    """Absence is the whole point. A node whose grounds were deleted rather than
    superseded is in more trouble than one whose grounds were replaced, not less,
    and the verb must not go quiet just because the target stopped resolving."""
    tree = sample()
    tree.root.children = [c for c in tree.root.children if c.id != "search-is-complete"]

    assert unsupported(tree, "last-word", "rests_on") == ["search-is-complete"]


def test_the_verb_reads_no_meaning_into_the_link_name():
    """`rests_on` is domain data. The core follows whatever link it is handed and
    tests currency; it knows nothing of ledgers."""
    tree = Quern()
    set_node(tree, "a", {"kind": "thing"})
    set_node(tree, "b", {"kind": "thing", "links": {"leans_on_the_fence": ["a"]}})
    set_node(tree, "c", {"kind": "thing", "links": {"supersedes": ["a"]}})

    assert unsupported(tree, "b", "leans_on_the_fence") == ["a"]
    assert unsupported(tree, "b", "rests_on") == []  # a link it does not have


def test_an_unknown_node_has_nothing_to_lean_on():
    assert unsupported(sample(), "no-such-node", "rests_on") == []


def test_the_rule_builtin_counts_so_a_rule_can_ask_for_zero():
    """The grounding convention: counts, not booleans — a rule wants `== 0` and a
    diagnostic wants to know how many."""
    tree = sample()
    tree.rules.append(Rule(
        name="what-a-decision-rests-on-still-stands",
        expr="unsupported(self, 'rests_on') == 0",
        kind="decision"))

    assert all(r.ok for r in run_rules(tree))

    set_node(tree, "search-is-incremental", {
        "kind": "decision", "links": {"supersedes": ["search-is-complete"]}})
    red = {r.node for r in run_rules(tree) if not r.ok}
    assert red == {"last-word", "may-accuse"}


def test_a_chain_of_supersessions_unsupports_every_link_in_it():
    """B replaces A, C replaces B. Anything resting on A OR on B is unsupported —
    the verb needs no transitive walk, because each superseded node is already not
    current in its own right. This is repolock's sequence (fail closed -> fail open
    -> stop guessing), where each decision fixed the hole the last one opened."""
    tree = Quern()
    set_node(tree, "fail-closed", {"kind": "decision"})
    set_node(tree, "fail-open", {
        "kind": "decision", "links": {"supersedes": ["fail-closed"]}})
    set_node(tree, "stop-guessing", {
        "kind": "decision", "links": {"supersedes": ["fail-open"]}})
    set_node(tree, "refusal-must-be-actionable", {
        "kind": "decision", "links": {"rests_on": ["fail-closed", "fail-open"]}})

    assert unsupported(tree, "refusal-must-be-actionable", "rests_on") == [
        "fail-closed", "fail-open"]
    # the head of the chain is current, and nothing rests on it yet
    assert unsupported(tree, "stop-guessing", "rests_on") == []
