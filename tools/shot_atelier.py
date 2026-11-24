"""Show the Throne tab with the atelier: the made-up room of ``shot_throne_room`` plus one guest card.

Ash's card is blocked and labelled ``guest``, so Ash walks through the right-wall door to the
atelier desk. The data directory is a temporary folder; no real session or board is read.

    python tools/shot_atelier.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shot_throne_room as base  # noqa: E402

from board.model import new_card  # noqa: E402
from board.store import LocalStore  # noqa: E402


def main() -> None:
    card = new_card("studio", "Rune sketch", labels=["guest"], assignee="a1")
    LocalStore().put({**card, "column": "blocked", "progress": 20})
    base.main()


if __name__ == "__main__":
    main()
