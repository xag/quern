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

A later, unrelated slice sits near the end: the read-only navigator (`quern navigate`)
and the one decision it rests on — that it depends on no vocabulary of its own, only on
the ledger-package convention, because `build()` hands back a tree with its semantics
already composed in.

The last slice is the other half of the estate's day-one practice, arriving late and for the
same reason the first one did: quern shipped the ledger to everyone else and instrumented
nothing of its own. It now declares a nondeterminism boundary and records every CLI run. The
decision worth reading twice is the second — where the seam goes — because the obvious answer
produced a tape that looked healthy and could not be played, and only running a replay said so.
"""

from __future__ import annotations

import os
from pathlib import Path

import quern.grounding  # noqa: F401 — the natives; the package itself arrives by pin
from quern import SUPERSEDES, Quern, Node, Quantity
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
            id="the-fleets-owings-are-computed-never-authored",
            kind="decision",
            name="`quern estate` reads what a directory of projects owes itself out of their "
                 "own ledgers, and a project it cannot read is reported rather than skipped",
            payload={
                "why":
                    "A fleet accumulates work faster than any one project's brief shows, and "
                    "the reflex is to keep a list of it — a bucket, a roadmap, a scratch "
                    "ledger spanning the projects. That list is precisely the memory a "
                    "ledger exists to replace. It drifts the first time a debt is discharged "
                    "and nobody edits it, and then two records disagree with nothing to say "
                    "which is right. Every project already states what it owes, in a kind "
                    "built to carry it, beside the decision that incurred it. So the "
                    "cross-project view authors nothing: it walks a directory, runs each "
                    "ledger's own brief, and collects the debts still open and the entries a "
                    "rule holds red. Discharge a debt and it leaves the roll-up because it "
                    "left the ledger, which is the only way a roll-up stays true.",
                "note":
                    "Each ledger is read IN ITS OWN ENVIRONMENT, and that is the whole "
                    "difficulty: a ledger imports its project's code, projects do not share "
                    "a venv, and one of them cannot depend on quern at all (a package quern "
                    "depends on cannot depend back). Hence a short list of invocations tried "
                    "in order, and the module form before any console script — `uv run "
                    "quern` finds an executable on PATH when the project's own environment "
                    "has none, so a project that cannot answer appears to answer, through "
                    "whichever quern the CALLER had. It was caught doing that. The caller's "
                    "VIRTUAL_ENV is dropped for the same reason. Silence is the failure this "
                    "is built against: an unread ledger is printed under its own heading, "
                    "the exit status is non-zero, and the heading says in words that these "
                    "are not projects with nothing owed.",
            },
            children=[
                Node(id="a-cross-project-bucket-ledger", kind="alternative",
                     name="Author one temporary ledger spanning the sessions and the projects",
                     payload={"why":
                              "It is the obvious answer and it is a second source of truth. "
                              "The entries would be copies, the copies would go stale, and "
                              "the stale one would be the one anybody reads — a list is "
                              "easier to open than fifteen repositories, which is exactly "
                              "why it would be believed after it stopped being true. What "
                              "was actually missing was never a place to write things down; "
                              "it was a way to read what had been."}),
                Node(id="one-invocation-for-every-project", kind="alternative",
                     name="Require every project to answer the same command",
                     payload={"why":
                              "There is no such command. A project that cannot depend on "
                              "quern still has a ledger and still owes things, and demanding "
                              "uniformity would either exclude it from the fleet's view or "
                              "force a dependency cycle to keep it visible. The tool bends "
                              "instead, and reports which way it had to bend."}),
            ],
        ),
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
                meta={"amended": "18517c6ea31b wording only: aphorism replaced with a plain statement, claim unchanged"},
                     name="Keep the ledger private and ship a README caveat instead",
                     payload={"why":
                              "A README caveat triggers no check — the exact pathology this "
                              "substrate exists to refuse, reintroduced at the front door of "
                              "the repo that argues against it."}),
            ],
        ),

        Node(
            id="the-gate-fails-on-unaccounted-red-not-on-red",
            kind="decision",
            meta={"amended": "eeb7f54c2d34 wording only: aphorism replaced with a plain statement, claim unchanged"},
            name="A red the ledger accounts for is not a failure: the gate exits 1 on red "
                 "nobody expected, and on an expectation whose red has gone",
            links={"rests_on": ["the-red-ledger-ships-red"]},
            payload={
                "rationale":
                    "Shipping red by decision and gating on red are not compatible, and for a "
                    "year this repo did both: `ledger-gate` failed on EVERY run in its recorded "
                    "history. A check that has never once passed carries the same information "
                    "as one that always does — none — so a genuinely broken ledger arrives amid "
                    "the noise and looks routine. That is not hypothetical here: "
                    "flight-recorder's README gate shipped red on 2026-08-03 and stayed red for "
                    "ten days, because nobody could see a new red inside the old one. The exit "
                    "code was carrying two claims at once — 'something is unsound' and "
                    "'something is WRONG' — and only the second is a gate's business. The first "
                    "is the ledger's content.",
                "consequence":
                    "`reckon` sorts red into news, carried and stale. A red is carried "
                    "when the node it fires at names the rule in "
                    "meta['expected:<rule>'] — testimony where it is red, not a baseline "
                    "file listing yesterday's reds. That distinction is the design: a "
                    "baseline records that a red was there, never that it was meant to "
                    "be, so it launders an accident into an expectation the moment it is "
                    "regenerated, and it is an anonymous line to add when you want a red "
                    "to stop being news. The note is refused the moment its rule goes "
                    "green (`stale`, and fatal), so it cannot outlive its reason — "
                    "discharging a debt makes the check ask you to withdraw the licence "
                    "that excused it. Carried reds are still printed on a passing run, "
                    "marked red*.",
                "note":
                    "This REVISES the consequence clause of the decision it rests on, "
                    "which said a stranger's first meeting should be `ledger.check` "
                    "exiting 1. It is now `red* the-host-surface` at the top of a passing "
                    "report. The substance is untouched — the red still ships, still "
                    "shows, and is still not scrubbed — but the demonstration moved from "
                    "the exit code to the report, because the exit code had to be freed "
                    "to mean something a gate can act on. Left standing rather than "
                    "edited: a correction travels by supersession.",
            },
            children=[
                Node(id="a-committed-baseline-of-expected-reds", kind="alternative",
                     name="Record the red set in a file and fail when it differs",
                     payload={"why":
                              "Memory instead of testimony. It says a red was there "
                              "before, not that anyone meant it — and since it is "
                              "regenerated mechanically, the first run after an accident "
                              "adopts the accident. Hiding a red costs one anonymous line "
                              "in a generated file, where the note costs an edit to the "
                              "node that is red, in the ledger's own diff, with a reason "
                              "attached."}),
                Node(id="reds-a-gate-admits-are-expected", kind="alternative",
                     name="Derive the expectation from the tree: a red under a gate's "
                          "`admits` is the system working",
                     payload={"why":
                              "Confuses a red of an expected KIND with a red that was "
                              "expected. Every gate red in this estate is of that kind, "
                              "including the ones that are news — so it would excuse the "
                              "whole class and gate on nothing, which is where this "
                              "started."}),
                Node(id="two-exit-codes", kind="alternative",
                     name="Exit 1 for red-as-designed, 2 for red-that-is-new; CI keys on 2",
                     payload={"why":
                              "Still needs to know which reds are designed, so it answers "
                              "the reporting question and leaves the actual one open. And "
                              "it makes every other caller — a hook, a human, a script "
                              "wiring this into something else — learn a private "
                              "convention to ask 'did this pass'."}),
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
            id="the-navigator-is-vocabulary-blind",
            kind="decision",
            name="quern navigate serves whatever build() composed, and depends on no "
                 "vocabulary of its own",
            payload={
                "rationale":
                    "The read-only navigator (`quern navigate <project>`) renders any "
                    "project's ledger with no per-project wiring. It rests on ONE "
                    "convention, which is its whole contract: a project's ledger is the "
                    "package `ledger/` whose `tree.py` exposes an argument-free "
                    "`build() -> Quern`. build() calls `lib.effective(...)`, so the pinned "
                    "vocabulary package (ledger@, or any domain's) is already folded into "
                    "the tree it returns — kinds, prose and rules and all. The navigator "
                    "therefore supplies nothing: its starter_vocabulary is empty, and it "
                    "wraps the composed tree in a read-only Workspace that refuses every "
                    "write. Meaning arrives pre-resolved; the viewer stays domain-agnostic "
                    "and renders any vocabulary unchanged.",
                "note":
                    "The dependency runs one way: a project pins a vocabulary and resolves "
                    "it; the navigator consumes the result and never learns which package "
                    "it was. Because the ledger is a PACKAGE, `tree.py` may `from . import` "
                    "its siblings, so the loader imports `ledger.tree` as a package, not as "
                    "a lone file.",
            },
            children=[
                Node(id="alt-navigator-loads-tree-as-a-lone-file", kind="alternative",
                     name="Load ledger/tree.py by file path, with no package context",
                     payload={"why":
                              "The first cut, and it worked only for ledgers that import "
                              "nothing local. A real ledger is a package and its tree.py "
                              "does `from . import strategy`; loaded as a lone file it has "
                              "no __package__ and the relative import fails. The loader "
                              "must import it AS the package `ledger.tree`."}),
                Node(id="alt-navigator-needs-per-project-wiring", kind="alternative",
                     name="Each project wires its own Workspace and serves the navigator",
                     payload={"why":
                              "Defeats the point — one command against any ledgered repo, "
                              "no wiring. And it would make the viewer carry a live "
                              "Workspace or vocabulary it does not need: build() already "
                              "returns a composed tree, so a read-only wrapper is enough."}),
            ],
        ),

        Node(
            id="the-roll-digests-what-an-entry-says",
            kind="decision",
            name="The roll records a digest of every node's words — name, payload, and "
                 "each param's bare value — and nothing else",
            meta={"amended": "1daeb595ec52 wording only: the incident is described "
                             "without naming the consumer it happened in. The claim, "
                             "the rejected alternatives and the scope are unchanged."},
            payload={
                "rationale":
                    "Path and kind catch the rare erasures: deletion and re-kinding. The "
                    "common one keeps the id and rewrites the words — a consumer rewrote "
                    "a debt's premise in place and the check reported zero removals, "
                    "which is the incident that prompted this. So the roll now digests "
                    "what each entry SAYS, and `rewritten` fires when it changes. The correction "
                    "channel is supersession; a wording-only edit is acknowledged in the "
                    "node's own meta (`amended: <digest> <why>`), which excuses exactly "
                    "one content state and goes stale the moment the words move again.",
                "scope":
                    "Deliberately outside the digest: a param's grounding (provenance, "
                    "`grounded`, source) — discharging a debt is the one in-place act "
                    "the record sanctions, and its trace belongs to provenance; `meta`, "
                    "which is where the acknowledgement itself lives; and links, which "
                    "are lifecycle — a gate's `admits` grows with every release, and "
                    "digesting links would make routine growth indistinguishable from "
                    "erasure. A link quietly deleted to dodge a red rule is therefore "
                    "still invisible to the roll; that window is open, known, and "
                    "narrower than the one this closed.",
            },
            children=[
                Node(id="alt-digest-load-bearing-fields", kind="alternative",
                     name="Digest only named load-bearing payload keys (rationale, why, "
                          "claim)",
                     meta={"amended": "3f415985ae75 wording only: the same rewrite, "
                                      "described without the consumer's commit hash. "
                                      "The refutation is unchanged."},
                     payload={"why":
                              "Refuted by the incident it was meant to catch: the rewrite "
                              "moved `why_this_is_the_load_bearing_one` and a "
                              "discharge's `who` — authors name payload keys freely, so "
                              "any fixed list is a list of places NOT to write the lie. "
                              "And the list would be domain vocabulary hard-coded into a "
                              "domain-free module, or one more knob in every consumer's "
                              "check."}),
                Node(id="alt-an-amendment-kind", kind="alternative",
                     name="A new `amendment` node kind acknowledging each rewrite",
                     payload={"why":
                              "A third mechanism to remember, minted the very week the "
                              "apparatus was called 'a problem rather than a help'. The "
                              "acknowledgement needs no node: the amended entry itself "
                              "can carry it in meta, self-describing and self-expiring, "
                              "with tombstones' property — visible in the diff — for "
                              "free."}),
            ],
        ),

        Node(
            id="the-working-set-is-computed",
            kind="decision",
            name="Reading a ledger costs one line per current claim: the brief drops "
                 "what is superseded, and the tree keeps it",
            payload={
                "rationale":
                    "A ledger pays for itself only if reading it is cheaper than "
                    "re-deriving it, and by default every session paid the whole "
                    "history to find the dozen claims that still bind. `quern brief` "
                    "renders the working set - kind, id, name, links, ungrounded "
                    "params, red rules, one line each - and counts the archaeology "
                    "away instead of spending it. Depth is on demand: brief, then "
                    "tree_get, then source. The same seam serves the navigator: "
                    "tree_get now carries the reverse link index (`linked_from`) and "
                    "the not-current set, so every relation is navigable both ways "
                    "and the stale is dimmed, with the viewer still vocabulary-blind. "
                    "`said_words` prices a subtree in the rule language, so a "
                    "vocabulary can put a budget where the decay actually happens: "
                    "not lying, growing.",
            },
            children=[
                Node(id="alt-summarize-with-a-model", kind="alternative",
                     name="Have a model summarize the ledger on demand",
                     payload={"why":
                              "Costs the tokens it claims to save, differs run to "
                              "run, and drifts from the tree - a summary nothing can "
                              "check is prose again, which is the pathology this "
                              "substrate exists to abolish. The brief is computed, "
                              "deterministic, and asserts nothing the tree does not."}),
                Node(id="alt-keep-ledgers-small-by-writing-less", kind="alternative",
                     name="Solve reading cost by recording less history",
                     payload={"why":
                              "Throws away the record to save the reader, when the "
                              "cost was never keeping history - it was READING it by "
                              "default. Superseded entries and refuted hypotheses are "
                              "the part a later reader most needs to not re-litigate; "
                              "they should cost a trailer line, not their prose."}),
            ],
        ),

        Node(
            id="the-dev-bridge-is-the-tool-surface-not-a-copy-of-it",
            kind="decision",
            name="serve_dev registers the real tree_* tools and calls them; it no longer "
                 "re-implements the verbs it serves",
            payload={
                "rationale":
                    "The navigator runs over two transports — an MCP App, where the page "
                    "calls the genuine tools, and a localhost dev server for a plain "
                    "browser. The dev server used to answer `POST /rpc` from a hand-written "
                    "`_dispatch` that re-implemented each verb against the Workspace. Two "
                    "implementations of one surface, and the drift was not hypothetical: "
                    "`tree_solver` was added to the host and was simply ABSENT over HTTP, so "
                    "a panel that worked for the model hit 'unknown tool' in the browser; "
                    "and the two slice builders pruned differently, so the UI's "
                    "'has children' test answered differently depending which tool it "
                    "asked. Both were found by using the thing, which is the expensive way.\n\n"
                    "`serve_dev` now builds an in-process FastMCP, registers the real tools "
                    "on it, and dispatches into them. A verb the model can call is a verb "
                    "the browser can call, by construction rather than by diligence. What "
                    "remains transport-specific is one envelope adapter, which is the only "
                    "thing that ever differed honestly.",
                "note":
                    "The collapse exposed a bug in the OTHER direction, which is the "
                    "argument for it: FastMCP gives a `-> str` tool an output schema of "
                    "`{result: string}` and sends that wrapper as structuredContent, so over "
                    "a REAL MCP host the page — which reads `.text` — got nothing. The Check "
                    "tab rendered raw JSON and the outline's RED markers never appeared, in "
                    "the transport nobody was testing. `norm()` unwraps it now. Two "
                    "implementations do not merely drift; they make one of them the only one "
                    "anybody exercises.",
            },
            children=[
                Node(id="alt-keep-a-hand-written-bridge", kind="alternative",
                     name="Keep _dispatch and add the missing verbs to it as they appear",
                     payload={"why":
                              "The status quo, and it is a standing tax paid by whoever adds "
                              "a tool — payable in a place they have no reason to look, with "
                              "a failure that shows up only in the transport they did not "
                              "run. Every instance of this drift so far was found by a user, "
                              "not a test."}),
                Node(id="alt-drop-the-dev-server", kind="alternative",
                     name="Serve the navigator only as an MCP App and delete serve_dev",
                     payload={"why":
                              "Removes the duplication by removing the capability, and the "
                              "capability earns its keep: verifying the UI in a plain browser "
                              "is how it gets tested at all, and it needs no Apps-capable "
                              "client. Note which transport had the undetected bug — the one "
                              "this alternative would have kept."}),
            ],
        ),

        Node(
            id="tree-solver-reads-the-effective-tree-writes-the-stored-one",
            kind="decision",
            name="tree_solver inspects the effective tree and authors the stored one — the "
                 "two are not the same tree",
            payload={
                "rationale":
                    "A solver reaches a tree two ways: authored into it (tree_solver register, "
                    "landing in the writable stored tree) or pinned from a package (arriving "
                    "in the effective tree, immutable). Every semantics slice lists BOTH — "
                    "`semantics_at` reads effective — but tree_solver's inspect and list paths "
                    "read only `ws.quern`, the stored tree. So a package-pinned solver was "
                    "shown in a slice and then, asked about itself, answered 'no artifact'. "
                    "The read paths now consult effective, and the caller can inspect any "
                    "solver it can see. The write paths — register, remove — still act on "
                    "`ws.quern` alone, because a pin is content addressed by digest and this "
                    "verb has no business editing it; removing a pinned solver says so rather "
                    "than failing blankly.",
                "note":
                    "Surfaced by the navigator's Solvers panel: its 'how to call' fetches a "
                    "descriptor on click (the manual this substrate keeps off the navigation "
                    "path), and every solver it could show was pinned, so every fetch missed. "
                    "The dev bridge mirrors the same read-only shape.",
            },
            children=[
                Node(id="alt-tree-solver-stays-on-the-stored-tree", kind="alternative",
                     name="Keep tree_solver entirely on ws.quern; pinned solvers are "
                          "inspected some other way",
                     payload={"why":
                              "Leaves the tool that names itself the solver surface unable to "
                              "describe most solvers in a tree, and invents a second inspect "
                              "path for the pinned majority. The read/write split is the "
                              "smaller seam: one verb, two trees, each for the thing it is "
                              "for — authoring writes what is editable, inspection reads what "
                              "is there."}),
            ],
        ),

        Node(
            id="a-slice-says-what-may-run-on-it-not-how-to-call-it",
            kind="decision",
            name="Solvers reach the viewer with their scope and how they run; the contract "
                 "detail stays off the navigation path",
            payload={
                "rationale":
                    "`semantics_at` had composed solvers into every slice since it existed, "
                    "and the navigator destructured `{kinds, rules, undefined_kinds}` and "
                    "dropped them — so the viewer rendered two of the three things the host "
                    "hands it, and no project's solvers were visible anywhere in the UI. "
                    "That is a plain contradiction of the navigator's own claim to serve "
                    "whatever build() composed. There is now a Solvers tab.\n\n"
                    "Making it useful meant deciding what a solver's ENTRY is, versus its "
                    "manual. `reads` and native-vs-wasm are the entry: they answer what a "
                    "solver may see and where it runs, which is what makes it comprehensible "
                    "at a glance and, for native, is the exact distinction the compute "
                    "boundary turns on. `params_doc`, `fuel` and the blob sha are the manual "
                    "— and this dict rides on EVERY tree_get, which is the hot path for "
                    "navigation. Paying for documentation on every click to save one "
                    "tree_solver call is the wrong trade, so the manual is fetched, never "
                    "carried.",
                "note":
                    "A consequence worth stating because it reads as a bug: the host lists a "
                    "solver where it may RUN, filtering by `reads`, so one scoped to a branch "
                    "is absent at the root and appears on the way down. The empty state "
                    "distinguishes 'none reads this branch' from 'none exist' — the panel is "
                    "the only place a reader could tell those apart.",
            },
            children=[
                Node(id="alt-send-the-whole-solver-descriptor", kind="alternative",
                     name="Put the full SolverDef in every slice — params_doc, fuel, blob",
                     payload={"why":
                              "The tempting completeness, paid on every navigation click by "
                              "every consumer, to spare a caller one tree_solver. A slice's "
                              "semantics are for ORIENTATION; the moment they become "
                              "documentation they are a payload nobody reads and everybody "
                              "transfers."}),
                Node(id="alt-leave-solvers-out-of-the-viewer", kind="alternative",
                     name="Keep the viewer to kinds and rules; solvers are an authoring concern",
                     payload={"why":
                              "The status quo, and it was silent rather than deliberate — "
                              "nothing recorded a choice, the field was simply not "
                              "destructured. And it is false on its own terms: a rule "
                              "predicate may CALL a solver (this ledger's own gate does), so "
                              "a reader who cannot see solvers cannot see why a gate is red."}),
            ],
        ),

        Node(
            id="the-outline-groups-by-kind-and-refuses-to-nest-by-link",
            kind="decision",
            name="The navigator's outline buckets top-level entries by kind and carries the "
                 "brief's markers — and never nests by links",
            payload={
                "rationale":
                    "A ledger is a WIDE, SHALLOW tree: quern's own is 14 entries over 21 "
                    "children and exactly zero grandchildren, so the outline pane could "
                    "draw at most one level of indentation and correctly rendered a long "
                    "flat list. Faithful, and the least informative axis available — the "
                    "structure a ledger actually carries is in its LINKS (supersedes, "
                    "rests_on, admits), a graph laid over a deliberately flat index.\n\n"
                    "Two changes, both vocabulary-blind. Kinds become collapsible groups, "
                    "which is the only grouping a flat tree has and turns forty rows into "
                    "four. And each row now carries what the CLI brief has always put on "
                    "its line — `!ungrounded` params and RED rules — so the outline stops "
                    "being strictly less informative than the one-liner it mirrors.",
                "note":
                    "Group order is first-appearance, never alphabetical: authoring order "
                    "is information in a roughly chronological record, and re-sorting would "
                    "be a vocabulary-blind viewer asserting a precedence among kinds it is "
                    "forbidden to know. Rule verdicts come from parsing tree_check's report, "
                    "which is the weak seam — tree_get says nothing about red, and making it "
                    "would cost a full rule evaluation on every navigation.",
            },
            children=[
                Node(id="alt-nest-the-outline-by-rests-on", kind="alternative",
                     name="Give the outline real depth by nesting entries under what they "
                          "rest on",
                     payload={"why":
                              "The tempting one, and it forces a graph into a tree. Links "
                              "cycle, and one entry can be named by several — so a node "
                              "either appears many times or is silently dropped under one "
                              "arbitrary parent. An outline that duplicates or hides nodes "
                              "to look deeper is an outline that lies about the shape of "
                              "the record. Depth is the wrong instrument; the link panel "
                              "already navigates the graph in both directions."}),
                Node(id="alt-put-red-in-tree-get", kind="alternative",
                     name="Return rule verdicts from tree_get so the outline need parse "
                          "nothing",
                     payload={"why":
                              "Cleaner to consume and wrong to pay for: tree_get is the "
                              "navigation primitive, called on every click, and folding "
                              "run_rules into it would make browsing cost a check on a "
                              "tree whose rules may call solvers. The verdicts are fetched "
                              "once and refreshed when the user runs one."}),
            ],
        ),

        Node(
            id="the-working-set-is-a-tool-not-only-a-command",
            kind="decision",
            name="tree_brief puts the brief on the model surface, and returns the rendered "
                 "lines rather than structured data",
            payload={
                "rationale":
                    "The brief was reachable only from the CLI, so the one reader whose "
                    "cost the decision beneath this was written about — a model context — "
                    "was the one reader who could not get it. A model on the MCP surface "
                    "had to `tree_find(current_only=True)` and then `tree_get` each hit: "
                    "more round-trips and more tokens than the argument for the brief "
                    "implies. `tree_brief` is the same `brief()`, resolved over the "
                    "workspace's EFFECTIVE tree like every other read verb.\n\n"
                    "It returns TEXT, unlike tree_get and tree_find. The line is the "
                    "artifact: kind, path, name, links, ungrounded params and red rules, "
                    "already composed into the one line a reader pays for. Handing back "
                    "the same facts as JSON would ship the assembly instructions instead "
                    "of the assembly, and cost more tokens to say less — which is the "
                    "precise failure the brief exists to avoid.",
                "note":
                    "Scope held deliberately narrow: no `under` parameter. `brief()` walks "
                    "top-level entries, and giving the tool a branch scope means changing "
                    "what the brief IS, which is a bigger question than exposing it.",
            },
            children=[
                Node(id="alt-brief-returns-structured-output", kind="alternative",
                     name="Return matches as JSON, like tree_get and tree_find",
                     payload={"why":
                              "Consistent with its neighbours and wrong for this verb. The "
                              "brief's value is the RENDERING — one line, already reduced; "
                              "a model handed the fields back would have to re-render them "
                              "to read them, paying twice for the reduction that was the "
                              "point."}),
                Node(id="alt-leave-the-brief-on-the-cli", kind="alternative",
                     name="Leave it a CLI command; models can compose tree_find and tree_get",
                     payload={"why":
                              "That composition is what the brief was built to replace, and "
                              "it costs a round-trip per entry. Leaving it CLI-only serves "
                              "the human reader while the argument for it was written about "
                              "the model one."}),
            ],
        ),

        Node(
            id="the-substrate-records-its-own-runs",
            kind="decision",
            name="quern declares a nondeterminism boundary and records every CLI run, "
                 "on by default",
            payload={
                "rationale":
                    "The estate's practice is to name the boundary as a project's first "
                    "artifact and record from commit one, so a bug is replayed rather than "
                    "re-derived. quern had shipped the ledger half of that practice to "
                    "every other project and kept neither half itself — a survey found it "
                    "among the repos with a ledger and no recorder. The boundary is "
                    "`src/quern/boundary.py`; `quern.replay` plays a tape back.\n\n"
                    "Recording is ON by default (`QUERN_FLIGHT=0` opts out) because a "
                    "recorder that must be remembered is a recorder that was off on the run "
                    "that mattered — and the tapes cost a few KB into `.quern/`, which is "
                    "already ignored as the synced-package cache.",
                "note":
                    "The boundary turned out to be four things, and naming what is ABSENT "
                    "was the more useful half: quern reads no clock and draws no randomness. "
                    "Identity here is a content digest, never a timestamp or a nonce, which "
                    "is exactly why a pin is reproducible. A clock read appearing in this "
                    "codebase is a design event before it is a recording gap.",
            },
            children=[
                Node(id="alt-flight-recorder-as-a-dev-dependency", kind="alternative",
                     name="Depend on the recorder in the dev group and record only in tests",
                     payload={"why":
                              "Recording that happens only in development is recording that "
                              "is absent from every run a user could report — which is the "
                              "one population of runs nobody can reproduce by hand. It is a "
                              "runtime dependency for the same reason the practice exists."}),
                Node(id="alt-no-recorder-quern-is-deterministic", kind="alternative",
                     name="Skip it: quern is nearly a pure function over a directory",
                     payload={"why":
                              "True, and it is the argument FOR instrumenting rather than "
                              "against — a boundary this narrow costs four declarations and "
                              "makes every run replayable. 'Deterministic given its inputs' "
                              "is precisely the claim a tape lets somebody check, and the "
                              "inputs are a directory another tool wrote."}),
            ],
        ),

        Node(
            id="the-boundary-sits-at-text-not-at-the-package-api",
            kind="decision",
            name="The seam is `read_text`/`write_text`, not `Library.get`/`publish` — a tape "
                 "may hold only what it can represent",
            payload={
                "rationale":
                    "The first cut wrapped the obvious API: `Library.get`, `Library.publish`, "
                    "`read_lock`, `write_lock`. It recorded, the counts were right, and every "
                    "result on the tape was `{\"__opaque__\": \"PackageRef(...)\"}` — because "
                    "the format holds primitives and containers, and a pydantic model is "
                    "neither. Such a tape replays the repr STRING into code expecting an "
                    "object. It would have looked healthy and reproduced nothing.\n\n"
                    "One level down the world's answer is a JSON string, which the tape holds "
                    "exactly. Feed it back and `model_validate_json` — quern's own code — "
                    "rebuilds what it built the first time. This is the cardinal rule read "
                    "carefully: parsing is not the boundary, it is the code under test, and "
                    "recording it hides the thing a replay exists to re-run.\n\n"
                    "The same reasoning moved the recorded CALL from the five `_cmd_*` verbs "
                    "to `run(argv)`. A verb takes an `argparse.Namespace`, opaque for the same "
                    "reason; an argv is a list of strings. So the tape now holds literally the "
                    "command that was typed, and parsing happens inside the replay.",
                "consequence":
                    "`read_text` returns `str | None` with the existence check folded in — "
                    "absence is an ANSWER, and a boundary that recorded only contents would "
                    "send a replay back to the real filesystem to ask whether a file was "
                    "there. `tests/test_flight.py` pins all of it by PLAYING a tape rather "
                    "than inspecting its shape: it asserts no result is opaque and that a "
                    "recorded `quern brief` replays bit-for-bit.",
            },
            children=[
                Node(id="alt-record-the-package-api", kind="alternative",
                     name="Record `Library.get`/`publish` — the meaningful-looking seam",
                     payload={"why":
                              "Refuted by running it: every result recorded as an opaque "
                              "repr, so the tape was unreplayable while every count on it "
                              "looked correct. The failure is silent, which is what makes it "
                              "worth a ledger entry rather than a comment."}),
                Node(id="alt-teach-the-recorder-about-pydantic", kind="alternative",
                     name="Serialize models by teaching the tape a pydantic codec",
                     payload={"why":
                              "Puts quern's type system inside a library whose whole doctrine "
                              "is that it knows no semantics, to record something quern can "
                              "already rebuild from the text it was parsed out of. The fix "
                              "belongs at the seam, not in the recorder."}),
            ],
        ),

        Node(
            id="a-solver-blob-records-opaquely",
            kind="debt",
            name="wasm blobs cross the boundary as bytes, and the tape cannot hold bytes",
            params={"replayable": _unsound(
                0, "effect",
                "`solver_blob` is declared in the boundary and records as "
                "{\"__opaque__\": \"<repr>\"} — the tape format represents str, not bytes. "
                "Text effects: fully replayable. Blob effects: zero.")},
            payload={"note":
                     "Every text path through quern replays bit-for-bit; a run that loads a "
                     "solver does not, because the recorded blob replays as a repr string "
                     "rather than a module. Narrow today — `brief`, `pin`, `sync` and "
                     "`navigate` touch no blob — and it will stop being narrow the moment a "
                     "solver bug is the one somebody needs to replay.",
                     "found": "2026-07-19, while proving the first tape replayable; the same "
                              "opacity that condemned the package-API seam, in the one place "
                              "moving the seam cannot fix it, because bytes are what the "
                              "world actually hands over."},
            children=[Node(
                id="record-blobs-by-digest", kind="discharge",
                name="Record a blob as its sha256 and let replay load the content from the "
                     "content-addressed store the digest already names",
                payload={"who": "anyone who can change quern's boundary declaration — the "
                                "content is immutable and already keyed by that hash, so "
                                "the tape needs to carry the key, not the bytes"})],
        ),

        Node(
            id="every-checkable-claim-ships-with-its-proof",
            kind="decision",
            name="Publication refuses a rule with no counter-example, and a contract "
                 "with no demonstrations",
            payload={"why":
                     "The proof gate is what answers the objection against authoring "
                     "meaning locally at all — that cheap semantics is a thousand private "
                     "vocabularies nobody can trust. It was not carrying that weight. An "
                     "unrefuted rule published with a log line, and a solver published on "
                     "its prose alone: the same vacuity twice. A gate reading "
                     "`solve('grounding/untrusted', self) == 0` cannot tell a contract "
                     "that counts guesses from one that returns 0, and reads green either "
                     "way. Every rule now needs the node it must refuse; every executable "
                     "contract needs demonstrations, at least two expecting DIFFERENT "
                     "answers, which is what tells a computation from a constant.",
                     "consequence":
                     "Cost nothing in the registry - every published package already had "
                     "full counter-example coverage, so the discipline existed and only "
                     "the enforcement was missing. It cost the test fixtures, which is "
                     "the tell: the toy packages were the ones skipping the proof."},
            children=[
                Node(id="alt-keep-the-warning-in-the-proof-log", kind="alternative",
                     name="Leave it as it was: a log line counting the rules that carry "
                          "no counter-example",
                     payload={"why":
                              "A warning is read by whoever already cares, and a package "
                              "that skipped the proof is precisely one whose log nobody "
                              "reads. It also made the README false, which is how it was "
                              "found."}),
                Node(id="alt-the-package-carries-a-natives-proof", kind="alternative",
                     name="Let the package declaring a native contract ship that "
                          "contract's demonstrations, like a blob's",
                     payload={"why":
                              "Symmetric, and wrong for the reason a gate cannot be handed "
                              "its own grounding: a native is the host's own code running "
                              "outside the sandbox, and whoever republished the package "
                              "could soften the proof of code they do not ship. The spec "
                              "registers beside the implementation; a package may ADD "
                              "scenarios, never replace them."}),
            ],
        ),

        Node(
            id="a-kind-may-ship-with-nothing-that-is-one",
            kind="debt",
            name="Vocabulary is the one kind of knowledge publication still takes on "
                 "trust",
            params={"demonstrated": _unsound(
                0, "kind",
                "Nothing requires a package's kinds to appear in its own examples: a "
                "word can enter the library with no referent.")},
            payload={"note":
                     "Prose genuinely cannot be gated - a reader judges what a kind "
                     "MEANS. But whether any example IS a node of that kind is "
                     "mechanical, and it goes unchecked, so the failure the whole gate "
                     "exists to prevent - inventing words - is the one it does not "
                     "catch. Not closed now because grounding@ ships a kind that is "
                     "explicitly a convention pack and not a node kind at all; requiring "
                     "an instance would mean authoring a lie to satisfy a gate.",
                     "found": "2026-08-01, while making the other two obligations bind."},
            children=[Node(
                id="let-a-kind-say-it-is-a-convention", kind="discharge",
                name="Give KindDef a way to declare itself a convention rather than a "
                     "node kind, then require an instance of every kind that is not",
                payload={"who":
                         "anyone adding the field to KindDef - the check is a few lines "
                         "once a kind can say which sort it is, and the only reason it "
                         "is not written is that today it would refuse a package that "
                         "is correct"})],
        ),

        Node(
            id="a-kind-is-a-word-something-is",
            kind="decision",
            name="A package's kinds must be instantiated by its own examples, and a "
                 "namespace entry says so and is held to naming nothing",
            links={SUPERSEDES: ["a-kind-may-ship-with-nothing-that-is-one"]},
            payload={"why":
                     "The debt above was right that a kind's MEANING cannot be gated - "
                     "prose is judged by a reader. It was wrong that this left nothing "
                     "to check. Whether anything in the package IS one is mechanical, "
                     "and it is precisely the failure the gate exists against: a word "
                     "entering the library with no referent. KindDef gains `convention`, "
                     "for an entry that names a namespace its contracts hang prose on. "
                     "The flag is held BOTH ways - a kind that is not a convention must "
                     "be instantiated, a kind that says it is one must be instantiated "
                     "by nothing - because an exemption anybody could flip would read "
                     "as a check while being none.",
                     "consequence":
                     "Measured before it was written: of the packages in the registry "
                     "carrying vocabulary, all but the namespace-only ones already "
                     "complied, so the flag is not a workaround for the check but the "
                     "shape the content already had. Versions are immutable, so the "
                     "packages that predate the field are republished rather than "
                     "edited, and every tree pinning the old ones repins when it takes "
                     "this revision of the substrate. That cost is the doctrine working, "
                     "not a surprise: exact versions, fork-or-republish, no ranges."},
            children=[
                Node(id="alt-infer-the-convention-from-an-empty-shape", kind="alternative",
                meta={"amended": "543897afd042 wording only: aphorism replaced with a plain statement, claim unchanged"},
                     name="Treat a kind that declares no params, no links and no "
                          "operations, and that nothing instantiates, as a namespace",
                     payload={"why":
                              "Needs no new field and would have cost no republication. "
                              "Rejected because it is inference, and it excuses exactly the "
                              "case being caught: a real node kind that happens to document "
                              "nothing would be silently forgiven, which is a check that cannot "
                              "catch the thing it exists for."}),
                Node(id="alt-let-a-counter-example-count-as-an-instance", kind="alternative",
                     name="Accept a kind demonstrated only by the node a rule must reject",
                     payload={"why":
                              "A defect is not a referent. A kind whose only appearance "
                              "in the package is the thing a rule refuses has never been "
                              "shown sound, and sound is what a consumer of the "
                              "vocabulary is being handed."}),
                Node(id="alt-a-flag-that-only-exempts", kind="alternative",
                     name="Let `convention=True` simply switch the check off for that kind",
                     payload={"why":
                              "The obvious shape, and the reason the debt sat open: it "
                              "makes the gate advisory for anyone willing to type the "
                              "flag. Holding the claim both ways costs nothing and makes "
                              "the declaration falsifiable."}),
            ],
        ),

        Node(
            id="the-recorder-is-upstream-and-the-circle-is-not-closed",
            kind="decision",
            name="quern depends on the recorder at runtime, and the recorder's own checkout "
                 "therefore cannot install quern - which is correct, not a defect",
            links={"rests_on": ["the-substrate-records-its-own-runs"]},
            payload={"why":
                     "The decision above makes recording a runtime dependency: a recorder that "
                     "only runs in development is absent from the run somebody reports. That "
                     "puts xag-flight-recorder under quern permanently, and in exactly ONE "
                     "checkout - the recorder's own - the dependency comes back around. uv "
                     "needs one URL per distribution and is offered two, the editable root and "
                     "quern's git pin, so it refuses. Nothing is wrong. A recorder cannot "
                     "record itself, any more than an eye can see itself: the recorder is the "
                     "sensory system, this substrate is the cortex, and the arrow points one "
                     "way. The resolver error is that fact arriving as a diagnostic.",
                     "consequence":
                     "The recorder keeps its own quern-authored ledger and runs the check OUT "
                     "of its project environment, where the root package is not installed and "
                     "there is nothing to collide with. It costs that repo one unusual command "
                     "and costs this one nothing. Recorded here rather than there because the "
                     "constraint is created by THIS package's dependency, and a reader who "
                     "meets the error will look for its cause upstream."},
            children=[
                Node(id="alt-make-the-recorder-an-extra", kind="alternative",
                     name="Ship recording as an optional extra so nothing depends on it by "
                          "default",
                     payload={"why":
                              "Dissolves the circle completely, and guts the reason for it. "
                              "Recording that a consumer opts into is recording that was off "
                              "on the run that mattered - the same argument that makes "
                              "QUERN_FLIGHT default to on. Trading the guarantee for a "
                              "resolver's convenience in one checkout is the wrong way round."}),
                Node(id="alt-delete-the-recorders-ledger", kind="alternative",
                     name="Let the recorder drop its design ledger, since it cannot install "
                          "the thing that checks it",
                     payload={"why":
                              "It is not a stub: it carries that project's six-runtime "
                              "decisions with the alternatives they rejected, behind gates "
                              "that can go red. Deleting a record to silence a resolver is the "
                              "trade this whole substrate exists to refuse."}),
                Node(id="alt-declare-a-workspace-member", kind="alternative",
                     name="Point the recorder's dependency at its own workspace member so uv "
                          "sees one source",
                     payload={"why":
                              "Tried, and it does not work: this package's git pin travels "
                              "inside its metadata, so no source declaration downstream can "
                              "outrank it. The variant uv does accept resolves by dropping "
                              "quern from the group entirely - a green command that installs "
                              "nothing, which is worse than the error it replaced."}),
            ],
        ),

        Node(
            id="the-host-surface",
            kind="gate",
            name="What quern's MCP host exposes to a caller",
            links={"admits": ["a-native-contract-is-unmetered",
                              "a-host-tool-runs-on-the-event-loop"]},
            # The prose below says this is red on purpose; this says it to the CHECK, by
            # rule name, so a SECOND red arriving here is news instead of more of the
            # same. It is refused the moment the two debts are discharged and the rule
            # goes green — the note cannot outlive its reason and become a licence.
            meta={"expected:nothing-unsound-passes-a-gate":
                  "the two debts it admits are ungrounded, which is this gate doing its job"},
            payload={"note":
                     "RED, and correctly so. The host today hands any caller an unmetered "
                     "compute path that blocks the process it runs in. It goes green when "
                     "the two debts below it are discharged by doing the work — not by "
                     "editing this file."},
        ),

        Node(
            id="the-breadth-is-on-the-record",
            kind="decision",
            name="What each adopter domain demanded of the substrate, and what each "
                 "worked around, surveyed across eleven repos and written down here — "
                 "with every workaround filed as an issue instead of bending a domain",
            payload={
                "why":
                    "2026-08-19. The breadth existed but the record did not, and "
                    "external adoption of one adopter's vocabulary (craft-laws) must "
                    "not freeze a core the other domains still pull on. What the "
                    "domains demanded and GOT, without forking the core: invest — "
                    "payload exprs as path-pinned rules over time-series windows; "
                    "home — provenance as a cut gate, derived branches, an evidence "
                    "integrator; geometry — relational contracts with refusal "
                    "demonstrations; epure — a prover landing grounded artifacts a "
                    "gate refuses; vigil — cadenced criteria with gap as an outcome; "
                    "assay — ledger@'s gate refusing an ungrounded verdict from a "
                    "vocabulary it never met; mindmap — a live writer with "
                    "current-belief projection; transponder — a gate red on purpose. "
                    "Vocabulary, packages, natives, gates and Quantity carried all of "
                    "it: the domain-neutrality argument, checkable here.",
                "worked_around":
                    "Seven walls, each hit by more than one domain, each filed with "
                    "its receipts: exprs not first-class (#44), payload unreadable by "
                    "the grammar (#45), links untraversable (#46), natives by import "
                    "side effect with implementations outside the digest (#47), no "
                    "exported gate runner (#48), refusal-swallowing in-process "
                    "publish (#49), kindless intermediates silently unbinding rules "
                    "(#50). Already carried, so unfiled: the unmetered blocking "
                    "native, and convention=True as the admission that event streams "
                    "have no typed home.",
                "weakest":
                    "mindmap: no pin, no lock, no registry, no ledger, swallowed "
                    "publish failures, central checks outside the substrate. Its own "
                    "loudest demand is #46 — link traversal — and that, not an "
                    "interface-law analogy, is the deepening it is owed next.",
            },
            children=[
                Node(id="alt-survey-from-memory", kind="alternative",
                     name="Write the breadth argument from what the maintainer recalls",
                     payload={"why":
                              "Memory produced the situation being corrected. Three "
                              "readers swept the repos; every claim carries a "
                              "file-level receipt in the issue it points to."}),
                Node(id="alt-fix-instead-of-file", kind="alternative",
                meta={"amended": "4eab374bcb6e wording only: aphorism replaced with a plain statement, claim unchanged"},
                     name="Fix the seven walls in one pass instead of filing them",
                     payload={"why":
                              "Each is a substrate release with a pin cascade across a dozen "
                              "adopters; seven at once turns a survey into an incident."}),
                Node(id="alt-bend-the-domains", kind="alternative",
                     name="Ask the domains to restate their demands in what the "
                          "grammar already says",
                     payload={"why":
                              "The freeze this survey exists to prevent: the census "
                              "shows the other domains already paying that tax."}),
            ],
        ),

        Node(
            id="the-obvious-predicates-are-computed-never-remembered",
            kind="decision",
            meta={"amended": "448633e1f876 the founder pushed back twice the "
                             "same day: first the floor tier became generated, "
                             "then the schema set stopped being a judgment "
                             "call - the grammar verb table joined the "
                             "metamodel as the second walked denominator"},
            name="`quern owed` derives the expected-predicate matrix from a "
                 "vocabulary - every declared param and link implies its obvious "
                 "rule - and computes which cells the rules cover, with the owed "
                 "remainder named",
            links={"rests_on": ["the-breadth-is-on-the-record"]},
            payload={
                "why":
                    "The obvious laws are exactly the ones nobody writes down. "
                    "Every adopter that authored them stopped somewhere with no "
                    "record of the stop: invest ruled its thesis params and left "
                    "noise-band's k unread; mindmap ruled a claim's confidence "
                    "and left four links unread. A KindDef already DECLARES the "
                    "shape, so the expectation is generable: a K states its p, "
                    "what a K's L points at still stands. The matrix generates "
                    "the EXPECTATION and deliberately not the rules - an "
                    "existence check is free but a range or a link's meaning is "
                    "the domain's. Amended the same day, on the founder's push: "
                    "the FLOOR half of every owed cell IS generable without "
                    "guessing — presence for a param (states), no holes for a "
                    "link (dangling == 0) — so floor() emits those as rule data "
                    "with the refuting node each must reject, for owed cells "
                    "only, and an authored rule retires its floor at "
                    "regeneration. Only the sharpening (ranges, tolerances, "
                    "meanings) stays authored. And the generator is held "
                    "complete against TWO enumerable denominators, both walked "
                    "by tests: the metamodel (every KindDef field mapped to a "
                    "predicate family or exempted with its reason) proves every "
                    "declaration is read, and the grammar's own verb table "
                    "(every env verb a floor the generator emits, or an "
                    "exemption with its reason) proves the schema set is not a "
                    "judgment call - what a declaration can imply is bounded by "
                    "what the grammar can ask, and a verb landing in the "
                    "grammar breaks the generator until its floor is decided "
                    "out loud. Outside both denominators sits what is neither "
                    "declared nor expressible; that rim is named, never "
                    "enumerated - refusal (epure's totality) and the census "
                    "against external corpora are its instruments. Coverage is "
                    "by mention over expr source, "
                    "legitimate in the core that owns the grammar (#44's day "
                    "makes it an AST walk). First runs: mindmap 2/7, invest 4/9 "
                    "- and assay answers 'nothing is implied', a finding about "
                    "its kinds declaring shape in prose instead of data.",
            },
            children=[
                Node(id="alt-generate-the-rules", kind="alternative",
                     name="Emit the missing rules themselves, not the worklist",
                     payload={"why":
                              "Existence checks alone would go green while the "
                              "range, tolerance or meaning stays unstated - "
                              "green that means nothing, minted at scale."}),
                Node(id="alt-leave-it-to-authors", kind="alternative",
                     name="Trust each package author to enumerate their own "
                          "obvious rules",
                     payload={"why":
                              "The survey shows every author stopping somewhere "
                              "silently; a computed denominator is the same "
                              "cure coverage was for surfaces and strings."}),
            ],
        ),

        Node(
            id="the-weakest-domains-demand-lands-first",
            kind="decision",
            name="The grammar learns to traverse links — linked, linked_current, "
                 "backlinked — because the weakest live domain's own loudest demand "
                 "(#46) comes before any interface-law analogy",
            links={"rests_on": ["the-breadth-is-on-the-record"]},
            payload={
                "why":
                    "mindmap's open-tension check lived in a parallel Python engine "
                    "whose findings cannot go red in tree_check and cannot travel "
                    "with a package — because no rule could range over a node's "
                    "links at all. Three verbs in the unsupported shape close the "
                    "core of it: linked (targets that resolve — dangling stays "
                    "unsupported's finding), linked_current (a tension superseded "
                    "away is worked, not open), backlinked (who points at me). Each "
                    "is driven through run_rules in its tests, because a verb the "
                    "grammar cannot reach is not an answer to #46. Deliberately NOT "
                    "closed: reading a link's meaning, list comprehension in exprs, "
                    "and self-reference tests — the issue stays open for what a "
                    "second consumer actually demands.",
            },
            children=[
                Node(id="alt-a-links-native", kind="alternative",
                     name="Ship link traversal as a native contract in a package",
                     payload={"why":
                              "A native is host code a consumer must install and "
                              "import; a traversal is structural, exactly what the "
                              "env's own verbs are for — unsupported already "
                              "follows links there."}),
                Node(id="alt-wait-for-a-second-consumer", kind="alternative",
                     name="Leave #46 unimplemented until a second domain demands it",
                     payload={"why":
                              "Two domains already did: mindmap's parallel checker "
                              "and epure's relation demoted to a child node. The "
                              "second consumer clause now governs what MORE #46 "
                              "gets, not whether it starts."}),
            ],
        ),
    ]
    return quern
