"""bom's own ledger — the content, not the vocabulary (that is test_ledger.py).

The suite stays GREEN by asserting what is true: the compute-boundary gate is red, and
these are the debts that hold it shut. `ledger.check` is what carries the red signal, and
it exits 1 until someone does the work. A test that went red on a recorded debt would only
get skipped, and a skipped guard guards nothing.
"""

from __future__ import annotations

from bom import get_node, run_rules

from ledger.tree import build


def _results():
    bom = build()
    return bom, {(r.rule, r.node): r for r in run_rules(bom)}


def test_the_compute_boundary_gate_is_red_and_names_why():
    bom, res = _results()
    gate = res[("nothing-unsound-passes-a-gate", "the-host-surface")]
    assert not gate.ok, "the host still meters nothing and still blocks — this cannot pass"

    # It is red because of these two, and discharging them is what opens it.
    for debt in ("a-native-contract-is-unmetered", "a-host-tool-runs-on-the-event-loop"):
        node = get_node(bom, debt)
        assert node.kind == "debt"
        assert all(not q.grounded for q in node.params.values()), \
            "a debt whose params are grounded is not a debt; the gate would go green on a lie"


def test_every_other_rule_is_green():
    """The ledger's own structural invariants hold: the decision names what it rejected,
    each debt says how it is discharged, and the hypothesis can be killed."""
    _, res = _results()
    red = [k for k, r in res.items() if not r.ok]
    assert red == [("nothing-unsound-passes-a-gate", "the-host-surface")], red


def test_the_exit_is_a_hypothesis_and_it_can_die():
    """The claim everything rests on — that expensive contracts are proposers, so their
    cost can leave the host entirely — is held provisionally, and names what would kill
    it. If an expensive JUDGE ever turns up, bom needs real compute and this is wrong."""
    node = get_node(build(), "heavy-compute-is-a-proposer-never-a-judge")
    assert node.kind == "hypothesis"
    kills = [c for c in node.children if c.kind == "falsification"]
    assert len(kills) == 1
    assert "authoritative" in kills[0].name
