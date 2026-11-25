"""MESSENGER on the Tasks tab: a lit card glows gold under a ``NEW FROM <room>`` ribbon until its note is opened.

``decorate`` runs from the floor's update: it adds the ribbon to the tile of each lit card and takes it off the rest.
A click on the ribbon opens the note on the floor (``CourierView.open``).
"""

from __future__ import annotations

from cli_avatars.app.courier_art import GLOW, INK, RIBBON

EDGE, EDGE_W = "#8a6a3a", 1


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def decorate(app, lit: dict, open_key) -> None:
    panel = getattr(app, "_tasks_panel", None)
    tiles = getattr(panel, "cards", None)
    if not isinstance(tiles, dict):
        return
    import tkinter as tk

    for card_id, box in tiles.items():
        info = lit.get(card_id)
        ribbon = getattr(box, "courier_ribbon", None)
        try:
            if info is None:
                if ribbon is not None:
                    ribbon.destroy()
                    box.courier_ribbon = None
                    box.config(highlightbackground=EDGE, highlightthickness=EDGE_W)
                continue
            words = f"✉ NEW FROM {(info.get('from_room') or info['from_topic'] or 'a room').upper()}"
            if ribbon is None or not ribbon.winfo_exists():
                first = box.pack_slaves()[0] if box.pack_slaves() else None
                ribbon = tk.Label(box, text=words, bg=_hex(RIBBON), fg=_hex(INK), font="DungeonBubble",
                                  anchor="w", padx=6, pady=1, cursor="hand2")
                ribbon.pack(fill="x", before=first) if first is not None else ribbon.pack(fill="x")
                box.courier_ribbon = ribbon
            elif ribbon.cget("text") != words:
                ribbon.config(text=words)
            ribbon.key = info["key"]
            ribbon.bind("<Button-1>", lambda _e, k=info["key"]: (open_key(k), "break")[1])
            if box.cget("highlightthickness") != 2:
                box.config(highlightbackground=_hex(GLOW), highlightthickness=2)
        except tk.TclError:
            continue
