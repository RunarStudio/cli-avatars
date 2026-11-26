"""Child process for ``test_tier_settings``: Settings › Chat tier rows off-screen on made-up data. Exit 77 without a
display.

    python tests/_tier_settings_probe.py <repo root> <data dir>

Prints ``ok <check>`` per check; any failed check exits 1.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
os.environ["CLI_AVATARS_DATA_DIR"] = sys.argv[2]
try:
    import tkinter as tk

    root = tk.Tk()
except Exception:
    raise SystemExit(77)

from cli_avatars.app import door_signs, orch_settings, tier_settings, tiers  # noqa: E402

DATA = Path(sys.argv[2])
failed = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("ok " if ok else "FAIL ") + name + ("" if ok else f": {detail!r}"))
    if not ok:
        failed.append(name)


config_file = DATA / "config.json"
config_file.write_text(json.dumps({"orchestrator": {"main": "claude"}, "text": {"size": 12}}), encoding="utf-8")
app = SimpleNamespace(config=json.loads(config_file.read_text(encoding="utf-8")), _config_path=config_file)
tab = tk.Frame(root, bg="#0d0d1a")
tab.place(x=0, y=0, width=420, height=900)
orch = app._orch_settings = orch_settings.mount(app, tab)
rows = tier_settings.mount(app, tab)
root.update()
check("one row per tier", list(rows) == list(tiers.TIERS), list(rows))
check("row shows name and where", rows["topic"]["name"].cget("text") == "Topic orchestrator · simple room",
      rows["topic"]["name"].cget("text"))
check("claude suggestions", tuple(rows["main"]["model"].cget("values")) == ("fable", "opus", "sonnet", "haiku"),
      rows["main"]["model"].cget("values"))


def pick(tier: str, model: str, effort: str) -> None:
    rows[tier]["model"].set(model)
    rows[tier]["model"].event_generate("<<ComboboxSelected>>")
    rows[tier]["effort"].set(effort)
    rows[tier]["effort"].event_generate("<<ComboboxSelected>>")
    root.update()


pick("main", "opus", "medium")
pick("topic", "opus", "medium")
saved = json.loads(config_file.read_text(encoding="utf-8"))
check("pick saves config.json", saved["chat"]["tiers"]["main"] == {"model": "opus", "effort": "medium"}
      and saved["chat"]["tiers"]["topic"] == {"model": "opus", "effort": "medium"} and saved["text"] == {"size": 12},
      saved)
check("pick is live", tiers.table(app.config)["topic"]["model"] == "opus", app.config)
check("orchestrator note follows", "(opus, medium effort)" in orch["note"].cget("text"), orch["note"].cget("text"))
check("sample line follows", rows["main"]["sample"].cget("text") == "Main orchestrator: claude opus, medium effort",
      rows["main"]["sample"].cget("text"))
layout = {"rooms": [{"session": "s-main", "kind": "main", "throne": True}, {"session": "s-west", "kind": "simple"}]}
chips = {k: dict(v)["label"] for k, v in door_signs.tier_chips(layout, app.config).items()}
check("door chip follows", chips == {"s-main": "OPUS · MEDIUM", "s-west": "OPUS · MEDIUM"}, chips)

rows["task"]["model"].focus_force()
root.update()
rows["task"]["model"].set("lantern-2.1")
rows["task"]["model"].event_generate("<Return>")
root.update()
saved = json.loads(config_file.read_text(encoding="utf-8"))
check("typed model saves", saved["chat"]["tiers"]["task"]["model"] == "lantern-2.1", saved)
rows["task"]["model"].set("no good;")
rows["task"]["model"].event_generate("<Return>")
root.update()
saved = json.loads(config_file.read_text(encoding="utf-8"))
check("bad typed model saves nothing", saved["chat"]["tiers"]["task"]["model"] == "lantern-2.1"
      and "not a model name" in rows["task"]["sample"].cget("text"), (saved, rows["task"]["sample"].cget("text")))

rows["topic"]["reset"].invoke()
root.update()
saved = json.loads(config_file.read_text(encoding="utf-8"))
check("reset to default", "topic" not in saved["chat"]["tiers"] and rows["topic"]["model"].get() == "fable"
      and rows["topic"]["effort"].get() == "high", saved)

orch["chips"]["grok"].invoke()
root.update()
check("main row follows the orchestrator switch", tuple(rows["main"]["model"].cget("values")) == ()
      and rows["main"]["sample"].cget("text") == "Main orchestrator: grok's own model, medium effort",
      (rows["main"]["model"].cget("values"), rows["main"]["sample"].cget("text")))
check("no new toplevel", not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
root.destroy()
raise SystemExit(1 if failed else 0)
