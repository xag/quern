"""#69: a rule's verdict on a node is kept while everything the rule read there is unchanged.

`run_rules` judged every rule on every node after every write, though a write touches one
node and the trace says which verdicts it can move. `VerdictCache` keeps each verdict with
what its evaluation reached - the digest of every node it read and the answer of every
backlink query it asked - and gives it back only while all of it is as it was.

The law it must keep: a run with the cache answers exactly what a run without it answers,
whatever was written in between. `test_a_kept_verdict_is_the_verdict_a_fresh_run_gives`
states it over a few hundred random writes; the other tests pin the cases one at a time.
"""

import random

from quern import Quern, Rule, run_rules, set_node
from quern.cache import VerdictCache
from quern.tree import delete_node


RULES = [
    # reads across links: a use case is served while a current expectation points at it
    Rule(name="served", kind="use_case",
         expr="len(backlinked(self, 'serves')) >= 1"),
    # reads the node's own param and a payload field
    Rule(name="bounded", kind="use_case", expr="weight <= 10"),
    Rule(name="said", kind="expectation", expr="contains(payload(self, 'text', ''), 'must')"),
    # reads a link to any depth
    Rule(name="rooted", kind="expectation",
         expr="superseded(self) or len(reach(self, 'serves')) >= 1"),
]


def base() -> Quern:
    t = Quern(rules=list(RULES))
    set_node(t, "uc1", {"kind": "use_case", "params": {"weight": {"value": 3}}})
    set_node(t, "uc2", {"kind": "use_case", "params": {"weight": {"value": 12}}})
    set_node(t, "e1", {"kind": "expectation", "payload": {"text": "it must work"},
                       "links": {"serves": ["uc1"]}})
    return t


def verdicts(results):
    return sorted((r.rule, r.node, r.verdict) for r in results)


def test_an_unrelated_write_keeps_every_verdict_it_cannot_move():
    t, cache = base(), VerdictCache(None)
    run_rules(t, verdicts=cache)
    assert cache.reused == 0
    set_node(t, "uc2", {"kind": "use_case", "params": {"weight": {"value": 4}}})
    run_rules(t, verdicts=cache)
    # uc2's two rules are judged again; uc1's two and e1's two are kept
    assert cache.judged == 2 and cache.reused == 4


def test_a_new_backlink_moves_the_verdict_of_the_node_it_points_at():
    """The node a write turns green is not the node written."""
    t, cache = base(), VerdictCache(None)
    first = run_rules(t, verdicts=cache)
    assert ("served", "uc2", "broken") in verdicts(first)
    set_node(t, "e2", {"kind": "expectation", "payload": {"text": "must"},
                       "links": {"serves": ["uc2"]}})
    second = run_rules(t, verdicts=cache)
    assert ("served", "uc2", "holds") in verdicts(second)
    assert ("served", "uc2", "broken", "holds") in cache.moved


def test_a_param_or_context_change_is_a_change_of_what_was_read():
    t, cache = base(), VerdictCache(None)
    run_rules(t, verdicts=cache)
    set_node(t, "uc1", {"kind": "use_case", "params": {"weight": {"value": 30}}})
    assert ("bounded", "uc1", "broken") in verdicts(run_rules(t, verdicts=cache))
    t.rules = [Rule(name="ctx", kind="use_case", expr="ctx('limit') > 1")]
    run_rules(t, context={"limit": 2}, verdicts=cache)
    assert [r.ok for r in run_rules(t, context={"limit": 0}, verdicts=cache)] == [False, False]


def test_a_rule_that_reaches_a_native_is_judged_every_time():
    from quern.tree import register_native
    calls = []
    register_native("test69/count", lambda tree, *a: calls.append(1) or 1.0)
    t, cache = base(), VerdictCache(None)
    t.rules = [Rule(name="native", kind="use_case", expr="solve('test69/count') == 1")]
    run_rules(t, verdicts=cache)
    run_rules(t, verdicts=cache)
    assert len(calls) == 4 and cache.reused == 0


def test_kept_verdicts_survive_the_process_on_disk(tmp_path):
    t = base()
    run_rules(t, verdicts=VerdictCache(tmp_path))
    again = VerdictCache(tmp_path)
    run_rules(t, verdicts=again)
    assert again.judged == 0 and again.reused == 6


def test_an_edited_rule_is_a_new_rule():
    t, cache = base(), VerdictCache(None)
    run_rules(t, verdicts=cache)
    t.rules = [r if r.name != "bounded" else Rule(name="bounded", kind="use_case",
                                                   expr="weight <= 20") for r in t.rules]
    assert ("bounded", "uc2", "holds") in verdicts(run_rules(t, verdicts=cache))


def test_a_kept_verdict_is_the_verdict_a_fresh_run_gives():
    """The law, over 300 random writes: adds, edits, link moves, supersessions and
    deletes. After each, the cached run and a fresh run agree on every verdict."""
    rng = random.Random(69)
    t, cache = base(), VerdictCache(None)
    for step in range(300):
        names = [p for p, _ in t.walk("")]
        op = rng.choice(["uc", "exp", "edit", "supersede", "delete"])
        if op == "uc":
            set_node(t, f"uc{rng.randint(1, 6)}", {"kind": "use_case",
                     "params": {"weight": {"value": rng.randint(0, 15)}}})
        elif op == "exp":
            targets = rng.sample([n for n in names] or ["uc1"], k=min(2, len(names) or 1))
            set_node(t, f"e{rng.randint(1, 8)}", {
                "kind": "expectation", "payload": {"text": rng.choice(["must", "may"])},
                "links": {"serves": targets}})
        elif op == "edit" and names:
            p = rng.choice(names)
            set_node(t, p, {"payload": {"text": rng.choice(["must", "nope", ""])}})
        elif op == "supersede" and names:
            set_node(t, f"s{rng.randint(1, 4)}", {"kind": "expectation",
                     "links": {"supersedes": [rng.choice(names)]}})
        elif op == "delete" and names:
            delete_node(t, rng.choice(names))
        assert verdicts(run_rules(t, verdicts=cache)) == verdicts(run_rules(t)), step
    assert cache.reused > cache.judged          # and it was worth keeping them


def test_a_write_reports_the_red_it_made_on_another_node(tmp_path):
    """The note in #69: after a write, the verdicts that changed are what the writer wants
    to see, and a new link turns its target red without the target being written."""
    from quern import KindDef, Node
    from quern.app_host import _bridge_tools, _dispatch
    from quern.library import Library

    class WS:
        label = "verdicts-69"

        def __init__(self):
            self._quern = Quern(
                vocabulary=[KindDef(kind="task", description="a task")],
                rules=[Rule(name="unblocked", kind="task",
                            expr="len(backlinked(self, 'blocks')) == 0")],
                root=Node(id="root", children=[Node(id="a", kind="task"),
                                               Node(id="c", kind="task")]))

        quern = property(lambda self: self._quern)
        effective = lambda self: self._quern
        assert_editable = lambda self, path: None
        save = lambda self: None
        blob_dir = property(lambda self: tmp_path)
        library = property(lambda self: Library(tmp_path))
        starter_vocabulary = lambda self: []

    ws = WS()
    mcp = _bridge_tools(lambda: ws)
    _dispatch(mcp, "tree_set", {"path": "c", "node": {"name": "C"}})
    said = str(_dispatch(mcp, "tree_set", {"path": "c", "node": {"links": {"blocks": ["a"]}}}))
    assert "FAIL unblocked @ a" in said
