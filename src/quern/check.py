"""`quern check`: run a project's ledger and say whether anything is unaccounted for.

Every ledgered project used to carry its own `ledger/check.py`, and 22 of them carried it
in 13 versions: the same run of the rules, the same comparison with the committed roll, the
same exit code, each copy drifting on its own. Only one of them recorded the verdicts the
brief reads. This is that script, once.

What it does, in order:

1. builds the tree (`<project>/ledger/tree.py:build`, or `[tool.quern] ledger`, or `--module`);
2. runs every rule, keeping a native's answer while what it read is unchanged
   (`quern.cache.NativeCache` under `.quern/check`; `--fresh` runs every native);
3. sorts the reds with `reckon`: a red no node expects, a red a node expects
   (`meta["expected:<rule>"]`), and an expectation whose red has gone;
4. compares the tree with the roll committed at `rev` (`quern.roll.audit`), excusing what a
   tombstone's `was` names;
5. rewrites the roll unless something left without saying so, and records the verdicts and
   the brief for `quern brief` (`quern.verdicts`).

Exit 1 when something is unaccounted for: a red no node expects, a stale expectation, or a
removal. Not on red as such: a ledger may ship red by decision, and a gate that fails on
every run it will ever have tells nobody anything when it fails.

`rev` matters. Locally the working tree holds the edit under judgement and HEAD is the last
good state. In CI the commit under judgement IS HEAD, so comparing against HEAD compares the
tree with itself; CI names the base it diffs from (`LEDGER_ROLL_REV`, or `--rev`).

A project whose check does more than this keeps its own script and calls `check()` from it,
or keeps its own entirely; this is the common part, not a framework.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .cache import CHECK_DEFAULT, NativeCache
from .roll import audit, write
from .tree import Quern, expectations, get_node, reckon, run_rules

ROLL_DEFAULT = "ledger/roll.json"


def default_rev() -> str:
    return os.environ.get("LEDGER_ROLL_REV", "HEAD")


def check(root: str | Path, build: Callable[[], Quern], *, rev: str | None = None,
          roll: str = ROLL_DEFAULT, cache_dir: str = CHECK_DEFAULT, fresh: bool = False,
          title: str = "", out: Callable[[str], None] = print) -> int:
    """Run the check over the tree `build()` returns, for the project at `root`. Prints
    the report through `out` (ASCII only: a Windows console under cp1252 mangles anything
    prettier) and returns the exit code."""
    root = Path(root)
    rev = rev or default_rev()
    tree = build()
    results = run_rules(tree, cache=None if fresh else NativeCache(root / cache_dir))
    news, carried, stale = reckon(tree, results)
    # A tombstone with no `was` excuses nothing - the right way round, because forgetting
    # it leaves the check red, never green.
    excused = {n.payload["was"] for _, n in tree.walk("")
               if n.kind == "tombstone" and n.payload.get("was")}
    removals, looked = audit(tree, root, roll, rev, excused)

    expected_at = {(r.node, r.rule) for r in carried}
    for r in sorted(results, key=lambda r: (r.ok, r.rule, r.node)):
        mark = "ok  " if r.ok else "red*" if (r.node, r.rule) in expected_at else "RED "
        at = f" @ {r.node}" if r.node else ""
        detail = f" - {r.detail}" if r.detail else ""
        out(f"{mark}{r.rule}{at}{detail}")
    for line in removals:
        out(f"GONE {line}")
    if not looked:
        out(f"note: no roll at {rev} - nothing was compared, so nothing was checked for")
        out("      removal. Honest on the first run of a ledger, and a problem on any other.")
    out("")

    # The roll is written on a red run too: a red rule may be a debt carried on purpose,
    # while the roll only records what exists. Only an unexplained removal makes it unsafe
    # to rewrite, because rewriting it then would launder what the check just caught.
    if not removals:
        write(tree, root / roll)
    from . import verdicts
    verdicts.record(tree, results, root / cache_dir, brief_title=title)

    if carried:
        out(f"{len(carried)} red carried on purpose, of {len(results)} rule(s):")
        for r in carried:
            node = get_node(tree, r.node) if r.node else None
            why = (expectations(node).get(r.rule) if node else "") or ""
            out(f"  red* {r.node or r.rule}: {why}")
        out("")

    if not news and not stale and not removals:
        out(f"{len(results)} rule(s), nothing unaccounted for; roll written.")
        return 0
    if news:
        out(f"{len(news)} of {len(results)} rule(s) RED and unaccounted for.")
    if stale:
        out(f"{len(stale)} expectation(s) outlived the red they excused.")
    if removals:
        out(f"{len(removals)} entr(y/ies) left the record without saying so.")
    out("")
    for r in news:
        node = get_node(tree, r.node) if r.node else None
        why = (node.payload.get("note") if node else None) or r.detail or ""
        out(f"  {r.node or r.rule}: {why}")
    for line in stale:
        out(f"  {line}")
    out("")
    out("Discharge a red node by doing the work it names - never by editing the ledger.")
    out("If a red is intended, say so where it is red: the node's")
    out("meta['expected:<rule>'] = '<why>'. It is refused once that rule goes green.")
    return 1
