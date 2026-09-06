"""`quern serve`: the tree_* tools with no host written by hand.

The awesome-mcp-servers listing described a server that did not exist — `quern[host]`
was a library, and every server over it had been written by a domain. These tests
hold the server to the two things a listing checker and a first user both do: start
it over stdio and ask what it offers, then author a node and find it in tree.json.
"""

import asyncio
import json
import os
import sys

from quern import Quern
from quern.serve import DirectoryWorkspace, build_server


def _call(mcp, name, args):
    res = asyncio.run(mcp.call_tool(name, args))
    contents, structured = res if isinstance(res, tuple) else (res, None)
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured if structured is not None else contents[0].text


def test_an_empty_directory_is_an_empty_tree_and_a_write_lands_in_tree_json(tmp_path):
    ws = DirectoryWorkspace(tmp_path / "t")
    assert ws.quern.root.children == []
    ws.quern.set("alpha", {"kind": "decision", "name": "the first decision"})
    ws.save()
    on_disk = Quern.model_validate_json((tmp_path / "t" / "tree.json").read_text("utf-8"))
    assert on_disk.get("alpha").name == "the first decision"
    assert not (tmp_path / "t" / "tree.json.tmp").exists()


def test_the_tree_survives_a_restart(tmp_path):
    first = DirectoryWorkspace(tmp_path)
    first.quern.set("alpha", {"kind": "decision", "name": "kept"})
    first.save()
    again = DirectoryWorkspace(tmp_path)
    assert again.quern.get("alpha").name == "kept"


def test_the_tools_author_a_tree_over_the_directory(tmp_path):
    mcp = build_server(tmp_path)
    _call(mcp, "tree_vocabulary", {"kind": "decision", "description": "a choice made"})
    _call(mcp, "tree_set", {"path": "alpha",
                            "node": {"kind": "decision", "name": "one decision"}})
    hits = _call(mcp, "tree_find", {"kind": "decision"})
    assert [m["path"] for m in hits["matches"]] == ["alpha"]
    saved = json.loads((tmp_path / "tree.json").read_text("utf-8"))
    assert saved["root"]["children"][0]["id"] == "alpha"
    assert saved["vocabulary"][0]["kind"] == "decision"


def test_the_navigator_app_is_registered(tmp_path):
    mcp = build_server(tmp_path)
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "tree_app" in names and "tree_brief" in names


def test_the_server_starts_over_stdio_and_lists_its_tools(tmp_path):
    """What a listing checker does: spawn `quern serve`, initialize, ask for the tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def ask():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "quern.cli", "serve", str(tmp_path / "srv")],
            env={**os.environ, "QUERN_FLIGHT": "0"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                return init.serverInfo.name, sorted(t.name for t in tools.tools)

    name, tools = asyncio.run(ask())
    assert name == "quern"
    assert {"tree_get", "tree_set", "tree_brief", "tree_check", "tree_app"} <= set(tools)
