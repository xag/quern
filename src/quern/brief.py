"""quern brief — a ledger at one line per entry, so reading it costs what it should.

A ledger's job is to make future work cheaper, and a record that must be read in
full to be used does the opposite: every session pays the whole history to find
the dozen claims that still bind. This module renders a composed tree as the
working set — one line per current entry: kind, id, name, the links it declares,
the params still ungrounded, the rules red on it — and *omits* what is settled.
Superseded entries, and the retraction/compaction machinery that records what
left, are counted in a trailer instead of spent on: the tree and git keep them,
and a reader who wants one goes to it by path.

This is the progressive-disclosure contract: the brief is the table of contents,
`tree.get(path)` or the source is the chapter. An agent that starts from the
brief reads tens of lines, not thousands, and knows exactly which entries are
load-bearing before it opens any of them.

Vocabulary-blind, like the navigator: kinds are labels, links are names, and the
only meanings consumed are the core's own — `supersedes` for currency, `grounded`
for soundness, rule verdicts for red. Nothing here knows what a debt is.
"""

from __future__ import annotations

from .tree import Quern, TreeStore, is_superseded, run_rules, said_words, superseders


def brief(tree: Quern | TreeStore, *, all: bool = False, fat: bool = False) -> str:
    """The ledger's working set, one line per top-level entry.

    `all` includes superseded entries (marked) instead of counting them away.
    `fat` appends each entry's `said_words` and sorts by it, descending — the
    curation view: the first line is the first thing to tighten."""
    reds = _reds_by_entry(tree)
    entries = [(p, n) for p, n in tree.walk("") if "/" not in p]

    kept: list[tuple[str, str, int]] = []  # (line, path, words)
    omitted: dict[str, int] = {}
    for path, node in entries:
        stale = is_superseded(tree, path)
        if stale and not all:
            omitted[node.kind or "?"] = omitted.get(node.kind or "?", 0) + 1
            continue
        kept.append((_line(tree, path, node, stale, reds.get(path, [])),
                     path, said_words(tree, path)))

    if fat:
        kept.sort(key=lambda e: -e[2])
        lines = [f"{line}  ~{words}w" for line, _, words in kept]
    else:
        lines = [line for line, _, _ in kept]

    total = sum(words for _, _, words in kept)
    trailer = [f"{len(kept)} entr(y/ies), ~{total} words of prose."]
    if omitted:
        gone = ", ".join(f"{v} {k}" for k, v in sorted(omitted.items()))
        trailer.append(f"omitted as no longer current: {gone} "
                       "(the tree keeps them; --all shows them).")
    if reds.get(None):
        trailer.append("rules not evaluated: " + reds[None][0])
    return "\n".join(lines + [""] + trailer)


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


def _reds_by_entry(tree) -> dict:
    """Failed rules keyed by the top-level entry they fall under. A rule that
    cannot run (a native contract not registered in this process) degrades to a
    note under key None — honest, never silently green."""
    try:
        results = run_rules(tree)
    except Exception as e:
        return {None: [f"{e} - run the project's own check for verdicts"]}
    out: dict = {}
    for r in results:
        if r.ok:
            continue
        entry = (r.node or "").split("/")[0]
        out.setdefault(entry, []).append(r.rule)
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse
    from pathlib import Path

    from .navigate import load_build, project_label

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
    args = ap.parse_args(argv)
    root = Path(args.project).resolve()
    tree = load_build(root, args.module)()
    print(f"{project_label(root)} - ledger brief")
    print(brief(tree, all=args.all, fat=args.fat))


if __name__ == "__main__":
    main()
