"""tree_verdicts: the verdicts a page marks and counts reds by, as data (#74).

The navigator parsed tree_check's printed report, and a printed report carries a node's
path but not its name, a rule's name but not its text, and drops the rules that name no
node. A page that counts reds by rule needs all of it.
"""

import asyncio

from quern import KindDef, Quern, Rule, _mcp, set_node
from quern.host import register_tree_tools, slice_at
from quern.navigate import ReadOnlyWorkspace


def tree() -> Quern:
    t = Quern(vocabulary=[KindDef(kind="state", description="a state"),
                          KindDef(kind="folder", description="a branch", section=True)],
              rules=[Rule(name="a-state-has-a-deadline", kind="state", description="bounded",
                          expr="len(linked(self, 'deadline')) > 0"),
                     Rule(name="nothing-is-empty", expr="count('') > 0"),
                     Rule(name="a-state-states-days", kind="state", expr="param(self, 'days') > 0")])
    set_node(t, "process", {"kind": "folder"})
    set_node(t, "process/permit/draft", {"kind": "state", "name": "Draft"})
    set_node(t, "process/permit/review", {"kind": "state", "name": "Review",
                                          "links": {"deadline": ["process"]}})
    return t


def call(name, args):
    mcp = _mcp.new_server("t")
    ws = ReadOnlyWorkspace(tree(), "t")
    register_tree_tools(mcp, lambda: ws)
    return asyncio.run(_mcp.call_tool(mcp, name, args))[1]


def test_each_verdict_carries_its_node_name_and_each_rule_its_text():
    out = call("tree_verdicts", {})
    broken = [v for v in out["verdicts"] if v["verdict"] == "broken"]
    assert broken == [{"rule": "a-state-has-a-deadline", "node": "process/permit/draft",
                       "name": "Draft", "verdict": "broken", "detail": None}]
    assert {v["verdict"] for v in out["verdicts"] if v["rule"] == "a-state-states-days"} == {"absent"}
    assert any(v["node"] == "" and v["rule"] == "nothing-is-empty" for v in out["verdicts"])
    rule = next(r for r in out["rules"] if r["name"] == "a-state-has-a-deadline")
    assert rule == {"name": "a-state-has-a-deadline", "kind": "state", "path": None,
                    "description": "bounded", "expr": "len(linked(self, 'deadline')) > 0"}


def test_the_slice_counts_the_kinds_beneath_it_at_any_depth():
    ws = ReadOnlyWorkspace(tree(), "t")
    assert slice_at(ws, "", 0, kinds=True)["kinds_under"] == {"folder": 1, "state": 2}
    assert slice_at(ws, "process", 0, kinds=True)["kinds_under"] == {"state": 2}
    assert "kinds_under" not in slice_at(ws, "", 0), "asked for, not sent on every read"
