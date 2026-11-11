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

Several processes may share the directory - a server and a one-off run, two workers of
one server (#70). Each call starts from the file as it is on disk (`fresh`, the resolver
`build_server` registers), and `save` writes under a lock taken on `tree.json.lock` and
only if the file is still the one this process read: a write that lost the race is refused
with `TreeChanged`, which names the fix (repeat the write), instead of overwriting the
other process's change without a word.

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

import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import _mcp
from ._mcp import Server, ToolError
from .app_host import register_app
from .host import register_tree_tools
from .library import Library
from .tree import KindDef, Quern

TREE_FILE = "tree.json"


class TreeChanged(ToolError):
    """Another process wrote the tree after this one read it: nothing was saved. A
    `ToolError`, so the caller reads the reason and the fix on either MCP major."""


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """An exclusive lock on `path` across processes, held for the block."""
    f = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:          # LK_LOCK gave up after its own retries
                    continue
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        f.close()


def _replace(tmp: Path, target: Path) -> None:
    """`os.replace`, retried while Windows refuses it because a reader holds the file."""
    for _ in range(100):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, target)


class DirectoryWorkspace:
    """A `host.Workspace` over one directory: `tree.json` beside a `library/`."""

    def __init__(self, root: Path | str, label: str | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.label = label or self.root.resolve().name
        self._library = Library(self.root / "library")
        self._tree_path = self.root / TREE_FILE
        self._lock_path = self.root / (TREE_FILE + ".lock")
        self._load()

    def _stamp(self) -> tuple[int, int] | None:
        try:
            st = self._tree_path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def _disk(self) -> bytes | None:
        try:
            return self._tree_path.read_bytes()
        except FileNotFoundError:
            return None

    def _load(self) -> None:
        self._read_stamp = self._stamp()
        data = self._disk()
        self._read_digest = hashlib.sha256(data).hexdigest() if data is not None else None
        self._quern = (Quern.model_validate_json(data.decode("utf-8"))
                       if data is not None else Quern())

    def fresh(self, caller: Any = None) -> "DirectoryWorkspace":
        """This workspace, reloaded first when another process changed the file: the
        resolver to register, so every call starts from what is on disk."""
        if self._stamp() != self._read_stamp:
            self._load()
        return self

    @property
    def quern(self) -> Quern:
        return self._quern

    def effective(self) -> Quern:
        # Non-strict: a pin whose package is missing from the library must not make
        # every read fail; tree_package is where the hole is reported.
        return self._library.effective(self._quern, strict=False)

    def assert_editable(self, path: str, caller: Any = None) -> None:
        pass  # the whole tree is the caller's to edit

    def save(self) -> None:
        """Write the tree, under the lock and only over the file this process read."""
        text = (self._quern.model_dump_json(indent=2, exclude_defaults=True) + "\n").encode("utf-8")
        with _locked(self._lock_path):
            data = self._disk()
            if (hashlib.sha256(data).hexdigest() if data is not None else None) != self._read_digest:
                raise TreeChanged(
                    f"{self._tree_path} was written by another process after this one read "
                    "it, so this write was not saved (it would have erased that change). "
                    "Repeat the write: the next call starts from the file as it is now.")
            tmp = self._tree_path.with_suffix(f".json.{os.getpid()}.tmp")
            tmp.write_bytes(text)
            _replace(tmp, self._tree_path)
            self._read_stamp = self._stamp()
            self._read_digest = hashlib.sha256(text).hexdigest()

    @property
    def blob_dir(self) -> Path:
        return self._library.blob_dir

    @property
    def library(self) -> Library:
        return self._library

    def starter_vocabulary(self) -> list[KindDef]:
        return []


def build_server(root: Path | str, label: str | None = None,
                 host: str = "127.0.0.1", port: int = 8000) -> Server:
    """The server, unstarted: every `tree_*` verb and the navigator app over the
    directory's Workspace. Tests call the tools on it directly; `serve` runs it."""
    ws = DirectoryWorkspace(root, label)
    mcp = _mcp.new_server(
        "quern", host=host, port=port,
        instructions=(
            f"A quern tree at {ws.root.resolve()}: nodes with kinds, params, links and "
            "payloads, whose semantics (vocabulary, rules, solvers) are data in the same "
            "tree. Start with tree_brief for what currently binds, tree_vocabulary for "
            "what kinds mean, tree_check for what is red. Edit with tree_set / "
            "tree_delete / tree_commit; every write is saved to tree.json."))
    register_tree_tools(mcp, ws.fresh)
    register_app(mcp, ws.fresh)
    return mcp


def serve(root: Path | str = ".quern", transport: str = "stdio",
          host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the server until the client hangs up (stdio) or Ctrl-C (HTTP)."""
    _mcp.run(build_server(root, host=host, port=port), transport)
