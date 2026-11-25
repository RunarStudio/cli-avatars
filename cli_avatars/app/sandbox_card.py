"""SANDBOX on the card panel: a cracked-stone slip with "Try it risky", then the sandbox's branch, Promote and Bin.

Try it risky makes the worktree, its branch and a Claude task chat in it (``sandbox.try_risky``) and opens that
chat in the dock; no CLI starts until Enter there. Promote (the seal) keeps the branch; Bin (the trapdoor) drops it,
and asks once more when the worktree has uncommitted changes. Each plays its cue unless another task is in focus.
"""

from __future__ import annotations

import tkinter as tk

import sandbox
from cli_avatars.app.sandbox_cues import cue

STONE, STONE_HI, EMBER, RUNE, PAPER, INK, SOFT, WINE, GOLD, ERR = (
    "#2b2433", "#4a3f55", "#ff6a2a", "#ffb347", "#efe3c2", "#2a1c10", "#6b5233", "#7a1f3d", "#ffcf4a", "#a02818")
TABLET = (
    ".kkkkkkkk.",
    "kssssssssk",
    "ksshsrsssk",
    "kssrrrsssk",
    "ksssrsxssk",
    "kssrsrxssk",
    "ksssssxxsk",
    "kssssxsssk",
    "kssssxsssk",
    ".kkkkkkkk.",
)
SEAL = ("..gggg..", ".gGGGGg.", "gGGrrGGg", "gGrGGrGg", "gGGrrGGg", ".gGGGGg.", "..gggg..", "..g..g..")
TRAPDOOR = ("wwwwwwww", "wbwbbwbw", "wbwbbwbw", "wwwwwwww", "wbwiibbw", "wbwiibbw", "wwwwwwww")
COLOURS = {"k": "#141018", "s": "#5a4e66", "h": "#7a6e88", "r": RUNE, "x": "#0a070c", "g": "#8a5a10",
           "G": GOLD, "w": "#6a4422", "b": "#3a2412", "i": "#b0b0c0"}


def icon(parent, bg: str, grid: tuple[str, ...], scale: int = 2) -> tk.Canvas:
    """A canvas painted from ``grid``, one character per pixel."""
    canvas = tk.Canvas(parent, width=len(grid[0]) * scale, height=len(grid) * scale, bg=bg, highlightthickness=0,
                       bd=0)
    for row, line in enumerate(grid):
        for col, char in enumerate(line):
            if char in COLOURS:
                canvas.create_rectangle(col * scale, row * scale, (col + 1) * scale, (row + 1) * scale,
                                        fill=COLOURS[char], width=0)
    return canvas


def button(parent, text: str, command, bg: str, fg: str = PAPER) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=GOLD, activeforeground=INK,
                     relief="flat", bd=0, font="DungeonText", padx=8, pady=1, cursor="hand2", highlightthickness=0,
                     compound="left")


class SandboxSection:
    """``directory()`` is the data dir, ``open_chat(room, new)`` shows a chat, ``play(name)`` plays a cue."""

    def __init__(self, sheet, directory, after, open_chat, play) -> None:
        self._directory = directory
        self._open_chat = open_chat
        self._play = play
        self.card: dict | None = None
        self.row: dict | None = None
        self._stamp: tuple | None = None
        self.frame = tk.Frame(sheet, bg=PAPER, highlightthickness=2, highlightbackground=STONE)
        band = tk.Frame(self.frame, bg=STONE)
        band.pack(fill="x")
        icon(band, STONE, TABLET).pack(side="left", padx=(5, 4), pady=2)
        tk.Label(band, text="SANDBOX", bg=STONE, fg=RUNE, font="DungeonBubble").pack(side="left")
        self.state = tk.Label(band, text="", bg=STONE, fg=EMBER, font="DungeonBubble")
        self.state.pack(side="right", padx=5)
        self.try_button = button(band, "⚠ Try it risky", self.try_it, WINE)
        self.line = tk.Frame(self.frame, bg=PAPER)
        tk.Label(self.line, text="branch", bg=PAPER, fg=SOFT, font="DungeonBubble").pack(side="left")
        button(self.line, "Copy", self.copy, STONE_HI).pack(side="right")
        self.branch = tk.Entry(self.line, bg=PAPER, fg=WINE, relief="flat", font="DungeonText", width=10,
                               readonlybackground=PAPER, highlightthickness=0)
        self.branch.pack(side="left", fill="x", expand=True, padx=4)
        self.actions = tk.Frame(self.frame, bg=PAPER)
        icon(self.actions, PAPER, SEAL).pack(side="left", padx=(0, 3))
        self.promote_button = button(self.actions, "Promote", self.promote, "#5a3a08", GOLD)
        self.promote_button.pack(side="left")
        icon(self.actions, PAPER, TRAPDOOR).pack(side="left", padx=(10, 3))
        self.bin_button = button(self.actions, "Bin", self.bin, STONE)
        self.bin_button.pack(side="left")
        self.chat_button = button(self.actions, "Open chat", self.open, STONE_HI)
        self.chat_button.pack(side="right")
        self.confirm_button = button(self.frame, "Bin anyway: lose the changes", lambda: self.bin(True), ERR)
        self.message = tk.Label(self.frame, text="", bg=PAPER, fg=WINE, font="DungeonBubble", anchor="w",
                                justify="left", wraplength=290)
        self.frame.pack(fill="x", padx=8, pady=(6, 0), after=after)

    def fill(self, card: dict, note: str = "") -> None:
        self.card = card
        self._stamp = sandbox.stamp(self._directory())
        self.row = row = sandbox.view(sandbox.for_card(self._directory(), card["id"]))
        live = row is not None and row["state"] == sandbox.LIVE
        for widget in (self.try_button, self.line, self.actions, self.confirm_button, self.message):
            widget.pack_forget()
        if not live:
            self.try_button.pack(side="right", padx=4, pady=2, before=self.state)
        if row is not None and row["state"] != sandbox.BINNED:
            self.line.pack(fill="x", padx=6, pady=(3, 0))
            self.branch.config(state="normal")
            self.branch.delete(0, "end")
            self.branch.insert(0, row["branch"])
            self.branch.config(state="readonly")
        if live:
            self.actions.pack(fill="x", padx=6, pady=(3, 2))
        self.state.config(text="" if row is None else row["state"])
        self._say(note or _note(row), WINE)

    def tick(self) -> None:
        if self.card is not None and sandbox.stamp(self._directory()) != self._stamp:
            self.fill(self.card)

    def try_it(self) -> None:
        if self.card is None:
            return
        from registry.facade import Registry

        try:
            made = sandbox.try_risky(Registry(self._directory()), self.card["id"])
        except sandbox.Refused as exc:
            return self._refused(exc.why)
        self.fill(self.card)
        cue(self._directory(), self._play, "risky", self.card["id"])
        self._open_chat(made["room"], True)

    def promote(self) -> None:
        if self.row is None:
            return
        try:
            done = sandbox.promote(self._directory(), self.row["id"])
        except sandbox.Refused as exc:
            return self._refused(exc.why)
        self.fill(self.card)
        cue(self._directory(), self._play, "seal", done["card"])

    def bin(self, confirm: bool = False) -> None:
        if self.row is None:
            return
        try:
            done = sandbox.bin_sandbox(self._directory(), self.row["id"], confirm=confirm)
        except sandbox.Dirty as exc:
            self._refused(exc.why[0].upper() + exc.why[1:])
            self.confirm_button.pack(anchor="w", padx=6, pady=(0, 2), before=self.message)
            return
        except sandbox.Refused as exc:
            return self._refused(exc.why)
        self.fill(self.card)
        cue(self._directory(), self._play, "trapdoor", done["card"])

    def open(self) -> None:
        if self.row is not None:
            self._open_chat(self.row["room"], False)

    def copy(self) -> None:
        self.frame.clipboard_clear()
        self.frame.clipboard_append(self.branch.get())
        self._say("Branch name copied.", WINE)

    def _refused(self, why: str) -> None:
        self._say(why, ERR)

    def _say(self, text: str, colour: str) -> None:
        self.message.config(text=text, fg=colour)
        if text:
            self.message.pack(fill="x", padx=6, pady=(0, 5))
        else:
            self.message.pack_forget()


def _note(row: dict | None) -> str:
    if row is None:
        return ""
    if row["state"] == sandbox.LIVE:
        return "Its chat works in the sandbox folder. Nothing is pushed or merged."
    if row["state"] == sandbox.PROMOTED:
        kept = " The folder stays: it had uncommitted changes." if row["kept"] else ""
        return "Promoted: the branch is yours. Merge or push it by hand." + kept
    return f"Binned: {row['branch']} is gone."
