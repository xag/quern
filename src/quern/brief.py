"""quern brief — a ledger at one line per entry, so reading it costs what it should.

A ledger's job is to make future work cheaper, and a record that must be read in
full to be used does the opposite: every session pays the whole history to find
the dozen claims that still bind. This module renders a composed tree as the
working set — one line per current entry: kind, path, name, the links it declares,
the params still ungrounded, the rules red on it — and *omits* what is settled.
Superseded entries, and the retraction/compaction machinery that records what
left, are counted in a trailer instead of spent on: the tree and git keep them,
and a reader who wants one goes to it by path.

A tree may be organised in branches: a kind whose definition says `section` is a
heading, not a claim, and its children are the entries. The brief renders such a
node as a heading with its entry count and its reds, and the entries beneath it,
indented, with their full paths — so a ledger of two hundred entries opens as ten
headings, and `--under` reads one branch alone. A tree with no section kinds
renders as one list, as before.

This is the progressive-disclosure contract: the brief is the table of contents,
`tree.get(path)` or the source is the chapter. An agent that starts from the
brief reads tens of lines, not thousands, and knows exactly which entries are
load-bearing before it opens any of them.

Vocabulary-blind, like the navigator: kinds are labels, links are names, and the
only meanings consumed are the core's own — `supersedes` for currency, `grounded`
for soundness, rule verdicts for red, `section` for structure. Nothing here knows
what a debt is.
"""

from __future__ import annotations

from .tree import Quern, TreeStore, is_superseded, run_rules, said_words, superseders


def section_kinds(tree: Quern | TreeStore) -> set[str]:
    """The kinds whose definition says `section`: headings, whose children are entries."""
    vocabulary = getattr(tree, "vocabulary", None) or []
    return {k.kind for k in vocabulary if getattr(k, "section", None)}


def brief(tree: Quern | TreeStore, *, all: bool = False, fat: bool = False,
          under: str = "") -> str:
    """The ledger's working set, one line per entry, under headings where the tree
    has sections.

    `all` includes superseded entries (marked) instead of counting them away.
    `fat` appends each entry's `said_words` and sorts by it, descending, as one
    flat list — the curation view: the first line is the first thing to tighten.
    `under` briefs one branch: the entries beneath that path."""
    sections = section_kinds(tree)
    reds = _reds_by_entry(tree, sections)

    kept: list[tuple[str, str, int]] = []  # (line, path, words)
    omitted: dict[str, int] = {}
    headings = 0

    def entries_under(path: str) -> list[tuple[str, object]]:
        node = tree.get(path)
        if node is None:
            return []
        return [(_join(path, c.id), c) for c in node.children]

    def current_count(path: str) -> tuple[int, int]:
        """(entries, red entries) beneath a section, sections descended, stale skipped."""
        n = red = 0
        for p, c in entries_under(path):
            if c.kind in sections:
                a, b = current_count(p)
                n, red = n + a, red + b
            elif all or not is_superseded(tree, p):
                n += 1
                red += 1 if reds.get(p) else 0
        return n, red

    def render(path: str, indent: str) -> None:
        nonlocal headings
        for p, node in entries_under(path):
            if node.kind in sections:
                headings += 1
                n, red = current_count(p)
                bits = [f"{indent}== {p}", "—", node.name or "",
                        f"({n} entr{'y' if n == 1 else 'ies'}"
                        + (f", {red} RED" if red else "") + ")"]
                kept.append(("  ".join(b for b in bits if b), p, -1))
                render(p, indent + "  ")
                continue
            stale = is_superseded(tree, p)
            if stale and not all:
                omitted[node.kind or "?"] = omitted.get(node.kind or "?", 0) + 1
                continue
            kept.append((indent + _line(tree, p, node, stale, reds.get(p, [])),
                         p, said_words(tree, p)))

    render(under, "")

    entries = [e for e in kept if e[2] >= 0]
    if fat:
        entries.sort(key=lambda e: -e[2])
        lines = [f"{line.strip()}  ~{words}w" for line, _, words in entries]
    else:
        lines = [line for line, _, _ in kept]

    total = sum(words for _, _, words in entries)
    trailer = [f"{len(entries)} entr(y/ies), ~{total} words of prose"
               + (f", in {headings} section(s)" if headings else "") + "."]
    if omitted:
        gone = ", ".join(f"{v} {k}" for k, v in sorted(omitted.items()))
        trailer.append(f"omitted as no longer current: {gone} "
                       "(the tree keeps them; --all shows them).")
    if reds.get(None):
        trailer.append("rules not evaluated: " + reds[None][0])
    return "\n".join(lines + [""] + trailer)


def _join(base: str, cid: str) -> str:
    return f"{base}/{cid}" if base else cid


def _line(tree, path, node, stale, red: list[str]) -> str:
    bits = [f"[{node.kind or '?'}]", path, "—", node.name or ""]
    if stale:
        bits.append(f"(superseded by {', '.join(superseders(tree, path))})")
    for rel, targets in sorted(node.links.items()):
        bits.append(f"{rel}->{','.join(targets)}")
    hollow = [k for k, q in node.params.items() if not q.grounded]
    if hollow:
        bits.append("!" + ",".join(sorted(hollow)))
    kinds: dict[str, int] = {}
    for c in node.children:
        kinds[c.kind or "?"] = kinds.get(c.kind or "?", 0) + 1
    if kinds:
        bits.append("{" + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())) + "}")
    if red:
        bits.append("RED(" + ", ".join(sorted(red)) + ")")
    return "  ".join(b for b in bits if b)


def entry_of(tree: Quern | TreeStore, path: str, sections: set[str]) -> str:
    """The entry a path falls under: the first node on the way down that is not a
    section. A rule red on a decision's alternative is red on the decision's line;
    one red on a section's entry is red on that entry, not on the heading."""
    segs = [s for s in (path or "").split("/") if s]
    prefix = ""
    for seg in segs:
        prefix = _join(prefix, seg)
        node = tree.get(prefix)
        if node is None or node.kind not in sections:
            return prefix
    return prefix


def _reds_by_entry(tree, sections: set[str]) -> dict:
    """Failed rules keyed by the entry they fall under. A rule that cannot run (a
    native contract not registered in this process) degrades to a note under key
    None — honest, never silently green."""
    try:
        results = run_rules(tree)
    except Exception as e:
        return {None: [f"{e} - run the project's own check for verdicts"]}
    out: dict = {}
    for r in results:
        if r.ok:
            continue
        out.setdefault(entry_of(tree, r.node or "", sections), []).append(r.rule)
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse
    from pathlib import Path

    from .cli import _utf8_streams
    from .navigate import load_build, project_label

    # The brief prints en-dashes and RED markers from ledger prose; a Windows console
    # defaults to cp1252 and dies on the first one. `quern brief` (the CLI entry) already
    # reconfigures the streams; this module entry point crashed on the estate's biggest
    # ledger until it did the same — found by a reader following the skill's own first
    # instruction.
    _utf8_streams()

    ap = argparse.ArgumentParser(
        prog="quern brief",
        description="one line per current ledger entry - the working set, "
                    "not the archaeology")
    ap.add_argument("project", nargs="?", default=".",
                    help="project root holding ledger/tree.py (default: current dir)")
    ap.add_argument("--module", metavar="PATH[:ATTR]",
                    help="override the build entry (default: <project>/ledger/tree.py:build)")
    ap.add_argument("--all", action="store_true",
                    help="include superseded entries instead of counting them away")
    ap.add_argument("--fat", action="store_true",
                    help="sort by said_words, heaviest first - the curation view")
    ap.add_argument("--under", default="", metavar="PATH",
                    help="brief one branch: the entries beneath this path")
    args = ap.parse_args(argv)
    root = Path(args.project).resolve()
    tree = load_build(root, args.module)()
    print(f"{project_label(root)} - ledger brief")
    print(brief(tree, all=args.all, fat=args.fat, under=args.under))


if __name__ == "__main__":
    main()
