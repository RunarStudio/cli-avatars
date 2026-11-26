"""Child process for ``test_skin_picker``: open, browse, pick and apply in an off-screen Dungeon. Exit 77 without Tk.

    python tests/_skin_picker_probe.py <repo root> <temp dir>

Prints ``ok <check>`` per check; any failed check exits 1. Made-up agents only.
"""

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import avatar_menu, cues  # noqa: E402
import text_fonts as fonts  # noqa: E402
from cli_avatars.app.skin_picker import PICK, PICK_ANIMS, PICK_FRAME_MS, SkinPicker  # noqa: E402
from cli_avatars.app.skin_picks import SkinPicks  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.sprites.registry import REGISTRY, load_sprites  # noqa: E402


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


played = []
cues._player = lambda name, app: played.append(name)
load_sprites(REGISTRY)
store = Path(sys.argv[2]) / "ui" / "avatar_skins.json"
agents = {"fx1": AgentInfo("fx1", "Moss", source="claude", skin="meowatar"),
          "fx2": AgentInfo("fx2", "Moss", source="claude", skin="amongo")}
bot = AgentInfo("bot:owl", "Owl", source="bot", skin="amongo")
inside = {aid: SimpleNamespace(agent=a) for aid, a in agents.items()}
inside[bot.agent_id] = SimpleNamespace(agent=bot)
app = SimpleNamespace(root=root, config={}, scanner=SimpleNamespace(
    get_agents=lambda: dict(agents), _lock=threading.Lock(), _agents=agents), _inside=inside, avatars={},
    skin_picks=SkinPicks(store))
picker = SkinPicker(app)
app.PICK, app.PICK_ANIMS, app.PICK_FRAME_MS = PICK, PICK_ANIMS, PICK_FRAME_MS
app._picker_sheet, app._picker_frame, app._apply_skin = picker._picker_sheet, picker._picker_frame, picker._apply_skin
root.geometry("1400x900+0+0")
root.update()


def panel():
    return root._skin_panel._picker


def widget(text):
    stack = [root._skin_panel]
    while stack:
        w = stack.pop()
        try:
            if w.cget("text") == text:
                return w
        except tk.TclError:
            pass
        stack.extend(w.winfo_children())
    return None


avatar_menu.open_skin_panel(app, "fx2")
root.update()
p = panel()
check("opens on the clicked avatar", p["agent"].get() != "" and p["id"]() == "fx2", p["id"]())
check("shows the skin the map draws", p["skin"]() == "caine", p["skin"]())
widget("michimaru").event_generate("<Button-1>")
root.update()
check("browse and select a card", p["skin"]() == "michimaru", p["skin"]())
p["hue"].set(90)
widget(fonts.caps("APPLY SKIN")).event_generate("<Button-1>")
root.update()
check("apply changes the selected avatar", agents["fx2"].skin == "michimaru_h90" and agents["fx1"].skin == "meowatar",
      (agents["fx1"].skin, agents["fx2"].skin))
check("apply is kept on disk", json.loads(store.read_text())["picks"]["fx2"]["skin"] == "michimaru_h90")
check("apply plays a cue", played == ["shimmer"], played)
check("apply closes the panel", getattr(root, "_skin_panel", None) is None)

avatar_menu.open_skin_panel(app, "fx2")
root.update()
check("reopens on the picked skin", (panel()["skin"](), panel()["hue"].get()) == ("michimaru", 90),
      (panel()["skin"](), panel()["hue"].get()))

avatar_menu.open_skin_panel(app, "bot:owl")
root.update()
check("a bot avatar is the one selected", panel()["id"]() == "bot:owl", panel()["id"]())
panel()["select"]("ember_mage")
app._focus = {"task": "t1", "title": "", "topic": "", "waiting": 0}
widget(fonts.caps("APPLY SKIN")).event_generate("<Button-1>")
root.update()
check("a bot avatar gets the skin", SkinPicks(store).get("bot:owl") == "ember_mage" and bot.skin == "ember_mage",
      (SkinPicks(store).get("bot:owl"), bot.skin))
check("focus holds the cue", played == ["shimmer"], played)

fresh = {"fx2": AgentInfo("fx2", "Moss", source="claude", skin="amongo")}
check("restart and rescan keep it", SkinPicks(store).restore(fresh) == ["fx2"] and fresh["fx2"].skin == "michimaru_h90",
      fresh["fx2"].skin)
root.destroy()
