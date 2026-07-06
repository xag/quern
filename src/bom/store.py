"""bom.store — scale as a choice of store, never a change of model.

`SqliteStore` is the `TreeStore` protocol on disk: the same verbs `Bom` answers
by walking live objects, answered here by indexes — path ranges for walks, a
kind column for kind queries, a link table for backlinks (supersession,
where-used, lineage invalidation). Every free function in `bom.tree` (and so
every rule evaluation, every solver slice, every host tool) accepts either; a
consumer opens a store instead of loading a Bom and nothing else changes.

The store is structural only, like the search: it persists nodes, params, links
and payloads without reading any of them, and holds the tree's semantics
(vocabulary, rules, solvers, package pins) as one small document — semantics
stay conversation-sized even when the tree does not. Node edits commit
immediately, each in its own transaction; semantics edits are in-memory lists
(exactly a Bom's) persisted by `save()`, matching the Workspace pattern.

SQLite in WAL mode carries the honest concurrency story this buys: snapshot
reads, one writer. Multi-user change workflow stays consumer code — the
substrate stores; it does not arbitrate.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from .solver import SolverDef
from .tree import (
    Bom,
    KindDef,
    Node,
    PackageRef,
    Rule,
    _coerce,
    _fold_payload,
    _segs,
)

# after '/' in ASCII: `path >= p || '/' AND path < p || '0'` is the subtree range
_AFTER_SLASH = "0"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    path   TEXT PRIMARY KEY,   -- slash path from the root
    parent TEXT NOT NULL,      -- '' for top-level nodes
    pos    INTEGER NOT NULL,   -- sibling order
    okey   TEXT NOT NULL,      -- materialized preorder key (zero-padded pos chain)
    kind   TEXT NOT NULL DEFAULT '',
    doc    TEXT NOT NULL       -- the node, JSON, children omitted (rows are the tree)
);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(parent, pos);
CREATE INDEX IF NOT EXISTS nodes_kind   ON nodes(kind);
CREATE INDEX IF NOT EXISTS nodes_okey   ON nodes(okey);
CREATE TABLE IF NOT EXISTS links (
    src    TEXT NOT NULL,      -- node path declaring the link
    name   TEXT NOT NULL,
    target TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS links_name_target ON links(name, target);
CREATE INDEX IF NOT EXISTS links_src ON links(src);
CREATE TABLE IF NOT EXISTS semantics (
    id  INTEGER PRIMARY KEY CHECK (id = 1),
    doc TEXT NOT NULL          -- vocabulary/rules/solvers/packages, one document
);
"""


class SqliteStore:
    """A `TreeStore` backed by one SQLite file. Open it where the tree lives;
    pass it wherever a `Bom` goes."""

    def __init__(self, path: Path | str) -> None:
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        row = self._db.execute("SELECT doc FROM semantics WHERE id=1").fetchone()
        doc = json.loads(row[0]) if row else {}
        self.vocabulary: list[KindDef] = [
            KindDef.model_validate(k) for k in doc.get("vocabulary", [])]
        self.rules: list[Rule] = [
            Rule.model_validate(r) for r in doc.get("rules", [])]
        self.solvers: list[SolverDef] = [
            SolverDef.model_validate(s) for s in doc.get("solvers", [])]
        self.packages: list[PackageRef] = [
            PackageRef.model_validate(p) for p in doc.get("packages", [])]

    def close(self) -> None:
        self._db.close()

    def save(self) -> None:
        """Persist the semantics lists (node edits persist as they happen)."""
        doc = json.dumps({
            "vocabulary": [k.model_dump(exclude_defaults=True) for k in self.vocabulary],
            "rules": [r.model_dump(exclude_none=True) for r in self.rules],
            "solvers": [s.model_dump() for s in self.solvers],
            "packages": [p.model_dump() for p in self.packages],
        })
        with self._db:
            self._db.execute(
                "INSERT INTO semantics (id, doc) VALUES (1, ?) "
                "ON CONFLICT (id) DO UPDATE SET doc=excluded.doc", (doc,))

    # --- the TreeStore protocol ---------------------------------------------

    def get(self, path: str, depth: int | None = None) -> Node | None:
        anchor = "/".join(_segs(path))
        if not anchor:
            root = Node(id="tree")
            root.children = self._hydrate_children("", depth)
            return root
        row = self._db.execute(
            "SELECT doc FROM nodes WHERE path=?", (anchor,)).fetchone()
        if row is None:
            return None
        node = _node_of(anchor, row[0])
        if depth is None or depth > 0:
            node.children = self._hydrate_children(
                anchor, None if depth is None else depth - 1)
        return node

    def set(self, path: str, data: dict[str, Any]) -> Node:
        segs = _segs(path)
        if not segs:
            raise ValueError("the root is not editable — address a child path")
        with self._db:
            parent = ""
            for seg in segs[:-1]:
                child = f"{parent}/{seg}" if parent else seg
                if not self._exists(child):
                    self._insert(parent, Node(id=seg), shallow=True)
                parent = child
            leaf_path = "/".join(segs)
            existing = self._row_node(leaf_path)
            data = _fold_payload(
                data, existing.payload if existing is not None else {})
            if existing is None:
                node = Node(id=segs[-1], **data)
                self._insert(parent, node)
                return self.get(leaf_path)
            patched = existing.model_copy(update={
                k: _coerce(Node, k, v) for k, v in data.items()})
            self._write_row(leaf_path, patched)
            if "children" in data:
                self._delete_range(leaf_path)
                for pos, child in enumerate(patched.children):
                    self._insert(leaf_path, child, pos=pos)
        return self.get(leaf_path)

    def delete(self, path: str) -> Node:
        segs = _segs(path)
        if not segs:
            raise ValueError("the root is not deletable")
        anchor = "/".join(segs)
        node = self.get(anchor)
        if node is None:
            raise ValueError(f"no node at '{path}'")
        with self._db:
            self._delete_range(anchor)
            self._db.execute("DELETE FROM nodes WHERE path=?", (anchor,))
            self._db.execute("DELETE FROM links WHERE src=?", (anchor,))
        return node

    def walk(self, under: str = "") -> Iterator[tuple[str, Node]]:
        anchor = "/".join(_segs(under))
        if anchor:
            row = self._db.execute(
                "SELECT doc FROM nodes WHERE path=?", (anchor,)).fetchone()
            if row is None:
                return
            yield anchor, _node_of(anchor, row[0])
            rows = self._db.execute(
                "SELECT path, doc FROM nodes WHERE path >= ? AND path < ? "
                "ORDER BY okey", (anchor + "/", anchor + _AFTER_SLASH))
        else:
            rows = self._db.execute("SELECT path, doc FROM nodes ORDER BY okey")
        for p, doc in rows:
            yield p, _node_of(p, doc)

    def children(self, path: str) -> list[str]:
        anchor = "/".join(_segs(path))
        rows = self._db.execute(
            "SELECT path FROM nodes WHERE parent=? ORDER BY pos", (anchor,))
        return [p.rsplit("/", 1)[-1] for (p,) in rows]

    def backlinks(self, name: str, target: str) -> list[str]:
        rows = self._db.execute(
            "SELECT src FROM links WHERE name=? AND target=?", (name, target))
        return sorted(p for (p,) in rows)

    def find(self, query: str | None = None, kind: str | None = None,
             has_param: str | None = None, links_to: str | None = None,
             under: str = "", current_only: bool = False,
             limit: int = 20) -> list[tuple[str, Node]]:
        """Same contract as `Bom.find`, index-narrowed: `kind` hits its column,
        `current_only` its link index; the rest filters the narrowed rows."""
        anchor = "/".join(_segs(under))
        if anchor and not self._exists(anchor):
            return []
        where, args = [], []
        if kind is not None:
            where.append("kind=?")
            args.append(kind)
        if anchor:
            where.append("(path=? OR (path >= ? AND path < ?))")
            args += [anchor, anchor + "/", anchor + _AFTER_SLASH]
        sql = "SELECT path, doc FROM nodes"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY okey"
        q = query.lower() if query else None
        stale = (set(t for (t,) in self._db.execute(
            "SELECT DISTINCT target FROM links WHERE name='supersedes'"))
            if current_only else None)
        out: list[tuple[str, Node]] = []
        for p, doc in self._db.execute(sql, args):
            if len(out) >= limit:
                break
            n = _node_of(p, doc)
            hay = " ".join([n.id, n.name, n.kind, *n.meta.values()]).lower()
            if ((q is None or q in hay)
                    and (has_param is None or has_param in n.params)
                    and (links_to is None
                         or any(links_to in v for v in n.links.values()))
                    and (stale is None or p not in stale)):
                out.append((p, n))
        return out

    # --- moving whole trees ---------------------------------------------------

    def ingest(self, tree: Bom) -> None:
        """Load a Bom into the store — nodes, semantics and all. The store must
        be empty: this is a migration, not a merge."""
        if self._db.execute("SELECT 1 FROM nodes LIMIT 1").fetchone():
            raise ValueError("the store already holds a tree — ingest into a "
                             "fresh one, or edit through set()")
        with self._db:
            for pos, child in enumerate(tree.root.children):
                self._insert("", child, pos=pos)
        self.vocabulary = [k.model_copy(deep=True) for k in tree.vocabulary]
        self.rules = [r.model_copy(deep=True) for r in tree.rules]
        self.solvers = [s.model_copy(deep=True) for s in tree.solvers]
        self.packages = [p.model_copy(deep=True) for p in tree.packages]
        self.save()

    def snapshot(self) -> Bom:
        """The whole store as an in-memory Bom — for export, diffing, or a
        consumer API that expects the model. On a large tree this is the one
        deliberately expensive call here."""
        return Bom(vocabulary=[k.model_copy(deep=True) for k in self.vocabulary],
                   rules=[r.model_copy(deep=True) for r in self.rules],
                   solvers=[s.model_copy(deep=True) for s in self.solvers],
                   packages=[p.model_copy(deep=True) for p in self.packages],
                   root=self.get(""))

    # --- rows ------------------------------------------------------------------

    def _exists(self, path: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM nodes WHERE path=?", (path,)).fetchone() is not None

    def _row_node(self, path: str) -> Node | None:
        row = self._db.execute(
            "SELECT doc FROM nodes WHERE path=?", (path,)).fetchone()
        return _node_of(path, row[0]) if row else None

    def _hydrate_children(self, path: str, depth: int | None) -> list[Node]:
        if depth is not None and depth < 0:
            return []
        out = []
        for p, doc in self._db.execute(
                "SELECT path, doc FROM nodes WHERE parent=? ORDER BY pos", (path,)):
            node = _node_of(p, doc)
            node.children = self._hydrate_children(
                p, None if depth is None else depth - 1)
            out.append(node)
        return out

    def _next_pos(self, parent: str) -> int:
        (pos,) = self._db.execute(
            "SELECT COALESCE(MAX(pos), -1) + 1 FROM nodes WHERE parent=?",
            (parent,)).fetchone()
        return pos

    def _okey(self, parent: str, pos: int) -> str:
        if parent:
            (pokey,) = self._db.execute(
                "SELECT okey FROM nodes WHERE path=?", (parent,)).fetchone()
        else:
            pokey = ""
        return f"{pokey}/{pos:08d}"

    def _insert(self, parent: str, node: Node, pos: int | None = None,
                shallow: bool = False) -> None:
        path = f"{parent}/{node.id}" if parent else node.id
        if pos is None:
            pos = self._next_pos(parent)
        self._db.execute(
            "INSERT INTO nodes (path, parent, pos, okey, kind, doc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (path, parent, pos, self._okey(parent, pos), node.kind, _doc_of(node)))
        self._write_links(path, node)
        if not shallow:
            for cpos, child in enumerate(node.children):
                self._insert(path, child, pos=cpos)

    def _write_row(self, path: str, node: Node) -> None:
        self._db.execute(
            "UPDATE nodes SET kind=?, doc=? WHERE path=?",
            (node.kind, _doc_of(node), path))
        self._write_links(path, node)

    def _write_links(self, path: str, node: Node) -> None:
        self._db.execute("DELETE FROM links WHERE src=?", (path,))
        self._db.executemany(
            "INSERT INTO links (src, name, target) VALUES (?, ?, ?)",
            [(path, name, "/".join(_segs(t)))
             for name, targets in node.links.items() for t in targets])

    def _delete_range(self, anchor: str) -> None:
        """Drop every row strictly under `anchor` (not the anchor itself)."""
        lo, hi = anchor + "/", anchor + _AFTER_SLASH
        self._db.execute(
            "DELETE FROM links WHERE src >= ? AND src < ?", (lo, hi))
        self._db.execute(
            "DELETE FROM nodes WHERE path >= ? AND path < ?", (lo, hi))


def _doc_of(node: Node) -> str:
    return node.model_dump_json(exclude={"children"}, exclude_defaults=True)


def _node_of(path: str, doc: str) -> Node:
    data = json.loads(doc)
    data["id"] = path.rsplit("/", 1)[-1]
    return Node.model_validate(data)


__all__ = ["SqliteStore"]
