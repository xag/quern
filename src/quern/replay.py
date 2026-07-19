"""Re-run a recorded invocation against the real code: `python -m quern.replay TAPE --call 0`.

The recorder's half of the practice is worth little on its own — a tape nobody can play is a
log with extra ceremony. This is the other half, and it is deliberately tiny, because the
recorder does the work: name the boundary, name the callable, and the library re-executes the
original command with the recorded answers fed back, under a tracer that can show any local
at any line.

Run it with no `--call` to list what a tape holds.
"""

from __future__ import annotations

import sys
from pathlib import Path

from flight_recorder import ReplayAdapter, run_cli

from . import cli
from .boundary import boundary


class QuernReplay(ReplayAdapter):
    """The whole per-app wiring: quern's boundary, and `run` as the callable to re-execute.

    `resolve` returns the function off `quern.cli` unwrapped — this process never calls
    `cli.main`, so the recorder was never installed here, and the replay machinery does its
    own patching in playback mode. The recorded kwargs are `{"argv": [...]}`, which is exactly
    `run`'s signature; that correspondence is not a coincidence but the reason the boundary
    was drawn where it was."""

    def __init__(self) -> None:
        self.boundary = boundary()
        # Trace quern's own frames and nothing else — the point is to watch quern's variables,
        # not pydantic's or argparse's.
        self.trace_root = str(Path(__file__).resolve().parent)

    def resolve(self, fn_name: str, feed) -> object:
        fn = getattr(cli, fn_name, None)
        if fn is None:
            raise SystemExit(f"this tape records '{fn_name}', which quern.cli no longer has — "
                             "the tape predates a rename, and the code moved out from under it")
        return fn


def main(argv: list[str] | None = None) -> int:
    return run_cli(QuernReplay(), argv, prog="quern-replay")


if __name__ == "__main__":
    sys.exit(main())
