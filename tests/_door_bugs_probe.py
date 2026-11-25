"""Child process for ``test_door_bugs``: overlays on a real Tk root, fake monitors. Exit 77 without a display.

    python tests/_door_bugs_probe.py <repo root> <check>

Prints ``ok <check>``; a failed check prints ``FAIL`` and exits 1.
"""

import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app.render import photos_for  # noqa: E402
from cli_avatars.app.overlays import OverlayBoard, apply_monitor_changes, refresh_overlay_visibility  # noqa: E402
from cli_avatars.desktop.monitors import Monitor  # noqa: E402
from cli_avatars.desktop.settings import desktop_settings  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402

M1 = Monitor("m1", (0, 0, 640, 400), (0, 0, 640, 380), 120, True)
M2 = Monitor("m2", (-480, -120, 0, 280), (-480, -120, 0, 260), 144, False)


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def make_app():
    root.geometry("80x60+20000+20000")
    app = SimpleNamespace(
        root=root, canvas=None, sw=640, sh=400, desktop_escape=True, avatars={}, sub_avatars={},
        _lingering_subs=[], _dying_subs=[], _on_right_click=noop, _on_left_press=noop,
        _on_left_drag=noop, _on_left_release=noop, _on_double_click=noop,
        desktop=desktop_settings({"desktop": {"overlay_monitors": "all"}}),
    )
    app.overlays = OverlayBoard(app)
    app.overlays.sync([M1, M2], app.desktop)
    root.update()
    return app


def walker(app, aid: str, x: float, y: float) -> Avatar:
    av = Avatar(AgentInfo(aid, aid.title(), status="busy"), app.sw, app.sh, 0, registry=None)
    av.x, av.y = float(x), float(y)
    from cli_avatars.app.overlays import bind_avatar

    bind_avatar(app, av)
    app.avatars[aid] = av
    return av


class Spy:
    """Counts the calls that map, raise or focus an overlay window."""

    NAMES = ("deiconify", "lift", "tkraise", "focus_force", "focus_set", "wm_attributes", "attributes")

    def __init__(self, window) -> None:
        self.calls: list[str] = []
        for name in self.NAMES:
            real = getattr(window, name)
            setattr(window, name, self._wrap(name, real))

    def _wrap(self, name, real):
        def call(*args, **kwargs):
            self.calls.append(name)
            return real(*args, **kwargs)
        return call


def keys_never_raise_an_overlay() -> None:
    app = make_app()
    walker(app, "hero", 200, 300)
    spies = {slot.key: Spy(slot.window) for slot in app.overlays.slots()}
    refresh_overlay_visibility(app)
    root.update()
    first = list(spies["m1"].calls)
    for _ in range(40):
        root.event_generate("<KeyPress-a>")
        refresh_overlay_visibility(app)
        root.update()
    later = spies["m1"].calls[len(first):]
    slot = app.overlays.slots()[0]
    check("one map", first.count("deiconify") <= 1 and slot.window.state() == "normal", str(first))
    check("keys never raise", later == [], str(later[:6]) + f" x{len(later)}")
    app.avatars.clear()
    refresh_overlay_visibility(app)
    root.update()
    check("empty withdraws", slot.window.state() == "withdrawn", slot.window.state())


def avatars_survive_an_overlay_rebuild() -> None:
    app = make_app()
    hero = walker(app, "hero", 200, 300)
    other = walker(app, "other", 400, 300)
    for av in (hero, other):
        av.draw(app.canvas, photos_for(app))
    found = [[], [M1, M2]]

    class Terrain:
        def take_monitors(self):
            return True, found.pop(0), "flap"

        def set_world(self, *_args):
            return None

    app.terrain = Terrain()
    errors = []
    for _ in range(2):
        apply_monitor_changes(app)
        root.update()
        for av in (hero, other):
            av.frame += 1
            try:
                av.draw(app.canvas, photos_for(app))
            except tk.TclError as exc:
                errors.append(str(exc))
    check("redraw after rebuild", errors == [], str(errors))
    canvas = app.overlays.slots()[0].canvas
    kinds = sorted(canvas.type(item) for item in canvas.find_all())
    check("both on the new overlay", kinds.count("image") + kinds.count("rectangle") == 2, str(kinds))


def off_monitor_draws_nothing() -> None:
    app = make_app()
    hero = walker(app, "hero", -300, 100)
    hero.draw(app.canvas, photos_for(app))
    app.canvas.create_text(5, 5, text="mark")
    other = walker(app, "other", 100, 300)
    other.draw(app.canvas, photos_for(app))
    before = [app.canvas.coords(item) for item in app.canvas.find_all()]
    hero.x, hero.y = -300.0, 330.0
    try:
        hero.draw(app.canvas, photos_for(app))
        error = ""
    except tk.TclError as exc:
        error = str(exc)
    check("dead zone draw", error == "", error)
    after = [app.canvas.coords(item) for item in app.canvas.find_all()]
    check("others untouched", before == after, f"{before} {after}")


CHECKS = {
    "keys": keys_never_raise_an_overlay,
    "rebuild": avatars_survive_an_overlay_rebuild,
    "deadzone": off_monitor_draws_nothing,
}

try:
    CHECKS[sys.argv[2]]()
finally:
    root.destroy()
