"""Solvers as data: client-submitted code, run in a sandbox, answering in proposals.

A solver is a WebAssembly module stored as a content-addressed blob and described
by a `SolverDef` in the tree — name, prose contract, and the branch prefixes it is
allowed to read (its *capabilities*: no declaration, no access; never the whole
tree by right). The runtime grants it nothing but memory and fuel: no filesystem,
no network, no clock. It cannot mutate the tree — it returns *diagnostics* (free
text) and *proposals* (param values), each proposal stamped `derived` with the
solver's identity, and the caller decides what to apply with an ordinary tree_set.
The server never learns what the solver means; it meters it and files its output.

ABI (deliberately tiny, any guest language can meet it):
    (export "memory")  a linear memory
    (export "alloc")   (func (param $len i32) (result i32)) — guest allocator
    (export "run")     (func (param $ptr i32) (param $len i32) (result i64))
The host writes the input JSON at alloc(len); `run` returns (ptr << 32) | len of
the output JSON in guest memory. Input: {"path", "slice", "params"}. Output:
{"diagnostics": [str], "proposals": [{"path", "param", "value", "note"?}]}.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_FUEL = 500_000_000        # ~ a fraction of a second of pure compute
DEFAULT_MEMORY_MB = 64
MAX_WASM_BYTES = 8 * 2**20
MAX_OUTPUT_BYTES = 4 * 2**20


class SolverDef(BaseModel):
    """One solver's descriptor — the code itself lives in the blob store, or, for a
    standard contract, in a first-class native implementation registered under the
    same name (`native=True`, no blob)."""

    name: str
    description: str = ""
    blob: str = ""  # sha256 of the wasm module; empty for native contracts
    native: bool = False
    reads: list[str] = Field(default_factory=list)  # branch prefixes it may see
    params_doc: dict[str, str] = Field(default_factory=dict)
    fuel: int = DEFAULT_FUEL


class SolverError(ValueError):
    """Anything that stops a run: bad module, trap, fuel out, bad output."""


# --- content-addressed blob store ----------------------------------------------

def save_blob(blob_dir: Path, data: bytes) -> str:
    if len(data) > MAX_WASM_BYTES:
        raise SolverError(f"module too large ({len(data)} bytes > {MAX_WASM_BYTES})")
    sha = hashlib.sha256(data).hexdigest()
    blob_dir.mkdir(parents=True, exist_ok=True)
    path = blob_dir / f"{sha}.wasm"
    if not path.exists():
        path.write_bytes(data)
    return sha


def load_blob(blob_dir: Path, sha: str) -> bytes:
    path = blob_dir / f"{sha}.wasm"
    if not path.exists():
        raise SolverError(f"no blob {sha[:12]}… in the store")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise SolverError(f"blob {sha[:12]}… fails its own hash — refusing to run it")
    return data


# --- capabilities ----------------------------------------------------------------

def path_allowed(reads: list[str], path: str) -> bool:
    """Segment-aware prefix check: 'foo' allows 'foo/bar', not 'foobar'."""
    want = [s for s in path.split("/") if s]
    for r in reads:
        have = [s for s in r.split("/") if s]
        if want[:len(have)] == have:
            return True
    return False


# --- the sandboxed run ------------------------------------------------------------

def run_solver(wasm: bytes, payload: dict[str, Any],
               fuel: int = DEFAULT_FUEL, memory_mb: int = DEFAULT_MEMORY_MB) -> dict[str, Any]:
    """Execute one solver call and validate its answer. Raises SolverError."""
    import wasmtime

    cfg = wasmtime.Config()
    cfg.consume_fuel = True
    engine = wasmtime.Engine(cfg)
    try:
        module = wasmtime.Module(engine, wasm)
    except Exception as e:
        raise SolverError(f"not a valid wasm module: {e}") from e

    store = wasmtime.Store(engine)
    store.set_limits(memory_size=memory_mb * 2**20)
    store.set_fuel(fuel)

    linker = wasmtime.Linker(engine)  # nothing linked in: no imports, no ambient world
    try:
        instance = linker.instantiate(store, module)
    except Exception as e:
        raise SolverError(f"instantiation failed (imports are not provided): {e}") from e

    exports = instance.exports(store)
    memory, alloc, run = exports.get("memory"), exports.get("alloc"), exports.get("run")
    if memory is None or alloc is None or run is None:
        raise SolverError("module must export 'memory', 'alloc' and 'run'")

    data = json.dumps(payload).encode("utf-8")
    try:
        ptr = alloc(store, len(data))
        memory.write(store, data, ptr)
        packed = run(store, ptr, len(data))
    except wasmtime.Trap as e:
        raise SolverError(f"solver trapped (out of fuel or faulted): {e}") from e

    out_ptr, out_len = (packed >> 32) & 0xFFFFFFFF, packed & 0xFFFFFFFF
    if out_len > MAX_OUTPUT_BYTES:
        raise SolverError(f"output too large ({out_len} bytes)")
    try:
        raw = bytes(memory.read(store, out_ptr, out_ptr + out_len))
        out = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise SolverError(f"output is not valid JSON: {e}") from e
    return _validate_output(out)


def _validate_output(out: Any) -> dict[str, Any]:
    if not isinstance(out, dict):
        raise SolverError("output must be an object")
    diagnostics = out.get("diagnostics", [])
    proposals = out.get("proposals", [])
    if (not isinstance(diagnostics, list)
            or not all(isinstance(d, str) for d in diagnostics)):
        raise SolverError("diagnostics must be a list of strings")
    if not isinstance(proposals, list):
        raise SolverError("proposals must be a list")
    clean = []
    for p in proposals:
        if (not isinstance(p, dict) or not isinstance(p.get("path"), str)
                or not isinstance(p.get("param"), str)
                or not isinstance(p.get("value"), (int, float))):
            raise SolverError(f"bad proposal (need path/param/value): {p}")
        clean.append({"path": p["path"], "param": p["param"],
                      "value": float(p["value"]),
                      **({"note": p["note"]} if isinstance(p.get("note"), str) else {})})
    return {"diagnostics": list(diagnostics), "proposals": clean}


def stamp(proposals: list[dict[str, Any]], solver_name: str, blob_sha: str,
          path: str) -> list[dict[str, Any]]:
    """Attach the ready-to-apply Quantity to each proposal: provenance 'derived',
    source naming the exact code and slice that produced it — auditable, and
    invalidatable the day the inputs change."""
    src = f"solver {solver_name}@{blob_sha[:8]} on '{path}'"
    return [{**p, "quantity": {"value": p["value"], "provenance": "derived",
                               "source": src, **({"note": p["note"]} if "note" in p else {})}}
            for p in proposals]
