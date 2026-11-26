"""BACKLOG-BOSS on the Dungeon floor (docs/backlog-boss.md): the oni in its pit, hits, the HP bar and the burn-down.

``Hall.place`` calls ``update`` and ``paint`` each frame. At most every ``READ_S`` the view reads every board and
syncs ``boss.json`` (``backlog_boss.sync``). The pit sits in the middle of the Oni Pit, its own room (BOSS-ROOM.1,
``boss_rooms``), and widens with it. The oni breathes in it at the size of its stage; a stage up roars. Each new hit
plays in turn: a white flash, a shake, a ``-1`` rising, the HP bar dropping and a thud; the last hit to zero plays a
fanfare and the oni falls (the defeated pose) for ``DOWN_S``; at HP 0 the room is bare. ``crypt_view`` draws the
Crypt's skulls and ``boss_dust`` the dust of a sliding wall. Hover shows HP and the tasks that feed it, a click
lists them on a parchment and a row opens its card. On Fridays the HP bar and the week's burn-down parchment show;
any day the scroll button or ``b`` toggles them. While a task is in focus the cues wait and the last one plays when
focus ends. Canvas items are made once and changed in place.
"""

from __future__ import annotations

import logging
import math
import sys
import time

import backlog_boss
import focus
from cli_avatars.app import boss_art as art
from cli_avatars.app import boss_dust, boss_rooms, crypt_view, cues
from cli_avatars.app import boss_oni as oni
from cli_avatars.app import boss_room_art as room_art
from cli_avatars.app.throttle import StoreThrottle

TAG = "boss"
READ_S = 2.0
HIT_S = 0.9
BAR_AFTER_S = 2.5
DOWN_S = 3.0
LIST_W = 300
LIST_ROWS = 8
_log = logging.getLogger("cli_avatars.boss")


def view_for(book) -> "BossView":
    found = getattr(book, "_boss", None)
    if found is None:
        found = book._boss = BossView(book)
    return found


def update(book, hall, plan, now: float) -> None:
    try:
        view_for(book).update(plan, now)
        crypt_view.view_for(book).update(now)
        boss_dust.dust_for(book).update(plan, now)
    except Exception:
        _log.debug("boss update failed", exc_info=True)


def paint(book, scene, hall, now: float | None = None) -> None:
    try:
        now = time.time() if now is None else now
        boss_dust.dust_for(book).paint(scene, now)
        crypt_view.view_for(book).paint(scene, now)
        view_for(book).paint(scene, hall, now)
    except Exception:
        _log.debug("boss paint failed", exc_info=True)


def pit_room(plan) -> str | None:
    """The Oni Pit when it is on the floor."""
    floor = plan.floor(boss_rooms.PIT)
    return boss_rooms.PIT if floor is not None and not floor.corridor else None


def pit_spot(plan) -> tuple[float, float] | None:
    """The pit: the middle of the Oni Pit's floor."""
    room = pit_room(plan)
    return plan.floor(room).centre() if room is not None else None


def pit_width(plan) -> int:
    """The pit's width in 1x px: most of the room's floor, so it widens as the room grows."""
    floor = plan.floor(boss_rooms.PIT)
    return round(min(floor.w - 1, floor.h - 1) * 0.8 * 16 * math.sqrt(2)) if floor is not None else 0


def _why(row: dict) -> str:
    return "blocked" if row["why"] == "blocked" else f"idle {row['idle_days']} d"


class BossView:
    def __init__(self, book) -> None:
        self.book, self.app = book, book.app
        self.state: dict = {"hp": 0, "max": 1, "stage": 0, "feeding": [], "week": [], "friday": False,
                            "defeated": True, "name": backlog_boss.NAMES[0]}
        self.hits: list[dict] = []
        self.hit: tuple[dict, float, int] | None = None
        self.shown_hp: int | None = None
        self.chart_on: tuple[str, bool] | None = None
        self._now = time.time()
        self.listing = False
        self.hot = False
        self.held: str | None = None
        self.played: list[str] = []
        self._stage: int | None = None
        self._read = StoreThrottle(READ_S)
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._photos: dict[tuple, object] = {}
        self._text: list[int] = []
        self._list_key: tuple | None = None
        self._bound = None
        self._bar_until = 0.0
        self._down_until = 0.0
        self.cued = float("-inf")

    # --- state -------------------------------------------------------------------------------------
    def _directory(self):
        found = getattr(self.app, "_chat_directory", None)
        return found() if callable(found) else None

    def reread(self) -> None:
        self._read._ready = False

    def _inputs(self, now: float) -> tuple[dict, list[dict]] | None:
        root = self._directory()
        if root is None:
            return None

        def load():
            cards = backlog_boss.cards_in(root)
            boss_rooms.remember(root, cards, now)
            synced = backlog_boss.sync(root, cards, now)
            return backlog_boss.public(root, cards, now), synced["hits"]

        try:
            return self._read.get(load)
        except Exception:
            _log.debug("boss read failed", exc_info=True)
            return None

    def update(self, plan, now: float) -> None:
        self._now = now
        found = self._inputs(now)
        if found is not None:
            state, fresh = found
            if state is not self.state:
                self.hits.extend(h for h in fresh if h not in self.hits)
                self.state = state
        if self._stage is not None and self.state["stage"] > self._stage:
            self._cue("roar")
        self._stage = self.state["stage"]
        if self.hit is None and self.hits:
            info = self.hits.pop(0)
            base = self.state["hp"] + len(self.hits) + 1
            self.hit = (info, now, base)
            self._bar_until = now + BAR_AFTER_S
            self._cue("fanfare" if base - 1 <= 0 else "thud")
            self._down_until = now + HIT_S + DOWN_S if base - 1 <= 0 else self._down_until
        if self.hit is not None and now - self.hit[1] >= HIT_S:
            self.hit = None
        pending = len(self.hits) + (1 if self.hit is not None else 0)
        self.shown_hp = self.state["hp"] + pending
        root = self._directory()
        if self.held and root is not None and focus.current(root) is None:
            name, self.held = self.held, None
            cues.play(self.app, name)
            self.played.append(name)

    def _cue(self, name: str) -> None:
        self.cued = self._now
        root = self._directory()
        try:
            task = focus.current(root) if root is not None else None
        except Exception:
            task = None
        hit = self.hits[0]["card"] if name in ("thud", "fanfare") and self.hits else None
        hit = self.hit[0]["card"] if self.hit is not None else hit
        if task is not None and task != hit:
            self.held = name
            return
        cues.play(self.app, name)
        self.played.append(name)

    def chart_shown(self) -> bool:
        """Fridays by default; a toggle (the scroll button, ``b``) holds for the day it was made."""
        day = time.strftime("%Y-%m-%d", time.localtime(self._now))
        if self.chart_on is not None and self.chart_on[0] == day:
            return self.chart_on[1]
        return self.state.get("friday", False)

    def toggle_chart(self) -> None:
        self.chart_on = (time.strftime("%Y-%m-%d", time.localtime(self._now)), not self.chart_shown())

    def open_card(self, card: str) -> None:
        self.listing = False
        view = getattr(self.app, "dungeon", None)
        panel = getattr(self.app, "_tasks_panel", None)
        if view is not None:
            view.show_center("tasks")
            if panel is not None:
                panel.open_card(card)

    # --- drawing -----------------------------------------------------------------------------------
    def paint(self, scene, hall, now: float) -> None:
        tk = sys.modules.get("tkinter")
        painter = getattr(scene, "_rooms_painter", None)
        plan = hall.plan()
        spot = pit_spot(plan) if plan is not None else None
        at = painter.to_canvas(*spot) if painter is not None and spot is not None else None
        if tk is None or not isinstance(scene, tk.Canvas) or at is None:
            self._drop(scene, set())
            self._paint_list(scene, None, (0, 0))
            return
        self._bind(scene)
        s = max(1, int(painter._scale))
        stage, hp = self.state["stage"], self.shown_hp if self.shown_hp is not None else self.state["hp"]
        glow = round((0.5 + 0.5 * math.sin(now * math.tau * 0.5)) * 7)
        bare = hp <= 0 and self.hit is None and now >= self._down_until
        keep = set() if bare else {"pit", "oni"}
        x, y = at
        width = pit_width(plan)
        if not bare:
            self._image(scene, "pit", ("pit", width, stage, glow, s), (x, y), "center", True)
        dx, level = 0, 0
        if self.hit is not None:
            t = (now - self.hit[1]) / HIT_S
            level = max(0, 4 - int(t * 10))
            dx = round(math.sin(t * math.tau * 4) * 3 * (1 - t)) * s
            keep.add("dmg")
        foot = y + (width // 2) * s // 4
        if self.hit is not None:
            rise = round(t * 18 * s)
            at = (x + (oni.size(stage) / 2 + 6) * s, foot - oni.size(stage) * s * 0.6 - rise)
            self._image(scene, "dmg", ("dmg", "-1", s), at, "s", False)
        if bare:
            pass
        elif hp <= 0 and self.hit is None:
            self._image(scene, "oni", ("down", stage, s), (x, foot), "s", True)
        else:
            f = int(now * 2.5) % 4
            key = ("flash", stage, f, level, s) if level else ("oni", stage, f, s)
            self._image(scene, "oni", key, (x + dx, foot), "s", True)
        top = foot - (oni.size(stage) + 6) * s
        if self.chart_shown() or self.hot or now < self._bar_until:
            keep |= {"bar", "btn"}
            self._image(scene, "bar", ("bar", max(0, hp), self.state["max"], self.state["name"], self.hot, s),
                        (x, top), "s", True)
            self._image(scene, "btn", ("btn", self.chart_shown(), s), (x + 46 * s, top - 4 * s), "s", "chart")
        elif not bare:
            keep.add("btn")
            self._image(scene, "btn", ("btn", False, s), (x + 14 * s, top), "s", "chart")
        if self.chart_shown() and self.state["week"]:
            keep.add("chart")
            week = tuple(r["hp"] for r in self.state["week"])
            days = tuple(r["day"].upper() for r in self.state["week"])
            monday = time.strptime(self.state["week"][0]["date"], "%Y-%m-%d")
            title = f"BURN-DOWN - WEEK OF {monday.tm_mday} {time.strftime('%b', monday).upper()}"
            right = max(art.CHART_W * s + 8, x - (oni.size(stage) / 2 + 16) * s)
            self._image(scene, "chart", ("chart", week, days, title, s),
                        (right, max(art.CHART_H * s + 8, foot - 6 * s)), "se", "chart")
        self._drop(scene, keep)
        corner = (x - (oni.size(stage) / 2 + 16) * s, foot - oni.size(stage) * s)
        self._paint_list(scene, self.state if (self.listing or self.hot) else None, corner)
        scene.after_idle(self._raise, scene)

    def _raise(self, scene) -> None:
        try:
            scene.tag_raise(TAG)
            scene.tag_raise("boss-list")
        except Exception:
            return

    def _bind(self, scene) -> None:
        if self._bound is scene:
            return
        self._bound = scene
        scene.bind("<KeyPress-b>", lambda _e: self.toggle_chart(), add="+")

    def _image(self, scene, name: str, key: tuple, at, anchor: str, click) -> None:
        photo = self._photo(scene, key)
        item = self._items.get(name)
        if item is None or not scene.find_withtag(item):
            item = self._items[name] = scene.create_image(0, 0, image=photo, anchor=anchor, tags=(TAG,))
            if click:
                scene.tag_bind(item, "<Button-1>", lambda _e, c=click: self._click(c))
            if click is True:
                scene.tag_bind(item, "<Enter>", lambda _e: self._hover(True))
                scene.tag_bind(item, "<Leave>", lambda _e: self._hover(False))
        elif self._keys.get(name) != key:
            scene.itemconfigure(item, image=photo)
        self._keys[name] = key
        scene.coords(item, round(at[0]), round(at[1]))

    def _click(self, what) -> None:
        if what == "chart":
            self.toggle_chart()
        else:
            self.listing = not self.listing

    def _hover(self, on: bool) -> None:
        self.hot = on

    def _photo(self, scene, key: tuple):
        found = self._photos.get(key)
        if found is None:
            from PIL import Image, ImageTk

            kind, s = key[0], key[-1]
            image = {"pit": lambda: room_art.pit(key[1], key[2], key[3]), "oni": lambda: oni.frame(key[1], key[2]),
                     "flash": lambda: art.flash(key[1], key[2], key[3]), "down": lambda: oni.defeated(key[1]),
                     "dmg": lambda: art.damage(key[1]), "bar": lambda: art.bar(key[1], key[2], key[3], key[4]),
                     "btn": lambda: art.button(key[1]), "chart": lambda: art.chart(key[1], key[2], key[3])}[kind]()
            if s > 1:
                image = image.resize((image.width * s, image.height * s), Image.NEAREST)
            found = self._photos[key] = ImageTk.PhotoImage(image, master=scene)
            used = set(self._keys.values()) | {key}
            for old in [k for k in self._photos if k not in used][:-64]:
                self._photos.pop(old)
        return found

    def _drop(self, scene, keep: set[str]) -> None:
        for name in [n for n in self._items if n not in keep and n != "list"]:
            try:
                scene.delete(self._items.pop(name))
            except Exception:
                self._items.pop(name, None)
            self._keys.pop(name, None)

    def _paint_list(self, scene, state: dict | None, corner: tuple[float, float]) -> None:
        """HP and the feeding tasks on a parchment left of the oni (``corner`` is its top right); while listing (a
        click) each row opens its card."""
        corner = (round(max(LIST_W + 8, corner[0])), round(max(10, corner[1])))
        key = None if state is None else (state["hp"], tuple(r["id"] for r in state["feeding"]), self.listing, corner)
        if key == self._list_key:
            return
        self._list_key = key
        for item in self._text + [self._items.pop("list", None)]:
            if item is not None:
                scene.delete(item)
        self._text = []
        if state is None:
            return
        ink, dim, wine = "#3a2414", "#7a5a3a", "#8a1c2a"
        rows = state["feeding"][:LIST_ROWS]
        lines = [(f"{state['name']} · HP {state['hp']}", wine, None),
                 ("Fed by:" if rows else "Nothing feeds it: the backlog is clear.", dim, None)]
        lines += [(f"{'■' if r['why'] == 'blocked' else '◷'} {r['title'][:38]} · {_why(r)}", ink, r["id"])
                  for r in rows]
        if len(state["feeding"]) > LIST_ROWS:
            lines.append((f"+{len(state['feeding']) - LIST_ROWS} more", dim, None))
        if self.listing and rows:
            lines.append(("Click a task to open its card.", dim, None))
        x = corner[0] - LIST_W / 2
        top = 0.0
        for text, colour, card in lines:
            item = scene.create_text(x - LIST_W / 2 + 18, top, text=text, anchor="nw", fill=colour,
                                     font="DungeonBubble", width=LIST_W - 36, tags=(TAG, "boss-list"))
            if card and self.listing:
                scene.tag_bind(item, "<Button-1>", lambda _e, c=card: (self.open_card(c), "break")[1])
            self._text.append(item)
            box = scene.bbox(item)
            top = (box[3] if box else top + 14) + 3
        height = int(top) + 30
        for item in self._text:
            scene.move(item, 0, corner[1] + 14)
        from PIL import ImageTk

        from cli_avatars.app.courier_art import note

        photo = self._photos[("list", height)] = ImageTk.PhotoImage(note(LIST_W, height), master=scene)
        self._items["list"] = scene.create_image(x, corner[1], image=photo, anchor="n", tags=(TAG, "boss-list"))
        scene.tag_lower(self._items["list"], self._text[0])
