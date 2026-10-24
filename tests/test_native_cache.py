"""A native's answer is kept while everything it read is unchanged (quern.cache).

A check runs every rule each time; the cost is in the natives the rules reach. A run with a
NativeCache calls a native again only when the subtrees it reached, the files it opened or
declared, or the code it runs have moved since the answer was kept - and never keeps what it
cannot see the inputs of.
"""

from pathlib import Path

import pytest

from quern import Node, Quern, run_rules
from quern.cache import OPENS_ONLY, NativeCache
from quern.tree import NATIVE, NATIVE_READS, NATIVE_SPEC, Rule, register_native


@pytest.fixture
def native():
    """Install a counting native for one test; `calls` says how often it really ran."""
    installed = []
    calls = []

    def install(fn, reads=None, name="test/count", spawns=False):
        def counted(tree, *args):
            calls.append(args)
            return fn(tree, *args)
        register_native(name, counted, reads=reads, spawns=spawns)
        installed.append(name)
        return calls

    yield install
    for name in installed:
        NATIVE.pop(name, None)
        NATIVE_SPEC.pop(name, None)
        NATIVE_READS.pop(name, None)


def _tree(expr="solve('test/count', 'a') >= 0"):
    return Quern(rules=[Rule(name="r", expr=expr)],
                 root=Node(id="tree", children=[
                     Node(id="a", payload={"n": 1}, children=[Node(id="a1")]),
                     Node(id="b", payload={"n": 2})]))


def _child_count(tree, path):
    return float(len(tree.get(path).children))


def test_an_answer_is_reused_until_the_subtree_it_read_moves(native, tmp_path):
    calls = native(_child_count, reads=OPENS_ONLY)
    cache = NativeCache(tmp_path)
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 1
    tree.get("b").payload["n"] = 3            # a subtree it did not read
    run_rules(tree, cache=cache)
    assert len(calls) == 1
    tree.get("a").children.append(Node(id="a2"))   # the subtree it read
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_native_that_does_not_say_what_it_reads_runs_every_time(native, tmp_path):
    calls = native(_child_count)
    cache = NativeCache(tmp_path)
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_call_that_cannot_say_what_it_reads_runs_every_time(native, tmp_path):
    calls = native(_child_count, reads=lambda tree, *args: None)
    cache = NativeCache(tmp_path)
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_file_opened_while_it_runs_is_one_of_its_reads(native, tmp_path):
    data = tmp_path / "data.txt"
    data.write_text("x", encoding="utf-8")
    calls = native(lambda tree, p: float(len(Path(data).read_text(encoding="utf-8"))),
                   reads=OPENS_ONLY)
    cache = NativeCache(tmp_path / "cache")
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 1
    data.write_text("xyz", encoding="utf-8")
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_declared_file_is_one_of_its_reads_though_it_is_not_opened(native, tmp_path):
    """State the process loaded before the call - a parsed module, data in memory - is
    declared, since the call does not open it."""
    held = tmp_path / "held.txt"
    held.write_text("one", encoding="utf-8")
    calls = native(lambda tree, p: 1.0, reads=lambda tree, *args: [held])
    cache = NativeCache(tmp_path / "cache")
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 1
    held.write_text("three", encoding="utf-8")
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_file_added_under_a_declared_directory_is_seen(native, tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    calls = native(lambda tree, p: 1.0, reads=lambda tree, *args: [folder])
    cache = NativeCache(tmp_path / "cache")
    tree = _tree()
    run_rules(tree, cache=cache)
    (folder / "new.txt").write_text("n", encoding="utf-8")
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_native_that_writes_outside_the_cache_is_not_kept(native, tmp_path):
    out = tmp_path / "out.txt"

    def writes(tree, p):
        out.write_text("w", encoding="utf-8")
        return 1.0
    calls = native(writes, reads=OPENS_ONLY)
    cache = NativeCache(tmp_path / "cache")
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_native_that_reaches_the_whole_tree_moves_with_any_entry(native, tmp_path):
    calls = native(lambda tree, p: float(len(tree.root.children)), reads=OPENS_ONLY)
    cache = NativeCache(tmp_path)
    tree = _tree()
    run_rules(tree, cache=cache)
    tree.get("b").payload["n"] = 3
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_refusal_is_never_kept(native, tmp_path):
    def refuses(tree, p):
        raise ValueError("no")
    calls = native(refuses, reads=OPENS_ONLY)
    cache = NativeCache(tmp_path)
    tree = _tree()
    assert not run_rules(tree, cache=cache)[0].ok
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_run_without_a_cache_calls_every_native(native, tmp_path):
    calls = native(_child_count, reads=OPENS_ONLY)
    tree = _tree()
    run_rules(tree)
    run_rules(tree)
    assert len(calls) == 2


def test_the_answer_kept_is_the_answer_given(native, tmp_path):
    native(_child_count, reads=OPENS_ONLY)
    cache = NativeCache(tmp_path)
    tree = _tree("solve('test/count', 'a') == 1")
    first = run_rules(tree, cache=cache)
    again = run_rules(tree, cache=cache)
    assert [r.ok for r in first] == [r.ok for r in again] == [True]
    assert cache.reused == 1


def _starts_a_process(tree, p):
    import subprocess
    import sys
    subprocess.run([sys.executable, "-c", "pass"], check=True)
    return 1.0


def test_a_native_that_starts_a_process_is_not_kept(native, tmp_path):
    calls = native(_starts_a_process, reads=OPENS_ONLY)
    cache = NativeCache(tmp_path)
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 2


def test_a_native_whose_reads_cover_its_processes_is_kept(native, tmp_path):
    calls = native(_starts_a_process, reads=OPENS_ONLY, spawns=True)
    cache = NativeCache(tmp_path)
    tree = _tree()
    run_rules(tree, cache=cache)
    run_rules(tree, cache=cache)
    assert len(calls) == 1
