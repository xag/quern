"""The semantic package library: capitalizing vocabulary, rules and solvers.

A package is the unit of capitalization — everything a use case learned, as data:
what its kinds mean (vocabulary), what must hold (rules), what computes (solvers,
as content-addressed blobs) and example subtrees that *prove* it all. Publishing
is gated on that proof: every rule must be exercised by the package's own examples
and pass, and every solver blob must exist and meet the ABI. A package that can't
demonstrate itself doesn't enter the library.

Versions are immutable: republishing name@version with different content is
refused, so a pin (`Bom.packages`) means the same thing forever — packaged
clients freeze on pins and never go stale, live environments move their pins.

Merging is by precedence, never by magic: a tree's own vocabulary, rules and
solvers always win over package ones; among packages, install order decides.
The library interprets nothing — it stores, validates and serves.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .tree import KindDef, Node, PackageRef, Rule, Bom, run_rules
from .solver import SolverDef, SolverError, load_blob, save_blob


class CounterExample(BaseModel):
    """A node a rule MUST reject: the evidence that a guard guards.

    An example proves a rule does not fire on sound data. It says nothing about
    whether the rule fires on unsound data — so a rule rotted into vacuity ('1 ==
    1', a renamed param, a contract quietly returning 0) publishes exactly like a
    real one, and every consumer that pins it keeps trusting it. The failure is
    silent and open, which for a package whose whole purpose is to *reject* is the
    only failure that matters.

    `because` names the defect this embodies. It is not decoration: it is what the
    proof log reports, and the sentence a later reader checks the rule against when
    they wonder what it was ever for.

    `nodes` is a tree state, not a single node — the same shape as `examples` — because
    a defect is often relational: a design fitted against an unmeasured wall needs both
    the design and the wall to exist. Staging only the design would trip the rule for
    the wrong reason (a dangling link, not an unmeasured one) and the proof would be a
    lie that reads like a proof.
    """

    rule: str                # the rule this state must trip
    nodes: list[Node] = Field(default_factory=list)  # the defect, embodied
    because: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_single_node(cls, data: Any) -> Any:
        """`node: {...}` is the common case — one node is one defect."""
        if isinstance(data, dict) and "node" in data and "nodes" not in data:
            data = dict(data)
            data["nodes"] = [data.pop("node")]
        return data


class Package(BaseModel):
    """One versioned bundle of semantics, self-demonstrating via its examples.

    `requires` lets a package depend on and extend others — exact versions only,
    so a pin (direct or transitive) means the same thing forever. No ranges, no
    resolver algebra: organic innovation favors fork-or-republish over dependency
    SAT solving. Extension needs no machinery beyond precedence: redefining a
    dependency's kind or re-implementing a contract name already wins for whoever
    sits nearer in the closure.

    `examples` prove the rules pass on sound data; `counter_examples` prove they
    fire on unsound data. A guard must ship the evidence that it guards.
    """

    name: str
    version: str
    description: str = ""
    publisher: str = ""
    requires: list[PackageRef] = Field(default_factory=list)
    vocabulary: list[KindDef] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    solvers: list[SolverDef] = Field(default_factory=list)
    examples: list[Node] = Field(default_factory=list)
    counter_examples: list[CounterExample] = Field(default_factory=list)


def package_digest(package: Package) -> str:
    """The package's content identity: sha256 of its canonical serialization.

    Deliberately NOT a hash of the stored file's bytes. Storage and transport
    mangle bytes without changing meaning — text-mode writes translate newlines
    per platform, git checkouts rewrite them per .gitattributes — and an identity
    that flips when a file crosses an OS boundary would report drift where there
    is none. Re-parse, re-serialize, hash that: the digest names the semantics,
    wherever and however they are stored.
    """
    return hashlib.sha256(_canonical(package).encode("utf-8")).hexdigest()


def _canonical(package: Package) -> str:
    return package.model_dump_json(indent=2, exclude_none=True)


class Library:
    """Directory-backed registry: packages/<name>/<version>.json + blobs/."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def blob_dir(self) -> Path:
        return self.root / "blobs"

    def _path(self, name: str, version: str) -> Path:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in name)
        safev = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in version)
        return self.root / "packages" / safe / f"{safev}.json"

    def list(self) -> list[tuple[str, list[str]]]:
        pdir = self.root / "packages"
        if not pdir.exists():
            return []
        out = []
        for d in sorted(p for p in pdir.iterdir() if p.is_dir()):
            versions = sorted(f.stem for f in d.glob("*.json"))
            if versions:
                out.append((d.name, versions))
        return out

    def get(self, name: str, version: str) -> Package | None:
        path = self._path(name, version)
        if not path.exists():
            return None
        return Package.model_validate_json(path.read_text(encoding="utf-8"))

    def publish(self, package: Package, wasm_blobs: dict[str, bytes]) -> list[str]:
        """Validate and store; returns the proof log. `wasm_blobs` maps solver
        names to modules (their hashes go in the stored descriptors)."""
        for s in package.solvers:
            if s.name in wasm_blobs:
                s.blob = save_blob(self.blob_dir, wasm_blobs[s.name])
        log = validate_package(package, self.blob_dir, self)

        path = self._path(package.name, package.version)
        if path.exists():
            existing = Package.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.model_dump() != package.model_dump():
                raise ValueError(
                    f"{package.name}@{package.version} already exists with different "
                    "content — versions are immutable, publish a new one")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_canonical(package).encode("utf-8"))
        log.append(f"digest sha256:{package_digest(package)} — a pin carrying it "
                   "freezes this meaning across libraries, not just this one")
        return log

    def resolve(self, tree: Bom, strict: bool = True) -> list[Package]:
        """The pinned packages and their dependency closure, in deterministic
        order: each pin followed depth-first by its requires, already-seen
        skipped — so a package precedes its dependencies and `effective`'s
        precedence fold makes the extender win over what it extends.

        A dangling reference (pin or require) raises when strict — a silent hole
        in the semantics is worse than an error — as does a diamond conflict
        (two exact versions of one name in the closure) and a hash-bearing ref
        whose library content digests differently: the version string says the
        semantics are the pinned ones, the bytes say otherwise, and serving them
        anyway would be exactly the silent drift the hash exists to catch. Read
        paths may pass strict=False to keep serving while tree_package reports
        the hole; there the first version encountered wins and a mismatched
        package is skipped like a missing one."""
        out: list[Package] = []
        chosen: dict[str, str] = {}

        def visit(ref: PackageRef, via: str) -> None:
            if ref.sha256:
                pinned = self.get(ref.name, ref.version)
                if pinned is not None and package_digest(pinned) != ref.sha256:
                    if strict:
                        raise ValueError(
                            f"{ref.name}@{ref.version} ({via}) is not the content "
                            f"pinned: the library holds sha256:"
                            f"{package_digest(pinned)[:12]}…, the pin says "
                            f"{ref.sha256[:12]}… — same name, different meaning; "
                            "repin what you actually mean")
                    return
            if ref.name in chosen:
                if chosen[ref.name] != ref.version and strict:
                    raise ValueError(
                        f"diamond conflict: {ref.name}@{chosen[ref.name]} and "
                        f"{ref.name}@{ref.version} ({via}) are both in the "
                        "closure — exact versions only, republish against one")
                return
            pkg = self.get(ref.name, ref.version)
            if pkg is None:
                if strict:
                    raise ValueError(f"{ref.name}@{ref.version} ({via}) "
                                     "is not in the library")
                return
            chosen[ref.name] = ref.version
            out.append(pkg)
            for req in pkg.requires:
                visit(req, f"required by {ref.name}@{ref.version}")
        for ref in tree.packages:
            visit(ref, "pinned")
        return out

    def effective(self, tree: Bom, strict: bool = True) -> Bom:
        """A composed copy where package semantics apply, the tree's own always
        winning — precedence, never merge magic."""
        eff = tree.model_copy(deep=True)
        kinds = {k.kind for k in eff.vocabulary}
        rules = {r.name for r in eff.rules}
        solvers = {s.name for s in eff.solvers}
        for pkg in self.resolve(tree, strict=strict):
            for k in pkg.vocabulary:
                if k.kind not in kinds:
                    eff.vocabulary.append(k)
                    kinds.add(k.kind)
            for r in pkg.rules:
                if r.name not in rules:
                    eff.rules.append(r)
                    rules.add(r.name)
            for s in pkg.solvers:
                if s.name not in solvers:
                    eff.solvers.append(s)
                    solvers.add(s.name)
        return eff


def lock_refs(library: Library, pins: list[PackageRef]) -> list[PackageRef]:
    """The flattened dependency closure of `pins`, every entry hash-bearing —
    what a lockfile records. Exact names, exact versions, exact bytes: a lock
    that leaves any of the three open is not a lock."""
    closure = library.resolve(Bom(packages=pins))
    return [PackageRef(name=p.name, version=p.version, sha256=package_digest(p))
            for p in closure]


def read_lock(path: Path) -> list[PackageRef]:
    """The lockfile's refs — the flattened, hash-bearing closure `lock_refs`
    computed. Missing file means nothing locked, not an error: the caller
    decides whether an empty lock is a state or a mistake."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [PackageRef.model_validate(e) for e in data["packages"]]


def write_lock(path: Path, refs: list[PackageRef]) -> None:
    path.write_bytes((json.dumps(
        {"packages": [r.model_dump(exclude_none=True) for r in refs]},
        indent=2) + "\n").encode("utf-8"))


def sync(source: Library, dest: Library, refs: list[PackageRef]) -> list[str]:
    """Materialize `refs` (and their solver blobs) from one library into another,
    hash-verified — the consumer half of the channel: registry in, local cache out.

    Every ref must carry its sha256; resolve refuses any whose source content
    digests differently. Entry into `dest` is through `publish` and nowhere
    else, so the proof gate re-runs on the consumer's machine — a registry is
    trusted for transport, not for validation. Dependencies are published
    first (publish resolves requires against `dest`), and a re-sync of already
    materialized content is the identical-republish no-op.
    """
    hashless = [r for r in refs if not r.sha256]
    if hashless:
        raise ValueError("refusing to sync without content pins: "
                         + ", ".join(f"{r.name}@{r.version}" for r in hashless)
                         + " carry no sha256 — a lock is exact or it is not a lock")
    closure = source.resolve(Bom(packages=refs))  # verifies every pinned hash
    log: list[str] = []
    done: set[tuple[str, str]] = set()

    def emit(pkg: Package) -> None:
        if (pkg.name, pkg.version) in done:
            return
        done.add((pkg.name, pkg.version))
        for req in pkg.requires:
            dep = source.get(req.name, req.version)
            if dep is not None:  # a dangling require already raised in resolve
                emit(dep)
        for s in pkg.solvers:
            if s.blob:
                save_blob(dest.blob_dir, load_blob(source.blob_dir, s.blob))
        dest.publish(pkg, {})
        log.append(f"{pkg.name}@{pkg.version} sha256:{package_digest(pkg)[:12]}… "
                   "synced, proof re-run")
    for pkg in closure:
        emit(pkg)
    return log


def validate_package(package: Package, blob_dir: Path,
                     library: Library | None = None) -> list[str]:
    """The publish gate: a package must demonstrate itself.

    Every rule must be *exercised* by the package's own examples (at least one
    binding) and pass on all of them; every solver blob must exist, hash true and
    export the ABI. The examples run against the package's dependency closure —
    the chain's vocabulary, rules and solvers in scope, the package's own on top —
    so a package that extends another proves itself in the semantics it will
    actually live in, and its examples must satisfy the layers beneath too.

    Examples alone prove only that a rule does not fire on sound data. A rule that
    guards nothing passes them identically to one that guards everything, so a
    `counter_examples` entry — a node the named rule MUST reject — is the evidence
    that the guard guards. Each is staged alone, so the rule has to fail *on that
    node*: a defect elsewhere in the package cannot stand in for the proof.

    Raises ValueError with the first failure; returns the proof log when
    everything holds.
    """
    log: list[str] = []
    if package.rules and not package.examples:
        raise ValueError("a package with rules must carry examples that exercise them")

    named = {r.name for r in package.rules}
    for ce in package.counter_examples:
        if ce.rule not in named:
            raise ValueError(f"counter-example names rule '{ce.rule}', which this "
                             "package does not define")

    stage = Bom(vocabulary=package.vocabulary, rules=package.rules,
                solvers=package.solvers, packages=package.requires)
    if package.requires:
        if library is None:
            raise ValueError("the package declares requires but there is no "
                             "library to resolve them against")
        closure = library.resolve(stage)  # dangling require / diamond raise here
        log.append("closure: " + ", ".join(f"{p.name}@{p.version}" for p in closure)
                   + " staged beneath the package's own semantics")
        stage = library.effective(stage)
    stage.root.children = [n.model_copy(deep=True) for n in package.examples]
    results = run_rules(stage)
    exercised = {r.rule for r in results}
    for rule in package.rules:
        if rule.name not in exercised:
            raise ValueError(f"rule '{rule.name}' is never exercised by the "
                             "package's examples — prove it or drop it")
    failing = [r for r in results if not r.ok]
    if failing:
        f = failing[0]
        raise ValueError(f"rule '{f.rule}' fails on the package's own example "
                         f"@ '{f.node}'{f' ({f.detail})' if f.detail else ''}")
    if package.rules:
        log.append(f"{len(package.rules)} rule(s) exercised by "
                   f"{len(package.examples)} example(s), all pass")

    # The other half of the proof: each counter-example is staged ALONE, so the rule
    # it names must reject THAT node. A rule that fires on something else in the
    # package cannot borrow the credit.
    refuted: list[str] = []
    for ce in package.counter_examples:
        stage.root.children = [n.model_copy(deep=True) for n in ce.nodes]
        outcomes = run_rules(stage)
        caught = [r for r in outcomes if r.rule == ce.rule and not r.ok]
        if not caught:
            why = ("it passes there" if any(r.rule == ce.rule for r in outcomes)
                   else "the rule does not even bind to that node")
            defect = ce.because or "its own counter-example"
            raise ValueError(f"counter-example for rule '{ce.rule}' is not refuted — "
                             f"{why}. A rule that cannot reject {defect} guards nothing")
        refuted.append(f"{ce.rule} @ {caught[0].node}"
                       + (f" ({ce.because})" if ce.because else ""))
    if refuted:
        log.append(f"{len(refuted)} rule(s) refuted by their counter-example(s): "
                   + ", ".join(refuted))
    unproven = sorted(named - {ce.rule for ce in package.counter_examples})
    if unproven:
        log.append(f"{len(unproven)} rule(s) carry no counter-example, so nothing "
                   f"shows they reject anything: {', '.join(unproven)}")

    for s in package.solvers:
        if s.native:
            log.append(f"solver '{s.name}' is a native contract — trusted server "
                       "code, outside the sandbox gate")
            continue
        blob = load_blob(blob_dir, s.blob)  # exists + hashes true
        if s.medium == "wasm":
            _check_abi(blob, s.name)
            log.append(f"solver '{s.name}' @ {s.blob[:12]}… meets the ABI")
        else:  # presentation or instructions: content-addressed, never executed here
            log.append(f"artifact '{s.name}' ({s.medium}) @ {s.blob[:12]}… stored — "
                       "serves experience/guidance, never derived values")
    return log


def _check_abi(wasm: bytes, name: str) -> None:
    import wasmtime

    try:
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, wasm)
    except Exception as e:
        raise ValueError(f"solver '{name}' is not a valid wasm module: {e}") from e
    exports = {e.name: e for e in module.exports}
    for needed in ("memory", "alloc", "run"):
        if needed not in exports:
            raise ValueError(f"solver '{name}' does not export '{needed}' — "
                             "the ABI is memory/alloc/run")
    if module.imports:
        raise ValueError(f"solver '{name}' declares imports — the sandbox "
                         "provides none, it could never instantiate")


def solver_blob(user_dir: Path, library: Library, sha: str) -> bytes:
    """A solver's code, wherever it lives: the user's own store first, then the
    shared library."""
    try:
        return load_blob(user_dir, sha)
    except SolverError:
        return load_blob(library.blob_dir, sha)
