"""The rule grammar as a first-class object, and the trace of one evaluation.

#44: four adopters routed around a private parser — one imported `_tokenize` and
froze it by pin, two recovered what an expression reads by regex over its source,
two fabricated a staged tree with a one-rule rule list to evaluate an expression
sitting in a payload. #52: a red says a rule did not hold and says nothing about
what it saw, so every reporter re-evaluated the sub-expressions in its own dialect
to recover the numbers. Both are the same missing thing: the expression, and what
it read, as data from the evaluator that made the answer.
"""

import pytest

from quern import (
    Quern,
    Rule,
    compile_expr,
    design_target,
    evaluate_expr,
    rule_env,
    run_rules,
    set_node,
)
from quern.expr import Call, Lit, Var


def tree() -> Quern:
    """Two debts, one of them over budget, and a rule that says so."""
    t = Quern(rules=[
        Rule(name="within-budget", kind="debt",
             expr="param(self, 'spent') <= param(self, 'budget')"),
        Rule(name="named", kind="debt", expr="len(self) > 0"),
    ])
    set_node(t, "meter", {"kind": "debt",
                          "params": {"spent": design_target(30, unit="d"),
                                     "budget": design_target(10, unit="d")}})
    set_node(t, "concurrency", {"kind": "debt",
                                "params": {"spent": design_target(2, unit="d"),
                                           "budget": design_target(5, unit="d")}})
    return t


# --- the expression as an object (#44) ----------------------------------------

def test_an_expression_compiles_once_and_is_the_same_object():
    """The cache is not a nicety: a rule bound to every node of a kind used to be
    reparsed once per node, and a consumer holding an Expr must be able to keep it."""
    assert compile_expr("1 + 1 == 2") is compile_expr("1 + 1 == 2")
    assert compile_expr("1 + 1 == 2") is not compile_expr("1 + 1 == 3")


def test_the_parsed_form_is_readable_without_running_anything():
    expr = compile_expr("param(self, 'spent') <= 10")
    left = expr.term.left
    assert isinstance(left, Call) and left.fn == "param"
    assert left.args == (Var("self"), Lit("spent"))
    assert expr.term.right == Lit(10)


def test_reads_names_the_functions_variables_and_ctx_keys():
    """What vigil recovered by regex, and what a daemon must stage before a tick."""
    expr = compile_expr(
        "ctx('series') > 0 and solve('invest/drawdown', self) < ctx('cap')")
    assert expr.reads.functions == ("ctx", "solve")
    assert expr.reads.names == ("self",)
    assert expr.reads.ctx_keys == ("series", "cap")
    assert expr.reads.strings == ("series", "invest/drawdown", "cap")


def test_a_numeric_bound_is_data_not_something_to_regex_back_out():
    """transponder read a limit out of the expr source with a regular expression
    because the limit was not readable as data. It is now."""
    assert compile_expr("said_words(self) <= 300").reads.numbers == (300,)


def test_a_ctx_key_that_is_computed_states_nothing():
    """There is no literal to report, so reporting one would be an invention."""
    assert compile_expr("ctx(name) > 0").reads.ctx_keys == ()
    assert compile_expr("ctx(name) > 0").reads.names == ("name",)


def test_an_expression_evaluates_against_a_tree_without_staging_a_rule():
    """The fabrication #44 names: vigil and invest each built a throwaway tree with a
    one-rule rule list to get at this environment. Two public calls now."""
    t = tree()
    expr = compile_expr("param(self, 'spent') <= param(self, 'budget')")
    env = rule_env(t)
    assert expr.evaluate(env, {"self": "concurrency"}) is True
    assert expr.evaluate(env, {"self": "meter"}) is False


def test_booleans_are_literals_and_integers_stay_integers():
    """Both patched back in by every adopter that needed them."""
    assert compile_expr("true").evaluate({}) is True
    assert compile_expr("not false").evaluate({}) is True
    assert compile_expr("3").evaluate({}) == 3
    assert isinstance(compile_expr("3").evaluate({}), int)
    assert isinstance(compile_expr("3.5").evaluate({}), float)


def test_a_malformed_expression_refuses_at_compile_time():
    with pytest.raises(ValueError):
        compile_expr("1 +")
    with pytest.raises(ValueError):
        compile_expr("count('a'")


def test_the_grammar_still_reaches_nothing_it_was_not_handed():
    with pytest.raises(ValueError, match="unknown function"):
        evaluate_expr("open('x')", {})
    with pytest.raises(ValueError, match="unknown name"):
        evaluate_expr("self", {})


# --- what the evaluation read (#52) -------------------------------------------

def test_trace_reports_every_call_with_its_arguments_and_its_value():
    t = tree()
    expr = compile_expr("param(self, 'spent') <= param(self, 'budget')")
    value, reads = expr.trace(rule_env(t), {"self": "meter"})
    assert value is False
    assert [(r.call, r.args, r.value) for r in reads] == [
        ("param", ["meter", "spent"], 30.0),
        ("param", ["meter", "budget"], 10.0),
    ]


def test_a_rule_result_carries_what_it_read_when_the_run_is_traced():
    """A red is only actionable with the values behind it, and they come from the
    evaluator that produced the verdict — never from a second pass over the same
    grammar by whoever is reporting it."""
    red = next(r for r in run_rules(tree(), rules="within-budget", trace=True)
               if not r.ok)
    assert red.node == "meter"
    assert [(r.call, r.value) for r in red.reads] == [
        ("param", 30.0), ("param", 10.0)]


def test_an_untraced_run_carries_no_reads():
    """Off by default: the trace of a whole tree's check is much larger than its
    verdicts, and the calls that matter are the ones behind a line being read."""
    assert all(r.reads == [] for r in run_rules(tree()))


def test_a_rule_that_raises_still_reports_what_it_read_first():
    """What was read before it blew up is most of the diagnosis."""
    t = tree()
    t.rules = [Rule(name="boom", kind="debt",
                    expr="param(self, 'spent') + param(self, 'missing')")]
    red = next(r for r in run_rules(t, rules="boom", trace=True) if r.node == "meter")
    assert not red.ok and "missing" in red.detail
    assert [(r.call, r.value) for r in red.reads] == [("param", 30.0)]


# --- one rule, one node (#53) -------------------------------------------------

def test_a_rule_filter_runs_that_rule_and_no_other():
    results = run_rules(tree(), rules="within-budget")
    assert {r.rule for r in results} == {"within-budget"}
    assert {r.node for r in results} == {"meter", "concurrency"}


def test_a_filter_takes_several_names():
    results = run_rules(tree(), rules=["within-budget", "named"])
    assert {r.rule for r in results} == {"within-budget", "named"}


def test_the_filter_composes_with_the_path_scope():
    """'Is this still wrong?' is one rule and one node, asked by whoever has just
    done something about it — and it should cost that rule's reads."""
    results = run_rules(tree(), "meter", rules="within-budget")
    assert [(r.rule, r.node, r.ok) for r in results] == \
           [("within-budget", "meter", False)]


def test_a_rule_name_no_rule_carries_is_an_error_not_an_empty_green():
    """An empty pass would answer the question with a typo."""
    with pytest.raises(ValueError, match="within-buget"):
        run_rules(tree(), rules="within-buget")
