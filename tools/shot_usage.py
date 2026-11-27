"""USAGE.1 evidence: door chips with the model and effort each CLI reported, the Sessions panel with its Usage list
and the total, and one bridged bot's answer file with the new fields.

Made-up rooms, bots and stream lines (the ORCH.ROOM stage of ``shot_orch_rooms``) in a temporary data folder; no CLI
runs. Run it under Xvfb:

    xvfb-run -a -s "-screen 0 1366x768x24" python tools/shot_usage.py <out-dir>
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))

import shot_orch_rooms as orch_shot  # noqa: E402

orch_shot.W, orch_shot.H, orch_shot.DOCK = 1366, 940, 430
CONFIG = {"orchestrator": {"main": "grok"}, "chat": {"tiers": {"main": {"effort": "medium"}}}}
RUNS = (  # room, cli, effort flag sent, stream lines
    ("release-train", "grok", "medium", (
        {"sessionId": "7f3e0000-0000-4000-8000-000000000001", "model": "grok-stub-4"},
        {"stopReason": "end_turn", "usage": {"inputTokens": 18400, "outputTokens": 2300}})),
    ("harbor-map", "claude", "high", (
        {"type": "system", "subtype": "init", "model": "claude-stub-sonnet"},
        {"type": "result", "subtype": "success", "duration_ms": 194000, "total_cost_usd": 0.4120,
         "usage": {"input_tokens": 9100, "cache_read_input_tokens": 52000, "output_tokens": 6100}})),
    ("lantern-docs", "grok", None, ({"type": "turn_completed", "stopReason": "end_turn"},)),
)
ANSWER = {"model": "lark-stub-2", "effort": "high",
          "usage": {"tokens_in": 3200, "tokens_out": 410, "cost_usd": 0.0061, "duration_s": 12.5}}


def rooms(model) -> None:
    """The stage's rooms and cards (``shot_orch_rooms``), with the throne and one simple room on Grok."""
    from cli_avatars.app import session_rooms as sr
    from registry.facade import Registry
    from topics import ensure_topic

    for kind, cli, topic in ((sr.MAIN, "grok", "release-train"), (sr.SIMPLE, "claude", "harbor-map"),
                             (sr.SIMPLE, "grok", "lantern-docs")):
        model.open(kind, cli, topic)
        ensure_topic(orch_shot._DATA, topic, ts=1)
    reg = Registry(orch_shot._DATA)
    for topic, title, column, _note in orch_shot.CARDS:
        card = reg.task_create(topic, title, topic=topic)
        if column != "todo":
            reg.task_move(card["id"], column)


orch_shot._seed = rooms


def seed(data: Path) -> dict:
    """The made-up runs through ``usage.watch`` and one bridged bot's answer; the answer file written."""
    import bot_bridge
    from cli_avatars.app import usage

    for room, cli, effort, lines in RUNS:
        see = usage.watch(data, room, cli, effort, None)
        for obj in lines:
            see(json.dumps(obj))
    bridge = bot_bridge.root(data, CONFIG)
    roster = SimpleNamespace(bots=[SimpleNamespace(id="lark-bot", name="Lark", group_id="garden")],
                             groups=[SimpleNamespace(id="garden", name="Garden")])
    ask = bot_bridge.ask(data, bridge, roster, "lark-bot", "Which reef chart is current?", room="harbor-map")
    answer = {"schema_version": 1, "id": ask["id"], "bot": "lark-bot",
              "answer": "The spring survey; the winter one misses the new buoy.", "answered_at": "2026-11-27T18:40:00Z",
              **ANSWER}
    (bridge / "inbox").mkdir(parents=True, exist_ok=True)
    (bridge / "inbox" / f"{ask['id']}.json").write_text(json.dumps(answer, indent=2) + "\n", encoding="utf-8")
    bot_bridge.sync(data, bridge)
    return answer


def main() -> None:
    import tkinter as tk

    from cli_avatars.app.session_panel import SessionPanel

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    data = orch_shot._DATA
    answer = seed(data)
    (out / "bridge-answer.example.json").write_text(json.dumps(answer, indent=2) + "\n", encoding="utf-8")
    orch_shot.load_sprites(orch_shot.REGISTRY)
    root = tk.Tk()
    root.geometry(f"{orch_shot.W}x{orch_shot.H}+0+0")
    stage = orch_shot.Stage(root)
    stage.app.config = CONFIG
    tk.Frame(stage.dock, bg="#0d0d1a", height=40).pack(fill="x")
    SessionPanel(stage.app, stage.dock).frame.pack(fill="x")
    stage.tick(6.0)
    shot = orch_shot.caption(stage.grab(), "USAGE: door chips and Sessions show the model and effort each CLI "
                                           "reported; Usage lists tokens, cost and time, then the total")
    shot.save(out / "usage-1366.png")
    root.destroy()
    shutil.rmtree(data, ignore_errors=True)
    print("wrote", ", ".join(p.name for p in sorted(out.iterdir())))


if __name__ == "__main__":
    main()
