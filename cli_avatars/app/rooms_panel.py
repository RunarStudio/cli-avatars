"""Rooms list and the topic cards beside the desktop.

Topic chips read ``STATUS_COLOR`` from the agent palette. ``topics`` has
its own map under the same name; this module does not import that one.
The chip colors stay on the agent palette until a separate fix.
"""

import time
import tkinter as tk
from dataclasses import replace
from types import SimpleNamespace

from cli_avatars.app import orch_dock
from cli_avatars.app.bots_ui import bot_signature, render_bot_sections
from cli_avatars.app.toolbar_widgets import paint
from cli_avatars.desktop.capabilities import HAS_PIL
from cli_avatars.model.agent import AGENT_STATUS_COLOR as STATUS_COLOR
from decisions import open_counts_by_room
from events import EventRejected
from rooms import (
    build_rooms,
    config_with_rooms,
    dot_color,
    fade_hex,
    fade_image,
    idle_thumbnail,
    save_rooms_pref,
    skin_base,
    warn_icon,
)
from topics import group_by_project, source_stamp, status_label, sync_topics

if HAS_PIL:
    try:
        from PIL import ImageTk
    except ImportError:
        HAS_PIL = False


def _remember_rooms(self) -> None:
    self.config = config_with_rooms(self.config, self._rooms_shown)
    try:
        save_rooms_pref(self._config_path, self._rooms_shown)
    except OSError:
        pass


def _paint_rooms_button(self) -> None:
    btn = getattr(self, "_rooms_btn", None)
    if btn is None:
        return
    try:
        if not btn.winfo_exists():
            return
    except Exception:
        return
    paint(btn, self._rooms_shown)


def _toggle_rooms(self) -> None:
    if self._rooms_shown:
        self._close_rooms()
        return
    self._rooms_shown = True
    self._open_rooms_win()
    self._paint_rooms_button()
    self._remember_rooms()


def _close_rooms(self) -> None:
    self._rooms_shown = False
    self._rooms_sig = None
    dungeon = getattr(self, "dungeon", None)
    if dungeon is not None:
        dungeon.set_left(False)
    self._paint_rooms_button()
    self._remember_rooms()


def _open_rooms_win(self) -> None:
    if getattr(self, "_rooms_list", None) is None:
        self._build_rooms_win()
    self._rooms_shown = True
    dungeon = getattr(self, "dungeon", None)
    if dungeon is not None:
        dungeon.set_left(True)
    self._update_rooms_win(force=True)


def _rooms_records(self):
    """Top-level sessions, plus each live sub avatar as its own row."""
    records = list(self.scanner.get_agents().values())
    for subs in self.sub_avatars.values():
        for sv in subs:
            if sv._floating_away:
                continue
            agent = sv.agent
            records.append(SimpleNamespace(
                agent_id=agent.agent_id,
                name=agent.name,
                status=agent.status,
                source=agent.source,
                project=agent.project,
                parent_id=agent.parent_id,
                last_seen=sv.last_active,
                skin=agent.skin,
                is_demo=agent.is_demo,
                failed=agent.failed,
                subagents=0,
            ))
    return records


def _scroll_rooms(self, event) -> None:
    canvas = getattr(self, "_rooms_canvas", None)
    if canvas is None:
        return
    try:
        if not canvas.winfo_exists():
            return
    except Exception:
        return
    if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
        canvas.yview_scroll(-1, "units")
    else:
        canvas.yview_scroll(1, "units")


def _bind_rooms_scroll(self, widget) -> None:
    widget.bind("<Button-4>", self._scroll_rooms)
    widget.bind("<Button-5>", self._scroll_rooms)
    widget.bind("<MouseWheel>", self._scroll_rooms)
    for child in widget.winfo_children():
        self._bind_rooms_scroll(child)


def _room_thumb(self, skin: str, dimmed: bool):
    if not HAS_PIL:
        return None
    key = (skin, bool(dimmed))
    if key in self._rooms_thumbs:
        return self._rooms_thumbs[key]
    photo = None
    try:
        image = idle_thumbnail(skin, 32)
        if image is not None:
            if dimmed:
                image = fade_image(image, 0.5)
            photo = ImageTk.PhotoImage(image)
    except Exception:
        photo = None
    self._rooms_thumbs[key] = photo
    return photo


def _room_warn(self, dimmed: bool):
    if not HAS_PIL:
        return None
    key = bool(dimmed)
    if key in self._rooms_warns:
        return self._rooms_warns[key]
    photo = None
    try:
        image = warn_icon(16)
        if image is not None:
            if dimmed:
                image = fade_image(image, 0.55)
            photo = ImageTk.PhotoImage(image)
    except Exception:
        photo = None
    self._rooms_warns[key] = photo
    return photo


def _build_rooms_win(self) -> None:
    """Topics list inside the Dungeon dock. No separate window."""
    bg = "#0d0d1a"
    parent = getattr(self, "_rooms_parent", None)
    if parent is None:
        return
    self._rooms_win = parent
    canvas = tk.Canvas(parent, bg=bg, highlightthickness=0, bd=0)
    self._rooms_canvas = canvas
    inner = tk.Frame(canvas, bg=bg)
    self._rooms_list = inner
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner(_event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas(event):
        canvas.itemconfig(window_id, width=event.width)

    inner.bind("<Configure>", _on_inner)
    canvas.bind("<Configure>", _on_canvas)
    canvas.pack(fill="both", expand=True)
    from cli_avatars.app import door_totals

    door_totals.attach(self, parent, canvas)
    self._bind_rooms_scroll(canvas)
    from cli_avatars.app.memmap_panel import attach

    attach(self, parent)


def _update_rooms_win(self, force: bool = False) -> None:
    if not self._rooms_shown:
        return
    win = getattr(self, "_rooms_win", None)
    if win is None or not win.winfo_exists():
        return
    from cli_avatars.app import door_totals

    door_totals.refresh(self)
    cards = build_rooms(self._rooms_records(), time.time())
    self._sync_topics(force)
    directory = self._chat_directory()
    try:
        topics = group_by_project(self._topic_rows())
    except EventRejected:
        topics = []
    try:
        counts = open_counts_by_room(directory, timeout=0.2)
    except EventRejected:
        counts = {}
    topic_sig = tuple((name, tuple(row.get("id") for row in rows)) for name, rows in topics)
    self._orch_rows = orch_dock.rows(self)
    sig = (tuple(_steady(card) for card in cards), topic_sig, tuple(sorted(counts.items())), bot_signature(self),
           orch_dock.steady(self._orch_rows))
    if not force and sig == self._rooms_sig:
        _set_ages(self, cards)
        orch_dock.set_ages(self, self._orch_rows)
        return
    self._rooms_sig = sig
    self._render_topic_groups(topics, cards, counts)


def _steady(card):
    """The card without the clock parts that change every second; those are set in place."""
    return replace(card, activity="", last_seen=0.0, subs=tuple(replace(sub, activity="") for sub in card.subs))


def _set_ages(self, cards) -> None:
    labels = getattr(self, "_rooms_ages", {})
    for card in cards:
        label = labels.get(card.agent_id)
        if label is not None and label.cget("text") != card.activity:
            label.configure(text=card.activity)


def _topic_rows(self) -> list:
    from topics import list_topics
    return list_topics(self._chat_directory(), timeout=0.2)


def _sync_topics(self, force: bool) -> None:
    directory = self._chat_directory()
    try:
        stamp = source_stamp(directory)
    except OSError:
        return
    if not force and stamp == self._topics_stamp:
        return
    try:
        sync_topics(directory, timeout=0.2)
    except EventRejected:
        return
    self._topics_stamp = stamp


def _render_topic_groups(self, groups, cards, counts) -> None:
    parent = self._rooms_list
    canvas = self._rooms_canvas
    top = canvas.yview()[0]
    self._rooms_ages = {}
    for child in parent.winfo_children():
        child.destroy()
    bg = "#0d0d1a"
    orch_dock.render(self, parent, getattr(self, "_orch_rows", None) or [])
    if not groups:
        tk.Label(parent, text="No topics", bg=bg, fg="#9a98b8",
                 font=("Courier", 10), anchor="w").pack(anchor="w", padx=12, pady=8)
    for project, topics in groups:
        label = project or "No project"
        tk.Label(parent, text=label, bg=bg, fg="#88aaff",
                 font=("Courier", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(8, 2))
        for topic in topics:
            self._render_topic_card(parent, topic, int(counts.get(str(topic.get("id")), 0)))
    render_bot_sections(self, parent)
    tk.Label(parent, text="Orchestrators", bg=bg, fg="#9a98b8",
             font=("Courier", 9), anchor="w").pack(anchor="w", padx=12, pady=(10, 2))
    if not cards:
        tk.Label(parent, text="No orchestrators", bg=bg, fg="#9a98b8",
                 font=("Courier", 10), anchor="w").pack(anchor="w", padx=12, pady=4)
    for card in cards:
        self._render_orchestrator_dot(parent, card)
    self._bind_rooms_scroll(parent)
    parent.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))
    canvas.yview_moveto(top)


def _render_topic_card(self, parent, topic, decisions: int) -> None:
    bg = "#16162a"
    topic_id = str(topic.get("id") or "")
    frame = tk.Frame(parent, bg=bg, highlightbackground="#223366",
                     highlightthickness=1, padx=8, pady=6, cursor="hand2")
    frame.pack(fill="x", padx=10, pady=3)
    members = topic.get("members") if isinstance(topic.get("members"), list) else []
    shown = [str(item) for item in members[:4]]
    thumbs = tk.Frame(frame, bg=bg)
    thumbs.pack(side="left", anchor="n")
    if not shown:
        shown = [""]
    for agent_id in shown:
        if not agent_id:
            break
        _name, skin, _status = self._member_face(agent_id)
        thumb = self._room_thumb(skin, False)
        if thumb is not None:
            shot = tk.Label(thumbs, image=thumb, bg=bg, cursor="hand2")
            shot.image = thumb
            shot.pack(side="left", padx=(0, 2))
    body = tk.Frame(frame, bg=bg)
    body.pack(side="left", fill="x", expand=True, padx=(6, 0))
    head = tk.Frame(body, bg=bg)
    head.pack(fill="x")
    tk.Label(head, text=str(topic.get("title") or topic_id), bg=bg, fg="#e8e6f4",
             font=("Courier", 10, "bold"), cursor="hand2").pack(side="left")
    status = str(topic.get("status") or "open")
    chip = tk.Label(head, text=status_label(status), bg=STATUS_COLOR.get(status, "#9a98b8"),
                    fg="#141018" if status == "waiting_on_user" else "white",
                    font=("Courier", 8), padx=4, cursor="hand2")
    chip.pack(side="left", padx=(8, 0))
    if decisions:
        tk.Label(head, text=f"decisions {decisions}", bg=bg, fg="#9a98b8",
                 font=("Courier", 8), cursor="hand2").pack(side="right")
    dots = tk.Frame(body, bg=bg)
    dots.pack(fill="x", pady=(4, 0))
    for agent_id in members[:8]:
        _name, _skin, agent_status = self._member_face(str(agent_id))
        tk.Label(dots, text="●", bg=bg, fg=dot_color(agent_status),
                 font=("Courier", 8), cursor="hand2").pack(side="left", padx=(0, 2))
    self._bind_topic_click(frame, topic_id)


def _bind_topic_click(self, widget, topic_id: str) -> None:
    widget.bind("<Button-1>", lambda _event, topic_id=topic_id: self._select_topic(topic_id))
    for child in widget.winfo_children():
        self._bind_topic_click(child, topic_id)


def _select_topic(self, topic_id: str) -> None:
    """Open this topic in the chat window. The id is a room name, not a command."""
    if not topic_id:
        return
    self._show_chat(topic_id=topic_id)


def _member_face(self, agent_id: str) -> tuple:
    info = self._live_agent(agent_id)
    if info is None or getattr(info, "is_demo", False):
        return agent_id or "member", "caine", "idle"
    name = getattr(info, "name", "") or agent_id
    skin = skin_base(getattr(info, "skin", "") or "") or "caine"
    status = str(getattr(info, "status", "") or "idle")
    return str(name), skin, status


def _live_agent(self, agent_id: str):
    agents = self.scanner.get_agents()
    if not isinstance(agents, dict):
        return None
    info = agents.get(agent_id)
    if info is not None:
        return info
    source, sep, session_id = str(agent_id).partition(":")
    if sep and source == "claude":
        info = agents.get(session_id)
        if info is not None:
            return info
    for candidate in agents.values():
        if getattr(candidate, "agent_id", None) == agent_id:
            return candidate
    return None


def _render_orchestrator_dot(self, parent, card) -> None:
    bg = "#101018" if card.dimmed else "#0d0d1a"
    ink = "#6a6a80" if card.dimmed else "#e8e6f4"
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", padx=12, pady=1)
    dot = fade_hex(card.dot) if card.dimmed else card.dot
    tk.Label(row, text="●", bg=bg, fg=dot, font=("Courier", 10)).pack(side="left")
    tk.Label(row, text=card.name, bg=bg, fg=ink,
             font=("Courier", 9)).pack(side="left", padx=(4, 0))
    if card.mark:
        tk.Label(row, text=card.mark, bg=bg, fg="#c6c6dc",
                 font=("Courier", 9)).pack(side="left", padx=(6, 0))
    for sub in card.subs:
        sub_dot = fade_hex(sub.dot) if card.dimmed else sub.dot
        tk.Label(row, text="●", bg=bg, fg=sub_dot, font=("Courier", 8)).pack(side="left", padx=(6, 0))
    if card.warn:
        icon = self._room_warn(card.dimmed)
        if icon is not None:
            warn = tk.Label(row, image=icon, bg=bg)
            warn.image = icon
            warn.pack(side="left", padx=(4, 0))
    age = tk.Label(row, text=card.activity, bg=bg, fg="#9a98b8", font=("Courier", 9))
    age.pack(side="right")
    ages = getattr(self, "_rooms_ages", None)
    if ages is not None:
        ages[card.agent_id] = age


class RoomsPanel:
    """Topics list and the orchestrator dots under it."""

    def __init__(self, app):
        self.app = app

    def _remember_rooms(self):
        return _remember_rooms(self.app)

    def _paint_rooms_button(self):
        return _paint_rooms_button(self.app)

    def _toggle_rooms(self):
        return _toggle_rooms(self.app)

    def _close_rooms(self):
        return _close_rooms(self.app)

    def _open_rooms_win(self):
        return _open_rooms_win(self.app)

    def _rooms_records(self):
        return _rooms_records(self.app)

    def _scroll_rooms(self, event):
        return _scroll_rooms(self.app, event)

    def _bind_rooms_scroll(self, widget):
        return _bind_rooms_scroll(self.app, widget)

    def _room_thumb(self, skin, dimmed):
        return _room_thumb(self.app, skin, dimmed)

    def _room_warn(self, dimmed):
        return _room_warn(self.app, dimmed)

    def _build_rooms_win(self):
        return _build_rooms_win(self.app)

    def _update_rooms_win(self, force=False):
        return _update_rooms_win(self.app, force)

    def _topic_rows(self):
        return _topic_rows(self.app)

    def _sync_topics(self, force):
        return _sync_topics(self.app, force)

    def _render_topic_groups(self, groups, cards, counts):
        return _render_topic_groups(self.app, groups, cards, counts)

    def _render_topic_card(self, parent, topic, decisions):
        return _render_topic_card(self.app, parent, topic, decisions)

    def _bind_topic_click(self, widget, topic_id):
        return _bind_topic_click(self.app, widget, topic_id)

    def _select_topic(self, topic_id):
        return _select_topic(self.app, topic_id)

    def _member_face(self, agent_id):
        return _member_face(self.app, agent_id)

    def _live_agent(self, agent_id):
        return _live_agent(self.app, agent_id)

    def _render_orchestrator_dot(self, parent, card):
        return _render_orchestrator_dot(self.app, parent, card)

    def refresh(self, frame: object = None) -> None:
        panel = getattr(self.app, "_memmap_panel", None)
        if panel is not None:
            panel.refresh()
        tasks = getattr(self.app, "_tasks_panel", None)
        if tasks is not None:
            tasks.refresh()
        return _update_rooms_win(self.app)
