"""`tree_find(where=...)`: the nodes a condition in the rule grammar holds for (#75).

The search finds nodes whose words match; the questions a reader brings are structural
("which state has no deadline"), and the only way to ask one was to write a rule and read
its failures among every other red.
"""

import pytest

from quern import Quern, find_nodes, set_node
from quern.host import register_tree_tools
from quern.navigate import ReadOnlyWorkspace


def states() -> Quern:
    tree = Quern()
    set_node(tree, "deadlines/d1", {"kind": "deadline"})
    set_node(tree, "roles/ana", {"kind": "role"})
    set_node(tree, "obj/draft", {"kind": "state", "links": {"deadline": ["deadlines/d1"],
                                                            "held_by": ["roles/ana"]}})
    set_node(tree, "obj/review", {"kind": "state", "links": {"held_by": ["roles/ana"]}})
    set_node(tree, "obj/done", {"kind": "state", "params": {"days": {"value": 3, "unit": "d"}}})
    return tree


def test_the_condition_keeps_the_nodes_it_holds_for():
    hits = find_nodes(states(), kind="state", where="len(linked(self, 'deadline')) == 0")
    assert [p for p, _ in hits] == ["obj/review", "obj/done"]


def test_a_node_the_condition_reads_something_absent_on_is_not_kept():
    hits = find_nodes(states(), kind="state", where="param(self, 'days') > 1")
    assert [p for p, _ in hits] == ["obj/done"]


def test_the_limit_counts_kept_nodes_not_candidates():
    hits = find_nodes(states(), kind="state", where="len(linked(self, 'deadline')) == 0",
                      limit=1)
    assert [p for p, _ in hits] == ["obj/review"]


def test_a_condition_that_does_not_parse_is_an_error_not_an_empty_answer():
    with pytest.raises(ValueError):
        find_nodes(states(), kind="state", where="len(linked(self, 'deadline') ==")


def test_the_tool_returns_the_error_to_the_caller():
    from quern import _mcp
    import asyncio

    mcp = _mcp.new_server("t")
    ws = ReadOnlyWorkspace(states(), "t")
    register_tree_tools(mcp, lambda: ws)
    _, out = asyncio.run(_mcp.call_tool(mcp, "tree_find",
                                        {"kind": "state", "where": "nope(self) =="}))
    assert "error" in out
    _, out = asyncio.run(_mcp.call_tool(mcp, "tree_find",
                                        {"kind": "state", "where": "count(self) == 0"}))
    assert [m["path"] for m in out["matches"]] == ["obj/draft", "obj/review", "obj/done"]
