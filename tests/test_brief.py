"""The brief: the working set at one line per entry, the archaeology counted away.

A ledger pays for itself only if reading it is cheaper than re-deriving it. These
pin the contract that makes that true: current entries render one line each with
their structure (links, ungrounded params, child counts), superseded ones cost a
trailer count instead of their prose, and the curation view sorts by the one
number that predicts future cost — words.
"""

from quern import Quern, Quantity, said_words, set_node
from quern.brief import brief


def ledger() -> Quern:
    tree = Quern()
    set_node(tree, "cache-the-parse", {"kind": "decision",
                                       "name": "Parse each bundle once and cache it"})
    set_node(tree, "cache-the-parse/alt-per-request",
             {"kind": "alternative", "name": "Parse on every request",
              "payload": {"why": "simpler, and too slow"}})
    set_node(tree, "parse-every-time",
             {"kind": "decision", "name": "Parse on every request after all",
              "links": {"supersedes": ["cache-the-parse"]}})
    set_node(tree, "cache-size-is-a-guess",
             {"kind": "debt", "name": "The cache is sized by a number nobody measured",
              "links": {"rests_on": ["parse-every-time"]},
              "params": {"entries": Quantity(value=512, unit="entry",
                                             provenance="unreviewed", grounded=False)}})
    return tree


def test_said_words_counts_the_whole_subtree():
    tree = ledger()
    own = said_words(tree, "cache-the-parse/alt-per-request")  # name + payload.why
    assert own == 4 + 4
    assert said_words(tree, "cache-the-parse") == own + 7  # + the parent's name


def test_a_superseded_entry_costs_a_count_not_its_prose():
    out = brief(ledger())
    assert "parse-every-time" in out
    assert "cache-size-is-a-guess" in out
    assert "\n[decision]  cache-the-parse" not in out
    assert "omitted as no longer current: 1 decision" in out


def test_all_shows_the_superseded_with_its_supersessor_named():
    out = brief(ledger(), all=True)
    assert "cache-the-parse" in out and "(superseded by parse-every-time)" in out


def test_structure_travels_on_the_line():
    out = brief(ledger())
    line = next(l for l in out.splitlines() if l.startswith("[debt]"))
    assert "rests_on->parse-every-time" in line   # the link, navigable by name
    assert "!entries" in line                     # the ungrounded param, flagged
    kids = next(l for l in out.splitlines() if "parse-every-time" in l and "[decision]" in l)
    assert kids  # present, one line


def test_fat_sorts_by_words_heaviest_first():
    out = brief(ledger(), fat=True)
    lines = [l for l in out.splitlines() if l.startswith("[")]
    weights = [int(l.rsplit("~", 1)[1].rstrip("w")) for l in lines]
    assert weights == sorted(weights, reverse=True)


def test_the_brief_is_rule_aware_or_says_it_is_not():
    """No rules staged here, so nothing is red and nothing claims to be - and the
    module must never turn 'could not evaluate' into silence (that contract is
    exercised end-to-end by the estate's checks; here we pin the green path)."""
    out = brief(ledger())
    assert "RED(" not in out
    assert "rules not evaluated" not in out
