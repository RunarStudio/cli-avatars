"""Discord-style chat window. The overlay shows it. Nothing here is executed.

Three columns: topics, the selected thread with a composer, and the live
avatars. The composer writes the local inbox of an orchestrator. It does
not start a process, open a socket, or run the text. ROOM-CHAT.4: with the
Claude target picked, Enter or Send on Daniel's typed prompt starts one CLI
run through ``cli_runner`` (``_send_cli``); the prompt goes on stdin.

``routing.py`` chooses the inbox. A subagent click opens the parent's topic.
"""

from __future__ import annotations

import atexit
import time
from pathlib import Path
from types import SimpleNamespace

tk = None


def _load_tk():
    """Import tkinter on first use so store tests do not load a GUI."""
    global tk
    if tk is None:
        import tkinter as tk_mod
        tk = tk_mod
    return tk


from chatlog import (
    ChannelTail,
    ScrollFollow,
    default_skin,
    filter_lines,
    shown_name,
    shown_skin,
    talk_icon,
)
from decisions import answer_decision, list_decisions, pin_answered
from events import EventRejected, app_data_dir
from registry.facade import Registry
from rooms import build_rooms, idle_thumbnail
from routing import (
    ALL_ORCHESTRATORS,
    GROK_FALLBACK_ID,
    Router,
    WindowBox,
    focus_for,
    orchestrators,
    parties_from,
    recipients_for,
    routes_from_config,
    save_window_box,
    topic_address,
    unread_counts,
    window_box_from_config,
)
from topics import (
    STATUS_COLOR,
    SUMMARY_STALE,
    VISIBLE_MESSAGES,
    ensure_topic,
    get_topic,
    group_by_project,
    latest_per_topic,
    list_topics,
    source_stamp,
    status_label,
    sync_topics,
    topic_messages,
    unpin_item,
)


def install_bot_redactor() -> None:
    """Mask token-shaped snippets in bot status before the dock shows them.

    Loaded on use. Importing this module must not pull the package in.
    """
    import importlib

    from bots.status import use_redactor

    module = importlib.import_module("cli_avatars.runner.cli_runner")
    use_redactor(module.redact_secrets)


_STOP_ON_EXIT = []


def _runner():
    """``cli_runner``, loaded on use like ``install_bot_redactor``."""
    import importlib

    return importlib.import_module("cli_avatars.runner.cli_runner")


def launch_cli(request, prompt: str, event=None):
    """Start one CLI run for a prompt the user sent: Enter or Send here, or Send on the phone page (PHONE.2).

    Argv is fixed by the runner; the prompt and the room context go on stdin. Raises ``CliRejected``.
    """
    runner = _runner()
    process = runner.start(
        user_action=runner.UserAction.from_ui_event(event),
        room_id=request.room_id,
        cli=request.cli,
        binary=runner.ConfirmedBinary(cli=request.cli, **request.pin),
        working_dir=request.working_dir,
        prompt=prompt,
        topic_title=request.topic_title,
        open_cards=request.open_cards,
        permission_mode=request.mode,
        session_id=request.session_id,
        on_stdout_line=request.on_line,
        on_done=request.on_done,
    )
    if not _STOP_ON_EXIT:
        _STOP_ON_EXIT.append(atexit.register(runner.stop_all))
    return process


def room_tools() -> SimpleNamespace:
    """The runner's checks the room pane may call. None of them starts a process."""
    runner = _runner()
    return SimpleNamespace(
        validate_dir=runner.validate_working_dir,
        resolve=runner.resolve_binary,
        confirm=runner.confirm_binary,
        rejected=runner.CliRejected,
    )


BG = "#0d0d1a"
TITLE_BG = "#111133"
CARD = "#16162a"
INK = "#e8e6f4"
META = "#9a98b8"
ACCENT = "#88aaff"
LINE = "#223366"
BTN = "#334477"
FONT = ("Courier", 10)
FONT_BOLD = ("Courier", 10, "bold")
FONT_SMALL = ("Courier", 8)
FONT_TITLE = ("Courier", 11, "bold")


def simulated_agents(now: float = 1_700_000_200.0) -> list[SimpleNamespace]:
    """One Claude orchestrator, its subagent, and one Grok session.

    Projects are folder names. The subagent hangs off the Claude parent.
    """
    parent = "abcd1234"
    return [
        SimpleNamespace(
            agent_id=parent, name="Claude-west", status="busy", source="claude",
            project="cli-avatars", parent_id=None, last_seen=now - 4, skin="caine",
            is_demo=False, failed=False, subagents=1,
        ),
        SimpleNamespace(
            agent_id=f"{parent}_sub_0", name="sub-1", status="busy", source="claude",
            project="cli-avatars", parent_id=parent, last_seen=now - 2, skin="bubble",
            is_demo=False, failed=False, subagents=0,
        ),
        SimpleNamespace(
            agent_id="grok:north01", name="Grok-north", status="thinking", source="grok",
            project="cli-avatars", parent_id=None, last_seen=now - 9, skin="michimaru",
            is_demo=False, failed=False, subagents=0,
        ),
    ]


def seed_simulated(directory: Path | str) -> None:
    """Write a small local store. The text is data. It is not run."""
    from decisions import ask_decision
    from topics import join_topic, pin_item, set_summary, set_topic

    root = Path(directory)
    set_topic(root, "hooks", title="Hooks", project="cli-avatars", status="open", ts=10)
    set_topic(
        root, "sprites", title="Sprites", project="cli-avatars",
        status="waiting_on_user", ts=20,
    )
    set_topic(root, "quiet", title="Quiet", project="notes", status="done", ts=30)
    join_topic(root, "hooks", "abcd1234", ts=10)
    join_topic(root, "sprites", "grok:north01", ts=20)
    set_summary(root, "hooks", "Meet on the same window.", ts=40)
    pin_item(root, "hooks", kind="fact", text="Perch is clear.", author="abcd1234", ts=50)
    from inbox import send_message

    send_message(
        root, sender="claude:abcd1234", recipients=["abcd1234"],
        text="Walk to the middle.", room="hooks", ts=100,
    )
    Registry(root).chat_post("hooks", "Use the same window.", ["abcd1234"])
    ask_decision(
        root, agent="abcd1234", room="hooks", question="Same window?",
        options=["a=Same window", "b=Drop to the floor"], ts=200,
    )


class ChatWindow:
    """Resizable three-column chat. Size is remembered when config.json exists."""

    def __init__(
        self,
        master,
        directory,
        agents,
        config=None,
        config_path: Path | str | None = None,
        on_box=None,
        offscreen: bool = False,
        container=None,
        on_show=None,
        room_pane=None,
    ) -> None:
        self.master = master
        self._directory = directory
        self._agents = agents
        self._config_source = config if config is not None else {}
        self._config_path = None if config_path is None else Path(config_path)
        self._on_box = on_box
        self._offscreen = offscreen
        self._container = container
        self._on_show = on_show
        self._embedded = container is not None
        self.win = None
        self._shown = False
        self._topic_id = ""
        self._manual_target: str | None = None
        self._pins_open = True
        self._seen: dict[str, float] = {}
        self._router = Router()
        self._tail: ChannelTail | None = None
        self._tail_dir: Path | None = None
        self._stamp = None
        self._sig = None
        self._photos: dict[tuple, object] = {}
        self._follow = ScrollFollow()
        self._applied: WindowBox | None = None
        self._topics: list = []
        self._thread = None
        self._topic_list = None
        self._roster = None
        self._summary = None
        self._pin_box = None
        self._pin_btn = None
        self._to_btn = None
        self._entry = None
        self._status = None
        self._room_pane_factory = room_pane
        self._room = None
        self._thread_wrap = None
        if container is not None:
            self._ensure()

    @property
    def shown(self) -> bool:
        return self._shown and self.win is not None

    def directory(self) -> Path:
        value = self._directory() if callable(self._directory) else self._directory
        if value:
            return Path(value)
        return app_data_dir()

    def open(self, topic_id: str | None = None, address_id: str | None = None) -> None:
        """Show the chat. Docked chat selects its tab; a window is raised."""
        self._ensure()
        if topic_id:
            self._topic_id = topic_id
            try:
                ensure_topic(self.directory(), topic_id)
            except (EventRejected, OSError):
                pass
        if address_id:
            parties = self._parties()
            self._router.observe(parties)
            found = recipients_for(address_id, parties, self._router.routes, self._router.grok_id)
            self._manual_target = found[0] if found else None
        self._shown = True
        if self._embedded:
            if self._on_show is not None:
                try:
                    self._on_show()
                except Exception:
                    return
            self.refresh(force=True)
            return
        try:
            self.win.deiconify()
            self.win.lift()
        except Exception:
            return
        self.refresh(force=True)

    def rehome(self, container) -> None:
        """Mount the chat in another frame.

        A widget's parent cannot be a Toplevel that is not its ancestor, so
        Pop out builds the same pane again instead of packing the dock frame
        into the new window. Unsent text is kept. Nothing is executed.
        """
        text = ""
        if self._entry is not None:
            try:
                text = self._entry.get()
            except Exception:
                text = ""
        self._clear_mount()
        self._container = container
        self._embedded = True
        self._ensure()
        if text and self._entry is not None:
            try:
                self._entry.insert(0, text)
            except Exception:
                pass
        if self._shown:
            self.refresh(force=True)

    def _clear_mount(self) -> None:
        host = self.win
        if host is not None:
            try:
                if self._embedded:
                    for child in list(host.winfo_children()):
                        child.destroy()
                elif host.winfo_exists():
                    host.destroy()
            except Exception:
                pass
        self.win = None

    def hide(self) -> None:
        if not self._embedded:
            self._capture()
        self._shown = False
        if self._embedded or self.win is None:
            return
        try:
            if self.win.winfo_exists():
                self.win.withdraw()
        except Exception:
            return

    def refresh(self, force: bool = False) -> None:
        if not self._shown or self.win is None or tk is None:
            return
        try:
            if not self.win.winfo_exists():
                return
        except Exception:
            return
        directory = self.directory()
        self._sync(directory, force)
        lines = self._poll(directory)
        parties = self._parties()
        self._router.routes = routes_from_config(self._config())
        self._router.observe(parties)
        try:
            topics = list_topics(directory, timeout=0.2)
        except (EventRejected, OSError):
            topics = list(self._topics)
        self._topics = topics
        self._pick_topic(topics)
        if self._room is not None:
            self._room.sync(self._topic_id)
        if self._topic_id:
            self._mark_seen(self._topic_id, lines)
        counts = unread_counts(lines, self._seen)
        try:
            decisions = list_decisions(directory, timeout=0.2)
        except (EventRejected, OSError):
            decisions = []
        open_n: dict[str, int] = {}
        for row in decisions:
            if row.get("status") == "open" and isinstance(row.get("room"), str):
                room = str(row["room"])
                open_n[room] = open_n.get(room, 0) + 1
        topic = self._topic_record(directory)
        room_lines = latest_per_topic(
            filter_lines(lines, self._topic_id or None, None),
            VISIBLE_MESSAGES,
        )
        sig = (
            self._topic_id,
            self._manual_target,
            self._pins_open,
            tuple(counts.items()),
            tuple(sorted(open_n.items())),
            _topic_sig(topics),
            tuple((line.ts, line.sender, line.icon, line.note, line.room) for line in room_lines),
            tuple(
                (row.get("id"), row.get("status"), row.get("choice", ""))
                for row in decisions
                if row.get("room") == self._topic_id
            ),
            None if topic is None else (
                topic.get("summary"),
                tuple((item.get("id"), item.get("text")) for item in topic.get("pinned") or []),
            ),
            tuple((party.agent_id, party.name, party.source) for party in parties),
        )
        self._paint_to(parties, topic)
        if not force and sig == self._sig:
            return
        self._sig = sig
        self._render_topics(topics, counts, open_n)
        self._render_header(topic, directory)
        self._render_thread(room_lines, decisions, parties)
        self._render_roster(parties)

    def recipient_ids(self) -> list[str]:
        """Inbox ids the composer would write. Subagent ids are not included."""
        parties = self._parties()
        self._router.routes = routes_from_config(self._config())
        self._router.observe(parties)
        if self._manual_target:
            return recipients_for(
                self._manual_target, parties, self._router.routes, self._router.grok_id,
            )
        topic = None
        for row in self._topics:
            if str(row.get("id") or "") == self._topic_id:
                topic = row
                break
        members = topic.get("members") if isinstance(topic, dict) else []
        if not isinstance(members, list):
            members = []
        addr = topic_address(
            self._topic_id, parties, members, self._router.routes, self._router.grok_id,
        )
        return [addr] if addr else []

    def _ensure(self) -> None:
        _load_tk()
        if tk is None:
            raise RuntimeError("tkinter is not available")
        if self.win is not None:
            try:
                if self.win.winfo_exists():
                    return
            except Exception:
                pass
        if self._container is not None:
            self.win = self._container
            self._embedded = True
            self._mount(self._container)
            return
        win = tk.Toplevel(self.master)
        win.title("Chat")
        win.configure(bg=BG)
        win.minsize(760, 480)
        win.resizable(True, True)
        self._apply_geometry(win)
        win.protocol("WM_DELETE_WINDOW", self.hide)
        win.bind("<Escape>", lambda _event: self.hide())
        win.bind("<Configure>", self._on_configure)
        self.win = win
        self._embedded = False
        self._mount(win)

    def _mount(self, host) -> None:
        host.grid_columnconfigure(1, weight=1)
        host.grid_rowconfigure(0, weight=1)
        win = host
        left = tk.Frame(win, bg=BG, width=240)
        center = tk.Frame(win, bg=BG)
        right = tk.Frame(win, bg=BG, width=220)
        center.grid(row=0, column=1, sticky="nsew")
        # The dock is too narrow for three columns; its topics and avatars live in the Topics panel.
        if not self._embedded:
            left.grid(row=0, column=0, sticky="ns")
            right.grid(row=0, column=2, sticky="ns")
        # children use pack(), so pack_propagate is what keeps the side columns fixed
        left.pack_propagate(False)
        right.pack_propagate(False)

        tk.Label(left, text="Topics", bg=TITLE_BG, fg=ACCENT, font=FONT_TITLE,
                 anchor="w", padx=10, pady=6).pack(fill="x")
        self._topic_list = self._scroller(left)
        self._build_center(center)
        tk.Label(right, text="Avatars", bg=TITLE_BG, fg=ACCENT, font=FONT_TITLE,
                 anchor="w", padx=10, pady=6).pack(fill="x")
        self._roster = self._scroller(right)

    def _build_center(self, center) -> None:
        header = tk.Frame(center, bg="#12121f")
        header.pack(fill="x")
        self._header = header
        self._summary = tk.Label(
            header, text="", bg="#12121f", fg=INK, font=FONT,
            anchor="w", justify="left", wraplength=480,
        )
        self._pin_btn = tk.Button(
            header, text="Pins", command=self._toggle_pins,
            bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
            font=FONT_SMALL, relief="flat", padx=8, pady=1, cursor="hand2",
        )
        self._pin_box = tk.Frame(header, bg="#12121f")

        thread_wrap = tk.Frame(center, bg=BG)
        thread_wrap.pack(fill="both", expand=True)
        self._thread_wrap = thread_wrap
        self._thread = self._scroller(thread_wrap)
        self._build_composer(center)

    def _build_composer(self, center) -> None:
        composer = tk.Frame(center, bg=BG)
        composer.pack(fill="x", padx=8, pady=(0, 8))
        row = tk.Frame(composer, bg=BG)
        row.pack(fill="x", pady=(6, 4))
        self._to_btn = tk.Button(
            row, text="To:", command=self._post_to_menu,
            bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
            font=FONT, relief="flat", padx=8, pady=2, cursor="hand2",
        )
        self._to_btn.pack(side="left")
        text_row = tk.Frame(composer, bg=BG)
        text_row.pack(fill="x")
        entry = tk.Entry(
            text_row, bg="#12121f", fg=INK, insertbackground=INK,
            relief="flat", font=FONT,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=4)
        entry.bind("<Return>", self._on_enter)
        self._entry = entry
        tk.Button(
            text_row, text="Send", command=self._on_enter,
            bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
            font=FONT, relief="flat", padx=12, pady=3, cursor="hand2",
        ).pack(side="right")
        self._status = tk.Label(
            composer, text="Stored locally. Nothing here runs.",
            bg=BG, fg="#55556a", font=FONT_SMALL, anchor="w",
        )
        self._status.pack(fill="x", pady=(4, 0))
        if self._room_pane_factory is not None:
            if self._room is None:
                self._room = self._room_pane_factory(self, room_tools())
            self._room.mount(center, self._thread_wrap, composer, text_row)

    def _scroller(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        inner = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfig(window_id, width=event.width)

        inner.bind("<Configure>", _on_inner)
        canvas.bind("<Configure>", _on_canvas)
        canvas.pack(fill="both", expand=True)
        self._bind_wheel(canvas, canvas)
        inner._canvas = canvas
        return inner

    def _bind_wheel(self, canvas, widget) -> None:
        def _wheel(event, canvas=canvas):
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-1, "units")
            else:
                canvas.yview_scroll(1, "units")
            if canvas is getattr(self._thread, "_canvas", None):
                try:
                    self._follow.observe(*canvas.yview())
                except Exception:
                    return

        widget.bind("<Button-4>", _wheel)
        widget.bind("<Button-5>", _wheel)
        widget.bind("<MouseWheel>", _wheel)
        for child in widget.winfo_children():
            self._bind_wheel(canvas, child)

    def _parties(self):
        agents = self._agents() if callable(self._agents) else self._agents
        return parties_from(agents)

    def _config(self) -> dict:
        value = self._config_source() if callable(self._config_source) else self._config_source
        return value if isinstance(value, dict) else {}

    def _poll(self, directory: Path):
        if self._tail is None or self._tail_dir != directory:
            self._tail = ChannelTail(directory)
            self._tail_dir = directory
        try:
            return self._tail.poll()
        except OSError:
            return list(self._tail.lines)

    def _sync(self, directory: Path, force: bool) -> None:
        try:
            stamp = source_stamp(directory)
        except OSError:
            return
        if not force and stamp == self._stamp:
            return
        try:
            sync_topics(directory, timeout=0.2)
        except EventRejected:
            return
        self._stamp = stamp

    def _pick_topic(self, topics: list) -> None:
        ids = [str(row.get("id")) for row in topics if row.get("id")]
        if self._topic_id in ids:
            return
        self._topic_id = ids[0] if ids else ""
        self._manual_target = None

    def _mark_seen(self, topic_id: str, lines) -> None:
        newest = None
        for line in lines:
            if getattr(line, "room", None) != topic_id:
                continue
            ts = getattr(line, "ts", None)
            if isinstance(ts, (int, float)) and (newest is None or ts > newest):
                newest = float(ts)
        if newest is None:
            return
        self._seen[topic_id] = max(float(self._seen.get(topic_id, newest)), newest)

    def _topic_record(self, directory: Path):
        if not self._topic_id:
            return None
        try:
            return get_topic(directory, self._topic_id, timeout=0.2)
        except EventRejected:
            return None

    def _render_topics(self, topics, counts, open_n) -> None:
        parent = self._topic_list
        if parent is None:
            return
        for child in parent.winfo_children():
            child.destroy()
        groups = group_by_project(topics)
        if not groups:
            tk.Label(parent, text="No topics", bg=BG, fg=META, font=FONT,
                     anchor="w").pack(anchor="w", padx=10, pady=8)
        for project, rows in groups:
            tk.Label(parent, text=project or "No project", bg=BG, fg=ACCENT,
                     font=FONT_BOLD, anchor="w").pack(anchor="w", padx=10, pady=(8, 2))
            for topic in rows:
                self._topic_row(parent, topic, counts, open_n)
        self._bind_wheel(parent._canvas, parent)

    def _topic_row(self, parent, topic, counts, open_n) -> None:
        topic_id = str(topic.get("id") or "")
        selected = topic_id == self._topic_id
        bg = "#223366" if selected else CARD
        frame = tk.Frame(parent, bg=bg, highlightbackground=LINE, highlightthickness=1,
                         padx=8, pady=6, cursor="hand2")
        frame.pack(fill="x", padx=8, pady=3)
        title = str(topic.get("title") or topic_id)
        tk.Label(frame, text=title, bg=bg, fg=INK, font=FONT_BOLD,
                 anchor="w", cursor="hand2").pack(anchor="w")
        status = str(topic.get("status") or "open")
        meta = tk.Frame(frame, bg=bg)
        meta.pack(anchor="w", pady=(3, 0))
        chip_fg = "#141018" if status == "waiting_on_user" else "white"
        tk.Label(meta, text=status_label(status), bg=STATUS_COLOR.get(status, META),
                 fg=chip_fg, font=FONT_SMALL, padx=4).pack(side="left")
        unread = int(counts.get(topic_id, 0))
        decisions = int(open_n.get(topic_id, 0))
        tk.Label(meta, text=f"unread {unread}", bg=bg, fg=META,
                 font=FONT_SMALL).pack(side="left", padx=(6, 0))
        tk.Label(meta, text=f"decisions {decisions}", bg=bg, fg=META,
                 font=FONT_SMALL).pack(side="left", padx=(6, 0))
        self._click_topic(frame, topic_id)

    def _click_topic(self, widget, topic_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, topic_id=topic_id: self._select(topic_id))
        for child in widget.winfo_children():
            self._click_topic(child, topic_id)

    def _select(self, topic_id: str) -> None:
        """Show this topic. The id is a room name, not a command."""
        if not topic_id:
            return
        self._topic_id = topic_id
        self._manual_target = None
        self.refresh(force=True)

    def _render_header(self, topic, directory: Path) -> None:
        header = self._header
        for child in header.winfo_children():
            child.destroy()
        self._pin_box = tk.Frame(header, bg="#12121f")
        if topic is None:
            tk.Label(header, text="No topic", bg="#12121f", fg=META, font=FONT,
                     anchor="w").pack(anchor="w", padx=8, pady=6)
            return
        topic_id = str(topic.get("id") or "")
        head = tk.Frame(header, bg="#12121f")
        head.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(head, text=str(topic.get("title") or topic_id), bg="#12121f", fg=INK,
                 font=FONT_BOLD, anchor="w").pack(side="left")
        status = str(topic.get("status") or "open")
        tk.Label(head, text=status_label(status), bg=STATUS_COLOR.get(status, META),
                 fg="#141018" if status == "waiting_on_user" else "white",
                 font=FONT_SMALL, padx=4).pack(side="left", padx=(8, 0))
        summary = str(topic.get("summary") or "") or "No summary yet."
        tk.Label(header, text=summary, bg="#12121f", fg=INK, font=FONT,
                 anchor="w", justify="left", wraplength=520).pack(anchor="w", padx=8, pady=(4, 2))
        try:
            arrived = len(topic_messages(directory, topic_id))
            baseline = int(topic.get("summary_count") or 0)
            stale = (arrived - baseline) > SUMMARY_STALE
        except (EventRejected, TypeError, ValueError, OSError):
            stale = False
        if stale:
            tk.Label(header, text="Summary is stale. An agent can refresh it.",
                     bg="#12121f", fg="#ffcf4a", font=FONT_SMALL, anchor="w").pack(anchor="w", padx=8)
        pins = topic.get("pinned") if isinstance(topic.get("pinned"), list) else []
        label = "Hide pins" if self._pins_open else f"Pins {len(pins)}"
        self._pin_btn = tk.Button(
            header, text=label, command=self._toggle_pins,
            bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
            font=FONT_SMALL, relief="flat", padx=8, pady=1, cursor="hand2",
        )
        self._pin_btn.pack(anchor="w", padx=8, pady=(2, 4))
        if not self._pins_open:
            return
        self._pin_box.pack(fill="x", padx=8, pady=(0, 6))
        if not pins:
            tk.Label(self._pin_box, text="No pins", bg="#12121f", fg=META,
                     font=FONT_SMALL, anchor="w").pack(anchor="w")
            return
        for item in pins:
            if not isinstance(item, dict):
                continue
            row = tk.Frame(self._pin_box, bg="#12121f")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{item.get('kind') or ''}  {item.get('text') or ''}",
                     bg="#12121f", fg=INK, font=FONT_SMALL, anchor="w",
                     justify="left", wraplength=420).pack(side="left", fill="x", expand=True)
            pin_id = str(item.get("id") or "")
            tk.Button(
                row, text="Unpin",
                command=lambda topic_id=topic_id, pin_id=pin_id: self._unpin(topic_id, pin_id),
                bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
                font=FONT_SMALL, relief="flat", padx=6, pady=0, cursor="hand2",
            ).pack(side="right")

    def _toggle_pins(self) -> None:
        self._pins_open = not self._pins_open
        self.refresh(force=True)

    def _render_thread(self, lines, decisions, parties) -> None:
        parent = self._thread
        if parent is None:
            return
        saved = 0.0
        canvas = getattr(parent, "_canvas", None)
        if canvas is not None:
            try:
                saved = float(canvas.yview()[0])
            except Exception:
                saved = 0.0
        for child in parent.winfo_children():
            child.destroy()
        room_decisions = [
            row for row in decisions
            if row.get("room") == self._topic_id
        ]
        items = []
        for line in lines:
            if line.icon == "decision":
                continue
            items.append(("msg", float(line.ts), line))
        for row in room_decisions:
            try:
                ts = float(row.get("ts") or 0)
            except (TypeError, ValueError):
                ts = 0.0
            items.append(("decision", ts, row))
        items.sort(key=lambda item: item[1])
        if not items:
            tk.Label(parent, text="No messages", bg=BG, fg=META, font=FONT,
                     anchor="w").pack(anchor="w", padx=12, pady=12)
        else:
            by_id = {party.agent_id: party for party in parties}
            for index, (kind, _ts, payload) in enumerate(items):
                if kind == "decision":
                    self._render_decision(parent, payload, by_id)
                else:
                    self._render_line(parent, payload, by_id, index)
        self._bind_wheel(parent._canvas, parent)
        if canvas is not None:
            canvas.after_idle(lambda saved=saved: self._restore(canvas, saved))

    def _restore(self, canvas, saved: float) -> None:
        try:
            if not canvas.winfo_exists():
                return
            canvas.update_idletasks()
            if self._follow.stick():
                canvas.yview_moveto(1.0)
            else:
                canvas.yview_moveto(saved)
        except Exception:
            return

    def _render_line(self, parent, line, by_id, index: int) -> None:
        bg = "#12121f" if index % 2 else CARD
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", padx=8, pady=1)
        tk.Label(row, text=line.clock, bg=bg, fg=META, font=FONT, width=5,
                 anchor="w").grid(row=0, column=0, padx=(6, 4), pady=4, sticky="w")
        party = _party_for_sender(line.sender, by_id)
        live_name = party.name if party is not None else None
        name = shown_name(line, live_name)
        skin = shown_skin(line, None)
        self._thumb(row, skin, bg).grid(row=0, column=1, padx=4, pady=4)
        tk.Label(row, text=name, bg=bg, fg=INK, font=FONT_BOLD, anchor="w").grid(
            row=0, column=2, padx=4, sticky="w")
        tk.Label(row, text=line.source_label, bg=bg, fg=ACCENT, font=FONT_SMALL,
                 anchor="w").grid(row=0, column=3, padx=4, sticky="w")
        icon = self._photo(("icon", line.icon), lambda name=line.icon: talk_icon(name, 18))
        if icon is not None:
            glyph = tk.Label(row, image=icon, bg=bg)
            glyph.image = icon
            glyph.grid(row=0, column=4, padx=4)
        else:
            tk.Label(row, text=line.icon, bg=bg, fg=META, font=FONT_SMALL).grid(
                row=0, column=4, padx=4)
        tk.Label(row, text=line.note, bg=bg, fg=INK, font=FONT, anchor="w",
                 justify="left", wraplength=280).grid(
                     row=0, column=5, padx=(4, 8), pady=4, sticky="ew")
        row.grid_columnconfigure(5, weight=1)

    def _render_decision(self, parent, row, by_id) -> None:
        answered = row.get("status") == "answered"
        bg = "#12121f" if answered else CARD
        card = tk.Frame(parent, bg=bg, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", padx=8, pady=4)
        party = by_id.get(str(row.get("from") or ""))
        name = party.name if party is not None else str(row.get("from") or "")
        skin = default_skin("claude")
        self._thumb(card, skin, bg).pack(side="left", padx=6, pady=6)
        body = tk.Frame(card, bg=bg)
        body.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        tk.Label(body, text=name, bg=bg, fg=INK, font=FONT_BOLD, anchor="w").pack(anchor="w")
        tk.Label(body, text=str(row.get("question") or ""), bg=bg, fg=INK, font=FONT,
                 anchor="w", justify="left", wraplength=360).pack(anchor="w", pady=(2, 4))
        if answered:
            choice = str(row.get("choice") or "")
            label = choice
            options = row.get("options") if isinstance(row.get("options"), list) else []
            for item in options:
                if isinstance(item, dict) and item.get("letter") == choice:
                    label = f"{choice}  {item.get('text') or ''}"
                    break
            tk.Label(body, text="Answered " + label, bg=bg, fg=META, font=FONT,
                     anchor="w").pack(anchor="w")
            tk.Button(
                body, text="Pin",
                command=lambda decision_id=str(row.get("id") or ""): self._pin(decision_id),
                bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
                font=FONT, relief="flat", padx=8, pady=2, cursor="hand2",
            ).pack(anchor="w", pady=(4, 0))
            return
        decision_id = str(row.get("id") or "")
        options = row.get("options") if isinstance(row.get("options"), list) else []
        for item in options:
            if not isinstance(item, dict):
                continue
            letter = str(item.get("letter") or "")
            tk.Button(
                body, text=f"{letter}  {item.get('text') or ''}",
                command=lambda decision_id=decision_id, letter=letter: self._answer(decision_id, letter),
                bg=BTN, fg="white", activebackground="#4466aa", activeforeground="white",
                font=FONT, relief="flat", padx=8, pady=2, cursor="hand2",
            ).pack(anchor="w", pady=1)

    def _render_roster(self, parties) -> None:
        parent = self._roster
        if parent is None:
            return
        for child in parent.winfo_children():
            child.destroy()
        agents = self._agents() if callable(self._agents) else self._agents
        cards = build_rooms(agents, time.time())
        if not cards:
            tk.Label(parent, text="No avatars", bg=BG, fg=META, font=FONT,
                     anchor="w").pack(anchor="w", padx=8, pady=8)
        by_id = {party.agent_id: party for party in parties}
        for card in cards:
            self._roster_card(parent, card, by_id)
        self._bind_wheel(parent._canvas, parent)

    def _roster_card(self, parent, card, by_id) -> None:
        bg = "#101018" if card.dimmed else CARD
        frame = tk.Frame(parent, bg=bg, cursor="hand2")
        frame.pack(fill="x", padx=8, pady=4)
        top = tk.Frame(frame, bg=bg)
        top.pack(fill="x")
        shot = self._thumb(top, card.skin, bg)
        shot.pack(side="left", padx=(0, 6))
        words = tk.Frame(top, bg=bg)
        words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text=card.name, bg=bg, fg=INK, font=FONT_BOLD, anchor="w").pack(anchor="w")
        meta = tk.Frame(words, bg=bg)
        meta.pack(anchor="w")
        tk.Label(meta, text=card.source, bg=bg, fg=ACCENT, font=FONT_SMALL).pack(side="left")
        dot = card.dot
        tk.Label(meta, text=" ●", bg=bg, fg=dot, font=FONT_SMALL).pack(side="left")
        self._click_avatar(frame, card.agent_id, by_id)
        for sub in card.subs:
            row = tk.Frame(frame, bg=bg, cursor="hand2")
            row.pack(fill="x", padx=(28, 0), pady=1)
            tk.Label(row, text="●", bg=bg, fg=sub.dot, font=FONT_SMALL).pack(side="left")
            tk.Label(row, text=sub.name, bg=bg, fg=INK, font=FONT_SMALL).pack(side="left", padx=(4, 0))
            self._click_avatar(row, sub.agent_id, by_id)

    def _click_avatar(self, widget, agent_id: str, by_id) -> None:
        def _go(_event, agent_id=agent_id):
            agent = by_id.get(agent_id)
            if agent is None:
                agent = SimpleNamespace(agent_id=agent_id, parent_id="", project="", source="")
            focus = focus_for(agent, by_id)
            self._topic_id = focus.topic_id
            found = recipients_for(
                focus.address_id, self._parties(), self._router.routes, self._router.grok_id,
            )
            self._manual_target = found[0] if found else None
            self.refresh(force=True)

        widget.bind("<Button-1>", _go)
        for child in widget.winfo_children():
            if isinstance(child, (tk.Frame, tk.Label)):
                child.bind("<Button-1>", _go)

    def _thumb(self, parent, skin: str, bg: str):
        photo = self._photo(("thumb", skin), lambda s=skin: idle_thumbnail(s, 32))
        if photo is None:
            swatch = tk.Frame(parent, bg=LINE, width=32, height=32)
            swatch.pack_propagate(False)
            return swatch
        label = tk.Label(parent, image=photo, bg=bg)
        label.image = photo
        return label

    def _photo(self, key, factory):
        if key in self._photos:
            return self._photos[key]
        photo = None
        if tk is not None:
            try:
                image = factory()
                if image is not None:
                    from PIL import ImageTk
                    photo = ImageTk.PhotoImage(image)
            except Exception:
                photo = None
        self._photos[key] = photo
        return photo

    def _paint_to(self, parties, topic) -> None:
        if self._to_btn is None:
            return
        try:
            if not self._to_btn.winfo_exists():
                return
        except Exception:
            return
        label = self._to_label(parties, topic)
        self._to_btn.configure(text="To: " + label)

    def _to_label(self, parties, topic) -> str:
        if self._manual_target == ALL_ORCHESTRATORS:
            return "All orchestrators"
        target = self._manual_target
        if not target:
            members = topic.get("members") if isinstance(topic, dict) else []
            if not isinstance(members, list):
                members = []
            target = topic_address(
                self._topic_id, parties, members, self._router.routes, self._router.grok_id,
            )
        if not target:
            return "nobody"
        found = recipients_for(target, parties, self._router.routes, self._router.grok_id)
        agent_id = found[0] if found else target
        for party in parties:
            if party.agent_id == agent_id:
                return party.name
        if agent_id == GROK_FALLBACK_ID:
            return "Grok"
        return agent_id

    def _post_to_menu(self) -> None:
        if tk is None or self.win is None or self._to_btn is None:
            return
        menu = tk.Menu(
            self.win, tearoff=0, bg=BG, fg=INK,
            activebackground=BTN, activeforeground="white", font=FONT,
        )
        parties = self._parties()
        self._router.observe(parties)
        for party in orchestrators(parties):
            menu.add_command(
                label=f"{party.name}  {party.source}",
                command=lambda agent_id=party.agent_id: self._pick(agent_id),
            )
        menu.add_command(
            label="All orchestrators",
            command=lambda: self._pick(ALL_ORCHESTRATORS),
        )
        try:
            menu.tk_popup(
                self._to_btn.winfo_rootx(),
                self._to_btn.winfo_rooty() + self._to_btn.winfo_height(),
            )
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _pick(self, target: str) -> None:
        self._manual_target = target
        self.refresh(force=True)

    def _on_enter(self, event=None) -> None:
        """Enter or Send: a CLI target runs Daniel's prompt, otherwise it goes to the inboxes."""
        if self._room is not None and self._room.cli_target() is not None:
            self._send_cli(event)
            return
        self._send()

    def _send_cli(self, event=None) -> None:
        """Start one CLI run for the prompt Daniel typed. Called only from ``_on_enter``.

        Argv is fixed by the runner; the prompt and the room context go on stdin.
        Output comes back as text through the pane's queue and is never run.
        """
        entry = self._entry
        if entry is None or self._room is None:
            return
        try:
            raw = str(entry.get())
        except Exception:
            return
        request = self._room.prepare(raw)
        if request is None:
            return
        try:
            process = launch_cli(request, raw, event)
        except _runner().CliRejected as exc:
            self._room.rejected(request, str(exc))
            return
        try:
            entry.delete(0, "end")
        except Exception:
            pass
        self._room.started(request, process)

    def _send(self) -> None:
        """Write the entry to orchestrator inboxes. The text is not run."""
        entry = self._entry
        if entry is None:
            return
        try:
            raw = entry.get()
        except Exception:
            return
        if not str(raw).strip():
            self._set_status("Empty")
            return
        ids = self.recipient_ids()
        if not ids:
            self._set_status("No orchestrator")
            return
        room = self._topic_id or "general"
        try:
            Registry(self.directory()).chat_post(room, raw, ids)
        except EventRejected:
            self._set_status("Not sent")
            return
        try:
            entry.delete(0, "end")
        except Exception:
            return
        self._set_status("Sent")
        self.refresh(force=True)

    def _answer(self, decision_id: str, choice: str) -> None:
        """Store the letter. The option text is data, not a command."""
        try:
            answer_decision(self.directory(), decision_id, choice)
        except EventRejected as exc:
            if exc.reason == "answered":
                self._set_status("Already answered")
            elif exc.reason == "missing":
                self._set_status("Unknown decision")
            else:
                self._set_status("Not sent")
            return
        self._set_status("Answered")
        self.refresh(force=True)

    def _pin(self, decision_id: str) -> None:
        """Pin an answered card. The text is not run."""
        try:
            pin_answered(self.directory(), decision_id)
        except EventRejected as exc:
            if exc.reason == "missing":
                self._set_status("Unknown decision")
            elif exc.reason == "limit":
                self._set_status("Pin list is full")
            else:
                self._set_status("Not pinned")
            return
        self._set_status("Pinned")
        self.refresh(force=True)

    def _unpin(self, topic_id: str, pin_id: str) -> None:
        try:
            unpin_item(self.directory(), topic_id, pin_id, timeout=0.2)
        except EventRejected:
            self._set_status("Not unpinned")
            return
        self._set_status("Unpinned")
        self.refresh(force=True)

    def _set_status(self, text: str) -> None:
        label = self._status
        if label is None:
            return
        try:
            if label.winfo_exists():
                label.config(text=text)
        except Exception:
            return

    def _apply_geometry(self, win) -> None:
        if self._offscreen:
            win.geometry("960x640+20000+20000")
            return
        box = window_box_from_config(self._config())
        if box is None:
            win.geometry("1040x680+80+60")
            return
        win.geometry(f"{box.width}x{box.height}+{box.x}+{box.y}")
        self._applied = box

    def _on_configure(self, event) -> None:
        if self.win is None or event.widget is not self.win:
            return
        self._capture()

    def _capture(self) -> None:
        if self._embedded or self._offscreen or self.win is None:
            return
        try:
            if not self.win.winfo_exists():
                return
            box = WindowBox(
                int(self.win.winfo_x()),
                int(self.win.winfo_y()),
                int(self.win.winfo_width()),
                int(self.win.winfo_height()),
            )
        except Exception:
            return
        if box.width < 480 or box.height < 320:
            return
        if box == self._applied:
            return
        self._applied = box
        if self._on_box is not None:
            try:
                self._on_box(box)
            except Exception:
                return
            return
        if self._config_path is not None:
            try:
                save_window_box(self._config_path, box)
            except OSError:
                return


def _party_for_sender(sender: str, by_id: dict):
    if sender in by_id:
        return by_id[sender]
    _source, sep, ident = sender.partition(":")
    if sep and ident in by_id:
        return by_id[ident]
    return None


def _topic_sig(topics: list) -> tuple:
    rows = []
    for topic in topics:
        rows.append((
            topic.get("id"),
            topic.get("status"),
            topic.get("title"),
            topic.get("project"),
        ))
    return tuple(rows)


def write_chat_window_preview(path: Path | str | None = None) -> Path:
    """Draw the three columns from simulated rows. Nothing is read from disk."""
    from PIL import Image, ImageDraw

    from chatlog import _hex, _load_font

    target = Path(path) if path else Path(__file__).resolve().parent / "docs" / "media" / "chat-window.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    bg = _hex(BG)
    title_bg = _hex(TITLE_BG)
    card = _hex(CARD)
    ink = _hex(INK)
    meta = _hex(META)
    accent = _hex(ACCENT)
    line = _hex(LINE)
    btn = _hex(BTN)
    title_font = _load_font(18, bold=True)
    name_font = _load_font(14, bold=True)
    body = _load_font(13)
    small = _load_font(11)

    width, height = 1100, 680
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 36], fill=title_bg)
    draw.text((16, 8), "Chat", font=title_font, fill=accent)

    left, right = 280, 860
    draw.line([left, 36, left, height], fill=line, width=1)
    draw.line([right, 36, right, height], fill=line, width=1)
    draw.text((12, 48), "cli-avatars", font=name_font, fill=accent)

    def chip(x, y, text, fill, ink_rgb=(255, 255, 255)):
        tw = int(small.getlength(text)) + 10
        draw.rounded_rectangle([x, y, x + tw, y + 16], radius=3, fill=_hex(fill))
        draw.text((x + 5, y + 1), text, font=small, fill=ink_rgb)
        return tw

    def topic_card(y, title, status, status_fill, unread, decisions, selected, chip_ink=(255, 255, 255)):
        fill = _hex("#223366") if selected else card
        draw.rounded_rectangle([10, y, left - 10, y + 74], radius=4, fill=fill, outline=line)
        draw.text((18, y + 6), title, font=name_font, fill=ink)
        chip(18, y + 28, status, status_fill, chip_ink)
        draw.text((18, y + 50), f"unread {unread}   decisions {decisions}", font=small, fill=meta)
        return y + 82

    y = topic_card(76, "Hooks", "open", "#4488ff", 1, 1, True)
    y = topic_card(y, "Sprites", "waiting on you", "#ffcf4a", 0, 0, False, (20, 16, 24))
    draw.text((12, y + 4), "notes", font=name_font, fill=accent)
    topic_card(y + 28, "Quiet", "done", "#9a98b8", 0, 0, False)

    draw.text((left + 16, 48), "Hooks", font=name_font, fill=ink)
    chip(left + 80, 50, "open", "#4488ff")
    draw.text((left + 16, 76), "Meet on the same window.", font=body, fill=ink)
    draw.rounded_rectangle([left + 16, 100, left + 92, 118], radius=3, fill=btn)
    draw.text((left + 24, 102), "Hide pins", font=small, fill=(255, 255, 255))
    draw.text((left + 16, 126), "fact  Perch is clear.", font=small, fill=ink)

    def message(y, clock, name, source, note, skin):
        thumb = idle_thumbnail(skin, 28)
        if thumb is not None:
            image.paste(thumb, (left + 70, y), thumb)
        draw.text((left + 16, y + 6), clock, font=small, fill=meta)
        draw.text((left + 104, y), name, font=name_font, fill=ink)
        draw.text((left + 104, y + 18), source, font=small, fill=accent)
        icon = talk_icon("speech", 16)
        if icon is not None:
            image.paste(icon, (left + 230, y + 4), icon)
        draw.text((left + 252, y + 4), note, font=body, fill=ink)

    message(160, "12:01", "Claude-west", "Claude", "Walk to the middle.", "caine")
    message(200, "12:02", "You", "You", "Use the same window.", "caine")

    card_top = 250
    draw.rounded_rectangle(
        [left + 16, card_top, right - 16, card_top + 132], radius=4, fill=card, outline=line,
    )
    draw.text((left + 28, card_top + 8), "Claude-west", font=name_font, fill=ink)
    draw.text((left + 28, card_top + 30), "Same window?", font=body, fill=ink)
    draw.rounded_rectangle([left + 28, card_top + 56, left + 180, card_top + 80], radius=3, fill=btn)
    draw.text((left + 36, card_top + 60), "a  Same window", font=small, fill=(255, 255, 255))
    draw.rounded_rectangle([left + 28, card_top + 88, left + 196, card_top + 112], radius=3, fill=btn)
    draw.text((left + 36, card_top + 92), "b  Drop to the floor", font=small, fill=(255, 255, 255))

    draw.rounded_rectangle(
        [left + 16, 396, right - 16, 460], radius=4, fill=_hex("#12121f"), outline=line,
    )
    draw.text((left + 28, 404), "Answered a  Same window", font=body, fill=meta)
    draw.rounded_rectangle([left + 28, 426, left + 72, 448], radius=3, fill=btn)
    draw.text((left + 38, 430), "Pin", font=small, fill=(255, 255, 255))

    draw.rectangle([left + 12, height - 78, right - 12, height - 14], fill=_hex("#12121f"))
    draw.rounded_rectangle([left + 20, height - 70, left + 150, height - 46], radius=3, fill=btn)
    draw.text((left + 28, height - 66), "To: Claude-west", font=small, fill=(255, 255, 255))
    draw.rectangle([left + 20, height - 40, right - 90, height - 18], fill=bg)
    draw.rounded_rectangle([right - 82, height - 42, right - 24, height - 18], radius=3, fill=btn)
    draw.text((right - 70, height - 36), "Send", font=small, fill=(255, 255, 255))

    draw.text((right + 12, 48), "Avatars", font=name_font, fill=accent)
    roster = [
        ("Claude-west", "Claude", "#4488ff", "caine", ["sub-1"]),
        ("Grok-north", "Grok", "#aa44ff", "michimaru", []),
    ]
    ry = 84
    for name, source, dot, skin, subs in roster:
        thumb = idle_thumbnail(skin, 32)
        if thumb is not None:
            image.paste(thumb, (right + 16, ry), thumb)
        draw.text((right + 56, ry), name, font=name_font, fill=ink)
        draw.text((right + 56, ry + 18), source, font=small, fill=accent)
        draw.ellipse([right + 110, ry + 22, right + 120, ry + 32], fill=_hex(dot))
        sy = ry + 40
        for sub in subs:
            draw.ellipse([right + 56, sy + 4, right + 64, sy + 12], fill=_hex("#4488ff"))
            draw.text((right + 70, sy), sub, font=small, fill=ink)
            sy += 18
        ry = sy + 16

    image.save(target, format="PNG")
    return target
