"""`where(x, xs, cond)`: a rule that judges only some of a node's links.

`and` and `or` evaluate both sides (the-grammar-is-an-object-not-a-private-parser), so a guard
written with them still reads, on the links it means to pass over, a param those links do not
have: the rule comes out absent on a node it should not judge. Quantifying over the links the
guard keeps reads nothing of the others.
"""

from quern import Quantity, Quern, Rule, compile_expr, rule_env, run_rules, set_node


def joints() -> Quern:
    """A joint held by a connector that states its limit, and one held by screws, which state none."""
    t = Quern(rules=[Rule(
        name="a-connectors-joint-is-wide-enough", kind="joint",
        expr="every(c, where(c, linked(self, 'uses'), kind(c) == 'connector'), "
             "param(self, 'width') >= param(c, 'min_width'))")])
    set_node(t, "dowel", {"kind": "connector",
                          "params": {"min_width": Quantity(value=75, unit="mm", provenance="published")}})
    set_node(t, "screws", {"kind": "material"})
    for name, uses, width in (("narrow", "dowel", 60), ("wide", "dowel", 90), ("screwed", "screws", 20)):
        set_node(t, name, {"kind": "joint", "links": {"uses": [uses]},
                           "params": {"width": Quantity(value=width, unit="mm", provenance="design-target")}})
    return t


def test_where_keeps_the_elements_its_condition_holds_for():
    t = joints()
    keep = compile_expr("where(c, linked(self, 'uses'), kind(c) == 'connector')")
    assert keep.evaluate(rule_env(t), {"self": "narrow"}) == ["dowel"]
    assert keep.evaluate(rule_env(t), {"self": "screwed"}) == []


def test_a_rule_over_the_kept_links_judges_only_those():
    verdicts = {r.node: r.verdict for r in run_rules(joints())}
    assert verdicts == {"narrow": "broken", "wide": "holds", "screwed": "holds"}


def test_the_same_guard_written_with_or_reads_what_screws_lack():
    """Why `where` exists: the guard in `or` is evaluated with the rest, and the rest is absent."""
    t = joints()
    t.rules = [Rule(name="guarded-with-or", kind="joint",
                    expr="every(c, linked(self, 'uses'), kind(c) != 'connector') or "
                         "param(self, 'min_width') <= param(self, 'width')")]
    assert {r.node: r.verdict for r in run_rules(t)}["screwed"] == "absent"


def test_where_names_its_bound_variable_and_no_function():
    reads = compile_expr("where(c, linked(self, 'uses'), kind(c) == 'connector')").reads
    assert "c" not in reads.names and "where" not in reads.functions
