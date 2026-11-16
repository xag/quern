"""require(ref): an installed package gets a registry package by its pin, from the cache when it holds
it, else synced into the cache, the proof re-run, from a registry directory or one served over HTTP."""

from __future__ import annotations

import functools
import http.server
import threading

import pytest

from quern.library import CounterExample, Library, Package, PackageRef, package_digest, require
from quern.tree import KindDef, Node, Rule

BOX = Package(
    name="box", version="0.1.0", description="a box states its size", publisher="test",
    vocabulary=[KindDef(kind="box", description="A box: payload size.")],
    rules=[Rule(name="a-box-states-its-size", kind="box", expr="len(payload(self, 'size', '')) > 0",
                description="A box states its size.")],
    examples=[Node(id="b", kind="box", payload={"size": "big"})],
    counter_examples=[CounterExample(rule="a-box-states-its-size", nodes=[Node(id="b", kind="box")],
                                     because="a box with no size")],
)


@pytest.fixture
def registry(tmp_path):
    root = tmp_path / "registry"
    Library(root).publish(BOX, {})
    return root


@pytest.fixture
def served(registry):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(registry))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.delenv("QUERN_REGISTRY", raising=False)
    monkeypatch.setenv("QUERN_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


PIN = PackageRef(name="box", version="0.1.0", sha256=package_digest(BOX))


def test_a_package_is_fetched_over_http_by_its_pin_and_kept(served, cache):
    url = f"http://127.0.0.1:{served.server_address[1]}"
    assert package_digest(require(PIN, url)) == PIN.sha256
    served.shutdown()  # offline now: the cache answers
    assert package_digest(require(PIN, url)) == PIN.sha256
    assert (cache / "packages" / "box" / "0.1.0.json").exists()


def test_a_package_is_read_from_a_registry_directory(registry):
    assert require(PIN, registry).name == "box"


def test_a_pin_whose_digest_the_registry_does_not_hold_is_refused(registry):
    with pytest.raises(ValueError):
        require(PackageRef(name="box", version="0.1.0", sha256="0" * 64), registry)


def test_a_pin_without_its_digest_is_refused(registry):
    with pytest.raises(ValueError, match="sha256"):
        require(PackageRef(name="box", version="0.1.0"), registry)


def test_a_package_the_registry_lacks_is_refused(served):
    with pytest.raises(ValueError):
        require(PackageRef(name="ghost", version="1.0.0", sha256="0" * 64),
                f"http://127.0.0.1:{served.server_address[1]}")
