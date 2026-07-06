"""SqliteStore: the same verbs as Bom, answered by indexes — parity, then scale."""

import pytest

from bom import (
    Bom,
    KindDef,
    Rule,
    SqliteStore,
    delete_node,
    find_nodes,
    get_node,
    is_superseded,
    rollup,
    run_rules,
    set_node,
    superseders,
)


def build(tree) -> None:
    """The same edits against any TreeStore — Bom and SqliteStore alike."""
    set_node(tree, "parts/bolt", {
        "kind": "fastener",
        "params": {"mass": {"value": 10, "unit": "g"}}})
    set_node(tree, "rooms/kitchen", {
        "kind": "space", "name": "Kitchen", "meta": {"floor": "ground"}})
    set_node(tree, "rooms/kitchen/sink", {
        "kind": "fixture",
        "params": {"width": {"value": 600, "unit": "mm"}},
        "links": {"drains": ["rooms/kitchen"]}})
    set_node(tree, "rooms/kitchen/sink-v2", {
        "kind": "fixture",
        "links": {"supersedes": ["rooms/kitchen/sink"]}})
    set_node(tree, "ebom/line1", {
        "links": {"uses": ["parts/bolt"]},
        "params": {"qty": {"value": 3, "unit": "each"}}})


@pytest.fixture()
def stores(tmp_path):
    bom = Bom()
    build(bom)
    store = SqliteStore(tmp_path / "tree.db")
    build(store)
    yield bom, store
    store.close()


def test_get_and_children_parity(stores):
    bom, store = stores
    for path in ("", "rooms", "rooms/kitchen", "rooms/kitchen/sink", "missing"):
        b, s = get_node(bom, path), get_node(store, path)
        if b is None:
            assert s is None
            continue
        assert s is not None
        assert (s.kind, s.name, s.meta) == (b.kind, b.name, b.meta)
        assert {k: q.value for k, q in s.params.items()} == \
               {k: q.value for k, q in b.params.items()}
        assert [c.id for c in s.children] == [c.id for c in b.children]
    assert store.children("rooms/kitchen") == bom.children("rooms/kitchen")


def test_walk_preserves_document_order(stores):
    bom, store = stores
    assert [p for p, _ in store.walk("")] == [p for p, _ in bom.walk("")]
    assert [p for p, _ in store.walk("rooms/kitchen")] == \
           [p for p, _ in bom.walk("rooms/kitchen")]


def test_find_parity(stores):
    bom, store = stores
    for kwargs in (
        {"kind": "fixture"},
        {"query": "kitchen"},
        {"has_param": "qty"},
        {"links_to": "rooms/kitchen/sink"},
        {"under": "rooms"},
        {"kind": "fixture", "current_only": True},
        {"query": "ground"},  # meta values are searchable
    ):
        assert [p for p, _ in find_nodes(store, **kwargs)] == \
               [p for p, _ in find_nodes(bom, **kwargs)], kwargs


def test_supersession_reads_from_the_link_index(stores):
    _, store = stores
    assert superseders(store, "rooms/kitchen/sink") == ["rooms/kitchen/sink-v2"]
    assert is_superseded(store, "rooms/kitchen/sink")
    assert not is_superseded(store, "rooms/kitchen/sink-v2")


def test_partial_update_folds_payload_like_bom(stores):
    bom, store = stores
    for tree in (bom, store):
        set_node(tree, "rooms/kitchen/sink",
                 {"shape": {"op": "box", "size": [600, 500, 200]}})
        set_node(tree, "rooms/kitchen/sink",
                 {"params": {"width": {"value": 650, "unit": "mm"}}})
        node = get_node(tree, "rooms/kitchen/sink")
        assert node.payload["shape"]["op"] == "box"   # a partial edit kept it
        assert node.params["width"].value == 650
        assert node.links == {"drains": ["rooms/kitchen"]}


def test_children_replacement_and_delete(stores):
    bom, store = stores
    for tree in (bom, store):
        set_node(tree, "rooms/kitchen", {"children": [
            {"id": "hob", "kind": "fixture"}, {"id": "fridge", "kind": "fixture"}]})
        assert tree.children("rooms/kitchen") == ["hob", "fridge"]
        gone = delete_node(tree, "rooms/kitchen")
        assert [c.id for c in gone.children] == ["hob", "fridge"]
        assert get_node(tree, "rooms/kitchen") is None
        assert get_node(tree, "rooms") is not None


def test_rules_evaluate_identically(stores):
    bom, store = stores
    rules = [
        Rule(name="wide-enough", kind="fixture",
             expr="param(self, 'width') >= 500", description="fixtures fit"),
        Rule(name="bolt-mass", path="",
             expr="rollup('ebom', 'qty', 'mass') == 30"),
    ]
    bom.rules.extend(rules)
    store.rules.extend(rules)
    key = lambda results: sorted((r.rule, r.node, r.ok) for r in results)
    assert key(run_rules(store)) == key(run_rules(bom))
    assert rollup(store, "ebom", "qty", "mass") == rollup(bom, "ebom", "qty", "mass")


def test_persistence_across_reopen(tmp_path):
    db = tmp_path / "tree.db"
    store = SqliteStore(db)
    build(store)
    store.vocabulary.append(KindDef(kind="fixture", description="a fitted thing"))
    store.rules.append(Rule(name="r", path="", expr="1 < 2"))
    store.save()
    store.close()

    again = SqliteStore(db)
    assert get_node(again, "rooms/kitchen/sink").params["width"].value == 600
    assert [k.kind for k in again.vocabulary] == ["fixture"]
    assert [r.name for r in again.rules] == ["r"]
    assert [p for p, _ in again.walk("")]  # tree survived whole
    again.close()


def test_ingest_and_snapshot_round_trip(tmp_path):
    bom = Bom()
    build(bom)
    bom.vocabulary.append(KindDef(kind="space", description="a room"))
    store = SqliteStore(tmp_path / "tree.db")
    store.ingest(bom)
    assert store.snapshot() == bom
    with pytest.raises(ValueError, match="already holds a tree"):
        store.ingest(bom)
    store.close()


def test_depth_hint_prunes_hydration(stores):
    _, store = stores
    shallow = store.get("rooms/kitchen", depth=0)
    assert shallow.children == []
    one = store.get("rooms", depth=1)
    assert [c.id for c in one.children] == ["kitchen"]
    assert one.children[0].children == []


def test_a_wider_tree_stays_answerable(tmp_path):
    store = SqliteStore(tmp_path / "wide.db")
    for i in range(1500):
        set_node(store, f"lines/l{i:04d}", {
            "kind": "line" if i % 3 else "milestone",
            "params": {"qty": {"value": float(i % 7), "unit": "each"}}})
    assert len(find_nodes(store, kind="milestone", limit=10)) == 10
    assert store.children("lines")[:2] == ["l0000", "l0001"]
    assert len(list(store.walk("lines"))) == 1501  # anchor + 1500
    store.close()
