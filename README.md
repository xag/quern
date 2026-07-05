# bom — the generic backend substrate

The **BOM** — Business Object Model: a tree of typed-by-data objects with a
vocabulary that rules are written against (the pattern BRMS engines like IBM ODM
call a "Business Object Model"), generalized so **semantics are data**, not code.
The `Bom` type is the model — vocabulary, rules, solvers, packages, and a `root`
node tree. The code here is mechanics and
safety only; everything that *means* something is content:

- **Nodes**: free-text `kind`, params (every number carries `unit`, `tolerance`,
  `provenance: measured | inferred | design-target | derived`, `source`), named
  links, optional shape payload, children. Path-addressed, partially updatable.
- **Vocabulary**: what kinds mean — prose, registered at runtime, discovered with
  each node you read (`semantics_at`).
- **Rules**: a tiny safe expression language (no eval). Builtins are structural
  (`param`, `nodes`, `params_of`, `count`, `sum`, `len`, `ctx`, arithmetic,
  comparisons, booleans) plus **one bridge to meaning: `solve('contract', …)`**.
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
  semantics of its own.

**Evaluation is pure**: rules and solvers see the tree slice and the
caller-supplied `context`, nothing else — every evaluation is deterministic and
replayable (what makes backtesting structural for time-series consumers).

invariants stay in consumer code: meaning is data, safety is code.


