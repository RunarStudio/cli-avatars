"""Settings, Phone tab (WEB.3): serve the phone view, pick the interface, show the pairing link and QR code.

Starting it here is Daniel's click; ``start_from_config`` restarts it with the app when he left it on.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace

import text_fonts as fonts
from cli_avatars.app import door_counts, tier_settings
from events import app_data_dir
from webui import auth, config, live, qr, repo_routes, server, tier_routes, writes

_BG, _FG, _SEL, _DIM, _BAD = "#0d0d1a", "#aaccff", "#223366", "#9a98b8", "#ff8866"
_FONT = fonts.face(9)


def _settings(app) -> config.WebSettings:
    return config.web_settings(getattr(app, "config", {}) or {})


def start(app, settings: config.WebSettings) -> str:
    """Serve on the chosen address; ``""`` when it runs, else why not."""
    stop(app)
    calls = writes.TkCalls(getattr(app, "root", None))
    actions = writes.Actions(app_data_dir(), book=lambda: getattr(app, "places", None),
                             model=lambda: _session_model(app), call=calls, after_change=lambda: _refresh(app))
    from cli_avatars.app.update_ui import PhoneUpdate

    try:
        app._phone_server, _thread = server.start(app_data_dir(), settings.bind, settings.port,
                                                  writes=lambda: _settings(app).allow_writes, actions=actions,
                                                  updater=PhoneUpdate(app, calls))
    except (OSError, ValueError) as exc:
        calls.stop()
        return f"Could not serve on {settings.bind}:{settings.port}: {exc}"
    app._phone_calls = calls
    live.set_roster(lambda _lay, _now: live.dungeon_roster(app))
    live.set_sessions(lambda: door_counts.session_rows(app))
    repo_routes.set_seen(lambda: getattr(app, "_repo_seen", {}))
    tier_routes.set_target(getattr(app, "_config_path", None),
                           lambda config: calls(lambda: tier_settings.apply_live(app, config)))
    return ""


def stop(app) -> None:
    live.set_roster(None)
    live.set_sessions(None)
    repo_routes.set_seen(None)
    tier_routes.set_target(None, None)
    server.stop(getattr(app, "_phone_server", None))
    app._phone_server = None
    calls = getattr(app, "_phone_calls", None)
    if calls is not None:
        calls.stop()
    app._phone_calls = None


def _session_model(app):
    from cli_avatars.app.session_rooms import model_for

    return model_for(app)


def _refresh(app) -> None:
    panel = getattr(getattr(app, "dungeon", None), "_sessions", None)
    if panel is not None:
        panel.refresh()


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
    v_writes = tk.BooleanVar(parent, current.allow_writes)
    v_if = tk.StringVar(parent, chosen)
    v_addr = tk.StringVar(parent, current.address)

    def line(text, fg=_FG):
        label = tk.Label(parent, text=text, bg=_BG, fg=fg, font=_FONT, anchor="w", justify="left", wraplength=440)
        label.pack(fill="x", padx=12, pady=2)
        return label

    line("Phone view: the Dungeon map, tasks and room chat in a browser.", _DIM)
    head = tk.Frame(parent, bg=_BG)
    head.pack(fill="x", padx=12, pady=4)
    tk.Checkbutton(head, variable=v_on, text="Serve the phone view", command=lambda: _apply(),
                   bg=_BG, fg=_FG, selectcolor=_SEL, activebackground=_BG, activeforeground="white",
                   font=_FONT, highlightthickness=0).pack(side="left")
    tk.Checkbutton(parent, variable=v_writes, text="Allow the phone to open sessions and send prompts",
                   command=lambda: _apply(), bg=_BG, fg=_FG, selectcolor=_SEL, activebackground=_BG,
                   activeforeground="white", font=_FONT, highlightthickness=0).pack(anchor="w", padx=12)
    line("Off by default. On: Send on the phone runs your own CLI here, in the room's folder, like Enter "
         "in the Dungeon's chat.", _DIM)
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
                                                "bind": bind, "address": v_addr.get(),
                                                "allow_writes": bool(v_writes.get())}}, rows)
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
