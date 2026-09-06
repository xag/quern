"""Asking the host one question instead of the whole tree's.

Three tools that a client mirroring external objects into a tree had no way to
reach: check one rule at one node and see what it read (#53, #52), find by a
payload field's value rather than by a substring of prose (#54), and read the roll
and diff it against the one you kept from last time (#55).
"""

import asyncio
import json

import pytest

from quern import Quern, KindDef, Rule, design_target, set_node
from quern.library import Library


class Ws:
    label = "gov"

    def __init__(self, tmp):
        self._quern = Quern(
            vocabulary=[KindDef(kind="program", description="a programme of work")],
            rules=[
                Rule(name="opened-has-a-budget", kind="program",
                     expr="param(self, 'budget') > 0"),
                Rule(name="named", kind="program", expr="len(self) > 0"),
            ])
        set_node(self._quern, "alpha", {
            "kind": "program", "payload": {"state": "Opened", "ref": "P-1"},
            "params": {"budget": design_target(0, unit="EUR")}})
        set_node(self._quern, "beta", {
            "kind": "program", "payload": {"state": "Closed"},
            "params": {"budget": design_target(50, unit="EUR")}})
        self._dir = tmp

    @property
    def quern(self):
        return self._quern

    def effective(self):
        return self._quern

    def assert_editable(self, path):
        pass

    def save(self):
        pass

    @property
    def blob_dir(self):
        return self._dir

    @property
    def library(self):
        return Library(self._dir)

    def starter_vocabulary(self):
        return []


@pytest.fixture()
def tools(tmp_path):
    from mcp.server.fastmcp import FastMCP

    from quern.host import register_tree_tools

    ws = Ws(tmp_path)
    mcp = FastMCP("t")
    register_tree_tools(mcp, lambda: ws)
    return mcp, ws


def _call(mcp, name, args):
    """A tool's answer: text tools come back wrapped as {"result": "..."} by the
    server, exactly as the navigator's bridge unwraps them."""
    res = asyncio.run(mcp.call_tool(name, args))
    contents, structured = res if isinstance(res, tuple) else (res, None)
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured if structured is not None else contents[0].text


# --- one rule, one node, with the values behind it (#53, #52) -----------------

def test_a_named_rule_runs_alone(tools):
    mcp, _ = tools
    out = _call(mcp, "tree_check", {"rule": "named"})
    assert "named @ alpha" in out and "named @ beta" in out
    assert "opened-has-a-budget" not in out


def test_a_named_rule_at_one_node_reports_what_it_read(tools):
    """The question asked interactively: 'is this still wrong?' — and a red is only
    actionable with the value behind it."""
    mcp, _ = tools
    out = _call(mcp, "tree_check", {"path": "alpha", "rule": "opened-has-a-budget"})
    assert "FAIL opened-has-a-budget @ alpha" in out
    assert 'param("alpha", "budget") -> 0.0' in out
    assert "beta" not in out


def test_an_unnamed_check_prints_verdicts_and_no_trace(tools):
    """The default output is unchanged: a whole tree's trace is far larger than its
    verdicts, and every existing reader parses these lines."""
    mcp, _ = tools
    out = _call(mcp, "tree_check", {})
    assert "FAIL opened-has-a-budget @ alpha" in out
    assert "->" not in out


def test_a_rule_nobody_registered_is_an_error_not_an_empty_pass(tools):
    mcp, _ = tools
    out = _call(mcp, "tree_check", {"rule": "opened-has-a-budjet"})
    assert "no rule named" in out and "opened-has-a-budjet" in out


# --- scoping by a field's value (#54) ----------------------------------------

def test_find_scopes_by_a_payload_field(tools):
    mcp, _ = tools
    hits = _call(mcp, "tree_find", {"payload": {"state": "Opened"}})
    assert [m["path"] for m in hits["matches"]] == ["alpha"]

    both = _call(mcp, "tree_find", {"payload": {"state": ["Opened", "Closed"]}})
    assert [m["path"] for m in both["matches"]] == ["alpha", "beta"]


# --- the roll, and what changed since the last one (#55) ---------------------

def test_tree_roll_returns_the_roll_and_no_comparison_unasked(tools):
    mcp, _ = tools
    out = _call(mcp, "tree_roll", {})
    assert [e["path"] for e in out["roll"]] == ["alpha", "beta"]
    assert all(e["digest"] for e in out["roll"])
    assert "vanished" not in out


def test_tree_roll_against_a_kept_roll_reports_what_changed(tools):
    """The mirror's question on every refresh: what left scope, what was rewritten
    in place, what changed kind — against the roll the caller holds, never git."""
    mcp, ws = tools
    before = _call(mcp, "tree_roll", {})["roll"]

    ws.quern.root.children = [c for c in ws.quern.root.children if c.id != "beta"]
    set_node(ws.quern, "alpha", {"payload": {"state": "Closed"}})

    out = _call(mcp, "tree_roll", {"against": before})
    assert [e["path"] for e in out["vanished"]] == ["beta"]
    assert [e["path"] for e in out["rewritten"]] == ["alpha"]
    assert out["rekinded"] == []

    spared = _call(mcp, "tree_roll", {"against": before, "excused": ["beta"]})
    assert spared["vanished"] == []


def test_the_roll_is_json_a_client_can_hand_straight_back(tools):
    mcp, _ = tools
    out = _call(mcp, "tree_roll", {})
    assert json.loads(json.dumps(out["roll"])) == out["roll"]
