"""quern.app_host — the semantic navigator, served as an MCP App (SEP-1865).

The Quern is the shared context of codesign: the model reads and edits it through
the generic `tree_*` verbs, and the human needs the same grip — see the tree,
navigate its semantics (kinds, provenance, rules), and coedit it. This module
serves that UI two ways over one Workspace:

- **MCP App** — `register_app(mcp, get_ws)` adds a `ui://quern/navigator.html`
  resource (`text/html;profile=mcp-app`) and a `tree_app` entry tool carrying
  `_meta.ui.resourceUri`. In an Apps-capable client (claude.ai, Claude Desktop,
  VS Code) the tool result renders as the navigator, and every interaction in
  the iframe goes through `callServerTool` — the SAME tree_* tools the model
  uses. Human and model hold one tree with the same verbs.
- **Dev server** — `serve_dev(get_ws)` serves the identical HTML on localhost
  with a `POST /rpc` bridge, for a plain browser: verification and coediting
  need no Apps-capable client.

Deliberately not geometric: no shapes, no 3D — this is the *meaning* view
(kinds with their prose, params with provenance and grounding, links, rules
with pass/fail). Rendering shapes stays a domain concern (quern.geometry_host).

Importing this needs the MCP SDK: install `quern[host]`.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tree as treemod
from .host import Resolver

APP_URI = "ui://quern/navigator.html"
APP_MIME = "text/html;profile=mcp-app"

# The iframe imports the official bridge SDK from this CDN; the host enforces
# CSP, so the domain must be declared on the tool that opens the app.
_CSP = {"resourceDomains": ["https://cdn.jsdelivr.net"]}


def app_html() -> str:
    return (resources.files("quern") / "app.html").read_text(encoding="utf-8")


def register_app(mcp: FastMCP, get_ws: Resolver) -> None:
    """Register the navigator UI resource and its `tree_app` entry tool.

    Call alongside `register_tree_tools` — the app drives the tree through
    those generic verbs; this module adds only the entry point and the HTML.
    """

    @mcp.resource(APP_URI, name="Quern navigator", mime_type=APP_MIME)
    def navigator_html() -> str:
        return app_html()

    @mcp.tool(
        structured_output=True,
        meta={"ui": {"resourceUri": APP_URI, "visibility": ["model", "app"],
                     "csp": _CSP}},
    )
    def tree_app() -> dict[str, Any]:
        """Open the Quern navigator — an interactive view of the tree and its
        semantics (kinds, params with provenance, links, rules) where the user
        can browse and coedit. Returns the root slice; the UI then navigates
        and edits through the same tree_* tools you use."""
        ws = get_ws()
        if isinstance(ws, str):
            return {"error": ws}
        composed = ws.effective()
        data = composed.root.model_dump(exclude_none=True)
        _prune(data, 2)
        semantics = treemod.semantics_at(composed, "", 2)
        if semantics:
            data["semantics"] = semantics
        data["label"] = ws.label
        return data


def _prune(data: dict[str, Any], depth: int) -> None:
    if depth <= 0:
        data.pop("children", None)
        return
    for child in data.get("children", []):
        _prune(child, depth - 1)


# --- the dev bridge: the same verbs over plain HTTP, for a plain browser ------

def _dispatch(ws, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Serve the five verbs the app uses, in the MCP result envelope
    ({structuredContent} or {content: [{type: 'text', text}]}), so the HTML
    normalizes both transports identically."""

    def text(t: str) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": t}]}

    def structured(d: dict[str, Any]) -> dict[str, Any]:
        return {"structuredContent": d}

    if name == "tree_app":
        composed = ws.effective()
        data = composed.root.model_dump(exclude_none=True)
        _prune(data, 2)
        semantics = treemod.semantics_at(composed, "", 2)
        if semantics:
            data["semantics"] = semantics
        data["label"] = ws.label
        return structured(data)

    if name == "tree_get":
        composed = ws.effective()
        node = treemod.get_node(composed, args.get("path", ""))
        if node is None:
            return structured({"error": f"no node at '{args.get('path', '')}'"})
        data = node.model_dump(exclude_none=True)
        if args.get("depth") is not None:
            _prune(data, int(args["depth"]))
        semantics = treemod.semantics_at(composed, args.get("path", ""),
                                         args.get("depth"))
        if semantics:
            data["semantics"] = semantics
        return structured(data)

    if name == "tree_find":
        hits = treemod.find_nodes(
            ws.effective(), query=args.get("query"), kind=args.get("kind"),
            has_param=args.get("has_param"), links_to=args.get("links_to"),
            under=args.get("under", ""), current_only=args.get("current_only", False),
            limit=int(args.get("limit", 20)))
        return structured({"matches": [
            {"path": p, "kind": n.kind or None, "name": n.name or None,
             "params": sorted(n.params) or None}
            for p, n in hits]})

    if name == "tree_set":
        path = args["path"]
        ws.assert_editable(path)
        treemod.set_node(ws.quern, path, args.get("node") or {})
        ws.save()
        return text(f"set '{path}'.")

    if name == "tree_delete":
        path = args["path"]
        ws.assert_editable(path)
        treemod.delete_node(ws.quern, path)
        ws.save()
        return text(f"deleted '{path}'.")

    if name == "tree_check":
        results = treemod.run_rules(ws.effective(), args.get("path", ""))
        if not results:
            return text("no rules apply — register some with tree_rule.")
        lines = []
        for r in results:
            state = "PASS" if r.ok else "FAIL"
            where = f" @ {r.node}" if r.node else ""
            detail = f" ({r.detail})" if r.detail else ""
            lines.append(f"{state} {r.rule}{where}{detail}")
        return text("\n".join(lines))

    return structured({"error": f"unknown tool '{name}'"})


def serve_dev(get_ws: Resolver, port: int = 8765, open_browser: bool = True) -> None:
    """Serve the navigator on http://127.0.0.1:{port} for a plain browser —
    same HTML, same verbs, POST /rpc as the bridge. Blocks until Ctrl-C."""
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    html = app_html().encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):
            if self.path != "/rpc":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            try:
                req = json.loads(body or b"{}")
                ws = get_ws()
                if isinstance(ws, str):
                    out = {"structuredContent": {"error": ws}}
                else:
                    out = _dispatch(ws, req.get("name", ""), req.get("arguments") or {})
            except Exception as e:  # surface, never crash the server
                out = {"structuredContent": {"error": str(e)}}
            payload = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"quern navigator: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
