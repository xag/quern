# quern — the generic backend substrate

## Why: knowledge that moves as fast as the work

Designing anything takes three kinds of knowledge — **semantics** (what the parts mean), **models**
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

The **Quern**: a tree of typed-by-data objects with a
vocabulary that rules are written against (the pattern BRMS engines like IBM ODM
call a "Business Object Model"), generalized so **semantics are data**, not code.
The `Quern` type is the model — vocabulary, rules, solvers, packages, and a `root`
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
- **Standard contracts**: domains are authored in their own repos and travel the
  registry as data (xag/quern#19): `geometry@` (xag/geometry) documents shape
  conventions and solver contracts and ships its own native implementations —
  installing that Python registers them; `ledger@` (xag/ledger) is pure
  vocabulary and rules; `grounding@` (xag/grounding) authors the meaning whose
  implementations stay HERE in `quern.grounding`, because every gate leans on
  them: meaning is data, safety is code. A native is an optimisation of
  content, never a semantics of its own, and a plain `import quern` pulls in no
  domain.
- **Host** (`quern.host`, extra `quern[host]`): registers the generic `tree_*` MCP
  tools once over a **`Workspace`** — the few seams a domain provides (its live
  quern, its effective read view, the write guard, persistence, its blob store,
  its library, its starter vocabulary). One endpoint hosts several domains by
  resolving a different Workspace per call — same code, separate stores.

- **Navigator** (`quern.app_host`, same `quern[host]` extra): the Quern is the shared
  context of codesign, so the human needs the same grip on it as the model.
  `register_app(mcp, get_ws)` serves a semantic navigator as an **MCP App**
  (SEP-1865): a `ui://quern/navigator.html` resource plus a `tree_app` entry tool;
  in an Apps-capable client the tree renders in-conversation — outline, kind
  prose, params with provenance and grounding, links, rules with pass/fail —
  and every browse or edit in the UI goes through the **same generic `tree_*`
  tools** the model uses. `serve_dev(get_ws)` serves the identical HTML on
  localhost for a plain browser. Deliberately not geometric: this is the
  meaning view; shapes stay a domain concern (`geometry.host`, in xag/geometry).

The substrate knows nothing of its consumers. A domain lives entirely outside this
library — as a package (vocabulary, rules, solvers) plus a `Workspace` embedding
`quern` — and domain safety invariants stay in that consumer code: meaning is data,
safety is code.

Canonical repo: `xag/quern` (private while it hardens). A consumer that vendors it
(e.g. via `git subtree` under some `<prefix>`) syncs with:

    git subtree pull --prefix=<prefix> <remote> main --squash
