"""Child process for ``test_avatar_menu``: the avatar menu and skin panel in an off-screen Dungeon. Exit 77 without Tk.

    python tests/_avatar_menu_probe.py <repo root>

Prints ``ok <check>`` per check; any failed check exits 1. Made-up agents only.
"""

import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import avatar_menu  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.app.input import InputController  # noqa: E402
from cli_avatars.app.skin_picker import PICK, PICK_ANIMS, PICK_FRAME_MS, SkinPicker  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402
from routing import PointerGesture  # noqa: E402


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def noop(*_args, **_kwargs) -> None:
    return None


class Hall:
    def __init__(self):
        self.moved, self.dropped = [], []

    def plan(self):
        return SimpleNamespace(names=lambda: ["Hall", "Pit"])

    def room_of(self, _aid):
        return "Hall"

    def move(self, aid, room, _now):
        self.moved.append((aid, room))
        return True

    def drop(self, aid, x, y, _now):
        self.dropped.append((aid, round(x), round(y)))
        return True


load_sprites(REGISTRY)
agent = SimpleNamespace(agent_id="demo:0001", name="Pip", is_demo=True, skin="caine", status="idle", pid=1)
agents = {agent.agent_id: agent}
av = SimpleNamespace(x=200.0, y=150.0, aw=48.0, ah=48.0, agent=agent)
hall = Hall()


def hit(x, y):
    return av if av.x <= x <= av.x + av.aw and av.y <= y <= av.y + av.ah else None


opened = []
app = SimpleNamespace(
    root=root, config={}, desktop_escape=False, _quit=noop, _toggle_rooms=noop, _toggle_chat=noop,
    _create_hud_win=noop, _rooms_shown=False, _chat_shown=False, avatars={}, _inside={agent.agent_id: av},
    _gesture=PointerGesture(), _drag_av=None, _press_av=None, _drag_off=(0, 0), _drag_prev=(0, 0),
    places=SimpleNamespace(hit=hit, lands=lambda *a: False, past_client=lambda *a: False, _hall=hall),
    scanner=SimpleNamespace(get_agents=lambda: dict(agents), _lock=threading.Lock(), _agents=agents),
    _open_chat_for_avatar=opened.append,
)
picker = SkinPicker(app)
app.PICK, app.PICK_ANIMS, app.PICK_FRAME_MS = PICK, PICK_ANIMS, PICK_FRAME_MS
app._picker_sheet, app._picker_frame, app._apply_skin = picker._picker_sheet, picker._picker_frame, picker._apply_skin
view = DungeonWindow(app)
app.dungeon = view
view.build(offscreen=True)
view._right.pack_forget()
view._sash_r.pack_forget()
root.deiconify()
root.geometry("1500x900+0+0")
root.update()
pointer = InputController(app)
app._on_scene_drag = pointer.on_scene_drag
app._on_scene_release = pointer.on_scene_release


def ev(x, y):
    sx, sy = view.scene.winfo_rootx(), view.scene.winfo_rooty()
    return SimpleNamespace(x=x, y=y, x_root=sx + x, y_root=sy + y, widget=view.scene)


def click(x, y):
    pointer.on_scene_press(ev(x, y))
    pointer.on_scene_release(ev(x, y))
    root.update()


def menu():
    found = getattr(root, "_avatar_menu", None)
    return found if found is not None and found.winfo_exists() and found.winfo_manager() == "place" else None


def panel():
    found = getattr(root, "_skin_panel", None)
    return found if found is not None and found.winfo_exists() and found.winfo_manager() == "place" else None


def labels(frame):
    return [w.cget("text") for w in frame._rows]


def press_item(frame, text):
    row = next(w for w in frame._rows if w.cget("text") == text)
    row.event_generate("<ButtonRelease-1>")
    root.update()


def inside_root(widget):
    x = widget.winfo_rootx() - root.winfo_rootx()
    y = widget.winfo_rooty() - root.winfo_rooty()
    return x >= 0 and y >= 0 and x + widget.winfo_width() <= root.winfo_width() \
        and y + widget.winfo_height() <= root.winfo_height()


def no_toplevel():
    return not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


keys = [getattr(w, "_kit_key", None) for w in view._tab_dungeon.master.pack_slaves()]
check("no skins tab", "skins" not in keys and "dungeon" in keys and "tasks" in keys, keys)

click(224, 174)
m = menu()
check("click shows menu", m is not None and labels(m)[:3] == ["Chat", "Grab (hold click)", "Skin"],
      m and labels(m))
check("move to room kept", labels(m) == ["Chat", "Grab (hold click)", "Skin", "Move to room ▸"], labels(m))
check("click does not open chat", opened == [], opened)
check("menu in kit frame", m.cget("highlightbackground") == avatar_menu.GOLD and inside_root(m) and no_toplevel())

press_item(m, "Chat")
check("chat via menu", opened == [av] and menu() is None, opened)

click(224, 174)
press_item(menu(), "Move to room ▸")
check("rooms listed", labels(menu())[1:] == ["Hall ●", "Pit"], labels(menu()))
press_item(menu(), "Pit")
check("move to room", hall.moved == [(agent.agent_id, "Pit")] and menu() is None, hall.moved)

click(224, 174)
view.scene.event_generate("<ButtonPress-1>", x=600, y=500)
root.update()
check("outside click closes menu", menu() is None)

click(224, 174)
view.on_escape()
check("esc closes menu", menu() is None)

pointer.on_scene_press(ev(224, 174))
pointer.on_scene_drag(ev(260, 190))
pointer.on_scene_drag(ev(300, 220))
pointer.on_scene_release(ev(300, 220))
root.update()
check("hold drag moves, no menu", menu() is None and (av.x, av.y) == (240.0, 180.0) and len(hall.dropped) == 1,
      (av.x, av.y, hall.dropped))

av.x, av.y = 200.0, 150.0
click(224, 174)
press_item(menu(), "Grab (hold click)")
check("grab picks up", app._drag_av is av and menu() is None)
view.scene.event_generate("<Motion>", x=400, y=300)
root.update()
check("grabbed follows pointer", (av.x + av.aw / 2, av.y + av.ah / 2) == (400.0, 300.0), (av.x, av.y))
pointer.on_scene_press(ev(400, 300))
pointer.on_scene_release(ev(400, 300))
root.update()
check("next click drops", app._drag_av is None and len(hall.dropped) == 2 and menu() is None, hall.dropped)

av.x, av.y = 200.0, 150.0
click(224, 174)
press_item(menu(), "Skin")
p = panel()
check("skin panel in window", p is not None and p.master is root and no_toplevel() and menu() is None)
check("panel in kit frame", p.cget("highlightbackground") == avatar_menu.GOLD and inside_root(p))
check("avatar preselected", p._picker["agent"].get() == "Pip [demo]" and p._picker["skin"]() == "caine",
      (p._picker["agent"].get(), p._picker["skin"]()))
p._picker["select"]("ember_mage")
p._picker["apply"]()
root.update()
check("apply changes skin and closes", agent.skin == "ember_mage" and panel() is None, agent.skin)

click(224, 174)
press_item(menu(), "Skin")
view.on_escape()
root.update()
check("esc closes panel", panel() is None)

click(224, 174)
press_item(menu(), "Skin")
app._rooms_btn.event_generate("<ButtonPress-1>")
root.update()
check("outside click closes panel", panel() is None)

click(1480, 880)
check("empty click shows nothing", menu() is None)
av.x, av.y = 1060.0, 800.0
click(1080, 820)
check("menu clamped to window", menu() is not None and inside_root(menu()))
root.destroy()
