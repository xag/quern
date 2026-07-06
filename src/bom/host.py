"""bom.host — the reusable MCP host: one `tree_*` surface over any Workspace.

The generic Business Object Model tools (navigate, author, render, check, solve,
package) are the same verbs whatever the domain. This module registers them once
against a `Workspace` — the few seams a domain must provide: its live bom, its
effective read view (its own derived overlays plus pinned library packages), the
guard on which branches are writable, persistence, its solver blob store, its
library, and its starter vocabulary. A consumer provides the first Workspace; a
second domain is the next. One endpoint can host several by resolving a different
Workspace per call — the same code, no shared datastore.

Importing this needs the MCP SDK: install `bom[host]`.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Callable, Protocol

from mcp.server.fastmcp import FastMCP, Image

from . import geometry, library as librarymod, solver as solvermod, tree as treemod
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
        name a param from any ancestor. Declare what a kind MEANS with
        tree_vocabulary."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        ws.assert_editable(path)
        treemod.set_node(ws.bom, path, node)
        ws.save()
        return f"set '{path}'. Render it with tree_render to see the result."

    @mcp.tool(structured_output=True)
    def tree_get(path: str = "", depth: int | None = None) -> dict[str, Any]:
        """Read the BOM at `path` (default: whole tree), pruned to `depth` levels if
        given. Each slice arrives with its own semantics (the kinds present, the
        rules that apply). A workspace may expose derived branches (recomputed from
        their source on every read) — inspect and link to them, don't edit."""
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
        return f"deleted '{path}' ({len(node.children)} children went with it)"

    @mcp.tool()
    def tree_render(path: str = "", eye: list[float] | None = None,
                    look_at: list[float] | None = None, fov_deg: float = 50,
                    views: list[str] | None = None) -> Image:
        """Render a branch as a PNG from the viewpoint YOU choose: `eye` and
        `look_at` are [x, y, z] mm in the tree frame, `fov_deg` the field of view —
        a perspective wireframe (solid = material, dashed = cuts; behind-camera
        geometry clipped). Omit `eye` for a default corner view. Pass `views`
        (['top','front','left']) for flat drafting projections instead."""
        ws = get_ws()
        if isinstance(ws, str):
            raise ValueError(ws)
        solids = geometry.realize(ws.effective(), path)
        png = (geometry.render(solids, views, fmt="png") if views
               else geometry.render_perspective(solids, eye, look_at, fov_deg,
                                                fmt="png"))
        return Image(data=png, format="png")

    @mcp.tool()
    def tree_vocabulary(kind: str | None = None, description: str | None = None,
                        params: dict[str, str] | None = None,
                        links: dict[str, str] | None = None) -> str:
        """The tree's semantics, as data. No arguments: list every kind defined
        (stored + pinned packages + the domain's starter kinds). With kind +
        description: define or refine what that kind means, and optionally what its
        params/links stand for. Nothing branches on kinds — they mean exactly what
        this vocabulary says."""
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
                             + (f" links: {k.links}" if k.links else "") for k in merged)
        if description is None:
            entry = next((k for k in voc if k.kind == kind), None)
            return (f"[{entry.kind}] {entry.description} params: {entry.params} "
                    f"links: {entry.links}") if entry else f"kind '{kind}' is not defined."
        entry = next((k for k in voc if k.kind == kind), None)
        if entry is None:
            voc.append(KindDef(kind=kind, description=description,
                               params=params or {}, links=links or {}))
        else:
            entry.description = description
            if params is not None:
                entry.params = params
            if links is not None:
                entry.links = links
        ws.save()
        return f"defined kind '{kind}'"

    @mcp.tool()
    def tree_rule(name: str | None = None, expr: str | None = None,
                  description: str = "", kind: str | None = None,
                  path: str | None = None, remove: bool = False) -> str:
        """The tree's checks, as data. No arguments: list the rules. With name +
        expr: register one — a boolean expression whose builtins are STRUCTURAL only
        (param, nodes, params_of, count, sum/len/abs/min/max, ctx, and/or/not) plus
        one bridge to meaning: solve('contract', args…), e.g.
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
        """Run every applicable rule at or under `path`, plus a geometry summary
        (bounding box, signed volume estimate) of the branch."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        tree = ws.effective()
        lines = []
        try:
            solids = geometry.realize(tree, path)
            bb = geometry.bbox(solids)
            if bb is not None:
                w = bb["max"][0] - bb["min"][0]
                d = bb["max"][1] - bb["min"][1]
                h = bb["max"][2] - bb["min"][2]
                lines.append(f"bbox: {w:g} x {d:g} x {h:g} mm; "
                             f"volume ~ {geometry.volume(solids) / 1e9:.4f} m3 "
                             f"({len(solids)} solids)")
            else:
                lines.append("no solids in this branch yet")
        except ValueError as e:
            lines.append(str(e))
        results = treemod.run_rules(tree, path)
        for r in results:
            state = "PASS" if r.ok else "FAIL"
            where = f" @ {r.node}" if r.node else ""
            detail = f" ({r.detail})" if r.detail else ""
            lines.append(f"{state} {r.rule}{where}{detail}")
        if not results:
            lines.append("no rules apply — register some with tree_rule.")
        return "\n".join(lines)

    @mcp.tool()
    def tree_solver(name: str | None = None, description: str = "",
                    wasm_b64: str | None = None, reads: list[str] | None = None,
                    params_doc: dict[str, str] | None = None, remove: bool = False) -> str:
        """The tree's solvers, as data — code you submit, run in a sandbox. No
        arguments: list them. With name + wasm_b64 + reads: register one. Stored by
        content hash; `reads` declares the only branch prefixes it may see. ABI:
        export 'memory', 'alloc(len)->ptr', 'run(ptr,len)->(ptr<<32|len)'; input
        JSON {path, slice, params}; output {diagnostics:[str], proposals:[{path,
        param, value, note?}]}. A solver never writes the tree — it proposes; you
        apply with tree_set. Fuel + memory only: no filesystem, network or imports."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        solvers = ws.bom.solvers
        if name is None:
            if not solvers:
                return "no solvers yet — register one with name + wasm_b64 + reads."
            return "\n".join(f"[{s.name}] {s.blob[:12]}… reads: {', '.join(s.reads) or '(nothing)'}"
                             + (f" — {s.description}" if s.description else "") for s in solvers)
        existing = next((s for s in solvers if s.name == name), None)
        if remove:
            if existing is None:
                return f"no solver '{name}'"
            solvers.remove(existing)
            ws.save()
            return f"removed solver '{name}' (its blob stays in the content store)"
        if wasm_b64 is None:
            return (f"[{existing.name}] blob {existing.blob[:12]}… reads: {existing.reads} "
                    f"params: {existing.params_doc} — {existing.description} "
                    f"(module: solver://{existing.blob} — fetch it to run client-side)"
                    if existing else f"no solver '{name}'")
        try:
            wasm = base64.b64decode(wasm_b64, validate=True)
        except Exception:
            return "wasm_b64 is not valid base64"
        try:
            sha = solvermod.save_blob(ws.blob_dir, wasm)
        except solvermod.SolverError as e:
            return str(e)
        new = solvermod.SolverDef(name=name, description=description, blob=sha,
                                  reads=reads or [], params_doc=params_doc or {})
        if existing is None:
            solvers.append(new)
        else:
            solvers[solvers.index(existing)] = new
        ws.save()
        return (f"registered solver '{name}' @ {sha[:12]}… reading {reads or '(nothing)'} — "
                f"invoke it with tree_solve, or fetch solver://{sha} to run it client-side")

    @mcp.resource("solver://{sha}", name="Solver module", mime_type="application/wasm")
    def solver_module(sha: str) -> bytes:
        """A solver's code, by content hash — for clients that run solvers
        THEMSELVES. Fetch it, execute it in your own sandbox with the ABI
        (memory/alloc/run, JSON in and out), and apply the proposals you accept with
        tree_set, stamped provenance='derived', source 'solver <name>@<sha8>
        (client-run)'. The hash IS the identity: what you fetched is what everyone
        else runs."""
        ws = get_ws()
        if isinstance(ws, str):
            raise ValueError(ws)
        return librarymod.solver_blob(ws.blob_dir, ws.library, sha)

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
        and this workspace's pins. install='name@version' pins a package (its
        semantics apply, your own entries always winning); uninstall removes the pin.
        publish submits {name, version, description, vocabulary, rules, solvers:
        [{name, description, reads, wasm_b64}], examples}. Publishing is proof-gated:
        every rule must be exercised by the package's own examples and pass; every
        solver must meet the ABI. Versions are immutable — ship a new one to evolve."""
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
                        blob=s.get("blob", ""), reads=s.get("reads", []),
                        params_doc=s.get("params_doc", {})))
                pkg = librarymod.Package(
                    name=publish["name"], version=publish["version"],
                    description=publish.get("description", ""), publisher=ws.label,
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
            pins[:] = [p for p in pins if p.name != pname]
            pins.append(treemod.PackageRef(name=pname, version=version))
            ws.save()
            return f"pinned {pname}@{version} — its semantics apply here now (yours win)"
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
                f"by {pkg.publisher or '?'}" for v, pkg in entries)
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
        return "\n".join(lines) if lines else \
            "the library is empty — publish the first package with publish={...}"


def _prune(data: dict[str, Any], depth: int) -> None:
    kids = data.get("children") or []
    if depth <= 0 and kids:
        data["children"] = f"({len(kids)} children — raise depth or address them by path)"
        return
    for c in kids:
        _prune(c, depth - 1)
