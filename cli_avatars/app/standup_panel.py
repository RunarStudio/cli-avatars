"""STANDUP on the desktop: when the day's standup runs, and its show on the Dungeon's Throne tab (docs/standup.md).

``step`` runs from the overlay tick, at most every ``CHECK_S``: the first time the Dungeon is open after the morning
hour (``config.json`` ``standup.hour``, default 9) it runs the standup (``standup.run``: local code, no AI, no CLI)
and plays it. A standup run elsewhere (the phone, the U key) plays too. While a task is in focus nothing runs or
plays; it waits until focus ends. ``Stage`` is the show inside ``ThronePanel``: the horn banner, agents walking in
through the hall door, one pixel bubble each, then back out. Keys on the Throne tab: Space or Right next bubble,
S skip, R replay, U call the standup now. Cues: ``gather`` at the horn, ``blip`` per bubble.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
import zlib
from datetime import datetime

import focus
import standup
from cli_avatars.app import cues
from cli_avatars.app import standup_art as art
from cli_avatars.app import standup_show as ss
from cli_avatars.app import throne_model as tm
from cli_avatars.app.throttle import StoreThrottle

CHECK_S = 2.0
CLOCK = time.monotonic
NOW = datetime.now
TAG = "standup_ui"
_LOG = logging.getLogger("cli_avatars.standup")


def step(app, now: datetime | None = None) -> None:
    gate = getattr(app, "_standup_gate", None)
    if gate is None:
        gate = app._standup_gate = StoreThrottle(CHECK_S)
    if not gate.due():
        return
    gate.mark()
    try:
        directory = app._chat_directory()
        if not hasattr(app, "_standup_seen"):
            app._standup_seen = (standup.latest(directory) or {}).get("at")
        if getattr(app, "dungeon", None) is None or not _open(app):
            return
        focused = focus.current(directory) is not None
        if not focused and standup.due(directory, now or NOW(), standup.hour(getattr(app, "config", None))):
            _run(app, directory, False, now)
        _check(app, directory, focused)
    except OSError:
        return
    except Exception:
        _LOG.exception("standup step failed")


def call(app) -> None:
    """Run today's standup again (U key, the call button) and play it unless a task is in focus."""
    directory = app._chat_directory()
    try:
        _run(app, directory, True, None)
        _check(app, directory, focus.current(directory) is not None)
    except OSError:
        return


def _open(app) -> bool:
    try:
        return bool(app.root.winfo_viewable()) and app.root.state() != "iconic"
    except (tk.TclError, AttributeError):
        return False


def _run(app, directory, force: bool, now: datetime | None) -> dict | None:
    lord, name, names = lord_of(app)
    return standup.run(directory, lord, name, names, now=now or NOW(), force=force)


def _check(app, directory, focused: bool) -> None:
    record = standup.latest(directory)
    if record is None or focused or record.get("at") == getattr(app, "_standup_seen", None):
        return
    app._standup_seen = record.get("at")
    view = app.dungeon
    view.show_center("throne")
    view.throne.stage.start(record)


def lord_of(app) -> tuple[str, str, dict]:
    """The main orchestrator (the main session room's lord, else the first top-level agent), its name, and names."""
    agents = dict(app.scanner.get_agents()) if getattr(app, "scanner", None) is not None else {}
    tops = {aid: a for aid, a in agents.items() if not getattr(a, "parent_id", None)}
    names = {}
    for aid, agent in tops.items():
        name = str(getattr(agent, "name", "") or "")
        names[aid] = name
        if getattr(agent, "source", ""):
            names[f"{agent.source}:{str(aid)[:8]}"] = name
    lord = ""
    try:
        from cli_avatars.app.orch_rooms import room_agents
        from cli_avatars.app.session_rooms import MAIN, model_for

        model = model_for(app)
        main = next((s for s in model.sessions if s.kind == MAIN), None)
        if main is not None:
            lord = room_agents(model.layout(time.time()), agents, main.sid)[1]
    except Exception:
        lord = ""
    lord = lord or (min(tops) if tops else "")
    return lord, names.get(lord, ""), names


def _match(entry_agent: str, live: dict) -> tm.Actor | None:
    if entry_agent in live:
        return live[entry_agent]
    bare = entry_agent.partition(":")[2] or entry_agent
    return next((a for aid, a in sorted(live.items()) if aid.startswith(bare) or bare.startswith(aid[:8])), None)


class Stage:
    """The standup show inside one ``ThronePanel``: seating while it runs, canvas overlays, keys, cues."""

    def __init__(self, panel) -> None:
        self.panel = panel
        self.show: ss.Show | None = None
        self.record: dict | None = None
        self._photos: dict = {}
        self._shown: tuple | None = None
        canvas = panel.canvas
        for key, action in (("<space>", self.next), ("<Right>", self.next), ("s", self.skip), ("r", self.replay),
                            ("u", lambda: call(panel.app))):
            canvas.bind(key, lambda _e, f=action: (f(), "break")[1])
        canvas.bind("<Button-1>", lambda _e: canvas.focus_set(), add="+")

    def start(self, record: dict) -> None:
        self.record = record
        self.show = ss.Show(record.get("entries") or [], CLOCK())
        self.panel._key = None
        self.tick()

    def walking(self) -> bool:
        return self.show is not None and self.show.frame(CLOCK()).phase in ("gather", "return")

    def next(self) -> None:
        self._move("next")

    def skip(self) -> None:
        self._move("skip")

    def replay(self) -> None:
        if self.show is None and self.record is not None:
            self.show = ss.Show(self.record.get("entries") or [], CLOCK())
        self._move("replay")

    def _move(self, verb: str) -> None:
        if self.show is not None:
            getattr(self.show, verb)(CLOCK())
            self.panel._key = None
            self.tick()

    def tick(self) -> None:
        now = CLOCK()
        if self.show is not None:
            for name in self.show.cues(now):
                cues.play(self.panel.app, name)
            if self.show.over(now):
                self.show = None
                self.panel._key = None
        self.place()

    def lord(self, seating: tm.Seating, live: dict) -> tm.Actor:
        found = _match(str((self.record or {}).get("lord") or ""), live) if (self.record or {}).get("lord") else None
        if found is None and seating.placed and seating.placed[0].main:
            found = seating.placed[0].actor
        return found or tm.Actor(standup.ORCHESTRATOR, (self.record or {}).get("lord_name") or "Orchestrator")

    def seating(self, seating: tm.Seating, actors) -> tm.Seating:
        """The hall during the show: the orchestrator on the throne, the called agents walking or standing."""
        live = {a.id: a for a in actors if not a.sub}
        entries = self.show.entries
        lord = self._lord = self.lord(seating, live)
        cast = {}
        for entry in entries:
            found = _match(entry["agent"], live)
            skin = found.skin if found else self._skin(entry["agent"])
            state = "blocked" if entry.get("tone") == "stuck" else found.state if found else "idle"
            cast[entry["agent"]] = tm.Actor(entry["agent"], entry.get("name") or "", skin=skin, state=state)
        return ss.seat(self.show.frame(CLOCK()), lord, entries, cast)

    def _skin(self, agent: str) -> str:
        registry = self.panel._registry_obj()
        try:
            skins = sorted(s for s in registry.list_sheets() if not registry.is_subagent_skin(s))
        except Exception:
            return ""
        return skins[zlib.crc32(agent.encode("utf-8")) % len(skins)] if skins else ""

    # Overlays
    def speaking(self) -> int | None:
        return None if self.show is None else self.show.frame(CLOCK()).speaker

    def tone(self) -> str:
        index = self.speaking()
        return "" if index is None else self.show.entries[index].get("tone", "ok")

    def place(self) -> None:
        """Banner, bubble, key plates and the call button as canvas images; redrawn only when they change."""
        c, panel = self.panel.canvas, self.panel
        try:
            width, height = int(c.winfo_width()), int(c.winfo_height())
        except tk.TclError:
            return
        frame = self.show.frame(CLOCK()) if self.show is not None else None
        ox, oy, k = panel._origin[0], panel._origin[1], panel._scale
        bs = max(2, k)
        items = []
        if frame is None:
            items.append(("call", "CALL STANDUP  U", ox + (tm.WIDTH - 8) * k, oy + (tm.HEIGHT - 8) * k, "se"))
        else:
            if frame.phase in ("horn", "gather"):
                lord = (self.record or {}).get("lord_name") or "The orchestrator"
                items.append(("banner", f"{lord} calls the hall", ox + tm.WIDTH * k // 2, oy + 132 * k, "n"))
                if (self.record or {}).get("boss"):
                    items.append(("banner", self.record["boss"], ox + tm.WIDTH * k // 2, oy + 146 * k, "n"))
            if frame.speaker is not None:
                items.append(("bubble", frame.speaker) + self._anchor(frame.speaker, ox, oy, k) + ("s",))
            n = len(self.show.entries)
            at = f"{frame.speaker + 1}/{n}" if frame.speaker is not None else f"{n} AGENTS"
            x = ox + (tm.WIDTH - 8) * k
            for verb, label in (("replay", "REPLAY  R"), ("skip", "SKIP  S"), ("next", f"NEXT  SPACE  {at}")):
                items.append((verb, label, x, oy + (tm.HEIGHT - 8) * k, "se"))
                x -= (len(label) * 4 + 15) * bs
        sig = (tuple(items), width, height, bs)
        if sig == self._shown and c.find_withtag(TAG):
            return
        self._shown = sig
        c.delete(TAG)
        for kind, what, x, y, anchor in items:
            photo = self._photo(kind, what, bs)
            if photo is None:
                continue
            if kind == "bubble":
                x = min(max(x, photo.width() // 2 + 4), width - photo.width() // 2 - 4)
                y = max(y, photo.height() + 4)
            item = c.create_image(x, y, image=photo, anchor=anchor, tags=(TAG, f"{TAG}_{kind}"))
            if kind in ("call", "next", "skip", "replay"):
                action = {"call": lambda: call(panel.app), "next": self.next, "skip": self.skip,
                          "replay": self.replay}[kind]
                c.tag_bind(item, "<Button-1>", lambda _e, f=action: f())
                c.tag_bind(item, "<Enter>", lambda _e: c.configure(cursor="hand2"))
                c.tag_bind(item, "<Leave>", lambda _e: c.configure(cursor=""))

    def _anchor(self, index: int, ox: int, oy: int, k: int) -> tuple[int, int]:
        lord = getattr(self, "_lord", None) or self.lord(tm.Seating(), {})
        u, v = ss.speaker_spot(index, self.show.entries, lord)
        if (u, v) == tm.THRONE_SEAT[:2]:
            x, y = tm.iso(u, v, tm.THRONE_SEAT[2])
        else:
            x, y = tm.iso(u + 0.5, v + 0.5, 0.0)
        return ox + x * k, oy + (y - 44) * k

    def _photo(self, kind: str, what, bs: int):
        from PIL import Image, ImageTk

        key = (kind, what, bs, self.record.get("at") if self.record else None)
        photo = self._photos.get(key)
        if photo is not None:
            return photo
        if kind == "bubble":
            entry = self.show.entries[what]
            image = art.bubble(entry.get("name") or "", entry.get("line") or "", entry.get("tone", "ok"),
                               entry.get("title") or "")
        elif kind == "banner":
            image = art.banner("STANDUP", what)
        else:
            image = art.plate(what, art.WAX if kind == "call" else art.GOLD)
        image = image.resize((image.width * bs, image.height * bs), Image.NEAREST)
        if len(self._photos) > 64:
            self._photos.clear()
        photo = self._photos[key] = ImageTk.PhotoImage(image, master=self.panel.canvas)
        return photo
