"""PHONE.2 / WEB.4: what the phone may change, behind ``web.allow_writes``. No Tk.

Open or end a session (START.1), start a task chat (TASK-CHAT.1), send a prompt to a room's chat,
answer a decision (DECIDE.1), move a card (TASKBACK.5: Daniel's move through the registry, one ``moved`` event),
and capture a thought as a card or a task chat (QUICK-CAPTURE).
The phone's Send tap is the user's Enter: the run goes through the Dungeon chat's own launch
(``chat_window.launch_cli``), with the room's folder and the binary the user confirmed there. The
phone never names a folder, a binary, a mode or a CLI flag; a room without a folder picked in the
Dungeon is refused.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from cli_avatars.app import room_log, task_sessions
from cli_avatars.app import session_rooms as sr
from cli_avatars.app import session_walks as sw
from cli_avatars.model.room import PARTICIPANTS, ROOM_DIR_NAME, add_participant, load_binary_pin, load_room
from events import EventRejected
from registry import task_chats
from registry.facade import Registry
from rooms import project_folder
from topics import get_topic, valid_topic_id
from webui import media

MAX_PROMPT = 8000
MAX_ANSWER = 1000
MAX_FOLDERS = 50
NO_FOLDER = "Pick this room's folder once in the Dungeon's chat (Folder…), then send from the phone."
NO_BINARY = "Confirm the Claude binary once in the Dungeon's chat, then send from the phone."


class Actions:
    """The phone's writes on one data folder. The app passes its Places book and a Tk-thread caller."""

    def __init__(self, directory: Path | str, book=None, model=None, call=None, after_change=None) -> None:
        self.directory = Path(directory)
        self._book = book or (lambda: None)
        self._model = model or (lambda: sr.SessionRooms(self.directory / "ui" / "session_rooms.json"))
        self._call = call or (lambda fn: fn())
        self._after_change = after_change or (lambda: None)
        self._lock = threading.Lock()
        self.running: set[str] = set()

    def state(self) -> dict:
        """Open sessions and the rooms the phone may open (a folder was picked in the Dungeon). Names only."""
        try:
            sessions = self._call(lambda: [{"sid": s.sid, "kind": s.kind, "cli": s.cli}
                                           for s in self._model().sessions if not s.closing])
        except Exception:
            sessions = []
        return {"sessions": sessions, "folders": folders(self.directory)}

    def open_session(self, kind: object, cli: object, topic: object) -> str:
        """``""`` when the room is placed, else why not. Starts no CLI."""
        if kind not in sr.KINDS or cli not in sr.CLIS or not isinstance(topic, str) or not valid_topic_id(topic):
            return "Pick simple or main, Claude or Grok, and one of your rooms."
        if not _room(self.directory, topic).working_dir:
            return NO_FOLDER

        def run() -> str:
            error = sw.open_session(self._book(), self._model(), kind, cli, topic, time.time())
            if not error:
                try:
                    add_participant(self.directory, topic, cli)
                except (EventRejected, OSError):
                    pass
                self._after_change()
            return error

        try:
            return self._call(run)
        except Exception:
            return "The Dungeon did not answer. Try again."

    def end_session(self, sid: object) -> bool:
        if not isinstance(sid, str) or not valid_topic_id(sid):
            return False

        def run() -> bool:
            done = sw.end_session(self._book(), self._model(), sid, time.time())
            if done:
                self._after_change()
            return done

        try:
            return bool(self._call(run))
        except Exception:
            return False

    def rooms(self, op: str, *args, **fields) -> tuple[str, str]:
        """PHONE.3: ``add``, ``edit`` or ``delete`` a room in the shared model: ``(why not, room id)``."""

        def run() -> tuple[str, str]:
            model = self._model()
            why = {"add": model.add_room, "edit": model.edit_room, "delete": model.delete_room}[op](*args, **fields)
            if why:
                return why, ""
            self._after_change()
            return "", model.rooms[-1].rid if op == "add" else str(args[0])

        try:
            return self._call(run)
        except Exception:
            return "The Dungeon did not answer. Try again.", ""

    def room_state(self) -> dict:
        """Rooms with what may change, the points to connect to, and the 30 skins."""
        from cli_avatars.app.room_skins import SKINS

        try:
            state = self._call(lambda: {"rooms": self._model().catalog(), "points": self._model().points()})
        except Exception:
            state = {"rooms": [], "points": []}
        state["skins"] = [{"id": k.id, "name": k.name, "light": k.light} for k in SKINS.values()]
        return state

    def plan_room(self, size: str, at: str, point: str) -> str:
        try:
            return self._call(lambda: self._model().plan_room(size, at, point))
        except Exception:
            return "The Dungeon did not answer. Try again."

    def task_chat(self, card_id: str, cli: str) -> tuple[str, str]:
        """``(room, "")`` for a new chat on the card, else ``("", why)``; ``why`` is ``missing`` for no card.

        Starts no CLI: the first Send in that room does.
        """
        ready, why = task_chats.cli_ready(cli)
        if not ready:
            return "", why
        registry = Registry(self.directory)
        if registry.task_get(card_id) is None:
            return "", "missing"
        try:
            _card, chat = task_chats.start_chat(registry, card_id, cli)
        except (EventRejected, OSError):
            return "", f"Not started: up to {task_chats.MAX_CHATS} chats per task."
        self._after_change()
        return chat["room"], ""

    def move(self, card_id: str, column: str) -> tuple[dict | None, str]:
        """``(card, "")`` after Daniel's move from the phone; ``(None, why)``, ``why`` is ``missing`` for no card."""
        try:
            card = Registry(self.directory).task_move(card_id, column)
        except EventRejected as exc:
            return None, "missing" if exc.reason == "missing" else exc.reason
        except OSError:
            return None, "io"
        self._after_change()
        return card, ""

    def capture(self, text: str, topic: str, chat: bool) -> tuple[dict | None, str | None, str]:
        """``(card, room, "")`` for a captured thought; ``(None, None, why)``: ``empty``, ``missing`` or ``schema``."""
        from registry import capture

        try:
            card, room = capture.capture(self.directory, text, topic, chat)
        except EventRejected as exc:
            return None, None, exc.reason
        except OSError:
            return None, None, "io"
        self._after_change()
        return card, room, ""

    def decide(self, decision_id: str, choice: str | None, text: str | None) -> tuple[str, str, bool]:
        """``(room, why, sent)``: Daniel's answer from the phone. ``why`` is ``missing``, ``schema`` or a sentence.

        A decision a task chat asked also runs as that chat's next turn (the tap is his Enter).
        """
        from decisions import list_decisions
        from events import UUID_RE
        from registry.task_decisions import said

        if UUID_RE.fullmatch(decision_id) is None:
            return "", "missing", False
        row = next((r for r in list_decisions(self.directory) if r["id"] == decision_id), None)
        if row is None:
            return "", "missing", False
        try:
            Registry(self.directory).decision_answer(decision_id, choice, text)
        except EventRejected as exc:
            return "", {"answered": "Already answered.", "missing": "missing"}.get(exc.reason, "schema"), False
        except OSError:
            return "", "Not stored.", False
        self._after_change()
        room = row["room"]
        chat = task_chats.chat_for(task_chats.task_for(self.directory, room), room)
        if chat is None or task_chats.chat_agent(chat) != row["from"]:
            return room, "", False
        answered = next(r for r in list_decisions(self.directory) if r["id"] == decision_id)
        return room, "", not self.send(room, f'Daniel answered your question "{row["question"]}": {said(answered)}')

    def send(self, topic: str, text: str) -> str:
        """Start one run for the phone's Send tap; ``""`` when it started, else why not."""
        from chat_window import launch_cli, room_tools

        room = _room(self.directory, topic)
        if hasattr(room, "room_id"):
            room = task_chats.with_folder(self.directory, room)
        cli = self._cli(topic, room)
        if not room.working_dir:
            return NO_FOLDER
        pin = load_binary_pin(self.directory, cli)
        if pin is None:
            return NO_BINARY
        with self._lock:
            if topic in self.running:
                return "Still answering here. Wait for the reply."
            self.running.add(topic)
        title, cards = room_log.context(self.directory, topic)
        turn = room_log.new_turn(cli)
        before = media.snapshot(room.working_dir)
        try:
            room_log.post_prompt(self.directory, topic, cli, text)
        except (EventRejected, OSError):
            self.running.discard(topic)
            return "Not stored."

        texts: list[str] = []

        def on_line(line: str) -> None:
            messages = turn.feed(line)
            texts.extend(m.text for m in messages if m.icon == "speech")
            if messages:
                try:
                    room_log.post_messages(self.directory, topic, cli, messages)
                except (EventRejected, OSError):
                    pass

        def on_done(result) -> None:
            try:
                media.collect(self.directory, topic, room.working_dir, before, room_log.cli_sender(cli))
                room_log.finish_turn(self.directory, room, cli, turn, result.outcome, result.stderr)
                task_chats.apply_reply(self.directory, topic, texts, result.outcome)
            except (EventRejected, OSError):
                pass
            finally:
                self.running.discard(topic)

        session = task_sessions.session(self.directory, topic, cli)
        request = SimpleNamespace(room_id=topic, cli=cli, pin=pin, working_dir=room.working_dir,
                                  mode=room.permission_mode, session_id=session, topic_title=title,
                                  open_cards=cards, on_line=on_line, on_done=on_done,
                                  preamble=task_chats.preamble(self.directory, topic, fresh=session is None))
        try:
            launch_cli(request, text, "phone-send")
        except room_tools().rejected as exc:
            self.running.discard(topic)
            _note(self.directory, topic, cli, f"Not started: {exc}")
            return f"Not started: {exc}"
        return ""

    def _cli(self, topic: str, room) -> str:
        session = next((s for s in self._model().sessions if s.sid == topic and not s.closing), None)
        if session is not None:
            return session.cli
        return next((c for c in room.participants if c in PARTICIPANTS), "claude")


def folders(directory: Path | str) -> list[dict]:
    """Rooms whose folder was picked in the Dungeon: topic, title, folder name. Never the path."""
    root = Path(directory) / ROOM_DIR_NAME
    if root.is_symlink() or not root.is_dir():
        return []
    found = []
    for path in sorted(root.glob("*.json"))[:500]:
        topic = path.stem
        if path.name.startswith(".") or not valid_topic_id(topic):
            continue
        room = _room(directory, topic)
        if room.working_dir:
            found.append({"topic": topic, "title": _title(directory, topic),
                          "folder": project_folder(room.working_dir)})
        if len(found) >= MAX_FOLDERS:
            break
    return found


def _room(directory: Path, topic: str):
    try:
        return load_room(directory, topic)
    except (EventRejected, OSError):
        return SimpleNamespace(working_dir="", participants=())


def _title(directory: Path | str, topic: str) -> str:
    try:
        return str((get_topic(directory, topic) or {}).get("title") or topic)
    except EventRejected:
        return topic


def _note(directory: Path, topic: str, cli: str, text: str) -> None:
    from events import append_channel

    try:
        append_channel(directory, {"ts": time.time(), "from": room_log.cli_sender(cli), "to": "user",
                                   "channel": topic, "icon": "error", "note": text, "kind": "msg"})
    except (EventRejected, OSError):
        pass


class TkCalls:
    """Runs a phone write on the Tk thread: the server thread queues it, an ``after()`` loop runs it."""

    def __init__(self, root, every_ms: int = 50) -> None:
        self.root, self.every_ms = root, every_ms
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._job = None
        if root is not None:
            self._pump()

    def __call__(self, fn, timeout: float = 5.0):
        if self.root is None or threading.current_thread() is threading.main_thread():
            return fn()
        box: list = []
        done = threading.Event()
        self._queue.put((fn, box, done))
        if not done.wait(timeout):
            raise TimeoutError("the Dungeon did not answer")
        if isinstance(box[0], BaseException):
            raise box[0]
        return box[0]

    def _pump(self) -> None:
        while True:
            try:
                fn, box, done = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                box.append(fn())
            except Exception as exc:
                box.append(exc)
            done.set()
        try:
            self._job = self.root.after(self.every_ms, self._pump)
        except Exception:
            self._job = None

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
        self._job = None
