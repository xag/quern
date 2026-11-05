# Contributing

The proof gate is the review: a package must carry examples that exercise every rule and
counter-examples that refute them, or `publish` refuses it — for your PR exactly as for
anyone's. Run the tests with `uv run pytest`, and the repo's own ledger with
`uv run python -m ledger.check` (it is red today, on purpose — discharge a red node by
doing the work it names, never by editing the ledger).

## Releasing

Bump `version` in `pyproject.toml` on main. Once the tests pass on that commit, the release workflow publishes it to PyPI, tags it `v<version>` and makes the GitHub release. Consumers install quern from PyPI by version, so a change they need reaches them only with a bump; without one they must pin a git rev, which a wheel installed from an index cannot carry.
