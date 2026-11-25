"""Room chat pane in the chat dock (ROOM-CHAT.4/.7): target picker, folder, mode, transcript, Stop.

The pane never starts a process. ``ChatWindow``'s Enter or Send handler asks
``prepare`` for the room's settings and starts the CLI itself; ``tools`` holds
only the runner's non-launching checks. Runner callbacks arrive on runner
threads and go through a queue that a Tk ``after()`` loop drains, so no Tk
call happens off the Tk thread. Output is shown as text and never run.
"""

from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog
from types import SimpleNamespace

from cli_avatars.app import room_log
from cli_avatars.model.room import (
    PERMISSION_MODES,
    Room,
    load_binary_pin,
    load_room,
    save_binary_pin,
    set_permission_mode,
    set_session_id,
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
FONT = ("Courier", 10)
FONT_SMALL = ("Courier", 8)
INBOX = "inbox"
TARGETS = (("Inbox", INBOX, True), ("Claude", "claude", True), ("Grok", "grok", False), ("Both", "both", False))
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
        self._buttons: dict[str, tk.Button] = {}
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

    def mount(self, center, thread_wrap, composer, before) -> None:
        """Build the picker row above ``before`` and the transcript beside the thread."""
        self._thread_wrap = thread_wrap
        self._composer = composer
        bar = tk.Frame(composer, bg=BG)
        bar.pack(fill="x", pady=(6, 0), before=before)
        tk.Label(bar, text="Run:", bg=BG, fg=META, font=FONT_SMALL).pack(side="left", padx=(0, 4))
        self._buttons = {}
        for label, key, enabled in TARGETS:
            btn = tk.Button(
                bar, text=label, command=lambda key=key: self.pick_target(key), font=FONT_SMALL,
                bg=BTN, fg="white", activebackground=BTN_ON, activeforeground="white",
                disabledforeground="#666688", relief="flat", padx=6, pady=1,
                state="normal" if enabled else "disabled",
            )
            btn.pack(side="left", padx=1)
            self._buttons[key] = btn
        # Own row: the docked chat is too narrow for targets and session controls on one line.
        controls = tk.Frame(composer, bg=BG)
        controls.pack(fill="x", pady=(2, 0), before=before)
        self._stop_btn = self._small(controls, "Stop", self.stop)
        self._new_btn = self._small(controls, "New session", self.new_session)
        self._mode_btn = self._small(controls, "plan", self.toggle_mode)
        self._folder_btn = self._small(controls, "Folder…", self.pick_folder)
        self._bin_row = tk.Frame(composer, bg=BG)
        self._bin_label = tk.Label(self._bin_row, text="", bg=BG, fg=META, font=FONT_SMALL, anchor="w")
        self._bin_label.pack(side="left", fill="x", expand=True)
        self._bin_btn = tk.Button(
            self._bin_row, text="Use this binary", command=self.confirm_binary, font=FONT_SMALL,
            bg=BTN, fg="white", relief="flat", padx=6, pady=1,
        )
        self._bin_btn.pack(side="right")
        self._bin_before = before
        term = tk.Text(
            center, height=1, bg=TERM_BG, fg=INK, insertbackground=INK, font=FONT, relief="flat", wrap="word",
            padx=10, pady=8, highlightthickness=0, state="disabled",
        )
        for tag, color in (("prompt", ACCENT), ("reply", INK), ("tool", META), ("ok", OK_INK),
                           ("error", ERR_INK), ("note", META)):
            term.tag_configure(tag, foreground=color)
        self._term = term
        self._show()

    def sync(self, topic_id: str) -> None:
        """Follow the topic the chat shows. The Claude target stays on in a room that used it."""
        topic_id = topic_id or "general"  # the room the inbox send uses when there is no topic
        if topic_id == self.room_id:
            return
        self.room_id = topic_id
        room = self._room()
        self.target = "claude" if room is not None and "claude" in room.participants else INBOX
        self._show()
        self._reload()

    def cli_target(self) -> str | None:
        return None if self.target == INBOX else self.target

    def pick_target(self, key: str) -> None:
        if key not in ("claude", INBOX):
            return
        self.target = key
        if key == "claude" and self._pin("claude") is None:
            self._resolve("claude")
        self._show()
        self._reload()

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
            self._status("Claude is still answering here. Stop it or wait.")
            return None
        pin = self._pin(cli)
        if pin is None:
            self._resolve(cli)
            self._show()
            self._status("Confirm the Claude binary first.")
            return None
        if not room.working_dir:
            room = self.pick_folder()
            if room is None or not room.working_dir:
                return None
        directory = self.window.directory()
        title, cards = room_log.context(directory, room.room_id)
        run = _Run(room, cli, room_log.new_turn(cli))
        try:
            room_log.post_prompt(directory, room.room_id, cli, prompt)
        except (EventRejected, OSError):
            self._status("Not stored")
            return None
        self._write(f"> {prompt}\n", "prompt")
        return SimpleNamespace(
            room_id=room.room_id, cli=cli, pin=pin, working_dir=room.working_dir, mode=room.permission_mode,
            session_id=room.session_id(cli), topic_title=title, open_cards=cards,
            preamble=task_chats.preamble(directory, room.room_id),
            on_line=lambda line: run.events.put(("line", line)),
            on_done=lambda result: run.events.put(("done", result)),
            run=run,
        )

    def started(self, request, process) -> None:
        request.run.process = process
        self._runs[request.room_id] = request.run
        resume = " (resumed session)" if request.session_id else ""
        self._write(f"… {request.cli} is answering{resume}\n", "note")
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
        room = self._room()
        if room is None or room.room_id in self._runs:
            return
        try:
            set_session_id(self.window.directory(), room.room_id, "claude", None)
        except (EventRejected, OSError):
            return
        self._write("— new session: the next prompt starts fresh —\n", "note")
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

    def pick_folder(self) -> Room | None:
        """The folder dialog is the only way a working dir reaches the room file."""
        room = self._room()
        if room is None:
            return None
        picked = self._ask_folder()
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
        messages = run.turn.feed(line)
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
            self._write(("  · " if tag == "tool" else "") + message.text + "\n", tag)

    def _on_done(self, run: _Run, result) -> None:
        try:
            room_log.finish_turn(self.window.directory(), run.room, run.cli, run.turn, result.outcome, result.stderr)
        except (EventRejected, OSError):
            pass
        try:
            changed = task_chats.apply_reply(self.window.directory(), run.room.room_id, run.texts)
        except OSError:
            changed = []
        self._paint()
        if run.room.room_id == self.room_id:
            for line in changed:
                self._write(f"  ✓ task: {line}\n", "error" if line.startswith("refused") else "ok")
            tag = "ok" if result.outcome == "ok" else "error"
            self._write(f"[{result.outcome}]\n\n", tag)
            self._status("Done. Type a follow-up: it resumes this session." if run.turn.session_id else "Done")

    def _room(self) -> Room | None:
        if not self.room_id:
            return None
        try:
            return task_chats.with_folder(self.window.directory(), load_room(self.window.directory(), self.room_id))
        except (EventRejected, OSError):
            return None

    def _pin(self, cli: str):
        try:
            return load_binary_pin(self.window.directory(), cli)
        except (EventRejected, OSError):
            return None

    def _resolve(self, cli: str) -> None:
        try:
            self._resolved = self.tools.resolve(cli)
        except self.tools.rejected:
            self._resolved = SimpleNamespace(cli=cli, path="", found=False, settings_note="")

    def _reload(self) -> None:
        term = self._term
        if term is None or self.cli_target() is None:
            return
        self._clear()
        task = task_chats.preamble(self.window.directory(), self.room_id)
        if task:
            self._write(task + "\n", "note")
        for sender, text in room_log.history(self.window.directory(), self.room_id, self.target):
            self._write(f"> {text}\n" if sender == "user" else text + "\n", "prompt" if sender == "user" else "reply")
        if self.room_id in self._runs:
            self._write("… still answering\n", "note")

    def _show(self) -> None:
        """Transcript in place of the thread while a CLI is the target; the picker shows the room's state."""
        term, wrap = self._term, self._thread_wrap
        if term is None or wrap is None:
            return
        try:
            if self.cli_target() is None:
                term.pack_forget()
                wrap.pack(fill="both", expand=True, before=self._composer)
            else:
                wrap.pack_forget()
                term.pack(fill="both", expand=True, before=self._composer)
            resolved = self._resolved
            if self.cli_target() is not None and self._pin(self.target) is None and resolved is not None:
                note = f"Claude CLI: {resolved.path}" if resolved.found else "Claude CLI not found on PATH."
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
        try:
            for key, btn in self._buttons.items():
                if str(btn.cget("state")) != "disabled":
                    btn.config(bg=BTN_ON if key == self.target else BTN)
            cli_on = self.cli_target() is not None
            running = room is not None and room.room_id in self._runs
            self._stop_btn.config(state="normal" if running else "disabled")
            folder = project_folder(room.working_dir) if room is not None else ""
            self._folder_btn.config(text=folder or "Folder…", state="normal" if cli_on and not running else "disabled")
            self._mode_btn.config(text=room.permission_mode if room is not None else "plan",
                                  state="normal" if cli_on and not running else "disabled")
            has_session = room is not None and bool(room.session_id("claude"))
            self._new_btn.config(state="normal" if cli_on and has_session and not running else "disabled")
            self.window._to_btn.config(state="disabled" if cli_on else "normal")
        except (tk.TclError, AttributeError):
            return
        if not cli_on:
            self._status("Stored locally. Nothing here runs.")
        elif not running and room is not None:
            where = folder or "a folder you pick on first send"
            resume = "resumes the session" if room.session_id("claude") else "starts a session"
            self._status(f"Enter runs Claude in {where} ({room.permission_mode}), {resume}. Output is never run.")

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

    def _clear(self) -> None:
        try:
            self._term.config(state="normal")
            self._term.delete("1.0", "end")
            self._term.config(state="disabled")
        except (tk.TclError, AttributeError):
            return

    def _small(self, parent, text: str, command) -> tk.Button:
        btn = tk.Button(parent, text=text, command=command, font=FONT_SMALL, bg=BTN, fg="white",
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
