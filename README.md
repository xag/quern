# quern

quern is a tree of typed objects where the types, the rules and the solvers are **data**,
authored at runtime — not code, not schema migrations. You register what a kind of node
*means* (in prose), write rules against that meaning in a small safe expression language,
and watch them go red on the exact node that violates them. What proves out gets published
as a versioned, digest-pinned package — and publication is **proof-gated**: a rule that no
example exercises and no counter-example refutes does not enter.

```bash
git clone https://github.com/xag/quern && cd quern && uv sync
```

The core needs only pydantic and wasmtime. The MCP host and the navigator need one extra:
`uv sync --extra host`.

## Read a tree

The tree most projects meet first is a **design ledger**: the decisions a codebase rests on
with the alternatives they rejected, the debts it carries on purpose, the hypotheses still
open, and the gates that refuse to go green while a debt is unpaid. Two commands open one,
and neither needs any per-project wiring.

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

10 entr(y/ies), ~2066 words of prose.
```

Every marker on a line is read off the node, never annotated by hand. `!meter` names a
param that is **not grounded** — the unsound value the entry is carrying, and precisely
what a gate reads to refuse. `admits->…` are the node's links, `{2 alternative}` counts
its children by kind, and `RED(…)` names the rule failing on it.

Superseded entries are counted away rather than printed, with a trailer saying what was
omitted; the tree keeps them and `--all` prints them marked with what superseded them.
`--fat` appends each entry's wordcount and sorts by it, heaviest first — the curation
view, where the first line is the first thing to tighten.

A model reads it the same way: `tree_brief` serves exactly this over MCP, with the same
two flags. It is the table of contents and `tree_get` is the chapter — reading a tree by
`tree_get('')` spends its whole history to find the dozen claims that still bind, which
is the cost the brief exists to refuse.

**`quern navigate`** — the same tree in a browser, read-only:

```bash
uv run quern navigate          # serves http://localhost:8765 and opens it
uv run quern navigate path/to/project
```

Outline, kind prose, params with their provenance and grounding, links, and each rule's
pass or fail against the node it names. The same view is served in-conversation as an MCP
App, where the model browses through exactly the tools you are looking at.

Both rest on **one convention, which is the contract of the commands**: the project keeps
its tree in a package `ledger/` — an `__init__.py` beside a `tree.py` — and `tree.py`
exposes `build() -> Quern` that takes no arguments and resolves its own registry. Point
`--module PATH[:ATTR]` at any other entry and the convention is bypassed; it is the
default, not a requirement.

**Checking it** is a separate act from reading it, and it is what makes a ledger worth
keeping. A project's own gate is an ordinary Python module — quern ships one for itself:

```bash
uv run python -m ledger.check   # exit 1 while any rule is red
```

This repo's own ledger is **red today, on purpose**: the host's compute boundary carries
two open debts, recorded as data a gate can see, refusing to call the surface sound until
the work is done. A caveat that fires is the pitch.

None of that vocabulary is quern's. `decision`, `debt`, `hypothesis`, `gate` and the rules
that judge them arrive as a package pinned by digest in `quern.lock`, like any other
content. quern supplies the mechanics — the tree, the rule evaluator, the proof gate, the
roll, the viewer — and interprets none of it.

## Every run is recorded

quern declares its nondeterminism boundary — text on disk, the registry listing, solver
blobs, `$QUERN_REGISTRY` — and writes one small JSONL *tape* per invocation into
`.quern/flight/`. A tape is that run, compressed: replay it and the real code re-executes
with the recorded answers fed back, every internal variable observable.

```bash
uv run python -m quern.replay .quern/flight/<tape>.jsonl            # what does it hold?
uv run python -m quern.replay .quern/flight/<tape>.jsonl --call 0   # play it
```

Set `QUERN_FLIGHT=0` to turn it off. It is on by default because a recorder you have to
remember to switch on is a recorder that was off on the run that mattered — and the point
of a bug report is that nobody knew it was coming.

## Five minutes

**Author a kind, write a rule** — meaning first, as data:

```python
from quern import KindDef, Node, Quantity, Quern, Rule, run_rules

tree = Quern(
    vocabulary=[KindDef(kind="tank",
                        description="A storage tank. Params: level and capacity, in litres.")],
    rules=[Rule(name="never-over-capacity", kind="tank",
                description="a tank's level stays within its capacity",
                expr="param(self, 'level') <= param(self, 'capacity')")],
)
```

**Add a node that violates it, and watch the rule fire** — every number is a `Quantity`
carrying its unit, where it came from, and whether it is grounded enough to act on:

```python
tree.root.children = [Node(id="t1", kind="tank", params={
    "level": Quantity(value=120, unit="L", provenance="sensor", grounded=True, source="gauge 4"),
    "capacity": Quantity(value=100, unit="L", provenance="spec", grounded=True, source="datasheet"),
})]
for r in run_rules(tree):
    print(("ok " if r.ok else "RED"), r.rule, "@", r.node)
# RED never-over-capacity @ t1
```

**Try to publish it, and watch the proof gate refuse** — a rule nothing demonstrates is a
claim nobody has to believe:

```python
from quern.library import Library, Package

Library("registry").publish(Package(name="tanks", version="0.1.0", description="tanks",
                                    publisher="you", vocabulary=tree.vocabulary,
                                    rules=tree.rules), {})
# ValueError: a package with rules must carry examples that exercise them
```

**Add the demonstration, and the same call publishes** — an example the rule passes, and a
counter-example it must reject:

```python
from quern.library import CounterExample

Library("registry").publish(Package(
    name="tanks", version="0.1.0", description="tanks", publisher="you",
    vocabulary=tree.vocabulary, rules=tree.rules,
    examples=[Node(id="sound", kind="tank", params={
        "level": Quantity(value=80, unit="L", provenance="sensor", grounded=True, source="gauge 4"),
        "capacity": Quantity(value=100, unit="L", provenance="spec", grounded=True, source="datasheet"),
    })],
    counter_examples=[CounterExample(
        rule="never-over-capacity", because="a tank fuller than its capacity",
        node=Node(id="overfull", kind="tank", params={
            "level": Quantity(value=120, unit="L", provenance="sensor", grounded=True, source="gauge 4"),
            "capacity": Quantity(value=100, unit="L", provenance="spec", grounded=True, source="datasheet"),
        }))],
), {})
# registry/packages/tanks/0.1.0.json — versioned, immutable, pinned by digest
```

That is the whole loop: meaning is authored where the work happens, checked where it
stands, and only what demonstrates itself becomes something others can build on.

## Why: knowledge that moves as fast as the work

Designing anything takes three kinds of knowledge — **semantics** (what the parts mean),
**models** (what must hold between them), **solvers** (what computes over them). In the old
world all three are frozen into software the moment a programme is built. You learn
something while designing — a better way to describe a part, a rule you should have
had, a smarter way to compute a fit — and you cannot apply it to the very programme
that taught it to you without a new release cycle. So the capitalization loop on
knowledge, modeling and best practice runs slow: semantics are fixed in the code,
models are fixed, solvers are fixed. Innovation waits for the next version.

AI dissolves that. Semantics, models and solvers can now be **authored on the go**,
while the design is happening, by the intelligence sitting *at* the work. Not
centralized in the heads of the people who once designed the PLM system, and not
frozen in its code — distributed, like a squid whose intelligence lives in its arms
and can regrow, rather than commanded from a single brain. Meaning is written at the
node that needs it, the moment it is needed, and kept.

That is the premise this substrate is built on. **In quern, all three are data**, not
code — vocabulary you register as you navigate, rules you write against it, solvers
you install behind one bridge — authored at runtime, per tree, by whoever designs
there, and capitalized into versioned packages the next design pins and refines. The
core interprets none of it; it is mechanics and safety only. Innovation and
capitalization become **organic by design**: every endeavor is a research project
that is operative on the go, and the boundary between research and operations
disappears — the model you reason with *is* the model you run. Knowledge no longer
sits still while operations move around it; the two evolve together. With AI at every
node, that is simply the new normal.

## What quern is

The **Quern**: a tree of typed-by-data objects with a vocabulary that rules are written
against (the pattern BRMS engines call a "Business Object Model"), generalized so
**semantics are data**, not code. The `Quern` type is the model — vocabulary, rules,
solvers, packages, and a `root` node tree. The code here is mechanics and safety only;
everything that *means* something is content:

- **Nodes**: free-text `kind`, params (every number is a Quantity: `value`, `unit`,
  `tolerance`, a free-text `provenance` label the domain names, the fixed `grounded`
  predicate — is this an observation you may act on? — plus `source` and
  `derived_from` lineage), named links, an opaque payload, children.
  Path-addressed, partially updatable.
- **Vocabulary**: what kinds mean — prose, registered at runtime, discovered with
  each node you read (`semantics_at`). A kind may also declare `operations` —
  name → `{contract, description, params_doc, medium}` — binding it to solver
  contracts that make sense on it, so every read answers "what is this, what
  must hold, what can be computed here". Capability attaches to what a node
  *means*, as data: nodes get affordances everywhere the kind appears, the tool
  surface stays closed, and the core never branches on an operation name.
- **Rules**: a tiny safe expression language (no eval). Builtins are structural
  (`param`, `nodes`, `params_of`, `count`, `sum`, `len`, `ctx`, `superseded`,
  `uses`, `where_used`, `rollup`, `tally`, the trace verbs `before`,
  `preceding`, `following`, `index`, `at`, `parent`, arithmetic, comparisons,
  booleans) plus **one bridge to meaning: `solve('contract', …)`**.
- **Solvers**: sandboxed WASM (wasmtime: fuel + memory caps, zero imports, no
  clock/net) that *propose* — outputs stamped `derived` with the code hash —
  and never write the tree. Content-addressed blobs; clients may fetch and run
  them locally (same artefact, same ABI). The store is medium-general: one
  `artifact://{sha}` channel serves `wasm` (universal compute), `web` (a
  self-contained bundle a host renders against a node slice, for the user) and
  `prose` (a skill an agent follows with the generic verbs) — the medium is
  data on the descriptor, and only `wasm` output may enter the tree as
  `derived`. The purity boundary is the point: replayability survives exactly
  because only the sandboxed, content-addressed medium can propose values.
- **Library**: versioned, immutable packages `{requires, vocabulary, rules,
  solvers, examples}` — publication is proof-gated (rules must be exercised by
  the package's own examples and pass, with the `requires` closure staged
  beneath; modules must meet the ABI). A package extends others by requiring
  them — exact versions only, no ranges, fork-or-republish over resolver
  algebra — and a `Quern` pin pulls the whole closure, nearer layers winning;
  local content always wins over packages. Two versions of one name in a
  closure is a diamond conflict, refused at pin time.
- **The roll** (`quern.roll`): every rule runs against the tree as it is now, so no rule
  can see what was *removed*. The roll is the smallest artifact that makes absence
  mechanical — each node's path, kind, and a digest of what it says, committed beside
  the tree. A vanished entry, a re-kinded one, or one that quietly no longer says what
  the record said it did is then a fact in the diff rather than a memory.
- **Host** (`quern.host`, extra `quern[host]`): registers the generic `tree_*` MCP
  tools once over a **`Workspace`** — the few seams a domain provides (its live
  quern, its effective read view, the write guard, persistence, its blob store,
  its library, its starter vocabulary). One endpoint hosts several domains by
  resolving a different Workspace per call — same code, separate stores.
- **Navigator** (`quern.app_host`, same extra): the Quern is the shared context of
  codesign, so the human needs the same grip on it as the model. `register_app(mcp,
  get_ws)` serves it as an **MCP App** (SEP-1865) — a `ui://quern/navigator.html`
  resource plus a `tree_app` entry tool — and every browse or edit in the UI goes
  through the **same generic `tree_*` tools** the model uses. `serve_dev(get_ws)`
  serves the identical HTML on localhost, which is what `quern navigate` runs.
  Deliberately not geometric: this is the meaning view, and shapes stay a domain
  concern.

Domains are authored in their own repositories and travel the registry as data. A domain
package may be nothing but vocabulary and rules; it may also carry native implementations
of its contracts, registered when its Python is imported — a native is an optimisation of
content, never a semantics of its own, and a plain `import quern` pulls in no domain at
all. The one asymmetry is deliberate: the contracts every gate leans on are authored as
content like anything else, while their implementations ship here in `quern.grounding`,
because a gate that could be handed its own grounding is not a gate. Meaning is data,
safety is code.

The substrate knows nothing of its consumers. A domain lives entirely outside this
library — as a package (vocabulary, rules, solvers) plus a `Workspace` embedding
`quern` — and domain safety invariants stay in that consumer code.

Canonical repo: `xag/quern`. Depend on it by git rev, never a range; a consumer that
vendors it instead (e.g. via `git subtree` under some `<prefix>`) syncs with:

    git subtree pull --prefix=<prefix> https://github.com/xag/quern main --squash

## License

Apache-2.0 — see [LICENSE](LICENSE).

© 2026 Xavier Grehant
