"""STATUSCOLOR.1: the one state-to-colour palette (no Tk); ``cli_avatars.app.status_ink`` re-exports it."""

from __future__ import annotations

PALETTE = {
    "idle": "#9a98b8",
    "busy": "#4fd16a",
    "thinking": "#a77bff",
    "subagent": "#2ec4b6",
    "blocked": "#ffb000",
    "error": "#ff5a5a",
    "done": "#7fb4ff",
}


def colour(status: str) -> str:
    """The state's colour; an unknown state is idle grey."""
    return PALETTE.get(status, PALETTE["idle"])
