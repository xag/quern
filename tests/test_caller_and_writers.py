"""#70: who is calling reaches the workspace, and the directory store keeps every writer's change.

1. A host given `identify` hands the caller to a resolver that takes one argument and to a
   guard that takes two, and stamps each node a write makes (`meta.created_by`,
   `meta.updated_by`). Resolvers and guards written before keep working as they were.
2. Two processes over one directory used to each write their own copy, and one change was
   lost without an error. Now each call starts from the file on disk, and a write that lost
   the race is refused (`TreeChanged`) rather than saved over the other one.
"""

import asyncio
import json
import subprocess
import sys
import textwrap

import pytest

from quern import KindDef, Node, Quern
from quern._mcp import call_tool, new_server
from quern.host import register_tree_tools
from quern.library import Library
from quern.serve import DirectoryWorkspace, TreeChanged, build_server


def call(mcp, name, args):
    content, structured = asyncio.run(call_tool(mcp, name, args))
    if structured is not None:
        return structured
    return "".join(getattr(c, "text", "") for c in content)


class TeamWS:
    """A workspace whose resolver and guard are told who is calling."""

    label = "team"

    def __init__(self, tmp):
        self._quern = Quern(vocabulary=[KindDef(kind="note", description="a note")],
                            root=Node(id="root"))
        self._dir = tmp
        self.resolved_for, self.guarded_for = [], []

    quern = property(lambda self: self._quern)

    def effective(self):
        return self._quern

    def assert_editable(self, path, caller):
        self.guarded_for.append(caller)
        if path.startswith("private/") and caller != "ana":
            raise PermissionError(f"{caller} may not write {path}")

    def save(self):
        pass

    blob_dir = property(lambda self: self._dir)
    library = property(lambda self: Library(self._dir))

    def starter_vocabulary(self):
        return []


def team_server(ws, who):
    mcp = new_server("team")

    def resolver(caller):
        ws.resolved_for.append(caller)
        return ws

    register_tree_tools(mcp, resolver, identify=lambda ctx: who[0])
    return mcp


def test_the_caller_reaches_the_resolver_and_the_guard_and_is_stamped(tmp_path):
    ws, who = TeamWS(tmp_path), ["ana"]
    mcp = team_server(ws, who)
    call(mcp, "tree_set", {"path": "n1", "node": {"kind": "note", "name": "first"}})
    assert ws.resolved_for == ["ana"] and ws.guarded_for == ["ana"]
    assert ws.quern.get("n1").meta == {"created_by": "ana", "updated_by": "ana"}

    who[0] = "ben"
    call(mcp, "tree_set", {"path": "n1", "node": {"meta": {"topic": "x"}}})
    # a write that replaces meta keeps who made the node
    assert ws.quern.get("n1").meta == {"topic": "x", "created_by": "ana", "updated_by": "ben"}

    call(mcp, "tree_commit", {"changes": [{"op": "set", "path": "n2", "node": {"kind": "note"}}]})
    assert ws.quern.get("n2").meta == {"created_by": "ben", "updated_by": "ben"}


def test_a_guard_can_say_yes_to_one_caller_and_no_to_another(tmp_path):
    ws, who = TeamWS(tmp_path), ["ben"]
    mcp = team_server(ws, who)
    with pytest.raises(Exception, match="ben may not write"):
        call(mcp, "tree_set", {"path": "private/n", "node": {"kind": "note"}})
    assert ws.quern.get("private/n") is None
    assert call(mcp, "tree_get", {"path": "private"}).get("error")    # nothing was made
    who[0] = "ana"
    call(mcp, "tree_set", {"path": "private/n", "node": {"kind": "note"}})
    assert ws.quern.get("private/n").meta["created_by"] == "ana"


def test_a_host_without_identify_writes_as_before(tmp_path):
    mcp = build_server(tmp_path)
    call(mcp, "tree_set", {"path": "n", "node": {"name": "plain"}})
    assert DirectoryWorkspace(tmp_path).quern.get("n").meta == {}


# --- several writers over one directory ---------------------------------------------

def test_a_call_starts_from_what_another_process_wrote(tmp_path):
    a, b = DirectoryWorkspace(tmp_path), DirectoryWorkspace(tmp_path)
    a.fresh().quern.root.children.append(Node(id="x"))
    a.save()
    b.fresh().quern.root.children.append(Node(id="y"))
    b.save()
    assert {c.id for c in DirectoryWorkspace(tmp_path).quern.root.children} == {"x", "y"}


def test_a_write_that_lost_the_race_is_refused_not_saved_over_the_other(tmp_path):
    a, b = DirectoryWorkspace(tmp_path), DirectoryWorkspace(tmp_path)
    a.fresh(), b.fresh()
    a.quern.root.children.append(Node(id="x"))
    a.save()
    b.quern.root.children.append(Node(id="y"))
    with pytest.raises(TreeChanged, match="Repeat the write"):
        b.save()
    assert [c.id for c in DirectoryWorkspace(tmp_path).quern.root.children] == ["x"]
    assert [c.id for c in b.fresh().quern.root.children] == ["x"]    # and b starts over


WRITER = textwrap.dedent("""
    import asyncio, sys
    from quern._mcp import call_tool
    from quern.serve import build_server
    mcp = build_server(sys.argv[1])
    for i in range(int(sys.argv[3])):
        while True:
            try:
                asyncio.run(call_tool(mcp, "tree_set",
                                      {"path": f"{sys.argv[2]}{i}", "node": {"name": "w"}}))
                break
            except Exception as e:
                if "Repeat the write" not in str(e):
                    raise
""")


def test_two_processes_writing_at_once_lose_no_change(tmp_path):
    script = tmp_path / "writer.py"
    script.write_text(WRITER, encoding="utf-8")
    store = tmp_path / "store"
    DirectoryWorkspace(store).save()
    procs = [subprocess.Popen([sys.executable, str(script), str(store), name, "15"])
             for name in ("a", "b")]
    assert [p.wait(timeout=240) for p in procs] == [0, 0]
    ids = {c.id for c in DirectoryWorkspace(store).quern.root.children}
    assert ids == {f"{n}{i}" for n in "ab" for i in range(15)}
