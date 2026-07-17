"""quern's own ledger — the substrate finally taking its own medicine.

quern has shipped `ledger@0.1.0` for other projects to pin since #20, and kept no ledger
itself. This is that, and the first slice is the one that hurt: **the compute boundary**.

The story is short. `register_native` lets a package ship a first-class implementation of
a contract, and `run_native` calls it directly rather than inside the wasm runtime. That
decision is *right* — the sandbox exists to contain code the host did not write, and a
native contract is the host's own code. It is recorded below with the alternatives it
rejected, because it should not be re-litigated.

What is recorded below it is what the decision did NOT argue for, and got anyway. "Trusted"
came, silently, to mean two further things:

- **unmetered.** A wasm solver is granted fuel and a memory cap and cannot outstay its
  welcome. `run_native` grants nothing: `fn(tree, path, **(params or {}))`. And `tree_solve`
  splats the CALLER's params straight into the contract, so whatever cost knob a contract
  exposes is turned by whoever is on the wire, with no ceiling anywhere in the host.
- **unmovable.** A wasm module is portable — the host already hands it out at
  `solver://<sha>` precisely so a client can run the same ABI itself. Native code cannot
  leave the process. The most expensive contract a domain can write is therefore the one
  contract that is forbidden to run anywhere but on the host.

And the host runs it on the event loop. The MCP tools are sync `def`s, and the server calls
a sync tool directly — no thread offload — so for the whole duration of a CPU-bound native
contract the process serves nothing else: no other request, no stream, no socket.

None of this is a bug in any one contract. It is the shape of the boundary, and the
hypothesis at the end is the load-bearing claim about how to fix it.
"""

from __future__ import annotations

import os
from pathlib import Path

import quern.grounding  # noqa: F401 — the natives; the package itself arrives by pin
from quern import Quern, Node, Quantity
from quern.library import consume

_ROOT = Path(__file__).resolve().parents[1]


def _unsound(value: float, unit: str, note: str) -> Quantity:
    """A debt's params carry the unsound value and are NOT grounded — that is the whole
    mechanism: `grounding/*` can see them, and therefore so can a gate."""
    return Quantity(value=value, unit=unit, provenance="unreviewed", grounded=False,
                    source=note)


def build() -> Quern:
    """quern's ledger, with ledger@0.1.0's semantics staged beneath it."""
    # The channel of #19 exists now, and the substrate is its own consumer: the ledger
    # arrives by pin — quern.lock, digest and all — never published from source. This is
    # the line the tempdir pattern occupied in every other project, discharged. The
    # sibling checkout is the fleet's registry convention; $QUERN_REGISTRY overrides.
    lib, refs = consume(_ROOT, os.environ.get("QUERN_REGISTRY",
                                              _ROOT.parent / "quern-registry"))
    quern = Quern(packages=[next(r for r in refs if r.name == "ledger")])
    quern = lib.effective(quern)

    quern.root.children = [
        Node(
            id="native-contracts-bypass-the-sandbox",
            kind="decision",
            name="A package may ship a first-class contract that does not run in wasm",
            payload={"why":
                     "The wasm sandbox exists to contain code the host did not write: a "
                     "user may register a solver, and a rule may be extended without a "
                     "deploy, so the runtime must grant an unknown module nothing but "
                     "memory and fuel. A NATIVE contract is the opposite case — it is the "
                     "host's own code, shipped by a package the host installed. Containing "
                     "it against itself buys nothing, and it costs the effective tree: a "
                     "native contract sees the whole of it, where wasm sees only the slice "
                     "at `path`. Rules need that, because a rule predicate IS a contract.",
                     "note":
                     "Sound about ISOLATION, and it is not the isolation that went wrong. "
                     "What it never argued for — and silently licensed — is metering and "
                     "portability. See the two debts below."},
            children=[
                Node(id="compile-every-contract-to-wasm", kind="alternative",
                     name="Force every contract, native or not, through the wasm runtime",
                     payload={"why":
                              "Would make the host's own code pay the cost of being "
                              "contained against itself, and would put a compile step "
                              "between a package and its own semantics — a rule could not "
                              "be evaluated without a toolchain. Rejected for the RULE "
                              "path, and it remains the right answer for the expensive "
                              "PROPOSER path (see the hypothesis)."}),
                Node(id="no-native-contracts", kind="alternative",
                     name="Every contract is a wasm blob; the host implements none",
                     payload={"why":
                              "A rule predicate is a contract. Forbidding native ones means "
                              "no package can define what its own kinds MEAN without "
                              "shipping a binary, which is most of the substrate's promise."}),
            ],
        ),

        Node(
            id="a-native-contract-is-unmetered",
            kind="debt",
            name="run_native grants no fuel, no memory cap and no clock",
            params={"meter": _unsound(
                0, "fuel",
                "run_solver: cfg.consume_fuel, store.set_fuel(fuel), memory_mb. "
                "run_native: `fn(tree, path, **(params or {}))` — and that is all of it.")},
            payload={"note":
                     "The sandbox's runaway guard is the fuel limit, and the native path "
                     "goes around the sandbox, so it goes around the guard. Worse, the cost "
                     "knobs are CALLER-supplied: tree_solve splats its `params` dict into "
                     "the contract, and the host clamps nothing. A contract whose search "
                     "space is exponential in its input therefore has no bound at all, and "
                     "the bound it needs cannot be written by the contract — a contract "
                     "that meters itself is a contract that can forget to.",
                     "found": "2026-07-13, from a consumer whose heaviest contract could be "
                              "asked, over the wire, for a trillion units of work."},
            children=[Node(
                id="meter-the-native-path", kind="discharge",
                name="run_native takes a ceiling the way run_solver takes fuel, and the "
                     "host clamps caller params before they reach any contract",
                payload={"who": "anyone who can change quern's solver boundary — the "
                                "competence is knowing what a contract may be asked for, "
                                "not who is asking"})],
        ),

        Node(
            id="a-host-tool-runs-on-the-event-loop",
            kind="debt",
            name="A CPU-bound tool makes the whole host deaf for its duration",
            params={"concurrency": _unsound(
                0, "request",
                "The MCP surface's tools are sync `def`s, and a sync tool is invoked "
                "directly: `if fn_is_async: return await fn(...) else: return fn(...)`. "
                "No thread offload. Requests served while one computes: zero.")},
            payload={"note":
                     "This is what turns an expensive contract from a slow answer into an "
                     "outage: for as long as it computes, the process serves no other "
                     "request, no stream and no socket. It is also why streaming progress "
                     "out of a long contract cannot work as a fix — the loop that would "
                     "emit the progress is the loop being blocked.",
                     "found": "2026-07-13, alongside the meter."},
            children=[Node(
                id="offload-the-compute-tools", kind="discharge",
                name="The compute-bearing host tools become async and run the contract on "
                     "a worker thread",
                payload={"who": "anyone who can change quern's host surface"})],
        ),

        Node(
            id="heavy-compute-is-a-proposer-never-a-judge",
            kind="hypothesis",
            name="A contract that is expensive never needs to be authoritative",
            payload={"claim":
                     "Contracts divide cleanly in two, and the division predicts where they "
                     "must run.\n\n"
                     "A JUDGE decides whether a write is legal — it is what a rule calls, "
                     "and its verdict gates the tree. It must run on the host, because a "
                     "caller cannot be trusted to mark its own homework, and anything the "
                     "host gates on (a release, a cut, a trade) is only as good as the "
                     "judge being the host's. Judges are cheap: they evaluate a predicate "
                     "against a state that is already fixed.\n\n"
                     "A PROPOSER computes something and hands back PROPOSALS. The host "
                     "writes none of them: the caller applies what it accepts with a "
                     "tree_set that the judges then check anyway. So a proposer needs no "
                     "authority whatsoever — and it is proposers, not judges, that search. "
                     "If this holds, the expensive path never needs host compute at all: "
                     "compile it to wasm and it runs in the CALLER's process, on the "
                     "caller's clock, where a long search costs nobody anything and the "
                     "meter is somebody else's problem. The host already offers exactly "
                     "this — a client may fetch solver://<sha> and run the same ABI — and "
                     "the only reason the expensive contract cannot take the offer is that "
                     "being native is what makes it unmovable.",
                     "note":
                     "This is the claim that decides whether quern ever needs real compute "
                     "capacity (a job queue, workers, a scheduler) or merely a meter and a "
                     "way out. Everything above is a mitigation; this is the exit."},
            children=[Node(
                id="an-expensive-judge", kind="falsification",
                name="A domain appears with a contract that is BOTH expensive AND "
                     "authoritative",
                payload={"claim":
                         "A contract whose verdict gates a write, a payment or a cut — so "
                         "it cannot be delegated to the caller — and which is nonetheless "
                         "not cheap. A rule predicate that must search, or evaluate over a "
                         "long series, rather than check a fixed state. If one exists, the "
                         "host cannot push its cost outward and must schedule real compute, "
                         "and this hypothesis is dead rather than merely inconvenient.",
                         "cadence": "at each new domain, and at any rule whose predicate "
                                    "calls a contract that searches"})],
        ),

        Node(
            id="the-red-ledger-ships-red",
            kind="decision",
            name="quern goes public with its own gate visibly red — deliberately, not "
                 "by accident",
            payload={
                "rationale":
                    "The pitch of this substrate is that a caveat can FIRE: debts are "
                    "data, gates lean on grounding, and nothing unsound passes. A repo "
                    "that scrubbed its ledger green before flipping public would be "
                    "refuting its own thesis in the launch commit — the first thing a "
                    "stranger should meet is `ledger.check` exiting 1 on the compute "
                    "boundary, with the two debts named and their discharge conditions "
                    "attached, because that is the product behaving as designed. The "
                    "red is not an admission bolted on for honesty points; it is the "
                    "demonstration.",
                "consequence":
                    "The README says it out loud ('red today, on purpose'), CONTRIBUTING "
                    "repeats the discharge discipline, and the go/no-go for the flip "
                    "does not wait on the compute-boundary work — the two are unrelated, "
                    "and coupling them would hold the launch hostage to engineering it "
                    "does not need.",
            },
            children=[
                Node(id="alt-green-before-flipping", kind="alternative",
                     name="Discharge the compute-boundary debts first, flip public green",
                     payload={"why":
                              "Ties the flip to unrelated engineering and, worse, "
                              "launches a ledger whose gates have never been seen red — "
                              "indistinguishable, to a stranger, from decoration."}),
                Node(id="alt-hide-the-ledger", kind="alternative",
                     name="Keep the ledger private and ship a README caveat instead",
                     payload={"why":
                              "A README caveat cannot fire — the exact pathology this "
                              "substrate exists to refuse, reintroduced at the front "
                              "door of the repo that argues against it."}),
            ],
        ),

        Node(
            id="the-history-ships-as-is",
            kind="decision",
            name="The public flip keeps the full git history — scrubbed and found clean, "
                 "no fresh root needed",
            params={
                "findings": Quantity(
                    value=0, unit="finding", provenance="verified", grounded=True,
                    source="full-depth scan over all 47 commits, 2026-07-17: token/key "
                           "patterns (AWS, GitHub, Slack, OpenAI, private keys, "
                           "password/secret assignments) zero hits; the only emails in "
                           "history are the public git identities; no local paths, no "
                           "personal names, no real-usage data in tests or fixtures"),
            },
            payload={
                "rationale":
                    "The issue reserved a fresh-root release for a dirty history. The "
                    "scan came back clean — the repo has carried synthetic fixtures from "
                    "the start — so the history's forty-seven commits of recorded "
                    "decisions are an asset a squash would destroy for nothing.",
            },
            children=[
                Node(id="alt-fresh-root", kind="alternative",
                     name="One squashed initial commit for the public release",
                     payload={"why":
                              "The right call when history is dirty — rewrite gymnastics "
                              "are worse — but a clean history squashed loses the "
                              "provenance of every decision for no gain."}),
            ],
        ),

        Node(
            id="the-host-surface",
            kind="gate",
            name="What quern's MCP host exposes to a caller",
            links={"admits": ["a-native-contract-is-unmetered",
                              "a-host-tool-runs-on-the-event-loop"]},
            payload={"note":
                     "RED, and correctly so. The host today hands any caller an unmetered "
                     "compute path that blocks the process it runs in. It goes green when "
                     "the two debts below it are discharged by doing the work — not by "
                     "editing this file."},
        ),
    ]
    return quern
