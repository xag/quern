"""bom.app_host — the semantic navigator: registration, dispatch, HTML."""

import anyio

from bom import Bom, KindDef, Node, Rule, design_target
from bom.app_host import APP_MIME, APP_URI, _dispatch, app_html, register_app
from bom.library import Library


class WS:
    label = "test-ws"

    def __init__(self, tmp):
        self._bom = Bom(
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
    def bom(self):
        return self._bom

    def effective(self):
        return self._bom

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
    for verb in ("tree_app", "tree_get", "tree_set", "tree_find", "tree_check",
                 "tree_delete", "callServerTool", "/rpc"):
        assert verb in html


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
    assert ws.bom.get("a").name == "Alpha2"

    check = _dispatch(ws, "tree_check", {})["content"][0]["text"]
    assert "PASS x-positive @ a" in check

    _dispatch(ws, "tree_delete", {"path": "a/b"})
    assert ws.bom.get("a/b") is None

    bad = _dispatch(ws, "tree_get", {"path": "nope"})["structuredContent"]
    assert "error" in bad
