"""The boundary is instrumented, and the tape it writes actually replays.

Two claims, and the second is the one that rots quietly. Recording is easy to keep working by
accident; RECORDING SOMETHING REPLAYABLE is not. The failure mode this guards is specific and
was hit once already while the boundary was being drawn: move the seam up to `Library.get` and
the tape fills with `{"__opaque__": "Package(...)"}` — every event still present, every count
still right, and the recording reproduces nothing, because a repr string replays as a repr
string. A tape that cannot be played is a log with ceremony, and nothing in a green suite
would have said so.

So the test does not inspect the tape's shape. It plays it.
"""

from __future__ import annotations

import json
from pathlib import Path

from flight_recorder import replay_call, uninstall

from quern.cli import main
from quern.replay import QuernReplay


def _tapes(root: Path) -> list[Path]:
    return sorted((root / ".quern" / "flight").glob("*.jsonl"))


def _record_a_brief(tmp_path, monkeypatch) -> Path:
    """Run `quern brief` on quern's own repo, from a scratch cwd so the tape lands there.

    The recorder is a process-global with an open session file, so a test that armed it leaves
    the next one writing into the PREVIOUS test's tmp dir. Tear it down on both sides: the
    library's own `uninstall` restores every patch, and quern's `_armed` latch has to be
    released alongside it or `_record` would decline to re-arm."""
    uninstall()
    monkeypatch.setattr("quern.cli._armed", False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QUERN_FLIGHT", raising=False)
    main(["brief", str(Path(__file__).resolve().parents[1])])
    uninstall()
    tapes = _tapes(tmp_path)
    assert len(tapes) == 1, f"expected exactly one tape, got {tapes}"
    return tapes[0]


def test_a_cli_run_records_its_boundary(tmp_path, monkeypatch):
    tape = _record_a_brief(tmp_path, monkeypatch)
    lines = [json.loads(line) for line in tape.read_text(encoding="utf-8").splitlines()]
    header, call = lines[0], lines[1]

    assert header["ev"] == "session"
    assert "quern_registry" in header, "the header must say which registry the run was pointed at"

    # The recorded call is the ARGV, not a Namespace — see cli.run for why that is the seam.
    assert call["fn"] == "run"
    assert call["kwargs"]["argv"] == ["brief", str(Path(__file__).resolve().parents[1])]
    assert call["events"], "reading a ledger must cross the boundary at least once"


def test_no_boundary_answer_is_opaque(tmp_path, monkeypatch):
    """The regression that matters: an opaque result is an unreplayable one."""
    tape = _record_a_brief(tmp_path, monkeypatch)
    call = [json.loads(line) for line in tape.read_text(encoding="utf-8").splitlines()][1]

    opaque = [e["fn"] for e in call["events"]
              if isinstance(e.get("res"), dict) and "__opaque__" in e["res"]]
    assert not opaque, (
        f"these effects record as reprs and would replay as strings: {opaque}. "
        "Move the boundary down to where the value is text the tape can hold exactly.")


def test_the_tape_replays_bit_for_bit(tmp_path, monkeypatch):
    tape = _record_a_brief(tmp_path, monkeypatch)
    report = replay_call(tape, 0, QuernReplay(), trace_path=None)

    assert report.ok, f"replay diverged: {report.divergence or report.result_diff}"
    assert report.events_consumed == report.events_total, (
        f"{report.events_total - report.events_consumed} recorded answers went unused — "
        "the replayed code asked fewer questions than the recording holds")
