"""The one place quern meets the MCP SDK, so `quern[host]` runs on mcp 1.x and 2.x.

mcp 2.0 renamed `FastMCP` to `MCPServer` (`mcp.server.mcpserver`), moved `host`/`port`
from the constructor to `run()`, made `call_tool` return a `CallToolResult` where 1.x
returned `(content, structured)`, and keeps the low-level server under another attribute.
Consumers of `quern[host]` sit on either major — a server that also imports a 2.x-only
library cannot hold 1.x, and one that pins 1.x for its own code cannot be forced onto 2.x
by bumping quern — so the host takes whichever is installed. Everything that differs
between the two goes through here; the decorators (`tool`, `resource`) are the same on both
and stay on the server object.
"""

from __future__ import annotations

from typing import Any

try:
    from mcp.server.mcpserver import Context, MCPServer as Server
    from mcp.server.mcpserver.exceptions import ToolError

    MAJOR = 2
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import Context, FastMCP as Server
    from mcp.server.fastmcp.exceptions import ToolError

    MAJOR = 1

# `Context` is what a tool declares to be handed the request it serves; both majors inject
# a parameter annotated with it, optional or not, and leave it out of the tool's schema.
# `ToolError` is a refusal a tool raises on purpose: 2.x hands the caller its message and
# reports any other exception as a bare "Error executing tool", so a reason meant for the
# caller is raised as one.
__all__ = ["Context", "Server", "ToolError", "MAJOR", "new_server", "run", "call_tool", "declare_extension",
           "capabilities"]


def new_server(name: str, *, instructions: str | None = None,
               host: str = "127.0.0.1", port: int = 8000) -> Server:
    """A server bound to `host`/`port` for an HTTP transport, on either major.

    1.x takes the binding at construction; 2.x takes it at `run()`, so it is kept on the
    object for `run` below to hand over."""
    if MAJOR == 1:
        return Server(name, host=host, port=port, instructions=instructions)
    server = Server(name, instructions=instructions)
    server._quern_bind = {"host": host, "port": port}
    return server


def run(server: Server, transport: str = "stdio") -> None:
    """Run until the client hangs up (stdio) or Ctrl-C (HTTP)."""
    if MAJOR == 1 or transport == "stdio":
        server.run(transport=transport)  # type: ignore[arg-type]
    else:
        server.run(transport, **getattr(server, "_quern_bind", {}))  # type: ignore[arg-type]


async def call_tool(server: Server, name: str, args: dict[str, Any]) -> tuple[Any, Any]:
    """Call a registered tool in process: `(content blocks, structured content)`.

    1.x answers a tuple for a tool with an output schema and a bare content list
    otherwise; 2.x always answers a `CallToolResult`."""
    res = await server.call_tool(name, args)
    if MAJOR == 2:
        return res.content, res.structured_content
    return res if isinstance(res, tuple) else (res, None)


def _lowlevel(server: Server) -> Any:
    return server._lowlevel_server if MAJOR == 2 else server._mcp_server


def declare_extension(server: Server, identifier: str, settings: dict[str, Any]) -> None:
    """Advertise an extension under `capabilities.extensions` in the initialize answer.

    2.x keeps the advertised extensions as a dict on the low-level server. 1.x's
    `ServerCapabilities` predates extensions but allows extra fields, so the declaration
    is added to the options it builds. Idempotent on both."""
    low = _lowlevel(server)
    if MAJOR == 2:
        low.extensions[identifier] = settings
        return
    declared = getattr(low.create_initialization_options, "_quern_extensions", None)
    if declared is not None:
        declared[identifier] = settings
        return
    orig = low.create_initialization_options
    declared = {identifier: settings}

    def with_extensions(notification_options=None, experimental_capabilities=None):
        opts = orig(notification_options, experimental_capabilities)
        ext = getattr(opts.capabilities, "extensions", None) or {}
        ext.update(declared)
        opts.capabilities.extensions = ext  # ServerCapabilities: extra="allow"
        return opts

    with_extensions._quern_extensions = declared
    low.create_initialization_options = with_extensions


def capabilities(server: Server) -> dict[str, Any]:
    """The capabilities this server would announce at initialize, as plain data."""
    return _lowlevel(server).create_initialization_options().capabilities.model_dump()
