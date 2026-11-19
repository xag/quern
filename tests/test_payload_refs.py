"""`refs` on a kind: the payload fields that name another node (#72).

Trees refer to nodes from the payload as well as through links: a citation's `source` is
the id of a node under `sources/`. A kind declares which fields do, so the navigator shows
such a value as the node it names and `quern owed` implies the rule that it names one,
and nothing that merely looks like an id is read as one.
"""

from quern import KindDef, Quern, dangling_ref, payload_refs, run_rules, set_node
from quern.host import slice_at
from quern.navigate import ReadOnlyWorkspace
from quern.owed import floor, matrix

CLAIM = KindDef(kind="claim", description="a claim citing sources",
                refs={"citations.source": "sources", "owner": ""})


def cited() -> Quern:
    tree = Quern(vocabulary=[CLAIM, KindDef(kind="source", description="a source")])
    set_node(tree, "sources/smith-2020", {"kind": "source", "name": "Smith, 2020"})
    set_node(tree, "roles/editor", {"name": "the editor"})
    set_node(tree, "c1", {"kind": "claim", "payload": {
        "citations": [{"source": "smith-2020"}, {"source": "gone-1999"}, {"page": 3}],
        "owner": "roles/editor"}})
    # the same field on a kind that declares nothing names nothing
    set_node(tree, "note", {"kind": "note", "payload": {"owner": "roles/editor"}})
    return tree


def test_a_declared_field_names_nodes_under_its_branch_and_nothing_else_does():
    tree = cited()
    assert payload_refs(tree, "c1") == {
        "citations.source": ["sources/smith-2020", "sources/gone-1999"],
        "owner": ["roles/editor"]}
    assert payload_refs(tree, "note") == {}


def test_a_name_that_resolves_to_nothing_is_dangling():
    tree = cited()
    assert dangling_ref(tree, "c1", "citations.source", "sources") == ["sources/gone-1999"]
    assert dangling_ref(tree, "c1", "owner", "") == []


def test_owed_implies_the_rule_and_the_rule_convicts_its_refuter_and_passes_a_sound_node():
    cells = {(c.kind, c.subject): c for c in matrix([CLAIM], [])}
    assert cells[("claim", "ref:citations.source")].owed
    gen, refuters = floor([CLAIM], [])
    assert {r.expr for r in gen} == {
        "dangling_ref(self, 'citations.source', 'sources') == 0",
        "dangling_ref(self, 'owner', '') == 0"}
    stage = Quern(vocabulary=[CLAIM], rules=gen)
    stage.root.children = [n for _, n in refuters]
    assert {r.rule for r in run_rules(stage) if not r.ok} == {r.name for r in gen}

    tree = cited()
    tree.rules = gen
    red = {(r.rule, r.node) for r in run_rules(tree) if not r.ok}
    assert red == {("a-claim-citations-source-names-a-node", "c1")}


def test_the_slice_carries_each_named_node_and_none_for_a_missing_one():
    ws = ReadOnlyWorkspace(cited(), "t")
    data = slice_at(ws, "", 2)
    assert data["refs"] == {
        "sources/smith-2020": {"name": "Smith, 2020", "kind": "source"},
        "sources/gone-1999": None,
        "roles/editor": {"name": "the editor", "kind": None}}
    # a slice that stops above the payload carries none of what it names
    assert "refs" not in slice_at(ws, "", 0)
