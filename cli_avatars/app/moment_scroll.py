"""TIMELAPSE: scroll a room's CLI transcript to the line nearest a time and light it for a moment."""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app import room_log

MOMENT, MOMENT_MS = "#3a2a10", 2400


def see_in_pane(pane, ts: float) -> None:
    """Find the transcript lines in order, as ``RoomPane._reload`` wrote them, up to the one nearest ``ts``."""
    term = pane._term
    lines = room_log.history(pane.window.directory(), pane.room_id, pane.target, stamped=True)
    if term is None or not lines:
        return
    near = min(range(len(lines)), key=lambda n: abs(lines[n][2] - ts))
    try:
        at = found = "1.0"
        for sender, text, _ts in lines[:near + 1]:
            shown = f"> {text}" if sender == "user" else text
            found = term.search(shown.split("\n", 1)[0], at, stopindex="end", exact=True)
            if not found:
                return
            at = term.index(f"{found} + {len(shown)}c")
        term.tag_configure("moment", background=MOMENT)
        term.tag_remove("moment", "1.0", "end")
        term.tag_add("moment", found, f"{at} lineend")
        term.see(found)
        term.after(MOMENT_MS, lambda: term.tag_remove("moment", "1.0", "end"))
    except tk.TclError:
        return
