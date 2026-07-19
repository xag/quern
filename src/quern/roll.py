"""The roll: what the tree held last time, so that deletion can be seen at all.

Every rule in this substrate runs against the tree as it is now. That is enough to
ask whether what is there is sound, and it can never ask whether something that
ought to be there is missing — a deleted node is not red, it is absent, and a gate
counting ungrounded params on a debt that no longer exists counts zero and passes.
This is not a gap in the rules; a rule has nothing to evaluate. Absence is invisible
from inside a tree.

So the comparison has to be against the previous tree, and in a repository the
previous tree is already kept: git has it. The roll is the smallest artifact that
makes the comparison mechanical — every node's path, kind, and a digest of what it
says, canonically ordered, written beside the tree and committed with it. Diff the
built tree against the roll at HEAD and a vanished id is a fact, not a memory.

The digest is there because deletion is the *rare* erasure. The common one keeps
the id and rewrites the words: the node is still on the roll, still the right kind,
and no longer says what the record said it did. Path and kind alone wave that
through (korean-gpt-coach 1d11a9e rewrote a debt's premise in place and the check
reported zero removals). So the roll also records WHAT WAS SAID — name, payload,
and every param's value — and `rewritten` fires when it changes. What it
deliberately does not digest: a param's grounding (provenance, `grounded`, source),
because grounding a debt's values is the one in-place act a record sanctions, and
its trace belongs to provenance, not to the roll; `meta`, which is where the
acknowledgement below lives; and links, which are lifecycle (a gate's `admits`
grows with every release).

A rewrite that is *acknowledged* is not silent, and the acknowledgement is the node's
own: `meta["amended"] = "<digest> <why>"`, naming the digest of what the node says
NOW. That excuses exactly one content state — edit the words again and the note no
longer matches, so it cannot be left in place as a standing licence. It is the
tombstone pattern for words instead of nodes: visible in the diff, precise about
what it excuses, and it closes over itself.

Two properties carry the weight. It is INDUCTIVE: each commit is checked against its
parent, so nothing needs to read the whole history to be sure of it. And it is
SELF-CLOSING when a domain excuses deletions by leaving a tombstone behind, because
the tombstone is itself a node on the roll — removing it trips the same check.

Domain-free, like everything in the core: this module knows that nodes have paths,
kinds and words, that `excused` ids were removed on purpose, and that an `amended`
note acknowledges a rewrite. What earns an excuse — a retraction, a migration, a
correction that must instead travel by supersession — is the vocabulary's business.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .tree import Node, Quern, TreeStore

# The reserved meta key, in the same register as tree.SUPERSEDES: the one meta name
# the core reads. Its value starts with the digest of what the node says now,
# optionally followed by prose ("3fa9c2e1b0d4 wording only, claim unchanged").
AMENDED = "amended"


def said(node: Node) -> dict[str, Any]:
    """What a node says, as distinct from what it is linked to, how its values are
    grounded, or what its meta notes: the name, the payload, and each param's bare
    value and unit. This is the content whose silent rewrite the roll exists to see."""
    return {"name": node.name,
            "payload": node.payload,
            "params": {k: [q.value, q.unit] for k, q in node.params.items()}}


def digest(node: Node) -> str:
    """A short stable digest of `said(node)` — canonical JSON, sha256, 12 hex chars.
    Stable across formatters and dict order; changed by any change to the words."""
    canon = json.dumps(said(node), sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def roll(tree: Quern | TreeStore) -> list[dict[str, str]]:
    """Every node in the tree as {path, kind, digest}, ordered by path.

    Path, not id: a node moved to a different parent has left the place the record
    said it was, and that is a change worth seeing. Kind travels with it so that a
    node quietly re-kinded — a hypothesis rewritten into a decision, which is how a
    belief gets retracted without anyone saying so — is visible in the same diff.
    The digest travels with both so that a node quietly re-worded is too."""
    return sorted(({"path": p, "kind": n.kind, "digest": digest(n)}
                   for p, n in tree.walk("")),
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
    out += [f"{e['path']} ({e['kind']}) no longer says what the roll recorded "
            f"({e['was']} -> {e['now']}) - a correction travels by supersession: add "
            "the corrected entry and leave this one standing. If only the wording "
            f"moved and the claim did not, acknowledge it: meta['{AMENDED}'] = "
            f"'{e['now']} <why>'"
            for e in rewritten(tree, previous)]
    out += [f"{e['path']} was a {e['was']} and is now a {e['now']} - a belief "
            "rewritten into a decision was not confirmed, it stopped being falsifiable"
            for e in rekinded(tree, previous)]
    return out, True


def rewritten(tree: Quern | TreeStore,
              previous: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Nodes still present, still their kind, that no longer say what the roll
    recorded — the erasure that keeps the id and rewrites the words, which a diff
    of path and kind waves through. `was`/`now` are the recorded and current digests.

    An entry whose previous roll line carries no digest is skipped, not failed: a
    roll written before digests existed recorded nothing to compare, and claiming a
    rewrite there would be inventing a memory. The induction resumes one commit
    later, when the rewritten roll carries them.

    A node whose meta acknowledges the current digest (`meta["amended"]` starting
    with it) is excused: the rewrite was recorded, which is all the roll polices.
    The note excuses exactly this content state — change the words again and it no
    longer matches."""
    here = {p: n for p, n in tree.walk("")}
    out = []
    for e in previous:
        node = here.get(e["path"])
        recorded = e.get("digest")
        if node is None or not recorded:
            continue
        now = digest(node)
        if now == recorded:
            continue
        note = node.meta.get(AMENDED, "")
        if note.split(maxsplit=1)[0:1] == [now]:
            continue
        out.append({"path": e["path"], "kind": node.kind,
                    "was": recorded, "now": now})
    return out


def rekinded(tree: Quern | TreeStore,
             previous: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Nodes still present but under a different kind than the roll recorded. A
    hypothesis that became a decision was not tested and confirmed — it stopped
    being falsifiable, and its falsification children left with it."""
    kinds = {p: n.kind for p, n in tree.walk("")}
    return [{"path": e["path"], "was": e.get("kind", ""), "now": kinds[e["path"]]}
            for e in previous
            if e["path"] in kinds and kinds[e["path"]] != e.get("kind", "")]
