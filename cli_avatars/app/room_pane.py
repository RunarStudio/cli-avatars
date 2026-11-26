"""Room chat pane in the chat dock (ROOM-CHAT.4/.7): target picker, folder, mode, transcript, Stop.

CHAT-CTX.1: Inbox, Claude, Grok or Cursor (``cli_chips``), one session per task and CLI (``task_sessions``).
GROK-CHAT: while Grok is lit, the Grok topics strip (``grok_list``) lists every Grok conversation to switch to.

The pane never starts a process. ``ChatWindow``'s Enter or Send handler asks
``prepare`` for the room's settings and starts the CLI itself; ``tools`` holds
only the runner's non-launching checks. Runner callbacks arrive on runner
threads and go through a queue that a Tk ``after()`` loop drains, so no Tk
call happens off the Tk thread. Output is shown as text and never run.
A pin over the transcript shows the room's task summary (TASK-SUMMARY); a turn that changes it plays a cue.
"""

from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog
from types import SimpleNamespace

import text_fonts as fonts
from board.model import CHAT_CLIS
from cli_avatars.app import cli_chips, cues, grok_topics, pack_pane, room_log, task_sessions, tiers
from cli_avatars.app.chat_clis import COLORS, NAMES, launch, short_path, state, template
from cli_avatars.app.grok_list import GrokList
from cli_avatars.model.room import (
    PERMISSION_MODES,
    Room,
    load_binary_pin,
    load_room,
    save_binary_pin,
    set_permission_mode,
    set_working_dir,
)
from events import EventRejected
from registry import task_chats
from rooms import project_folder

BG = "#0d0d1a"
TERM_BG = "#08080f"
INK = "#e8e6f4"
META = "#9a98b8"
ACCENT = "#88aaff"
OK_INK = "#7fd18b"
ERR_INK = "#ff7a7a"
BTN = "#334477"
BTN_ON = "#5577cc"
FONT = fonts.face(10)
FONT_SMALL = fonts.face(8)
PIN_BG = "#1a1426"
PIN_EDGE = "#7a1f3d"
PIN_GOLD = "#ffcf4a"
INBOX = "inbox"
DRAIN_MS = 40


@dataclass
class _Run:
    room: Room
    cli: str
    turn: object
    process: object = None
    events: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)
    texts: list = field(default_factory=list)


class RoomPane:
    """One per ``ChatWindow``. Widgets are rebuilt by ``mount``; runs survive a re-mount."""

    def __init__(self, window, tools) -> None:
        self.window = window
        self.tools = tools
        self.room_id = ""
        self.target = INBOX
        self._runs: dict[str, _Run] = {}
        self._draining = False
        self._resolved = None
        self.chips: dict = {}
        self._states: dict = {}
        self._term = None
        self._thread_wrap = None
        self._composer = None
        self._folder_btn = None
        self._mode_btn = None
        self._stop_btn = None
        self._new_btn = None
        self._bin_row = None
        self._bin_label = None
        self._bin_btn = None
        self._bin_before = None
        self._pin_box = None
        self._pin_title = None
        self._pin_age = None
        self._pin_text = None
        self._pin_next = 0.0
        self.grok = None

    def mount(self, center, thread_wrap, composer, before) -> None:
        """Build the picker row above ``before`` and the transcript beside the thread."""
        self._thread_wrap = thread_wrap
        self._composer = composer
        bar = tk.Frame(composer, bg=BG)
        bar.pack(fill="x", pady=(6, 0), before=before)
        tk.Label(bar, text="Run:", bg=BG, fg=META, font=FONT_SMALL).pack(side="left", padx=(0, 4))
        self.chips = cli_chips.build(bar, self.pick_target)
        # Own row: the docked chat is too narrow for targets and session controls on one line.
        controls = tk.Frame(composer, bg=BG)
        controls.pack(fill="x", pady=(2, 0), before=before)
        self._stop_btn = self._small(controls, "Stop", self.stop)
        self._new_btn = self._small(controls, "New session", self.new_session)
        self._mode_btn = self._small(controls, "plan", self.toggle_mode)
        self._folder_btn = self._small(controls, "Folder…", self.pick_folder)
        self._ask_btn = self._small(controls, "Ask a bot…", self.ask_bot)
        self._small(self.window._to_btn.master, "Copy context", self.copy_context)  # beside To:, the roomy row
        self._bin_row = tk.Frame(composer, bg=BG)
        self._bin_label = tk.Label(self._bin_row, text="", bg=BG, fg=META, font=FONT_SMALL, anchor="w")
        self._bin_label.pack(side="left", fill="x", expand=True)
        self._bin_btn = tk.Button(
            self._bin_row, text="Use this binary", command=self.confirm_binary, font=FONT_SMALL,
            bg=BTN, fg=fonts.OFF_WHITE, relief="flat", padx=6, pady=1,
        )
        self._bin_btn.pack(side="right")
        self._bin_before = before
        term = tk.Text(
            center, height=1, bg=TERM_BG, fg=INK, insertbackground=INK, font=FONT, relief="flat", wrap="word",
            padx=10, pady=8, highlightthickness=0, state="disabled",
        )
        for tag, color in (("prompt", ACCENT), ("reply", INK), ("tool", META), ("ok", OK_INK),
                           ("error", ERR_INK), ("note", META), *((f"src-{c}", COLORS[c]) for c in CHAT_CLIS)):
            term.tag_configure(tag, foreground=color)
        self._term = term
        self.grok = GrokList(self, center)
        self._pin_box = tk.Frame(center, bg=PIN_BG, highlightthickness=1, highlightbackground=PIN_EDGE)
        band = tk.Frame(self._pin_box, bg=PIN_BG)
        band.pack(fill="x", padx=8, pady=(4, 0))
        self._pin_age = tk.Label(band, text="", bg=PIN_BG, fg=META, font=FONT_SMALL)
        self._pin_age.pack(side="right")
        self._pin_title = tk.Label(band, text="", bg=PIN_BG, fg=PIN_GOLD, font=FONT_SMALL, anchor="w")
        self._pin_title.pack(side="left", fill="x", expand=True)
        self._pin_text = tk.Label(self._pin_box, text="", bg=PIN_BG, fg=INK, font=FONT, anchor="w", justify="left",
                                  wraplength=460)
        self._pin_text.pack(fill="x", padx=8, pady=(2, 6))
        self._pin_box.bind("<Configure>", lambda e: self._pin_text.config(wraplength=max(120, e.width - 20)))
        self.refresh_clis()
        self._show()
        self._pin_refresh(force=True)

    def refresh_clis(self) -> None:
        """Which CLIs are found, confirmed or configured; searches PATH, starts nothing."""
        self._states = {cli: state(self.window.directory(), self.window._config(), cli, self.tools.resolve)
                        for cli in CHAT_CLIS}
        self._paint()

    def sync(self, topic_id: str) -> None:
        """Follow the topic the chat shows. The Claude target stays on in a room that used it."""
        topic_id = topic_id or "general"  # the room the inbox send uses when there is no topic
        if topic_id == self.room_id:
            self._pin_refresh()
            return
        self.room_id = topic_id
        room = self._room()
        if not (self.cli_target() and room is not None and room.participants):
            first = ("claude",)
            if topic_id == tiers.main_sid(self.window.directory()):
                first = (tiers.main_cli(self.window._config()), "claude")
            self.target = next((c for c in first if room is not None and c in room.participants), INBOX)
        self._show()
        self._reload()
        self._pin_refresh(force=True)

    def cli_target(self) -> str | None:
        return None if self.target == INBOX else self.target

    def pick_target(self, key: str) -> None:
        cli = self._states.get(key)
        if key != INBOX and not getattr(cli, "enabled", False):
            return self._status(cli.why) if cli is not None else None
        self.target = key
        if key != INBOX and self._pin(key) is None:
            self._resolve(key)
        self._show()
        self._reload()

    copy_context = cli_chips.copy_context

    def ask_bot(self) -> None:
        """GROK-ORCH.1: the bot picker for this chat; a task chat's ask names its card. Runs no bot."""
        from cli_avatars.app.bot_ask import open_picker

        directory = self.window.directory()
        card = task_chats.task_for(directory, self.room_id) if self.room_id else None
        open_picker(self._composer.winfo_toplevel(), directory, card=card["id"] if card else "", room=self.room_id,
                    on_sent=lambda row: self._status(f"Asked {row['bot_name']}: the answer lands here."))

    def prepare(self, prompt: str):
        """Room settings for one launch, or ``None`` with the reason in the status line.

        Runs inside the Enter or Send handler. A room with no folder opens the folder dialog first.
        """
        cli = self.cli_target()
        room = self._room()
        if cli is None or room is None:
            return None
        if not prompt.strip():
            self._status("Empty")
            return None
        if room.room_id in self._runs:
            self._status(f"{NAMES[self._runs[room.room_id].cli]} is still answering here. Stop it or wait.")
            return None
        pin = self._pin(cli)
        if pin is None:
            self._resolve(cli)
            self._show()
            self._status(f"Confirm the {NAMES[cli]} binary first.")
            return None
        argv = template(self.window._config(), cli)
        if argv is None and cli != "claude":
            self._status(self._states[cli].why if cli in self._states else "Not configured")
            return None
        if not room.working_dir:
            room = self.pick_folder()
            if room is None or not room.working_dir:
                return None
        directory = self.window.directory()
        fields = launch(directory, self.window._config(), room.room_id, cli)
        session = fields["session_id"]
        title, cards = room_log.context(directory, room.room_id)
        run = _Run(room, cli, room_log.new_turn(cli, fields["new_session_id"]))
        try:
            room_log.post_prompt(directory, room.room_id, cli, prompt)
        except (EventRejected, OSError):
            self._status("Not stored")
            return None
        self._write(f"> {prompt}\n", "prompt")
        return SimpleNamespace(
            room_id=room.room_id, cli=cli, pin=pin, working_dir=room.working_dir, mode=room.permission_mode,
            session_id=session, topic_title=title, open_cards=cards, template=argv,
            preamble=task_chats.preamble(directory, room.room_id, fresh=session is None),
            new_session_id=fields["new_session_id"], on_line=lambda line: run.events.put(("line", line)),
            on_done=lambda result: run.events.put(("done", result)),
            run=run, **tiers.launch(directory, self.window._config(), room.room_id, cli, session is None),
        )

    def started(self, request, process) -> None:
        request.run.process = process
        self._runs[request.room_id] = request.run
        fresh = " (new session with the task's pack)" if request.preamble.startswith("[cli-avatars context pack") \
            else " (new session)"
        self._write(f"… {NAMES[request.cli]} is answering{' (resumed session)' if request.session_id else fresh}\n",
                    "note")
        pack_pane.started(self.window.directory(), self.window._config(), request)
        self.grok.started(request.cli)
        self._status("Running. Output is shown, never run.")
        self._paint()
        if not self._draining:
            self._draining = True
            self._after(self._drain)

    def rejected(self, request, reason: str) -> None:
        self._write(f"! not started: {reason}\n", "error")
        self._status("Not started")

    def stop(self) -> None:
        run = self._runs.get(self.room_id)
        if run is not None and run.process is not None:
            run.process.stop()
            self._status("Stopping…")

    def new_session(self) -> None:
        room, cli = self._room(), self.cli_target()
        if room is None or cli is None or room.room_id in self._runs:
            return
        try:
            task_sessions.drop(self.window.directory(), room.room_id, cli)
        except (EventRejected, OSError):
            return
        self._write(f"— new {NAMES[cli]} session: the next prompt starts fresh, with the task's pack —\n", "note")
        self._paint()

    def toggle_mode(self) -> None:
        """Daniel's own click switches plan <-> acceptEdits. Nothing else changes the mode."""
        room = self._room()
        if room is None:
            return
        mode = PERMISSION_MODES[1] if room.permission_mode == PERMISSION_MODES[0] else PERMISSION_MODES[0]
        try:
            set_permission_mode(self.window.directory(), room.room_id, mode)
        except (EventRejected, OSError):
            return
        self._paint()

    def pick_folder(self, ask=None) -> Room | None:
        """The folder dialog (or Summon's, ``ask``) is the only way a working dir reaches the room file."""
        room = self._room()
        if room is None:
            return None
        picked = self._ask_folder() if ask is None else ask()
        if not picked:
            self._status("No folder picked")
            return None
        try:
            room = set_working_dir(self.window.directory(), room.room_id, picked, check=self.tools.validate_dir)
        except self.tools.rejected as exc:
            self._status(f"Folder refused: {exc}")
            return None
        except (EventRejected, OSError):
            self._status("Folder not stored")
            return None
        self._paint()
        self._status(f"Folder: {project_folder(room.working_dir)}")
        return room

    def confirm_binary(self) -> None:
        """Daniel's click pins the path shown, with its size and mtime."""
        resolved = self._resolved
        if resolved is None or not resolved.found:
            return
        try:
            pin = self.tools.confirm(resolved)
            save_binary_pin(self.window.directory(), resolved.cli, pin.path, pin.size, pin.mtime_ns, pin.shim)
        except self.tools.rejected as exc:
            self._status(f"Binary refused: {exc}")
            return
        except (EventRejected, OSError):
            self._status("Binary not stored")
            return
        self._resolved = None
        self.refresh_clis()
        self._show()
        self._status("Binary confirmed. Press Enter to send.")

    def _ask_folder(self) -> str:
        return filedialog.askdirectory(parent=self.window.win, mustexist=True, title="Folder for this room")

    def _drain(self) -> None:
        for room_id, run in list(self._runs.items()):
            while True:
                try:
                    kind, payload = run.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "line":
                    self._on_line(run, payload)
                else:
                    self._runs.pop(room_id, None)
                    self._on_done(run, payload)
                    break
        if self._runs:
            self._after(self._drain, DRAIN_MS)
        else:
            self._draining = False

    def _on_line(self, run: _Run, line: str) -> None:
        self._messages(run, run.turn.feed(line))

    def _messages(self, run: _Run, messages: list) -> None:
        if not messages:
            return
        directory = self.window.directory()
        try:
            room_log.post_messages(directory, run.room.room_id, run.cli, messages)
        except (EventRejected, OSError):
            pass
        run.texts.extend(m.text for m in messages if m.icon == "speech")
        if run.room.room_id != self.room_id:
            return
        for message in messages:
            tag = {"typing": "tool", "ok": "ok", "error": "error", "warn": "note"}.get(message.icon, "reply")
            self._line(run.cli, message.text, tag)

    def _on_done(self, run: _Run, result) -> None:
        self._messages(run, run.turn.finish() if hasattr(run.turn, "finish") else [])
        try:
            room_log.finish_turn(self.window.directory(), run.room, run.cli, run.turn, result.outcome, result.stderr)
        except (EventRejected, OSError):
            pass
        try:
            changed = task_chats.apply_reply(self.window.directory(), run.room.room_id, run.texts, result.outcome)
        except OSError:
            changed = []
        self._paint()
        self.grok.done(run.cli, run.room.room_id, run.texts, result.outcome)
        if "summary updated" in changed:
            cues.play(SimpleNamespace(config=self.window._config()), "arrive")
            self._pin_refresh(force=True)
        if run.room.room_id == self.room_id:
            for line in changed:
                self._write(f"  ✓ task: {line}\n", "error" if line.startswith("refused") else "ok")
            tag = "ok" if result.outcome == "ok" else "error"
            self._write(f"[{result.outcome}]\n\n", tag)
            self._status(f"Done. A follow-up to {NAMES[run.cli]} resumes its session." if run.turn.session_id
                         else "Done")

    _pin_refresh = pack_pane.pin_refresh

    def _room(self) -> Room | None:
        if not self.room_id:
            return None
        try:
            directory = self.window.directory()
            room = task_chats.with_folder(directory, load_room(directory, self.room_id))
            return grok_topics.with_folder(directory, room)
        except (EventRejected, OSError):
            return None

    def _pin(self, cli: str):
        try:
            return load_binary_pin(self.window.directory(), cli)
        except (EventRejected, OSError):
            return None

    def _resolve(self, cli: str) -> None:
        try:
            self._resolved = self.tools.resolve(cli, templated=cli != "claude")
        except self.tools.rejected:
            self._resolved = SimpleNamespace(cli=cli, path="", found=False, settings_note="")

    _reload = cli_chips.reload

    def _show(self) -> None:
        """Transcript in place of the thread while a CLI is the target; the picker shows the room's state."""
        term, wrap = self._term, self._thread_wrap
        if term is None or wrap is None:
            return
        try:
            self.grok.show(self.target == "grok", self._composer)
            if self.cli_target() is None:
                term.pack_forget()
                wrap.pack(fill="both", expand=True, before=self._composer)
            else:
                wrap.pack_forget()
                term.pack(fill="both", expand=True, before=self._composer)
            resolved = self._resolved
            if self.cli_target() is not None and self._pin(self.target) is None and resolved is not None:
                note = f"{NAMES[self.target]} CLI: " + (short_path(resolved.path) if resolved.found else "not on PATH.")
                if resolved.found and resolved.settings_note:
                    note += f"  ({resolved.settings_note})"
                self._bin_label.config(text=note)
                self._bin_btn.config(state="normal" if resolved.found else "disabled")
                self._bin_row.pack(fill="x", pady=(4, 0), before=self._bin_before)
            else:
                self._bin_row.pack_forget()
        except tk.TclError:
            return
        self._paint()

    def _paint(self) -> None:
        room = self._room()
        cli_chips.paint(self.chips, self.target, self._states,
                        tiers.room_chip(self.window.directory(), self.window._config(), self.room_id))
        try:
            cli_on = self.cli_target() is not None
            running = room is not None and room.room_id in self._runs
            self._stop_btn.config(state="normal" if running else "disabled")
            folder = project_folder(room.working_dir) if room is not None else ""
            self._folder_btn.config(text=folder or "Folder…", state="normal" if cli_on and not running else "disabled")
            self._mode_btn.config(text=room.permission_mode if room is not None else "plan",
                                  state="normal" if cli_on and not running else "disabled")
            session = task_sessions.session(self.window.directory(), room.room_id, self.target) \
                if cli_on and room is not None else None
            has_session = bool(session)
            self._new_btn.config(state="normal" if cli_on and has_session and not running else "disabled")
            self.window._to_btn.config(state="disabled" if cli_on else "normal")
        except (tk.TclError, AttributeError):
            return
        if not cli_on:
            self._status("Stored locally. Nothing here runs.")
        elif not running and room is not None:
            where = folder or "a folder you pick on first send"
            resume = "resumes this task's session" if session else "starts a session with the task's pack"
            mode = f" ({room.permission_mode})" if self.target == "claude" else ""
            self._status(f"Enter runs {NAMES[self.target]} in {where}{mode}, {resume}. Output is never run.")

    def _write(self, text: str, tag: str) -> None:
        term = self._term
        if term is None:
            return
        try:
            term.config(state="normal")
            term.insert("end", text, tag)
            term.config(state="disabled")
            term.see("end")
        except tk.TclError:
            return

    _line = cli_chips.line

    def _clear(self) -> None:
        try:
            self._term.config(state="normal")
            self._term.delete("1.0", "end")
            self._term.config(state="disabled")
        except (tk.TclError, AttributeError):
            return

    def _small(self, parent, text: str, command) -> tk.Button:
        btn = tk.Button(parent, text=text, command=command, font=FONT_SMALL, bg=BTN, fg=fonts.OFF_WHITE,
                        activebackground=BTN_ON, activeforeground="white", disabledforeground="#666688",
                        relief="flat", padx=6, pady=1)
        btn.pack(side="right", padx=1)
        return btn

    def _status(self, text: str) -> None:
        self.window._set_status(text)

    def _after(self, fn, ms: int = 0) -> None:
        try:
            self.window.master.after(ms, fn)
        except tk.TclError:
            self._draining = False
