"""Activity sentences on the Dungeon scene and on each desktop overlay."""

from __future__ import annotations

import logging
from typing import Any

from activity import BubbleSpot, bubble_settings, place_spots, rollup_id, spring_dots
from bubbles import render_text_frame, text_frame_size
from cli_avatars.app.render import photos_for
from cli_avatars.physics.geometry import child_flight_mode, elastic_endpoints

log = logging.getLogger("cli_avatars.activity")

_GAP = 16
_CHILD = 32
_DOT = 4


def _font(app: Any):
    import tkinter.font as tkfont

    try:
        return tkfont.nametofont("DungeonBubble")
    except Exception:
        root = getattr(app, "root", None)
        if root is None:
            return None
        return tkfont.Font(root, family="Courier", size=8)


def _measure(app: Any, text: str) -> tuple[int, int]:
    font = _font(app)
    if font is None:
        return max(8, len(text) * 7 + 20), 12
    try:
        # Tk's measure is a little short of the ink create_text actually draws.
        width = int(font.measure(text)) + 20
        return max(8, width), max(8, int(font.metrics("linespace")))
    except Exception:
        return max(8, len(text) * 7 + 20), 12


def _inside_ids(app: Any) -> set[str]:
    book = getattr(app, "places", None)
    if book is None or not hasattr(book, "inside_ids"):
        return set()
    try:
        return set(book.inside_ids())
    except Exception:
        return set()


def _surfaces(app: Any, av: Any, inside: bool) -> list[tuple]:
    if inside:
        scene = getattr(getattr(app, "dungeon", None), "scene", None)
        if scene is None:
            return []
        return [("scene", scene, 0.0, 0.0)]
    board = getattr(av, "_board", None)
    if board is not None:
        try:
            found = board.targets(av.x, av.y, av.aw, av.ah)
        except Exception:
            found = None
        if found:
            return list(found)
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return []
    return [("legacy", canvas, 0.0, 0.0)]


def _occupied(app: Any, ox: float, oy: float, inside: bool) -> list[tuple[int, int, int, int]]:
    if inside:
        return []
    boxes = []
    for hit in list(getattr(app, "_bubble_hits", ()) or ()):
        if len(hit) < 4:
            continue
        boxes.append((int(hit[0] - ox), int(hit[1] - oy), int(hit[2]), int(hit[3])))
    return boxes


class ActivityDraw:
    """Reuse canvas items. A new image is built only when the sentence changes."""

    def __init__(self) -> None:
        self._drawn: dict[tuple, dict] = {}
        self._spots: list[BubbleSpot] = []
        self._dots: dict[tuple, list] = {}

    def step(self, app: Any, now: float) -> None:
        board = getattr(getattr(app, "scanner", None), "activity", None)
        hits: list[tuple[float, float, float, float]] = []
        app._activity_hits = hits
        if board is None:
            self._drop_all()
            self._clear_dots(app)
            return
        settings = getattr(app, "bubbles_cfg", None) or bubble_settings(getattr(app, "config", {}))
        board.configure(settings)
        if not settings.activity:
            self._drop_all()
            self._clear_dots(app)
            return
        try:
            self._sync(app, board, now, settings, hits)
        except Exception:
            log.exception("activity bubbles failed")
            self._drop_all()
            hits.clear()

    def _sync(self, app: Any, board: Any, now: float, settings: Any, hits: list) -> None:
        home = _inside_ids(app)
        agents = {}
        scanner = getattr(app, "scanner", None)
        if scanner is not None and hasattr(scanner, "get_agents"):
            try:
                agents = scanner.get_agents()
            except Exception:
                agents = {}
        bodies: list[tuple[Any, bool, bool]] = []
        for aid, av in list((getattr(app, "_inside", None) or {}).items()):
            if not home or aid in home:
                bodies.append((av, True, False))
        for aid, av in list(getattr(app, "avatars", {}).items()):
            if aid in home:
                continue
            bodies.append((av, False, False))
        if settings.subagents:
            for subs in getattr(app, "sub_avatars", {}).values():
                for sv in subs:
                    bodies.append((sv, False, True))
        for av, _inside, sub in bodies:
            agent = getattr(av, "agent", None)
            if agent is None:
                continue
            info = agents.get(getattr(agent, "agent_id", ""), agent)
            board.note_agent(
                getattr(info, "agent_id", ""),
                getattr(info, "status", ""),
                getattr(info, "tool", ""),
                getattr(info, "file", ""),
                getattr(info, "subagents", 0),
                now,
                subagent=sub,
            )
        shown = {slot.agent_id: slot for slot in board.visible(now)}
        groups: dict[tuple, list] = {}
        for av, inside, _sub in bodies:
            agent = getattr(av, "agent", None)
            aid = getattr(agent, "agent_id", "")
            slot = shown.get(aid)
            if slot is None and not _sub:
                slot = shown.get(rollup_id(aid))
            if slot is None:
                continue
            for surface in _surfaces(app, av, inside):
                groups.setdefault((surface[0], id(surface[1]), inside), []).append((av, slot, surface))
        live: set[tuple] = set()
        for (_key, _ident, inside), rows in groups.items():
            _canvas_key, canvas, ox, oy = rows[0][2]
            spots = self._take_spots(len(rows))
            for index, (av, slot, _surface) in enumerate(rows):
                spot = spots[index]
                spot.agent_id = slot.agent_id
                spot.text = slot.text
                spot.priority = slot.priority
                spot.ax = float(av.x) - float(ox)
                spot.ay = float(av.y) - float(oy) - _GAP
                spot.aw = float(getattr(av, "aw", 40) or 40)
                tw, th = _measure(app, slot.text)
                fw, fh, _body = text_frame_size(tw, th)
                spot.bw = fw
                spot.bh = fh
                spot.show = False
            place_spots(spots, _occupied(app, ox, oy, inside))
            try:
                limit = int(canvas.winfo_width())
            except Exception:
                limit = 0
            for spot in spots:
                if limit > spot.bw:
                    spot.x = max(0, min(spot.x, limit - spot.bw))
            for spot in spots:
                if not spot.show:
                    continue
                item_key = (id(canvas), spot.agent_id)
                live.add(item_key)
                self._paint(app, canvas, item_key, spot, float(ox), float(oy), hits, inside)
        for key in list(self._drawn):
            if key not in live:
                self._drop(key)
        self._dots_for(app, board, now, settings)

    def _take_spots(self, count: int) -> list[BubbleSpot]:
        while len(self._spots) < count:
            self._spots.append(BubbleSpot())
        return self._spots[:count]

    def _paint(self, app, canvas, key, spot, ox: float, oy: float, hits: list, inside: bool) -> None:
        tw, th = _measure(app, spot.text)
        _fw, _fh, body = text_frame_size(tw, th)
        dpi = getattr(app, "_ui_dpi", None)
        sig = (spot.text, tw, th, dpi)
        drawn = self._drawn.get(key)
        photo = None
        if drawn is None or drawn.get("sig") != sig or drawn.get("canvas") is not canvas:
            cache = photos_for(app)
            photo = cache.get(
                ("activity", spot.text, tw, th, dpi),
                lambda tw=tw, th=th: render_text_frame(tw, th),
            )
            if photo is None:
                return
            if drawn is not None:
                self._erase(drawn)
            image_id = canvas.create_image(spot.x, spot.y, image=photo, anchor="nw", tags="activity_bubble")
            tx = spot.x + spot.bw / 2
            ty = spot.y + body / 2
            face = _font(app) or ("Courier", 8)
            try:
                text_id = canvas.create_text(
                    tx, ty, text=spot.text, font=face, fill="#202848",
                    tags="activity_bubble",
                )
            except Exception:
                text_id = canvas.create_text(
                    tx, ty, text=spot.text, font=("Courier", 8), fill="#202848",
                    tags="activity_bubble",
                )
            drawn = {
                "canvas": canvas, "image": image_id, "text": text_id,
                "photo": photo, "sig": sig, "x": spot.x, "y": spot.y,
            }
            self._drawn[key] = drawn
        elif drawn["x"] != spot.x or drawn["y"] != spot.y:
            canvas.coords(drawn["image"], spot.x, spot.y)
            canvas.coords(drawn["text"], spot.x + spot.bw / 2, spot.y + body / 2)
            drawn["x"] = spot.x
            drawn["y"] = spot.y
        if not inside:
            hits.append((spot.x + ox, spot.y + oy, float(spot.bw), float(spot.bh)))

    def _dots_for(self, app, board, now: float, settings) -> None:
        if not settings.spring_dots:
            self._clear_dots(app)
            return
        live: set[tuple] = set()
        parents = getattr(app, "avatars", {}) or {}
        inside = getattr(app, "_inside", {}) or {}
        home = _inside_ids(app)
        for parent_id, children in list(getattr(app, "sub_avatars", {}).items()):
            parent = parents.get(parent_id)
            if parent is None:
                continue
            for child in children:
                cid = getattr(getattr(child, "agent", None), "agent_id", "")
                if not board.spring_hot(now, parent_id, cid):
                    continue
                self._link_dots(app, parent, child, False, live)
        for parent_id, parent in list(inside.items()):
            if home and parent_id not in home:
                continue
            count = getattr(getattr(parent, "agent", None), "subagents", 0)
            if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                continue
            if not board.spring_hot(now, parent_id, parent_id + "_sub_0"):
                continue
            count = min(count, 8)
            scene = getattr(getattr(app, "dungeon", None), "scene", None)
            if scene is None:
                continue
            for index in range(count):
                left = parent.x + parent.aw + 6 + index * (_CHILD + 4)
                top = parent.y + parent.ah - _CHILD
                self._segment_dots(
                    scene, parent_id, f"{parent_id}_sub_{index}",
                    parent.x + parent.aw / 2, parent.y + parent.ah / 2,
                    left + _CHILD / 2, top + _CHILD / 2, live,
                )
        for key in list(self._dots):
            if key not in live:
                self._drop_dots(key)

    def _link_dots(self, app, parent, child, _inside: bool, live: set) -> None:
        surfaces = _surfaces(app, parent, False)
        if not surfaces:
            return
        _key, canvas, ox, oy = surfaces[0]
        try:
            x0, y0, x1, y1 = elastic_endpoints(parent, child, child_flight_mode(child))
        except Exception:
            return
        cid = getattr(getattr(child, "agent", None), "agent_id", "")
        pid = getattr(getattr(parent, "agent", None), "agent_id", "")
        self._segment_dots(
            canvas, pid, cid, x0 - ox, y0 - oy, x1 - ox, y1 - oy, live,
        )

    def _segment_dots(self, canvas, parent_id, child_id, x0, y0, x1, y1, live: set) -> None:
        points = spring_dots(x0, y0, x1, y1, 3)
        key = (id(canvas), parent_id, child_id)
        live.add(key)
        stored = self._dots.get(key)
        if stored is None:
            stored = [canvas, []]
            self._dots[key] = stored
        ids = stored[1]
        while len(ids) < len(points):
            ids.append(canvas.create_oval(0, 0, _DOT, _DOT, fill="#aa44ff", outline="", tags="activity_dot"))
        while len(ids) > len(points):
            try:
                canvas.delete(ids.pop())
            except Exception:
                ids.pop()
        for iid, (x, y) in zip(ids, points, strict=False):
            try:
                canvas.coords(iid, x - 1, y - 1, x + 2, y + 2)
            except Exception:
                return

    def _drop_dots(self, key: tuple) -> None:
        stored = self._dots.pop(key, None)
        if not stored:
            return
        canvas, ids = stored
        for iid in ids:
            try:
                canvas.delete(iid)
            except Exception:
                return

    def _clear_dots(self, app: Any) -> None:
        canvases = []
        scene = getattr(getattr(app, "dungeon", None), "scene", None)
        if scene is not None:
            canvases.append(scene)
        canvas = getattr(app, "canvas", None)
        if canvas is not None:
            canvases.append(canvas)
        board = getattr(app, "overlays", None)
        if board is not None and hasattr(board, "slots"):
            try:
                for slot in board.slots():
                    canvases.append(slot.canvas)
            except Exception:
                pass
        for canvas in canvases:
            try:
                canvas.delete("activity_dot")
            except Exception:
                continue
        self._dots.clear()

    def _erase(self, drawn: dict) -> None:
        canvas = drawn.get("canvas")
        if canvas is None:
            return
        for iid in (drawn.get("image"), drawn.get("text")):
            if iid:
                try:
                    canvas.delete(iid)
                except Exception:
                    return

    def _drop(self, key: tuple) -> None:
        drawn = self._drawn.pop(key, None)
        if drawn is not None:
            self._erase(drawn)

    def _drop_all(self) -> None:
        for key in list(self._drawn):
            self._drop(key)
