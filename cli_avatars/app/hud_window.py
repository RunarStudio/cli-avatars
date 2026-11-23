"""HUD window, status rows, and the corner bubble icon.

The window is a normal ``Toplevel`` (not topmost). Tray callbacks reach it
through ``root.after``.
"""

import logging
import time
import tkinter as tk
from tkinter import ttk

from bundle_paths import asset_path
from decisions import decisions_caption, open_count
from events import EventRejected
from hud import hud_status_lines, status_row_style

from cli_avatars.desktop.capabilities import HAS_PIL

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
    if not HAS_PIL or not img_path.exists():
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
    wins = [self._hud_win, self._picker, self._config_win]
    if self._rooms_shown:
        wins.append(self._rooms_win)
    if self._chat_shown:
        wins.append(self._chat_win)
    for win in wins:
        if win and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()


def _show_hud_win(self):
    if not (self._hud_win and self._hud_win.winfo_exists()):
        self._create_hud_win()
    else:
        self._hud_win.deiconify()
        self._hud_win.lift()
        self._hud_win.attributes("-topmost", True)
        self._hud_win.after(200, lambda: (
            self._hud_win and self._hud_win.winfo_exists() and
            self._hud_win.attributes("-topmost", False)
        ))


def _create_hud_win(self):
    BG = "#0d0d1a"; FG = "#aaccff"; SEL = "#223366"
    FONT = ("Courier", 10); BFONT = ("Courier", 11, "bold")

    win = tk.Toplevel(self.root)
    offscreen = getattr(self, "_offscreen", False)
    if offscreen:
        win.withdraw()
    win.title("AI Overlay")
    win.overrideredirect(True)
    win.attributes("-topmost", False)      # can go behind other windows
    win.configure(bg=BG)
    if offscreen:
        win.geometry("560x460+20000+20000")
    else:
        win.geometry("560x460+10+10")
    win.resizable(True, True)
    try:
        win.wm_attributes("-alpha", 0.92)
    except Exception:
        pass
    self._hud_win = win

    # Title bar (drag handle)
    title_bar = tk.Frame(win, bg="#111133", pady=6, cursor="fleur")
    title_bar.pack(fill="x")
    tk.Button(title_bar, text="x", command=lambda: win.withdraw(),
              bg="#111133", fg="#445566",
              activebackground="#330011", activeforeground="#ff6666",
              font=("Courier", 10), relief="flat", bd=0,
              padx=6, pady=0, cursor="hand2"
              ).pack(side="right", padx=(0, 4))
    tk.Label(title_bar, text="  AI Overlay v0.4", bg="#111133",
             fg="#88aaff", font=BFONT, anchor="w").pack(side="left")

    # Buttons row
    btn_row = tk.Frame(win, bg=BG, pady=3)
    btn_row.pack(fill="x", padx=8)
    tk.Button(btn_row, text="Skins", command=self._open_skin_picker,
              bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
              font=FONT, relief="flat", padx=10, pady=3, cursor="hand2"
              ).pack(side="left", padx=(0, 4))
    tk.Button(btn_row, text="Config", command=self._open_config_screen,
              bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
              font=FONT, relief="flat", padx=10, pady=3, cursor="hand2"
              ).pack(side="left", padx=(0, 4))
    self._rooms_btn = tk.Button(btn_row, text="Rooms", command=self._toggle_rooms,
              bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
              font=FONT, relief="flat", padx=10, pady=3, cursor="hand2")
    self._rooms_btn.pack(side="left", padx=(0, 4))
    self._paint_rooms_button()
    self._chat_btn = tk.Button(btn_row, text="Chat", command=self._toggle_chat,
              bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
              font=FONT, relief="flat", padx=10, pady=3, cursor="hand2")
    self._chat_btn.pack(side="left")
    self._paint_chat_button()

    tk.Frame(win, bg=SEL, height=1).pack(fill="x", padx=8, pady=(4, 0))

    # Status lines — one label each so a Grok row can use its own color.
    self._hud_status_box = tk.Frame(win, bg=BG)
    self._hud_status_box.pack(fill="x", pady=(8, 0))
    self._hud_status_lbl = self._hud_status_box
    self._hud_status_labels: list = []
    self._hud_status_font = FONT
    self._hud_status_bg = BG
    talk0 = self.scanner.bubbles.talks_at(time.time())
    self._hud_talks_lbl = tk.Label(
        win, text="  " + talk0.text, bg=BG, fg=talk0.color,
        font=FONT, anchor="w", justify="left", padx=10,
    )
    self._hud_talks_lbl.pack(fill="x", pady=(2, 0))
    self._hud_decisions_lbl = tk.Label(
        win, text="  " + decisions_caption(0), bg=BG, fg="#aaaaaa",
        font=FONT, anchor="w", justify="left", padx=10,
    )
    self._hud_decisions_lbl.pack(fill="x", pady=(0, 8))

    tk.Frame(win, height=1, bg="#223366").pack(fill="x", padx=8, pady=(4, 0))
    tk.Label(win, text="HOW TO USE", font=("Consolas", 10, "bold"),
             fg="#00ffee", bg=BG).pack(anchor="w", padx=12, pady=(6, 0))
    for line in [
        "R-click avatar  →  see bubble menu",
        "Double-click    →  focus terminal",
        "L-drag          →  throw",
        "R-click empty   →  quit",
        "Click avatar + ESC  →  close",
    ]:
        tk.Label(win, text=line, font=("Consolas", 9),
                 fg="#aaccff", bg=BG, justify="left").pack(
                     anchor="w", padx=12, pady=1)

    # Resize grip — bottom-right corner drag
    import tkinter.ttk as ttk
    grip_style = ttk.Style(win)
    grip_style.configure("Dark.TSizegrip", background=BG)
    grip = ttk.Sizegrip(win, style="Dark.TSizegrip")
    grip.pack(side="right", anchor="se")

    # Drag the window by its title bar
    def _drag_start(e):
        self._hud_drag_origin = (e.x_root - win.winfo_x(),
                                 e.y_root - win.winfo_y())
    def _drag_move(e):
        if self._hud_drag_origin:
            ox, oy = self._hud_drag_origin
            win.geometry(f"+{e.x_root - ox}+{e.y_root - oy}")
    def _drag_end(e):
        self._hud_drag_origin = None

    title_bar.bind("<ButtonPress-1>",   _drag_start)
    title_bar.bind("<B1-Motion>",       _drag_move)
    title_bar.bind("<ButtonRelease-1>", _drag_end)
    for child in title_bar.winfo_children():
        child.bind("<ButtonPress-1>",   _drag_start)
        child.bind("<B1-Motion>",       _drag_move)
        child.bind("<ButtonRelease-1>", _drag_end)

    if self._rooms_shown:
        self._open_rooms_win()


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
    for lbl, (text, color) in zip(labels, rows):
        lbl.config(text=text, fg=color)
        if not lbl.winfo_ismapped():
            lbl.pack(fill="x")
    for lbl in labels[len(rows):]:
        lbl.pack_forget()


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
        count = self._decision_count
        try:
            count = open_count(self._chat_directory(), timeout=0.05)
            self._decision_count = count
        except EventRejected:
            count = self._decision_count
        except Exception:
            logging.getLogger("cli_avatars.decisions").exception("decision count failed")
            count = self._decision_count
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

    def refresh(self, frame):
        return _update_hud_win(self.app, frame.agents)
