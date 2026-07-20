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
