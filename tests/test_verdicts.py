"""A brief that reads the check's verdicts instead of running every rule.

On a ledger of two thousand rules the brief spent 52 s running them, where building the tree
took 1 s, and the project's check had run them all already. These pin that a recorded run is
what the brief reads, and that an entry changed since is said to be unjudged rather than
shown green.
"""

from pathlib import Path

from quern import Quern, Rule, run_rules, set_node
from quern import verdicts
from quern.brief import brief


def ledger() -> Quern:
    tree = Quern()
    set_node(tree, "cache-the-parse", {"kind": "decision", "name": "Parse each bundle once and cache it"})
    set_node(tree, "cache-the-parse/alt-per-request",
             {"kind": "alternative", "name": "Parse on every request",
              "payload": {"why": "simpler, and too slow"}})
    set_node(tree, "size-is-a-guess", {"kind": "debt", "name": "The cache is sized by a guess"})
    tree.rules.append(Rule(name="a-debt-is-paid", kind="debt", expr="1 == 0"))
    return tree


def test_a_recorded_red_is_read_back_without_running_a_rule(tmp_path: Path):
    tree = ledger()
    verdicts.record(tree, run_rules(tree), tmp_path)
    tree.rules.clear()            # nothing left to run: a red now can only be the recorded one
    out = brief(tree, verdicts=verdicts.load(tree, tmp_path))
    line = next(l for l in out.splitlines() if l.startswith("[debt]"))
    assert "RED(a-debt-is-paid)" in line and "UNCHECKED" not in line
    assert "reds as the last check recorded them" in out


def test_an_entry_changed_since_the_check_is_marked_unchecked(tmp_path: Path):
    tree = ledger()
    verdicts.record(tree, run_rules(tree), tmp_path)
    set_node(tree, "cache-the-parse/alt-per-request",
             {"kind": "alternative", "name": "Parse on every request",
              "payload": {"why": "simpler, and measured too slow"}})
    out = brief(tree, verdicts=verdicts.load(tree, tmp_path))
    changed = next(l for l in out.splitlines() if l.startswith("[decision]"))
    kept = next(l for l in out.splitlines() if l.startswith("[debt]"))
    assert changed.endswith("UNCHECKED") and "UNCHECKED" not in kept
    assert "1 entr(y/ies) changed since" in out


def test_the_check_writes_the_brief_as_text_beside_its_verdicts(tmp_path: Path):
    tree = ledger()
    written = verdicts.record(tree, run_rules(tree), tmp_path, brief_title="demo - ledger brief")
    assert [p.name for p in written] == ["verdicts.json", "brief.txt"]
    text = (tmp_path / "brief.txt").read_text(encoding="utf-8")
    assert text.startswith("demo - ledger brief\n") and "RED(a-debt-is-paid)" in text
    # deterministic: the same tree and verdicts write the same bytes
    before = (tmp_path / "verdicts.json").read_bytes()
    verdicts.record(tree, run_rules(tree), tmp_path, brief_title="demo - ledger brief")
    assert (tmp_path / "verdicts.json").read_bytes() == before


def test_no_recorded_check_is_none(tmp_path: Path):
    assert verdicts.load(ledger(), tmp_path) is None
