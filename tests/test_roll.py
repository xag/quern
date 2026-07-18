"""The roll: seeing a node that is no longer there.

Every other check in this repository asks whether what is in the tree is sound.
These ask the one question a tree cannot answer about itself.
"""

import json

from quern import Quern, set_node
from quern.roll import committed, dumps, read, rekinded, roll, vanished, write


def ledger() -> Quern:
    tree = Quern()
    set_node(tree, "key-for-key", {"kind": "decision"})
    set_node(tree, "key-for-key/alt-fallback", {"kind": "alternative"})
    set_node(tree, "the-eight-are-human", {"kind": "hypothesis"})
    set_node(tree, "the-eight-are-human/a-reader-reports", {"kind": "falsification"})
    set_node(tree, "release", {"kind": "gate"})
    return tree


def test_the_roll_is_every_node_by_path_and_kind():
    assert roll(ledger()) == [
        {"path": "key-for-key", "kind": "decision"},
        {"path": "key-for-key/alt-fallback", "kind": "alternative"},
        {"path": "release", "kind": "gate"},
        {"path": "the-eight-are-human", "kind": "hypothesis"},
        {"path": "the-eight-are-human/a-reader-reports", "kind": "falsification"},
    ]


def test_the_roll_is_canonical_so_a_diff_shows_the_tree_not_the_formatter():
    tree = ledger()
    assert dumps(tree) == dumps(ledger())
    assert dumps(tree).endswith("\n")
    assert json.loads(dumps(tree)) == roll(tree)


def test_nothing_vanishes_from_a_tree_that_did_not_change():
    tree = ledger()
    assert vanished(tree, roll(tree)) == []


def test_a_deleted_node_is_reported():
    before = roll(ledger())
    tree = ledger()
    tree.root.children = [c for c in tree.root.children if c.id != "release"]

    assert vanished(tree, before) == [{"path": "release", "kind": "gate"}]


def test_a_deleted_parent_reports_its_children_too():
    """chores deleted `the-french-gui-has-never-been-seen` and its discharge child
    in one commit. Both were on the roll; both come back."""
    before = roll(ledger())
    tree = ledger()
    tree.root.children = [c for c in tree.root.children if c.id != "the-eight-are-human"]

    assert [e["path"] for e in vanished(tree, before)] == [
        "the-eight-are-human", "the-eight-are-human/a-reader-reports"]


def test_a_rename_is_a_deletion_and_is_reported_as_one():
    """spec-studio's baae263 rewrote `sampling-first-no-model-of-our-own` into
    `deal-over-a-switchboard-channel`, id and all. In a diff that reads as an edit.
    On the roll the old id is simply gone, which is what it is."""
    before = roll(ledger())
    tree = ledger()
    tree.root.children = [c for c in tree.root.children if c.id != "key-for-key"]
    set_node(tree, "en-fallback-for-missing-keys", {"kind": "decision"})

    assert [e["path"] for e in vanished(tree, before)] == [
        "key-for-key", "key-for-key/alt-fallback"]


def test_an_excused_path_is_spared():
    """What earns an excuse is the domain's business — this module only honours it."""
    before = roll(ledger())
    tree = ledger()
    tree.root.children = [c for c in tree.root.children if c.id != "release"]

    assert vanished(tree, before, excused={"release"}) == []


def test_a_rekinded_node_is_reported_though_it_never_vanished():
    """switchboard's 8d9a17a turned a hypothesis into a decision and deleted its
    falsification child. The node is still there; what it claims about itself is
    not. `vanished` cannot see this and does not pretend to — `rekinded` does."""
    before = roll(ledger())
    tree = ledger()
    set_node(tree, "the-eight-are-human", {"kind": "decision"})

    assert vanished(tree, before) == []
    assert rekinded(tree, before) == [
        {"path": "the-eight-are-human", "was": "hypothesis", "now": "decision"}]


def test_write_and_read_round_trip(tmp_path):
    tree = ledger()
    p = tmp_path / "roll.json"
    write(tree, p)
    assert read(p) == roll(tree)


def test_reading_an_absent_roll_is_empty_not_an_error(tmp_path):
    assert read(tmp_path / "never-written.json") == []


def test_git_that_cannot_answer_returns_none_never_an_empty_roll(tmp_path):
    """The distinction the caller must not lose: None is "I could not look", and a
    caller that cannot look has not checked. Reporting [] here would turn a blind
    gate into a green one, which is the exact failure this whole module exists to
    remove."""
    assert committed(tmp_path, "ledger/roll.json") is None


def test_git_reads_the_roll_at_head(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    (repo / "ledger").mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a],
                                    capture_output=True, check=True)
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")

    tree = ledger()
    write(tree, repo / "ledger" / "roll.json")
    run("add", "-A")
    run("commit", "-qm", "roll")

    assert committed(repo, "ledger/roll.json") == roll(tree)

    # ...and the working tree may now drop a node without the committed roll moving
    tree.root.children = [c for c in tree.root.children if c.id != "release"]
    assert vanished(tree, committed(repo, "ledger/roll.json")) == [
        {"path": "release", "kind": "gate"}]
