"""#64, #65, #66: three things a rule could not say.

- `reach(self, rel)`: a relation that nests (a member of a group part of a larger group)
  checked to any depth, where `linked` reads one hop.
- `let(name, value, body)`: a condition named once and used several times, where a rule
  had to paste it in full for each pair it covers.
- `some(x, i, xs, cond)` / `every(x, i, xs, cond)`: an element's position in a payload
  list, where the list's order was the only record of which try came last.

Each case is driven through `run_rules` or `compile_expr` on the tree its issue describes,
because a verb the grammar cannot reach answers none of them.
"""

import pytest

from quern import Quern, Rule, compile_expr, reach, reach_current, rule_env, run_rules, set_node


# --- #64: reach ---------------------------------------------------------------

def stakeholders() -> Quern:
    """A client inside a team inside a department; the department owns a use case."""
    t = Quern()
    set_node(t, "dept", {"kind": "stakeholder"})
    set_node(t, "team", {"kind": "stakeholder", "links": {"part_of": ["dept"]}})
    set_node(t, "client", {"kind": "stakeholder", "links": {"part_of": ["team"]}})
    set_node(t, "checkout", {"kind": "use_case", "links": {"done_by": ["dept"]}})
    set_node(t, "fast-checkout", {"kind": "expectation",
                                  "links": {"held_by": ["client"], "for": ["checkout"]}})
    return t


def test_reach_follows_a_link_to_every_depth_own_targets_first():
    t = stakeholders()
    assert reach(t, "client", "part_of") == ["team", "dept"]
    assert reach(t, "dept", "part_of") == []


def test_reach_cuts_a_cycle_and_leaves_the_node_itself_out():
    t = stakeholders()
    set_node(t, "dept", {"kind": "stakeholder", "links": {"part_of": ["client"]}})
    assert reach(t, "client", "part_of") == ["team", "dept"]


def test_reach_current_does_not_cross_a_superseded_node():
    """A hop is a living link, as in `linked_current`: past a superseded group the
    relation no longer holds, so nothing beyond it is reached either."""
    t = stakeholders()
    set_node(t, "team-2", {"kind": "stakeholder", "links": {"supersedes": ["team"]}})
    assert reach_current(t, "client", "part_of") == []
    assert reach(t, "client", "part_of") == ["team", "dept"]


def test_the_holder_two_groups_down_is_green_where_one_hop_was_red():
    """The issue's rule: whoever holds an expectation is, or is part of, whoever does
    the use case it is for."""
    one_hop = ("every(u, linked(self, 'for'), every(o, linked(u, 'done_by'), "
               "some(h, linked(self, 'held_by'), h == o or contains(linked(h, 'part_of'), o))))")
    any_depth = one_hop.replace("linked(h, 'part_of')", "reach(h, 'part_of')")
    t = stakeholders()
    t.rules = [Rule(name="held-within", kind="expectation", expr=one_hop)]
    assert [r.ok for r in run_rules(t)] == [False]
    t.rules = [Rule(name="held-within", kind="expectation", expr=any_depth)]
    assert [r.ok for r in run_rules(t)] == [True]


# --- #65: let -----------------------------------------------------------------

def test_let_names_a_value_once_and_the_body_reads_it():
    t = stakeholders()
    expr = compile_expr("let(up, reach(self, 'part_of'), len(up) == 2 and contains(up, 'dept'))")
    value, reads = expr.trace(rule_env(t), {"self": "client"})
    assert value is True
    # the named value is computed once: one reach call, and one `let` read naming it
    assert [r.call for r in reads].count("reach") == 1
    assert [r.args for r in reads if r.call == "let"] == [["up", ["team", "dept"]]]


def test_a_let_name_is_bound_in_its_body_only_and_is_no_function():
    reads = compile_expr("let(n, len(xs), n > 0) and n == 1").reads
    assert "let" not in reads.functions
    assert reads.names == ("n", "xs")          # the second `n` is outside the body: free


def test_let_takes_a_name_then_a_value_then_a_body():
    with pytest.raises(ValueError, match="let"):
        compile_expr("let('n', 1, n)").evaluate({}, {})
    with pytest.raises(ValueError, match="let"):
        compile_expr("let(n, 1)").evaluate({}, {})


# --- #66: a position in a payload list ----------------------------------------

def question() -> Quern:
    """Two tries reported on the same day: failed on 1.2, answered on 1.3. Only the
    order of the list says which came last."""
    t = Quern()
    set_node(t, "q", {"kind": "question", "payload": {"tries": [
        {"release": "1.2", "outcome": "failed", "date": "2026-11-01"},
        {"release": "1.3", "outcome": "answered", "date": "2026-11-01"},
    ]}})
    return t


LATEST_ANSWERED = ("some(t, i, payload(self, 'tries'), field(t, 'outcome') == 'answered' "
                   "and every(u, j, payload(self, 'tries'), j <= i or "
                   "field(u, 'date') < field(t, 'date')))")


def test_the_position_tells_the_latest_try_where_the_date_ties():
    t = question()
    by_date = ("some(t, payload(self, 'tries'), field(t, 'outcome') == 'answered' and "
               "every(u, payload(self, 'tries'), field(u, 'date') < field(t, 'date') "
               "or u == t))")
    t.rules = [Rule(name="by-date", kind="question", expr=by_date)]
    assert [r.ok for r in run_rules(t)] == [False]       # the tie: the date cannot tell
    t.rules = [Rule(name="by-position", kind="question", expr=LATEST_ANSWERED)]
    assert [r.ok for r in run_rules(t)] == [True]


def test_the_latest_try_failing_is_red():
    t = question()
    tries = list(reversed(t.get("q").payload["tries"]))
    set_node(t, "q", {"kind": "question", "payload": {"tries": tries}})
    t.rules = [Rule(name="by-position", kind="question", expr=LATEST_ANSWERED)]
    assert [r.ok for r in run_rules(t)] == [False]


def test_the_position_is_bound_and_counts_from_zero():
    expr = compile_expr("every(x, i, xs, x == i * 10)")
    assert expr.evaluate({}, {"xs": [0, 10, 20]}) is True
    assert expr.evaluate({}, {"xs": [0, 20]}) is False
    assert expr.reads.names == ("xs",)


def test_the_position_name_must_be_a_name():
    with pytest.raises(ValueError, match="name"):
        compile_expr("some(x, 1, xs, true)").evaluate({}, {"xs": [1]})
