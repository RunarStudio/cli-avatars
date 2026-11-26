"""Child process for ``test_grok_orch_ui``: New chat (quick Grok start, resume from the list), the main orchestrator
setting and Ask a bot on a task card, off-screen on made-up data. Exit 77 without a display.

    python tests/_grok_orch_probe.py <repo root> <data dir> <work dir>

Prints ``ok <check>`` per check; any failed check exits 1. The Grok binary is the ``grok_fake`` stub, pinned only.
"""

import json
import os
import subprocess  # noqa: TID251  # patched to prove nothing here runs a process
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

import bot_bridge  # noqa: E402
from bots.roster import load_example, save_roster  # noqa: E402
from cli_avatars.app import bot_ask, cues, new_chat, orch_settings, task_sessions, tiers  # noqa: E402
from cli_avatars.app.tasks_card import CardPanel  # noqa: E402
from cli_avatars.model.room import save_binary_pin  # noqa: E402
from cli_avatars.runner import cli_runner  # noqa: E402
from events import channel_path  # noqa: E402
from grok_fake import install  # noqa: E402
from registry.facade import Registry  # noqa: E402

DATA, WORK = Path(sys.argv[2]), Path(sys.argv[3])
SID = "d4e5f6a7-0000-4000-8000-00000000f00d"


def check(name: str, ok: bool, detail: object = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)
    print(f"ok {name}")


def texts(widget) -> list[str]:
    out = []
    for child in widget.winfo_children():
        try:
            out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        out.extend(texts(child))
    return out


ran: list = []
subprocess.Popen = lambda *a, **k: ran.append(a)  # type: ignore[assignment]
played: list = []
cues.play = lambda _app, name: played.append(name)
WORK.mkdir(parents=True, exist_ok=True)
script = install(WORK)
pin = cli_runner.confirm_binary(cli_runner.resolve_binary("grok", finder=lambda _n: str(script), templated=True))
save_binary_pin(DATA, "grok", pin.path, pin.size, pin.mtime_ns, pin.shim)

shown, picked = [], []
pane = SimpleNamespace(refresh_clis=lambda: None, pick_target=picked.append)
config_file = WORK / "config.json"
app = SimpleNamespace(root=root, config={}, _config_path=config_file, _chat_directory=lambda: DATA,
                      _chat_window=SimpleNamespace(_room=pane))
app._show_chat = lambda topic_id=None, address_id=None: shown.append(topic_id)
root.geometry("900x700")
root.update()

# Ask 1: start a Grok chat with nothing picked, then reopen it from the list.
nc = new_chat.open_card(app)
check("new chat defaults to the main orchestrator", nc.cli.get() == "grok", nc.cli.get())
nc.start()
check("quick grok chat starts with nothing picked", shown[-1] == "chat-1" and picked[-1] == "grok", (shown, picked))
task_sessions.remember(DATA, "chat-1", "grok", SID)
nc = new_chat.open_card(app)
row = next((r for r in nc.recent if r["id"] == "chat-1"), None)
check("chat list shows it with resume", row is not None and row["cli"] == "grok" and row["resumes"], row)
check("chat list buttons say resumes", any("resumes" in str(b.cget("text")) for b in nc.recent_buttons))
nc.reach("chat-1", "grok")
check("reopen picks its cli", shown[-1] == "chat-1" and picked[-1] == "grok" and not nc.card.alive())
check("resume id kept for the next send", task_sessions.session(DATA, "chat-1", "grok") == SID)

# Ask 2: the main orchestrator in Settings, switched live and saved.
tab = tk.Frame(root, bg="#0d0d1a")
tab.place(x=0, y=0, width=700, height=200)
rows = orch_settings.mount(app, tab)
check("setting shows grok by default", rows["var"].get() == "grok")
rows["chips"]["claude"].invoke()
saved = json.loads(config_file.read_text(encoding="utf-8"))
check("switch saves config.json", saved.get("orchestrator") == {"main": "claude"}, saved)
check("switch is live", tiers.main_cli(app.config) == "claude" and "Claude sits on the throne" in rows["note"].cget("text"))
nc = new_chat.open_card(app)
claude_ok = str(nc.chips["claude"].cget("state")) == "normal"
check("new chat follows the switch", nc.cli.get() == ("claude" if claude_ok else "grok"), nc.cli.get())
nc.card.close()
rows["chips"]["grok"].invoke()
check("switch back to grok", tiers.main_cli(app.config) == "grok")
tab.destroy()

# Ask 3: Ask a bot from a task card; a fake answer file lands on the card and in its chat.
save_roster(DATA / "bots" / "roster.json", load_example())
reg = Registry(DATA)
card = reg.task_create("lantern", "Count the glass apples")
from registry import task_chats  # noqa: E402

room = task_chats.start_chat(reg, card["id"], "grok")[1]["room"]
card = reg.task_get(card["id"])
panel = CardPanel(root, lambda *a, **k: SimpleNamespace(errors={}, card=card), lambda: [], lambda: None,
                  pack_dir=lambda: DATA)
panel.frame.place(x=0, y=0, width=360, height=680)
panel.show_card(card)
root.update()
check("card has the bot asks slip", panel.asks is not None and panel.asks.ask_btn.winfo_exists())
panel.asks.ask_btn.invoke()
picker = root._bot_picker
check("picker lists the roster groups", len(picker.ids) >= 20 and any("Personal" in picker.list.get(i)
                                                                         for i in range(picker.list.size())))
picker.search.insert(0, "grok bot")
picker._fill()
check("search narrows the list", picker.ids == ["grok-bot"], picker.ids)
picker.text.insert("1.0", "Which apples ripen first?")
sent = picker.send()
outbox = bot_bridge.root(DATA, {}) / "outbox" / f"{sent['id']}.json"
check("send writes the hand-off file", outbox.is_file() and json.loads(outbox.read_text())["card"] == card["id"])
check("slip shows pending", "pending" in " ".join(texts(panel.asks.rows)))
second = bot_ask.open_picker(root, DATA, card=card["id"])
second.pick("dwight")
second.text.insert("1.0", "Any beets near the orchard?")
second.send()
panel.asks.tick()
check("two asks open at once", panel.asks.title.cget("text") == "Bot asks (2 open)", panel.asks.title.cget("text"))
inbox = outbox.parent.parent / "inbox"
inbox.mkdir(parents=True, exist_ok=True)
(inbox / outbox.name).write_text(json.dumps({"schema_version": 1, "id": sent["id"], "bot": "grok-bot",
                                             "answer": "The west row, by Friday.",
                                             "answered_at": "2026-11-26T10:00:00Z"}), encoding="utf-8")
landed = bot_ask.step(app)
check("answer lands", [r["id"] for r in landed] == [sent["id"]])
check("answer cue plays", played[-1:] == ["answer"], played)
panel.asks.tick()
words = " ".join(texts(panel.asks.rows))
check("slip shows answered and the answer", "answered" in words and "The west row" in words, words)
check("answer in the task's chat", "The west row" in channel_path(DATA, room).read_text(encoding="utf-8"))
check("nothing ran", ran == [], ran)
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
