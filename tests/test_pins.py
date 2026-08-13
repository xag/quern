"""The pins this package cannot leave open.

A dependency imported at MODULE SCOPE by shipped code is not a range question, it is an
availability question: the next fresh resolve either has the name or the process dies at
import. `host.py` does `from mcp.server.fastmcp import FastMCP` at line 29, and mcp 2.0.0
does not have it.

This is the third time the same shape has cost something. korean-gpt-coach took a
production outage on 2026-08-12 when a rebuilt image resolved mcp 2.0.0 and crash-looped;
this repo's first-ever CI run failed on 2026-08-13 for the identical reason. Both times a
local environment holding 1.x had been passing for weeks — only a FRESH resolve moves, so
the failure waits for CI, or for a deploy, and never for a developer.
"""

import re
import tomllib
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

# name -> (module it is imported for, at module scope)
_MUST_BE_CAPPED = {"mcp": "mcp.server.fastmcp, imported by src/quern/host.py"}


def _requirements() -> dict[str, str]:
    """Every requirement this package declares, by name — dependencies and extras."""
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    out = {}
    for spec in specs:
        m = re.match(r"([A-Za-z0-9._-]+)(\[[^\]]*\])?(.*)", spec.strip())
        if m:
            out[m.group(1).lower()] = (m.group(3) or "").strip()
    return out


@pytest.mark.parametrize("name,why", sorted(_MUST_BE_CAPPED.items()))
def test_a_module_scope_import_carries_an_upper_bound(name, why):
    spec = _requirements().get(name)
    assert spec is not None, f"{name} is no longer declared; it was pinned for {why}"
    assert re.search(r"<\s*\d", spec), (
        f"{name} is pinned as {spec!r} with no upper bound, and {why}. The next major "
        f"release reaches production the next time anything resolves fresh — which is a "
        f"deploy or a CI run, never a developer's already-working venv.")


def test_the_capped_import_actually_resolves_here():
    """The cap is only worth what the import is worth: if this environment cannot
    import what host.py imports, the range is wrong rather than merely narrow."""
    pytest.importorskip("mcp", reason="the [host] extra is not installed in this env")
    import importlib

    importlib.import_module("mcp.server.fastmcp")
