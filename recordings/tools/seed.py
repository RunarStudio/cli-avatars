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

STUB = r'''#!/usr/bin/env python3
"""Made-up stand-in for the claude / grok CLI: streams a canned reply, never reads the network or a key."""
import json, sys, time
args = sys.argv[1:]
prompt = sys.stdin.read()
grok = "--permission-mode" not in args and "-p" not in args and "--output-format" not in args or "grok" in sys.argv[0]
last = prompt.strip().splitlines()[-1] if prompt.strip() else ""
if grok:
    words = ("Resumen listo: 42 eventos de hoy, agrupados por agente. Lo más lento fue el minimapa."
             " Siguiente: escribir el texto final.").split()
else:
    words = ("Hecho: puertas y pasillos conectados. Ahora: el minimapa enseña la sala activa."
             " Siguiente: pruebas del recorrido.").split()
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
    text = " ".join(words) + "\nTASK check 3\nTASK summary done: puertas | now: minimapa | next: pruebas"
    emit({"type": "assistant", "session_id": sid, "message": {"content": [{"type": "text", "text": text}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": sid})
'''


def config_path(work: Path) -> Path:
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
        path.write_text(STUB, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        out[name] = path
    return out


def seed(data: Path, work: Path) -> None:
    if data.exists():
        return
    data.mkdir(parents=True)
    config_path(work).write_text(json.dumps(config(work)), encoding="utf-8")
    ui = data / "ui"
    ui.mkdir()
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
    folders = work / "proyectos"
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
    for cli, path in stubs(work).items():
        pin = cli_runner.confirm_binary(cli_runner.resolve_binary(cli, finder=lambda _n, p=path: str(p),
                                                                  templated=cli == "grok"))
        save_binary_pin(data, cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
