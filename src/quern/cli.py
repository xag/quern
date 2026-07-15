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

from .library import Library, Package, lock_refs, read_lock, write_lock
from .library import sync as sync_libraries
from .tree import PackageRef

LOCK_DEFAULT = "quern.lock"
CACHE_DEFAULT = ".quern/library"


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


def cmd_publish(args: argparse.Namespace) -> None:
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


def cmd_pin(args: argparse.Namespace) -> None:
    lib = _registry(args)
    lock = Path(args.lock)
    pins = {r.name: r for r in read_lock(lock)}
    for spec in args.packages:
        if "@" not in spec:
            sys.exit(f"pin takes name@version, got '{spec}'")
        name, version = spec.rsplit("@", 1)
        pins[name] = PackageRef(name=name, version=version)
    try:  # re-lock the whole set: the closure is flattened, every entry hashed
        refs = lock_refs(lib, list(pins.values()))
    except ValueError as e:
        sys.exit(f"not pinned: {e}")
    write_lock(lock, refs)
    for r in refs:
        print(f"{r.name}@{r.version} sha256:{r.sha256}")
    print(f"locked {len(refs)} package(s) in {lock}")


def cmd_sync(args: argparse.Namespace) -> None:
    lib = _registry(args)
    lock = Path(args.lock)
    refs = read_lock(lock)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="quern", description="packages travel as data: publish, pin, sync")
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
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("pin", help="record name@version + digest in the lockfile")
    p.add_argument("packages", nargs="+", metavar="name@version")
    p.add_argument("--lock", default=LOCK_DEFAULT)
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("sync", help="materialize the lockfile into a local library")
    p.add_argument("--lock", default=LOCK_DEFAULT)
    p.add_argument("--dest", default=CACHE_DEFAULT)
    p.set_defaults(func=cmd_sync)

    args = parser.parse_args(argv)
    import importlib
    for module in args.natives or []:
        importlib.import_module(module)
    args.func(args)


if __name__ == "__main__":
    main()
