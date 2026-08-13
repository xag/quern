# quern

**Meaning does not have to be formal to be actionable.** quern is a Python substrate for trees whose semantics are written in prose, at the node that needs them, while the work is happening — where rules go red on the node that breaks them, and nothing reaches anybody else without the evidence for what it claims.

## Why: knowledge that moves as fast as the work

Designing anything takes three kinds of knowledge — **semantics** (what the things mean), **models** (what must hold between them), **solvers** (what computes over them). Until now you could write them down cheaply, or you could make them actionable. Not both.

Cheap is a document, a spreadsheet, a wiki. A new column, a new heading, a new paragraph costs seconds and needs nobody's agreement — which is why most of what a team knows lives there. What you cannot do is get anything to act on it. A spreadsheet computes over the numbers and knows nothing about what they are: the column name is a string, the rule you had in mind is a comment or nothing at all, and a figure somebody guessed in a meeting sits in a cell that looks exactly like the one that was measured. It travels well enough — a spreadsheet is the most effective thing most organisations have for moving knowledge around — but it travels as a copy, carrying no evidence that any of it holds and no version anybody can pin, so the copy and the original drift apart and nothing anywhere says they have.

Actionable meant formal. Give a machine a schema, a type system, an ontology, and it can validate, infer, compute, and exchange with a team on another continent that never met you. The price is the formalizing: the terms have to be settled before anybody uses one, by whoever owns the definitions, and extending them means going back to that owner and waiting.

The shared model is that second road taken as far as it goes — one ontology, one canonical schema, authored up front and handed to everyone else. Sometimes it works, and it is worth being precise about when. SNOMED CT and the Gene Ontology are maintained by permanent institutions over domains whose subject matter exists independently of any project — a disease and a gene are there whether or not you are modelling them today — and both are load-bearing infrastructure for entire fields.

The failures share the opposite shape, and they are not small. HL7 v3 spent a decade building a canonical Reference Information Model for health information; implementers largely would not adopt it, and FHIR exists because the industry needed something it could actually build against. Cyc spent forty years encoding common sense into one consistent ontology and never reached the general reasoning it was for. The Semantic Web's vision of universal linked ontologies produced, in the end, mostly schema.org — small, pragmatic, and nothing like the plan. In each case the ambition was to finish the vocabulary before the work, and in each case the vocabulary was itself part of what was being worked out.

Not because formalism is wrong — a schema that fits its subject is a gift, and the two above are proof of it. Because formalizing had to come **first**, and the work is what teaches you the words. You find the distinction that turns out to matter halfway through; you find the rule you should have had just after something has broken for want of it. A vocabulary that must be finished before the work can only be finished before anyone knows what it is for.

**What changed is not that meaning got cheaper to write down. It is that meaning no longer has to be formal to be actionable.**

A model needs no reduction to structure at all. It reads the sentence a practitioner would have written anyway — *something known-unsound, carried deliberately, with its cost stated rather than forgotten* — and acts on it: finds the nodes that are one, tells you which of them are unpaid, refuses to let one past a gate. Nothing was formalized. So semantics can be prose, and prose can be partial where the work is partial, provisional where the thinking is provisional, invented on the spot and sharpened the next time somebody reads it.

That is why this substrate interprets none of it. What must be mechanical is kept deliberately narrow — whether a value is grounded, whether a rule holds on a node, whether a package demonstrated its claims, what a digest says — and everything that must be *meaningful* stays in language, where it can be argued with and rewritten. So semantics, models and solvers are **authored on the go**, while the design is happening, by the intelligence sitting *at* the work: not centralized in the heads of the people who once specified the system, and not frozen in its code — distributed, like a squid whose intelligence lives in its arms and can regrow, rather than commanded from a single brain. Meaning is written at the node that needs it, the moment it is needed, and kept.

Which buys a new failure, and it is the obvious objection: cheap local meaning is a thousand private vocabularies that never converge — everyone inventing words, nobody able to read anyone else's tree. **The proof gate is the answer to it, and it is the load-bearing part of the design.** Local content costs nothing and binds nobody: invent whatever word the work needs. Leaving the local tree costs evidence. A rule enters a package only if the package's own examples exercise it and pass, and only if a counter-example staged alone makes it fire — because every rule here passes its examples, and so does `1 == 1`. A contract enters only if it has been shown answering worked cases, at least two of them expecting different answers, since a gate reading `solve(…) == 0` cannot otherwise tell a contract that counts from one that returns zero. What ships is pinned by digest at an exact version, so adopting it is a fork rather than a negotiation, and the diamond that would force one is refused at pin time.

So quern does not replace the shared model — it changes what one costs to make and what it costs to be wrong: **small, local, provable and disposable**, in place of central, permanent and therefore unreachable. Innovation and capitalization become organic by design — every endeavor is a research project that is operative on the go, and the boundary between research and operations disappears, because the model you reason with *is* the model you run.

## What quern is

A **Quern** is a tree of nodes, plus the semantics that give it meaning: a vocabulary saying what each kind of node means, rules that must hold over it, and solvers that compute across it. All three are data — registered at runtime, per tree, by whoever designs there — which is why the code can interpret none of them and be mechanics and safety only.

- **A node** carries a free-text `kind`, params where every number is a `Quantity` (its unit, where it came from, and whether it is grounded), named links, an opaque payload, and children.
- **A vocabulary entry** is a name and a paragraph of prose. Nothing parses it.
- **A rule** is one expression in a small safe language, bound to a kind or to a path, which goes red on the exact node that violates it.
- **A solver** is a sandboxed module that *proposes* values, stamped with the hash of the code that produced them, and never writes the tree itself.
- **A package** is all of that, versioned and pinned by digest — and it can only be published through the proof gate.

That is the whole model. [The detail is below](#the-model-in-detail); everything between here and there is what it looks like in use.

## What people build with it

Four trees that sit about as far apart as they can, each the same three ingredients in different clothes — because the domain supplies the words, and the substrate supplies none of them:

- **A design ledger.** Kinds: decision, debt, hypothesis, gate. Rules: a decision names at least one alternative it rejected; a debt names how it is discharged; nothing unsound passes a gate. This is the tree quern keeps about itself, and the one shown below.
- **A research notebook.** Kinds: thesis, kill-criterion, confirming-signal. Rules: a belief carries at least one observation that would falsify it; a conviction is a probability. Contracts compute over a data window, so a criterion is watched rather than remembered.
- **A survey of a place.** Kinds: space, opening, boundary. Every dimension carries whether it was measured or estimated, so a rule can refuse to let anything be cut against a guess, and contracts solve the geometry the measurements leave under-determined.
- **A specification of a running system.** Kinds: promise, and the evidence that enforces it. Rules: a promise claiming to be proven must name what proves it — so a sheet of claims can be checked against the artifacts underneath instead of believed.

None of those vocabularies is quern's, and the substrate knows nothing of any of them. They are shapes, not products: each is a package of kinds, rules and contracts, authored in its own repository and pinned by digest like any other content.

## Read a tree

```bash
git clone https://github.com/xag/quern && cd quern && uv sync
```

The core needs only pydantic and wasmtime. The MCP host and the navigator need one extra: `uv sync --extra host`.

The tree most projects meet first is a **design ledger**: the decisions a codebase rests on with the alternatives they rejected, the debts it carries on purpose, the hypotheses still open, and the gates that refuse to go green while a debt is unpaid. Two commands open one, and neither needs any per-project wiring.

**`quern brief`** — one line per claim that still binds:

```bash
uv run quern brief             # the ledger of the current directory
uv run quern brief path/to/project
```

```
quern - ledger brief
[decision]  native-contracts-bypass-the-sandbox  —  A package may ship a first-class contract that does not run in wasm  {2 alternative}
[debt]  a-native-contract-is-unmetered  —  run_native grants no fuel, no memory cap and no clock  !meter  {1 discharge}
[debt]  a-host-tool-runs-on-the-event-loop  —  A CPU-bound tool makes the whole host deaf for its duration  !concurrency  {1 discharge}
[hypothesis]  heavy-compute-is-a-proposer-never-a-judge  —  A contract that is expensive never needs to be authoritative  {1 falsification}
...
[gate]  the-host-surface  —  What quern's MCP host exposes to a caller  admits->a-native-contract-is-unmetered,a-host-tool-runs-on-the-event-loop  RED(nothing-unsound-passes-a-gate)

21 entr(y/ies), ~5546 words of prose.
omitted as no longer current: 1 debt (the tree keeps them; --all shows them).
```

Every marker on a line is read off the node, never annotated by hand. `!meter` names a param that is **not grounded** — the unsound value the entry is carrying, and precisely what a gate reads to refuse. `admits->…` are the node's links, `{2 alternative}` counts its children by kind, and `RED(…)` names the rule failing on it.

Superseded entries are counted away rather than printed, with a trailer saying what was omitted; the tree keeps them and `--all` prints them marked with what superseded them. `--fat` appends each entry's wordcount and sorts by it, heaviest first — the curation view, where the first line is the first thing to tighten.

A model reads it the same way: `tree_brief` serves exactly this over MCP, with the same two flags. It is the table of contents and `tree_get` is the chapter — reading a tree by `tree_get('')` spends its whole history to find the dozen claims that still bind, which is the cost the brief exists to refuse.

**`quern navigate`** — the same tree in a browser, read-only:

```bash
uv run quern navigate          # serves http://localhost:8765 and opens it
uv run quern navigate path/to/project
```

Outline, kind prose, params with their provenance and grounding, links, and each rule's pass or fail against the node it names. The same view is served in-conversation as an MCP App, where the model browses through exactly the tools you are looking at.

Both rest on **one convention, which is the contract of the commands**: the project keeps its tree in a package `ledger/` — an `__init__.py` beside a `tree.py` — and `tree.py` exposes `build() -> Quern` that takes no arguments and resolves its own registry. Point `--module PATH[:ATTR]` at any other entry and the convention is bypassed; it is the default, not a requirement.

**Checking it** is a separate act from reading it, and it is what makes a ledger worth keeping. A project's own gate is an ordinary Python module — quern ships one for itself:

```bash
uv run python -m ledger.check   # exit 1 while any rule is red
```

This repo's own ledger is **red today, on purpose**: the host's compute boundary carries two open debts, recorded as data a gate can see, refusing to call the surface sound until the work is done. A caveat that fires is the pitch.

## Five minutes

**Author a kind, write a rule** — meaning first, as data:

```python
from quern import KindDef, Node, Quantity, Quern, Rule, run_rules

tree = Quern(
    vocabulary=[KindDef(kind="task",
                        description="A piece of work. Params: spent and budget, in hours.")],
    rules=[Rule(name="never-over-budget", kind="task",
                description="a task's spent hours stay within its budget",
                expr="param(self, 'spent') <= param(self, 'budget')")],
)
```

**Add a node that violates it, and watch the rule fire** — every number is a `Quantity` carrying its unit, where it came from, and whether it is grounded enough to act on:

```python
tree.root.children = [Node(id="migration", kind="task", params={
    "spent": Quantity(value=120, unit="h", provenance="measured", grounded=True,
                      source="the timesheet"),
    # Ungrounded: a figure somebody said, that nobody has checked. It still computes —
    # this is the value a gate refuses to let travel, and what `!budget` marks in a brief.
    "budget": Quantity(value=100, unit="h", provenance="asserted", grounded=False,
                       source="quoted in the kickoff, never agreed"),
})]
for r in run_rules(tree):
    print(("ok " if r.ok else "RED"), r.rule, "@", r.node)
# RED never-over-budget @ migration
```

**Try to publish it, and watch the proof gate refuse** — it asks for referents before anything else: a kind no node is, is a private word, and a rule nothing demonstrates is a claim nobody has to believe:

```python
from quern.library import Library, Package

Library("registry").publish(Package(name="work", version="0.1.0", description="tasks and budgets",
                                    publisher="you", vocabulary=tree.vocabulary,
                                    rules=tree.rules), {})
# ValueError: 1 kind(s) that no example is: task. A word with no referent is what a
#             private vocabulary is made of — ship a node that is one, or mark the
#             entry `convention=True` if nothing ever should be
```

**Add the demonstration, and the same call publishes** — an example the rule passes, and a counter-example it must reject:

```python
from quern.library import CounterExample

agreed = dict(provenance="measured", grounded=True, source="the agreed scope")

Library("registry").publish(Package(
    name="work", version="0.1.0", description="tasks and budgets", publisher="you",
    vocabulary=tree.vocabulary, rules=tree.rules,
    examples=[Node(id="within", kind="task", params={
        "spent": Quantity(value=80, unit="h", **agreed),
        "budget": Quantity(value=100, unit="h", **agreed),
    })],
    counter_examples=[CounterExample(
        rule="never-over-budget", because="a task that spent more than it was given",
        node=Node(id="overrun", kind="task", params={
            "spent": Quantity(value=120, unit="h", **agreed),
            "budget": Quantity(value=100, unit="h", **agreed),
        }))],
), {})
# registry/packages/work/0.1.0.json — versioned, immutable, pinned by digest
```

That is the whole loop: meaning is authored where the work happens, checked where it stands, and only what demonstrates itself becomes something others can build on.

Vocabulary is checked for the one thing about it that is not prose. What a kind *means* is judged by a reader and no gate can pretend otherwise — but whether anything in the package *is* one is mechanical, and that is the failure the gate exists against: a word entering the library with no referent. So every kind must be instantiated by an example, or declare `convention=True` for an entry that names a namespace its contracts hang prose on. The flag is held **both** ways — say a kind is a convention and nothing in the package may be one — because an exemption anyone could flip would read as a check while being none.

## Every run is recorded

quern declares its nondeterminism boundary — text on disk, the registry listing, solver blobs, `$QUERN_REGISTRY` — and writes one small JSONL *tape* per invocation into `.quern/flight/`. A tape is that run, compressed: replay it and the real code re-executes with the recorded answers fed back, every internal variable observable.

```bash
uv run python -m quern.replay .quern/flight/<tape>.jsonl            # what does it hold?
uv run python -m quern.replay .quern/flight/<tape>.jsonl --call 0   # play it
```

Set `QUERN_FLIGHT=0` to turn it off. It is on by default because a recorder you have to remember to switch on is a recorder that was off on the run that mattered — and the point of a bug report is that nobody knew it was coming.

## The model in detail

Everything above in full. The `Quern` type is the model — vocabulary, rules, solvers, packages, and a `root` node tree — a tree of typed-by-data objects with a vocabulary that rules are written against (the pattern BRMS engines call a "Business Object Model"), generalized so **semantics are data**, not code. The code here is mechanics and safety only; everything that *means* something is content:

- **Nodes**: free-text `kind`, params (every number is a Quantity: `value`, `unit`, `tolerance`, a free-text `provenance` label the domain names, the fixed `grounded` predicate — is this an observation you may act on? — plus `source` and `derived_from` lineage), named links, an opaque payload, children. Path-addressed, partially updatable.
- **Vocabulary**: what kinds mean — prose, registered at runtime, discovered with each node you read (`semantics_at`). An entry that names a namespace rather than a shape a node can have says `convention=True`, which publication holds it to. A kind may also declare `operations` — name → `{contract, description, params_doc, medium}` — binding it to solver contracts that make sense on it, so every read answers "what is this, what must hold, what can be computed here". Capability attaches to what a node *means*, as data: nodes get affordances everywhere the kind appears, the tool surface stays closed, and the core never branches on an operation name.
- **Rules**: a tiny safe expression language (no eval). Builtins are structural (`param`, `nodes`, `params_of`, `count`, `sum`, `len`, `ctx`, `superseded`, `uses`, `where_used`, `rollup`, `tally`, the trace verbs `before`, `preceding`, `following`, `index`, `at`, `parent`, arithmetic, comparisons, booleans) plus **one bridge to meaning: `solve('contract', …)`**.
- **Solvers**: sandboxed WASM (wasmtime: fuel + memory caps, zero imports, no clock/net) that *propose* — outputs stamped `derived` with the code hash — and never write the tree. Content-addressed blobs; clients may fetch and run them locally (same artefact, same ABI). The store is medium-general: one `artifact://{sha}` channel serves `wasm` (universal compute), `web` (a self-contained bundle a host renders against a node slice, for the user) and `prose` (a skill an agent follows with the generic verbs) — the medium is data on the descriptor, and only `wasm` output may enter the tree as `derived`. The purity boundary is the point: replayability survives exactly because only the sandboxed, content-addressed medium can propose values. A contract also carries **demonstrations** — the worked cases it must answer, as data — because a gate reading `solve(…) == 0` cannot tell a contract that counts from one that returns zero. A blob's travel in its package; a **native**'s register beside the implementation (`register_native(…, spec=…)`), since a package must not be able to soften the proof of code it does not ship.
- **Library**: versioned, immutable packages `{requires, vocabulary, rules, solvers, examples, counter_examples, demonstrations}` — publication is proof-gated, once per kind of knowledge that can be checked. Every kind must be instantiated by an example, or declare itself a `convention` — a namespace entry, then held to naming nothing. Every rule must be exercised by the package's own examples and pass (with the `requires` closure staged beneath, so a package proves itself in the semantics it will actually live in) **and** be refused by a counter-example staged alone. Every executable contract must hold against demonstrations — a tree state, the call, the answer it must give — including two that expect *different* answers, since one expected number is satisfied by a contract that returns it and computes nothing. A package extends others by requiring them — exact versions only, no ranges, fork-or-republish over resolver algebra — and a `Quern` pin pulls the whole closure, nearer layers winning; local content always wins over packages. Two versions of one name in a closure is a diamond conflict, refused at pin time.
- **The roll** (`quern.roll`): every rule runs against the tree as it is now, so no rule can see what was *removed*. The roll is the smallest artifact that makes absence mechanical — each node's path, kind, and a digest of what it says, committed beside the tree. A vanished entry, a re-kinded one, or one that quietly no longer says what the record said it did is then a fact in the diff rather than a memory.
- **Host** (`quern.host`, extra `quern[host]`): registers the generic `tree_*` MCP tools once over a **`Workspace`** — the few seams a domain provides (its live quern, its effective read view, the write guard, persistence, its blob store, its library, its starter vocabulary). One endpoint hosts several domains by resolving a different Workspace per call — same code, separate stores.
- **Navigator** (`quern.app_host`, same extra): the Quern is the shared context of codesign, so the human needs the same grip on it as the model. `register_app(mcp, get_ws)` serves it as an **MCP App** (SEP-1865) — a `ui://quern/navigator.html` resource plus a `tree_app` entry tool — and every browse or edit in the UI goes through the **same generic `tree_*` tools** the model uses. `serve_dev(get_ws)` serves the identical HTML on localhost, which is what `quern navigate` runs. Deliberately not geometric: this is the meaning view, and shapes stay a domain concern.

Domains are authored in their own repositories and travel the registry as data. A domain package may be nothing but vocabulary and rules; it may also carry native implementations of its contracts, registered when its Python is imported — a native is an optimisation of content, never a semantics of its own, and a plain `import quern` pulls in no domain at all. The one asymmetry is deliberate: the contracts every gate leans on are authored as content like anything else, while their implementations ship here in `quern.grounding`, because a gate that could be handed its own grounding is not a gate. Meaning is data, safety is code.

The substrate knows nothing of its consumers. A domain lives entirely outside this library — as a package (vocabulary, rules, solvers) plus a `Workspace` embedding `quern` — and domain safety invariants stay in that consumer code. `ledger@0.6.0`, the vocabulary this repo's own brief is written in, is one such package; it is pinned in `quern.lock` like any other content.

Canonical repo: `xag/quern`. Depend on it by git rev, never a range; a consumer that vendors it instead (e.g. via `git subtree` under some `<prefix>`) syncs with:

    git subtree pull --prefix=<prefix> https://github.com/xag/quern main --squash

## License

Apache-2.0 — see [LICENSE](LICENSE).

© 2026 Xavier Grehant
