# quern

quern is a tree of typed objects where the types, the rules and the solvers are **data**,
authored at runtime — not code, not schema migrations. You register what a kind of node
*means* (in prose), write rules against that meaning in a small safe expression language,
and watch them go red on the exact node that violates them. What proves out gets published
as a versioned, digest-pinned package — and publication is **proof-gated**: a rule that no
example exercises and no counter-example refutes does not enter.

## Five minutes

```bash
git clone https://github.com/xag/quern && cd quern && uv sync
```

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

Add an example that exercises the rule and a counter-example that refutes it, and the same
call publishes a versioned, immutable package other trees pin by digest. That is the whole
loop: meaning is authored where the work happens, checked where it stands, and only what
demonstrates itself becomes something others can build on.

This repo's own design ledger runs on the same machinery (`uv run python -m ledger.check`)
— and it is **red today, on purpose**: the host's compute boundary carries two open debts,
recorded as data a gate can see, refusing to call the surface sound until the work is done.
A caveat that fires is the pitch.

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

Canonical repo: `xag/quern`. Depend on it by git rev (the estate pins by rev, never a
range); a consumer that vendors it instead (e.g. via `git subtree` under some `<prefix>`)
syncs with:

    git subtree pull --prefix=<prefix> https://github.com/xag/quern main --squash

## License

Apache-2.0 — see [LICENSE](LICENSE).

© 2026 Xavier Grehant
