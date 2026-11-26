"""Child process for ``test_start_setup_ui``: start card, New chat card, To: line and tour on a real Tk root.

    python tests/_start_setup_probe.py <repo root> <work root>

Prints ``ok <check>`` per check; a failed check exits 1; 77 without Tk. Made-up folders, a stub binary, PATH is an
empty folder: no real CLI, network or key.
"""

import stat
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

import repos  # noqa: E402
from bubbles import BubbleBoard  # noqa: E402
from chat_window import ChatWindow, room_tools, seed_simulated, simulated_agents  # noqa: E402
from cli_avatars.app import cues, new_chat, start_card, tour, tour_steps  # noqa: E402
from cli_avatars.app.bootcheck import _ProbeHost, start_bootcheck  # noqa: E402
from cli_avatars.app.dungeon_window import DungeonWindow  # noqa: E402
from cli_avatars.model.room import load_room, save_binary_pin  # noqa: E402
from topics import ensure_topic  # noqa: E402

work = Path(sys.argv[2])
data = work / "data"
data.mkdir(parents=True)
played = []
cues.play = lambda _app, name: played.append(name)
start_card.CLOSE_MS = 50


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def pump(until, seconds: float = 8.0) -> bool:
    """Run the main loop (the boot check posts back with ``after``) until ``until()`` or the time is up."""
    end, done = time.time() + seconds, []

    def poll():
        if until():
            done.append(1)
        if done or time.time() > end:
            root.quit()
            return
        root.after(20, poll)

    root.after(0, poll)
    root.mainloop()
    return bool(done)


def toplevels() -> list:
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


stub = work / "bin" / "claude"
stub.parent.mkdir()
stub.write_bytes(b"\x7fELF stub")
stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
tools = room_tools()
pin = tools.confirm(tools.resolve("claude", path=str(stub.parent)))
save_binary_pin(data, "claude", pin.path, pin.size, pin.mtime_ns, pin.shim)
lantern = work / "lantern"
lantern.mkdir()
repos.add(data, "Lantern", str(lantern))
lantern.rmdir()

shown = []
host = _ProbeHost(root)
host.scanner = SimpleNamespace(bubbles=BubbleBoard())
host._chat_directory = lambda: data
host._show_chat = lambda topic_id=None, address_id=None: shown.append(topic_id)
host._status_parent = None
host.dungeon = DungeonWindow(host)
host.dungeon.build(offscreen=True)
root.deiconify()
root.geometry("1366x800+0+0")
root.update()
check("toolbar_new_chat", str(host._new_chat_btn.cget("text")) == "New chat")

# Start check: live rows, one missing repo folder, Browse + Save, ✓, the card closes by itself.
host._status_parent = tk.Frame(root)
host._status_parent.pack(side="bottom", fill="x")
start_bootcheck(host)
card = start_card.card(host)
check("start_card_shown", card is not None and card.card.outer.winfo_manager() == "place")
check("boot_rows_pending", len(card.rows) == 14 and any(r["status"] == "wait" for r in card.rows.values()))
check("boot_rows_live", pump(lambda: card.boot_done and "repo:lantern" in card.setup, 15))
check("boot_rows_all_done", all(r["status"] != "wait" for k, r in card.rows.items() if not k.startswith(("cli", "repo"))))
check("missing_folder_needs_you", card.rows["repo:lantern"]["status"] == "fail" and card.card.alive(),
      card.status.cget("text"))
check("fix_row_shown", card.rows["repo:lantern"]["fix"].winfo_manager() == "pack")
found = work / "found" / "lantern"
found.mkdir(parents=True)
card.browse("repo:lantern", ask=lambda _row: str(found))
check("picked_shows_name_only", card.rows["repo:lantern"]["shown"].cget("text") == "lantern")
card.save("repo:lantern")
check("row_turns_ok", pump(lambda: card.rows["repo:lantern"]["status"] == "ok"))
check("card_closes", pump(lambda: not card.card.alive()))
check("saved_cue", "filed" in played, played)
check("tour_follows_start_card", getattr(host, "_tour", None) is not None and host._tour.alive())
host._tour.close()
check("no_new_window", not toplevels())
host._bootcheck_label.event_generate("<Button-1>")
check("status_line_reopens", pump(lambda: start_card.card(host) is not None))
start_card.card(host).card.close()

# New chat: a recent chat in one click, then a new one with Claude.
ensure_topic(data, "west-keep", title="West keep")
nc = new_chat.open_card(host)
check("recent_listed", [r["id"] for r in nc.recent][:1] == ["west-keep"])
check("cli_greyed_when_missing", str(nc.chips["grok"].cget("state")) == "disabled"
      and str(nc.chips["claude"].cget("state")) == "normal")
nc.reach("west-keep")
check("reach_in_one_click", shown[-1] == "west-keep" and not nc.card.alive())
nc = new_chat.open_card(host)
nc.name.insert(0, "Moon Garden")
nc.cli.set("claude")
nc.start()
check("start_opens_new_chat", shown[-1] == "moon-garden" and "claude" in load_room(data, "moon-garden").participants)
check("chat_start_cue", played[-1] == "pack", played)
nc = new_chat.open_card(host, "west-keep")
check("room_preselects_topic", nc.topic.get() == "West keep")
nc.card.close()

# To: line in plain words; the raw id only in the tooltip.
seed_simulated(data)
window = ChatWindow(root, directory=data, agents=simulated_agents(), config={}, offscreen=True,
                    on_new_chat=lambda: shown.append("new"))
window.open(topic_id="hooks", address_id="abcd1234_sub_0")
root.update()
text = str(window._to_btn.cget("text"))
check("to_line_plain", text.startswith("To: ") and text.count(" · ") == 2 and "abcd1234" not in text, text)
check("to_line_tooltip_has_id", "abcd1234" in window._to_btn._kit_reason)
window._new_chat_btn.invoke()
check("composer_new_chat", shown[-1] == "new")
window.hide()

# Tour: callouts placed over the window, Next through the steps on screen, Done marks it seen.
t = tour.start(host)
check("tour_first_step", t.alive() and t.shown == ["chat"] and t.card.outer.winfo_manager() == "place")
steps = 1
while t.alive() and steps < 10:
    t.next()
    root.update()
    steps += 1
check("tour_walked", t.shown[:2] == ["chat", "new_chat"] and len(t.shown) >= 3, t.shown)
check("tour_seen", not tour_steps.due(data))
check("tour_no_window", not [w for w in toplevels() if w is not window.win])
root.destroy()
print("done")
