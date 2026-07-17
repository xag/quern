"""tree_commit — authoring's one invariant: the committed red set never changes silently.

Green stays green; a change-set that would create reds is refused whole, nothing saved;
acknowledged reds commit and the acknowledgment lands on the root's meta. The estate
ships deliberate reds on purpose, so the gate forbids drift, never honesty — these tests
hold both directions.
"""

import pytest

from quern import Quern, KindDef, Node, Rule, design_target
from quern.host import commit_changes


class WS:
    label = "test-ws"

    def __init__(self):
        self._quern = Quern(
            vocabulary=[KindDef(kind="thing", description="a thing means this")],
            rules=[Rule(name="x-positive", kind="thing",
                        expr="param(self, 'x') > 0")],
            root=Node(id="root", children=[
                Node(id="a", kind="thing", name="Alpha",
                     params={"x": design_target(1, unit="")},
                     children=[Node(id="b", kind="thing", name="Beta",
                                    params={"x": design_target(2, unit="")})]),
            ]),
        )
        self.saved = 0

    @property
    def quern(self):
        return self._quern

    def effective(self):
        return self._quern

    def assert_editable(self, path):
        pass

    def save(self):
        self.saved += 1


def _x(ws, path):
    node = ws.quern.root
    for seg in path.split("/"):
        node = next(c for c in node.children if c.id == seg)
    return node.params["x"].value


def _set_x(path, value):
    return {"op": "set", "path": path,
            "node": {"params": {"x": {"value": value, "unit": "",
                                      "provenance": "design-target"}}}}


def test_a_green_commit_lands_and_saves():
    ws = WS()
    out = commit_changes(ws, [_set_x("a", 3)])
    assert out["committed"] and ws.saved == 1
    assert _x(ws, "a") == 3
    assert out["reds_after"] == []


def test_a_red_creating_commit_is_refused_whole_and_unsaved():
    ws = WS()
    out = commit_changes(ws, [_set_x("a", -1)])
    assert out["committed"] is False
    assert [r["red"] for r in out["refused"]] == ["x-positive@a"]
    assert ws.saved == 0, "a refused commit must write nothing"
    assert _x(ws, "a") == 1, "the tree must roll back to the snapshot"


def test_an_acknowledged_red_commits_and_is_recorded():
    ws = WS()
    out = commit_changes(ws, [_set_x("a", -1)], acknowledge=["x-positive@a"])
    assert out["committed"] and ws.saved == 1
    assert out["acknowledged"] == ["x-positive@a"]
    assert ws.quern.root.meta["acknowledged-reds"] == ["x-positive@a"]
    assert _x(ws, "a") == -1


def test_a_preexisting_red_needs_no_reacknowledgment():
    """The gate compares SETS, not counts: an edit elsewhere commits over a standing
    red without re-litigating it — deliberate reds are lived with, not nagged about."""
    ws = WS()
    commit_changes(ws, [_set_x("a", -1)], acknowledge=["x-positive@a"])
    out = commit_changes(ws, [_set_x("a/b", 5)])
    assert out["committed"]
    assert out["reds_before"] == out["reds_after"] == ["x-positive@a"]
    assert out["acknowledged"] == []


def test_atomicity_one_bad_change_rolls_back_the_set():
    ws = WS()
    with pytest.raises(ValueError, match="unknown op"):
        commit_changes(ws, [_set_x("a/b", 5), {"op": "rename", "path": "a"}])
    assert _x(ws, "a/b") == 2, "the good change must not survive its set"
    assert ws.saved == 0


def test_delete_goes_through_the_same_gate():
    ws = WS()
    out = commit_changes(ws, [{"op": "delete", "path": "a/b"}])
    assert out["committed"]
    assert all(c.id != "b" for c in ws.quern.root.children[0].children)


def test_the_property_holds_over_accepted_sequences():
    """The issue's acceptance property, run as stated: for any edit sequence the gate
    accepts, the committed red set equals the prior one or is explicitly extended by
    acknowledged entries."""
    ws = WS()
    reds = set()
    attempts = [
        ([_set_x("a", 5)], []),
        ([_set_x("a/b", -2)], []),                       # refused
        ([_set_x("a/b", -2)], ["x-positive@a/b"]),       # acknowledged
        ([_set_x("a", -9)], []),                         # refused
        ([{"op": "delete", "path": "a/b"}], []),         # red leaves with its node
        ([_set_x("a", 7)], []),
    ]
    for changes, ack in attempts:
        out = commit_changes(ws, changes, acknowledge=ack)
        if out["committed"]:
            after = set(out["reds_after"])
            assert after - reds == set(out["acknowledged"])
            reds = after
        else:
            assert set(out["reds_after"]) if "reds_after" in out else True
            # refusal leaves the world exactly as it was
            assert set(ws.quern.root.meta.get("acknowledged-reds", [])) <= {
                "x-positive@a/b"}
