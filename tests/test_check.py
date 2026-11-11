"""`quern check`: the ledger check every project used to copy, run once from quern.

Each test is a law the command must keep: what exits 0, what exits 1, and what it leaves
behind for the next run and for the brief.
"""

import subprocess
import textwrap

import pytest

from quern import Quern, Rule, set_node
from quern.check import check
from quern.cli import run
from quern.verdicts import load


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "ledger").mkdir()
    return tmp_path


def _commit(root):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "x")


def _ledger(*, keep_gate=True, sound=True, expected=False) -> Quern:
    tree = Quern(rules=[Rule(name="sound", kind="gate", expr="1 == 1" if sound else "1 == 0")])
    set_node(tree, "a-decision", {"kind": "decision"})
    if keep_gate:
        meta = {"expected:sound": "carried on purpose"} if expected else {}
        set_node(tree, "release", {"kind": "gate", "meta": meta})
    return tree


def test_the_command_finds_the_ledger_writes_the_roll_and_records_what_the_brief_reads(tmp_path):
    root = _repo(tmp_path)
    (root / "ledger" / "tree.py").write_text(textwrap.dedent("""
        from quern import Quern, Rule, set_node

        def build():
            tree = Quern(rules=[Rule(name="sound", kind="gate", expr="1 == 1")])
            set_node(tree, "release", {"kind": "gate"})
            return tree
    """), encoding="utf-8")

    run(["check", str(root)])  # exit 0 returns; any other code raises SystemExit

    assert (root / "ledger" / "roll.json").exists()
    from quern.navigate import load_build
    kept = load(load_build(root, None)(), root / ".quern" / "check")
    assert kept is not None and kept.red == {} and kept.unchecked == set()


def test_an_entry_gone_since_the_committed_roll_fails_and_the_roll_is_not_rewritten(tmp_path):
    root = _repo(tmp_path)
    assert check(root, _ledger, out=lambda s: None) == 0
    _commit(root)
    before = (root / "ledger" / "roll.json").read_text(encoding="utf-8")

    lines = []
    assert check(root, lambda: _ledger(keep_gate=False), out=lines.append) == 1
    assert any(line.startswith("GONE release") for line in lines)
    assert (root / "ledger" / "roll.json").read_text(encoding="utf-8") == before


def test_a_red_nobody_expects_fails_and_the_same_red_expected_passes(tmp_path):
    root = _repo(tmp_path)
    assert check(root, lambda: _ledger(sound=False), out=lambda s: None) == 1
    assert check(root, lambda: _ledger(sound=False, expected=True), out=lambda s: None) == 0


def test_an_expectation_that_outlived_its_red_fails(tmp_path):
    root = _repo(tmp_path)
    assert check(root, lambda: _ledger(sound=True, expected=True), out=lambda s: None) == 1


def test_the_cli_returns_the_exit_code(tmp_path):
    root = _repo(tmp_path)
    (root / "ledger" / "tree.py").write_text(textwrap.dedent("""
        from quern import Quern, Rule, set_node

        def build():
            tree = Quern(rules=[Rule(name="sound", kind="gate", expr="1 == 0")])
            set_node(tree, "release", {"kind": "gate"})
            return tree
    """), encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        run(["check", str(root)])
    assert stop.value.code == 1
