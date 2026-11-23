"""Chat window glue: open, hide, and address an avatar.

ROOM-CHAT.4: the chat pane, the target picker, and Both mode belong in
this module. A CLI is started only from a button or Enter handler in the
chat window. Do not start one from the tick, the scanner, or a hook.

BOARD.4: the board tab lives on ``chat_window.py`` and is wired from here
(``ChatController.open`` / the window ``ChatWindow`` builds).

Message text is data. Nothing in this module executes it.
"""

from pathlib import Path

from chat_window import ChatWindow
from events import app_data_dir
from routing import config_with_window_box, focus_for, save_window_box


def _chat_directory(self) -> Path:
    source = getattr(self.scanner, "_events", None)
    data = getattr(source, "data_dir", None)
    if data:
        return Path(data)
    return app_data_dir()


def _remember_chat_box(self, box) -> None:
    self.config = config_with_window_box(self.config, box)
    try:
        save_window_box(self._config_path, box)
    except OSError:
        pass


def _ensure_chat_window(self) -> ChatWindow:
    window = getattr(self, "_chat_window", None)
    if window is not None and window.win is not None:
        try:
            if window.win.winfo_exists():
                return window
        except Exception:
            pass
    window = ChatWindow(
        self.root,
        directory=self._chat_directory,
        agents=self._rooms_records,
        config=lambda: self.config,
        config_path=self._config_path,
        on_box=self._remember_chat_box,
    )
    self._chat_window = window
    return window


def _show_chat(self, topic_id: str | None = None, address_id: str | None = None) -> None:
    """Open the chat window. Message text stays data. Nothing is executed."""
    window = self._ensure_chat_window()
    self._chat_shown = True
    window.open(topic_id=topic_id, address_id=address_id)
    self._chat_win = window.win
    self._paint_chat_button()


def _paint_chat_button(self) -> None:
    btn = getattr(self, "_chat_btn", None)
    if btn is None:
        return
    try:
        if not btn.winfo_exists():
            return
    except Exception:
        return
    if self._chat_shown:
        btn.config(bg="#334477", fg="white")
    else:
        btn.config(bg="#223366", fg="#aaccff")


def _toggle_chat(self) -> None:
    if self._chat_shown:
        self._close_chat()
        return
    self._show_chat()


def _close_chat(self) -> None:
    window = getattr(self, "_chat_window", None)
    if window is not None:
        window.hide()
    self._chat_shown = False
    self._paint_chat_button()


def _update_chat_win(self, force: bool = False) -> None:
    if not self._chat_shown:
        return
    window = getattr(self, "_chat_window", None)
    if window is None:
        return
    window.refresh(force=force)


def _open_chat_for_avatar(self, avatar) -> None:
    """One click opens that avatar's topic, addressed to its orchestrator."""
    by_id = {}
    for main in self.avatars.values():
        by_id[main.agent.agent_id] = main.agent
    for subs in self.sub_avatars.values():
        for child in subs:
            by_id[child.agent.agent_id] = child.agent
    for child in self._lingering_subs:
        by_id[child.agent.agent_id] = child.agent
    focus = focus_for(avatar.agent, by_id)
    self._show_chat(topic_id=focus.topic_id, address_id=focus.address_id)


class ChatController:
    """Show and hide the chat window. Sending stays inside ``ChatWindow``."""

    def __init__(self, app):
        self.app = app

    def _chat_directory(self):
        return _chat_directory(self.app)

    def _remember_chat_box(self, box):
        return _remember_chat_box(self.app, box)

    def _ensure_chat_window(self):
        return _ensure_chat_window(self.app)

    def _show_chat(self, topic_id=None, address_id=None):
        return _show_chat(self.app, topic_id, address_id)

    def open(self, topic_id=None, address_id=None):
        """ROOM-CHAT.4 / BOARD.4 entry. Same path as the Chat button."""
        return _show_chat(self.app, topic_id, address_id)

    def _paint_chat_button(self):
        return _paint_chat_button(self.app)

    def _toggle_chat(self):
        return _toggle_chat(self.app)

    def _close_chat(self):
        return _close_chat(self.app)

    def _update_chat_win(self, force=False):
        return _update_chat_win(self.app, force)

    def _open_chat_for_avatar(self, avatar):
        return _open_chat_for_avatar(self.app, avatar)

    def refresh(self, frame=None):
        return _update_chat_win(self.app)
