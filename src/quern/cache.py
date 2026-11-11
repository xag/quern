"""A native's answer kept while everything it read is unchanged.

A check runs every rule on every run, and the rules that cost are the ones that reach a
native: a proof, a sweep of witnesses, a derivation over source files. Most runs made while
editing change one entry or one file, and every other native answers what it answered the
last time. This module keeps those answers and gives one back only when it can show that
nothing the call read has moved.

What a call read is recorded as it runs, not guessed:

- the tree: the native is handed a tree that notes every path it reaches - a `get`, a
  `walk`, the `children` of a path - and the answer is kept with the digest of each of
  those subtrees. Reaching the tree any other way (its root, a copy, a reverse-index scan)
  notes the whole tree. A native that writes to the tree is not kept.
- files: every file opened and every directory listed while the call runs, through the
  interpreter's audit hook, with its size and modification time. Writing a file outside the
  cache, starting a process or opening a connection makes the answer unkeepable: what it
  depends on cannot be seen from here. A native whose declared reads cover what the
  processes it starts read registers with `spawns=True`, and starting one, or connecting
  to this machine's loopback (an event loop's own socket pair, a process it started), is
  then allowed.
- what the call cannot be seen reading: state the process loaded before the call (a parsed
  module kept in memory, data an earlier native loaded) is invisible to both. The native
  declares it when it registers (`register_native(..., reads=...)`): a function of the
  call's arguments naming the files and directories that state came from, or None when
  this call cannot say. `OPENS_ONLY` declares that the call reads nothing but the tree and
  what it opens while it runs. A native registered without `reads` is never kept.
- code: the answer is kept with the identity of every Python file of quern and of the
  native's own package, so an edit to either sends the call back to the run.

The key of a call is the contract's name, its arguments, the environment variables it
declares and the working directory; under it a few traces are kept, each the reads of one
run and the answer it gave. A lookup re-reads each trace's inputs - digests of subtrees,
sizes and times of files, listings of directories - and returns the first whose inputs are
all as they were. That is correct exactly when the native is a function of what it read,
which is what registering `reads` asserts. Exceptions are never kept, nor an answer that is
not plain JSON.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

CHECK_DEFAULT = ".quern/check"
KEPT_TRACES = 4

ReadsFn = Callable[..., "Iterable[str | os.PathLike] | None"]


def OPENS_ONLY(tree: Any, *args: Any) -> tuple:
    """The `reads` of a native that reads nothing outside the tree but the files it opens
    while it runs."""
    return ()


def _sha(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


# --- what the call reads of the tree -------------------------------------------------

WHOLE = ""


class TracedTree:
    """A tree that notes the paths a native reaches. The structural protocol is answered
    by the tree underneath; anything reached outside it notes the whole tree."""

    def __init__(self, tree: Any):
        object.__setattr__(self, "_tree", tree)
        object.__setattr__(self, "_paths", set())
        object.__setattr__(self, "_wrote", False)

    def get(self, path: str, depth: int | None = None):
        self._paths.add(str(path or "").strip("/"))
        return self._tree.get(path, depth) if depth is not None else self._tree.get(path)

    def walk(self, under: str = ""):
        self._paths.add(str(under or "").strip("/"))
        return self._tree.walk(under)

    def children(self, path: str):
        self._paths.add(str(path or "").strip("/"))
        return self._tree.children(path)

    def backlinks(self, name: str, target: str):
        self._paths.add(WHOLE)
        return self._tree.backlinks(name, target)

    def find(self, *args: Any, **kwargs: Any):
        self._paths.add(WHOLE)
        return self._tree.find(*args, **kwargs)

    def set(self, path: str, data: dict):
        object.__setattr__(self, "_wrote", True)
        return self._tree.set(path, data)

    def delete(self, path: str):
        object.__setattr__(self, "_wrote", True)
        return self._tree.delete(path)

    def __getattr__(self, name: str):
        self._paths.add(WHOLE)
        return getattr(self._tree, name)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, "_wrote", True)
        setattr(self._tree, name, value)


def _subtree_digest(tree: Any, path: str) -> str:
    if path == WHOLE:
        parts = [getattr(tree, "root", None)]
        for field in ("vocabulary", "rules", "solvers", "packages"):
            parts.append(getattr(tree, field, None))
        return _sha([p.model_dump(mode="json") if hasattr(p, "model_dump") else
                     [x.model_dump(mode="json") for x in p] if isinstance(p, list) else p
                     for p in parts])
    node = tree.get(path)
    return "absent" if node is None else _sha(node.model_dump(mode="json"))


# --- what the call reads outside the tree --------------------------------------------

_PROCESSES = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
              "os.startfile", "os.fork")
_NETWORK = ("socket.connect", "socket.getaddrinfo", "urllib.Request", "http.client.connect",
            "ftplib.connect", "smtplib.connect")
_MUTATES = ("os.remove", "os.rename", "os.replace", "os.rmdir", "os.mkdir", "shutil.rmtree",
            "shutil.move", "shutil.copyfile", "os.truncate", "os.chmod", "os.utime")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


class _Watch:
    def __init__(self, allowed: Path, spawns: bool = False):
        self.allowed = str(allowed.resolve())
        self.spawns = spawns
        self.files: set[str] = set()
        self.dirs: set[str] = set()
        self.unkeepable = ""


_watching: list[_Watch] = []
_hooked = [False]
_lock = threading.Lock()


def _abs(p: Any) -> str | None:
    if isinstance(p, bytes):
        p = os.fsdecode(p)
    if not isinstance(p, (str, os.PathLike)):
        return None
    try:
        return str(Path(os.fspath(p)).resolve())
    except (OSError, ValueError):
        return None


def _hook(event: str, args: tuple) -> None:
    if not _watching:
        return
    for w in list(_watching):
        if event == "open":
            path = _abs(args[0]) if args else None
            if path is None or "__pycache__" in path:
                continue
            mode, flags = (args[1] if len(args) > 1 else None), (args[2] if len(args) > 2 else 0)
            writes = (any(c in str(mode) for c in "wax+") if mode else bool((flags or 0) & _WRITE_FLAGS))
            if writes:
                if not path.startswith(w.allowed):
                    w.unkeepable = w.unkeepable or f"it wrote {path}"
            else:
                w.files.add(path)
        elif event in ("os.listdir", "os.scandir"):
            path = _abs(args[0] if args and args[0] is not None else ".")
            if path is not None:
                w.dirs.add(path)
        elif event.startswith(_PROCESSES) and not w.spawns:
            w.unkeepable = w.unkeepable or f"it called {event}"
        elif event.startswith(_NETWORK) and not (w.spawns and _loopback(event, args)):
            w.unkeepable = w.unkeepable or f"it called {event}"
        elif event.startswith(_MUTATES):
            path = _abs(args[0]) if args else None
            if path is None or not path.startswith(w.allowed):
                w.unkeepable = w.unkeepable or f"it called {event}"


def _loopback(event: str, args: tuple) -> bool:
    """A connection that stays on this machine's loopback: an event loop's own socket pair,
    or a process the native started. Anything else is the network."""
    if event == "socket.connect" and len(args) > 1:
        addr = args[1]
        host = addr[0] if isinstance(addr, tuple) and addr else None
    elif event == "socket.getaddrinfo" and args:
        host = args[0]
    else:
        return False
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    return str(host) in ("127.0.0.1", "::1", "localhost")


def _ensure_hook() -> None:
    with _lock:
        if not _hooked[0]:
            sys.addaudithook(_hook)
            _hooked[0] = True


_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}


def _file_state(path: str) -> list | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def _dir_state(path: str) -> str | None:
    try:
        return _sha(sorted(os.listdir(path)))
    except OSError:
        return None


def _expand(paths: Iterable[Any]) -> tuple[set[str], set[str]]:
    """Declared paths as (files, directories): a directory is every file under it, and its
    listing at every level, so a file added under it is seen."""
    files, dirs = set(), set()
    for p in paths:
        a = _abs(p)
        if a is None:
            continue
        if os.path.isdir(a):
            for here, subdirs, names in os.walk(a):
                subdirs[:] = [d for d in subdirs if d not in _SKIP_DIRS]
                dirs.add(str(Path(here).resolve()))
                files.update(str(Path(here, n).resolve()) for n in names)
        else:
            files.add(a)
    return files, dirs


# --- the code a call runs ------------------------------------------------------------

_CODE: dict[str, str] = {}


def _package_dir(module_name: str) -> str | None:
    top = module_name.split(".")[0]
    mod = sys.modules.get(top)
    f = getattr(mod, "__file__", None)
    if not f:
        return None
    p = Path(f).resolve()
    return str(p.parent if p.name == "__init__.py" else p)


def _code_identity(fn: Callable) -> str:
    dirs = sorted({d for d in (_package_dir(__name__), _package_dir(getattr(fn, "__module__", "")))
                   if d})
    out = []
    for d in dirs:
        if d not in _CODE:
            files, _ = _expand([d]) if os.path.isdir(d) else ({d}, set())
            _CODE[d] = _sha(sorted((f, _file_state(f)) for f in files if f.endswith(".py")))
        out.append(_CODE[d])
    return _sha(out)


# --- the cache -----------------------------------------------------------------------


class NativeCache:
    """Natives' answers under `directory`, reused while what each read is unchanged.
    Hand it to `run_rules(..., cache=...)`; a run without it calls every native."""

    def __init__(self, directory: str | os.PathLike = CHECK_DEFAULT):
        self.dir = Path(directory)
        self._tree: Any = None
        self._digests: dict[str, str] = {}
        self.kept = 0
        self.reused = 0

    def begin(self, tree: Any) -> None:
        """A new run over `tree`: the subtree digests of the last one are dropped."""
        self._tree, self._digests = tree, {}

    def _digest(self, tree: Any, path: str) -> str:
        if tree is not self._tree:
            self.begin(tree)
        if path not in self._digests:
            self._digests[path] = _subtree_digest(tree, path)
        return self._digests[path]

    def _file(self, name: str, args: list, env: tuple) -> Path:
        key = _sha(name, args, {k: os.environ.get(k) for k in env}, os.getcwd())
        return self.dir / "natives" / f"{key[:32]}.json"

    def answer(self, tree: Any, name: str, fn: Callable, args: list,
               reads: ReadsFn, env: tuple = (), spawns: bool = False) -> Any:
        """The native's answer: a kept one whose reads are unchanged, else a new run, kept
        when what it read could all be seen."""
        try:
            json.dumps(args)
        except (TypeError, ValueError):
            return fn(tree, *args)
        path = self._file(name, args, env)
        code = _code_identity(fn)
        traces = self._load(path)
        for t in traces:
            if t.get("code") == code and self._unchanged(tree, t):
                self.reused += 1
                return t["result"]
        declared = reads(tree, *args)
        if declared is None:
            return fn(tree, *args)
        _ensure_hook()
        traced = TracedTree(tree)
        watch = _Watch(self.dir, spawns)
        before = set(sys.modules)
        _watching.append(watch)
        try:
            result = fn(traced, *args)
        finally:
            _watching.remove(watch)
        # a module imported from its compiled copy opens no source: its file is a read too
        for m in set(sys.modules) - before:
            f = getattr(sys.modules.get(m), "__file__", None)
            if f:
                watch.files.add(str(Path(f).resolve()))
        if traced._wrote or watch.unkeepable:
            return result
        try:
            json.dumps(result)
        except (TypeError, ValueError):
            return result
        files, dirs = _expand(declared)
        files |= watch.files
        dirs |= watch.dirs
        trace = {"code": code,
                 "nodes": {p: self._digest(tree, p) for p in sorted(traced._paths)},
                 "files": {f: _file_state(f) for f in sorted(files)},
                 "dirs": {d: _dir_state(d) for d in sorted(dirs)},
                 "result": result}
        self._store(path, [trace] + [t for t in traces if t.get("code") == code][:KEPT_TRACES - 1])
        self.kept += 1
        return result

    def _unchanged(self, tree: Any, t: dict) -> bool:
        return (all(self._digest(tree, p) == d for p, d in (t.get("nodes") or {}).items())
                and all(_file_state(f) == s for f, s in (t.get("files") or {}).items())
                and all(_dir_state(d) == s for d, s in (t.get("dirs") or {}).items()))

    @staticmethod
    def _load(path: Path) -> list[dict]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _store(path: Path, traces: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(traces, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


# --- a rule's verdict ------------------------------------------------------------------


class _VerdictTree(TracedTree):
    """A traced tree that records each backlink query instead of noting the whole tree.
    Nearly every rule asks one (`superseded(self)` is `backlinks('supersedes', self)`), so
    taking it for a read of everything would keep nothing; its answer is what is kept."""

    def __init__(self, tree: Any):
        super().__init__(tree)
        object.__setattr__(self, "_backlinks", set())

    def backlinks(self, name: str, target: str):
        self._backlinks.add((name, target))
        return self._tree.backlinks(name, target)


class VerdictCache:
    """A rule's verdict on a node, kept while everything the rule read there is unchanged
    (#69). Hand it to `run_rules(..., verdicts=...)`.

    `run_rules` used to judge every rule on every node after every write, though a write
    touches one node. Each evaluation runs over a tree that records what it reached: the
    nodes it read (kept as the digest of each one's subtree), the backlink queries it asked
    (kept as their answers), and the node's bound params. The verdict comes back while the
    rule's text, the run's context, quern's code and every one of those reads are as they
    were; otherwise the rule is judged again. A node a write turns red is often not the node
    written - a new link makes its target's `backlinked` answer move - and the recorded
    query is what sends that target back to judgement.

    A rule that reaches `solve` is judged every time: what a native read is the native
    cache's business (`NativeCache`), which still answers it. A traced run (`trace=True`)
    judges everything, since a kept verdict has no reads to hand back.

    `directory` keeps the verdicts on disk under it, one file per rule; None keeps them in
    memory for the life of the object. After a run, `moved` lists `(rule, node, before,
    after)` for each verdict that changed since the one kept: what a writer wants to see."""

    def __init__(self, directory: str | os.PathLike | None = CHECK_DEFAULT):
        self.dir = Path(directory) if directory is not None else None
        self._rules: dict[str, dict[str, dict]] = {}
        self._dirty: set[str] = set()
        self._code = _code_identity(_sha)
        self._tree: Any = None
        self._digests: dict[str, str] = {}
        self._index: dict[tuple[str, str], list[str]] | None = None
        self._ctx = ""
        self.reused = 0
        self.judged = 0
        self.moved: list[tuple[str, str, str, str]] = []

    # --- one run ---

    def begin(self, tree: Any, context: dict | None) -> None:
        self._tree, self._digests, self._index = tree, {}, None
        self._ctx = _sha(context or {})
        self.reused = self.judged = 0
        self.moved = []

    def end(self) -> None:
        if self.dir is None:
            self._dirty.clear()
            return
        for key in self._dirty:
            path = self.dir / "verdicts" / f"{key[:32]}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._rules[key], ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        self._dirty.clear()

    def tracer(self) -> _VerdictTree:
        return _VerdictTree(self._tree)

    def lookup(self, rule: Any, node: str, variables: Any) -> dict | None:
        """The kept verdict, as `{verdict, ok, detail}`, when nothing it read has moved."""
        e = self._entries(rule).get(node)
        if (e is not None and e.get("vars") == self._vars(variables)
                and e.get("ctx") == self._ctx
                and all(self._digest(p) == d for p, d in e.get("nodes", {}).items())
                and all(self._backlinks(n, t) == a for n, t, a in e.get("back", []))):
            self.reused += 1
            return e
        return None

    def keep(self, rule: Any, node: str, variables: Any, verdict: str, ok: bool,
             detail: str | None, traced: _VerdictTree, keepable: bool) -> None:
        self.judged += 1
        entries = self._entries(rule)
        before = entries.get(node)
        if before is not None and before.get("verdict") != verdict:
            self.moved.append((rule.name, node, before["verdict"], verdict))
        key = self._key(rule)
        if not keepable or traced._wrote:
            if entries.pop(node, None) is not None:
                self._dirty.add(key)
            return
        entries[node] = {
            "verdict": verdict, "ok": ok, "detail": detail,
            "vars": self._vars(variables), "ctx": self._ctx,
            "nodes": {p: self._digest(p) for p in sorted(traced._paths)},
            "back": [[n, t, self._backlinks(n, t)] for n, t in sorted(traced._backlinks)],
        }
        self._dirty.add(key)

    # --- what was read ---

    def _key(self, rule: Any) -> str:
        return _sha(rule.name, rule.expr, rule.kind, rule.path, self._code)

    def _entries(self, rule: Any) -> dict[str, dict]:
        key = self._key(rule)
        if key not in self._rules:
            data: dict = {}
            if self.dir is not None:
                try:
                    data = json.loads((self.dir / "verdicts" / f"{key[:32]}.json")
                                      .read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    data = {}
            self._rules[key] = data if isinstance(data, dict) else {}
        return self._rules[key]

    @staticmethod
    def _vars(variables: Any) -> str:
        return _sha(dict(variables), sorted(getattr(variables, "absent", ())))

    def _digest(self, path: str) -> str:
        if path not in self._digests:
            self._digests[path] = _subtree_digest(self._tree, path)
        return self._digests[path]

    def _backlinks(self, name: str, target: str) -> list[str]:
        """The answer the tree gives now, from one pass over an in-memory tree's links
        (built on first need, once per run) or from the store's own index."""
        if not hasattr(self._tree, "root"):
            return list(self._tree.backlinks(name, target))
        if self._index is None:
            index: dict[tuple[str, str], list[str]] = {}
            for p, n in self._tree.walk(""):
                for rel, targets in n.links.items():
                    for t in targets:
                        index.setdefault((rel, t), []).append(p)
            self._index = {k: sorted(v) for k, v in index.items()}
        return self._index.get((name, target), [])
