"""quern estate — what a directory of projects owes itself, read from their ledgers.

One project's brief answers "what still binds here". Across a fleet the question changes:
what is OWED, everywhere, and what is RED. That list is worth having and it is worth having
computed, because the alternative — a hand-kept list of outstanding work beside the ledgers
— is exactly the memory a ledger exists to replace. It drifts the first time something is
discharged and nobody edits it, and then two records disagree with no way to tell which.

So this authors nothing. It walks a directory, finds the projects that have a ledger, runs
each one's brief IN ITS OWN ENVIRONMENT, and collects the debts still open and the entries
a rule holds red.

Each in its own environment is the whole difficulty. A ledger imports its project's code,
and projects do not share a venv; one of them may not even be able to depend on quern (a
package quern itself depends on cannot depend back, and its ledger is read another way).
There is therefore no single invocation that works everywhere, and this tries several in
order rather than assuming one.

**A project it cannot read is REPORTED, never skipped.** A roll-up that silently omits what
it failed to open is worse than no roll-up: it reads as "nothing owed here" and is believed.
The exit status is non-zero when any project could not be read, so a caller finds out too.

    quern estate                  # the directory holding this project
    quern estate ~/Projects       # anywhere
    quern estate --json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Tried in order, per project, until one prints a brief.
#
# The module form and not the console script, deliberately. `uv run quern` finds an
# executable on PATH when the project's own environment has none — so a project that cannot
# answer at all appears to answer, using whichever quern the CALLER happened to have. It was
# caught here doing exactly that: a project with no quern rendered its brief from the
# calling shell's venv, and reported success. `python -m quern.cli` runs in the interpreter
# uv resolved for that project and fails honestly when quern is not there, which is the
# answer this tool needs. It also survives a broken console-script shim, which is a venv
# artifact and not a missing ledger — telling those two apart by hand costs a session.
#
# The second needs nothing installed in the project at all, and is what reads the ledger of
# a project that CANNOT depend on quern: a package quern itself depends on cannot depend
# back, and its ledger is still a ledger.
_INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("uv", "run", "--no-sync", "python", "-m", "quern.cli", "brief"),
    ("uv", "run", "--no-project", "--with", "quern", "quern", "brief", "."),
)


def _child_env() -> dict[str, str]:
    """The caller's own virtualenv, removed. uv honours VIRTUAL_ENV, and this tool is
    usually run from inside one project to ask about the others — inheriting it would read
    every ledger through one project's dependencies and call the result the fleet's."""
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    return env


_ENTRY = re.compile(r"^\[(?P<kind>[^\]]+)\]\s+(?P<name>\S+)\s+—\s+(?P<rest>.*)$")
_RED = re.compile(r"RED\((?P<rule>[^)]+)\)")


@dataclass
class Reading:
    """One project's ledger, as this tool managed to read it — or failed to."""

    project: str
    how: str = ""                       # the invocation that answered
    owed: list[tuple[str, str]] = field(default_factory=list)     # (entry, one line)
    red: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, entry, rule)
    unread: str = ""                    # why, when nothing answered

    @property
    def ok(self) -> bool:
        return not self.unread


def has_ledger(project: Path) -> bool:
    """A project declares a ledger by holding one where the default entry looks, or by
    saying where it is in pyproject. Both, because a ledger that lives beside its code is
    now the ordinary case and the default path is the older one."""
    if (project / "ledger" / "tree.py").exists():
        return True
    pyproject = project / "pyproject.toml"
    if not pyproject.exists():
        return False
    try:
        return "[tool.quern]" in pyproject.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def read(project: Path, timeout: float = 300.0) -> Reading:
    """One project's brief, however it can be got. Every failure is kept, not the last one:
    when nothing works the reader deserves to see what each attempt said."""
    out = Reading(project=project.name)
    failures: list[str] = []
    for argv in _INVOCATIONS:
        try:
            done = subprocess.run(argv, cwd=project, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout,
                                  env=_child_env())
        except (OSError, subprocess.SubprocessError) as e:
            failures.append(f"{' '.join(argv[3:])}: {type(e).__name__} {e}"[:120])
            continue
        text = done.stdout or ""
        if done.returncode != 0 or "ledger brief" not in text:
            why = (done.stderr or text or "no output").strip().splitlines()
            failures.append(f"{' '.join(argv[3:])}: {why[0][:100] if why else 'silent'}")
            continue
        out.how = " ".join(argv[3:])
        _harvest(text, out)
        return out
    out.unread = " | ".join(failures) or "no invocation tried"
    return out


def _harvest(text: str, out: Reading) -> None:
    for line in text.splitlines():
        line = line.strip()
        m = _ENTRY.match(line)
        if not m:
            continue
        kind, name, rest = m.group("kind"), m.group("name"), m.group("rest")
        if red := _RED.search(line):
            out.red.append((kind, name, red.group("rule")))
        # A debt that has been paid says so in its own name rather than leaving the tree;
        # that is the discharge convention, and reading it here is the only way to tell a
        # live debt from a settled one without opening the entry.
        if kind == "debt" and "Discharged" not in rest:
            out.owed.append((name, rest))


def survey(root: Path, timeout: float = 300.0) -> list[Reading]:
    projects = sorted(p for p in root.iterdir()
                      if p.is_dir() and not p.name.startswith(".") and has_ledger(p))
    return [read(p, timeout) for p in projects]


def render(readings: list[Reading], width: int = 96) -> str:
    owed = [(r.project, n, why) for r in readings for n, why in r.owed]
    red = [(r.project, k, n, rule) for r in readings for k, n, rule in r.red]
    unread = [r for r in readings if not r.ok]

    lines = [f"{len(readings)} project(s) with a ledger, "
             f"{len(readings) - len(unread)} read"]
    lines.append("")
    lines.append(f"OWED — {len(owed)} debt(s) still open")
    for project, name, why in owed:
        lines.append(f"  {project:<18} {name:<48} {why[:width]}")
    lines.append("")
    lines.append(f"RED — {len(red)} entr(y/ies) a rule holds")
    for project, kind, name, rule in red:
        lines.append(f"  {project:<18} {kind:<10} {name:<48} {rule}")
    if unread:
        lines.append("")
        lines.append(f"UNREAD — {len(unread)} project(s) whose ledger did not answer. "
                     "These are not projects with nothing owed.")
        for r in unread:
            lines.append(f"  {r.project:<18} {r.unread[:width * 2]}")
    return "\n".join(lines)


def as_json(readings: list[Reading]) -> str:
    return json.dumps([{
        "project": r.project, "how": r.how, "unread": r.unread,
        "owed": [{"entry": n, "line": why} for n, why in r.owed],
        "red": [{"kind": k, "entry": n, "rule": rule} for k, n, rule in r.red],
    } for r in readings], ensure_ascii=False, indent=2)
