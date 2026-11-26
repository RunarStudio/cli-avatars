"""PARK.1 + IDLE-PROPS.1: where an online avatar that is not working spends its time. No Tk.

Tiers on top of BODY's idle pose: quiet for ``short_s`` (60 s) takes the nearest free idle object in or beside its
room (one avatar each, two at the hearth and the dice table); quiet for ``after_s`` (``park.after_min``, 10 min)
goes to the park to sit, train or stroll; work, a blocked card or a wait on Daniel releases the spot and the
avatar walks home. Quiet time counts from the session's last activity. Reservations are kept in memory and stay
put while the tier holds.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

SHORT, LONG = "short", "long"
WORKING = ("busy", "thinking", "subagent")
HELD = ("blocked", "error")
NEAR_HOPS = 2


@dataclass(frozen=True)
class Hold:
    aid: str
    tier: str
    oid: str
    room: str
    seat: int
    feet: tuple[float, float]
    face: int
    act: str


@dataclass
class Life:
    _held: dict[str, Hold] = field(default_factory=dict)
    _homes: dict[str, str | None] = field(default_factory=dict)

    def taken(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for aid, hold in sorted(self._held.items()):
            out.setdefault(hold.oid, []).append(aid)
        return out

    def held(self) -> dict[str, Hold]:
        return dict(self._held)

    def step(self, agents, homes, busy: set, objs, stations, cfg, now: float, plan) -> dict[str, Hold]:
        """Every idle avatar's spot this frame; the ones left out wander (or work) as before."""
        want: dict[str, str] = {}
        for aid, agent in agents.items():
            if getattr(agent, "parent_id", None):
                continue
            seen = float(getattr(agent, "last_seen", 0.0) or 0.0)
            status = getattr(agent, "status", "")
            if status in WORKING and now - seen <= cfg.flow_s:
                continue
            if aid in busy or status in HELD or getattr(agent, "failed", False):
                continue
            quiet = now - seen
            if cfg.park and stations and quiet >= cfg.after_s:
                want[aid] = LONG
            elif cfg.props and objs and quiet >= cfg.short_s:
                want[aid] = SHORT
        pool = {LONG: {s.oid: s for s in stations}, SHORT: {o.oid: o for o in objs}}
        kept = {aid: h for aid, h in self._held.items()
                if want.get(aid) == h.tier and h.oid in pool[h.tier] and homes.get(aid) == self._homes.get(aid)}
        out = dict(kept)
        used: dict[str, set[int]] = {}
        for hold in kept.values():
            used.setdefault(hold.oid, set()).add(hold.seat)
        for aid in sorted(want):
            if aid in out:
                continue
            tier = want[aid]
            choice = self._pick(aid, tier, homes.get(aid), pool[tier], used, plan)
            if choice is None and tier == LONG and cfg.props:
                tier, choice = SHORT, self._pick(aid, SHORT, homes.get(aid), pool[SHORT], used, plan)
            if choice is None:
                continue
            thing, seat = choice
            used.setdefault(thing.oid, set()).add(seat)
            feet = thing.spots[seat] if thing.act != "stroll" else thing.spots[zlib.crc32(aid.encode()) % 6]
            out[aid] = Hold(aid, tier, thing.oid, thing.room, seat, feet, _face(feet, thing.centre), thing.act)
            self._homes[aid] = homes.get(aid)
        self._held = out
        return dict(out)

    def _pick(self, aid: str, tier: str, home, pool: dict, used: dict, plan):
        free = []
        for thing in pool.values():
            seats = [i for i in range(thing.seats) if i not in used.get(thing.oid, set())]
            if not seats:
                continue
            if tier == SHORT:
                hops = 0 if thing.room == home else len(plan._hops(home, thing.room) or ()) if home else 0
                if (thing.room != home and not hops) or hops > NEAR_HOPS:
                    continue
                floor = plan.floor(home) if home else None
                at = floor.centre() if floor is not None else thing.centre
                rank = (hops, math.dist(at, thing.centre), thing.oid)
            else:
                spin = (zlib.crc32(f"{aid}|{thing.oid}".encode()) % 1000) / 1000.0
                rank = (thing.act == "stroll", spin, thing.oid)
            free.append((rank, thing, seats[0]))
        if not free:
            return None
        _rank, thing, seat = min(free, key=lambda row: row[0])
        return thing, seat


def _face(p: tuple[float, float], q: tuple[float, float]) -> int:
    from cli_avatars.app.room_floor import facing

    return facing(p, q)
