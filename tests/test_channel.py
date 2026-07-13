"""The channel: lock the closure, sync it hash-verified, publish as the only door."""

import json

import pytest

from bom import Bom, PackageRef
from bom.cli import main
from bom.library import Library, Package, lock_refs, package_digest, sync
from bom.solver import load_blob
from bom.tree import KindDef, Node, Rule


def bolt(id: str, mass: float = 10.0) -> Node:
    return Node(id=id, kind="bolt",
                params={"mass": {"value": mass, "unit": "g"}})


def fasteners(min_mass: str = "0") -> Package:
    return Package(
        name="fasteners", version="1",
        vocabulary=[KindDef(kind="bolt", description="a threaded fastener",
                            params={"mass": "grams"})],
        rules=[Rule(name="bolt-has-mass", kind="bolt", expr=f"mass > {min_mass}")],
        examples=[bolt("proof-bolt")])


def assemblies() -> Package:
    return Package(
        name="assemblies", version="1",
        requires=[PackageRef(name="fasteners", version="1")],
        vocabulary=[KindDef(kind="pack", description="bolts sold together")],
        rules=[Rule(name="pack-of-two", kind="pack",
                    expr="tally(self, 'bolt', 'qty') == 2")],
        examples=[Node(id="proof-pack", kind="pack",
                       children=[bolt("b1"), bolt("b2")])])


def registry(tmp_path) -> Library:
    reg = Library(tmp_path / "registry")
    reg.publish(fasteners(), {})
    reg.publish(assemblies(), {})
    return reg


def test_lock_refs_flattens_the_closure_with_digests(tmp_path):
    reg = registry(tmp_path)
    refs = lock_refs(reg, [PackageRef(name="assemblies", version="1")])
    assert [(r.name, r.version) for r in refs] == [
        ("assemblies", "1"), ("fasteners", "1")]
    assert all(r.sha256 for r in refs)
    assert refs[1].sha256 == package_digest(reg.get("fasteners", "1"))


def test_sync_materializes_deps_first_and_reruns_the_proof(tmp_path):
    reg = registry(tmp_path)
    cache = Library(tmp_path / "cache")
    refs = lock_refs(reg, [PackageRef(name="assemblies", version="1")])
    log = sync(reg, cache, refs)
    assert len(log) == 2 and "proof re-run" in log[0]
    # the cache now serves the closure by itself
    tree = Bom(packages=[PackageRef(name="assemblies", version="1")])
    assert [p.name for p in cache.resolve(tree)] == ["assemblies", "fasteners"]
    # and a re-sync is the identical-republish no-op, not an error
    sync(reg, cache, refs)


def test_sync_refuses_a_hashless_ref(tmp_path):
    reg = registry(tmp_path)
    with pytest.raises(ValueError, match="a lock is exact or it is not a lock"):
        sync(reg, Library(tmp_path / "cache"),
             [PackageRef(name="fasteners", version="1")])


def test_sync_refuses_drifted_registry_content(tmp_path):
    reg = registry(tmp_path)
    refs = lock_refs(reg, [PackageRef(name="fasteners", version="1")])
    drifted = Library(tmp_path / "drifted")
    drifted.publish(fasteners(min_mass="1"), {})  # same name@version, other bytes
    with pytest.raises(ValueError, match="same name, different meaning"):
        sync(drifted, Library(tmp_path / "cache"), refs)


def test_sync_carries_solver_blobs(tmp_path):
    reg = Library(tmp_path / "registry")
    notes = Package(
        name="notes", version="1",
        solvers=[{"name": "field-guide", "medium": "prose",
                  "description": "how to read the tree"}])
    reg.publish(notes, {"field-guide": b"read the params before the children"})
    cache = Library(tmp_path / "cache")
    sync(reg, cache, lock_refs(reg, [PackageRef(name="notes", version="1")]))
    blob = cache.get("notes", "1").solvers[0].blob
    assert load_blob(cache.blob_dir, blob) == b"read the params before the children"


def test_cli_publish_pin_sync_end_to_end(tmp_path, capsys):
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    artifact = tmp_path / "fasteners.json"
    artifact.write_text(fasteners().model_dump_json(), encoding="utf-8")
    lock = tmp_path / "bom.lock"
    cache = tmp_path / "cache"

    main(["--registry", str(reg_dir), "publish", str(artifact)])
    assert "published fasteners@1" in capsys.readouterr().out
    main(["--registry", str(reg_dir), "pin", "fasteners@1", "--lock", str(lock)])
    entries = json.loads(lock.read_text(encoding="utf-8"))["packages"]
    assert entries[0]["sha256"] == package_digest(fasteners())
    main(["--registry", str(reg_dir), "sync",
          "--lock", str(lock), "--dest", str(cache)])
    assert Library(cache).get("fasteners", "1") is not None


def test_the_real_ledger_travels_the_channel(tmp_path):
    # Phase 2 of #19 in miniature: the packages currently sited in src/bom/
    # publish, pin and sync like any other — nothing about them needs the
    # substrate's source except the native contracts, which stay host code
    # (importing bom.ledger registers grounding's natives in-process; the CLI
    # exposes the same act as --natives).
    from bom.grounding import GROUNDING_PACKAGE
    from bom.ledger import LEDGER_PACKAGE
    reg = Library(tmp_path / "registry")
    reg.publish(GROUNDING_PACKAGE, {})
    reg.publish(LEDGER_PACKAGE, {})
    cache = Library(tmp_path / "cache")
    refs = lock_refs(reg, [PackageRef(name=LEDGER_PACKAGE.name,
                                      version=LEDGER_PACKAGE.version)])
    log = sync(reg, cache, refs)
    assert len(log) == 2  # grounding travelled as the ledger's require
    assert cache.get(LEDGER_PACKAGE.name, LEDGER_PACKAGE.version) is not None


def test_cli_pin_refuses_what_the_registry_lacks(tmp_path):
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    with pytest.raises(SystemExit, match="not pinned"):
        main(["--registry", str(reg_dir), "pin", "ghosts@9",
              "--lock", str(tmp_path / "bom.lock")])
