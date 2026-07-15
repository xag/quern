"""A write says what it broke.

Rules are only a judge if someone consults them. Leaving that to the caller's memory is
how a survey ends up full of defects with nothing in the loop to contradict it — so the
verdict arrives with the write that caused it, not only when asked.
"""

import pytest

from quern import Quern, KindDef, Rule
from quern.host import _relevant


def test_a_write_speaks_about_its_own_branch_and_the_ones_above_it():
    # the write itself, and anything under it
    assert _relevant("home/chambre", "home/chambre")
    assert _relevant("home/chambre/mur", "home/chambre")
    # a branch-wide rule that CONTAINS the write: it has plenty to say about a room
    # you just moved
    assert _relevant("home", "home/chambre")
    assert _relevant("", "home/chambre")          # a global rule


def test_a_write_stays_quiet_about_somebody_elses_branch():
    assert not _relevant("pieces/etagere", "home/chambre")
    assert not _relevant("home/sejour", "home/chambre")
    # ...and not a sibling that merely shares a prefix
    assert not _relevant("home/chambre-bis", "home/chambre")


# --- through the tools, on a workspace ---------------------------------------

class Ws:
    def __init__(self, rules=()):
        self._quern = Quern(vocabulary=[KindDef(kind="space", description="a room")],
                        rules=list(rules))

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
        raise NotImplementedError

    @property
    def library(self):
        raise NotImplementedError

    def starter_vocabulary(self):
        return []


@pytest.fixture
def tools():
    from mcp.server.fastmcp import FastMCP

    from quern.host import register_tree_tools

    ws = Ws([Rule(name="space-has-a-name", kind="space", expr="len(self) > 0",
                  description="placeholder, replaced per test")])
    mcp = FastMCP("t")
    register_tree_tools(mcp, lambda: ws)
    return mcp, ws


def _set(mcp, path, node):
    import asyncio
    res = asyncio.run(mcp.call_tool("tree_set", {"path": path, "node": node}))
    contents = res[0] if isinstance(res, tuple) else res
    return contents[0].text


def test_a_write_with_nothing_to_report_stays_terse(tools):
    mcp, ws = tools
    ws.quern.rules = []
    out = _set(mcp, "home/salon", {"kind": "space"})
    assert out == "set 'home/salon'. Render it with tree_render to see the result."


def test_a_write_that_breaks_a_rule_says_so(tools):
    mcp, ws = tools
    ws.quern.rules = [Rule(name="space-has-height", kind="space",
                         expr="param(self, 'height') > 0",
                         description="a room is a volume")]
    out = _set(mcp, "home/salon", {"kind": "space"})
    assert "set 'home/salon'." in out
    assert "FAIL space-has-height @ home/salon" in out

    fixed = _set(mcp, "home/salon", {"kind": "space", "params": {
        "height": {"value": 2500, "unit": "mm"}}})
    assert "FAIL" not in fixed


def test_a_write_hears_about_the_branch_rule_above_it(tools):
    """The one that matters for a survey: moving a room breaks a rule scoped to the
    whole survey, not to the room."""
    mcp, ws = tools
    ws.quern.rules = [Rule(name="at-most-one-room", path="home",
                         expr="count('home') <= 1",
                         description="a stand-in for any survey-wide rule")]
    assert "FAIL" not in _set(mcp, "home/salon", {"kind": "space"})
    out = _set(mcp, "home/chambre", {"kind": "space"})
    assert "FAIL at-most-one-room @ home" in out, out


def test_a_rule_that_explodes_does_not_make_the_write_look_failed(tools):
    mcp, ws = tools
    ws.quern.rules = [Rule(name="boom", kind="space", expr="solve('nope/nothing', self)")]
    out = _set(mcp, "home/salon", {"kind": "space"})
    assert out.startswith("set 'home/salon'.")  # the write happened, and says so
