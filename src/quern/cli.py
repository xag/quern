"""The channel's verbs: publish (authoring repo → registry), pin (registry →
lockfile) and sync (registry → local cache).

A registry is nothing but a published Library — a directory whose layout
`Library` already owns (`packages/<name>/<version>.json + blobs/`). Git moves
that directory around; this CLI never runs git, because git is transport, not
identity: identity is the content digest in the pin, and it is checked at every
door. The consumer's `quern.lock` records the flattened closure — name, version,
sha256 — and `sync` materializes exactly those bytes into a local Library, the
one the tempdir-publish pattern always expected to exist. Publication into any
library goes through `publish` and its proof gate, on the publisher's machine
AND again on the consumer's: a registry is trusted for transport, not for
validation.

Where the registry lives is a convention, not a mechanism: pass --registry or
set QUERN_REGISTRY; anyone can root another, and a fork is a directory copy.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# `library` is imported as a MODULE, and reached through it below, because the flight
# recorder wraps a boundary by setting the attribute on the module it was handed: a name
# bound here by `from .library import ...` would keep pointing at the unwrapped original,
# and its calls would silently never be recorded. Today's boundary sits one level deeper
# (read_text/write_text), so nothing imported here is wrapped — but the discipline is what
# keeps that true by accident rather than by luck the next time the boundary moves.
# `Library` may come by value: the recorder patches methods on the class object itself,
# which every reference already shares.
from . import library
from .library import Library, Package, lock_refs
from .library import sync as sync_libraries
from .tree import PackageRef

LOCK_DEFAULT = "quern.lock"
CACHE_DEFAULT = ".quern/library"
FLIGHT_DEFAULT = ".quern/flight"


def _registry(args: argparse.Namespace) -> Library:
    root = args.registry or os.environ.get("QUERN_REGISTRY")
    if not root:
        sys.exit("no registry: pass --registry DIR or set QUERN_REGISTRY")
    root = Path(root)
    if not root.exists():
        sys.exit(f"registry '{root}' does not exist")
    return Library(root)


def _load_package(spec: str) -> Package:
    """A package to publish: a serialized artifact (`pkg.json`), or the object an
    authoring module builds (`path/to/semantics.py:PACKAGE`, `mymod:PACKAGE`)."""
    if spec.endswith(".json"):
        return Package.model_validate_json(Path(spec).read_text(encoding="utf-8"))
    if ":" not in spec:
        sys.exit(f"'{spec}' is neither a .json artifact nor a module:ATTR spec")
    modpart, attr = spec.rsplit(":", 1)
    if modpart.endswith(".py"):
        import importlib.util
        mspec = importlib.util.spec_from_file_location("_quern_authoring", modpart)
        if mspec is None or mspec.loader is None:
            sys.exit(f"cannot load '{modpart}'")
        mod = importlib.util.module_from_spec(mspec)
        mspec.loader.exec_module(mod)
    else:
        import importlib
        mod = importlib.import_module(modpart)
    pkg = getattr(mod, attr, None)
    if not isinstance(pkg, Package):
        sys.exit(f"'{spec}' is not a quern.library.Package")
    return pkg


def _cmd_publish(args: argparse.Namespace) -> None:
    lib = _registry(args)
    pkg = _load_package(args.package)
    blobs: dict[str, bytes] = {}
    for pair in args.blob or []:
        if "=" not in pair:
            sys.exit(f"--blob takes name=file, got '{pair}'")
        name, file = pair.split("=", 1)
        blobs[name] = Path(file).read_bytes()
    try:
        proof = lib.publish(pkg, blobs)
    except Exception as e:
        sys.exit(f"not published: {e}")
    print(f"published {pkg.name}@{pkg.version}")
    for line in proof:
        print(f"  {line}")


def _cmd_pin(args: argparse.Namespace) -> None:
    lib = _registry(args)
    lock = Path(args.lock)
    pins = {r.name: r for r in library.read_lock(lock)}
    for spec in args.packages:
        if "@" not in spec:
            sys.exit(f"pin takes name@version, got '{spec}'")
        name, version = spec.rsplit("@", 1)
        pins[name] = PackageRef(name=name, version=version)
    try:  # re-lock the whole set: the closure is flattened, every entry hashed
        refs = lock_refs(lib, list(pins.values()))
    except ValueError as e:
        sys.exit(f"not pinned: {e}")
    library.write_lock(lock, refs)
    for r in refs:
        print(f"{r.name}@{r.version} sha256:{r.sha256}")
    print(f"locked {len(refs)} package(s) in {lock}")


def _cmd_sync(args: argparse.Namespace) -> None:
    lib = _registry(args)
    lock = Path(args.lock)
    refs = library.read_lock(lock)
    if not refs:
        sys.exit(f"nothing to sync: {lock} is missing or empty — pin something first")
    dest = Library(Path(args.dest))
    try:
        log = sync_libraries(lib, dest, refs)
    except Exception as e:
        sys.exit(f"not synced: {e}")
    for line in log:
        print(f"  {line}")
    print(f"{len(log)} package(s) in {dest.root}")


def _cmd_navigate(args: argparse.Namespace) -> None:
    from .navigate import serve
    serve(args.project, module=args.module, port=args.port,
          open_browser=not args.no_browser)


def _cmd_brief(args: argparse.Namespace) -> None:
    from pathlib import Path

    from .brief import brief
    from .navigate import load_build, project_label
    root = Path(args.project).resolve()
    tree = load_build(root, args.module)()
    print(f"{project_label(root)} - ledger brief")
    print(brief(tree, all=args.all, fat=args.fat))


def _utf8_streams() -> None:
    """The help text, the briefs and the proof lines all carry en-dashes and
    arrows; Windows consoles default to cp1252, which cannot encode them, so
    `quern --help` died inside argparse before it could print a word. Encode
    UTF-8 and replace what the terminal cannot render: a mojibake arrow still
    tells the reader what the command does, a UnicodeEncodeError does not."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_armed = False


def _record() -> None:
    """Arm the flight recorder over this invocation: one tape per CLI run, the command as
    the call, under `.quern/flight`.

    `install` wraps every public function this module defines — `run`, which is the one that
    matters, and `main`, which is merely along for the ride. Arming is guarded because a
    process may call `main` many times (the test suite does), and re-patching an already
    patched boundary each time would stack wrappers on wrappers; the recorder is explicit
    that idempotence is the caller's business, so this is the caller minding it.

    On by default, because a recorder that must be remembered is a recorder that is off on
    the run that mattered. `QUERN_FLIGHT=0` opts out for anyone who wants a CLI that writes
    nothing but what it was asked to write."""
    global _armed
    if _armed or os.environ.get("QUERN_FLIGHT", "1").lower() in ("0", "off", "false", "no"):
        return
    _armed = True
    try:
        from flight_recorder import install

        from .boundary import boundary
        install(boundary(), sys.modules[__name__], directory=FLIGHT_DEFAULT)
    except Exception:
        # Never let instrumentation break the tool it instruments. A missing or broken
        # recorder costs a tape; it must not cost the user their `quern sync`.
        pass


def run(argv: list[str]) -> None:
    """The whole command, taking the ARGV and nothing else — which is what makes the tape
    worth having.

    The obvious shape was to record the `_cmd_*` verbs, and it does not work: each takes an
    `argparse.Namespace`, an object the tape can only hold as `{"__opaque__": "Namespace(…)"}`
    and can only replay as that repr STRING. The recording would look healthy and reproduce
    nothing. A list of strings, by contrast, the tape holds exactly — so `run` is the seam,
    parsing happens INSIDE the replayed code where it belongs, and the recorded call is
    literally the command the user typed."""
    parser = argparse.ArgumentParser(
        prog="quern",
        description="packages travel as data: publish, pin, sync; navigate a ledger")
    parser.add_argument("--registry", help="registry directory (or $QUERN_REGISTRY)")
    parser.add_argument("--natives", action="append", metavar="MODULE",
                        help="module to import for its register_native side "
                             "effects (repeatable) — native contracts are host "
                             "code and travel as Python, never in the artifact; "
                             "the proof gate needs them in-process to re-run")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("publish", help="authoring repo → registry, proof-gated")
    p.add_argument("package", help="pkg.json, path/to/module.py:ATTR, or module:ATTR")
    p.add_argument("--blob", action="append", metavar="NAME=FILE",
                   help="solver blob to store content-addressed (repeatable)")
    p.set_defaults(func=_cmd_publish)

    p = sub.add_parser("pin", help="record name@version + digest in the lockfile")
    p.add_argument("packages", nargs="+", metavar="name@version")
    p.add_argument("--lock", default=LOCK_DEFAULT)
    p.set_defaults(func=_cmd_pin)

    p = sub.add_parser("sync", help="materialize the lockfile into a local library")
    p.add_argument("--lock", default=LOCK_DEFAULT)
    p.add_argument("--dest", default=CACHE_DEFAULT)
    p.set_defaults(func=_cmd_sync)

    p = sub.add_parser("brief", help="one line per current ledger entry - the working "
                                     "set, not the archaeology")
    p.add_argument("project", nargs="?", default=".",
                   help="project root holding ledger/tree.py (default: current dir)")
    p.add_argument("--module", metavar="PATH[:ATTR]",
                   help="override the build entry (default: <project>/ledger/tree.py:build)")
    p.add_argument("--all", action="store_true",
                   help="include superseded entries instead of counting them away")
    p.add_argument("--fat", action="store_true",
                   help="sort by said_words, heaviest first - the curation view")
    p.set_defaults(func=_cmd_brief)

    p = sub.add_parser("navigate", help="serve a project's ledger in the read-only navigator")
    p.add_argument("project", nargs="?", default=".",
                   help="project root holding ledger/tree.py (default: current dir)")
    p.add_argument("--module", metavar="PATH[:ATTR]",
                   help="override the build entry (default: <project>/ledger/tree.py:build)")
    p.add_argument("--port", type=int, default=8765, help="localhost port (default: 8765)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    p.set_defaults(func=_cmd_navigate)

    args = parser.parse_args(argv)
    import importlib
    for module in args.natives or []:
        importlib.import_module(module)
    args.func(args)


def main(argv: list[str] | None = None) -> None:
    """The process entry: set the streams up, arm the recorder, then hand the argv to `run`.

    Nothing here is recorded — it IS the recording apparatus, and a tape of the code that
    starts the tape would be a curiosity rather than evidence."""
    _utf8_streams()
    _record()
    run(sys.argv[1:] if argv is None else list(argv))


if __name__ == "__main__":
    main()
