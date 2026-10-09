"""The last check's verdicts, kept beside the ledger, so reading the ledger costs a read.

The brief marks the entries a rule is red on, and finding that out means running every
rule - every proof, every solver - which on a large ledger takes most of a minute. The
project's own check runs them all anyway, before every commit. This module is where that
run is kept: `record` writes the verdicts the check computed, per entry, with a digest of
what each entry said when it was judged, and the brief's text beside them; `load` gives
the brief those verdicts back, and names the entries that changed since, which no rule has
judged in their present words.

Two files, both deterministic, so they change in a diff only when the ledger or a verdict
did:

  verdicts.json  {"entries": {entry: digest}, "red": {entry: [rule, ...]}} - an entry is
                 what the brief prints one line for (brief.entry_of), its digest covers it
                 and everything under it (roll.digest of each node, with path and kind).
  brief.txt      the brief, rendered from those verdicts: the table of contents as plain
                 text, which a reader searches without loading the ledger at all.

What the verdicts cannot know is a rule red on an unchanged entry because something
OUTSIDE the ledger moved - code a bound reads, a tape a law holds. They are the check's
verdicts as of its run, and they say so; `quern brief --fresh` runs the rules.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .roll import digest
from .tree import Quern, TreeStore

VERDICTS = "verdicts.json"
BRIEF = "brief.txt"


def entries(tree: Quern | TreeStore) -> dict[str, str]:
    """Every entry the brief prints a line for, by path, with a digest of what it and
    everything under it says."""
    from .brief import entry_of, section_kinds
    sections = section_kinds(tree)
    parts: dict[str, list[str]] = {}
    for path, node in tree.walk(""):
        if node.kind in sections:
            continue
        entry = entry_of(tree, path, sections)
        parts.setdefault(entry, []).append(f"{path}\t{node.kind}\t{digest(node)}")
    return {e: hashlib.sha256("\n".join(sorted(p)).encode("utf-8")).hexdigest()[:12]
            for e, p in sorted(parts.items())}


def reds(tree: Quern | TreeStore, results) -> dict[str, list[str]]:
    """The failed rules of a run, by the entry they fall under; a rule bound to no node
    falls under the empty path, the ledger as a whole."""
    from .brief import entry_of, section_kinds
    sections = section_kinds(tree)
    out: dict[str, set[str]] = {}
    for r in results:
        if not r.ok:
            out.setdefault(entry_of(tree, r.node or "", sections), set()).add(r.rule)
    return {e: sorted(rs) for e, rs in sorted(out.items())}


def record(tree: Quern | TreeStore, results, directory: str | Path, *,
           brief_title: str = "") -> list[Path]:
    """Write a check's verdicts and the brief rendered from them into `directory`.
    `results` is the check's `run_rules` over the same tree. Returns the paths written."""
    from .brief import brief
    d = Path(directory)
    data = {"entries": entries(tree), "red": reds(tree, results)}
    verdicts = d / VERDICTS
    verdicts.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
    text = brief(tree, verdicts=Verdicts(data["red"], set()))
    out = d / BRIEF
    out.write_text((brief_title + "\n" if brief_title else "") + text + "\n", encoding="utf-8")
    return [verdicts, out]


class Verdicts:
    """What the brief needs of a recorded check: the reds by entry, and the entries whose
    words changed since it ran."""

    def __init__(self, red: dict[str, list[str]], unchecked: set[str]):
        self.red = red
        self.unchecked = unchecked


def load(tree: Quern | TreeStore, directory: str | Path) -> Verdicts | None:
    """The recorded verdicts for `tree`, or None when the check has recorded none."""
    p = Path(directory) / VERDICTS
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    then = data.get("entries") or {}
    now = entries(tree)
    unchecked = {e for e, d in now.items() if then.get(e) != d}
    red = {e: rs for e, rs in (data.get("red") or {}).items() if e in now or e == ""}
    return Verdicts(red, unchecked)
