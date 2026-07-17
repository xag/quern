# Contributing

The proof gate is the review: a package must carry examples that exercise every rule and
counter-examples that refute them, or `publish` refuses it — for your PR exactly as for
anyone's. Run the tests with `uv run pytest`, and the repo's own ledger with
`uv run python -m ledger.check` (it is red today, on purpose — discharge a red node by
doing the work it names, never by editing the ledger).
