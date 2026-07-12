"""bom.host — the reusable MCP host: one `tree_*` surface over any Workspace.

The generic Business Object Model tools (navigate, author, check, solve, package)
are the same verbs whatever the domain. This module registers them once against a
`Workspace` — the few seams a domain must provide: its live bom, its effective read
view (its own derived overlays plus pinned library packages), the guard on which
branches are writable, persistence, its solver blob store, its library, and its
starter vocabulary. A consumer provides the first Workspace; a second domain is the
next. One endpoint can host several by resolving a different Workspace per call — the
same code, no shared datastore.

Rendering is a domain concern, not a generic verb: a spatial domain draws PNGs of
shapes, a mind map draws a graph. So the geometry tools (`tree_render`, `tree_measure`)
live in `bom.geometry_host.register_geometry_tools`, which a shape-carrying domain
opts into alongside this — the generic surface here stays geometry-free.

Importing this needs the MCP SDK: install `bom[host]`.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable, Protocol

from mcp.server.fastmcp import FastMCP

from . import library as librarymod, solver as solvermod, tree as treemod
from .library import Library
from .tree import Bom, KindDef


class Workspace(Protocol):
    """One domain's live BOM plus the seams the generic tools need. A resolver
    hands the host the caller's active Workspace (or an error string) per call."""

    label: str

    @property
    def bom(self) -> Bom: ...
    def effective(self) -> Bom: ...              # read view: overlays + packages
    def assert_editable(self, path: str) -> None: ...
    def save(self) -> None: ...
    @property
    def blob_dir(self) -> Path: ...
    @property
    def library(self) -> Library: ...
    def starter_vocabulary(self) -> list[KindDef]: ...   # domain default kinds


Resolver = Callable[[], "Workspace | str"]

_MAX_REPORTED = 8


def _relevant(node: str, path: str) -> bool:
    """Does a rule that ran at `node` speak about a write to `path`?

    Two ways it can. It ran on the written branch itself (or something under it), or it
    ran on a branch that CONTAINS the write — a survey-wide rule about how rooms fit
    together has plenty to say about the room you just moved. A rule that ran somewhere
    else entirely is somebody else's business.
    """
    return (node == path or node.startswith(f"{path}/")
            or path.startswith(f"{node}/") or node == "")


def _broke(ws: "Workspace", path: str) -> str:
    """What the write just broke, said at the moment it breaks.

    A tree whose semantics are data is exactly the kind of tree where a write should
    tell you what it violated. Without this the rules are a thing you must remember to
    ask about — and "must remember" is how a survey ends up with nine dimensionless
    openings and nothing in the loop to contradict it. A workspace with no rules sees no
    change: this says nothing when there is nothing to say.
    """
    try:
        results = treemod.run_rules(ws.effective(), "")
    except Exception:  # a broken rule must never make a write look like it failed
        return " Render it with tree_render to see the result."
    failed = [r for r in results if not r.ok and _relevant(r.node, path)]
    if not failed:
        return " Render it with tree_render to see the result."
    lines = [f"  FAIL {r.rule}" + (f" @ {r.node}" if r.node else "")
             + (f" ({r.detail})" if r.detail else "")
             for r in failed[:_MAX_REPORTED]]
    if len(failed) > _MAX_REPORTED:
        lines.append(f"  …and {len(failed) - _MAX_REPORTED} more — tree_check for all.")
    return "\n" + "\n".join(lines)


def register_tree_tools(mcp: FastMCP, get_ws: Resolver) -> None:
    """Register the tree_* tools and the solver:// resource on `mcp`, each acting
    on the Workspace `get_ws()` returns for the current caller."""

    @mcp.tool()
    def tree_set(path: str, node: dict[str, Any]) -> str:
        """Create or update the node at `path` (e.g. 'wardrobe/frame'). Fields given
        replace those fields; missing intermediates become plain groups. A node:
        {kind, name, params: {name: {value, unit, provenance, tolerance, source}},
        links: {name: [paths]}, meta, payload, children}. Geometry lives in payload:
        {shape: box {size:[w,d,h]} | prism {polygon, height} | cylinder {diameter,
        height} | mesh {uri} | union|difference|intersection over children,
        transform: {translate:[x,y,z] mm, rotate_z_deg}}. Numeric shape args may
        name a param from any ancestor — so a shape written in terms of its params
        follows them when they are corrected, and cannot disagree with them.
        Declare what a kind MEANS with tree_vocabulary.

        The write answers with any rule it broke — on the branch itself or on one
        that contains it. Treat that as the verdict: it is the same thing tree_check
        would tell you, said at the moment you caused it."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        ws.assert_editable(path)
        treemod.set_node(ws.bom, path, node)
        ws.save()
        return f"set '{path}'." + _broke(ws, path)

    @mcp.tool(structured_output=True)
    def tree_get(path: str = "", depth: int | None = None) -> dict[str, Any]:
        """Read the BOM at `path` (default: whole tree), pruned to `depth` levels if
        given. Each slice arrives with its own semantics: the kinds present (with
        the operations they afford — full contract at operation://{kind}/{name}),
        the rules that apply, the solvers whose reads cover the slice. A workspace
        may expose derived branches (recomputed from their source on every read) —
        inspect and link to them, don't edit."""
        ws = get_ws()
        if isinstance(ws, str):
            return {"error": ws}
        composed = ws.effective()
        node = treemod.get_node(composed, path)
        if node is None:
            return {"error": f"no node at '{path}'"}
        data = node.model_dump(exclude_none=True)
        if depth is not None:
            _prune(data, depth)
        semantics = treemod.semantics_at(composed, path, depth)
        if semantics:
            data["semantics"] = semantics
        return data

    @mcp.tool(structured_output=True)
    def tree_find(query: str | None = None, kind: str | None = None,
                  has_param: str | None = None, links_to: str | None = None,
                  under: str = "", current_only: bool = False,
                  limit: int = 20) -> dict[str, Any]:
        """Search the BOM instead of walking it — when the user names an element,
        locate it in one call. `query` matches id/name/kind/meta (case-insensitive
        substring); `kind`/`has_param` match exactly; `links_to` finds every node
        referencing a path; `under` scopes to a branch; `current_only` drops nodes
        another node supersedes (the "what do we hold now?" query). Returns paths +
        a one-line summary each; then tree_get the one you meant. Purely structural."""
        ws = get_ws()
        if isinstance(ws, str):
            return {"error": ws}
        hits = treemod.find_nodes(ws.effective(), query=query, kind=kind,
                                  has_param=has_param, links_to=links_to,
                                  under=under, current_only=current_only,
                                  limit=limit)
        return {"matches": [
            {"path": p, "kind": n.kind or None, "name": n.name or None,
             "shape": (n.payload.get("shape") or {}).get("op"),
             "params": sorted(n.params) or None,
             "links": {k: v for k, v in n.links.items()} or None}
            for p, n in hits],
            "truncated": len(hits) >= limit}

    @mcp.tool()
    def tree_delete(path: str) -> str:
        """Delete the node at `path`, with its whole branch."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        ws.assert_editable(path)
        node = treemod.delete_node(ws.bom, path)
        ws.save()
        out = f"deleted '{path}' ({len(node.children)} children went with it)"
        # What you delete can break what remains — a room that other rooms still claim to
        # adjoin, a boundary a design is still scribed to. The parent hears about it.
        broke = _broke(ws, "/".join(treemod._segs(path)[:-1]))
        return out + (broke if broke.startswith("\n") else "")

    @mcp.tool()
    def tree_vocabulary(kind: str | None = None, description: str | None = None,
                        params: dict[str, str] | None = None,
                        links: dict[str, str] | None = None,
                        operations: dict[str, dict[str, Any]] | None = None) -> str:
        """The tree's semantics, as data. No arguments: list every kind defined
        (stored + pinned packages + the domain's starter kinds). With kind +
        description: define or refine what that kind means, and optionally what its
        params/links stand for and what `operations` it affords — name:
        {contract, description, params_doc, medium}, binding the kind to a solver
        contract that makes sense on it (fetch the full contract at
        operation://{kind}/{name}, execute with tree_solve). Nothing branches on
        kinds — they mean exactly what this vocabulary says."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        voc = ws.bom.vocabulary
        if kind is None:
            have = {k.kind for k in ws.effective().vocabulary}
            merged = [*ws.effective().vocabulary,
                      *(k for k in ws.starter_vocabulary() if k.kind not in have)]
            return "\n".join(f"[{k.kind}] {k.description}"
                             + (f" params: {k.params}" if k.params else "")
                             + (f" links: {k.links}" if k.links else "")
                             + (f" operations: {sorted(k.operations)}"
                                if k.operations else "") for k in merged)
        if description is None:
            entry = next((k for k in voc if k.kind == kind), None)
            return (f"[{entry.kind}] {entry.description} params: {entry.params} "
                    f"links: {entry.links}"
                    + (f" operations: {sorted(entry.operations)}"
                       if entry.operations else "")
                    ) if entry else f"kind '{kind}' is not defined."
        ops = ({name: treemod.OperationDef.model_validate(o)
                for name, o in operations.items()}
               if operations is not None else None)
        entry = next((k for k in voc if k.kind == kind), None)
        if entry is None:
            voc.append(KindDef(kind=kind, description=description,
                               params=params or {}, links=links or {},
                               operations=ops or {}))
        else:
            entry.description = description
            if params is not None:
                entry.params = params
            if links is not None:
                entry.links = links
            if ops is not None:
                entry.operations = ops
        ws.save()
        return f"defined kind '{kind}'"

    @mcp.tool()
    def tree_rule(name: str | None = None, expr: str | None = None,
                  description: str = "", kind: str | None = None,
                  path: str | None = None, remove: bool = False) -> str:
        """The tree's checks, as data. No arguments: list the rules. With name +
        expr: register one — a boolean expression whose builtins are STRUCTURAL only
        (param, nodes, params_of, count, sum/len/abs/min/max, ctx, superseded,
        uses/where_used, the reuse folds rollup(under, mult, value) /
        tally(under, kind, mult) — mult/value name params, data not schema —
        the trace verbs over event subtrees: before(a, b) document order,
        preceding/following(p, kind?) earlier/later siblings, index(p),
        at(parent, i), parent(p) — so a scenario whose children are events is
        checkable ('the confirmation email precedes the charge') — and
        and/or/not) plus one bridge to meaning: solve('contract', args…), e.g.
        solve('geometry/bbox_h', 'pieces/x'). Contracts come from packages. Scope
        with `kind` (per node of that kind; its params + `self` in scope) or `path`;
        neither = global. Rules run in tree_check; `remove` deletes one."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        rules = ws.bom.rules
        if name is None:
            if not rules:
                return "no rules yet — register one with name + expr."
            return "\n".join(f"[{r.name}] {r.expr}"
                             + (f" (kind={r.kind})" if r.kind else "")
                             + (f" (path={r.path})" if r.path else "")
                             + (f" — {r.description}" if r.description else "")
                             for r in rules)
        existing = next((r for r in rules if r.name == name), None)
        if remove:
            if existing is None:
                return f"no rule '{name}'"
            rules.remove(existing)
            ws.save()
            return f"removed rule '{name}'"
        if expr is None:
            return f"[{existing.name}] {existing.expr}" if existing else f"no rule '{name}'"
        new = treemod.Rule(name=name, expr=expr, description=description,
                           kind=kind, path=path)
        if existing is None:
            rules.append(new)
        else:
            rules[rules.index(existing)] = new
        ws.save()
        return f"registered rule '{name}' — it will run in tree_check"

    @mcp.tool()
    def tree_check(path: str = "") -> str:
        """Run every applicable rule at or under `path` — the domain's data checks.
        Structural only; domain summaries (e.g. geometry's bounding box / volume via
        tree_measure) are registered by the domain's own tools, not here."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        results = treemod.run_rules(ws.effective(), path)
        if not results:
            return "no rules apply — register some with tree_rule."
        lines = []
        for r in results:
            state = "PASS" if r.ok else "FAIL"
            where = f" @ {r.node}" if r.node else ""
            detail = f" ({r.detail})" if r.detail else ""
            lines.append(f"{state} {r.rule}{where}{detail}")
        return "\n".join(lines)

    @mcp.tool()
    def tree_solver(name: str | None = None, description: str = "",
                    wasm_b64: str | None = None, reads: list[str] | None = None,
                    params_doc: dict[str, str] | None = None,
                    medium: str = "wasm", remove: bool = False) -> str:
        """The tree's artifacts, as data — capabilities you submit, stored by
        content hash and served from artifact://{sha}. No arguments: list them.
        With name + wasm_b64 (base64 of the content, whatever the medium): register
        one. `medium` says what the content is — 'wasm' (default): sandboxed
        compute; ABI: export 'memory', 'alloc(len)->ptr',
        'run(ptr,len)->(ptr<<32|len)'; input JSON {path, slice, params}; output
        {diagnostics:[str], proposals:[{path, param, value, note?}]}; run it with
        tree_solve (fuel + memory only: no filesystem, network or imports), and it
        never writes the tree — it proposes, you apply with tree_set. 'web': a
        self-contained HTML/JS bundle a host renders against a node slice, for the
        user. 'prose': instructions an agent follows with the generic verbs. Only
        wasm output may enter the tree as derived — the other media serve
        experience and guidance, never values. `reads` declares the only branch
        prefixes wasm may see."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        solvers = ws.bom.solvers
        if name is None:
            if not solvers:
                return "no artifacts yet — register one with name + wasm_b64."
            return "\n".join(f"[{s.name}]"
                             + (f" ({s.medium})" if s.medium != "wasm" else "")
                             + f" {s.blob[:12]}… reads: {', '.join(s.reads) or '(nothing)'}"
                             + (f" — {s.description}" if s.description else "") for s in solvers)
        existing = next((s for s in solvers if s.name == name), None)
        if remove:
            if existing is None:
                return f"no solver '{name}'"
            solvers.remove(existing)
            ws.save()
            return f"removed solver '{name}' (its blob stays in the content store)"
        if wasm_b64 is None:
            return (f"[{existing.name}] ({existing.medium}) blob {existing.blob[:12]}… "
                    f"reads: {existing.reads} params: {existing.params_doc} — "
                    f"{existing.description} (content: artifact://{existing.blob})"
                    if existing else f"no artifact '{name}'")
        try:
            content = base64.b64decode(wasm_b64, validate=True)
        except Exception:
            return "wasm_b64 is not valid base64"
        try:
            sha = solvermod.save_blob(ws.blob_dir, content)
        except solvermod.SolverError as e:
            return str(e)
        new = solvermod.SolverDef(name=name, description=description, blob=sha,
                                  medium=medium, reads=reads or [],
                                  params_doc=params_doc or {})
        if existing is None:
            solvers.append(new)
        else:
            solvers[solvers.index(existing)] = new
        ws.save()
        if medium == "wasm":
            return (f"registered solver '{name}' @ {sha[:12]}… reading "
                    f"{reads or '(nothing)'} — invoke it with tree_solve, or fetch "
                    f"artifact://{sha} to run it client-side")
        return (f"registered {medium} artifact '{name}' @ {sha[:12]}… — serve it "
                f"from artifact://{sha}; it proposes no values (only wasm does)")

    @mcp.resource("solver://{sha}", name="Solver module", mime_type="application/wasm")
    def solver_module(sha: str) -> bytes:
        """A solver's code, by content hash — for clients that run solvers
        THEMSELVES. Fetch it, execute it in your own sandbox with the ABI
        (memory/alloc/run, JSON in and out), and apply the proposals you accept with
        tree_set, stamped provenance='derived', source 'solver <name>@<sha8>
        (client-run)'. The hash IS the identity: what you fetched is what everyone
        else runs. (artifact://{sha} is the same store's general channel, media
        beyond wasm included.)"""
        ws = get_ws()
        if isinstance(ws, str):
            raise ValueError(ws)
        return librarymod.solver_blob(ws.blob_dir, ws.library, sha)

    @mcp.resource("artifact://{sha}", name="Artifact",
                  mime_type="application/octet-stream")
    def artifact_content(sha: str) -> bytes:
        """Any stored artifact, by content hash — the one distribution channel
        for every medium: wasm modules (run under the ABI), web bundles (render
        against a node slice, for the user), prose skills (read and follow with
        the generic verbs). The medium is data on the descriptor that names this
        hash (tree_solver, or the package that ships it). Only wasm output may
        enter the tree as derived; whatever a user does in a web bundle comes
        back through tree_set, stamped as user input."""
        ws = get_ws()
        if isinstance(ws, str):
            raise ValueError(ws)
        return librarymod.solver_blob(ws.blob_dir, ws.library, sha)

    @mcp.resource("operation://{kind}/{name}", name="Operation contract",
                  mime_type="application/json")
    def operation_contract(kind: str, name: str) -> str:
        """The full contract behind an operation a slice's semantics surfaced:
        the operation's binding plus the solver descriptor its `contract` resolves
        to in this workspace (None when nothing provides it yet). Execute through
        the existing verb — tree_solve(contract, path) — or fetch the module at
        solver://{sha} and run it client-side."""
        ws = get_ws()
        if isinstance(ws, str):
            raise ValueError(ws)
        eff = ws.effective()
        have = {k.kind for k in eff.vocabulary}
        merged = [*eff.vocabulary,
                  *(k for k in ws.starter_vocabulary() if k.kind not in have)]
        entry = next((k for k in merged if k.kind == kind), None)
        if entry is None or name not in entry.operations:
            raise ValueError(f"no operation '{name}' on kind '{kind}'")
        op = entry.operations[name]
        solver = next((s for s in eff.solvers if s.name == op.contract), None)
        return json.dumps({"kind": kind, "operation": name, **op.model_dump(),
                           "solver": solver.model_dump() if solver else None})

    @mcp.tool(structured_output=True)
    def tree_solve(name: str, path: str = "", params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a registered solver on a branch it may read, in the SERVER's sandbox.
        Returns diagnostics and proposals — each proposal carries a ready-to-apply
        Quantity stamped provenance='derived' with the solver's identity, so a
        computed number is distinguishable from a measured one. Nothing is written:
        apply the proposals you accept with tree_set. Clients may instead fetch the
        module at solver://<sha> and run the same ABI locally."""
        ws = get_ws()
        if isinstance(ws, str):
            return {"error": ws}
        effective = ws.effective()
        solver = next((s for s in effective.solvers if s.name == name), None)
        if solver is None:
            return {"error": f"no solver '{name}' — register it with tree_solver "
                             "or install a package that carries it"}
        if solver.medium != "wasm":  # the purity boundary: only wasm proposes values
            return {"error": f"'{name}' is a {solver.medium} artifact, not compute — "
                             "only wasm output may enter the tree as derived. Fetch "
                             f"artifact://{solver.blob} and interpret it host-side."}
        if not solvermod.path_allowed(solver.reads, path):
            return {"error": f"solver '{name}' declared reads {solver.reads} — "
                             f"'{path}' is outside them"}
        node = treemod.get_node(effective, path)
        if node is None:
            return {"error": f"no node at '{path}'"}
        try:
            wasm = librarymod.solver_blob(ws.blob_dir, ws.library, solver.blob)
            out = solvermod.run_solver(
                wasm, {"path": path, "slice": node.model_dump(exclude_none=True),
                       "params": params or {}}, fuel=solver.fuel)
        except solvermod.SolverError as e:
            return {"error": str(e)}
        return {"solver": name, "blob": solver.blob[:12],
                "diagnostics": out["diagnostics"],
                "proposals": solvermod.stamp(out["proposals"], name, solver.blob, path)}

    @mcp.tool()
    def tree_package(name: str | None = None, install: str | None = None,
                     uninstall: str | None = None,
                     publish: dict[str, Any] | None = None) -> str:
        """The semantic package library — capitalized vocabulary, rules and solvers,
        shared across every account on this server. No arguments: list the library
        and this workspace's pins. install='name@version' pins a package — its whole
        dependency closure applies (its requires, transitively), your own entries
        always winning; a broken closure (missing dep, two versions of one name) is
        refused at pin time. uninstall removes the pin. publish submits {name,
        version, description, requires: [{name, version}], vocabulary, rules,
        solvers: [{name, description, reads, wasm_b64, medium: wasm|web|prose}],
        examples}. Publishing is proof-gated: every rule must be exercised by the
        package's own examples and pass — examples run with the requires closure
        staged beneath, so extending packages prove themselves in the semantics
        they will live in; every wasm solver must meet the ABI (web/prose
        artifacts are stored content-addressed, served from artifact://{sha},
        never executed). requires pin exact versions of already-published
        packages. Versions are immutable — ship a new one to evolve."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        lib = ws.library
        if publish is not None:
            try:
                blobs: dict[str, bytes] = {}
                defs = []
                for s in publish.get("solvers") or []:
                    if "wasm_b64" in s:
                        blobs[s["name"]] = base64.b64decode(s["wasm_b64"], validate=True)
                    defs.append(solvermod.SolverDef(
                        name=s["name"], description=s.get("description", ""),
                        blob=s.get("blob", ""), medium=s.get("medium", "wasm"),
                        reads=s.get("reads", []),
                        params_doc=s.get("params_doc", {})))
                pkg = librarymod.Package(
                    name=publish["name"], version=publish["version"],
                    description=publish.get("description", ""), publisher=ws.label,
                    requires=[treemod.PackageRef.model_validate(r)
                              for r in publish.get("requires", [])],
                    vocabulary=[KindDef.model_validate(k) for k in publish.get("vocabulary", [])],
                    rules=[treemod.Rule.model_validate(r) for r in publish.get("rules", [])],
                    solvers=defs,
                    examples=[treemod.Node.model_validate(n) for n in publish.get("examples", [])])
                proof = lib.publish(pkg, blobs)
            except Exception as e:
                return f"not published: {e}"
            return (f"published {pkg.name}@{pkg.version} — proof: "
                    + "; ".join(proof or ["no rules, no solvers — pure vocabulary"]))
        if install is not None:
            if "@" not in install:
                return "install takes 'name@version' — see the list for versions"
            pname, version = install.rsplit("@", 1)
            if lib.get(pname, version) is None:
                return f"no {pname}@{version} in the library"
            pins = ws.bom.packages
            trial = [p for p in pins if p.name != pname]
            trial.append(treemod.PackageRef(name=pname, version=version))
            try:  # refuse a broken closure loudly at pin time, not on first read
                lib.resolve(Bom(packages=trial))
            except ValueError as e:
                return f"not pinned: {e}"
            pins[:] = trial
            ws.save()
            return (f"pinned {pname}@{version} — its semantics (and its requires' "
                    "closure) apply here now, yours winning")
        if uninstall is not None:
            pins = ws.bom.packages
            before = len(pins)
            pins[:] = [p for p in pins if p.name != uninstall]
            if len(pins) == before:
                return f"no pin on '{uninstall}'"
            ws.save()
            return f"unpinned '{uninstall}'"
        if name is not None:
            entries = [(v, lib.get(name, v)) for v in dict(lib.list()).get(name, [])]
            if not entries:
                return f"no package '{name}' in the library"
            return "\n".join(
                f"{name}@{v} — {pkg.description or '(no description)'} "
                f"[{len(pkg.vocabulary)} kinds, {len(pkg.rules)} rules, "
                f"{len(pkg.solvers)} solvers, {len(pkg.examples)} examples] "
                f"by {pkg.publisher or '?'}"
                + (" requires: " + ", ".join(f"{r.name}@{r.version}"
                                             for r in pkg.requires)
                   if pkg.requires else "") for v, pkg in entries)
        listing = lib.list()
        pins = {p.name: p.version for p in ws.bom.packages}
        lines = []
        for pname, versions in listing:
            mark = f" — pinned @{pins[pname]}" if pname in pins else ""
            missing = (" (PIN DANGLES: version absent)"
                       if pname in pins and pins[pname] not in versions else "")
            lines.append(f"[{pname}] versions: {', '.join(versions)}{mark}{missing}")
        for pname, version in pins.items():
            if pname not in dict(listing):
                lines.append(f"[{pname}] PIN DANGLES: @{version} pinned but the "
                             "package is not in the library")
        if not any("PIN DANGLES" in line for line in lines):
            try:  # the transitive hole a per-pin check misses: requires + diamonds
                lib.resolve(ws.bom)
            except ValueError as e:
                lines.append(f"CLOSURE BROKEN: {e}")
        return "\n".join(lines) if lines else \
            "the library is empty — publish the first package with publish={...}"


def _prune(data: dict[str, Any], depth: int) -> None:
    kids = data.get("children") or []
    if depth <= 0 and kids:
        data["children"] = f"({len(kids)} children — raise depth or address them by path)"
        return
    for c in kids:
        _prune(c, depth - 1)
