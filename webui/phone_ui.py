"""Settings, Phone tab (WEB.3): serve the phone view, pick the interface, show the pairing link and QR code.

Starting it here is Daniel's click; ``start_from_config`` restarts it with the app when he left it on.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace

from events import app_data_dir
from webui import auth, config, qr, server

_BG, _FG, _SEL, _DIM, _BAD = "#0d0d1a", "#aaccff", "#223366", "#9a98b8", "#ff8866"
_FONT = ("Courier", 9)


def _settings(app) -> config.WebSettings:
    return config.web_settings(getattr(app, "config", {}) or {})


def start(app, settings: config.WebSettings) -> str:
    """Serve on the chosen address; ``""`` when it runs, else why not."""
    stop(app)
    try:
        app._phone_server, _thread = server.start(app_data_dir(), settings.bind, settings.port)
    except (OSError, ValueError) as exc:
        return f"Could not serve on {settings.bind}:{settings.port}: {exc}"
    return ""


def stop(app) -> None:
    server.stop(getattr(app, "_phone_server", None))
    app._phone_server = None


def start_from_config(app) -> None:
    settings = _settings(app)
    if settings.enabled and start(app, settings):
        print("[phone] the phone view did not start")


def _qr_image(link: str, master, scale: int = 3):
    from PIL import Image, ImageTk

    m = qr.encode(link)
    n = len(m) + 8
    image = Image.new("L", (n, n), 255)
    image.putdata([0 if 4 <= y < n - 4 and 4 <= x < n - 4 and m[y - 4][x - 4] else 255
                   for y in range(n) for x in range(n)])
    return ImageTk.PhotoImage(image.resize((n * scale, n * scale), Image.NEAREST), master=master)


def build_phone_settings(app, parent) -> None:
    current = _settings(app)
    rows = config.interfaces()
    labels = [label for label, _ip in rows]
    chosen = next((label for label, ip in rows if ip == current.bind), labels[0])
    v_on = tk.BooleanVar(parent, current.enabled and getattr(app, "_phone_server", None) is not None)
    v_if = tk.StringVar(parent, chosen)
    v_addr = tk.StringVar(parent, current.address)

    def line(text, fg=_FG):
        label = tk.Label(parent, text=text, bg=_BG, fg=fg, font=_FONT, anchor="w", justify="left", wraplength=440)
        label.pack(fill="x", padx=12, pady=2)
        return label

    line("Phone view: the Dungeon map, tasks and room chat in a browser. Read-only.", _DIM)
    head = tk.Frame(parent, bg=_BG)
    head.pack(fill="x", padx=12, pady=4)
    tk.Checkbutton(head, variable=v_on, text="Serve the phone view", command=lambda: _apply(),
                   bg=_BG, fg=_FG, selectcolor=_SEL, activebackground=_BG, activeforeground="white",
                   font=_FONT, highlightthickness=0).pack(side="left")
    pick = tk.Frame(parent, bg=_BG)
    pick.pack(fill="x", padx=12, pady=2)
    tk.Label(pick, text="Listen on", bg=_BG, fg=_FG, font=_FONT, width=12, anchor="w").pack(side="left")
    menu = tk.OptionMenu(pick, v_if, *labels, command=lambda _v: _apply())
    menu.configure(bg=_SEL, fg=_FG, activebackground="#334477", font=_FONT, highlightthickness=0, relief="flat")
    menu.pack(side="left")
    addr = tk.Frame(parent, bg=_BG)
    addr.pack(fill="x", padx=12, pady=2)
    tk.Label(addr, text="Phone address", bg=_BG, fg=_FG, font=_FONT, width=12, anchor="w").pack(side="left")
    entry = tk.Entry(addr, textvariable=v_addr, bg=_SEL, fg=_FG, insertbackground=_FG, font=_FONT, width=38,
                     relief="flat")
    entry.pack(side="left")
    entry.bind("<Return>", lambda _e: _apply())
    entry.bind("<FocusOut>", lambda _e: _apply())
    line("Keep Loopback and run `tailscale serve --bg 47280`, then paste its https://...ts.net address "
         "above. Or pick the Tailscale address. Never every interface. Guide: docs/phone-view.md", _DIM)
    status = line("")
    link_box = tk.Entry(parent, bg=_BG, fg=_FG, font=_FONT, relief="flat", readonlybackground=_BG)
    link_box.pack(fill="x", padx=12)
    code = tk.Label(parent, bg=_BG)
    code.pack(padx=12, pady=6, anchor="w")
    tk.Button(parent, text="New pairing link (unpairs every phone)", command=lambda: _rotate(),
              bg=_SEL, fg=_FG, activebackground="#334477", activeforeground="white", font=_FONT,
              relief="flat", padx=10, pady=3, cursor="hand2").pack(padx=12, pady=4, anchor="w")

    def _show(settings, why=""):
        running = getattr(app, "_phone_server", None) is not None
        link = config.phone_link(settings, auth.load_token(app_data_dir())) if running else ""
        status.configure(text=why or (f"Serving on {settings.bind}:{settings.port}." if running else "Off."),
                         fg=_BAD if why else _FG)
        link_box.configure(state="normal")
        link_box.delete(0, "end")
        link_box.insert(0, link)
        link_box.configure(state="readonly")
        code._photo = _qr_image(link, code) if link else None
        code.configure(image=code._photo or "")

    def _apply():
        bind = dict((label, ip) for label, ip in rows).get(v_if.get(), config.LOOPBACK)
        settings = config.web_settings({"web": {**_settings(app).__dict__, "enabled": bool(v_on.get()),
                                                "bind": bind, "address": v_addr.get()}}, rows)
        why = start(app, settings) if settings.enabled else stop(app) or ""
        if why:
            v_on.set(False)
            settings = replace(settings, enabled=False)
        app.config = {**(getattr(app, "config", {}) or {}), "web": {**settings.__dict__}}
        path = getattr(app, "_config_path", None)
        if path is not None:
            config.save_web(path, settings)
        _show(settings, why)

    def _rotate():
        auth.rotate_token(app_data_dir())
        _show(_settings(app))

    _show(current)
