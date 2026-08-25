"""quern estate: the fleet's ledgers, read rather than remembered - and loud when they cannot be."""

from pathlib import Path

from quern.estate import Reading, _harvest, _settled, has_ledger, render


BRIEF = """demo - ledger brief
[decision]  a-choice  —  Something settled  {2 alternative}
[debt]  still-owed  —  Nobody has done this yet  !ungrounded  {1 discharge}
[debt]  paid-off  —  An old gap. Discharged 2026-08-01: it was closed  {1 discharge}
[law]  a-law  —  Something that must hold  RED(a-law-cites-a-source)

4 entr(y/ies), ~100 words of prose.
"""


def test_a_discharged_debt_is_not_owed():
    # the discharge convention keeps a paid debt in the tree, saying so in its own name -
    # so the only way to tell a live one from a settled one, without opening every entry,
    # is to read that. A roll-up that counted both would report work already done.
    r = Reading(project="demo")
    _harvest(BRIEF, r)
    assert [n for n, _, _ in r.owed] == ["still-owed"]
    assert r.red == [("law", "a-law", "a-law-cites-a-source")]


def test_a_project_that_could_not_be_read_is_reported_not_skipped():
    # the failure this tool exists to avoid: a ledger that did not answer, omitted, and the
    # silence read as "nothing owed here". It has to appear, and it has to say it is not that.
    out = render([Reading(project="fine", how="x", owed=[("a", "b", {})]),
                  Reading(project="broken", unread="no interpreter")])
    assert "broken" in out and "no interpreter" in out
    assert "UNREAD" in out and "not projects with nothing owed" in out


def test_a_ledger_is_found_where_it_lives_or_where_it_says(tmp_path: Path):
    beside = tmp_path / "beside"
    (beside / "ledger").mkdir(parents=True)
    (beside / "ledger" / "tree.py").write_text("", encoding="utf-8")
    assert has_ledger(beside)

    declared = tmp_path / "declared"
    declared.mkdir()
    (declared / "pyproject.toml").write_text(
        '[tool.quern]\nledger = "src/thing/tree.py:build"\n', encoding="utf-8")
    assert has_ledger(declared)

    neither = tmp_path / "neither"
    neither.mkdir()
    (neither / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert not has_ledger(neither)


def test_a_debt_paid_in_part_is_still_owed():
    # the discharge convention keeps a paid debt in the tree, saying so in its own name.
    # A debt paid in PART says so too, and is still work — dropping it would report the
    # remainder as done. This held for a while only because the test was a case-sensitive
    # substring that "PARTLY DISCHARGED" happened to miss; "Discharged in part" did not.
    for said, owed in [("PARTLY DISCHARGED 2026-08-22 - the catalogue exists", True),
                       ("Partly discharged: half of it done", True),
                       ("Discharged in part; the rest waits on a publish", True),
                       ("An old gap. Discharged 2026-08-01: it was closed", False),
                       ("Nobody has done this yet", True)]:
        r = Reading(project="demo")
        _harvest(f"[debt]  an-entry  —  {said}  {{1 discharge}}", r)
        assert bool(r.owed) is owed, said


def test_the_links_a_line_renders_come_back_as_data():
    # renderer and parser live in this repo and this test holds them together: a
    # change to either breaks here, in the same commit, instead of silently
    # dropping every edge a fleet index derives from the estate reading
    from quern.brief import _line
    from quern.tree import Node

    node = Node(id="a-debt", kind="debt", name="Waits on two things",
                links={"blocked_by": ["near", "far:away"], "rests_on": ["why"]})
    line = _line(None, "a-debt", node, False, [])
    r = Reading(project="demo")
    _harvest(line, r)
    assert r.owed == [("a-debt", line.split("—  ", 1)[1],
                       {"blocked_by": ["near", "far:away"], "rests_on": ["why"]})]


def test_prose_arrows_are_not_links():
    r = Reading(project="demo")
    _harvest("[debt]  an-entry  —  Reads a -> b, then maps x->y in prose  "
             "blocked_by->real-one  {1 discharge}", r)
    (_, _, links), = r.owed
    assert links == {"blocked_by": ["real-one"]}
