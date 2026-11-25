"""Child process for ``test_mailroom_desktop``: the Mailroom tab in an off-screen Dungeon. Exit 77 without a display.

    python tests/_mailroom_probe.py <repo root> <data dir seeded by test_mailroom.seed>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import focus  # noqa: E402
import mailroom  # noqa: E402
from cli_avatars.app import cues, mail_panel, needs_panel  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from events import append_channel  # noqa: E402
from registry.facade import Registry  # noqa: E402

DATA = Path(sys.argv[2])
errors: list[str] = []
root.report_callback_exception = lambda kind, value, tb: errors.append(f"{kind.__name__}: {value}")


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


def tick() -> None:
    app._mail_gate = None
    mail_panel.step(app)
    root.update()


def key(name: str) -> None:
    panel.canvas.focus_force()
    panel.canvas.event_generate(f"<{name}>" if len(name) > 1 else name)
    root.update()


played: list[str] = []
cues.play = lambda app, name: played.append(name)
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _chat_window=SimpleNamespace(_topic_id="west-wing"), _chat_directory=lambda: str(DATA),
    scanner=SimpleNamespace(get_agents=lambda: {}), _show_chat=noop,
)
view = DungeonWindow(app)
app.dungeon = view
view.build(offscreen=True)
root.deiconify()
root.geometry("1366x768+0+0")
root.update()
mailroom.ingest(DATA, now=time.time() - 60)
toplevels = len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])

view.show_center("mailroom")
root.update()
panel = app._mail_panel
check("tab opens the room", view._center == "mailroom" and panel.frame.winfo_ismapped(), view._center)
check("empty room", panel.ids() == [] and panel.canvas.itemcget(panel._empty, "state") == "normal")

mailroom.post(DATA, "The apple rows need water")
append_channel(DATA, {"ts": time.time(), "from": "claude:5e6f7a8b", "to": "user", "channel": "orchard",
                      "icon": "speech", "note": "Brass or iron hinges for the orchard gate?", "kind": "msg"})
mailroom.post(DATA, "Fix the torches in the west wing")
tick()
check("three letters land", len(panel.ids()) == 3, str(panel.ids()))
check("one letter cue for the batch", played.count("letter") == 1, str(played))
check("tab counts", view._tab_mail.button.cget("text") == "Mailroom (3)", view._tab_mail.button.cget("text"))
water, hinges, torches = panel.ids()
check("sorter topics", [panel.topic_of(i) for i in (water, hinges, torches)] == ["orchard", "orchard", "west-wing"])
check("draft decision shown", panel.text_of(hinges, "draft").startswith("Decide: Brass or iron"),
      panel.text_of(hinges, "draft"))
check("task chat proposed", "+ task chat" in panel.text_of(torches, "tag"), panel.text_of(torches, "tag"))
slip_ids = {i: list(panel.slips[i]["ids"]) for i in panel.ids()}

before = len(Registry(DATA).task_list("garden"))
panel.selected = water
key("Return")
check("enter approves", len(Registry(DATA).task_list("garden")) == before + 1 and water not in panel.ids())
check("filed cue", played[-1] == "filed", str(played))

panel.selected = torches
key("t")
check("t picks the next topic", panel.topic_of(torches) == "orchard", panel.topic_of(torches))
check("slip changed in place", panel.slips[torches]["ids"] == slip_ids[torches])

panel.selected = hinges
key("b")
check("b bounces to unsorted", mailroom.public(DATA)["unsorted"][0]["id"] == hinges
      and panel.slips[hinges]["row"]["state"] == "unsorted")
check("bounced slip shows drop", panel.text_of(hinges, "bounce") == "✕ Drop")

card = Registry(DATA).task_list("keep")[0]["id"]
focus.start(DATA, card)
count = played.count("letter")
mailroom.post(DATA, "The apple rows need more water")
tick()
check("held while focused", "1 held (focus)" == panel.canvas.itemcget(panel._held, "text")
      and played.count("letter") == count, panel.canvas.itemcget(panel._held, "text"))
focus.leave(DATA)
tick()
check("released after focus", played.count("letter") == count + 1 and len(mailroom.public(DATA)["items"]) == 2)

needs_panel.open_item(app, {"kind": "mail", "key": "mail:mailroom"})
check("needs-you row opens the room", view._center == "mailroom")
view.show_center("dungeon")
root.update()
from cli_avatars.app.capture_strip import CaptureStrip  # noqa: E402

strip = CaptureStrip(SimpleNamespace(app=SimpleNamespace(_chat_directory=lambda: str(DATA))))
strip.to_mail = True
strip.entry = SimpleNamespace(get=lambda: "Sweep the orchard path")
strip.close = lambda *_a: "break"
strip._show_toast = lambda text: setattr(strip, "toasted", text)
strip.save()
check("capture mail posts", "Sweep the orchard path" in [i["text"] for i in mailroom.public(DATA)["items"]]
      and getattr(strip, "toasted", "") == "✉ In the Mailroom", getattr(strip, "toasted", ""))
check("no new toplevel", len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]) == toplevels)
check("no callback errors", not errors, str(errors))
root.destroy()
