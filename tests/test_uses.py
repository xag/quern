"""The reuse verb: definitions, usages, expansion, and the data-named folds."""

import pytest

from bom import (
    Bom,
    Rule,
    definition,
    explode,
    resolve_params,
    rollup,
    run_rules,
    set_node,
    tally,
    users,
)


def sample() -> Bom:
    """A two-branch bill: shared definitions under parts/, usages under ebom/."""
    tree = Bom()
    set_node(tree, "parts/bolt-m6", {
        "kind": "fastener",
        "params": {"mass": {"value": 10, "unit": "g"},
                   "cost": {"value": 0.2, "unit": "EUR"}}})
    set_node(tree, "parts/bracket", {
        "kind": "part",
        "params": {"mass": {"value": 50, "unit": "g"},
                   "cost": {"value": 1.5, "unit": "EUR"}}})
    set_node(tree, "parts/gearbox", {"kind": "assembly"})
    set_node(tree, "parts/gearbox/housing", {
        "kind": "part",
        "params": {"mass": {"value": 500, "unit": "g"},
                   "cost": {"value": 8, "unit": "EUR"}}})
    set_node(tree, "parts/gearbox/bolts", {
        "links": {"uses": ["parts/bolt-m6"]},
        "params": {"qty": {"value": 4, "unit": "each"}}})
    set_node(tree, "ebom/drive", {"kind": "assembly"})
    set_node(tree, "ebom/drive/gb", {
        "links": {"uses": ["parts/gearbox"]},
        "params": {"qty": {"value": 2, "unit": "each"}}})
    set_node(tree, "ebom/drive/mount", {
        "links": {"uses": ["parts/bracket"]},
        "params": {"qty": {"value": 1, "unit": "each"},
                   "cost": {"value": 1.0, "unit": "EUR"}}})  # usage overrides def
    return tree


def test_definition_and_users():
    tree = sample()
    assert definition(tree, "ebom/drive/gb") == "parts/gearbox"
    assert definition(tree, "parts/gearbox") is None  # not a usage
    assert users(tree, "parts/bolt-m6") == ["parts/gearbox/bolts"]
    assert users(tree, "parts/gearbox") == ["ebom/drive/gb"]


def test_alternates_resolve_to_first_existing_target():
    tree = sample()
    set_node(tree, "ebom/drive/alt", {
        "links": {"uses": ["parts/retired", "parts/bracket"]}})
    assert definition(tree, "ebom/drive/alt") == "parts/bracket"


def test_params_read_through_usage_overrides_definition():
    tree = sample()
    eff = resolve_params(tree, "ebom/drive/mount")
    assert eff["mass"].value == 50    # inherited from parts/bracket
    assert eff["cost"].value == 1.0   # the usage's own value wins


def test_explode_multiplies_the_domain_named_param_down_the_chain():
    tree = sample()
    occ = {o.path: o for o in explode(tree, "ebom/drive", mult="qty")}
    assert occ["ebom/drive"].factor == 1.0
    assert occ["ebom/drive/gb"].factor == 2.0
    assert occ["ebom/drive/gb/housing"].node == "parts/gearbox/housing"
    assert occ["ebom/drive/gb/housing"].factor == 2.0
    assert occ["ebom/drive/gb/bolts"].factor == 8.0  # 2 gearboxes x 4 bolts
    assert occ["ebom/drive/mount"].factor == 1.0


def test_rollup_and_tally_take_the_nouns_as_data():
    tree = sample()
    assert rollup(tree, "ebom/drive", "qty", "mass") == pytest.approx(
        2 * 500 + 8 * 10 + 1 * 50)                       # housing + bolts + mount
    assert rollup(tree, "ebom/drive", "qty", "cost") == pytest.approx(
        2 * 8 + 8 * 0.2 + 1 * 1.0)  # housing + bolts + mount's own override
    assert tally(tree, "ebom/drive", "fastener", "qty") == 8.0


def test_cycle_in_expansion_raises():
    tree = Bom()
    set_node(tree, "parts/a", {"kind": "assembly"})
    set_node(tree, "parts/a/x", {"links": {"uses": ["parts/a"]}})
    with pytest.raises(ValueError, match="cycle"):
        explode(tree, "parts/a")


def test_dangling_reference_is_refused_unless_told_otherwise():
    tree = Bom()
    set_node(tree, "ebom/x", {"links": {"uses": ["parts/ghost"]}})
    with pytest.raises(ValueError, match="no target exists"):
        explode(tree, "ebom")
    occ = explode(tree, "ebom", strict=False)
    assert [o.node for o in occ] == ["ebom", "ebom/x"]


def test_rule_builtins_reach_the_reuse_verb():
    tree = sample()
    tree.rules.append(Rule(
        name="mass-budget", path="ebom/drive",
        expr="rollup('ebom/drive', 'qty', 'mass') <= 1200"))
    tree.rules.append(Rule(
        name="gb-is-a-gearbox", path="ebom/drive/gb",
        expr="uses(self) == 'parts/gearbox'"))
    tree.rules.append(Rule(
        name="bolt-is-used", path="parts/bolt-m6",
        expr="len(where_used(self)) == 1"))
    tree.rules.append(Rule(
        name="mount-mass-via-param", path="ebom/drive/mount",
        expr="param(self, 'mass') == 50"))  # param() reads through the definition
    results = {r.rule: r for r in run_rules(tree)}
    for name in ("mass-budget", "gb-is-a-gearbox", "bolt-is-used",
                 "mount-mass-via-param"):
        assert results[name].ok, f"{name}: {results[name].detail}"
