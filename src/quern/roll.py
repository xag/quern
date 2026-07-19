"""The roll: what the tree held last time, so that deletion can be seen at all.

Every rule in this substrate runs against the tree as it is now. That is enough to
ask whether what is there is sound, and it can never ask whether something that
ought to be there is missing — a deleted node is not red, it is absent, and a gate
counting ungrounded params on a debt that no longer exists counts zero and passes.
This is not a gap in the rules; a rule has nothing to evaluate. Absence is invisible
from inside a tree.

So the comparison has to be against the previous tree, and in a repository the
previous tree is already kept: git has it. The roll is the smallest artifact that
makes the comparison mechanical — every node's path and kind, canonically ordered,
written beside the tree and committed with it. Diff the built tree against the roll
at HEAD and a vanished id is a fact, not a memory.

Two properties carry the weight. It is INDUCTIVE: each commit is checked against its
parent, so nothing needs to read the whole history to be sure of it. And it is
SELF-CLOSING when a domain excuses deletions by leaving a tombstone behind, because
the tombstone is itself a node on the roll — removing it trips the same check.

Domain-free, like everything in the core: this module knows that nodes have paths
and kinds, and that `excused` ids were removed on purpose. What earns an excuse —
a retraction, a migration, an amendment — is the vocabulary's business, decided by
the caller who passes the set in.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .tree import Quern, TreeStore


def roll(tree: Quern | TreeStore) -> list[dict[str, str]]:
    """Every node in the tree as {path, kind}, ordered by path.

    Path, not id: a node moved to a different parent has left the place the record
    said it was, and that is a change worth seeing. Kind travels with it so that a
    node quietly re-kinded — a hypothesis rewritten into a decision, which is how a
    belief gets retracted without anyone saying so — is visible in the same diff."""
    return sorted(({"path": p, "kind": n.kind} for p, n in tree.walk("")),
                  key=lambda e: e["path"])


def dumps(tree: Quern | TreeStore) -> str:
    """The roll as canonical JSON: sorted, two-space, trailing newline. Stable
    enough that a diff shows the change to the tree and never the formatter."""
    return json.dumps(roll(tree), indent=2, ensure_ascii=False) + "\n"


def write(tree: Quern | TreeStore, path: str | Path) -> None:
    Path(path).write_text(dumps(tree), encoding="utf-8")


def read(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def committed(repo: str | Path, relpath: str, rev: str = "HEAD") -> list[dict[str, str]] | None:
    """The roll as of `rev`, read out of git.

    None means git could not answer — no repository, or no roll at that revision,
    which is the honest state on the commit that first introduces one. It does NOT
    mean "nothing vanished": a caller that cannot see the previous tree has not
    checked, and should say so rather than report a pass. That distinction is the
    whole reason this returns None instead of []."""
    try:
        out = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{relpath}"],
                             capture_output=True, text=True, check=False)
    except OSError:
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def vanished(tree: Quern | TreeStore, previous: Iterable[dict[str, Any]],
             excused: Iterable[str] = ()) -> list[dict[str, str]]:
    """Entries on the previous roll with no node at that path today, minus those the
    caller excuses by path.

    A rename is a deletion and an addition, and is reported as the deletion — which
    is the point, because rewriting a node in place while keeping its meaning is the
    move that erases a record most quietly and reads, in a diff, like an edit."""
    spared = set(excused)
    here = {p for p, _ in tree.walk("")}
    return [dict(e) for e in previous
            if e["path"] not in here and e["path"] not in spared]


def audit(tree: Quern | TreeStore, repo: str | Path, relpath: str,
          rev: str = "HEAD", excused: Iterable[str] = (),
          ) -> tuple[list[str], bool]:
    """The whole removal check in one call: `(complaints, looked)`.

    Empty complaints and `looked` False is NOT a pass — it means the roll could not
    be read at `rev`, so nothing was compared. Every caller must report those two
    states differently, which is why this returns the flag rather than folding it
    into an empty list. A gate that says "all clear" when it never opened its eyes
    is the failure the roll exists to remove, and it would be an odd module that
    reintroduced it in its own convenience wrapper.

    WHICH `rev`, and it is not a detail. Working locally, the edit under judgement is
    in the working tree and HEAD is the last good state, so HEAD is right. In CI the
    commit under judgement IS HEAD and carries the roll written beside it, so HEAD
    compares the tree with itself and passes anything. CI must name the base it is
    diffing from.

    `excused` stays the caller's: what earns a removal is vocabulary, and this module
    knows only that some paths were removed on purpose."""
    previous = committed(repo, relpath, rev)
    if previous is None:
        return [], False

    out = [f"{e['path']} ({e['kind']}) was on the roll and is gone - supersede it, "
           "discharge it, or retract it with a tombstone, but do not delete it"
           for e in vanished(tree, previous, excused)]
    out += [f"{e['path']} was a {e['was']} and is now a {e['now']} - a belief "
            "rewritten into a decision was not confirmed, it stopped being falsifiable"
            for e in rekinded(tree, previous)]
    return out, True


def rekinded(tree: Quern | TreeStore,
             previous: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Nodes still present but under a different kind than the roll recorded. A
    hypothesis that became a decision was not tested and confirmed — it stopped
    being falsifiable, and its falsification children left with it."""
    kinds = {p: n.kind for p, n in tree.walk("")}
    return [{"path": e["path"], "was": e.get("kind", ""), "now": kinds[e["path"]]}
            for e in previous
            if e["path"] in kinds and kinds[e["path"]] != e.get("kind", "")]
