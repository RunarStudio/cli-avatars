"""Made-up world for the recordings: four rooms, five avatars, tasks, chats, repos and stub CLIs. Nothing real."""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

ROOMS = (  # topic id, kind, cli, title
    ("forja-lunar", "main", "claude", "Forja lunar"),
    ("jardin-cristal", "simple", "claude", "Jardín de cristal"),
    ("archivo-brasas", "simple", "grok", "Archivo de brasas"),
    ("torre-reloj", "simple", "claude", "Torre del reloj"),
)
AGENTS = [  # the scene may change status live
    {"id": "a1b2c3d4", "name": "Orrin", "room": "forja-lunar", "status": "busy", "skin": "frost_wanderer",
     "source": "claude",
     "tool": "Edit", "file": "mapa.py", "subagents": 1},
    {"id": "e5f6a7b8", "name": "Vessa", "room": "jardin-cristal", "status": "thinking", "skin": "forest_scout",
     "source": "claude"},
    {"id": "c9d0e1f2", "name": "Pell", "room": "archivo-brasas", "status": "busy", "skin": "ember_mage",
     "source": "grok", "tool": "read_file", "file": "notas.md"},
    {"id": "b3c4d5e6", "name": "Lumen", "room": "torre-reloj", "status": "idle", "skin": "frost_wanderer",
     "source": "claude"},
]
CARDS = (  # project, title, column, progress, note, checklist
    ("forja-lunar", "Mapa de mazmorras por proyecto", "doing", 60, "Puertas y pasillos listos",
     ["Plano de salas", "Puertas", "Minimapa", "Pruebas"]),
    ("forja-lunar", "Atajos de teclado del guardián", "review", 100, "Listo para revisar", ["Flechas", "WASD", "Esc"]),
    ("forja-lunar", "Sonidos por evento", "todo", None, "", []),
    ("jardin-cristal", "Vista del móvil a 400 px", "doing", 40, "Falta el tablero", ["Mapa", "Lista", "Tablero"]),
    ("jardin-cristal", "Burbujas de «te necesita»", "done", 100, "", []),
    ("archivo-brasas", "Resumen diario por agente", "doing", 75, "Ordenando por hora", ["Leer registros", "Agrupar",
                                                                                           "Texto final"]),
    ("archivo-brasas", "Exportar lo aprendido", "blocked", 20, "Espera una decisión", []),
    ("torre-reloj", "Reloj de la torre: zona horaria", "todo", None, "", []),
    ("torre-reloj", "Campana al terminar una tarea", "review", 90, "Falta el volumen", ["Sonido", "Volumen"]),
)
CHATS = {  # topic: (agent index or "user", text)
    "forja-lunar": [("user", "¿Cómo va el mapa?"), (0, "Puertas listas. Ahora el minimapa."),
                    (0, "Subagente revisando las pruebas.")],
    "jardin-cristal": [(1, "La lista ya cabe a 400 px."), ("user", "Perfecto, sigue con el tablero.")],
    "archivo-brasas": [(2, "Leí los registros de hoy: 42 eventos."), (2, "Agrupo por agente y por tarea.")],
    "torre-reloj": [(3, "Campana lista; ¿qué volumen prefieres?")],
}
WEB_PORT = 47281
REPLIES = ("Resumen listo: 42 eventos de hoy, agrupados por agente. Lo más lento fue el minimapa."
           " Siguiente: escribir el texto final.",
           "Hecho: puertas y pasillos conectados. Ahora: el minimapa enseña la sala activa."
           " Siguiente: pruebas del recorrido.", "puertas", "minimapa", "pruebas")
FOLDERS = "proyectos"
BY_PROMPT = {}

if os.environ.get("REC_LANG") == "en":  # the English recordings (2026-11-27)
    ROOMS = (
        ("moon-forge", "main", "grok", "Moon forge"),
        ("glass-garden", "simple", "claude", "Glass garden"),
        ("ember-archive", "simple", "grok", "Ember archive"),
        ("clock-tower", "simple", "claude", "Clock tower"),
    )
    AGENTS = [
        {"id": "a1b2c3d4", "name": "Orrin", "room": "moon-forge", "status": "busy", "skin": "frost_wanderer",
         "source": "grok", "tool": "edit_file", "file": "map.py", "subagents": 1},
        {"id": "e5f6a7b8", "name": "Vessa", "room": "glass-garden", "status": "thinking", "skin": "forest_scout",
         "source": "claude"},
        {"id": "c9d0e1f2", "name": "Pell", "room": "ember-archive", "status": "busy", "skin": "ember_mage",
         "source": "grok", "tool": "read_file", "file": "notes.md"},
        {"id": "b3c4d5e6", "name": "Lumen", "room": "clock-tower", "status": "idle", "skin": "frost_wanderer",
         "source": "claude"},
    ]
    CARDS = (
        ("moon-forge", "Dungeon map per project", "doing", 60, "Doors and halls done",
         ["Room plan", "Doors", "Mini-map", "Tests"]),
        ("moon-forge", "Keeper keyboard shortcuts", "review", 100, "Ready for review", ["Arrows", "WASD", "Esc"]),
        ("moon-forge", "A sound per event", "todo", None, "", []),
        ("glass-garden", "Phone view at 400 px", "doing", 40, "Board still to do", ["Map", "List", "Board"]),
        ("glass-garden", "Needs-you bubbles", "done", 100, "", []),
        ("ember-archive", "Daily recap per agent", "doing", 75, "Sorting by hour", ["Read logs", "Group",
                                                                                   "Final text"]),
        ("ember-archive", "Export what we learnt", "blocked", 20, "Waiting on a decision", []),
        ("clock-tower", "Tower clock: time zone", "todo", None, "", []),
        ("clock-tower", "Bell when a task ends", "review", 90, "Volume still open", ["Sound", "Volume"]),
    )
    CHATS = {
        "moon-forge": [("user", "How is the map going?"), (0, "Doors done. Mini-map next."),
                       (0, "A subagent is checking the tests.")],
        "glass-garden": [(1, "The list fits at 400 px now."), ("user", "Great, carry on with the board.")],
        "ember-archive": [(2, "Read today's logs: 42 events."), (2, "Grouping by agent and by task.")],
        "clock-tower": [(3, "Bell is ready; which volume do you prefer?")],
    }
    REPLIES = ("Recap ready: 42 events today, grouped by agent. The slowest part was the mini-map."
               " Next: write the final text.",
               "Done: doors and halls connected. Now: the mini-map shows the active room."
               " Next: walk-through tests.", "doors", "mini-map", "tests")
    FOLDERS = "projects"
    BY_PROMPT = {
        "what can you do": "I plan, write and check code in your projects, keep each task on the board, and ask you"
                           " when a choice is yours. Try: make a task for the tower bell.",
        "tower bell": "Plan for the bell: one soft chime per finished task, 40 % volume, quiet in focus mode."
                      " I can put it on the board as a task.",
    }

STUB = r'''#!/usr/bin/env python3
"""Made-up stand-in for the claude / grok CLI: streams a canned reply, never reads the network or a key."""
import json, sys, time
args = sys.argv[1:]
prompt = sys.stdin.read()
grok = "--permission-mode" not in args and "-p" not in args and "--output-format" not in args or "grok" in sys.argv[0]
last = prompt.strip().splitlines()[-1] if prompt.strip() else ""
if grok:
    words = GROK_REPLY.split()
else:
    words = CLAUDE_REPLY.split()
for key, reply in BY_PROMPT.items():
    if key.lower() in prompt.lower():
        words = reply.split()
def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
if grok:
    sid = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-r", "-s")),
               "6a0c0000-0000-4000-8000-000000000001")
    emit({"type": "session_start", "sessionId": sid})
    emit({"sessionUpdate": "tool_call", "title": "read_file"})
    for w in words:
        time.sleep(0.12)
        emit({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": w + " "}})
    emit({"type": "result", "stopReason": "end_turn", "sessionId": sid})
else:
    sid = args[args.index("--resume") + 1] if "--resume" in args else "c1a0de00-0000-4000-8000-000000000001"
    emit({"type": "system", "subtype": "init", "session_id": sid})
    time.sleep(1.2)
    text = " ".join(words) + "\nTASK check 3\nTASK summary done: DONE | now: NOW | next: NEXT"
    emit({"type": "assistant", "session_id": sid, "message": {"content": [{"type": "text", "text": text}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": sid})
'''


def config_path(work: Path) -> Path:
    if FOLDERS == "projects":
        return Path(os.environ["HOME"]) / ".config" / "cli-avatars" / "config.json"
    return work / "config.json"


def config(work: Path) -> dict:
    return {
        "dungeon": {"door": "closed"}, "sound": {"cues": True},
        "web": {"enabled": True, "bind": "127.0.0.1", "port": WEB_PORT, "allow_writes": True},
        "desktop": {"on_close": "quit",
                    "bootcheck": "1" in (os.environ.get("REC_MISSING_REPO"), os.environ.get("REC_BOOTCHECK"))},
    }


def stubs(work: Path) -> dict[str, Path]:
    """claude and grok stubs in the fake HOME's bin (first on PATH)."""
    out = {}
    bindir = Path(os.environ.get("HOME", work / "home")) / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for name in ("claude", "grok"):
        path = bindir / name
        grok, claude, done, now, nxt = REPLIES
        path.write_text(STUB.replace("BY_PROMPT", repr(BY_PROMPT)).replace("GROK_REPLY", repr(grok)).replace("CLAUDE_REPLY", repr(claude))
                        .replace("DONE", done).replace("NOW", now).replace("NEXT", nxt), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        out[name] = path
    return out


def seed(data: Path, work: Path) -> None:
    if data.exists():
        return
    data.mkdir(parents=True)
    config_path(work).parent.mkdir(parents=True, exist_ok=True)
    if FOLDERS == "projects":
        home = Path(os.environ["HOME"])
        (home / "Documents").mkdir(exist_ok=True)
        (home / ".gitconfig").write_text("[user]\n\tname = Notes Keeper\n\temail = keeper@example.invalid\n",
                                         encoding="utf-8")
    if os.environ.get("REC_FIRST_RUN") == "1":  # a fresh install: only the CLIs on PATH and an empty Documents
        (Path(os.environ["HOME"]) / "Documents").mkdir(exist_ok=True)
        config_path(work).write_text(json.dumps({"sound": {"cues": True}, "desktop": {"on_close": "quit"}}),
                                     encoding="utf-8")
        for a in AGENTS:  # one Grok session already running on this PC, nothing else
            a["live"] = a is AGENTS[0]
        stubs(work)
        return
    conf = config(work)
    if FOLDERS == "projects":
        conf["orchestrator"] = {"main": "grok"}
        (data / "ui").mkdir()
        (data / "ui" / "first_run.json").write_text(json.dumps({"done": True}), encoding="utf-8")
    config_path(work).write_text(json.dumps(conf), encoding="utf-8")
    ui = data / "ui"
    ui.mkdir(exist_ok=True)
    if os.environ.get("REC_TOUR") != "1":
        (ui / "tour.json").write_text(json.dumps({"seen": True}), encoding="utf-8")

    import repos
    from cli_avatars.app import session_rooms as sr
    from cli_avatars.model.room import save_binary_pin, set_working_dir
    from cli_avatars.runner import cli_runner
    from events import append_channel
    from registry.facade import Registry
    from topics import join_topic, set_summary, set_topic

    now = time.time()
    model = sr.SessionRooms(ui / "session_rooms.json")
    folders = Path(os.environ.get("HOME", work)) / FOLDERS if FOLDERS != "proyectos" else work / FOLDERS
    late = os.environ.get("REC_LATE_ROOM", "")
    for a in AGENTS:
        a["live"] = a["room"] != late
    for i, (topic, kind, cli, title) in enumerate(ROOMS):
        if topic != late:
            model.open(kind, cli, topic)
        set_topic(data, topic, title=title, project=topic, status="open", ts=now - 600 + i)
        (folders / topic).mkdir(parents=True, exist_ok=True)
        repos.add(data, title, str(folders / topic))
        set_working_dir(data, topic, str(folders / topic), check=lambda p: Path(p))
    for a in AGENTS:
        join_topic(data, a["room"], a["id"], ts=now - 500)
    set_summary(data, "forja-lunar", "Mapa por proyecto: puertas listas, minimapa en curso.")
    for topic, lines in CHATS.items():
        for n, (who, text) in enumerate(lines):
            sender = "user" if who == "user" else f"{AGENTS[who]['source']}:{AGENTS[who]['id']}"
            entry = {"ts": now - 400 + n * 30, "from": sender, "to": topic, "channel": topic, "icon": "speech",
                     "note": text, "kind": "msg"}
            if who != "user":
                entry["name"] = AGENTS[who]["name"]
            append_channel(data, entry)
    reg = Registry(data)
    owner = {a["room"]: a["id"] for a in AGENTS}
    for project, title, column, progress, note, checklist in CARDS:
        card = reg.task_create(project, title, topic=project, assignee=owner[project])
        if checklist:
            done = round(len(checklist) * (progress or 0) / 100)
            reg.task_edit(card["id"], checklist=[{"text": t, "done": i < done} for i, t in enumerate(checklist)])
        if progress is not None or note:
            reg.task_progress(card["id"], progress, note or None)
        if column != "todo":
            reg.task_move(card["id"], column, learnt="Medir antes de optimizar." if column == "done" else None)
    from cli_avatars.app import summon

    if os.environ.get("REC_MISSING_REPO") == "1":
        summon.remember(data, "forja-lunar")
        gone = folders / "faro"
        gone.mkdir()
        repos.add(data, "Faro", str(gone))
        gone.rmdir()
    if FOLDERS == "projects":
        notes_and_bots(data)
    for cli, path in stubs(work).items():
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary(cli, finder=lambda _n, p=path: str(p),
                                                                  templated=cli == "grok"))
        save_binary_pin(data, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)


def notes_and_bots(data: Path) -> None:
    """English takes: a notes folder with three topics (not yet a git repo) and three bots, one quiet for 5 h."""
    import repos  # noqa: F401  (the app's import order: repos before the app modules)
    from cli_avatars.app import first_run
    from cli_avatars.app import memory_notes as mn

    notes = first_run.default_save_dir(home=Path(os.environ["HOME"])) / "memory"
    import cli_avatars

    mn.create(notes, Path(cli_avatars.__file__).resolve().parents[1] / "tools" / "memory_curator.py")
    today = time.strftime("%Y-%m-%d")
    for cat, name, kind, updated, goal, nxt in (
            ("Dungeon", "mini-map", "topic", today, "the active room at a glance", "ring the active room"),
            ("Dungeon", "bell-sounds", "resource", "2026-01-04", "one soft sound per event", "pick the volume"),
            ("Phone", "board-view", "topic", today, "the board in one hand", "swipe between columns")):
        folder = notes / "Topics" / cat
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.md").write_text(
            f"---\ntype: {kind}\nname: {name}\ndescription: \ntopic: {cat}/{name}\nstatus: active\n"
            f"updated: {updated}\n---\nGoal: {goal}\nStatus: active\nNext action: {nxt}\n\n## Log\n", encoding="utf-8")
    (notes / "Learnings" / "Dungeon.md").write_text("---\ntype: learning\nname: Dungeon\n---\n# Dungeon\n",
                                                   encoding="utf-8")
    bots = data / "bots"
    (bots / "local" / "status").mkdir(parents=True)
    (bots / "roster.json").write_text(json.dumps({"schema_version": 1, "groups": [
        {"id": "couriers", "name": "Couriers", "collapsed": False, "order": 0, "show_in_dungeon": True}], "bots": [
        {"id": "lamplighter", "name": "Lamplighter", "emoji": "", "group_id": "couriers", "skin": ""},
        {"id": "night-owl", "name": "Night Owl", "emoji": "", "group_id": "couriers", "skin": ""},
        {"id": "bell-ringer", "name": "Bell Ringer", "emoji": "", "group_id": "couriers", "skin": "",
         "always_show": True}]}), encoding="utf-8")
    (bots / "source.json").write_text(json.dumps({"kind": "folder", "folder": "local", "interval_s": 30}),
                                      encoding="utf-8")
    now = time.time()
    for slug, ago, line in (("lamplighter", 600, "lighting the halls"), ("night-owl", 5 * 3600, "asleep"),
                            ("bell-ringer", 9 * 3600, "waiting for noon")):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - ago))
        (bots / "local" / "status" / f"{slug}.json").write_text(json.dumps(
            {"schema_version": 1, "bot": slug, "state": "idle", "line": line, "updated_at": stamp}), encoding="utf-8")
