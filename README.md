# bom — the generic backend substrate

## Why: knowledge that moves as fast as the work

A virtual twin is three things — **semantics** (what the parts mean), **models**
(what must hold between them), **solvers** (what computes over them). In the old
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

That is the premise this substrate is built on. **In bom, all three are data**, not
code — vocabulary you register as you navigate, rules you write against it, solvers
you install behind one bridge — authored at runtime, per tree, by whoever designs
there, and capitalized into versioned packages the next design pins and refines. The
core interprets none of it; it is mechanics and safety only. Innovation and
capitalization become **organic by design**: every endeavor is a research project
that is operative on the go, and the boundary between research and operations
disappears — the model you reason with *is* the model you run. Knowledge no longer
sits still while operations move around it; the two evolve together. With AI at every
node, that is simply the new normal.

## What bom is

The **BOM** — Business Object Model: a tree of typed-by-data objects with a
vocabulary that rules are written against (the pattern BRMS engines like IBM ODM
call a "Business Object Model"), generalized so **semantics are data**, not code.
The `Bom` type is the model — vocabulary, rules, solvers, packages, and a `root`
node tree. The code here is mechanics and
safety only; everything that *means* something is content:

- **Nodes**: free-text `kind`, params (every number is a Quantity: `value`, `unit`,
  `tolerance`, a free-text `provenance` label the domain names, the fixed `grounded`
  predicate — is this an observation you may act on? — plus `source` and
  `derived_from` lineage), named links, optional shape payload, children.
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
  `uses`, `where_used`, `rollup`, `tally`, arithmetic, comparisons, booleans)
  plus **one bridge to meaning: `solve('contract', …)`**.
- **Solvers**: sandboxed WASM (wasmtime: fuel + memory caps, zero imports, no
  clock/net) that *propose* — outputs stamped `derived` with the code hash —
  and never write the tree. Content-addressed blobs; clients may fetch and run
  them locally (same artefact, same ABI).
- **Library**: versioned, immutable packages `{vocabulary, rules, solvers,
  examples}` — publication is proof-gated (rules must be exercised by the
  package's own examples and pass; modules must meet the ABI). A `Bom` pins
  `name@version`; local content always wins over packages.
- **Standard contracts**: `geometry@1` documents shape conventions and solver
  contracts (`geometry/volume`, `bbox_*`, `clearance`, …); the Python here is
  its first-class native implementation, registered behind the same names
  (`register_native`). A native is an optimisation of content, never a
  semantics of its own. It is reached as the `bom.geometry` package, **not** the
  substrate's top-level namespace — importing it installs its natives, so a plain
  `import bom` pulls in no domain. Rendering (`render`, `render_perspective`, with
  the encoding `fmt` a data argument, not a name) is the package's own presentation,
  deliberately not a contract: it returns bytes for a human, never a value into the
  tree.

**The core fixes verbs a consumer branches on, never nouns a domain names.** What a
kind *is* stays vocabulary (data); the only meanings frozen into the substrate are
the handful of relations every consumer would otherwise re-implement and get wrong —
`grounded` (may I act on this value?), `supersedes` (which node do we currently
hold?), `derived_from` (what does this rest on, and what must fall when it
changes?), and `uses` (what is this an instance of?). Provenance was once a fixed
four-word epistemics; it is now a free label plus that one `grounded` predicate —
the label is the domain's to name, the verb is the core's to enforce.

**Reuse reads through `uses`.** A node that links `uses -> [definition]` is a
*usage*: params it does not carry resolve through the definition (usage always
wins), its kind inherits when empty, and `explode()` grafts the definition's
children under the usage — cycle-refused, dangling-refused. One definition, many
occurrences: what a bill of materials calls part reuse, kept a verb. The folds a
BOM lives on take their nouns as data — `rollup(under, 'qty', 'cost')` is a costed
bill, `tally(under, 'fastener', 'qty')` a where-used count — so the core multiplies
and sums without ever learning the word "qty". `where_used` is one indexed query,
like `superseded`.

**Scale is a choice of store, never a change of model.** Every verb runs against
the `TreeStore` protocol: `Bom` satisfies it in memory (the default, right for
design-sized trees), `bom.store.SqliteStore` satisfies it on disk with real
indexes — path ranges for walks, a kind column, a link table behind
supersession/where-used — plus WAL snapshot reads. The same call sites serve a
hundred-node design and a hundred-thousand-line bill; a consumer opens a store
instead of loading a Bom and changes nothing else. Multi-user change workflow
stays consumer code: the substrate stores, it does not arbitrate.

**Evaluation is pure**: rules and solvers see the tree slice and the
caller-supplied `context`, nothing else — every evaluation is deterministic and
replayable (what makes backtesting structural for time-series consumers).

- **Host** (`bom.host`, extra `bom[host]`): registers the generic `tree_*` MCP
  tools once over a **`Workspace`** — the few seams a domain provides (its live
  bom, its effective read view, the write guard, persistence, its blob store,
  its library, its starter vocabulary). One endpoint hosts several domains by
  resolving a different Workspace per call — same code, separate stores.

The substrate knows nothing of its consumers. A domain lives entirely outside this
library — as a package (vocabulary, rules, solvers) plus a `Workspace` embedding
`bom` — and domain safety invariants stay in that consumer code: meaning is data,
safety is code.

Canonical repo: `xag/bom` (private while it hardens). A consumer that vendors it
(e.g. via `git subtree` under some `<prefix>`) syncs with:

    git subtree pull --prefix=<prefix> <remote> main --squash
