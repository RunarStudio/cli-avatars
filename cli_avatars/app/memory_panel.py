"""MEMORY.1 desktop: the read-only "Memory" tab in the Dungeon's centre (docs/memory.md).

The category/topic tree, topic cards with their next action on top, the inbox count, the curator's last run with
its commit and any warning, Consolidate now and Open in Obsidian. The one write is Remember: one block appended to
the app's inbox. Note text is shown as data. No new window.
"""

from __future__ import annotations

import time
import tkinter as tk

from cli_avatars.app import memory_actions as ma
from cli_avatars.app import memory_inbox as mi
from cli_avatars.app import memory_notes as mn
from cli_avatars.app import topic_rooms as tr

BG, CARD, CARD_ON, EDGE, EDGE_ON = "#141018", "#1b1524", "#22183a", "#33284a", "#ffcf4a"
INK, DIM, GOLD, BAD, OK, FIELD = "#e8e6f4", "#9a98b8", "#ffcf4a", "#ff8866", "#7dff8a", "#0d0a14"
REFRESH_S = 1.0
_HOOK: list = [None]


def install(view) -> None:
    """Chat lines and task cards offer Remember through this hook."""
    _HOOK[0] = lambda text, source, topic="": remember(view.app, text, source, topic)


def offer(text: str, source: str, topic: str = "") -> bool:
    hook = _HOOK[0]
    if hook is None:
        return False
    hook(text, source, topic)
    return True


def remember_card(card: dict) -> bool:
    """A task card's title into the Remember form."""
    return offer(card.get("title", ""), f"task:{str(card.get('id', ''))[:8]}", card.get("topic") or "")


def ensure(view) -> MemoryPanel:
    panel = getattr(view.app, "_memory_panel", None)
    if panel is None:
        panel = view.app._memory_panel = MemoryPanel(view.app, view._memory)
    return panel


def opened(view) -> None:
    ensure(view).refresh(force=True)


def step(app) -> None:
    """From the tick: redraw at most once a second while shown; a cue when a consolidation finishes."""
    panel = getattr(app, "_memory_panel", None)
    if panel is not None:
        panel.watch(getattr(getattr(app, "dungeon", None), "_center", "") == "memory")


def remember(app, text: str, source: str, topic: str = "") -> None:
    """Open the Memory tab with the Remember form filled from a chat line or a task card."""
    view = getattr(app, "dungeon", None)
    if view is None:
        return
    view.show_center("memory")
    ensure(view).fill(text, source, topic)


def show_topic(app, key: str) -> None:
    view = getattr(app, "dungeon", None)
    if view is None:
        return
    view.show_center("memory")
    panel = ensure(view)
    panel.selected = key
    panel.refresh(force=True)


class MemoryPanel:
    def __init__(self, app, parent) -> None:
        self.app, self.parent = app, parent
        self.selected = ""
        self._key = None
        self._at = 0.0
        self._last_run = None
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(head, text="Memory", bg=BG, fg=GOLD, font="DungeonTitle", anchor="w").pack(side="left")
        self.obsidian_button = self._button(head, "Open in Obsidian", self.open_obsidian)
        self.obsidian_button.pack(side="right", padx=(6, 0))
        self.consolidate_button = self._button(head, "Consolidate now", self.consolidate)
        self.consolidate_button.pack(side="right")
        self.line = tk.Label(parent, text="", bg=BG, fg=DIM, font="DungeonText", anchor="w", justify="left")
        self.line.pack(fill="x", padx=14)
        self.warn = tk.Label(parent, text="", bg=BG, fg=BAD, font="DungeonText", anchor="w", justify="left")
        self.warn.pack(fill="x", padx=14)
        self._form(parent)
        body = tk.Frame(parent, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        self.tree = tk.Frame(body, bg=BG, width=190)
        self.tree.pack(side="left", fill="y")
        self.tree.pack_propagate(False)
        self.cards = tk.Frame(body, bg=BG)
        self.cards.pack(side="left", fill="both", expand=True, padx=(10, 0))

    def _form(self, parent) -> None:
        box = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=EDGE)
        box.pack(fill="x", padx=14, pady=(6, 0))
        tk.Label(box, text="Remember", bg=CARD, fg=GOLD, font="DungeonText").grid(row=0, column=0, sticky="w",
                                                                                padx=6, pady=3)
        self.kind = tk.StringVar(value="learning")
        self._menu(box, self.kind, mi.TYPES).grid(row=0, column=1, sticky="w")
        self.text = tk.Entry(box, bg=FIELD, fg=INK, insertbackground=GOLD, relief="flat", font="DungeonText")
        self.text.grid(row=0, column=2, sticky="ew", padx=6, ipady=2)
        self.text.bind("<Return>", lambda _e: self.save())
        self.category = tk.StringVar(value=mn.IDEAS)
        self.category_menu = self._menu(box, self.category, (mn.IDEAS,))
        self.category_menu.grid(row=0, column=3)
        self.topic = tk.Entry(box, bg=FIELD, fg=INK, insertbackground=GOLD, relief="flat", font="DungeonText",
                              width=14)
        self.topic.grid(row=0, column=4, padx=6, ipady=2)
        self.save_button = self._button(box, "Save", self.save)
        self.save_button.grid(row=0, column=5, padx=(0, 6), pady=3)
        self.source = tk.StringVar(value="app")
        self.said = tk.Label(box, text="", bg=CARD, fg=DIM, font="DungeonBubble", anchor="w")
        self.said.grid(row=1, column=0, columnspan=6, sticky="ew", padx=6)
        box.columnconfigure(2, weight=1)

    def _menu(self, parent, var, values) -> tk.OptionMenu:
        menu = tk.OptionMenu(parent, var, *values)
        menu.config(bg=FIELD, fg=INK, activebackground=EDGE, highlightthickness=0, relief="flat", font="DungeonText")
        return menu

    def _button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg="#3a2a1c", fg=GOLD, activebackground="#5a3a1c",
                         activeforeground="white", relief="flat", font="DungeonText", padx=10, pady=2,
                         cursor="hand2")

    def root(self):
        return mn.root(getattr(self.app, "config", None))

    def fill(self, text: str, source: str, topic: str = "") -> None:
        self.text.delete(0, "end")
        self.text.insert(0, mi.one_line(text))
        self.topic.delete(0, "end")
        self.topic.insert(0, mi.name(topic))
        self.source.set(mi.one_line(source, 120) or "app")
        self.said.config(text=f"From {self.source.get()}: pick a type and a category, then Save.", fg=DIM)
        self.text.focus_set()

    def save(self) -> str:
        why = mi.append(self.root(), self.kind.get(), self.text.get(), self.source.get(), self.category.get(),
                        self.topic.get())
        if why:
            self.said.config(text=why, fg=BAD)
            return why
        self.said.config(text="Remembered: it waits in the inbox for the next consolidation.", fg=OK)
        self.text.delete(0, "end")
        self.source.set("app")
        _cue(self.app, "remember")
        self.refresh(force=True)
        return ""

    def consolidate(self) -> str:
        said = ma.consolidate_now(self.root())
        self.line.config(text=said)
        self._key = None
        return said

    def open_obsidian(self) -> bool:
        return ma.open_in_obsidian(self.root())

    def watch(self, shown: bool) -> None:
        now = time.monotonic()
        if now - self._at < REFRESH_S:
            return
        self._at = now
        run = mn.status(self.root())
        stamp = (run.get("at"), run.get("commit"), run.get("ok"))
        if self._last_run is not None and stamp != self._last_run and run.get("ok"):
            _cue(self.app, "consolidated")
        self._last_run = stamp
        if shown:
            self.refresh()

    def refresh(self, force: bool = False) -> None:
        base = self.root()
        ready = mn.exists(base)
        tree = mn.tree(base) if ready else {}
        run = mn.status(base) if ready else {}
        layout = _layout(self.app)
        key = (str(base), ready, mn.inbox_count(base) if ready else 0, tuple(sorted(run.items())),
               tuple((c, tuple((t.name, t.next_action, t.status, t.goal, t.meta.get("updated", "")) for t in rows))
                     for c, rows in tree.items()), self.selected, tuple(tr.load_pins(_pins())),
               tuple(r.get("memory_topic") for r in (layout or {}).get("rooms") or [] if tr.room_type(r) == tr.TOPIC))
        if key == self._key and not force:
            return
        self._key = key
        self._status(base, ready, run)
        self._fill_categories(list(tree) or [mn.IDEAS])
        for child in (*self.tree.winfo_children(), *self.cards.winfo_children()):
            child.destroy()
        if not ready:
            self._missing(base)
            return
        self._tree(tree)
        self._cards(tree, layout)

    def _status(self, base, ready: bool, run: dict) -> None:
        if not ready:
            self.line.config(text=f"No notes folder at {base}.")
            self.warn.config(text="")
            return
        last = (f"last run {run.get('at')} · commit {run.get('commit') or '—'}" if run.get("at")
                else "not consolidated yet")
        waiting = " · consolidating…" if run.get("requested") else ""
        self.line.config(text=f"{base.name}/ · inbox {mn.inbox_count(base)} · {last}{waiting}")
        self.warn.config(text="" if run.get("ok", True) else f"⚠ {run.get('message', 'The last run failed.')}",
                         fg=BAD)

    def _fill_categories(self, names) -> None:
        menu = self.category_menu["menu"]
        menu.delete(0, "end")
        for name in names:
            menu.add_command(label=name, command=lambda n=name: self.category.set(n))
        if self.category.get() not in names:
            self.category.set(mn.IDEAS)

    def _missing(self, base) -> None:
        tk.Label(self.cards, text="Your notes folder is not set up yet. Create lays out MEMORY.md, inbox/, "
                 "Learnings/, Topics/, _log/ and the curator; your notes stay on this PC and your private remote.",
                 bg=BG, fg=DIM, font="DungeonText", wraplength=420, justify="left", anchor="w").pack(fill="x")
        self._button(self.cards, "Create", lambda: self._create(base)).pack(anchor="w", pady=6)

    def _create(self, base) -> None:
        why = mn.create(base)
        self.line.config(text=why or f"Laid out {base}.")
        self.refresh(force=True)

    def _tree(self, tree) -> None:
        for category, rows in tree.items():
            tk.Label(self.tree, text=f"▾ {category}", bg=BG, fg=GOLD, font="DungeonText", anchor="w").pack(fill="x")
            for topic in rows:
                on = topic.key == self.selected
                tk.Button(self.tree, text=f"   {topic.name}", anchor="w", relief="flat", bd=0, cursor="hand2",
                          bg=CARD_ON if on else BG, fg=INK if on else DIM, activebackground=CARD_ON,
                          font="DungeonText", command=lambda k=topic.key: self._pick(k)).pack(fill="x")

    def _pick(self, key: str) -> None:
        self.selected = "" if key == self.selected else key
        self.refresh(force=True)

    def _cards(self, tree, layout) -> None:
        rows = [t for topics in tree.values() for t in topics]
        if self.selected:
            rows = [t for t in rows if t.key == self.selected] or rows
        if not rows:
            tk.Label(self.cards, text="No topics yet: Remember something, then Consolidate now.", bg=BG, fg=DIM,
                     font="DungeonText", anchor="w").pack(fill="x")
            return
        pins = tr.load_pins(_pins())
        for i, topic in enumerate(rows[:12]):
            self._card(topic, i, topic.key in pins, tr.room_of_topic(layout, topic.key))
        self.cards.columnconfigure(0, weight=1)
        self.cards.columnconfigure(1, weight=1)

    def _card(self, topic, i: int, pinned: bool, room: str) -> None:
        on = topic.key == self.selected
        card = tk.Frame(self.cards, bg=CARD, highlightthickness=1, highlightbackground=EDGE_ON if on else EDGE)
        card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
        _wrap(tk.Label(card, text=f"Next: {topic.next_action or '—'}", bg=CARD, fg=GOLD, font="DungeonText",
                       anchor="w")).pack(fill="x", padx=8, pady=(6, 0))
        _wrap(tk.Label(card, text=topic.key, bg=CARD, fg=INK, font="DungeonText", anchor="w")).pack(fill="x", padx=8)
        bits = [b for b in (topic.goal and f"Goal: {topic.goal}", topic.status and f"Status: {topic.status}",
                            topic.meta.get("updated") and f"updated {topic.meta['updated']}") if b]
        _wrap(tk.Label(card, text=" · ".join(bits), bg=CARD, fg=DIM, font="DungeonBubble",
                       anchor="w")).pack(fill="x", padx=8)
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=8, pady=(2, 6))
        if topic.meta.get("type", "").lower() in mn.TOPIC_TYPES:
            pin = tk.BooleanVar(value=pinned)
            tk.Checkbutton(row, text="Pin room", variable=pin, command=lambda: self._pin(topic.key, pin.get()),
                           bg=CARD, fg=DIM, selectcolor=FIELD, activebackground=CARD, font="DungeonBubble",
                           highlightthickness=0).pack(side="left")
        if room:
            self._button(row, "Go to room", lambda: _go(self.app, room)).pack(side="right")

    def _pin(self, key: str, on: bool) -> None:
        tr.set_pin(_pins(), key, on)
        model = getattr(self.app, "_session_rooms", None)
        feed = getattr(model, "topics", None)
        if feed is not None and model is not None:
            model.topics = tr.feed(self.app)
        self.refresh(force=True)


def _wrap(label: tk.Label) -> tk.Label:
    """A card line that wraps to the card's width, so the card grows instead of cutting it."""
    label.config(justify="left", wraplength=160)
    label.bind("<Configure>", lambda e: label.config(wraplength=max(60, e.width - 4)))
    return label


def _pins():
    from events import app_data_dir

    return app_data_dir() / tr.PINS


def _layout(app):
    from cli_avatars.app.session_rooms import model_for

    try:
        return model_for(app).layout(time.time())
    except Exception:
        return None


def _go(app, room: str) -> None:
    from cli_avatars.app import dungeon_nav

    view = getattr(app, "dungeon", None)
    if view is not None:
        view.show_center("dungeon")
        dungeon_nav.jump(app, room)


def _cue(app, name: str) -> None:
    from cli_avatars.app import chime_cues

    try:
        chime_cues.cue(app, name)
    except Exception:
        return
