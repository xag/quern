"""Run the ledger's rules and report. `uv run python -m ledger.check`

Exit code is 1 when something is UNACCOUNTED FOR - a red no node expects, an expectation
whose red has gone, or an entry that left the record without a tombstone. Not on red as
such: this ledger ships red on purpose (the host's compute boundary is unmetered and
blocking), and a gate that fails on every run it will ever have tells nobody anything when
it fails. The standing red is still printed on a passing run, marked `red*`, because going
quiet about a debt the moment it is accounted for would trade one silence for another.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from quern import expectations, get_node, reckon, run_rules
from quern.roll import audit, write

from .tree import build


_ROOT = Path(__file__).resolve().parents[1]
_ROLL = "ledger/roll.json"

# WHICH revision's roll to compare against, and it is not a detail. Locally the
# working tree holds the edit under judgement and HEAD is the last good state, so
# HEAD is right. In CI the commit under judgement IS HEAD - and carries the roll
# written beside it - so comparing against HEAD compares the tree with itself and
# passes whatever it is handed. CI names the base it is diffing from instead.
_REV = os.environ.get("LEDGER_ROLL_REV", "HEAD")


def main() -> int:
    quern = build()
    results = run_rules(quern)
    # NOT `any red` - this ledger ships red by decision, so gating on red would fail
    # every run it will ever have, and a gate that never passes says nothing when it
    # fails. `news` is red nobody accounted for; `carried` is red a node declares it
    # expects, by rule name, in its own meta; `stale` is an expectation whose red has
    # gone, which must be withdrawn rather than left as a standing licence. See #42.
    news, carried, stale = reckon(quern, results)
    red = [r for r in results if not r.ok]
    # A tombstone with no `was` excuses nothing - the right way round, because
    # forgetting it leaves the check red, never green.
    excused = {n.payload["was"] for _, n in quern.walk("")
               if n.kind == "tombstone" and n.payload.get("was")}
    removals, looked = audit(quern, _ROOT, _ROLL, _REV, excused)

    # ASCII only: this prints to a Windows console under cp1252, which mangles anything
    # prettier and turns a clear report into mojibake exactly when it matters.
    expected_at = {(r.node, r.rule) for r in carried}
    for r in sorted(results, key=lambda r: (r.ok, r.rule, r.node)):
        mark = ("ok  " if r.ok else
                "red*" if (r.node, r.rule) in expected_at else "RED ")
        at = f" @ {r.node}" if r.node else ""
        detail = f" - {r.detail}" if r.detail else ""
        print(f"{mark}{r.rule}{at}{detail}")

    for line in removals:
        print(f"GONE {line}")
    if not looked:
        print(f"note: no roll at {_REV} - nothing was compared, so nothing was")
        print("      checked for removal. Honest on the first run of this check,")
        print("      and a problem on any other.")

    print()
    # The roll is written on a red run too, and that is deliberate. A red rule is a
    # debt carried on purpose - some of these ledgers ship red by decision - while
    # the roll only records WHAT EXISTS. Gating it on `not red` would deny a
    # permanently-red ledger the one protection it most needs. Only an unexplained
    # removal makes the roll unsafe to rewrite, because rewriting it then would
    # launder the very thing the check just caught.
    if not removals:
        write(quern, _ROOT / _ROLL)

    # Carried reds are reported on a PASSING run too. They are the ledger's standing
    # debts, and a gate that goes quiet about them the moment they are accounted for
    # would trade one silence for another.
    if carried:
        print(f"{len(carried)} red carried on purpose, of {len(results)} rule(s):")
        for r in carried:
            node = get_node(quern, r.node) if r.node else None
            why = (expectations(node).get(r.rule) if node else "") or ""
            print(f"  red* {r.node or r.rule}: {why}")
        print()

    if not news and not stale and not removals:
        print(f"{len(results)} rule(s), nothing unaccounted for; roll written.")
        return 0

    if news:
        print(f"{len(news)} of {len(results)} rule(s) RED and unaccounted for.")
    if stale:
        print(f"{len(stale)} expectation(s) outlived the red they excused.")
    if removals:
        print(f"{len(removals)} entr(y/ies) left the record without saying so.")
    print()
    # The node carries its own reason; the report should not paraphrase it from memory,
    # which is how a check drifts out of step with the thing it checks.
    for r in news:
        node = get_node(quern, r.node) if r.node else None
        why = (node.payload.get("note") if node else None) or r.detail or ""
        print(f"  {r.node or r.rule}: {why}")
    for line in stale:
        print(f"  {line}")
    print()
    print("Discharge a red node by doing the work it names - never by editing the ledger.")
    print("If a red is intended, say so where it is red: the node's")
    print("meta['expected:<rule>'] = '<why>'. It is refused once that rule goes green.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
