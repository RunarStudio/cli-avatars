"""Child process for ``test_standup_desktop``: the standup in an off-screen Dungeon's Throne tab. Exit 77 without a display.

    python tests/_standup_probe.py <repo root> <data dir seeded by test_standup.seed>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
import standup  # noqa: E402
from cli_avatars.app import cues, standup_panel  # noqa: E402
from cli_avatars.app import standup_show as ss  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from registry.facade import Registry  # noqa: E402

DATA = Path(sys.argv[2])
errors: list[str] = []
root.report_callback_exception = lambda kind, value, tb: errors.append(f"{kind.__name__}: {value}")
CLOCK = [1000.0]


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 25, hour, minute)


def step(when: datetime) -> None:
    app._standup_gate = None
    standup_panel.step(app, now=when)
    root.update()


def advance(seconds: float) -> None:
    CLOCK[0] += seconds
    throne.tick()
    root.update()


def key(name: str) -> None:
    throne.canvas.focus_force()
    throne.canvas.event_generate(f"<{name}>" if len(name) > 1 else name)
    root.update()


played: list[str] = []
cues.play = lambda app, name: played.append(name)
app = SimpleNamespace(
    root=root, config={"standup": {"hour": 9}}, desktop_escape=False, _quit=noop, _toggle_rooms=noop,
    _toggle_chat=noop, _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="moon-forge"),
    _chat_directory=lambda: str(DATA), scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=noop,
)
view = DungeonWindow(app)
app.dungeon = view
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
toplevels = len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
standup_panel.CLOCK = lambda: CLOCK[0]
standup_panel.NOW = lambda: at(10, 0)

step(at(8, 30))
check("not before the hour", standup.latest(DATA) is None and view._center == "dungeon", view._center)

card = Registry(DATA).task_list("keep")[0]["id"]
focus.start(DATA, card)
step(at(9, 30))
check("held while focused", standup.latest(DATA) is None and view._center == "dungeon" and not played, str(played))
focus.leave(DATA)
step(at(9, 31))
record = standup.latest(DATA)
check("runs after focus", record is not None and len(record["entries"]) == 5)
throne = view.throne
check("throne tab opens", view._center == "throne" and throne.stage.show is not None, view._center)
check("gather cue", played.count("gather") == 1, str(played))

advance(ss.HORN_S + ss.WALK_S + 0.1)
placed = {p.actor.id for p in throne.scene().seating.placed}
check("agents gather", {e["agent"] for e in record["entries"]} <= placed, str(placed))
check("bubble shown", throne.bubble_shown() == 0, str(throne.bubble_shown()))
key("space")
check("space next", throne.bubble_shown() == 1, str(throne.bubble_shown()))
check("blip per line", played.count("blip") == 2, str(played))
stuck = next(i for i, e in enumerate(record["entries"]) if e["tone"] == "stuck")
while throne.bubble_shown() != stuck:
    key("space")
check("stuck bubble", throne.bubble_tone() == "stuck", throne.bubble_tone())
key("s")
check("s skips", throne.stage.show.frame(CLOCK[0]).phase == "return" and throne.bubble_shown() is None)
key("r")
check("r replays", throne.stage.show.frame(CLOCK[0]).phase == "horn" and played.count("gather") == 2, str(played))
key("u")
check("u runs again", standup.latest(DATA)["runs"] == 2)
store = Registry(DATA).store
check("pinned on the cards", all(standup.pinned(store.get(e["card"])) for e in standup.latest(DATA)["entries"]))
advance(600)
check("show ends", throne.stage.show is None)
step(at(15, 0))
check("not twice a day", throne.stage.show is None and standup.latest(DATA)["runs"] == 2)

focus.start(DATA, card)
gathers = played.count("gather")
key("u")
check("silent while focused", standup.latest(DATA)["runs"] == 3 and throne.stage.show is None
      and played.count("gather") == gathers, str(played))
focus.leave(DATA)
step(at(15, 5))
check("plays after focus", throne.stage.show is not None and played.count("gather") == gathers + 1, str(played))
check("no new toplevel", len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]) == toplevels)
check("no callback errors", not errors, str(errors))
root.destroy()
