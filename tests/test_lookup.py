"""The two ways into one entry, neither running a rule: get prints it in full, find lists
the entries that carry every word asked for."""

from quern.lookup import find, get

from tests.test_verdicts import ledger


def test_get_prints_an_entry_by_its_id_with_its_children():
    out = get(ledger(), "cache-the-parse")
    assert out.startswith("[decision]  cache-the-parse")
    assert "cache-the-parse/alt-per-request" in out and "why: simpler, and too slow" in out


def test_get_by_a_childs_id_and_an_unknown_one():
    assert get(ledger(), "alt-per-request").startswith("[alternative]  cache-the-parse/alt-per-request")
    assert get(ledger(), "nothing-here") == "no entry is 'nothing-here'"


def test_find_lists_the_entries_that_carry_every_word():
    tree = ledger()
    out = find(tree, ["too", "SLOW"])
    assert out.splitlines() == [l for l in out.splitlines() if l.startswith("[decision]  cache-the-parse")]
    assert find(tree, ["guess"]).startswith("[debt]  size-is-a-guess")
    assert find(tree, ["absent"]) == "no entry mentions absent"
