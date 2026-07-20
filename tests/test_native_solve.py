"""tree_solve runs native contracts.

Packages ship native solver descriptors (native=True, no blob), and rules consult
them through solve(...). Until now that was the ONLY door: an agent could be judged
by a contract it could never ask directly. tree_solve now resolves native
descriptors through the same registry, with the same output validation and the same
'derived' stamp as wasm — one channel, either implementation.
"""

import asyncio

import pytest

from quern import Quern, Node
from quern.solver import SolverDef, SolverError, run_native, stamp
from quern.tree import NATIVE, register_native


class Ws:
    label = "test-ws"

    def __init__(self, solvers):
        self._quern = Quern(
            solvers=solvers,
            root=Node(id="root", children=[Node(id="home", children=[
                Node(id="salon", kind="space")])]))

    @property
    def quern(self):
        return self._quern

    def effective(self):
        return self._quern

    def assert_editable(self, path):
        pass

    def save(self):
        pass

    @property
    def blob_dir(self):
        raise NotImplementedError

    @property
    def library(self):
        raise NotImplementedError

    def starter_vocabulary(self):
        return []


@pytest.fixture
def natives():
    installed = []

    def install(name, fn):
        register_native(name, fn)
        installed.append(name)

    yield install
    for name in installed:
        NATIVE.pop(name, None)


def _solve(ws, args):
    from mcp.server.fastmcp import FastMCP

    from quern.host import register_tree_tools

    mcp = FastMCP("t")
    register_tree_tools(mcp, lambda: ws)
    res = asyncio.run(mcp.call_tool("tree_solve", args))
    return res[1] if isinstance(res, tuple) else res


def test_a_native_answering_in_proposals_comes_back_stamped(natives):
    natives("test/layout", lambda tree, path: {
        "diagnostics": ["placed 1 room"],
        "proposals": [{"path": "home/salon", "param": "x", "value": 1200.0,
                       "derived_from": ["evidence/a", "evidence/b"]}]})
    ws = Ws([SolverDef(name="test/layout", native=True, reads=[""])])
    out = _solve(ws, {"name": "test/layout", "path": "home"})
    assert out["blob"] == "native"
    assert out["diagnostics"] == ["placed 1 room"]
    q = out["proposals"][0]["quantity"]
    assert q["provenance"] == "derived" and q["grounded"] is False
    # the solver named the exact evidence the value came from; the stamp keeps it
    assert q["derived_from"] == ["evidence/a", "evidence/b"]
    assert "native" in q["source"]


def test_a_scalar_contract_answers_as_a_value(natives):
    natives("test/count", lambda tree, path: 3.0)
    ws = Ws([SolverDef(name="test/count", native=True, reads=[""])])
    out = _solve(ws, {"name": "test/count", "path": "home"})
    assert out["value"] == 3.0 and out["proposals"] == []


def test_params_reach_the_native_as_keywords(natives):
    natives("test/tol", lambda tree, path, tol=1.0: tol)
    ws = Ws([SolverDef(name="test/tol", native=True, reads=[""])])
    out = _solve(ws, {"name": "test/tol", "path": "home", "params": {"tol": 42}})
    assert out["value"] == 42.0


def test_a_declared_native_nobody_registered_is_an_error_not_a_crash(natives):
    ws = Ws([SolverDef(name="test/ghost", native=True, reads=[""])])
    out = _solve(ws, {"name": "test/ghost", "path": "home"})
    assert "not implement" in out["error"]


def test_reads_still_gate_native_contracts(natives):
    natives("test/narrow", lambda tree, path: 1.0)
    ws = Ws([SolverDef(name="test/narrow", native=True, reads=["pieces"])])
    out = _solve(ws, {"name": "test/narrow", "path": "home"})
    assert "outside" in out["error"]


def test_run_native_refuses_shapeless_output(natives):
    with pytest.raises(SolverError):
        run_native(lambda tree, path: "not a shape", Quern(), "")
    with pytest.raises(SolverError):
        run_native(lambda tree, path: {"proposals": [{"path": "p"}]}, Quern(), "")


def test_a_wasm_proposal_without_lineage_keeps_the_slice_default():
    stamped = stamp([{"path": "a", "param": "x", "value": 1.0}], "s", "deadbeef", "home")
    assert stamped[0]["quantity"]["derived_from"] == ["home"]


class SplitWs:
    """A workspace whose EFFECTIVE tree carries a solver its writable tree does not —
    the shape a pinned package makes: the descriptor is available to read and to solve,
    but it is not in the tree the host may edit."""
    label = "split-ws"

    def __init__(self, pinned):
        self._stored = Quern(root=Node(id="root"))
        self._effective = Quern(solvers=pinned, root=Node(id="root"))

    @property
    def quern(self):
        return self._stored

    def effective(self):
        return self._effective

    def assert_editable(self, path):
        pass

    def save(self):
        pass

    @property
    def blob_dir(self):
        raise NotImplementedError

    @property
    def library(self):
        raise NotImplementedError

    def starter_vocabulary(self):
        return []


def _solver_tool(ws, args):
    from mcp.server.fastmcp import FastMCP

    from quern.host import register_tree_tools

    mcp = FastMCP("t")
    register_tree_tools(mcp, lambda: ws)
    res = asyncio.run(mcp.call_tool("tree_solver", args))
    out = res[1] if isinstance(res, tuple) else res
    return out.get("result", out) if isinstance(out, dict) else out


def test_tree_solver_inspects_a_pinned_solver_it_cannot_author():
    """The bug this pins: tree_solver read ws.quern, so a package-pinned solver — the
    kind the Solvers panel lists — answered 'no artifact' when asked about itself. The
    read path now consults the effective tree; register/remove still cannot touch a pin."""
    ws = SplitWs([SolverDef(name="grounding/untrusted", native=True, reads=[""],
                            description="counts what is not safe to act on",
                            params_doc={"tolerance": "loosest grounding that still counts"})])

    listing = _solver_tool(ws, {})
    assert "grounding/untrusted" in listing  # listed though it is not in the writable tree

    detail = _solver_tool(ws, {"name": "grounding/untrusted"})
    assert "counts what is not safe to act on" in detail
    assert "tolerance" in detail                  # params_doc reaches the reader on demand
    assert "pinned from a package" in detail      # and it says the descriptor is not editable

    refused = _solver_tool(ws, {"name": "grounding/untrusted", "remove": True})
    assert "pinned from a package" in refused      # a read-listed pin is not removable
