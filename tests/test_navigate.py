"""The navigator's launcher: loading somebody else's ledger, and refusing to write it.

`navigate.py` had no test until 2026-08-13 (quern#40), and it is the module whose own
ledger entry admits its drift bugs were "found by a user, not a test". One of them was
still there: a function-local `import importlib` late in `_import_ledger_module` made the
name local to the whole function, so the STANDALONE branch — a ledger/tree.py with no
`__init__.py` beside it — hit an unbound local before the import ever ran. Every ledger in
the fleet happens to be a package, so nothing noticed until a bare one was stood up.

These tests build real ledgers on disk both ways round, because that difference is the
whole bug: a mock of the import machinery would have reproduced neither branch.
"""

from pathlib import Path

import pytest

from quern import Quern
from quern.navigate import (
    ReadOnlyWorkspace,
    _import_ledger_module,
    load_build,
    project_label,
)

_TREE = """\
from quern import Node, Quern


def build() -> Quern:
    q = Quern()
    q.root.children = [Node(id="only", kind="decision", name="the one entry")]
    return q


def other() -> Quern:
    return Quern()
"""


def _ledger(root: Path, *, package: bool) -> Path:
    """A ledger on disk. `package` decides the branch: a directory carrying
    `__init__.py` is imported as a module of its package; a bare one is loaded from
    its file."""
    d = root / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    if package:
        (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "tree.py").write_text(_TREE, encoding="utf-8")
    return d / "tree.py"


@pytest.mark.parametrize("package", [True, False], ids=["as-a-package", "standalone"])
def test_a_ledger_loads_whether_or_not_it_is_a_package(tmp_path, package):
    """The regression. The standalone branch was dead code that raised UnboundLocalError,
    and it is the branch a project stood up per the skill's own instructions produces."""
    path = _ledger(tmp_path, package=package)
    mod = _import_ledger_module(path)
    tree = mod.build()
    assert isinstance(tree, Quern)
    assert [c.id for c in tree.root.children] == ["only"]


def test_the_conventional_location_needs_no_spec(tmp_path):
    _ledger(tmp_path, package=True)
    assert load_build(tmp_path, None)().root.children[0].id == "only"


def test_a_spec_overrides_the_convention_and_may_name_the_attribute(tmp_path):
    path = _ledger(tmp_path / "elsewhere", package=False)
    assert load_build(tmp_path, str(path))().root.children[0].id == "only"      # ATTR defaults
    assert load_build(tmp_path, f"{path}:other")().root.children == []          # ATTR given


def test_a_missing_ledger_says_where_it_looked(tmp_path):
    """A launcher that fails must say what it wanted; this message is the one a
    person meets when they run `quern navigate` in the wrong directory."""
    with pytest.raises(SystemExit) as e:
        load_build(tmp_path, None)
    assert "does not exist" in str(e.value) and "ledger/tree.py" in str(e.value).replace("\\", "/")


def test_a_ledger_that_raises_at_import_names_itself(tmp_path):
    d = tmp_path / "ledger"
    d.mkdir()
    (d / "tree.py").write_text("raise ValueError('boom')\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_build(tmp_path, None)
    assert "boom" in str(e.value) and "failed" in str(e.value)


def test_a_ledger_without_the_callable_is_refused(tmp_path):
    path = _ledger(tmp_path, package=True)
    with pytest.raises(SystemExit) as e:
        load_build(tmp_path, f"{path}:nope")
    assert "no callable 'nope'" in str(e.value)


def test_the_label_prefers_the_project_name_over_the_directory(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "the-real-name"\n', encoding="utf-8")
    assert project_label(tmp_path) == "the-real-name"


def test_the_label_falls_back_to_the_directory(tmp_path):
    assert project_label(tmp_path) == tmp_path.name
    # A pyproject that cannot be parsed, or names nothing, must not break a viewer.
    (tmp_path / "pyproject.toml").write_text("not : valid : toml\n", encoding="utf-8")
    assert project_label(tmp_path) == tmp_path.name


class TestTheViewerCannotWrite:
    """A browser pointed at somebody else's ledger must not be able to edit it: every
    write seam raises rather than quietly doing nothing, because a silent no-op reads
    as a save that worked."""

    def _ws(self) -> ReadOnlyWorkspace:
        return ReadOnlyWorkspace(Quern(), "somebody-elses-ledger")

    def test_the_read_verbs_answer(self):
        ws = self._ws()
        assert ws.label == "somebody-elses-ledger"
        assert isinstance(ws.effective(), Quern)
        assert ws.starter_vocabulary() == []

    @pytest.mark.parametrize("act", [
        lambda ws: ws.assert_editable("anything"),
        lambda ws: ws.save(),
    ])
    def test_every_write_seam_refuses(self, act):
        with pytest.raises(PermissionError):
            act(self._ws())

    @pytest.mark.parametrize("attr", ["blob_dir", "library"])
    def test_the_stores_it_does_not_have_say_so(self, attr):
        with pytest.raises(NotImplementedError):
            getattr(self._ws(), attr)


def test_an_absolute_path_is_not_split_at_its_drive_letter(tmp_path):
    r"""The bug the first test of this module found. `--module C:\proj\ledger\tree.py`
    was partitioned at the DRIVE colon, so the launcher looked for a ledger at `C` and
    reported it missing — every absolute path on Windows, which is where this estate runs.
    Both forms must read the same file, with and without an explicit attribute."""
    path = _ledger(tmp_path, package=False)
    assert path.is_absolute() and ":" in str(path)          # the shape that broke it
    assert load_build(tmp_path, str(path))().root.children[0].id == "only"
    assert load_build(tmp_path, f"{path}:other")().root.children == []
