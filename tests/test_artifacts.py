"""Artifact media: one content-addressed store; only wasm proposes values."""

import hashlib

import pytest

from quern import ArtifactDef, SolverDef, load_blob, save_blob
from quern.library import Library, Package
from quern.solver import SolverError


def test_blobs_store_bare_and_roundtrip(tmp_path):
    data = b"<html>jog pad</html>"
    sha = save_blob(tmp_path, data)
    assert sha == hashlib.sha256(data).hexdigest()
    assert (tmp_path / sha).exists()
    assert load_blob(tmp_path, sha) == data


def test_legacy_wasm_named_blobs_keep_serving(tmp_path):
    data = b"\x00asm-legacy"
    sha = hashlib.sha256(data).hexdigest()
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{sha}.wasm").write_bytes(data)
    assert load_blob(tmp_path, sha) == data
    save_blob(tmp_path, data)  # idempotent: sees the legacy file, writes nothing
    assert not (tmp_path / sha).exists()


def test_corrupt_blob_is_refused(tmp_path):
    sha = save_blob(tmp_path, b"good content")
    (tmp_path / sha).write_bytes(b"tampered")
    with pytest.raises(SolverError, match="fails its own hash"):
        load_blob(tmp_path, sha)


def test_non_wasm_media_publish_without_the_abi_gate(tmp_path):
    lib = Library(tmp_path)
    log = lib.publish(Package(
        name="jog", version="1",
        solvers=[ArtifactDef(name="jog-pad", medium="web",
                             description="a pad the user drags"),
                 ArtifactDef(name="jog-howto", medium="prose")]),
        {"jog-pad": b"<html>pad</html>", "jog-howto": b"drag gently."})
    assert sum("stored" in line for line in log) == 2
    assert all("ABI" not in line for line in log)


def test_wasm_medium_still_faces_the_abi_gate(tmp_path):
    lib = Library(tmp_path)
    with pytest.raises(ValueError, match="not a valid wasm module"):
        lib.publish(Package(name="bad", version="1",
                            solvers=[SolverDef(name="claims-compute")]),
                    {"claims-compute": b"<html>not wasm</html>"})


def test_artifactdef_is_the_solverdef_shape():
    assert ArtifactDef is SolverDef
    assert SolverDef(name="x").medium == "wasm"  # descriptors predating media
