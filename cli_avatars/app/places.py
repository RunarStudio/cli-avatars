"""Inside and desktop actors. Drag across the Dungeon edge, and remember it.

New agents start inside, on a ring in the empty floor. Dragging past the
client edge hands the same sprite to an overlay. Releasing it on the Dungeon,
where no other window covers the pointer, starts the walk home. The door,
Call home, and the idle walk live here too. A hot-unplug still parks on a
remaining monitor. It does not send anyone inside. Wander does not.
"""

from __future__ import annotations

import time

from cli_avatars.app.dungeon_map import (
    client_rect_v,
    drop_on_dungeon,
    past_edge,
    virtual_from_canvas,
)
from cli_avatars.app.overlays import bind_avatar
from cli_avatars.app.place_store import (
    empty_file,
    forget,
    load_file,
    prune,
    remember,
    save_file,
)
from cli_avatars.app.place_markers import draw_inside_sub_marks
from cli_avatars.app.render import canvas_photos
from cli_avatars.sprites.registry import REGISTRY
from cli_avatars.desktop.chrome import frame_hwnd
from cli_avatars.desktop.windows import occlusion_covers
from cli_avatars.model.place import DESKTOP, INSIDE, RETURNING, Place, drag_out, new_actor, portal_done
from cli_avatars.world.avatar import Avatar
from cli_avatars.world.monitors import monitor_at


def places_path():
    """``ui/avatar_places.json`` under the per-user data dir."""
    from events import app_data_dir

    return app_data_dir() / "ui" / "avatar_places.json"


class PlaceBook:
    """Places for one shell. The file stores desktop actors only."""

    def __init__(self, app, path=None):
        self.app = app
        if getattr(app, "_inside", None) is None:
            app._inside = {}
        self._path = path
        if path is None and not getattr(getattr(app, "dungeon", None), "_offscreen", False):
            try:
                self._path = places_path()
            except OSError:
                self._path = None
        self._file = load_file(self._path, time.time()) if self._path else empty_file()
        self._actors: dict[str, Place] = {}
        self._applied: set[str] = set()
        self._cross: dict = {}
        self._desktop_since: dict[str, float] = {}
        self._arch_until = 0.0
        self._portals: list = []
        self._door_images: dict = {}
        self._now = 0.0
        self._job = None
        self._dirty = False

    def attach(self) -> None:
        scene = self._scene()
        if scene is None:
            return
        app = self.app
        scene.bind("<ButtonPress-1>", app._on_scene_press)
        scene.bind("<B1-Motion>", app._on_scene_drag)
        scene.bind("<ButtonRelease-1>", app._on_scene_release)
        scene.bind("<Double-Button-1>", app._on_scene_double)
        scene.bind("<Button-3>", app._on_scene_right)

    def reconcile(self, agents) -> None:
        """New ids start inside, unless a saved monitor is still plugged in."""
        now = time.time()
        self._file = prune(self._file, set(agents), now)
        for aid in list(self._actors):
            if aid not in agents:
                self._drop_actor(aid)
        escape = self.allows_desktop()
        for aid, agent in agents.items():
            actor = self._actors.get(aid)
            if actor is None:
                spot = self._file.spots.get(aid) if escape else None
                if spot is not None and self._monitor_ok(spot.monitor):
                    actor = Place(aid, DESKTOP, "drag", None)
                else:
                    actor = new_actor(aid)
                self._actors[aid] = actor
            elif not escape and actor.where != INSIDE:
                self._actors[aid] = new_actor(aid)
                held_out = self.app.avatars.pop(aid, None)
                if held_out is not None:
                    held_out.cleanup(getattr(self.app, "canvas", None))
                actor = self._actors[aid]
            if actor.where == INSIDE:
                self._ensure_inside(agent)
            else:
                held = self.app._inside.pop(aid, None)
                if held is not None and aid not in self.app.avatars:
                    held.agent = agent
                    self.app.avatars[aid] = held
                    bind_avatar(self.app, held)
                elif aid in self.app.avatars:
                    self.app.avatars[aid].agent = agent

    def desktop_ids(self) -> set[str]:
        return {aid for aid, actor in self._actors.items() if actor.where == DESKTOP}

    def inside_ids(self) -> set[str]:
        return {aid for aid, actor in self._actors.items() if actor.where == INSIDE}

    def claim_desktop(self, av) -> None:
        """Put a restored actor on its saved x and that monitor's ground, once."""
        aid = av.agent.agent_id
        if aid in self._applied:
            return
        self._applied.add(aid)
        spot = self._file.spots.get(aid)
        if spot is None:
            return
        point = self._on_ground(spot, av)
        if point is None:
            return
        av.x, av.y = point
        av.vx = av.vy = 0.0
        av.on_ground = True

    def hit(self, x: float, y: float):
        found = None
        for av in self.app._inside.values():
            if av.x <= x <= av.x + av.aw and av.y <= y <= av.y + av.ah:
                found = av
        return found

    def past_client(self, vx: float, vy: float) -> bool:
        try:
            return past_edge(vx, vy, self._client())
        except Exception:
            return False

    def lands(self, vx: float, vy: float) -> bool:
        """True when a release on this point would come back inside."""
        try:
            rect = self._client()
            hwnd = frame_hwnd(self.app.root)
        except Exception:
            return False
        dungeon_z, covers = occlusion_covers(hwnd)
        return drop_on_dungeon(vx, vy, rect, covers, dungeon_z)

    def allows_desktop(self) -> bool:
        """Windows may leave the Dungeon. Linux and macOS stay inside."""
        return bool(getattr(self.app, "desktop_escape", True))

    def handoff(self, av, pointer_x: float, pointer_y: float) -> bool:
        """The pointer left the client. The sprite continues on the overlay."""
        if not self.allows_desktop():
            return False
        aid = av.agent.agent_id
        actor = self._actors.get(aid)
        if actor is None:
            return False
        stepped = portal_done(drag_out(actor))
        if stepped.where != DESKTOP:
            return False
        scene = self._scene()
        origin = (0.0, 0.0)
        if scene is not None:
            try:
                origin = (scene.winfo_rootx(), scene.winfo_rooty())
            except Exception:
                origin = (0.0, 0.0)
            av.cleanup(scene)
        vx, vy = virtual_from_canvas(av.x, av.y, origin)
        av.x, av.y = vx, vy
        av.vx = av.vy = 0.0
        av.spr_id = None
        av.lbl_id = None
        av._draw_sig = None
        self.app._inside.pop(aid, None)
        self.app.avatars[aid] = av
        bind_avatar(self.app, av)
        self._actors[aid] = stepped
        self._applied.add(aid)
        from cli_avatars.app.crossing import note_drag

        note_drag(self, aid, time.time(), pointer_x, pointer_y)
        self.app._drag_av = av
        self.app._drag_off = (pointer_x - av.x, pointer_y - av.y)
        self.app._drag_prev = (pointer_x, pointer_y)
        self._show_avatar(av)
        self._remember_avatar(av)
        self._schedule()
        return True

    def bring_in(self, av) -> bool:
        """Drop on the Dungeon. The walk home from the door finishes within 1.2 s."""
        from cli_avatars.app.crossing import start_return

        return start_return(self, av.agent.agent_id, "drop", time.time())

    def tick(self, agents, now: float | None = None) -> None:
        """Door rules, idle walk-home, and crossings. Not wander."""
        from cli_avatars.app.crossing import advance

        self._now = time.time() if now is None else float(now)
        advance(self, agents, self._now)

    def set_room(self, aid: str, room: str) -> None:
        """MOVE.1: remember the room an inside avatar or the user was moved to."""
        from cli_avatars.app.place_store import with_room

        self._file = with_room(self._file, aid, room)
        self._schedule()

    def door(self) -> str:
        from cli_avatars.app.dungeon_geom import dungeon_prefs

        return dungeon_prefs(getattr(self.app, "config", {})).door

    def toggle_door(self) -> str:
        """Flip the door and remember it in config when that file already exists."""
        from cli_avatars.app.dungeon_geom import config_with_door
        from cli_avatars.app.dungeon_store import save_door

        nxt = "closed" if self.door() == "open" else "open"
        self.app.config = config_with_door(getattr(self.app, "config", {}), nxt)
        path = getattr(self.app, "_config_path", None)
        offscreen = getattr(getattr(self.app, "dungeon", None), "_offscreen", False)
        if path is not None and not offscreen:
            save_door(path, nxt)
        button = getattr(getattr(self.app, "dungeon", None), "_door_btn", None)
        if button is not None:
            try:
                button.config(text=f"Door: {nxt}")
            except Exception:
                pass
        return nxt

    def call_everyone(self) -> None:
        from cli_avatars.app.crossing import call_everyone

        call_everyone(self)

    def go_home(self, aid: str) -> bool:
        from cli_avatars.app.crossing import go_home

        return go_home(self, aid)

    def children_ready(self, aid: str, now: float | None = None) -> int:
        from cli_avatars.app.crossing import children_ready

        return children_ready(self, aid, time.time() if now is None else float(now))

    def draw_inside(self) -> None:
        scene = self._scene()
        if scene is None:
            return
        try:
            scene.delete("inside-sub")
        except Exception:
            return
        now = self._now or time.time()
        from cli_avatars.app.crossing import paint_marks
        from cli_avatars.app.dungeon_door import paint_door
        from cli_avatars.model.crossing import arch_visible

        zoom = getattr(getattr(self.app, "dungeon", None), "_zoom", 1)
        if self.allows_desktop():
            paint_door(scene, arch_visible(self.door(), now, self._arch_until), zoom, self._door_images)
        paint_marks(self, now)
        dragging = getattr(self.app, "_drag_av", None)
        settled = sorted(
            aid for aid, actor in self._actors.items()
            if actor.where == INSIDE and aid not in self._cross
        )
        from cli_avatars.app.inside_roster import hall

        room = hall(self)
        spots = room.place(self._spot_map(settled), now)
        from cli_avatars.app.room_glow import glow_for

        glow_for(self).paint(scene, room, dragging, now)
        photos = canvas_photos(self.app)
        from cli_avatars.app.nameplates import seat_inside

        seat_inside(scene, settled, spots, self.app._inside, dragging)
        for aid in settled:
            self._paint_inside(scene, aid, spots.get(aid, (0.0, 0.0)), photos, dragging, now, posed=False)
        for aid in list(self._cross):
            if self._actors.get(aid) is not None and self._actors[aid].where in (INSIDE, RETURNING):
                self._paint_inside(scene, aid, (0.0, 0.0), photos, dragging, now, posed=True)
        room.paint_user(scene, photos, now)
        room.paint_marks(scene)
        try:
            scene.tag_lower("floor")
        except Exception:
            return

    def note_positions(self) -> None:
        """Remember desktop feet. Inside actors are not written."""
        layout = self._layout()
        if layout is None:
            return
        changed = False
        now = time.time()
        for aid, av in list(self.app.avatars.items()):
            actor = self._actors.get(aid)
            if actor is None or actor.where != DESKTOP:
                continue
            try:
                feet_x = av.x + av.aw / 2.0
                feet_y = av.y + av.ah - av._foot_pad()
                ident = monitor_at(layout, feet_x, feet_y)
                if ident is None:
                    continue
                x = int(round(av.x))
                y = int(round(av.y))
            except Exception:
                continue
            prev = self._file.spots.get(aid)
            if prev is not None and prev.monitor == ident and prev.x == x and prev.y == y:
                continue
            updated = remember(self._file, aid, ident, x, y, now)
            if updated is self._file:
                continue
            self._file = updated
            changed = True
        if changed:
            self._schedule()

    def save_now(self) -> bool:
        self._dirty = False
        if self._path is None:
            return False
        return save_file(self._path, self._file)

    def _ensure_inside(self, agent) -> None:
        aid = agent.agent_id
        av = self.app._inside.get(aid)
        if av is None:
            av = Avatar(agent, 800, 600, getattr(self.app, "_cidx", 0), REGISTRY)
            self.app._cidx = getattr(self.app, "_cidx", 0) + 1
            av.vx = av.vy = 0.0
            self.app._inside[aid] = av
        av.agent = agent
        av.monitor_layout = None
        av._board = None

    def _drop_actor(self, aid: str) -> None:
        self._actors.pop(aid, None)
        self._applied.discard(aid)
        self._file = forget(self._file, aid)
        inside = self.app._inside.pop(aid, None)
        scene = self._scene()
        if inside is not None and scene is not None:
            inside.cleanup(scene)
        self._schedule()

    def _show_avatar(self, av) -> None:
        board = getattr(self.app, "overlays", None)
        if board is not None:
            board.show([(av.x, av.y, av.aw, av.ah)])
        canvas = getattr(self.app, "canvas", None)
        if canvas is None:
            return
        try:
            av.draw(canvas, canvas_photos(self.app))
        except Exception:
            return

    def _remember_avatar(self, av) -> None:
        layout = self._layout()
        if layout is None:
            return
        try:
            feet_x = av.x + av.aw / 2.0
            feet_y = av.y + av.ah - av._foot_pad()
            ident = monitor_at(layout, feet_x, feet_y)
        except Exception:
            return
        if ident is None:
            return
        self._file = remember(
            self._file, av.agent.agent_id, ident, int(round(av.x)), int(round(av.y)), time.time(),
        )

    def _on_ground(self, spot, av):
        layout = self._layout()
        if layout is None:
            return None
        monitor = layout.monitor(spot.monitor)
        if monitor is None:
            return None
        feet = av.ah - av._foot_pad()
        left, _top, right, ground = monitor.work
        width = av.aw
        x = min(max(float(spot.x), float(left)), max(float(left), float(right) - width))
        return (x, float(ground - feet))

    def _monitor_ok(self, ident: str) -> bool:
        layout = self._layout()
        monitors = getattr(layout, "monitors", None) or ()
        return any(getattr(item, "id", None) == ident for item in monitors)

    def spot_center(self, aid: str, ids) -> tuple[float, float]:
        from cli_avatars.app.inside_spots import one_center

        return one_center(self, aid, ids)

    def _spot_map(self, ids) -> dict[str, tuple[float, float]]:
        from cli_avatars.app.inside_spots import centers_for

        return centers_for(self, ids)

    def _spot_centers(self, count: int) -> list[tuple[float, float]]:
        from cli_avatars.app.inside_spots import ring_centers

        return ring_centers(self, count)

    def _paint_inside(self, scene, aid, spot, photos, dragging, now, posed: bool) -> None:
        from cli_avatars.app.crossing import pose
        from cli_avatars.app.dungeon_rooms import rooms_scale
        from cli_avatars.app.inside_roster import dress, hall, wearing

        av = self.app._inside.get(aid)
        if av is None:
            return
        av.monitor_layout = None
        av._board = None
        photos, look = dress(av, photos, rooms_scale(scene), hall(self).hues)
        shown = pose(self, aid, now) if posed else None
        if shown is not None:
            av.x, av.y = shown.x, shown.y
            av.vx = av.vy = 0.0
            if shown.hide:
                self._draw_children(scene, av)
                return
        elif av is not dragging:
            av.x = spot[0] - av.aw / 2.0
            av.y = spot[1] - av.ah / 2.0
            av.vx = av.vy = 0.0
        try:
            with wearing(av, look):
                av.draw(scene, photos)
        except Exception:
            pass
        self._draw_children(scene, av)

    def _draw_children(self, scene, av) -> None:
        draw_inside_sub_marks(scene, av, self.app)

    def _client(self):
        root = self.app.root
        return client_rect_v(
            root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height(),
        )

    def _scene(self):
        dungeon = getattr(self.app, "dungeon", None)
        if dungeon is None:
            return None
        return getattr(dungeon, "scene", None)

    def _layout(self):
        board = getattr(self.app, "overlays", None)
        if board is None or getattr(board, "legacy", True):
            return None
        return getattr(board, "layout", None)

    def _schedule(self) -> None:
        self._dirty = True
        root = getattr(self.app, "root", None)
        if self._path is None or root is None or self._job is not None:
            return
        try:
            self._job = root.after(1000, self._flush)
        except Exception:
            self.save_now()

    def _flush(self) -> None:
        self._job = None
        if self._dirty:
            self.save_now()
