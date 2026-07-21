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
with pass/fail). Rendering shapes stays a domain concern, registered by the
domain's own host module; quern ships none.

Importing this needs the MCP SDK: install `quern[host]`.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from mcp.server.fastmcp import FastMCP

from .host import Resolver, register_tree_tools, slice_at

APP_URI = "ui://quern/navigator.html"
APP_MIME = "text/html;profile=mcp-app"

# The iframe imports the official bridge SDK from this CDN; the host enforces
# CSP, so the domain must be declared on the tool that opens the app.
_CSP = {"resourceDomains": ["https://cdn.jsdelivr.net"]}

# The MCP Apps extension id (SEP-1865). A server that serves ui:// resources
# MUST say so in its initialize capabilities — a spec-conforming host that
# never hears this ignores every `_meta.ui` and renders nothing, silently.
UI_EXTENSION = "io.modelcontextprotocol/ui"


def app_html() -> str:
    return (resources.files("quern") / "app.html").read_text(encoding="utf-8")


def declare_ui_capability(mcp: FastMCP) -> None:
    """Declare the MCP Apps extension in the server's initialize capabilities.

    The SDK's ServerCapabilities predates the extension but allows extra
    fields, so the declaration rides initialization as data. Idempotent —
    `register_app` calls it, and a consumer registering a second app over the
    same server may call it again freely."""
    server = mcp._mcp_server
    if getattr(server.create_initialization_options, "_declares_ui", False):
        return
    orig = server.create_initialization_options

    def with_ui(notification_options=None, experimental_capabilities=None):
        opts = orig(notification_options, experimental_capabilities)
        ext = getattr(opts.capabilities, "extensions", None) or {}
        ext[UI_EXTENSION] = {"mimeTypes": [APP_MIME]}
        opts.capabilities.extensions = ext  # ServerCapabilities: extra="allow"
        return opts

    with_ui._declares_ui = True
    server.create_initialization_options = with_ui


def register_app(mcp: FastMCP, get_ws: Resolver) -> None:
    """Register the navigator UI resource and its `tree_app` entry tool.

    Call alongside `register_tree_tools` — the app drives the tree through
    those generic verbs; this module adds only the entry point and the HTML.
    """
    declare_ui_capability(mcp)

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
        # The root slice tree_get would return, plus the one thing the app needs and a
        # tree read has no business carrying: whose workspace this is. Shared with
        # tree_get rather than rebuilt — the two copies had already drifted apart in
        # how they pruned.
        data = slice_at(ws, "", 2)
        data["label"] = ws.label
        return data


# --- the dev bridge: the same verbs over plain HTTP, for a plain browser ------

def _bridge_tools(get_ws: Resolver) -> FastMCP:
    """A private FastMCP carrying the REAL tool surface, so the dev server serves the
    same code the model calls.

    This used to be a hand-written `_dispatch` that re-implemented each verb over the
    Workspace. Two implementations of one surface is one too many, and the drift was not
    hypothetical: a tool added to the host was simply absent over HTTP until someone
    noticed (`tree_solver`), and the two slice builders pruned differently. Registering
    the genuine tools costs one in-process server object and removes the entire class of
    bug — a verb that works for the model now works for the browser by construction.
    """
    mcp = FastMCP("quern-navigator")
    register_tree_tools(mcp, get_ws)
    register_app(mcp, get_ws)
    return mcp


def _envelope(structured: Any, content: Any) -> dict[str, Any]:
    """A tool result in the shape the page's `norm()` reads, for either transport.

    FastMCP gives a `-> str` tool an output schema of `{result: <string>}` and sends the
    wrapper as structuredContent. The page wants text tools as `{text: ...}`, so the
    wrapper is unwrapped here — and, more importantly, in `norm()` itself, because the
    real MCP transport delivers that same wrapper and the page was reading `.text` off
    it and finding nothing.
    """
    if isinstance(structured, dict) and list(structured) == ["result"]             and isinstance(structured["result"], str):
        return {"content": [{"type": "text", "text": structured["result"]}]}
    if structured is not None:
        return {"structuredContent": structured}
    text = getattr((content or [None])[0], "text", None)
    return {"content": [{"type": "text", "text": text}]} if text is not None else {}


def _dispatch(mcp: FastMCP, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a real registered tool and hand back its MCP result envelope."""
    import asyncio

    res = asyncio.run(mcp.call_tool(name, args))
    content, structured = res if isinstance(res, tuple) else (None, res)
    return _envelope(structured, content)



def serve_dev(get_ws: Resolver, port: int = 8765, open_browser: bool = True) -> None:
    """Serve the navigator on http://127.0.0.1:{port} for a plain browser —
    same HTML, same verbs, POST /rpc as the bridge. Blocks until Ctrl-C."""
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    mcp = _bridge_tools(get_ws)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        def do_GET(self):
            # Read per request, not once at startup. The page is a file on disk that a
            # developer is editing WHILE this serves it, and a snapshot taken at boot
            # silently serves stale HTML — an edit appears to have no effect, which is
            # a far more expensive minute than the file read it saves.
            body = app_html().encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/rpc":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            try:
                req = json.loads(body or b"{}")
                # The workspace is resolved by the tools themselves (each calls get_ws),
                # exactly as it is under a real MCP host — no pre-resolution here, or the
                # bridge would be making a decision the tool surface owns.
                out = _dispatch(mcp, req.get("name", ""), req.get("arguments") or {})
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
