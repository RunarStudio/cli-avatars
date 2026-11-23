"""Status bar and the corner bubble icon.

The HUD window is gone. The same rows sit on the Dungeon status bar.
The bubble icon raises the Dungeon. Tray callbacks still use ``root.after``.
"""

import logging
import time
import tkinter as tk

from bundle_paths import asset_path
from cli_avatars.app.throttle import StoreThrottle
from cli_avatars.desktop.capabilities import HAS_PIL
from decisions import decisions_caption, open_count
from events import EventRejected
from hud import hud_status_lines, status_row_style

if HAS_PIL:
    try:
        from PIL import Image, ImageTk
    except ImportError:
        HAS_PIL = False


def _hud_status_text(agents) -> tuple[list[tuple[str,str]], bool]:
    """Return (rows, no_sessions) for the HUD status panel.

    One row per source that has sessions, plus a total that includes
    subagents from every source. The talks row is a separate label.
    """
    lines = hud_status_lines(agents)
    waiting = bool(lines) and lines[0].strip().startswith("Waiting")
    return [status_row_style(line, waiting=waiting) for line in lines], waiting


def _load_bubble_icon(self):
    img_path = asset_path("Sprites", "bubble.png")
    if not HAS_PIL or not img_path.exists() or getattr(self, "canvas", None) is None:
        return
    try:
        sheet = Image.open(str(img_path)).convert("RGBA")
        frame = sheet.crop((48, 0, 96, 48))   # row 0 col 1 — idle neutral
        frame = frame.resize((72, 72), Image.NEAREST)
        self._bubble_icon_photo = ImageTk.PhotoImage(frame)
        self._bubble_icon_id = self.canvas.create_image(
            36, 36, image=self._bubble_icon_photo, anchor="center",
            tags="bubble_icon"
        )
        self.canvas.tag_bind("bubble_icon", "<Button-1>",
                             lambda e: self._show_hud_win())
        self.canvas.tag_bind("bubble_icon", "<Enter>",
                             lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.tag_bind("bubble_icon", "<Leave>",
                             lambda e: self.canvas.config(cursor=""))
    except Exception as e:
        print(f"[overlay] bubble icon load failed: {e}")


def _bring_all_to_front(self):
    """Raise the Dungeon. A popped-out chat comes up with it."""
    dungeon = getattr(self, "dungeon", None)
    if dungeon is not None:
        dungeon.raise_window()
        pop = getattr(dungeon, "_pop", None)
        if pop is not None:
            try:
                if pop.winfo_exists():
                    pop.deiconify()
                    pop.lift()
            except tk.TclError:
                pass
        return


def _show_hud_win(self):
    """The bubble icon and the tray both raise the Dungeon."""
    dungeon = getattr(self, "dungeon", None)
    if dungeon is not None:
        dungeon.raise_window()
        return
    parent = getattr(self, "_status_parent", None)
    if parent is None:
        return
    try:
        parent.winfo_toplevel().deiconify()
        parent.winfo_toplevel().lift()
    except tk.TclError:
        return


def _create_hud_win(self):
    """Status rows in the Dungeon status bar. There is no HUD window."""
    parent = getattr(self, "_status_parent", None)
    if parent is None:
        return
    box = getattr(self, "_hud_status_box", None)
    try:
        if box is not None and box.winfo_exists():
            return
    except tk.TclError:
        pass
    bg = "#111018"
    font = ("Courier", 10)
    self._hud_win = parent
    self._hud_status_box = tk.Frame(parent, bg=bg)
    self._hud_status_box.pack(side="left", fill="x", expand=True)
    self._hud_status_lbl = self._hud_status_box
    self._hud_status_labels = []
    self._hud_status_font = font
    self._hud_status_bg = bg
    talk0 = self.scanner.bubbles.talks_at(time.time())
    self._hud_talks_lbl = tk.Label(
        parent, text="  " + talk0.text, bg=bg, fg=talk0.color,
        font=font, anchor="w",
    )
    self._hud_talks_lbl.pack(side="left", padx=(4, 8))
    self._hud_decisions_lbl = tk.Label(
        parent, text="  " + decisions_caption(0), bg=bg, fg="#aaaaaa",
        font=font, anchor="w",
    )
    self._hud_decisions_lbl.pack(side="left", padx=(0, 8))


def _paint_hud_rows(self, rows):
    """One label per status line. Grok uses its own color and mark."""
    box = getattr(self, "_hud_status_box", None)
    if box is None:
        return
    try:
        if not box.winfo_exists():
            return
    except Exception:
        return
    labels = getattr(self, "_hud_status_labels", None)
    if labels is None:
        labels = []
        self._hud_status_labels = labels
    font = getattr(self, "_hud_status_font", ("Courier", 10))
    bg = getattr(self, "_hud_status_bg", "#0d0d1a")
    while len(labels) < len(rows):
        lbl = tk.Label(box, text="", bg=bg, fg="#aaccff",
                       font=font, anchor="w", justify="left", padx=10)
        lbl.pack(fill="x")
        labels.append(lbl)
    for lbl, (text, color) in zip(labels, rows, strict=False):
        lbl.config(text=text, fg=color)
        if not lbl.winfo_ismapped():
            lbl.pack(fill="x")
    for lbl in labels[len(rows):]:
        lbl.pack_forget()


def _decision_count_now(self) -> int:
    """Open decisions, read at most twice a second."""

    def load() -> int:
        try:
            return open_count(self._chat_directory(), timeout=0.05)
        except EventRejected:
            return self._decision_count
        except Exception:
            logging.getLogger("cli_avatars.decisions").exception("decision count failed")
            return self._decision_count

    # Agent ids live on ``_decision_agents_read`` (a list). This cache is
    # only the open count. One throttle for both handed the caption that
    # list, and ``int(list)`` raised.
    gate = getattr(self, "_decision_count_read", None)
    if not isinstance(gate, StoreThrottle):
        gate = StoreThrottle()
        self._decision_count_read = gate
    return gate.get(load)


def _update_hud_win(self, agents):
    if not (self._hud_win and self._hud_win.winfo_exists()):
        return
    rows, _ = _hud_status_text(agents)
    self._paint_hud_rows(rows)
    talks = getattr(self, "_hud_talks_lbl", None)
    if talks is not None and talks.winfo_exists():
        talk = self.scanner.bubbles.talks_at(time.time())
        talks.config(text="  " + talk.text, fg=talk.color)
    decisions = getattr(self, "_hud_decisions_lbl", None)
    if decisions is not None and decisions.winfo_exists():
        count = _decision_count_now(self)
        self._decision_count = count
        decisions.config(
            text="  " + decisions_caption(count),
            fg="#ffffff" if count else "#aaaaaa",
        )


class HudWindow:
    """HUD ``Toplevel``, the bubble icon, and the status rows."""

    def __init__(self, app):
        self.app = app

    def _load_bubble_icon(self):
        return _load_bubble_icon(self.app)

    def _bring_all_to_front(self):
        return _bring_all_to_front(self.app)

    def _show_hud_win(self):
        return _show_hud_win(self.app)

    def _create_hud_win(self):
        return _create_hud_win(self.app)

    def _paint_hud_rows(self, rows):
        return _paint_hud_rows(self.app, rows)

    def _update_hud_win(self, agents):
        return _update_hud_win(self.app, agents)

    def refresh(self, frame: object) -> None:
        agents = frame.agents
        if isinstance(agents, dict):
            agents = {
                key: agent for key, agent in agents.items() if getattr(agent, "source", "") != "bot"
            }
        return _update_hud_win(self.app, agents)
