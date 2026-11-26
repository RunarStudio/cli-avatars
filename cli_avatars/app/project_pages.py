"""GROK-ORCH.1: a page per task and per conversation of a project, built for a quick look. No Tk, no AI call.

Each page starts with one line, the next action, then the status, the open bot asks and the decisions; everything
else (checklist, where we are, chats, latest comments, last lines) sits folded under "More". Pages are made from the
board, the chat files and the bot bridge only. ``write`` keeps them as markdown in ``<data dir>/pages/<project>/``
with an ``index.md`` of next actions, rewriting a file only when it changed. Plain words, one count, no badges.
"""

from __future__ import annotations

import re
from pathlib import Path

from events import EventRejected

FOLDER = "pages"
COMMENTS = 3
LINE = 160
_SAFE = re.compile(r"[^a-z0-9._-]+")


def pages(directory: Path | str, slug: str, *, bridge: Path | None = None, snap=None) -> list[dict]:
    """The project's pages: open tasks first (blocked, doing, review, todo), its conversations, then done tasks."""
    import bot_bridge
    from cli_avatars.app import chat_list
    from cli_avatars.app import projects_view as pv
    from decisions import list_decisions

    snap = snap or pv.snapshot(directory)
    record = next((p for p in snap.projects if p.get("slug") == slug), None)
    if record is None:
        return []
    bridge = bridge if bridge is not None else bot_bridge.root(directory, {})
    topics, _grok, cards = pv._gather(snap, record)
    try:
        asking = list_decisions(directory, open_only=True, timeout=0.3)
    except (EventRejected, OSError):
        asking = []
    asks = bot_bridge.listing(bridge)
    out = [_task(directory, card, asking, asks) for card in cards if "archived" not in (card.get("labels") or [])]
    rooms = {chat["room"] for card in cards for chat in card.get("chats") or ()}
    names = pv._names(record) | {t["id"] for t in topics}
    for row in chat_list.rows(directory):
        mine = row["project"].lower() in names or row["room"] in names
        if row["cli"] and row["kind"] != "task" and row["room"] not in rooms and mine:
            out.append(_chat(directory, row, asking, asks))
    order = {"blocked": 0, "doing": 1, "review": 2, "todo": 3, "chat": 4, "done": 5}
    return sorted(out, key=lambda p: (order.get(p["column"], 4), p["title"].lower()))


def next_action(card: dict, decisions: list[str], asks: list[dict]) -> str:
    """One line: what to do next on this task, from its own data."""
    if decisions:
        return f"Answer: {decisions[0]}"
    if card.get("column") == "done":
        return "Nothing: it is done."
    if card.get("column") == "blocked":
        return f"Unblock: {card.get('status_note') or 'say what blocks it'}"
    for line in str(card.get("summary") or "").splitlines():
        head, _, rest = line.partition(":")
        if head.strip() in ("next", "blocked") and rest.strip():
            return f"{head.strip().capitalize()}: {rest.strip()}"
    item = next((c["text"] for c in card.get("checklist") or () if not c.get("done")), "")
    if item:
        return f"Do: {item}"
    waiting = [a for a in asks if a["status"] != "answered"]
    if waiting:
        return f"Wait for {waiting[0]['bot_name']}'s answer"
    return {"todo": "Start it: open a chat on it", "review": "Review it and move it to done",
            "doing": "Say the next step in its chat"}.get(card.get("column"), "Open it and decide the next step")


def markdown(page: dict) -> str:
    lines = [f"# {page['title']}", "", f"**Next action:** {page['next']}", "", f"Status: {page['status']}"]
    if page["asks"]:
        lines += ["", f"Open bot asks: {page['asks_open']}"] + [f"- {a}" for a in page["asks"]]
    if page["decisions"]:
        lines += ["", "Decisions waiting on you:"] + [f"- {d}" for d in page["decisions"]]
    if page["rest"]:
        lines += ["", "<details><summary>More</summary>", ""] + page["rest"] + ["", "</details>"]
    return "\n".join(lines) + "\n"


def index(slug: str, found: list[dict]) -> str:
    lines = [f"# {slug}: next actions", ""]
    lines += [f"- [{p['title']}]({p['file']}): {p['next']}" for p in found if p["column"] != "done"]
    return "\n".join(lines) + "\n"


def write(directory: Path | str, slug: str, found: list[dict]) -> int:
    """Keep the pages as markdown under ``pages/<project>/``; returns how many files changed."""
    folder = Path(directory) / FOLDER / _safe(slug)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0
    changed = 0
    for name, text in [(p["file"], markdown(p)) for p in found] + [("index.md", index(slug, found))]:
        path = folder / name
        try:
            if path.is_symlink() or (path.is_file() and path.read_text(encoding="utf-8") == text):
                continue
            path.write_text(text, encoding="utf-8")
            changed += 1
        except OSError:
            continue
    return changed


def _task(directory: Path | str, card: dict, asking: list[dict], asks: list[dict]) -> dict:
    from board.model import effective_progress

    rooms = {chat["room"] for chat in card.get("chats") or ()}
    decisions = [str(d.get("question") or "") for d in asking if d.get("card") == card["id"] or d.get("room") in rooms]
    own = [a for a in asks if a["card"] == card["id"]]
    progress = effective_progress(card)
    status = " · ".join(x for x in (card.get("column", ""), f"{progress}%" if progress is not None else "",
                                    str(card.get("status_note") or "")) if x)
    rest = []
    if card.get("summary"):
        rest += ["Where we are:"] + [f"- {line}" for line in str(card["summary"]).splitlines()]
    if card.get("checklist"):
        rest += ["Checklist:"] + [f"- [{'x' if c.get('done') else ' '}] {c['text']}" for c in card["checklist"]]
    if card.get("chats"):
        rest += ["Chats:"] + [f"- {c['cli']} · {c['room']}" for c in card["chats"]]
    comments = [e for e in card.get("history") or () if e.get("kind") == "commented"][-COMMENTS:]
    if comments:
        rest += ["Latest comments:"] + [f"- {e['actor']}: {_cut(e.get('text', ''))}" for e in comments]
    answered = [a for a in own if a["status"] == "answered"]
    if answered:
        rest += ["Bot answers:"] + [f"- {a['bot_name']}: {_cut(a['answer'])}" for a in answered]
    return {"kind": "task", "id": card["id"], "title": card.get("title", ""), "column": card.get("column", ""),
            "next": next_action(card, decisions, own), "status": status or "no status yet",
            "asks": [f"{a['bot_name']}: {_cut(a['ask'])} ({a['status']})" for a in own if a["status"] != "answered"],
            "asks_open": sum(1 for a in own if a["status"] != "answered"), "decisions": decisions, "rest": rest,
            "file": f"task-{card['id'][:8]}.md"}


def _chat(directory: Path | str, row: dict, asking: list[dict], asks: list[dict]) -> dict:
    from cli_avatars.app import room_log
    from cli_avatars.app.chat_clis import NAMES

    decisions = [str(d.get("question") or "") for d in asking if d.get("room") == row["room"]]
    own = [a for a in asks if a["room"] == row["room"] and not a["card"]]
    waiting = [a for a in own if a["status"] != "answered"]
    lines = room_log.history(directory, row["room"], row["cli"], limit=6) if row["cli"] else []
    name = NAMES.get(row["cli"], "Inbox")
    if decisions:
        step = f"Answer: {decisions[0]}"
    elif lines and lines[-1][0] != "user":
        step = f"Reply to {name}'s last answer"
    elif waiting:
        step = f"Wait for {waiting[0]['bot_name']}'s answer"
    elif lines:
        step = f"Wait for {name} to answer"
    else:
        step = "Write the first message"
    status = " · ".join(x for x in (f"{name} chat", "resumes its session" if row["resumes"] else "",
                                    f"{row['turns']} turns" if row["turns"] else "") if x)
    rest = ["Last lines:"] + [f"- {'You' if s == 'user' else name}: {_cut(t)}" for s, t in lines] if lines else []
    return {"kind": "chat", "id": row["room"], "title": row["title"], "column": "chat", "next": step,
            "status": status, "asks": [f"{a['bot_name']}: {_cut(a['ask'])} ({a['status']})" for a in waiting],
            "asks_open": len(waiting), "decisions": decisions, "rest": rest, "file": f"chat-{_safe(row['room'])}.md"}


def _cut(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= LINE else text[:LINE - 1] + "…"


def _safe(name: str) -> str:
    return _SAFE.sub("-", str(name).lower()).strip(".-")[:64] or "project"
