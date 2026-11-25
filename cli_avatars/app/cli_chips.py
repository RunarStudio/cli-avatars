"""CHAT-CTX.1: the composer's Run row: Inbox | Claude | Grok | Cursor as kit chips, each with its source's gem.

A chip is a plate with a pixel gem drawn in code in the CLI's colour (Claude a round stone, Grok a diamond, Cursor
an arrow, Inbox a letter). The lit chip takes its colour as its edge; a greyed chip keeps its hint in ``why`` and
shows it in the status line when clicked. Picking a chip starts nothing. HIERARCHY.1: a tier chip at the row's end
shows the room's tier with its model and effort.
"""

from __future__ import annotations

import tkinter as tk

from cli_avatars.app.chat_clis import COLORS, INBOX, NAMES, targets

PLATE, FACE, INK, OFF_INK, EDGE = "#0e1420", "#1a2438", "#aaccff", "#555a70", "#2a3048"
FONT = ("Courier", 8, "bold")
PX = 2
GEMS = {
    INBOX: ("111111", "110011", "101101", "100001", "111111"),
    "claude": ("011110", "111111", "111111", "111111", "011110"),
    "grok": ("001100", "011110", "111111", "011110", "001100"),
    "cursor": ("100000", "111000", "111110", "111000", "100100"),
}


class Chip(tk.Frame):
    """One target. ``enabled`` and ``why`` come from ``chat_clis.state``."""

    def __init__(self, parent, key: str, on_pick) -> None:
        super().__init__(parent, bg=EDGE, padx=1, pady=1, cursor="hand2")
        self.key, self.enabled, self.lit, self.why = key, True, False, ""
        face = tk.Frame(self, bg=PLATE)
        face.pack()
        rows = GEMS[key]
        self.gem = tk.Canvas(face, width=len(rows[0]) * PX, height=len(rows) * PX, bg=PLATE, highlightthickness=0)
        self.gem.pack(side="left", padx=(5, 3), pady=3)
        self.label = tk.Label(face, text="Inbox" if key == INBOX else NAMES[key], bg=PLATE, fg=INK, font=FONT)
        self.label.pack(side="left", padx=(0, 6))
        self.face = face
        for widget in (self, face, self.gem, self.label):
            widget.bind("<Button-1>", lambda _e: on_pick(key))
        self.paint()

    def set(self, enabled: bool, lit: bool, why: str) -> None:
        if (enabled, lit, why) != (self.enabled, self.lit, self.why):
            self.enabled, self.lit, self.why = enabled, lit, why
            self.paint()

    def paint(self) -> None:
        colour = COLORS[self.key] if self.enabled else OFF_INK
        face = FACE if self.lit else PLATE
        self.config(bg=colour if self.lit else EDGE, cursor="hand2" if self.enabled else "arrow")
        for widget in (self.face, self.gem, self.label):
            widget.config(bg=face)
        self.label.config(fg="#ffffff" if self.lit else INK if self.enabled else OFF_INK)
        self.gem.delete("all")
        for y, row in enumerate(GEMS[self.key]):
            for x, bit in enumerate(row):
                if bit == "1":
                    shade = "#ffffff" if self.enabled and y == 1 and 0 < x < 3 and self.key != INBOX else colour
                    self.gem.create_rectangle(x * PX, y * PX, x * PX + PX - 1, y * PX + PX - 1, fill=shade, width=0)


def copy_context(pane) -> None:
    """Daniel's click: the pack and task context as text, for a web or IDE chat. Starts nothing."""
    from types import SimpleNamespace

    from cli_avatars.app import pack_pane
    from cli_avatars.app.chat_clis import copy_text
    from events import EventRejected

    if not pane.room_id:
        return
    try:
        text = copy_text(pane.window.directory(), pane.room_id)
        pane.window.master.clipboard_clear()
        pane.window.master.clipboard_append(text)
    except (EventRejected, OSError, tk.TclError):
        pane._status("Not copied")
        return
    pack_pane.started(pane.window.directory(), pane.window._config(), SimpleNamespace(preamble=text))
    pane._status(f"Copied {len(text)} characters: paste them in Grok on the web or the Cursor IDE.")


def line(pane, cli: str, text: str, tag: str) -> None:
    """One transcript line, tagged with the CLI it came from in that CLI's colour."""
    pane._write(f"{NAMES.get(cli, cli)} › ", f"src-{cli}" if cli in NAMES else "note")
    pane._write(("· " if tag == "tool" else "") + text + "\n", tag)


def reload(pane) -> None:
    """The room's CLI turns, oldest first, each tagged with its CLI, in place of the transcript."""
    from board.model import CHAT_CLIS
    from cli_avatars.app import room_log
    from registry import task_chats

    if pane._term is None or pane.cli_target() is None:
        return
    pane._clear()
    if task := task_chats.shown(pane.window.directory(), pane.room_id):
        pane._write(task + "\n", "note")
    rows = sorted(((ts, cli, sender, text) for cli in CHAT_CLIS for sender, text, ts in
                   room_log.history(pane.window.directory(), pane.room_id, cli, stamped=True)), key=lambda r: r[0])
    for _ts, cli, sender, text in rows:
        if sender == "user":
            pane._write(f"> {text}\n", "prompt")
        else:
            pane._line(cli, text, "reply")
    if pane.room_id in pane._runs:
        pane._write("… still answering\n", "note")


class TierChip(tk.Frame):
    """HIERARCHY.1: the tier a send from this room takes: its glyph (crown, banner, scroll, spark), model and effort."""

    def __init__(self, parent) -> None:
        super().__init__(parent, bg=EDGE, padx=1, pady=1)
        face = tk.Frame(self, bg=PLATE)
        face.pack()
        self.gem = tk.Canvas(face, width=7 * PX, height=5 * PX, bg=PLATE, highlightthickness=0)
        self.gem.pack(side="left", padx=(5, 3), pady=3)
        self.label = tk.Label(face, text="", bg=PLATE, fg=INK, font=FONT)
        self.label.pack(side="left", padx=(0, 6))
        self.shown: dict | None = None

    def set(self, chip: dict) -> None:
        if chip == self.shown:
            return
        self.shown = chip
        self.config(bg=chip["color"])
        self.label.config(text=chip["label"], fg=chip["color"])
        self.gem.delete("all")
        for y, row in enumerate(chip["rows"]):
            for x, bit in enumerate(row):
                if bit == "1":
                    self.gem.create_rectangle(x * PX, y * PX, x * PX + PX - 1, y * PX + PX - 1, fill=chip["color"],
                                              width=0)


def build(parent, on_pick) -> dict[str, Chip]:
    chips = {}
    for key in targets():
        chip = Chip(parent, key, on_pick)
        chip.pack(side="left", padx=2)
        chips[key] = chip
    parent.tier_chip = TierChip(parent)
    parent.tier_chip.pack(side="right", padx=2)
    return chips


def paint(chips: dict[str, Chip], target: str, states: dict, tier: dict | None = None) -> None:
    for key, chip in chips.items():
        state = states.get(key)
        enabled = True if state is None else state.enabled
        chip.set(enabled, key == target, "" if state is None else state.why)
    bar = next(iter(chips.values())).master if chips else None
    if tier is not None and getattr(bar, "tier_chip", None) is not None:
        bar.tier_chip.set(tier)
