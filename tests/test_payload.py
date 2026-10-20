"""`payload` and `contains`: the payload read (#45) and text containment (#60).

A rule could read params and links and nothing a node's payload holds, and could compare
a string only for equality. The adopters that needed either minted a kind per value of a
field, projected the field into a param at build time, or checked outside quern. Each test
drives the verb through `run_rules` where the issue's own example is a rule, because a verb
the grammar cannot reach answers neither issue.
"""

import pytest

from quern import Quern, Rule, contains, payload_at, run_rules, set_node


def governance() -> Quern:
    """Governance objects indexed as nodes: the record is the payload (#45's second case)."""
    tree = Quern()
    set_node(tree, "req-1", {"kind": "requirement", "payload": {
        "state": "Proposed", "owner": "ana", "description": "[SEC] encrypt at rest"}})
    set_node(tree, "req-2", {"kind": "requirement", "payload": {
        "state": "Approved", "description": "fast start"}})
    set_node(tree, "plan", {"kind": "plan", "payload": {"steps": [
        {"name": "draft", "owner": "ana", "tags": ["doc"]},
        {"name": "review", "owner": "tom", "tags": ["gate", "urgent"]},
        {"name": "ship"}]}})
    return tree


def test_a_field_reads_its_value_and_a_missing_one_reads_as_the_default():
    tree = governance()
    assert payload_at(tree, "req-1", "state") == "Proposed"
    assert payload_at(tree, "req-2", "owner") is None, "absent reads as None, as tree_find does"
    assert payload_at(tree, "req-2", "owner", "") == ""
    assert payload_at(tree, "nowhere", "state", "gone") == "gone"


def test_a_path_walks_nested_objects_and_maps_over_lists():
    """#45's third case: nested payload, values at a path inside list elements."""
    tree = governance()
    assert payload_at(tree, "plan", "steps.name") == ["draft", "review", "ship"]
    assert payload_at(tree, "plan", "steps.owner") == ["ana", "tom", None]
    assert payload_at(tree, "plan", "steps.owner", "-") == ["ana", "tom", "-"]
    assert payload_at(tree, "plan", "steps.tags") == ["doc", "gate", "urgent", None]


def test_a_state_scopes_a_rule_without_minting_a_kind():
    """The rule assay could not write: bind only the Proposed ones, by a payload field."""
    tree = governance()
    tree.rules = [Rule(
        name="a-proposed-requirement-has-an-owner", kind="requirement",
        expr="payload(self, 'state') != 'Proposed' or payload(self, 'owner', '') != ''")]
    assert all(r.ok for r in run_rules(tree))

    set_node(tree, "req-3", {"kind": "requirement", "payload": {"state": "Proposed"}})
    red = [r for r in run_rules(tree) if not r.ok]
    assert [r.node for r in red] == ["req-3"]


def test_a_fixed_fragment_in_a_varying_text_has_an_expression():
    """#60: a convention in a description, with no param per fragment."""
    tree = governance()
    tree.rules = [Rule(
        name="a-proposed-requirement-is-tagged", kind="requirement",
        expr="payload(self, 'state') != 'Proposed' or contains(payload(self, 'description', ''), '[SEC]')")]
    assert all(r.ok for r in run_rules(tree))

    set_node(tree, "req-4", {"kind": "requirement", "payload": {
        "state": "Proposed", "owner": "tom", "description": "no tag here"}})
    assert [r.node for r in run_rules(tree) if not r.ok] == ["req-4"]


def test_contains_over_a_list_searches_its_elements():
    tree = governance()
    tree.rules = [Rule(name="something-is-urgent", kind="plan",
                       expr="contains(payload(self, 'steps.tags'), 'urgent')")]
    assert all(r.ok for r in run_rules(tree))
    assert contains(["draft", "review"], "view")
    assert contains([1, 2, 3], 2) and not contains([1, 2, 3], 4)
    assert not contains(None, "x")


def test_contains_refuses_what_it_cannot_search():
    with pytest.raises(ValueError):
        contains(12, "1")
    with pytest.raises(ValueError):
        contains("abc", 1)


def test_the_trace_names_the_field_and_the_value_read():
    """#52's promise holds for the new verbs: a red arrives with what it saw."""
    tree = governance()
    set_node(tree, "req-3", {"kind": "requirement", "payload": {"state": "Proposed"}})
    tree.rules = [Rule(name="owned", kind="requirement",
                       expr="payload(self, 'owner', '') != ''")]
    red = next(r for r in run_rules(tree, trace=True) if not r.ok and r.node == "req-3")
    assert any(rd.call == "payload" and rd.args[1] == "owner" and rd.value == ""
               for rd in red.reads)
