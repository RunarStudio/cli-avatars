"""Throne tab of the Dungeon: the orchestrator's hall, drawn by ``throne_art``.

Live agents, the lord's board and the state crystals are read once a second while the
tab shows. A changed room is drawn on a worker thread; the Tk thread only swaps images
and cycles the torch frames. A click on the door goes back to the Dungeon tab. A bot
whose blocked card is labelled ``guest`` walks to the atelier desk (``atelier``). The daily standup plays here
(``standup_panel.Stage``). SUMMON.1: with no main session open, a Summon plate sits at the foot of the hall; once
one is open, its room's newest session is the lord.
"""

from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from dataclasses import replace

from cli_avatars.app import atelier as at
from cli_avatars.app import onboarding, skin_picks, summon_ui
from cli_avatars.app import throne_model as tm
from cli_avatars.app.av_roster import GROK, LOOKS, shrink
from cli_avatars.app.dungeon_rooms import fit_scale
from cli_avatars.app.needs_walk import read_rooms
from cli_avatars.app.standup_panel import Stage
from cli_avatars.app.throne_art import FRAMES, RoomScene, ThroneArt
from cli_avatars.app.throne_px import BG
from cli_avatars.app.throttle import StoreThrottle

REFRESH_MS = 1000
WALK_MS = 200
FLICKER_MS = 180
BOARD_EVERY = 3
LORD_SKIN = "caine"
_LOG = logging.getLogger("cli_avatars.throne")


class ThronePanel:
    """One per Dungeon, inside the centre area. ``show``/``hide`` follow the tab."""

    def __init__(self, app, parent, registry=None, store=None):
        self.app = app
        self.canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        self.canvas.bind("<Configure>", lambda _e: self._draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._hover)
        self._registry = registry
        self._store = store
        self._art = ThroneArt()
        self._sheets: dict = {}
        self._live = False
        self._job = None
        self._flick_job = None
        self._key = None
        self._busy = False
        self._result = None
        self._frames: list = []
        self._photos: dict = {}
        self._frame = 0
        self._item = None
        self._origin = (0, 0)
        self._scale = 1
        self._ticks = 0
        self._cards: list = []
        self._project = None
        self._errands = at.Errands()
        self._rooms = StoreThrottle()
        self._starter: list = []
        self._guide = tk.Label(self.canvas, bg="#1a1426", fg="#e8e6f4", font="DungeonBubble", justify="left",
                               anchor="nw", padx=8, pady=5, wraplength=340, highlightthickness=1,
                               highlightbackground="#e0aa3e")
        self._guide_text = ""
        self.stage = Stage(self)

    def show(self) -> None:
        self.canvas.pack(fill="both", expand=True)
        if not self._live:
            self._live = True
            self._refresh()
            self._flicker()

    def hide(self) -> None:
        self._live = False
        self.canvas.pack_forget()
        for job in (self._job, self._flick_job):
            if job is not None:
                try:
                    self.canvas.after_cancel(job)
                except tk.TclError:
                    pass
        self._job = self._flick_job = None

    # Data
    def scene(self) -> RoomScene:
        agents, lord = self._room_agents(self._agents())
        actors = tm.actors_from(agents, self._registry_obj())
        seating = tm.seat(actors, lord)
        topics, cards = self._read_rooms()
        seating, marked = self._errands.step(seating, at.needing_guest(topics, cards, agents), time.monotonic())
        if self.stage.show is not None:
            seating, marked = self.stage.seating(seating, actors), frozenset()
        if self._ticks % BOARD_EVERY == 0:
            self._starter = self._read_starter()
            self._show_guide()
        project = onboarding.PROJECT if self._starter else tm.lord_project(agents, seating)
        if project != self._project or self._ticks % BOARD_EVERY == 0:
            self._project, self._cards = project, self._read_cards(project)
        self._ticks += 1
        sprites = {}
        lord = seating.placed[0].actor.id if seating.placed else ""
        picked = skin_picks.mapping(self.app)
        for placed in seating.placed:
            actor = placed.actor
            if actor.id == lord and actor.id not in picked and not actor.sub:
                actor = replace(actor, skin=LORD_SKIN)
            image = self._frame_1x(actor)
            if image is not None:
                sprites[placed.actor.id] = image
        guest = self._frame_1x(tm.Actor(at.GUEST_ID, at.GUEST_NAME, skin=at.GUEST_SKIN))
        if guest is not None:
            sprites[at.GUEST_ID] = guest
        return RoomScene(seating, tm.board_columns(self._cards), tm.lights(a.state for a in actors), sprites, marked)

    def _read_starter(self) -> list:
        """INSTALLDAY: the starter cards while one is still open; the board shows them first."""
        directory = getattr(self.app, "_chat_directory", None)
        try:
            return onboarding.steps(directory()) if callable(directory) else []
        except Exception:
            _LOG.exception("starter cards read failed")
            return []

    def _show_guide(self) -> None:
        """The open starter steps over the hall, updated in place only when the words change."""
        text = onboarding.guide(self._starter)
        if text == self._guide_text:
            return
        self._guide_text = text
        if text:
            self._guide.config(text=text)
            self._guide.place(relx=1.0, x=-8, y=8, anchor="ne")
        else:
            self._guide.place_forget()

    def _room_agents(self, agents: dict) -> tuple[dict, str]:
        """ORCH.ROOM: the selected topic's room and its lord; every agent when no orchestrator room is selected."""
        from cli_avatars.app.orch_rooms import room_agents
        from cli_avatars.app.session_rooms import model_for
        from cli_avatars.app.summon import throne_room
        from cli_avatars.app.tasks_view import selected_topic

        try:
            layout = model_for(self.app).layout(time.time())
        except Exception:
            return agents, ""
        return room_agents(layout, agents, throne_room(layout, agents, selected_topic(self.app)))

    def _agents(self) -> dict:
        app, agents = self.app, {}
        scanner = getattr(app, "scanner", None)
        if scanner is not None:
            agents.update(scanner.get_agents())
        bots = getattr(app, "bots", None)
        if bots is not None:
            try:
                agents.update(bots.dungeon_agents())
            except Exception:
                _LOG.exception("bot roster failed")
        return agents

    def _read_cards(self, project: str) -> list:
        if not project:
            return []
        try:
            if self._store is None:
                from board.store import LocalStore

                self._store = LocalStore()
            return self._store.list(project)
        except Exception:
            _LOG.exception("board read failed")
            return []

    def _read_rooms(self) -> tuple[list, list]:
        directory = getattr(self.app, "_chat_directory", None)
        if not callable(directory):
            return [], []
        try:
            return self._rooms.get(lambda: read_rooms(directory()))
        except Exception:
            _LOG.exception("rooms read failed")
            return [], []

    def _registry_obj(self):
        if self._registry is None:
            from cli_avatars.sprites.registry import REGISTRY

            self._registry = REGISTRY
        return self._registry

    def _frame_1x(self, actor: tm.Actor):
        """One frame of the actor's sheet at 1x (the overlay's sheets are scaled up)."""
        registry = self._registry_obj()
        if registry is None or not registry.has(actor.skin):
            return None
        sheet = self._sheets.get(actor.skin)
        if sheet is None:
            from sprite_loader import SpriteSheet

            # The registry has no public getter for a sheet's file and cell size.
            src = getattr(registry, "_sheets", {}).get(actor.skin)
            try:
                sheet = SpriteSheet(str(src.path), src.frame_w, src.frame_h, 1.0)
                sheet.placeholder = bool(getattr(src, "placeholder", False))
            except Exception:
                return None
            self._sheets[actor.skin] = sheet
        image = sheet.get_image(registry.animation_row(actor.skin, actor.state), 1)
        if image is not None and actor.skin.split("_h")[0] == LOOKS[GROK].skin:
            image = shrink(image, LOOKS[GROK].shrink)
        if image is not None and sheet.placeholder:
            image = image.copy()
            image.paste((0, 0, 0, 0), (0, 0, 12, 7))
        return image

    # Drawing
    def _refresh(self) -> None:
        if not self._live:
            return
        try:
            summon_ui.sync_throne(self)
            self.stage.tick()
            scene = self.scene()
            key = (scene.seating, scene.columns, scene.lights, scene.marked,
                   tuple((p.actor.skin, p.actor.state) for p in scene.seating.placed))
            if key != self._key and not self._busy:
                self._key, self._busy = key, True
                threading.Thread(target=self._work, args=(scene,), daemon=True, name="throne-art").start()
                self.canvas.after(50, self._poll)
        except Exception:
            _LOG.exception("throne room refresh failed")
        busy = self._errands.moving() or self.stage.show is not None
        self._job = self.canvas.after(WALK_MS if busy else REFRESH_MS, self._refresh)

    def _work(self, scene: RoomScene) -> None:
        try:
            self._result = self._art.render(scene, 1 if self.stage.walking() else FRAMES)
        except Exception:
            _LOG.exception("throne room render failed")
            self._result = []
        self._busy = False

    def _poll(self) -> None:
        if self._result is not None:
            frames, self._result = self._result, None
            if frames:
                self._frames, self._photos = frames, {}
                self._draw()
            return
        if self._busy:
            self.canvas.after(50, self._poll)

    def _flicker(self) -> None:
        if not self._live:
            return
        if self._frames:
            self._frame = (self._frame + 1) % len(self._frames)
            self._draw()
        self._flick_job = self.canvas.after(FLICKER_MS, self._flicker)

    def _draw(self) -> None:
        if not self._frames:
            return
        from PIL import Image, ImageTk

        try:
            width, height = int(self.canvas.winfo_width()), int(self.canvas.winfo_height())
        except tk.TclError:
            return
        base = self._frames[self._frame % len(self._frames)]
        scale = fit_scale(base.size, (width, height))
        key = (self._frame % len(self._frames), scale)
        photo = self._photos.get(key)
        if photo is None:
            shown = base if scale == 1 else base.resize((base.width * scale, base.height * scale), Image.NEAREST)
            photo = ImageTk.PhotoImage(shown, master=self.canvas)
            self._photos[key] = photo
        self._scale = scale
        self._origin = ((width - base.width * scale) // 2, (height - base.height * scale) // 2)
        if self._item is None or not self.canvas.find_withtag(self._item):
            self._item = self.canvas.create_image(*self._origin, image=photo, anchor="nw")
        else:
            self.canvas.itemconfigure(self._item, image=photo)
            self.canvas.coords(self._item, *self._origin)
        self.stage.place()

    # Standup
    def tick(self) -> None:
        """One standup step now: cues, the end of the show, the overlays."""
        self.stage.tick()

    def bubble_shown(self) -> int | None:
        return self.stage.speaking() if self.canvas.find_withtag("standup_ui_bubble") else None

    def bubble_tone(self) -> str:
        return self.stage.tone()

    def room_point(self, x: float, y: float) -> tuple[float, float]:
        return (x - self._origin[0]) / self._scale, (y - self._origin[1]) / self._scale

    def _click(self, event) -> None:
        if tm.in_door(*self.room_point(event.x, event.y)):
            dungeon = getattr(self.app, "dungeon", None)
            if dungeon is not None:
                dungeon.show_center("dungeon")

    def _hover(self, event) -> None:
        over = tm.in_door(*self.room_point(event.x, event.y))
        try:
            self.canvas.configure(cursor="hand2" if over else "")
        except tk.TclError:
            pass


def ensure(view):
    """The view's throne panel, built on first use inside ``view._throne``."""
    panel = getattr(view, "throne", None)
    if panel is None:
        panel = ThronePanel(view.app, view._throne)
        view.throne = panel
    return panel
