"""STANDUP in the throne room: the show's timeline and where everyone stands. No Tk, no pixels.

Horn (the orchestrator calls), gather (agents walk in through the hall door, one after another, to the spots in
front of the dais), talk (one bubble each, a stuck line a little longer), return (back out the door), done.
``next`` jumps to the next bubble, ``skip`` to the return, ``replay`` back to the horn.
"""

from __future__ import annotations

from dataclasses import dataclass

from cli_avatars.app import throne_model as tm
from cli_avatars.app.atelier import along

HORN_S = 1.6
WALK_S = 2.6
LINE_S = 3.4
STUCK_S = 4.6
STAGGER_S = 0.3
SPOTS = tuple((u, v) for u in (4.2, 7.0, 9.8, 12.6) for v in (4.1, 6.0)) + ((11.2, 8.2), (8.4, 8.2))
MAX_SPOTS = len(SPOTS)
DOOR = (tm.DOOR_U + 0.8, 0.6)
AISLE_V = 5.0


@dataclass(frozen=True)
class Frame:
    """``phase``: horn, gather, talk, return or done; ``speaker``: who talks; ``walk``: 0 at the door, 1 in place."""

    phase: str
    speaker: int | None
    walk: float


def spot(index: int) -> tuple[float, float]:
    return SPOTS[min(index, MAX_SPOTS - 1)]


def route(index: int) -> list[tuple[float, float]]:
    """Hall door, down the lane to the aisle between the crystals, along it, to the spot."""
    u, v = spot(index)
    return [DOOR, (DOOR[0], AISLE_V), (u + 1.0, AISLE_V), (u, v)]


class Show:
    """One standup's timeline from ``start`` (seconds on any steady clock)."""

    def __init__(self, entries, start: float) -> None:
        self.entries = list(entries or [])
        self.lines = [STUCK_S if e.get("tone") == "stuck" else LINE_S for e in self.entries]
        self.t0 = start
        self._cued: set = set()

    def _talk_start(self) -> float:
        return HORN_S + WALK_S

    def _line_start(self, index: int) -> float:
        return self._talk_start() + sum(self.lines[:index])

    def _return_start(self) -> float:
        return self._line_start(len(self.entries))

    def frame(self, now: float) -> Frame:
        e = max(0.0, now - self.t0)
        if e < HORN_S:
            return Frame("horn", None, 0.0)
        if e < self._talk_start():
            return Frame("gather", None, (e - HORN_S) / WALK_S)
        back = self._return_start()
        if e < back:
            index = max(i for i in range(len(self.entries)) if self._line_start(i) <= e)
            return Frame("talk", index, 1.0)
        if e < back + WALK_S:
            return Frame("return", None, 1.0 - (e - back) / WALK_S)
        return Frame("done", None, 0.0)

    def over(self, now: float) -> bool:
        return self.frame(now).phase == "done"

    def next(self, now: float) -> None:
        """Horn or gather: straight to the first bubble; talk: the next one (after the last, the return)."""
        frame = self.frame(now)
        if frame.phase in ("horn", "gather"):
            self.t0 = now - self._talk_start()
        elif frame.phase == "talk":
            self.t0 = now - self._line_start(frame.speaker + 1)

    def skip(self, now: float) -> None:
        if self.frame(now).phase in ("horn", "gather", "talk"):
            self.t0 = now - self._return_start()

    def replay(self, now: float) -> None:
        self.t0 = now
        self._cued = set()

    def cues(self, now: float) -> list[str]:
        """Cue names due since the last call: ``gather`` once at the horn, ``blip`` once per bubble."""
        frame, out = self.frame(now), []
        if frame.phase == "horn" and "gather" not in self._cued:
            self._cued.add("gather")
            out.append("gather")
        if frame.phase == "talk" and ("blip", frame.speaker) not in self._cued:
            self._cued.update({"gather", ("blip", frame.speaker)})
            out.append("blip")
        return out


def _walkers(entries, lord: tm.Actor | None) -> list[dict]:
    return [e for e in entries if lord is None or e["agent"] != lord.id]


def _progress(walk: float, index: int, count: int) -> float:
    """Each agent sets off ``STAGGER_S`` after the one before; all arrive by the end of the walk."""
    lag = min(STAGGER_S, WALK_S * 0.5 / max(1, count - 1)) / WALK_S
    span = 1.0 - lag * max(0, count - 1)
    return min(1.0, max(0.0, (walk - lag * index) / span))


def seat(frame: Frame, lord: tm.Actor | None, entries, actors: dict) -> tm.Seating:
    """The lord on the throne and the agents along their routes; past the last spot they wait outside (``more``)."""
    placed = []
    if lord is not None:
        placed.append(tm.Placed(lord, tm.THRONE_SEAT[0], tm.THRONE_SEAT[1], tm.THRONE_SEAT[2], True))
    walkers = _walkers(entries, lord)
    shown, more = walkers[:MAX_SPOTS], max(0, len(walkers) - MAX_SPOTS)
    if frame.phase in ("horn", "done"):
        return tm.Seating(tuple(placed), 0)
    for i, entry in enumerate(shown):
        t = _progress(frame.walk, i, len(shown))
        if frame.phase == "return" and t <= 0.0:
            continue
        actor = actors.get(entry["agent"]) or tm.Actor(entry["agent"], entry.get("name", ""))
        u, v = along(route(i), t)
        placed.append(tm.Placed(actor, u, v, 0.0, True))
    return tm.Seating(tuple(placed), more)


def speaker_spot(index: int, entries, lord: tm.Actor | None) -> tuple[float, float]:
    """Where entry ``index`` talks from: the throne for the lord, else its spot (the door if it waits outside)."""
    entry = entries[index]
    if lord is not None and entry["agent"] == lord.id:
        return tm.THRONE_SEAT[:2]
    walkers = _walkers(entries, lord)
    n = next(i for i, e in enumerate(walkers) if e is entry)
    return spot(n) if n < MAX_SPOTS else DOOR
