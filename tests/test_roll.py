"""The roll: seeing a node that is no longer there.

Every other check in this repository asks whether what is in the tree is sound.
These ask the one question a tree cannot answer about itself.
"""

import json

from quern import Quern, set_node
from quern.roll import (
    AMENDED, audit, committed, digest, dumps, read, rekinded, rewritten, roll,
    vanished, write,
)


def ledger() -> Quern:
    tree = Quern()
    set_node(tree, "key-for-key", {"kind": "decision",
                                   "payload": {"rationale": "blank strings ship silently"}})
    set_node(tree, "key-for-key/alt-fallback", {"kind": "alternative"})
    set_node(tree, "the-eight-are-human", {"kind": "hypothesis"})
    set_node(tree, "the-eight-are-human/a-reader-reports", {"kind": "falsification"})
    set_node(tree, "release", {"kind": "gate"})
    return tree


def test_the_roll_is_every_node_by_path_kind_and_what_it_says():
    tree = ledger()
    entries = roll(tree)
    assert [(e["path"], e["kind"]) for e in entries] == [
        ("key-for-key", "decision"),
        ("key-for-key/alt-fallback", "alternative"),
        ("release", "gate"),
        ("the-eight-are-human", "hypothesis"),
        ("the-eight-are-human/a-reader-reports", "falsification"),
    ]
    by_path = {p: n for p, n in tree.walk("")}
    assert all(e["digest"] == digest(by_path[e["path"]]) for e in entries)


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

    assert [(e["path"], e["kind"]) for e in vanished(tree, before)] == [
        ("release", "gate")]


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


def test_a_rewritten_payload_is_reported_though_nothing_vanished():
    """korean-gpt-coach's 1d11a9e rewrote a debt's premise in place. The id stayed,
    the kind stayed, and the check reported zero removals — the erasure the roll
    could not see. Now it is the digest that moved."""
    before = roll(ledger())
    tree = ledger()
    tree.get("key-for-key").payload["rationale"] = "it seemed tidier this way"

    assert vanished(tree, before) == []
    assert rekinded(tree, before) == []
    assert [e["path"] for e in rewritten(tree, before)] == ["key-for-key"]


def test_a_renamed_node_is_a_rewrite_too():
    """transponder marks supersession by editing names ('[SUPERSEDED] …'). The name
    is part of what an entry says."""
    before = roll(ledger())
    tree = ledger()
    tree.get("the-eight-are-human").name = "[SUPERSEDED] the eight are human"

    assert [e["path"] for e in rewritten(tree, before)] == ["the-eight-are-human"]


def test_a_param_value_rewrite_is_seen_but_grounding_it_is_not():
    """The one in-place act the record sanctions: discharging a debt grounds its
    values. The VALUE is what was said and is digested; provenance, `grounded` and
    source are the trace of checking it, and belong to grounding, not the roll."""
    from quern.provenance import Quantity

    tree = ledger()
    tree.get("key-for-key").params["strings"] = Quantity(
        value=47, unit="string", provenance="unreviewed", grounded=False,
        source="generator")
    before = roll(tree)

    # grounding the same value: the discharge act, invisible on purpose
    tree.get("key-for-key").params["strings"] = Quantity(
        value=47, unit="string", provenance="verified", grounded=True,
        source="checked by a reader, 2026-07")
    assert rewritten(tree, before) == []

    # rewriting the value itself: a different claim, and it fires
    tree.get("key-for-key").params["strings"].value = 512
    assert [e["path"] for e in rewritten(tree, before)] == ["key-for-key"]


def test_an_amended_note_excuses_exactly_one_content_state():
    """The acknowledgement is the node's own meta, naming the digest of what it says
    NOW. It excuses that state and no other — edit the words again and it no longer
    matches, so it cannot be left in place as a standing licence."""
    before = roll(ledger())
    tree = ledger()
    node = tree.get("key-for-key")
    node.payload["rationale"] = "blank strings ship silently to a reader"

    assert [e["path"] for e in rewritten(tree, before)] == ["key-for-key"]

    node.meta[AMENDED] = f"{digest(node)} wording only, claim unchanged"
    assert rewritten(tree, before) == []

    node.payload["rationale"] = "rewritten again, note left behind"
    assert [e["path"] for e in rewritten(tree, before)] == ["key-for-key"]


def test_a_roll_without_digests_is_skipped_not_failed():
    """A roll written before digests existed recorded nothing to compare; claiming a
    rewrite there would be inventing a memory. The induction resumes one commit
    later, when the rewritten roll carries them."""
    before = [{"path": e["path"], "kind": e["kind"]} for e in roll(ledger())]
    tree = ledger()
    tree.get("key-for-key").payload["rationale"] = "changed under an old roll"

    assert rewritten(tree, before) == []


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
    assert [e["path"] for e in vanished(tree, committed(repo, "ledger/roll.json"))] == [
        "release"]


def test_audit_reports_not_looking_as_distinct_from_all_clear(tmp_path):
    """The two states a gate must never confuse."""
    complaints, looked = audit(ledger(), tmp_path, "ledger/roll.json")
    assert complaints == [] and looked is False


def test_audit_folds_the_whole_check_into_one_call(tmp_path):
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

    assert audit(tree, repo, "ledger/roll.json") == ([], True)

    # drop a node, re-kind another, and rewrite a third in one go
    tree.root.children = [c for c in tree.root.children if c.id != "release"]
    set_node(tree, "the-eight-are-human", {"kind": "decision"})
    tree.get("key-for-key").payload["rationale"] = "quietly different now"
    complaints, looked = audit(tree, repo, "ledger/roll.json")
    assert looked is True
    assert any("release" in c and "is gone" in c for c in complaints)
    assert any("the-eight-are-human" in c and "stopped being falsifiable" in c
               for c in complaints)
    assert any("key-for-key" in c and "no longer says what the roll recorded" in c
               for c in complaints)

    # ...and a tombstone excuses the removal, but never the re-kinding
    complaints, _ = audit(tree, repo, "ledger/roll.json", excused={"release"})
    assert not any("is gone" in c for c in complaints)
    assert any("stopped being falsifiable" in c for c in complaints)


def test_an_excused_path_spares_its_subtree():
    """Burying a node buries its children: one tombstone naming the root of what
    left accounts for all of it. The ledger repo's first compaction hit this - the
    entry was excused, its two alternatives were not, and the check demanded
    tombstones that would have said nothing the first one did not."""
    before = roll(ledger())
    tree = ledger()
    tree.root.children = [c for c in tree.root.children if c.id != "key-for-key"]

    assert [e["path"] for e in vanished(tree, before)] == [
        "key-for-key", "key-for-key/alt-fallback"]
    assert vanished(tree, before, excused={"key-for-key"}) == []
    # ...and a sibling that merely shares the prefix string is NOT spared
    assert [e["path"] for e in vanished(tree, before, excused={"key-for"})] == [
        "key-for-key", "key-for-key/alt-fallback"]
