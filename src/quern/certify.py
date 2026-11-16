"""A certificate: what the standards a tree holds say of one of its nodes.

A standard is knowledge like any other: rules in a package, and, in the tree, the nodes
that say what those rules are for. Two kinds are read here by name (their meaning is the
`certification@` package's, published to the registry and pinned like any other):

- a `criterion` names the rules that judge one thing about a subject: payload
  `applies_to` (the kind of node it judges, or several), `rules` (their names) and
  `measures` (a free label: completeness, reliability, consistency, presentation);
- a `level` is a use a subject may be put to: payload `of` (the kind of subject) and the
  link `requires` to the criteria that use needs.

`certificate(tree, path)` runs the rules every criterion of the subject's kind names, on
the subject and what is beneath it, and answers with each criterion (held, or the reds
that break it) and each level (reached, or the criteria that block it). Nothing here
knows a domain: a package that publishes a better criterion, a new rule or another level
changes the certificate of everything it applies to, and no code that reads certificates
changes with it.

A red says what it saw. The rule's own description and messages travel with it, and a
contract may register an *explainer* beside its native: the same arguments, answered
with the lines a person needs (which param, against what) where the contract answers a
count. Explainers are host code for the same reason natives are.
"""

from __future__ import annotations

from typing import Any, Callable

from .tree import Node, Quern, TreeStore, run_rules

CRITERION = "criterion"
LEVEL = "level"

EXPLAINERS: dict[str, Callable[..., list[str]]] = {}  # contract -> fn(tree, *args) -> lines


def register_explainer(contract: str, fn: Callable[..., list[str]]) -> None:
    """Install what a contract's count is a count of: `fn(tree, *args)` takes the
    arguments the rule gave the contract and returns one line per thing counted."""
    EXPLAINERS[contract] = fn


def _kinds(value: Any) -> list[str]:
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def _why(tree, reads) -> list[str]:
    out: list[str] = []
    for r in reads or []:
        if r.call != "solve" or not r.args or r.args[0] not in EXPLAINERS:
            continue
        try:
            out += [str(line) for line in EXPLAINERS[r.args[0]](tree, *r.args[1:])]
        except Exception as e:  # noqa: BLE001 - an explainer never takes a certificate down
            out.append(f"({r.args[0]} could not say what it counted: {e})")
    return out


def certificate(tree: Quern | TreeStore, path: str, context: dict[str, Any] | None = None,
                solver_runner=None) -> dict[str, Any]:
    """What every criterion and level of the subject's kind says of the node at `path`.

    {"subject", "kind", "criteria": [{"criterion", "name", "say", "measures", "held", "reds":
    [{"rule", "node", "verdict", "says", "messages", "detail", "why"}]}], "levels":
    [{"level", "name", "say", "requires", "allows", "reached", "blocked_by"}],
    "reached": [level paths]}

    `say` is the criterion's or level's payload `say` as its standard wrote it (its name
    for people, per language), None when it states none; `requires` and `allows` are the
    level's own, so a reader lists what a use needs and what it opens without knowing
    the standard.

    A criterion is held when every rule it names holds wherever it ran, on the subject
    or beneath it. A rule that is absent (a value it needs is not stated) or in error
    breaks it: not judged is not passed. A name no rule carries, and a rule that ran on
    nothing, are reds of the criterion itself, since a standard that names what does
    not judge the subject certifies nothing. A level whose `requires` names a path that
    is no criterion of this kind is blocked by it."""
    subject = tree.get(path, depth=0)
    if subject is None:
        raise ValueError(f"no node at '{path}'")
    kind = subject.kind
    known = {r.name: r for r in tree.rules}

    criteria: dict[str, dict[str, Any]] = {}
    for cpath, c in list(tree.walk("", kind=CRITERION)):   # a store on disk too: no tree.root
        if kind not in _kinds(c.payload.get("applies_to")):
            continue
        names = [str(n) for n in c.payload.get("rules") or []]
        reds: list[dict[str, Any]] = []
        for missing in [n for n in names if n not in known]:
            reds.append({"rule": missing, "node": path, "verdict": "error",
                         "says": "", "messages": None, "detail": "no rule of that name", "why": []})
        run = [n for n in names if n in known]
        results = run_rules(tree, path, context=context, solver_runner=solver_runner,
                            rules=run, trace=True) if run else []
        ran = {r.rule for r in results}
        for idle in [n for n in run if n not in ran]:
            reds.append({"rule": idle, "node": path, "verdict": "error", "says": known[idle].description,
                         "messages": None, "detail": "the rule judges nothing at or under the subject",
                         "why": []})
        for r in results:
            if r.verdict == "holds":
                continue
            rule = known[r.rule]
            reds.append({"rule": r.rule, "node": r.node, "verdict": r.verdict, "says": rule.description,
                         "messages": rule.messages, "detail": r.detail or "", "why": _why(tree, r.reads)})
        criteria[cpath] = {"criterion": cpath, "name": c.name, "say": c.payload.get("say"),
                           "measures": c.payload.get("measures", ""),
                           "held": not reds, "reds": reds}

    levels = []
    for lpath, lv in list(tree.walk("", kind=LEVEL)):
        if kind not in _kinds(lv.payload.get("of")):
            continue
        requires = list(lv.links.get("requires", []))
        blocked = [c for c in requires if not criteria.get(c, {}).get("held")]
        levels.append({"level": lpath, "name": lv.name, "say": lv.payload.get("say"), "requires": requires,
                       "allows": list(lv.payload.get("allows") or []), "reached": not blocked,
                       "blocked_by": blocked})
    return {"subject": path, "kind": kind, "criteria": list(criteria.values()), "levels": levels,
            "reached": [lv["level"] for lv in levels if lv["reached"]]}
