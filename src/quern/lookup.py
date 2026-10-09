"""Reading one entry, or the entries that mention something, without the whole ledger.

The brief is the table of contents; these are the two ways into a chapter. `get` prints an
entry by its path or its id - the node, everything it says, and its children one line each
- and `find` lists the entries whose path, name or payload carry every word asked for. Neither
runs a rule: they read the tree as built, so they cost the build and nothing more.
"""

from __future__ import annotations

import json

from .tree import Quern, TreeStore, is_superseded


def paths_for(tree: Quern | TreeStore, ident: str) -> list[str]:
    """The paths `ident` names: itself when it is a path, else every node whose id it is,
    else every path ending with it."""
    ident = (ident or "").strip().strip("/")
    if not ident:
        return []
    if tree.get(ident) is not None:
        return [ident]
    walked = [p for p, _ in tree.walk("")]
    exact = [p for p in walked if p.rsplit("/", 1)[-1] == ident]
    return exact or [p for p in walked if p.endswith("/" + ident)]


def get(tree: Quern | TreeStore, ident: str) -> str:
    """One entry in full: its line, its links, params and payload, and its children."""
    from .brief import _line
    found = paths_for(tree, ident)
    if not found:
        return f"no entry is '{ident}'"
    if len(found) > 1:
        return f"'{ident}' names {len(found)} entries:\n" + "\n".join(f"  {p}" for p in found)
    path = found[0]
    node = tree.get(path)
    out = [_line(tree, path, node, is_superseded(tree, path), [])]
    for k, q in sorted(node.params.items()):
        out.append(f"  param {k} = {q.value} {q.unit or ''}".rstrip()
                   + ("" if q.grounded else "  (not grounded)"))
    if node.payload:
        out.append("  " + json.dumps(node.payload, indent=2, ensure_ascii=False,
                                     default=str).replace("\n", "\n  "))
    if node.meta:
        out.append("  meta " + json.dumps(node.meta, ensure_ascii=False, default=str))
    for c in node.children:
        cp = f"{path}/{c.id}"
        out.append("  " + _line(tree, cp, c, False, [])
                   + (f"  why: {c.payload.get('why')}" if isinstance(c.payload, dict)
                      and c.payload.get("why") else ""))
    return "\n".join(out)


def find(tree: Quern | TreeStore, words: list[str], *, superseded: bool = False,
         limit: int = 40) -> str:
    """The entries whose path, name or payload carry every word (case ignored), one line
    each; superseded ones only with `superseded`."""
    from .brief import _line, entry_of, section_kinds
    want = [w.casefold() for w in words if w.strip()]
    if not want:
        return "find what? give one word or more"
    sections = section_kinds(tree)
    hits: list[str] = []
    seen: set[str] = set()
    for path, node in tree.walk(""):
        if node.kind in sections:
            continue
        text = " ".join([path, node.name or "", json.dumps(node.payload, ensure_ascii=False,
                                                           default=str)]).casefold()
        if not all(w in text for w in want):
            continue
        entry = entry_of(tree, path, sections)
        if entry in seen:
            continue
        stale = is_superseded(tree, entry)
        if stale and not superseded:
            continue
        seen.add(entry)
        hits.append(_line(tree, entry, tree.get(entry), stale, []))
    if not hits:
        return f"no entry mentions {' '.join(words)}"
    more = len(hits) - limit
    return "\n".join(hits[:limit] + ([f"... {more} more (--limit)"] if more > 0 else []))
