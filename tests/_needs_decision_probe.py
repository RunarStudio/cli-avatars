"""Child process for ``test_needs_decision``: a room decision opened from Needs you shows the decision in the room
chat, on the Inbox, even when the room would open on Grok. Made-up data; no CLI runs; exit 77 without Tk.

    python tests/_needs_decision_probe.py <repo root> <data dir> <work dir> [shot.png]

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import os
import subprocess  # noqa: TID251  # patched to prove nothing here runs a process
import sys
import types
from pathlib import Path

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import needs_you  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from cli_avatars.app import chat, needs_panel  # noqa: E402
from cli_avatars.app.bootcheck import _ProbeHost  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.model.room import save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from decisions import ask_decision  # noqa: E402
from grok_fake import install  # noqa: E402
from topics import set_topic  # noqa: E402

DATA, WORK = Path(sys.argv[2]), Path(sys.argv[3])
QUESTION = "Clear or smoked glass for the lantern?"


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def texts(widget) -> list[str]:
    out = []
    for child in widget.winfo_children():
        if not child.winfo_ismapped():
            continue
        try:
            out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        if isinstance(child, tk.Text):
            out.append(child.get("1.0", "end"))
        out.extend(texts(child))
    return out


ran: list = []
subprocess.Popen = lambda *a, **k: ran.append(a)  # type: ignore[assignment]
WORK.mkdir(parents=True, exist_ok=True)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(install(WORK)),
                                                          templated=True))
save_binary_pin(DATA, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)
set_topic(DATA, "lantern", title="Lantern", project="lantern", status="open")
ask_decision(DATA, agent="a1b2c3d4", room="lantern", question=QUESTION,
             options=["a=Clear", "b=Smoked"])

host = _ProbeHost(root)
host.scanner = types.SimpleNamespace(bubbles=BubbleBoard(), get_agents=lambda: {})
host._chat_directory = lambda: DATA
host._rooms_records = lambda: []
host._status_parent = None
for name in ("_ensure_chat_window", "_show_chat", "_paint_chat_button", "_remember_chat_box"):
    setattr(host, name, types.MethodType(getattr(chat, name), host))
host._chat_btn = None
host.dungeon = view = DungeonWindow(host)
view.build(offscreen=True)
root.deiconify()
root.geometry("1920x1080+0+0")
root.update()
item = next((row for row in needs_you.pending(DATA) if row["kind"] == "decision"), None)
check("decision in Needs you", item is not None and item["room"] == "lantern" and not item["card"], item)
needs_panel.open_item(host, item)
for _ in range(4):
    root.update()
pane = host._chat_window._room
if len(sys.argv) > 4:
    from PIL import ImageGrab

    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab((x, y, x + 1920, y + 1080)).save(sys.argv[4])
check("room chat open on the room", host._chat_window._topic_id == "lantern" and view._right.winfo_ismapped())
check("the chat is on the Inbox", pane.target == "inbox", pane.target)
shown = texts(view._chat_host)
check("the decision shows", any(QUESTION in t for t in shown), [t[:40] for t in shown if t.strip()][:30])
check("no CLI ran", not ran, ran)
root.destroy()
print("done")
