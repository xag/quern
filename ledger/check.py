"""Run the ledger's rules and report. `uv run python -m ledger.check`, or `quern check`.

Exit code is 1 when something is UNACCOUNTED FOR - a red no node expects, an expectation
whose red has gone, or an entry that left the record without a tombstone. Not on red as
such: this ledger ships red on purpose (the host's compute boundary is unmetered and
blocking). The whole check is `quern.check`, which every ledgered project can call.
"""

from __future__ import annotations

import sys
from pathlib import Path

from quern.check import check

from .tree import build

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    return check(_ROOT, build, fresh="--fresh" in sys.argv[1:], title="quern - ledger brief")


if __name__ == "__main__":
    sys.exit(main())
