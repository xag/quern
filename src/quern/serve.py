"""quern.serve — the `tree_*` tools as a standalone MCP server over one directory.

Until this module, `pip install quern[host]` bought a library: every server in the
estate wrote its own `Workspace` — the live tree, the read view, the write guard,
persistence, a blob store, a library — and registered the generic verbs over it.
That is the right shape for a domain with its own store, and the wrong first hour
for anyone who wants to author a tree from an MCP client and has no domain yet.
`quern serve DIR` is the Workspace they would otherwise write: one directory holds
the tree (`tree.json`) and its library (`library/`, packages and blobs), every
`tree_*` verb and the navigator app are registered over it, and the transport is
stdio, the one every MCP client speaks.

Deliberately the plainest store there is. The tree is a pydantic `Quern` written
whole on every commit, because the host's transactional commit (`commit_changes`)
snapshots and restores an in-memory `Quern`; the SQLite store scales beyond what
one JSON file should hold, and a domain that needs it writes its Workspace over
`quern.store.SqliteStore` as the scaled hosts do. The file is written atomically
(temp file, then replace) so a crash mid-save leaves the previous tree, not half
of one.

Vocabulary-blind, like the navigator: the server supplies no starter kinds. What a
kind means is whatever the tree's own vocabulary and its pinned packages say, and
the first act of an empty tree is `tree_vocabulary` — or `tree_package` to pin a
published one.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .app_host import register_app
from .host import register_tree_tools
from .library import Library
from .tree import KindDef, Quern

TREE_FILE = "tree.json"


class DirectoryWorkspace:
    """A `host.Workspace` over one directory: `tree.json` beside a `library/`."""

    def __init__(self, root: Path | str, label: str | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.label = label or self.root.resolve().name
        self._library = Library(self.root / "library")
        self._tree_path = self.root / TREE_FILE
        if self._tree_path.exists():
            self._quern = Quern.model_validate_json(
                self._tree_path.read_text(encoding="utf-8"))
        else:
            self._quern = Quern()

    @property
    def quern(self) -> Quern:
        return self._quern

    def effective(self) -> Quern:
        # Non-strict: a pin whose package is missing from the library must not make
        # every read fail; tree_package is where the hole is reported.
        return self._library.effective(self._quern, strict=False)

    def assert_editable(self, path: str) -> None:
        pass  # the whole tree is the caller's to edit

    def save(self) -> None:
        text = self._quern.model_dump_json(indent=2, exclude_defaults=True)
        tmp = self._tree_path.with_suffix(".json.tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, self._tree_path)

    @property
    def blob_dir(self) -> Path:
        return self._library.blob_dir

    @property
    def library(self) -> Library:
        return self._library

    def starter_vocabulary(self) -> list[KindDef]:
        return []


def build_server(root: Path | str, label: str | None = None,
                 host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """The server, unstarted: every `tree_*` verb and the navigator app over the
    directory's Workspace. Tests call the tools on it directly; `serve` runs it."""
    ws = DirectoryWorkspace(root, label)
    mcp = FastMCP(
        "quern", host=host, port=port,
        instructions=(
            f"A quern tree at {ws.root.resolve()}: nodes with kinds, params, links and "
            "payloads, whose semantics (vocabulary, rules, solvers) are data in the same "
            "tree. Start with tree_brief for what currently binds, tree_vocabulary for "
            "what kinds mean, tree_check for what is red. Edit with tree_set / "
            "tree_delete / tree_commit; every write is saved to tree.json."))
    register_tree_tools(mcp, lambda: ws)
    register_app(mcp, lambda: ws)
    return mcp


def serve(root: Path | str = ".quern", transport: str = "stdio",
          host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the server until the client hangs up (stdio) or Ctrl-C (HTTP)."""
    build_server(root, host=host, port=port).run(transport=transport)  # type: ignore[arg-type]
