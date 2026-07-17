"""quern.app_host — the semantic navigator: registration, dispatch, HTML."""

import anyio

from quern import Quern, KindDef, Node, Rule, design_target
from quern.app_host import APP_MIME, APP_URI, _dispatch, app_html, register_app
from quern.library import Library


class WS:
    label = "test-ws"

    def __init__(self, tmp):
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
        self._dir = tmp
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

    @property
    def blob_dir(self):
        return self._dir

    @property
    def library(self):
        return Library(self._dir)

    def starter_vocabulary(self):
        return []


def test_html_ships_and_drives_the_generic_verbs():
    html = app_html()
    # Reads go through the generic read verbs; every WRITE goes through the commit
    # gate — the app deliberately never calls bare tree_set/tree_delete, so a write
    # cannot change the committed red set silently.
    for verb in ("tree_app", "tree_get", "tree_find", "tree_check",
                 "tree_commit", "callServerTool", "/rpc"):
        assert verb in html
    for bare in ('call("tree_set"', 'call("tree_delete"'):
        assert bare not in html, "a write slipped past the commit gate"


def test_register_app_wires_tool_meta_and_resource(tmp_path):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("t")
    ws = WS(tmp_path)
    register_app(mcp, lambda: ws)

    tools = anyio.run(mcp.list_tools)
    tool = next(t for t in tools if t.name == "tree_app")
    assert tool.meta["ui"]["resourceUri"] == APP_URI

    resources_ = anyio.run(mcp.list_resources)
    res = next(r for r in resources_ if str(r.uri) == APP_URI)
    assert res.mimeType == APP_MIME


def test_dispatch_covers_the_app_surface(tmp_path):
    ws = WS(tmp_path)

    root = _dispatch(ws, "tree_app", {})["structuredContent"]
    assert root["label"] == "test-ws"
    assert root["semantics"]["kinds"]["thing"]["description"]

    got = _dispatch(ws, "tree_get", {"path": "a", "depth": 1})["structuredContent"]
    assert got["name"] == "Alpha"

    hits = _dispatch(ws, "tree_find", {"query": "beta"})["structuredContent"]
    assert [h["path"] for h in hits["matches"]] == ["a/b"]

    _dispatch(ws, "tree_set", {"path": "a", "node": {"name": "Alpha2"}})
    assert ws.saved == 1
    assert ws.quern.get("a").name == "Alpha2"

    check = _dispatch(ws, "tree_check", {})["content"][0]["text"]
    assert "PASS x-positive @ a" in check

    _dispatch(ws, "tree_delete", {"path": "a/b"})
    assert ws.quern.get("a/b") is None

    bad = _dispatch(ws, "tree_get", {"path": "nope"})["structuredContent"]
    assert "error" in bad


def test_register_app_declares_the_ui_extension_capability(tmp_path):
    """SEP-1865: a server serving ui:// resources MUST declare the extension in
    its initialize capabilities - a spec-conforming host that never hears it
    ignores every _meta.ui and renders nothing, silently. (Found the hard way:
    the navigator negotiated fine and never rendered.)"""
    from mcp.server.fastmcp import FastMCP

    from quern.app_host import UI_EXTENSION, declare_ui_capability

    ws = WS(tmp_path)
    mcp = FastMCP("test")
    register_app(mcp, lambda: ws)
    declare_ui_capability(mcp)  # idempotent: a second app may declare again
    opts = mcp._mcp_server.create_initialization_options()
    dumped = opts.capabilities.model_dump()
    assert dumped["extensions"][UI_EXTENSION] == {"mimeTypes": [APP_MIME]}
