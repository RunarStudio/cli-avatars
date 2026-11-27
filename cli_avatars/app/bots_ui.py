"""Bots in the Topics dock, and the Settings tab that edits the roster.

No new window. Thumbnails are 40×40 idle frames of a shipped sheet, hue
shifted per bot. The status line sits under the name. Icon bubbles stay
icons; this text is the one line the status file is allowed to carry.
"""

from __future__ import annotations

import time
import tkinter as tk

import text_fonts as fonts
from bots.roster import SKINS, hue_degrees
from bots.status_source import SourceConfig, valid_branch, valid_url
from cli_avatars.desktop.capabilities import HAS_PIL
from rooms import idle_thumbnail

_BG = "#0d0d1a"
_INK = "#e8e6f4"
_DIM = "#9a98b8"
_ACCENT = "#88aaff"
_SEL = "#223366"
_GREY = "#5a5870"
_FONT = fonts.face(9)
_SMALL = fonts.face(8)
_THUMB = 40


def bot_signature(app) -> tuple:
    service = getattr(app, "bots", None)
    if service is None:
        return ()
    try:
        return service.signature()
    except Exception:
        return ()


def render_bot_sections(app, parent) -> None:
    """Pack the Bots area into the Topics list. The caller clears ``parent``."""
    service = getattr(app, "bots", None)
    if service is None:
        return
    photos = getattr(app, "_bot_photos", None)
    if photos is None:
        photos = []
        app._bot_photos = photos
    photos.clear()
    vars_ = getattr(app, "_bot_vars", None)
    if vars_ is None:
        vars_ = []
        app._bot_vars = vars_
    vars_.clear()
    tk.Label(
        parent, text="Bots", bg=_BG, fg=_ACCENT, font=fonts.face(10, "bold"), anchor="w",
    ).pack(anchor="w", padx=12, pady=(12, 2))
    try:
        sections = service.sections()
    except Exception:
        tk.Label(parent, text="Roster unavailable", bg=_BG, fg=_DIM, font=_FONT).pack(anchor="w", padx=12)
        return
    if not sections:
        tk.Label(
            parent, text="No bots yet. Import the example in Settings.",
            bg=_BG, fg=_DIM, font=_FONT, anchor="w", justify="left", wraplength=240,
        ).pack(anchor="w", padx=12, pady=4)
        return
    for group, bots in sections:
        _group_block(app, parent, service, group, bots, photos, vars_)


def build_bots_settings(app, parent) -> None:
    """Settings tab: groups, assignment, source, and import."""
    service = getattr(app, "bots", None)
    if service is None:
        tk.Label(parent, text="Bot roster is off.", bg=_BG, fg=_DIM, font=_FONT).pack(anchor="w", padx=12, pady=8)
        return
    canvas = tk.Canvas(parent, bg=_BG, highlightthickness=0, bd=0)
    canvas.pack(side="left", fill="both", expand=True)
    body = tk.Frame(canvas, bg=_BG)
    window = canvas.create_window((0, 0), window=body, anchor="nw")

    def _fit(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(window, width=event.width)

    body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", _fit)

    def refill() -> None:
        for child in body.winfo_children():
            child.destroy()
        _settings_body(app, body, service, refill)

    refill()


def _group_block(app, parent, service, group, bots, photos, vars_) -> None:
    head = tk.Frame(parent, bg=_BG)
    head.pack(fill="x", padx=10, pady=(6, 0))
    mark = "▸" if group.collapsed else "▾"
    tk.Button(
        head, text=f"{mark} {group.name}", command=lambda: _collapse(app, service, group),
        bg=_BG, fg=_ACCENT, activebackground=_BG, activeforeground="white",
        font=fonts.face(10, "bold"), relief="flat", anchor="w", cursor="hand2",
    ).pack(side="left")
    shown = tk.BooleanVar(value=group.show_in_dungeon)
    vars_.append(shown)
    tk.Checkbutton(
        parent, text="Show group in Dungeon", variable=shown,
        command=lambda gid=group.id, var=shown: _show(app, service, gid, var),
        bg=_BG, fg=_DIM, selectcolor=_SEL, activebackground=_BG, activeforeground=_INK,
        font=_SMALL, highlightthickness=0, anchor="w",
    ).pack(anchor="w", padx=18)
    if group.collapsed:
        return
    if not bots:
        tk.Label(parent, text="No bots", bg=_BG, fg=_DIM, font=_SMALL).pack(anchor="w", padx=22)
        return
    for bot, status in bots:
        _bot_row(parent, bot, status, photos)


def _bot_row(parent, bot, status, photos) -> None:
    row = tk.Frame(parent, bg=_BG)
    row.pack(fill="x", padx=16, pady=2)
    photo = _thumb(bot)
    if photo is not None:
        photos.append(photo)
        shot = tk.Label(row, image=photo, bg=_BG, width=_THUMB, height=_THUMB)
        shot.image = photo
        shot.pack(side="left")
    else:
        tk.Label(
            row, text=(bot.emoji or bot.name[:1] or "?"), bg=_SEL, fg=_INK,
            font=_FONT, width=4, height=2,
        ).pack(side="left")
    text = tk.Frame(row, bg=_BG)
    text.pack(side="left", fill="x", expand=True, padx=(8, 0))
    title = f"{bot.emoji} {bot.name}".strip()
    line = tk.Frame(text, bg=_BG)
    line.pack(anchor="w")
    tk.Label(line, text=title, bg=_BG, fg=_INK, font=_FONT).pack(side="left")
    tk.Label(line, text="●", bg=_BG, fg=status.dot, font=_FONT).pack(side="left", padx=(6, 0))
    if status.line:
        tk.Label(text, text=status.line, bg=_BG, fg=_DIM, font=_SMALL).pack(anchor="w")


def _thumb(bot):
    if not HAS_PIL:
        return None
    try:
        from PIL import ImageTk

        from sprite_loader import hue_rotate_image
    except Exception:
        return None
    image = idle_thumbnail(bot.skin, _THUMB)
    if image is None:
        return None
    hue = hue_degrees(bot.id)
    if hue:
        try:
            image = hue_rotate_image(image, hue)
        except Exception:
            pass
    try:
        return ImageTk.PhotoImage(image)
    except Exception:
        return None


def _collapse(app, service, group) -> None:
    service.set_collapsed(group.id, not group.collapsed)
    _refresh_topics(app)


def _show(app, service, group_id, var) -> None:
    service.set_show(group_id, bool(var.get()))
    _refresh_topics(app)


def _refresh_topics(app) -> None:
    app._rooms_sig = None
    refresh = getattr(app, "_update_rooms_win", None)
    if refresh is not None:
        refresh(True)


def _settings_body(app, parent, service, refill) -> None:
    config = service.source_config()
    tk.Label(parent, text="Status source", bg=_BG, fg=_ACCENT, font=fonts.face(10, "bold")).pack(
        anchor="w", padx=12, pady=(8, 2),
    )
    kind = tk.StringVar(value=config.kind)
    url = tk.StringVar(value=config.url)
    branch = tk.StringVar(value=config.branch)
    interval = tk.StringVar(value=str(config.interval_s))
    folder = tk.StringVar(value=config.folder)
    _field(parent, "Kind", lambda host: _kind_menu(host, kind))
    _field(parent, "Repo URL", lambda host: _entry(host, url))
    _field(parent, "Branch", lambda host: _entry(host, branch))
    _field(parent, "Every (s)", lambda host: _entry(host, interval, 6))
    _field(parent, "Local folder", lambda host: _entry(host, folder))
    tk.Label(
        parent,
        text="Git fetch uses the credentials already on this PC. Min 30 s. No token is stored.",
        bg=_BG, fg=_DIM, font=_SMALL, wraplength=280, justify="left",
    ).pack(anchor="w", padx=12, pady=(2, 4))
    tk.Button(
        parent, text="Save source", command=lambda: _save_source(service, kind, url, branch, interval, folder, refill),
        bg=_SEL, fg="#aaccff", font=_FONT, relief="flat", cursor="hand2",
    ).pack(anchor="w", padx=12, pady=4)

    tk.Label(parent, text="Groups", bg=_BG, fg=_ACCENT, font=fonts.face(10, "bold")).pack(
        anchor="w", padx=12, pady=(10, 2),
    )
    sections = service.sections()
    for group, _bots in sections:
        _group_editor(app, parent, service, group, refill)
    new_name = tk.StringVar()
    add = tk.Frame(parent, bg=_BG)
    add.pack(fill="x", padx=12, pady=4)
    tk.Entry(
        add, textvariable=new_name, bg=_SEL, fg=_INK, insertbackground=_INK, font=_FONT, width=16, relief="flat",
    ).pack(side="left")
    tk.Button(
        add, text="Add group", command=lambda: _add_group(app, service, new_name, refill),
        bg=_SEL, fg="#aaccff", font=_FONT, relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)

    tk.Label(parent, text="Bots", bg=_BG, fg=_ACCENT, font=fonts.face(10, "bold")).pack(
        anchor="w", padx=12, pady=(10, 2),
    )
    if hasattr(service, "hidden"):
        _hide_row(app, parent, service)
    names = [group.name for group, _bots in sections]
    ids = [group.id for group, _bots in sections]
    for _group, bots in sections:
        for bot, _status in bots:
            _bot_editor(app, parent, service, bot, names, ids, refill)
    tk.Button(
        parent, text="Import example", command=lambda: _import(app, service, refill),
        bg=_SEL, fg="#aaccff", font=fonts.face(9, "bold"), relief="flat", cursor="hand2",
    ).pack(anchor="w", padx=12, pady=(8, 12))


def _group_editor(app, parent, service, group, refill) -> None:
    row = tk.Frame(parent, bg=_BG)
    row.pack(fill="x", padx=12, pady=1)
    name = tk.StringVar(value=group.name)
    tk.Entry(
        row, textvariable=name, bg=_SEL, fg=_INK, insertbackground=_INK, font=_FONT, width=16, relief="flat",
    ).pack(side="left")
    tk.Button(
        row, text="Up", command=lambda: _move(app, service, group.id, -1, refill),
        bg=_SEL, fg="#aaccff", font=_SMALL, relief="flat",
    ).pack(side="left", padx=2)
    tk.Button(
        row, text="Down", command=lambda: _move(app, service, group.id, 1, refill),
        bg=_SEL, fg="#aaccff", font=_SMALL, relief="flat",
    ).pack(side="left")
    collapsed = tk.BooleanVar(value=group.collapsed)
    tk.Checkbutton(
        row, text="Collapse", variable=collapsed,
        command=lambda gid=group.id, var=collapsed: _set_collapsed(app, service, gid, var, refill),
        bg=_BG, fg=_DIM, selectcolor=_SEL, activebackground=_BG, font=_SMALL, highlightthickness=0,
    ).pack(side="left", padx=4)
    tk.Button(
        row, text="Rename", command=lambda gid=group.id, var=name: _rename(app, service, gid, var, refill),
        bg=_SEL, fg="#aaccff", font=_SMALL, relief="flat",
    ).pack(side="left")


def _bot_editor(app, parent, service, bot, names, ids, refill) -> None:
    row = tk.Frame(parent, bg=_BG)
    row.pack(fill="x", padx=12, pady=1)
    hidden = service.hidden(bot.id) if hasattr(service, "hidden") else False
    tk.Label(row, text=bot.name, bg=_BG, fg=_GREY if hidden else _INK, font=_SMALL, width=16,
             anchor="w").pack(side="left")
    by_id = dict(zip(ids, names, strict=True))
    current = by_id.get(bot.group_id, names[0] if names else "")
    group_var = tk.StringVar(value=current)
    if names:
        menu = tk.OptionMenu(row, group_var, *names)
        menu.config(bg=_SEL, fg="#aaccff", font=_SMALL, highlightthickness=0, relief="flat")
        menu.pack(side="left")
    skin_var = tk.StringVar(value=bot.skin if bot.skin in SKINS else SKINS[0])
    skin = tk.OptionMenu(row, skin_var, *SKINS)
    skin.config(bg=_SEL, fg="#aaccff", font=_SMALL, highlightthickness=0, relief="flat")
    skin.pack(side="left", padx=2)
    tk.Button(
        row, text="Assign",
        command=lambda: _assign(app, service, bot.id, group_var, skin_var, names, ids, refill),
        bg=_SEL, fg="#aaccff", font=_SMALL, relief="flat",
    ).pack(side="left")
    if not hasattr(service, "hidden"):
        return
    line = tk.Frame(parent, bg=_BG)
    line.pack(fill="x", padx=24)
    pin = tk.BooleanVar(value=bot.always_show)
    tk.Checkbutton(
        line, text="Always show", variable=pin, command=lambda: _pin(app, service, bot.id, pin, refill),
        bg=_BG, fg=_DIM, selectcolor=_SEL, activebackground=_BG, font=_SMALL, highlightthickness=0,
    ).pack(side="left")
    seen = service.last_seen(bot.id)
    words = f"last seen {_ago(time.time() - seen)}" if seen else "no status yet"
    tk.Label(line, text=("hidden from the Dungeon · " if hidden else "") + words, bg=_BG,
             fg=_GREY if hidden else _DIM, font=_SMALL).pack(side="left", padx=6)


def _ago(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


def _pin(app, service, bot_id, var, refill) -> None:
    service.set_always_show(bot_id, bool(var.get()))
    refill()
    _refresh_topics(app)


def _hide_row(app, parent, service) -> None:
    """MEMORY.1: Hide a bot from the Dungeon after N hours without a status update (``bots.hide_after_hours``)."""
    from bots.service import hide_after_s
    from cli_avatars.app.config_file import save_config_with

    hours = tk.StringVar(value=f"{hide_after_s(getattr(app, 'config', None)) / 3600:g}")
    row = tk.Frame(parent, bg=_BG)
    row.pack(fill="x", padx=12, pady=1)
    tk.Label(row, text="Hide after (h)", bg=_BG, fg="#aaccff", font=_SMALL, width=12, anchor="w").pack(side="left")
    _entry(row, hours, 6)
    note = tk.Label(row, text="", bg=_BG, fg=_DIM, font=_SMALL)

    def save():
        try:
            value = float(hours.get())
        except ValueError:
            value = 0
        if not 0 < value <= 24 * 30:
            note.config(text="1 to 720 hours")
            return
        config = dict(getattr(app, "config", None) or {})
        app.config = {**config, "bots": {**(config.get("bots") or {}), "hide_after_hours": value}}
        service.hide_after_s = value * 3600
        target = getattr(app, "_config_path", None)
        if target is not None:
            save_config_with(target, lambda data: {**data, "bots": {**(data.get("bots") or {}),
                                                                     "hide_after_hours": value}})
        note.config(text="Saved")

    tk.Button(row, text="Save", command=save, bg=_SEL, fg="#aaccff", font=_SMALL, relief="flat").pack(side="left",
                                                                                                    padx=4)
    note.pack(side="left")


def _field(parent, label, builder) -> None:
    row = tk.Frame(parent, bg=_BG)
    row.pack(fill="x", padx=12, pady=1)
    tk.Label(row, text=label, bg=_BG, fg="#aaccff", font=_SMALL, width=12, anchor="w").pack(side="left")
    builder(row)


def _entry(parent, variable, width=22) -> None:
    tk.Entry(
        parent, textvariable=variable, bg=_SEL, fg=_INK, insertbackground=_INK,
        font=_SMALL, width=width, relief="flat",
    ).pack(side="left")


def _kind_menu(parent, variable) -> None:
    menu = tk.OptionMenu(parent, variable, "git", "folder")
    menu.config(bg=_SEL, fg="#aaccff", font=_SMALL, highlightthickness=0, relief="flat")
    menu.pack(side="left")


def _save_source(service, kind, url, branch, interval, folder, refill) -> None:
    raw_url = url.get().strip()
    raw_branch = branch.get().strip()
    try:
        seconds = int(interval.get().strip())
    except ValueError:
        seconds = 60
    service.save_source(
        SourceConfig(
            kind.get().strip() or "git",
            raw_url if valid_url(raw_url) else service.source_config().url,
            raw_branch if valid_branch(raw_branch) else service.source_config().branch,
            seconds,
            folder.get().strip() or "status-local",
        )
    )
    refill()


def _add_group(app, service, name, refill) -> None:
    service.add_group(name.get())
    name.set("")
    refill()
    _refresh_topics(app)


def _move(app, service, group_id, delta, refill) -> None:
    service.move_group(group_id, delta)
    refill()
    _refresh_topics(app)


def _rename(app, service, group_id, name, refill) -> None:
    service.rename_group(group_id, name.get())
    refill()
    _refresh_topics(app)


def _set_collapsed(app, service, group_id, var, refill) -> None:
    service.set_collapsed(group_id, bool(var.get()))
    refill()
    _refresh_topics(app)


def _assign(app, service, bot_id, group_var, skin_var, names, ids, refill) -> None:
    try:
        group_id = ids[names.index(group_var.get())]
    except ValueError:
        return
    service.assign(bot_id, group_id)
    service.set_skin(bot_id, skin_var.get())
    refill()
    _refresh_topics(app)


def _import(app, service, refill) -> None:
    try:
        service.import_example()
    except Exception:
        return
    refill()
    _refresh_topics(app)
