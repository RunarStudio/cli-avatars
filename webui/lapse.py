"""TIMELAPSE on the phone: one day of ``timelapse.build`` in map pixels, read-only. No Tk.

Each avatar is a track of steps ``{m, at, route, span}``: from minute ``m`` it stands at ``at``; a step that changes
room walks ``route`` (through the doors) in the ``span`` minutes before ``m``, as the desktop's ``timelapse.walk``.
Ids are hashed; chat moments carry no text.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import recap
import timelapse
from cli_avatars.app.room_floor import Plan
from cli_avatars.app.timelapse_ghosts import spot
from webui import scene


def _hid(aid: str) -> str:
    return hashlib.blake2s(aid.encode("utf-8"), digest_size=5).hexdigest()


def build(directory: Path | str, day: date, today: date) -> dict:
    """The day for the phone; no avatars while there is no map."""
    lay = scene.layout(directory)
    found = scene._map(lay)
    out = {"day": day.isoformat(), "label": recap.day_label(day, today), "today": today.isoformat(),
           "first": recap.days(today)[-1].isoformat(), "start": 0, "map": None, "avatars": [], "tracks": {},
           "moments": [], "busy": [], "sprites": {}}
    built = timelapse.safe_build(directory, day, (lay or {}).get("rooms") or (), today=today) if found else None
    if built is None:
        return out
    _png, (w, h), (left, top) = found
    plan = Plan.from_layout(lay)

    def px(point) -> list[int]:
        return scene._px(point[0], point[1], left, top)

    out.update(start=built["start"], map={"w": w, "h": h})
    for avatar in built["avatars"]:
        aid, steps, last = avatar["id"], [], None
        for minute, room in built["paths"][aid]:
            here = spot(plan, aid, room)
            if here is None:
                continue
            step = {"m": minute, "at": px(here), "route": None, "span": 0}
            if last is not None:
                floor = plan.floor(room)
                route = plan.route(last[1], floor.name, here) if floor else [last[1], here]
                step.update(route=[px(p) for p in route], span=min(timelapse.WALK_MIN, minute - last[0]))
            steps.append(step)
            last = (minute, here)
        if steps:
            sprite = scene.sprite_key({"kind": avatar["kind"]})
            out["avatars"].append({"id": _hid(aid), "name": avatar["name"], "kind": avatar["kind"], "sprite": sprite})
            out["tracks"][_hid(aid)] = steps
    for key in sorted({a["sprite"] for a in out["avatars"]}):
        strip = scene.sprite_png(key)
        if strip:
            out["sprites"][key] = {"w": strip[1], "h": strip[2], "frames": strip[3], "feet": scene.FEET_UP,
                                   **scene.timing(key)}
    out["moments"] = [{"ts": m["ts"], "minute": m["minute"], "chat": m["chat"], "card": m["card"], "who": m["who"],
                       "aid": _hid(m["aid"]), "room": m["room"]} for m in built["moments"]]
    out["busy"] = [f["minute"] for f in built["frames"]]
    return out
