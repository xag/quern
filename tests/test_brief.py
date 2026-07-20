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


# --- the host surface ------------------------------------------------------------

def _call(ws, args: dict) -> str:
    """Reach tree_brief the way a model does — through the registered MCP tool, not
    by calling brief() again. What is under test is the WIRING: that the tool exists,
    resolves a workspace, reads the EFFECTIVE tree, and passes its flags through."""
    import asyncio

    from mcp.server.fastmcp import FastMCP

    from quern.host import register_tree_tools

    mcp = FastMCP("t")
    register_tree_tools(mcp, lambda: ws)
    res = asyncio.run(mcp.call_tool("tree_brief", args))
    out = res[1] if isinstance(res, tuple) else res
    # A str-returning FastMCP tool comes back as {'result': <text>}. Assert the shape
    # rather than str()-ing whatever arrives: a repr of the wrong object still contains
    # the text, so a fallback here would quietly turn a broken return into a green test.
    assert isinstance(out, dict) and "result" in out, f"unexpected tool return: {out!r}"
    return out["result"]


class _Ws:
    """The Workspace protocol, minimally. `effective()` returns a DIFFERENT tree from
    `quern` on purpose: the brief must read the composed view — overlays and pinned
    packages folded in — exactly as tree_get and tree_check do, and a tool that read
    the bare stored tree would pass every other assertion here."""

    label = "test-ws"

    def __init__(self, tree: Quern):
        self._composed = tree
        self._stored = Quern()  # deliberately empty: reading this would show nothing

    @property
    def quern(self) -> Quern:
        return self._stored

    def effective(self) -> Quern:
        return self._composed

    def assert_editable(self, path):
        pass

    def save(self):
        pass

    @property
    def blob_dir(self):
        from pathlib import Path
        return Path(".")

    @property
    def library(self):
        return None

    def starter_vocabulary(self):
        return []


def test_tree_brief_serves_the_working_set_over_mcp():
    out = _call(_Ws(ledger()), {})
    assert "[debt]  cache-size-is-a-guess" in out
    assert "!entries" in out                       # structure survives the round-trip
    assert "omitted as no longer current: 1 decision" in out
    assert "\n[decision]  cache-the-parse" not in out


def test_tree_brief_reads_the_effective_tree_not_the_stored_one():
    """The regression that would be invisible otherwise: a brief off ws.quern renders
    an empty tree, and 'no entries' looks like a clean ledger rather than a bug."""
    out = _call(_Ws(ledger()), {})
    assert "0 entr" not in out
    assert "cache-size-is-a-guess" in out


def test_tree_brief_passes_its_flags_through():
    shown = _call(_Ws(ledger()), {"all": True})
    assert "cache-the-parse" in shown and "superseded by" in shown
    assert "omitted as no longer current" not in shown

    fat = _call(_Ws(ledger()), {"fat": True})
    weights = [int(l.rsplit("~", 1)[1].rstrip("w"))
               for l in fat.splitlines() if l.startswith("[")]
    assert weights == sorted(weights, reverse=True)
