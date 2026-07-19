"""The nondeterminism boundary, declared as an artifact and recorded from every run.

The estate's practice is to name the boundary as a project's first artifact and record from
commit one, so a bug is replayed rather than re-derived. quern shipped the ledger that other
projects pin and instrumented nothing of its own; this is that gap closed, and closing it
turned out to be an exercise in how *narrow* an honest boundary is.

quern is almost a pure function. It reads a directory, writes a directory, and computes
digests over bytes — and a digest is not an input from the world, it is arithmetic. So the
boundary is four things and no more:

- **text on disk**, through `library.read_text` / `library.write_text`. Every package
  descriptor and every lockfile enters and leaves quern through that one pair.
- **the registry's directory listing**, through `Library.list` — what packages exist is a
  question only the filesystem can answer.
- **solver blobs**, through `solver_blob` — bytes off disk, content-addressed.
- **$QUERN_REGISTRY**, captured in the session header so a tape says which registry it ran
  against instead of leaving the reader to infer it.

What is deliberately NOT here matters as much, because the maintenance contract is that a
new input must be added and an absent one must be known to be absent:

- **no clock and no randomness.** quern reads neither. Identity is the content digest, never
  a timestamp or a nonce, which is why pins are reproducible in the first place. If a clock
  read ever appears, it is a design event before it is a recording gap — add it here, and
  ask in the ledger what it was for.
- **`consume`, `sync`, `lock_refs`, `read_lock`, `write_lock`, `Library.get/publish`.** All
  of these compose the calls above — they choose paths, parse, validate and re-serialize.
  That is quern's own logic, and it is precisely what a replay is supposed to RE-RUN rather
  than be handed back. Recording them would duplicate what their parts already record and
  hide the code under test behind its own tape.
- **the wasm runtime.** A solver runs fuel-metered in a sandbox with no ambient authority —
  deterministic by construction. Loading its blob crosses the boundary; running it does not.
"""

from __future__ import annotations

import os

from flight_recorder import Boundary

from . import library
from .library import Library


def boundary() -> Boundary:
    """quern's four inputs, wrapped in place.

    The seam sits at TEXT, not at the object API above it, and the choice is the whole
    difference between a replayable tape and a decorative one. Recording `Library.get` looks
    more meaningful — the registry answered with a Package — but a tape can only hold what it
    can represent, and a pydantic model is not that: it records as `{"__opaque__": "<repr>"}`
    and replays as the repr STRING, handing the code a str where it expects a Package. The
    questions would still match, so the tape would look healthy while being unreplayable.

    One level down, the world's answer is a JSON string, which the tape holds exactly. Feed
    it back and `model_validate_json` — quern's own code, not the recorder's — rebuilds the
    same object it built the first time. Instrument, never duplicate: parsing is quern's
    business, and the boundary is where the bytes arrive, not where they become meaningful.

    `Library.list` stays at the object level because it already answers in strings, and
    `Library` is a class rather than a module — which the recorder patches identically, since
    it only ever does getattr/setattr on the target it is handed."""
    return Boundary(
        effects=[
            (library, ["read_text", "write_text", "solver_blob"]),
            (Library, ["list"]),
        ],
        # A registry that is missing, unreadable or holds a package that fails the proof gate
        # raises, and the CLI turns that into an exit message. Revive the types so a replayed
        # failure takes the same branch the recorded one took.
        error_revivers={
            "ValueError": lambda args: ValueError(*args),
            "FileNotFoundError": lambda args: FileNotFoundError(*args),
            "KeyError": lambda args: KeyError(*args),
        },
        header_extras={
            # Where the run was pointed. Absent is a fact too: it means the invocation
            # carried --registry, or needed no registry at all.
            "quern_registry": lambda: os.environ.get("QUERN_REGISTRY", ""),
        },
        # No `redact`, no `scrub`, no `forbid`: a tape here carries package names, versions,
        # digests and paths. Nothing quern touches is a credential — and if that ever stops
        # being true, `forbid` is the line to add, because it fails loudly instead of leaking
        # quietly.
    )
