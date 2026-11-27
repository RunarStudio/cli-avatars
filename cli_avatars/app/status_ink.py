"""STATUSCOLOR.1: the one state-to-colour palette and the Dungeon nameplate's coloured status word.

After the floor is drawn, ``sweep`` blanks each nameplate's status line and ``Marks`` writes the word over
it in its state colour. A canvas write happens only when the word, its colour or the plate's spot changes; a
state change brightens the word for ``PULSE_MS`` with a few ``after`` steps, then no timer is left.
"""

from __future__ import annotations

from cli_avatars.app.throne_px import mix
from status_palette import PALETTE, colour  # noqa: F401  # the one palette, re-exported

WORDS = {"blocked": "needs you"}
FONT = "DungeonF7b"
PULSE_MS = 600
PULSE = (0.8, 0.6, 0.4, 0.2, 0.0)  # white share per step; the steps span PULSE_MS


def word(status: str) -> str:
    return WORDS.get(status, status or "idle")


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def _owns_status(av) -> bool:
    return not getattr(av, "spring_mode", False) and bool(getattr(av.agent, "status", ""))


def blank(text: str) -> str:
    """The nameplate with its status line (the second) a blank of the same height."""
    lines = text.split("\n")
    if len(lines) > 1:
        lines[1] = " "
    return "\n".join(lines)


def sweep(book) -> None:
    """After ``draw_inside``: each inside plate shows its status word in colour; gone avatars lose theirs."""
    dungeon = getattr(book.app, "dungeon", None)
    scene = getattr(dungeon, "scene", None)
    if scene is None:
        return
    own, shown = marks(scene), set()
    for aid, av in list(getattr(book.app, "_inside", {}).items()):
        label = getattr(av, "lbl_id", None)
        try:
            if not label or getattr(av, "_spr_canvas", None) is not scene or scene.type(label) != "text":
                continue
            if _owns_status(av):
                want = blank(av.plate_text())
                if scene.itemcget(label, "text") != want:  # the core wrote the full plate again
                    scene.itemconfigure(label, text=want)
            own.paint(av)
            shown.add(aid)
        except Exception:
            continue
    own.keep(shown)


class Marks:
    """The coloured status words on one canvas, one text item per avatar."""

    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self._items: dict[str, int] = {}
        self._keys: dict[str, tuple] = {}
        self._shown: dict[str, str] = {}
        self._pulses: dict[str, object] = {}

    def item(self, aid: str) -> int | None:
        return self._items.get(aid)

    def paint(self, av) -> None:
        """Put ``av``'s status word on its nameplate's second line."""
        aid = av.agent.agent_id
        canvas, label = self.canvas, getattr(av, "lbl_id", None)
        spot = self._spot(label) if label and _owns_status(av) else None
        if spot is None:
            self.drop(aid)
            return
        status = av.agent.status
        key = (spot, word(status), colour(status))
        if key == self._keys.get(aid) and aid in self._items and canvas.type(self._items[aid]):
            return
        changed = self._shown.get(aid, status) != status
        self._shown[aid] = status
        item = self._items.get(aid)
        if item is None or not canvas.type(item):
            item = self._items[aid] = canvas.create_text(*spot, text=key[1], fill=key[2], font=FONT, justify="center")
            canvas.tag_raise(item, label)
        else:
            if self._keys[aid][0] != spot:
                canvas.coords(item, *spot)
            if self._keys[aid][1:] != key[1:]:
                canvas.itemconfigure(item, text=key[1], fill=key[2])
        self._keys[aid] = key
        if changed:
            self._pulse(aid, key[2], 0)

    def keep(self, aids) -> None:
        """Drop the words of avatars no longer drawn."""
        for aid in [a for a in self._items if a not in aids]:
            self.drop(aid)
        for aid in [a for a in self._shown if a not in aids]:
            self._shown.pop(aid)

    def _spot(self, label) -> tuple[float, float] | None:
        """Centre of the plate's second line, from the label's centre and box."""
        canvas = self.canvas
        try:
            at, box = canvas.coords(label), canvas.bbox(label)
            lines = canvas.itemcget(label, "text").count("\n") + 1
        except Exception:
            return None
        if not at or not box or lines < 2:
            return None
        line = (box[3] - box[1]) / lines
        return (float(at[0]), float(box[1] + line * 1.5))

    def _pulse(self, aid: str, base: str, step: int) -> None:
        canvas = self.canvas
        old = self._pulses.pop(aid, None)
        if old is not None and step == 0:
            canvas.after_cancel(old)
        item = self._items.get(aid)
        if item is None or step >= len(PULSE):
            return
        canvas.itemconfigure(item, fill=_hex(mix(base, "#ffffff", PULSE[step])) if PULSE[step] else base)
        if step + 1 < len(PULSE):
            self._pulses[aid] = canvas.after(PULSE_MS // (len(PULSE) - 1), lambda: self._pulse(aid, base, step + 1))

    def drop(self, aid: str) -> None:
        """Remove ``aid``'s word; its last state is kept so a return does not pulse."""
        item = self._items.pop(aid, None)
        self._keys.pop(aid, None)
        pending = self._pulses.pop(aid, None)
        if pending is not None:
            self.canvas.after_cancel(pending)
        if item is not None:
            self.canvas.delete(item)


def marks(scene) -> Marks:
    """The scene's one ``Marks``."""
    found = getattr(scene, "_status_marks", None)
    if not isinstance(found, Marks):
        found = scene._status_marks = Marks(scene)
    return found
