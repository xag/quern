"""SqliteStore: the same verbs as Quern, answered by indexes — parity, then scale."""

import pytest

from quern import (
    Quern,
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
    """The same edits against any TreeStore — Quern and SqliteStore alike."""
    set_node(tree, "parts/bolt", {
        "kind": "fastener",
        "params": {"mass": {"value": 10, "unit": "g"}}})
    set_node(tree, "parts/rivet", {
        "kind": "fastener",
        "payload": {"field": "Some_API_Field_Name",
                    "notes": [{"text": "buried in a list"}], "count": 9},
        "params": {"length": {"value": 12, "unit": "mm",
                              "source": "datasheet DS-4471"}}})
    set_node(tree, "rooms/kitchen", {
        "kind": "space", "name": "Kitchen", "meta": {"floor": "ground"}})
    set_node(tree, "rooms/kitchen/sink", {
        "kind": "fixture",
        "params": {"width": {"value": 600, "unit": "mm"}},
        "links": {"drains": ["rooms/kitchen"]}})
    set_node(tree, "rooms/kitchen/sink-v2", {
        "kind": "fixture",
        "links": {"supersedes": ["rooms/kitchen/sink"]}})
    set_node(tree, "assembly/line1", {
        "links": {"uses": ["parts/bolt"]},
        "params": {"qty": {"value": 3, "unit": "each"}}})
    # Three mirrored records, the shape #54 is about: the state a check scopes by is
    # a payload FIELD, and the third node has the word in its prose and not in its
    # state — which is exactly what a substring query cannot tell apart.
    set_node(tree, "programs/alpha", {"kind": "program",
                                      "payload": {"state": "Opened", "ref": "P-1"}})
    set_node(tree, "programs/beta", {"kind": "program",
                                     "payload": {"state": "Proposed", "ref": "P-2"}})
    set_node(tree, "programs/gamma", {
        "kind": "program",
        "payload": {"state": "Closed", "record": {"origin": "platform"},
                    "note": "reopened once, then Opened again"}})


@pytest.fixture(params=["own file", "over a base"])
def stores(request, tmp_path):
    """The store holding the tree in its own file, and a store over a base file that holds it
    (SqliteStore(base=...)), whose writes land in the store's own rows: each answers as the Quern."""
    quern = Quern()
    build(quern)
    if request.param == "own file":
        store = SqliteStore(tmp_path / "tree.db")
        build(store)
    else:
        base = SqliteStore(tmp_path / "base.db")
        build(base)
        base.close()
        store = SqliteStore(":memory:", base=tmp_path / "base.db")
    yield quern, store
    store.close()


def test_get_and_children_parity(stores):
    quern, store = stores
    for path in ("", "rooms", "rooms/kitchen", "rooms/kitchen/sink", "missing"):
        b, s = get_node(quern, path), get_node(store, path)
        if b is None:
            assert s is None
            continue
        assert s is not None
        assert (s.kind, s.name, s.meta) == (b.kind, b.name, b.meta)
        assert {k: q.value for k, q in s.params.items()} == \
               {k: q.value for k, q in b.params.items()}
        assert [c.id for c in s.children] == [c.id for c in b.children]
    assert store.children("rooms/kitchen") == quern.children("rooms/kitchen")


def test_walk_preserves_document_order(stores):
    quern, store = stores
    assert [p for p, _ in store.walk("")] == [p for p, _ in quern.walk("")]
    assert [p for p, _ in store.walk("rooms/kitchen")] == \
           [p for p, _ in quern.walk("rooms/kitchen")]


def test_a_walk_of_one_kind_gives_those_nodes_in_order_and_reads_no_other(stores, monkeypatch):
    quern, store = stores
    for under in ("", "programs", "programs/beta", "rooms", "nowhere"):
        for kind in ("program", "fixture", "no-such-kind"):
            want = [p for p, n in quern.walk(under) if n.kind == kind]
            assert [p for p, _ in quern.walk(under, kind=kind)] == want
            assert [p for p, _ in store.walk(under, kind=kind)] == want
    assert [p for p, _ in quern.walk("", kind="program")] == ["programs/alpha", "programs/beta", "programs/gamma"]
    for under in ("", "programs", "programs/beta", "rooms", "nowhere"):
        for kind in (None, "program", "fixture"):
            want = [p for p, _ in quern.walk(under, kind)]
            assert quern.paths(under, kind) == want and store.paths(under, kind) == want
    # the store reads the nodes of that kind and no other: the point of asking for a kind
    import quern.store as qs
    read, real = [], qs._node_of
    monkeypatch.setattr(qs, "_node_of", lambda path, doc: (read.append(path), real(path, doc))[1])
    list(store.walk("", kind="program"))
    assert read == ["programs/alpha", "programs/beta", "programs/gamma"]
    read.clear()
    assert store.paths("", "program") == ["programs/alpha", "programs/beta", "programs/gamma"] and read == []


def test_a_param_keeps_the_grounding_it_was_given(stores):
    """`grounded` stated against its label's default comes back as stated, from both stores."""
    for store in stores:
        store.set("readings/a", {"kind": "clause", "params": {
            "found": {"value": 125.0, "unit": "mm", "provenance": "published", "grounded": True},
            "doubted": {"value": 3.0, "unit": "mm", "provenance": "measured", "grounded": False}}})
        got = store.get("readings/a").params
        assert (got["found"].grounded, got["doubted"].grounded) == (True, False)


def test_a_node_read_again_after_a_write_is_the_node_as_written(stores):
    """The disk store keeps the rows it last read; a write drops them, a delete too, and a node
    that was not there is found once it is set."""
    for store in stores:
        assert store.get("readings/b", depth=0) is None
        store.set("readings/b", {"kind": "clause", "name": "first"})
        assert store.get("readings/b", depth=0).name == "first"
        store.set("readings/b", {"name": "second"})
        assert store.get("readings/b").name == "second"
        store.set("readings/b/under", {"kind": "clause"})
        assert [c.id for c in store.get("readings/b").children] == ["under"]
        if store is not stores[0]:   # in memory the depth is a hint, and the live node has its children
            assert store.get("readings/b", depth=0).children == []
        store.delete("readings/b")
        assert store.get("readings/b") is None


def test_a_rule_reads_a_nodes_kind_and_payload_without_what_is_under_it(stores, monkeypatch):
    """kind(p) is a node's own kind, '' for none; payload(), linked() and kind() read the node
    alone, so a rule over thousands of leaves does not read their parent's branch at each."""
    from quern.tree import Rule, run_rules
    import quern.store as qs
    quern, store = stores
    for s in (quern, store):
        s.set("lib", {"kind": "source", "payload": {"authority": "maker"}})
        for i in range(30):
            s.set(f"lib/c{i}", {"kind": "clause"})
        s.rules = [Rule(name="a-clause-sits-in-a-source", kind="clause",
                        expr="kind(parent(self)) == 'source' and payload(parent(self), 'authority', '') != ''")]
    got = [{(r.node, r.ok) for r in run_rules(s, rules=["a-clause-sits-in-a-source"])} for s in (quern, store)]
    assert got[0] == got[1] and len(got[0]) == 30 and all(ok for _, ok in got[0])
    hydrated = []
    real = qs.SqliteStore._hydrate_children
    monkeypatch.setattr(qs.SqliteStore, "_hydrate_children",
                        lambda self, path, depth: (hydrated.append(path), real(self, path, depth))[1])
    run_rules(store, rules=["a-clause-sits-in-a-source"])
    assert hydrated == []


def test_find_parity(stores):
    quern, store = stores
    for kwargs in (
        {"kind": "fixture"},
        {"query": "kitchen"},
        {"has_param": "qty"},
        {"links_to": "rooms/kitchen/sink"},
        {"under": "rooms"},
        {"kind": "fixture", "current_only": True},
        {"query": "ground"},  # meta values are searchable
        {"query": "some_api_field"},  # and payload strings, however deep (#51)
        {"query": "ds-4471"},  # and the source a param cites
        {"payload": {"state": "Opened"}},              # a field's value (#54)
        {"payload": {"state": ["Opened", "Proposed"]}},  # any of several
        {"payload": {"count": 9}},                     # numbers, not only strings
        {"payload": {"state": "Opened"}, "kind": "program"},   # composes
        {"payload": {"state": None}, "kind": "fastener"},      # absent reads as None
        {"payload": {"record": {"origin": "platform"}}},        # a nested value
    ):
        assert [p for p, _ in find_nodes(store, **kwargs)] == \
               [p for p, _ in find_nodes(quern, **kwargs)], kwargs


def test_query_reaches_payload_and_param_sources(stores):
    """The one string a practitioner arrives with is often only in the payload — an
    external identifier, a definition, a field name the domain records — or in the
    source a param cites. Until #51 `query` stopped at id/name/kind/meta and such a
    node resolved to nothing."""
    for tree in stores:
        assert [p for p, _ in find_nodes(tree, query="some_api_field")] == \
            ["parts/rivet"]
        assert [p for p, _ in find_nodes(tree, query="in a list")] == ["parts/rivet"]
        assert [p for p, _ in find_nodes(tree, query="ds-4471")] == ["parts/rivet"]
        # a number in the payload is not prose: its digits find nothing
        assert find_nodes(tree, query="9") == []


def test_payload_scopes_by_a_fields_value_where_a_substring_cannot(stores):
    """Scoping is the first thing a check does, and the scope is nearly always a
    field's value. `query="Opened"` cannot say it — it also matches a description
    carrying the word, and "any of these" cannot be said at all."""
    for tree in stores:
        opened = find_nodes(tree, payload={"state": "Opened"})
        assert [p for p, _ in opened] == ["programs/alpha"]
        # the prose match a check does not want: gamma carries the word in a note
        assert [p for p, _ in find_nodes(tree, query="opened")] == [
            "programs/alpha", "programs/gamma"]
        # ...and "any of these", which a substring cannot say at all
        assert [p for p, _ in find_nodes(
            tree, payload={"state": ["Opened", "Proposed"]})] == [
            "programs/alpha", "programs/beta"]
        # every filter is an AND, and a value nothing holds finds nothing
        assert find_nodes(tree, payload={"state": "Opened"}, kind="fastener") == []
        assert find_nodes(tree, payload={"state": "Retired"}) == []
        # a key the payload does not carry reads as None, so this asks for the nodes
        # that state no such field - the honest reading, and the useful one
        assert [p for p, _ in find_nodes(
            tree, payload={"state": None}, kind="fastener")] == [
            "parts/bolt", "parts/rivet"]


def test_payload_matching_holds_where_sqlite_cannot_narrow(stores):
    """The json_extract clause is an optimisation over plain keys and scalar values.
    A nested value, or a key that would need quoting, is filtered in Python on both
    stores - so the two answer the same thing rather than one answering less."""
    for tree in stores:
        assert [p for p, _ in find_nodes(
            tree, payload={"record": {"origin": "platform"}})] == ["programs/gamma"]
        assert find_nodes(tree, payload={"no.such key": "x"}) == []


def test_supersession_reads_from_the_link_index(stores):
    _, store = stores
    assert superseders(store, "rooms/kitchen/sink") == ["rooms/kitchen/sink-v2"]
    assert is_superseded(store, "rooms/kitchen/sink")
    assert not is_superseded(store, "rooms/kitchen/sink-v2")


def test_partial_update_folds_payload(stores):
    quern, store = stores
    for tree in (quern, store):
        set_node(tree, "rooms/kitchen/sink",
                 {"shape": {"op": "box", "size": [600, 500, 200]}})
        set_node(tree, "rooms/kitchen/sink",
                 {"params": {"width": {"value": 650, "unit": "mm"}}})
        node = get_node(tree, "rooms/kitchen/sink")
        assert node.payload["shape"]["op"] == "box"   # a partial edit kept it
        assert node.params["width"].value == 650
        assert node.links == {"drains": ["rooms/kitchen"]}


def test_children_replacement_and_delete(stores):
    quern, store = stores
    for tree in (quern, store):
        set_node(tree, "rooms/kitchen", {"children": [
            {"id": "hob", "kind": "fixture"}, {"id": "fridge", "kind": "fixture"}]})
        assert tree.children("rooms/kitchen") == ["hob", "fridge"]
        gone = delete_node(tree, "rooms/kitchen")
        assert [c.id for c in gone.children] == ["hob", "fridge"]
        assert get_node(tree, "rooms/kitchen") is None
        assert get_node(tree, "rooms") is not None


def test_rules_evaluate_identically(stores):
    quern, store = stores
    rules = [
        Rule(name="wide-enough", kind="fixture",
             expr="param(self, 'width') >= 500", description="fixtures fit"),
        Rule(name="bolt-mass", path="",
             expr="rollup('assembly', 'qty', 'mass') == 30"),
    ]
    quern.rules.extend(rules)
    store.rules.extend(rules)
    key = lambda results: sorted((r.rule, r.node, r.ok) for r in results)
    assert key(run_rules(store)) == key(run_rules(quern))
    assert rollup(store, "assembly", "qty", "mass") == rollup(quern, "assembly", "qty", "mass")


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
    quern = Quern()
    build(quern)
    quern.vocabulary.append(KindDef(kind="space", description="a room"))
    store = SqliteStore(tmp_path / "tree.db")
    store.ingest(quern)
    assert store.snapshot() == quern
    with pytest.raises(ValueError, match="already holds a tree"):
        store.ingest(quern)
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


def test_a_store_over_a_base_leaves_the_base_as_it_was_and_to_itself(tmp_path):
    """Two stores over one base: each sees its own writes and deletions and not the other's,
    and the base file is the same bytes after."""
    base = SqliteStore(tmp_path / "base.db")
    build(base)
    base.close()
    before = (tmp_path / "base.db").read_bytes()
    one = SqliteStore(":memory:", base=tmp_path / "base.db")
    two = SqliteStore(tmp_path / "two.db", base=tmp_path / "base.db")
    one.set("rooms/kitchen/sink", {"params": {"width": {"value": 700, "unit": "mm"}}})
    one.delete("parts")
    two.set("rooms/hall", {"kind": "space"})
    assert one.get("rooms/kitchen/sink").params["width"].value == 700
    assert two.get("rooms/kitchen/sink").params["width"].value == 600
    assert one.get("parts/bolt") is None and two.get("parts/bolt") is not None
    assert one.backlinks("uses", "parts/bolt") == two.backlinks("uses", "parts/bolt") == ["assembly/line1"]
    assert one.get("rooms/hall") is None and two.children("rooms") == ["kitchen", "hall"]
    one.close()
    two.close()
    assert (tmp_path / "base.db").read_bytes() == before
