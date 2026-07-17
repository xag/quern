"""quern navigate — open any project's design ledger in the read-only navigator.

Every ledgered project ships the same seam: a `ledger/tree.py` exposing
`build() -> Quern`, self-locating its root and package registry through `__file__`.
That is enough to view it. This launcher loads that `build`, wraps its Quern in a
Workspace that answers the navigator's read verbs and refuses every write, and
serves `quern.app_host` — the same HTML view the model coedits through, minus the
editing.

Run it from an environment that has the host extra (`quern[host]`, for the MCP
SDK `serve_dev` needs) and point it at a project directory:

    quern navigate ../assay-office
    python -m quern.navigate            # defaults to the current directory

The launcher knows nothing of any consumer: it discovers `ledger/tree.py` by
convention, and `build()` resolves its own registry (`$QUERN_REGISTRY` or the
sibling `quern-registry`). Nothing is written back — this is a viewer.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

from .tree import KindDef, Quern


class ReadOnlyWorkspace:
    """A `host.Workspace` (structurally) wrapping an already-built Quern for
    viewing only. The navigator's read verbs (tree_app/get/find/check) need just
    `label` and `effective()`; every write seam raises, so a browser cannot mutate
    a ledger this launcher does not own."""

    def __init__(self, quern: Quern, label: str) -> None:
        self._quern = quern
        self.label = label

    @property
    def quern(self) -> Quern:
        return self._quern

    def effective(self) -> Quern:  # build() already resolved packages; return as-is
        return self._quern

    def assert_editable(self, path: str) -> None:
        raise PermissionError(
            "read-only navigator: this ledger cannot be edited here - "
            "author it in its own ledger/tree.py")

    def save(self) -> None:
        raise PermissionError("read-only navigator: nothing to save")

    @property
    def blob_dir(self) -> Path:
        raise NotImplementedError("read-only navigator has no blob store")

    @property
    def library(self) -> Any:
        raise NotImplementedError("read-only navigator has no library")

    def starter_vocabulary(self) -> list[KindDef]:
        return []


def _import_ledger_module(path: Path) -> Any:
    """Import the ledger module from a file, honoring relative imports. A ledger is
    normally a package (`ledger/__init__.py` beside `tree.py`, so `tree.py` can do
    `from . import strategy`), so it must be loaded *as* a package, not as a lone
    file. Walk up while `__init__.py` exists to find the top package and the
    directory that has to be on `sys.path`, then import the dotted name. A file with
    no package around it is a standalone script, loaded directly."""
    path = path.resolve()
    parts: list[str] = []
    d = path.parent
    while (d / "__init__.py").exists():
        parts.append(d.name)
        d = d.parent
    if not parts:  # standalone script — no package context to honor
        mspec = importlib.util.spec_from_file_location("_quern_navigate_ledger", path)
        if mspec is None or mspec.loader is None:
            raise SystemExit(f"cannot load '{path}'")
        mod = importlib.util.module_from_spec(mspec)
        mspec.loader.exec_module(mod)
        return mod
    parts.reverse()
    dotted = ".".join([*parts, path.stem])
    top = parts[0]
    # The target project's package must win over any same-named package already
    # imported (quern's own `ledger`, or a prior navigate in this process): drop the
    # cached tree, then put the target's root first on the path.
    for name in [n for n in sys.modules if n == top or n.startswith(f"{top}.")]:
        del sys.modules[name]
    sys.path.insert(0, str(d))
    import importlib
    return importlib.import_module(dotted)


def load_build(project: Path, spec: str | None) -> Callable[[], Quern]:
    """Resolve the `build` callable. By convention `<project>/ledger/tree.py:build`;
    `spec` overrides it as `PATH[:ATTR]` (ATTR defaults to `build`)."""
    if spec:
        modpart, sep, attr = spec.partition(":")
        path = Path(modpart)
        attr = attr if sep else "build"
    else:
        path = project / "ledger" / "tree.py"
        attr = "build"
    if not path.exists():
        raise SystemExit(
            f"no ledger to navigate: {path} does not exist - pass a PROJECT dir "
            f"holding ledger/tree.py, or --module PATH:ATTR")
    try:
        mod = _import_ledger_module(path)
    except SystemExit:
        raise
    except Exception as e:  # import-time failure in the ledger itself
        raise SystemExit(f"loading '{path}' failed: {e}")
    build = getattr(mod, attr, None)
    if not callable(build):
        raise SystemExit(f"'{path}' has no callable '{attr}'")
    return build


def project_label(project: Path) -> str:
    """The project's name from pyproject `[project].name`, else the directory name."""
    pp = project / "pyproject.toml"
    if pp.exists():
        try:
            import tomllib
            data = tomllib.loads(pp.read_text(encoding="utf-8"))
            name = data.get("project", {}).get("name")
            if isinstance(name, str) and name:
                return name
        except Exception:
            pass
    return project.name or str(project)


def serve(project: str = ".", module: str | None = None, port: int = 8765,
          open_browser: bool = True) -> None:
    """Build the target ledger and serve it read-only. Raises SystemExit with a
    plain message on any failure a user can fix (missing ledger, missing registry,
    missing host extra)."""
    root = Path(project).resolve()
    build = load_build(root, module)
    try:
        quern = build()
    except Exception as e:
        raise SystemExit(
            f"could not build the ledger: {e}\n"
            f"(build() resolves its registry from $QUERN_REGISTRY or "
            f"{root.parent / 'quern-registry'} - set QUERN_REGISTRY if it lives elsewhere)")
    ws = ReadOnlyWorkspace(quern, project_label(root))
    try:
        from .app_host import serve_dev
    except ImportError as e:
        raise SystemExit(
            f"the navigator needs the host extra - install quern[host] "
            f"(the MCP SDK is missing: {e})")
    serve_dev(lambda: ws, port=port, open_browser=open_browser)


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(
        prog="quern navigate",
        description="serve a read-only navigator for a project's design ledger")
    ap.add_argument("project", nargs="?", default=".",
                    help="project root holding ledger/tree.py (default: current dir)")
    ap.add_argument("--module", metavar="PATH[:ATTR]",
                    help="override the build entry (default: <project>/ledger/tree.py:build)")
    ap.add_argument("--port", type=int, default=8765, help="localhost port (default: 8765)")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open a browser window")
    args = ap.parse_args(argv)
    serve(args.project, module=args.module, port=args.port,
          open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
