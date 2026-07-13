"""The grounding contracts: is any of it safe to act on?

These test the implementations — host code that stays in bom while their meaning
(grounding@) is authored in xag/grounding and travels the registry as data.
"""

from bom.grounding import depends_untrusted, untrusted, untrusted_via
from bom.tree import Bom, Node, set_node


def tree(*nodes: Node) -> Bom:
    b = Bom()
    b.root.children = list(nodes)
    return b


MEASURED = {"value": 2500, "unit": "mm", "provenance": "measured", "tolerance": 2}
LOOSE = {"value": 2500, "unit": "mm", "provenance": "measured", "tolerance": 50}
GUESSED = {"value": 2500, "unit": "mm", "provenance": "inferred"}


def test_untrusted_counts_guesses_and_loose_measurements():
    t = tree(Node(id="wall", kind="boundary",
                  params={"height": MEASURED, "length": GUESSED}))
    assert untrusted(t, "wall") == 1                 # the guess
    assert untrusted(t, "wall", tolerance=1) == 2    # ...and 2mm is not tight enough for 1mm


def test_the_gate_a_design_passes_before_it_is_cut():
    """untrusted_via is the whole measured-before-cut idea: the design says what it
    is fitted against; this says whether those are observations."""
    t = tree(Node(id="wall", kind="boundary", params={"height": LOOSE}))
    set_node(t, "shelf", {"kind": "piece", "links": {"fits_against": ["wall"]}})
    assert untrusted_via(t, "shelf", "fits_against") == 0          # it IS measured...
    assert untrusted_via(t, "shelf", "fits_against", 2) == 1       # ...but to 50mm, not 2mm


def test_a_derived_value_resting_on_a_guess_is_a_guess():
    t = tree(Node(id="wall", kind="boundary", params={"height": GUESSED}))
    set_node(t, "shelf", {"kind": "piece", "params": {"cut_height": {
        "value": 2400, "unit": "mm", "provenance": "derived", "grounded": False,
        "derived_from": ["wall/height"]}}})
    assert untrusted(t, "wall") == 1
    assert depends_untrusted(t, "shelf") == 1  # followed the lineage to the guess
