"""CONTEXT-PACKS on the card panel: a leather-banded slip with the satchel, the pack's four parts, pin, unpin, edit.

Lines are text only. Writes go straight to ``context_packs`` (the pack is not card data); the slip redraws only
when the pack changes, and ``tick`` notices a pin made elsewhere (the phone).
"""

from __future__ import annotations

import tkinter as tk

import context_packs
import text_fonts as fonts
from cli_avatars.app import pack_art

LEATHER = pack_art.LEATHER
PARCH, PAPER, EDGE, INK, SOFT, WINE, GOLD, ERR = (
    "#d8c8a0", "#efe3c2", "#8a6a3a", "#2a1c10", "#6b5233", "#7a1f3d", "#ffcf4a", "#a02818")  # the card's sheet
LABELS = {"summary": "SUMMARY", "decisions": "DECISIONS", "files": "FILES", "links": "LINKS"}
EMPTY = "Empty for now: the summary, decisions, files and links fill it as the task moves."


def _entry(parent, width: int) -> tk.Entry:
    return tk.Entry(parent, bg=PARCH, fg=INK, insertbackground=INK, relief="flat", font="DungeonText", width=width,
                    highlightthickness=1, highlightbackground=EDGE, highlightcolor=WINE)


def button(parent, text: str, command, bg: str = WINE, fg: str = PAPER) -> tk.Button:
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=GOLD, activeforeground=INK,
                     relief="flat", bd=0, font="DungeonText", padx=8, pady=1, cursor="hand2", highlightthickness=0)


class PackSection:
    """``directory()`` is the data dir. ``fill(card)`` after any card change; ``tick()`` once a second."""

    def __init__(self, sheet, directory, after) -> None:
        self._directory = directory
        self.card: dict | None = None
        self.pack: dict | None = None
        self._sig: tuple | None = None
        self._stamp: tuple | None = None
        self.rows: dict[str, tk.Frame] = {}
        self.frame = tk.Frame(sheet, bg=PAPER, highlightthickness=2, highlightbackground=LEATHER)
        band = tk.Frame(self.frame, bg=LEATHER)
        band.pack(fill="x")
        pack_art.icon(band, LEATHER).pack(side="left", padx=(5, 4), pady=2)
        tk.Label(band, text=fonts.caps("CONTEXT PACK"), bg=LEATHER, fg=GOLD, font="DungeonBubble").pack(side="left")
        self.size = tk.Label(band, text="", bg=LEATHER, fg=PARCH, font="DungeonBubble")
        self.size.pack(side="right", padx=5)
        tk.Label(self.frame, text="Every new chat on this task starts with this pack.", bg=PAPER, fg=SOFT,
                 font="DungeonBubble", anchor="w", justify="left", wraplength=290).pack(fill="x", padx=6)
        row = tk.Frame(self.frame, bg=PAPER)
        row.pack(fill="x", padx=6, pady=(2, 0))
        self.part = tk.StringVar(row, "decisions")
        self.part_button = tk.Menubutton(row, textvariable=self.part, bg=PARCH, fg=WINE, relief="flat",
                                         font="DungeonBubble", width=9, activebackground=GOLD)
        menu = tk.Menu(self.part_button, tearoff=0, bg=PAPER, fg=INK, activebackground=WINE, activeforeground=PAPER)
        for part in context_packs.PARTS:
            menu.add_command(label=part, command=lambda p=part: self.part.set(p))
        self.part_button.config(menu=menu)
        self.part_button.pack(side="left")
        self.entry = _entry(row, 14)
        button(row, "Pin", self.pin_typed).pack(side="right")
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry.bind("<Return>", lambda _e: self.pin_typed())
        self.error = tk.Label(self.frame, text="", bg=PAPER, fg=ERR, font="DungeonBubble", anchor="w")
        self.error.pack(fill="x", padx=6)
        self.body = tk.Frame(self.frame, bg=PAPER)
        self.body.pack(fill="x", padx=6, pady=(0, 5))
        self.frame.pack(fill="x", padx=8, pady=(6, 0), after=after)

    def fill(self, card: dict, force: bool = False) -> None:
        self.card = card
        self._stamp = context_packs.stamp(self._directory())
        pack = context_packs.build(self._directory(), card)
        sig = tuple((x["key"], x["text"], x["pinned"]) for lines in pack["parts"].values() for x in lines)
        if sig == self._sig and not force:
            return
        self.pack, self._sig = pack, sig
        self.size.config(text=f"{pack['chars']}/{pack['limit']}" + (f" · {pack['dropped']} left out"
                                                                    if pack["dropped"] else ""))
        for child in self.body.winfo_children():
            child.destroy()
        self.rows = {}
        if not sig:
            tk.Label(self.body, text=EMPTY, bg=PAPER, fg=SOFT, font="DungeonBubble", anchor="w", justify="left",
                     wraplength=280).pack(fill="x")
        for part, lines in pack["parts"].items():
            if lines:
                self._part(part, lines)

    def tick(self) -> None:
        if self.card is not None and context_packs.stamp(self._directory()) != self._stamp:
            self.fill(self.card)

    def pin_typed(self) -> None:
        if self._write(context_packs.pin, self.part.get(), self.entry.get()):
            self.entry.delete(0, "end")

    def pin(self, line: dict) -> bool:
        return self._write(context_packs.pin, line["part"], line["text"])

    def unpin(self, line: dict) -> bool:
        return self._write(context_packs.unpin, line["key"])

    def edit(self, line: dict) -> None:
        """Swap the line for an entry: Enter saves, Escape puts the line back."""
        row = self.rows[line["key"]]
        for child in row.winfo_children():
            child.destroy()
        entry = _entry(row, 24)
        entry.insert(0, line["text"])
        entry.pack(fill="x")
        entry.bind("<Return>", lambda _e: self._write(context_packs.edit, line["key"], entry.get()))
        entry.bind("<Escape>", lambda _e: self.fill(self.card, force=True))
        entry.focus_set()
        row.entry = entry

    def _part(self, part: str, lines: list[dict]) -> None:
        head = tk.Frame(self.body, bg=PAPER)
        head.pack(fill="x", pady=(2, 0))
        pack_art.icon(head, PAPER, pack_art.PART_ICONS[part], 1).pack(side="left", padx=(0, 4))
        tk.Label(head, text=LABELS[part], bg=PAPER, fg=WINE, font="DungeonBubble").pack(side="left")
        for line in lines:
            row = tk.Frame(self.body, bg=PAPER, highlightthickness=1 if line["pinned"] else 0,
                           highlightbackground=GOLD)
            row.pack(fill="x", padx=(10, 0), pady=1)
            mark = tk.Canvas(row, width=6, height=8, bg=PAPER, highlightthickness=0, bd=0)
            if line["pinned"]:
                mark.create_rectangle(0, 0, 6, 4, fill=GOLD, outline=WINE)
                mark.create_rectangle(2, 4, 4, 8, fill=WINE, width=0)
            else:
                mark.create_rectangle(2, 3, 4, 5, fill=EDGE, width=0)
            mark.pack(side="left", padx=(0, 4))
            for text, command in (("✕", lambda x=line: self.unpin(x)), ("✎", lambda x=line: self.edit(x)),
                                  *([] if line["pinned"] else [("pin", lambda x=line: self.pin(x))])):
                small = button(row, text, command, PARCH, WINE)
                small.config(padx=3, font="DungeonBubble")
                small.pack(side="right")
            tk.Label(row, text=line["text"], bg=PAPER, fg=INK, font="DungeonText", anchor="w", justify="left",
                     wraplength=200).pack(side="left", fill="x", expand=True)
            row.line = line
            self.rows[line["key"]] = row

    def _write(self, fn, *args) -> bool:
        if self.card is None:
            return False
        try:
            ok = fn(self._directory(), self.card["id"], *args)
        except OSError:
            ok = False
        self.error.config(text="" if ok else "Not pinned: files are repo paths, links start with http(s)://.")
        if ok:
            self.fill(self.card)
        return ok
