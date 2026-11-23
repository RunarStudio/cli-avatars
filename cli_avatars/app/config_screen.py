"""Config window. Apply writes ``TUNING``. Movers read ``TUNING`` at call time."""

import tkinter as tk
from dataclasses import replace
from tkinter import ttk

from activity import bind_settings, bubble_settings
from cli_avatars.app.bots_ui import build_bots_settings
from cli_avatars.desktop.settings import desktop_settings, with_bootcheck
from cli_avatars.sprites.registry import REGISTRY
from cli_avatars.tuning import TUNING


def _open_config_screen(self):
    """Select the Settings tab. The screen is not its own window and is not topmost."""
    dungeon = getattr(self, "dungeon", None)
    if dungeon is not None:
        dungeon.show_settings()


def _build_config_ui(self, win):
    from cli_avatars.app.update_ui import mount_update_settings

    mount_update_settings(self, win)
    BG, FG, SEL = "#0d0d1a", "#aaccff", "#223366"
    FONT = ("Courier", 9)
    BFONT = ("Courier", 9, "bold")

    style = ttk.Style(win)
    style.theme_use("default")
    style.configure("Dark.TNotebook",        background=BG, borderwidth=0)
    style.configure("Dark.TNotebook.Tab",    background=SEL, foreground=FG,
                    font=FONT, padding=[8, 3])
    style.map("Dark.TNotebook.Tab",
              background=[("selected", "#334477")],
              foreground=[("selected", "white")])
    style.configure("Dark.TFrame", background=BG)

    nb = ttk.Notebook(win, style="Dark.TNotebook")
    nb.pack(fill="both", expand=True, padx=8, pady=8)

    def tab(label):
        f = ttk.Frame(nb, style="Dark.TFrame")
        nb.add(f, text=label)
        return f

    def row(parent, label, widget_fn, pady=3):
        r = tk.Frame(parent, bg=BG, pady=pady)
        r.pack(fill="x", padx=12)
        tk.Label(r, text=label, bg=BG, fg=FG, font=FONT,
                 width=18, anchor="w").pack(side="left")
        widget_fn(r)

    def slider(parent, var, lo, hi, res=0.01):
        tk.Scale(parent, variable=var, from_=lo, to=hi, resolution=res,
                 orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                 highlightthickness=0, showvalue=True, length=150,
                 font=("Courier", 7)).pack(side="left")

    def spinbox(parent, var, lo, hi, inc=1):
        tk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=inc,
                   bg=SEL, fg=FG, insertbackground=FG, font=FONT,
                   width=6, relief="flat").pack(side="left")

    # ── Tab 1: Physics ────────────────────────────────────────────
    tp = tab(" Physics ")
    tk.Label(tp, text="", bg=BG).pack(pady=4)

    v_grav  = tk.DoubleVar(win, TUNING.gravity)
    v_walk  = tk.DoubleVar(win, TUNING.walk_speed)
    v_jump  = tk.DoubleVar(win, TUNING.jump_vel)
    v_srest = tk.IntVar(win,    TUNING.spring_rest)
    v_sk    = tk.DoubleVar(win, TUNING.spring_k)
    v_sd    = tk.DoubleVar(win, TUNING.spring_damp)

    row(tp, "Gravity",        lambda p: slider(p, v_grav, 0.1, 1.5))
    row(tp, "Walk speed",     lambda p: slider(p, v_walk, 0.5, 4.0))
    row(tp, "Jump velocity",  lambda p: slider(p, v_jump, -15.0, -3.0))
    row(tp, "Spring rest px", lambda p: spinbox(p, v_srest, 20, 200, 5))
    row(tp, "Spring K",       lambda p: slider(p, v_sk, 0.01, 0.15, 0.005))
    row(tp, "Spring damping", lambda p: slider(p, v_sd, 0.80, 0.99, 0.01))

    # ── Tab 2: Display ────────────────────────────────────────────
    td = tab(" Display ")
    tk.Label(td, text="", bg=BG).pack(pady=4)

    v_scale = tk.DoubleVar(win, TUNING.avatar_scale)
    v_fps   = tk.StringVar(win, str(TUNING.overlay_fps))

    def _on_scale_cfg(val):
        TUNING.avatar_scale = round(float(val) * 2) / 2
        v_scale.set(TUNING.avatar_scale)
        if REGISTRY:
            REGISTRY.reload_all(TUNING.avatar_scale)

    def scale_widget(parent):
        tk.Scale(parent, variable=v_scale, from_=0.5, to=4.0, resolution=0.5,
                 orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                 highlightthickness=0, showvalue=True, length=150,
                 font=("Courier", 7), command=_on_scale_cfg).pack(side="left")

    def fps_widget(parent):
        om = tk.OptionMenu(parent, v_fps, "10", "20", "30", "60")
        om.config(bg=SEL, fg=FG, activebackground="#334477",
                  activeforeground="white", font=FONT,
                  highlightthickness=0, bd=0)
        om["menu"].config(bg=SEL, fg=FG, font=FONT)
        om.pack(side="left")

    row(td, "Avatar scale",  scale_widget)
    row(td, "Overlay FPS",   fps_widget)

    v_flalpha = tk.DoubleVar(win, TUNING.floor_line_alpha)
    v_walpha  = tk.DoubleVar(win, TUNING.overlay_alpha)

    def _on_floor_alpha(val):
        TUNING.floor_line_alpha = float(val)

    def _on_win_alpha(val):
        TUNING.overlay_alpha = float(val)
        self.root.wm_attributes("-alpha", TUNING.overlay_alpha)

    row(td, "Floor line opacity",
        lambda p: tk.Scale(p, variable=v_flalpha, from_=0.0, to=1.0, resolution=0.05,
                           orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                           highlightthickness=0, showvalue=True, length=150,
                           font=("Courier", 7), command=_on_floor_alpha).pack(side="left"))

    row(td, "Overlay opacity",
        lambda p: tk.Scale(p, variable=v_walpha, from_=0.1, to=1.0, resolution=0.05,
                           orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                           highlightthickness=0, showvalue=True, length=150,
                           font=("Courier", 7), command=_on_win_alpha).pack(side="left"))

    v_boot = tk.BooleanVar(win, desktop_settings(getattr(self, "config", {})).bootcheck)

    def _save_boot():
        enabled = bool(v_boot.get())
        from cli_avatars.app.bootcheck import save_bootcheck_pref

        path = getattr(self, "_config_path", None)
        if path is not None:
            save_bootcheck_pref(path, enabled)
        self.config = with_bootcheck(getattr(self, "config", {}), enabled)
        desktop = getattr(self, "desktop", None)
        if desktop is not None:
            try:
                self.desktop = replace(desktop, bootcheck=enabled)
            except TypeError:
                pass

    def boot_widget(parent):
        tk.Checkbutton(
            parent, variable=v_boot, text="on startup", command=_save_boot,
            bg=BG, fg=FG, selectcolor=SEL, activebackground=BG, activeforeground="white",
            font=FONT, highlightthickness=0,
        ).pack(side="left")

    row(td, "Boot check", boot_widget)

    current = getattr(self, "bubbles_cfg", None) or bubble_settings(getattr(self, "config", {}))
    v_act = tk.BooleanVar(win, current.activity)
    v_sub = tk.BooleanVar(win, current.subagents)
    v_dots = tk.BooleanVar(win, current.spring_dots)
    v_dur = tk.DoubleVar(win, current.duration_s)
    self._activity_var = v_act

    def _save_bubbles(*_args):
        settings = bubble_settings({"bubbles": {
            "activity": bool(v_act.get()),
            "subagents": bool(v_sub.get()),
            "spring_dots": bool(v_dots.get()),
            "duration_s": v_dur.get(),
        }})
        bind_settings(self, settings)

    def _bubble_check(parent, var, caption):
        tk.Checkbutton(
            parent, variable=var, text=caption, command=_save_bubbles,
            bg=BG, fg=FG, selectcolor=SEL, activebackground=BG, activeforeground="white",
            font=FONT, highlightthickness=0,
        ).pack(side="left")

    def _bubble_row(label, widget_fn):
        host = tk.Frame(td, bg=BG, pady=3)
        host.pack(fill="x", padx=12)
        tk.Label(host, text=label, bg=BG, fg=FG, font=FONT, width=22, anchor="w").pack(side="left")
        widget_fn(host)

    _bubble_row("Activity bubbles", lambda p: _bubble_check(p, v_act, "on"))
    _bubble_row("Show on subagents", lambda p: _bubble_check(p, v_sub, "too"))
    _bubble_row("Spring dots", lambda p: _bubble_check(p, v_dots, "on"))

    def _duration(parent):
        tk.Spinbox(
            parent, textvariable=v_dur, from_=1, to=12, increment=0.5,
            command=_save_bubbles, bg=SEL, fg=FG, insertbackground=FG,
            font=FONT, width=6, relief="flat",
        ).pack(side="left")

    _bubble_row("Bubble seconds", _duration)

    tk.Frame(td, bg="#223366", height=1).pack(fill="x", padx=12, pady=(10, 4))

    def _rescan_floors():
        self.terrain._scan()
        rescan_btn.config(text="Rescanned!", fg="#44ff88")
        win.after(1200, lambda: rescan_btn.config(text="Rescan Floors & Walls", fg=FG))

    rescan_btn = tk.Button(td, text="Rescan Floors & Walls", command=_rescan_floors,
        bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
        font=FONT, relief="flat", padx=10, pady=4, cursor="hand2")
    rescan_btn.pack(pady=6)

    tbots = tab(" Bots ")
    build_bots_settings(self, tbots)

    # ── Tab 3: Behavior ───────────────────────────────────────────
    tb = tab(" Behavior ")
    tk.Label(tb, text="", bg=BG).pack(pady=4)

    v_sscan  = tk.DoubleVar(win, TUNING.session_scan_rate)
    v_wscan  = tk.DoubleVar(win, TUNING.window_scan_rate)
    v_tsub   = tk.IntVar(win,   TUNING.test_subagents)
    v_idlelo = tk.IntVar(win,   30)
    v_idlehi = tk.IntVar(win,   90)

    row(tb, "Session scan s", lambda p: slider(p, v_sscan, 0.5, 10.0, 0.5))
    row(tb, "Window scan s",  lambda p: slider(p, v_wscan, 0.1, 2.0,  0.1))
    row(tb, "Test subagents", lambda p: spinbox(p, v_tsub, 0, 8))
    row(tb, "Idle min frames",lambda p: spinbox(p, v_idlelo, 5, 200, 5))
    row(tb, "Idle max frames",lambda p: spinbox(p, v_idlehi, 5, 200, 5))

    # ── Apply button ──────────────────────────────────────────────
    tk.Frame(win, bg="#223366", height=1).pack(fill="x", padx=10, pady=4)

    def _apply_all():
        TUNING.gravity = v_grav.get()
        TUNING.walk_speed = v_walk.get()
        TUNING.jump_vel = v_jump.get()
        TUNING.spring_rest = v_srest.get()
        TUNING.spring_k = v_sk.get()
        TUNING.spring_damp = v_sd.get()
        TUNING.overlay_fps = int(v_fps.get())
        TUNING.session_scan_rate = v_sscan.get()
        TUNING.window_scan_rate = v_wscan.get()
        TUNING.test_subagents = v_tsub.get()
        apply_btn.config(text="✓ Applied!", fg="#44ff88")
        win.after(1200, lambda: apply_btn.config(text="Apply", fg=FG))

    apply_btn = tk.Button(win, text="Apply", command=_apply_all,
        bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
        font=BFONT, relief="flat", padx=14, pady=5, cursor="hand2")
    apply_btn.pack(pady=6)


class ConfigScreen:
    def __init__(self, app):
        self.app = app

    def _open_config_screen(self):
        return _open_config_screen(self.app)

    def _build_config_ui(self, win):
        return _build_config_ui(self.app, win)
