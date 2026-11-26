"""GROK-ORCH.1 desktop: "Ask a bot…" from a task card or a chat, the card's bot asks, and the answer watch.

The picker is a kit card over the Dungeon (not a window): the roster's groups, a search line, the ask, Send. Send
writes one hand-off file (``bot_bridge.ask``); several asks can be open at once. The card's slip lists them with
pending, answered or stale and the answer. ``step`` (from the bubbles tick, about once a second) lands new answers in
the chat and the card and plays the ``answer`` cue, held while another task is in focus. Nothing here runs a bot.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from pathlib import Path

import bot_bridge
import text_fonts as fonts
from cli_avatars.app import kit_card as kc
from cli_avatars.app.throttle import StoreThrottle

STATE_INK = {bot_bridge.PENDING: "#8a5a10", bot_bridge.ANSWERED: "#2f6b2a", bot_bridge.STALE: "#a02818"}
WATCH_S = 1.0
SHOWN = 6


def roster(directory: Path | str):
    from bots.roster import Roster, RosterError, load_roster

    try:
        return load_roster(Path(directory) / "bots" / "roster.json")
    except (RosterError, OSError, ValueError):
        return Roster.empty()


def bridge_root(directory: Path | str, config: object = None) -> Path:
    """The bridge folder from ``config`` (the app's), else from config.json as Settings saved it."""
    if config is None:
        from cli_avatars.paths import config_path
        from rooms import load_config

        config = load_config(config_path())
    return bot_bridge.root(directory, config)


def choices(found, query: str = "") -> list[tuple[str, str]]:
    """``(bot id, "Group · Name")`` in group order; ``query`` keeps names or groups that contain it."""
    from bots.roster import grouped

    words = query.strip().lower()
    out = []
    for group, bots in grouped(found):
        for bot in bots:
            label = f"{group.name} · {bot.name}"
            if not words or words in label.lower():
                out.append((bot.id, label))
    return out


def open_picker(root, directory, card: str = "", room: str = "", on_sent=None) -> "Picker":
    found = getattr(root, "_bot_picker", None)
    if found is not None and found.card.alive():
        found.card.close()
    root._bot_picker = Picker(root, directory, card, room, on_sent)
    return root._bot_picker


class Picker:
    def __init__(self, root, directory, card: str = "", room: str = "", on_sent=None) -> None:
        self.directory, self.card_id, self.room, self.on_sent = directory, card, room, on_sent
        self.roster = roster(directory)
        self.card = kc.Card(root, "Ask a bot", width=420)
        body = self.card.body
        kc.note(body, "The ask goes to your bots' app as a file; the answer lands in this task's chat and card.")
        row = tk.Frame(body, bg=kc.PARCH)
        row.pack(fill="x", pady=(4, 2))
        tk.Label(row, text="Find", bg=kc.PARCH, fg=kc.SOFT, font="DungeonText", width=6, anchor="w").pack(side="left")
        self.search = tk.Entry(row, bg=kc.PAPER, fg=kc.INK, insertbackground=kc.INK, relief="flat", font="DungeonText",
                               highlightthickness=1, highlightbackground=kc.EDGE, highlightcolor=kc.WINE)
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<KeyRelease>", lambda _e: self._fill())
        self.list = tk.Listbox(body, height=8, bg=kc.PAPER, fg=kc.INK, selectbackground=kc.GOLD,
                               selectforeground=kc.INK, font="DungeonText", relief="flat", highlightthickness=1,
                               highlightbackground=kc.EDGE, activestyle="none", exportselection=False)
        self.list.pack(fill="x", pady=2)
        tk.Label(body, text="Ask", bg=kc.PARCH, fg=kc.SOFT, font="DungeonText", anchor="w").pack(fill="x")
        self.text = tk.Text(body, height=3, bg=kc.PAPER, fg=kc.INK, insertbackground=kc.INK, relief="flat",
                            font="DungeonText", wrap="word", highlightthickness=1, highlightbackground=kc.EDGE)
        self.text.pack(fill="x")
        foot = tk.Frame(body, bg=kc.PARCH)
        foot.pack(fill="x", pady=(6, 0))
        self.status = tk.Label(foot, text="", bg=kc.PARCH, fg=kc.BAD_INK, font="DungeonBubble", anchor="w",
                               justify="left", wraplength=280)
        self.status.pack(side="left", fill="x", expand=True)
        self.send_btn = kc.button(foot, "Send", self.send)
        self.send_btn.pack(side="right")
        self.ids: list[str] = []
        self._fill()
        if not self.ids:
            self.status.config(text="No bots yet: import the roster in Settings › Bots.")

    def _fill(self) -> None:
        picked = self.picked()
        self.list.delete(0, "end")
        rows = choices(self.roster, self.search.get())
        self.ids = [bot for bot, _label in rows]
        for _bot, label in rows:
            self.list.insert("end", label)
        if picked in self.ids:
            self.list.selection_set(self.ids.index(picked))
        elif self.ids:
            self.list.selection_set(0)

    def picked(self) -> str:
        sel = self.list.curselection() if hasattr(self, "list") else ()
        return self.ids[sel[0]] if sel and sel[0] < len(self.ids) else ""

    def pick(self, bot: str) -> None:
        if bot in self.ids:
            self.list.selection_clear(0, "end")
            self.list.selection_set(self.ids.index(bot))

    def send(self) -> dict | None:
        """Daniel's Send: one hand-off file; the card closes, the slip shows it pending."""
        bot, text = self.picked(), self.text.get("1.0", "end").strip()
        if not bot or not text:
            self.status.config(text="Pick a bot and write the ask.")
            return None
        row = bot_bridge.ask(self.directory, bridge_root(self.directory), self.roster, bot, text, card=self.card_id,
                             room=self.room)
        if row is None:
            self.status.config(text="The ask was not written: check the bridge folder in Settings › Chat.")
            return None
        self.card.close()
        if self.on_sent is not None:
            self.on_sent(row)
        return row


class AskSection:
    """The card's BOT ASKS slip: Ask a bot…, then each ask with its state and answer. ``directory()`` is the data
    dir; ``open_picker(card)`` opens the picker for the card."""

    def __init__(self, sheet, directory, after, root) -> None:
        self._directory, self._root = directory, root
        self.card: dict | None = None
        self._stamp: tuple | None = None
        self.frame = tk.Frame(sheet, bg=kc.PAPER, highlightthickness=1, highlightbackground=kc.EDGE)
        band = tk.Frame(self.frame, bg=kc.PAPER)
        band.pack(fill="x", padx=6, pady=(3, 0))
        self.title = tk.Label(band, text="Bot asks", bg=kc.PAPER, fg=kc.WINE, font="DungeonTitle", anchor="w")
        self.title.pack(side="left")
        self.ask_btn = kc.button(band, "Ask a bot…", self.ask)
        self.ask_btn.pack(side="right")
        self.rows = tk.Frame(self.frame, bg=kc.PAPER)
        self.rows.pack(fill="x", padx=6, pady=(2, 4))
        self.frame.pack(fill="x", padx=8, pady=(6, 0), after=after)

    def ask(self) -> None:
        if self.card is not None:
            open_picker(self._root, self._directory(), card=self.card["id"], on_sent=lambda _row: self.fill(self.card))

    def fill(self, card: dict) -> None:
        self.card = card
        bridge = bridge_root(self._directory())
        self._stamp = bot_bridge.stamp(bridge)
        found = bot_bridge.listing(bridge, card=card["id"])
        open_n = bot_bridge.open_count(found)
        self.title.config(text=f"Bot asks ({open_n} open)" if open_n else "Bot asks")
        for child in self.rows.winfo_children():
            child.destroy()
        if not found:
            tk.Label(self.rows, text="None yet. Ask a bot… sends this task to one of your bots.", bg=kc.PAPER,
                     fg=kc.SOFT, font="DungeonBubble", anchor="w").pack(fill="x")
        for row in found[:SHOWN]:
            line = tk.Frame(self.rows, bg=kc.PAPER)
            line.pack(fill="x", pady=1)
            tk.Label(line, text=row["status"], bg=kc.PAPER, fg=STATE_INK[row["status"]], font="DungeonBubble",
                     width=8, anchor="w").pack(side="left")
            tk.Label(line, text=f"{row['bot_name']}: {row['ask']}"[:80], bg=kc.PAPER, fg=kc.INK, font="DungeonBubble",
                     anchor="w").pack(side="left", fill="x", expand=True)
            if row["answer"]:
                tk.Label(self.rows, text="  " + row["answer"][:300], bg=kc.PAPER, fg="#2f6b2a",
                         font=fonts.face(8), anchor="w", justify="left", wraplength=290).pack(fill="x")

    def tick(self) -> None:
        if self.card is not None and bot_bridge.stamp(bridge_root(self._directory())) != self._stamp:
            self.fill(self.card)


def step(app, now: float | None = None) -> list[dict]:
    """Land new answers (about once a second): chat line, card comment, the ``answer`` cue unless focus holds it."""
    gate = getattr(app, "_bridge_gate", None)
    if gate is None:
        gate = app._bridge_gate = StoreThrottle(WATCH_S)
    if not gate.due():
        return []
    gate.mark()
    try:
        directory = app._chat_directory()
        landed = bot_bridge.sync(directory, bridge_root(directory, getattr(app, "config", None)),
                                 time.time() if now is None else now)
    except Exception:
        logging.getLogger("cli_avatars.bridge").exception("bridge watch failed")
        return []
    if landed:
        from cli_avatars.app import chime_cues

        chime_cues.cue(app, "answer")
    return landed
