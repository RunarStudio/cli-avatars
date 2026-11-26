"""Boot check on the Dungeon: status line, Settings list, and ``--bootcheck-only``.

The window probe for the CLI flag runs on the caller thread. While the app
is up, that check only looks at the Dungeon that is already on screen.
Every other check runs on a daemon thread so the first frame is not delayed.
"""

from __future__ import annotations

import gc
import threading
import time
import tkinter as tk
from types import SimpleNamespace

from cli_avatars import VERSION
from cli_avatars.app.config_file import save_config_with
from cli_avatars.app.dungeon_geom import floor_diamonds
from cli_avatars.bootcheck import (
    BUDGET_S,
    HISTORY_CAP,
    HISTORY_NAME,
    BootReport,
    BootRunner,
    Check,
    CheckResult,
    Trend,
    append_history,
    check_app_data,
    check_assets,
    check_board,
    check_config,
    check_dpi,
    check_event_bus,
    check_hook_port,
    check_manifest,
    check_monitors,
    check_registry,
    check_sprites_32,
    check_sprites_40,
    compare_runs,
    format_table,
    load_last,
    stamp_now,
    status_line,
)
from cli_avatars.desktop.settings import with_bootcheck
from cli_avatars.paths import CONFIG_PATH
from cli_avatars.tuning import SPRITES_DIR
from cli_avatars.update.version import boot_commit
from events import app_data_dir, default_port

_BG = "#0d0d1a"
_INK = "#aaccff"
_DIM = "#9a98b8"
_OK = "#44ff88"
_BAD = "#ff8866"


def run_bootcheck_only() -> int:
    """Run the checks, print the table, and exit 0 when every check passed."""
    report, trend = execute()
    print(format_table(report, trend))
    return 0 if report.ok else 1


def start_bootcheck(app) -> None:
    """Start the checks after the Dungeon exists. A disabled config does nothing."""
    desktop = getattr(app, "desktop", None)
    if desktop is not None and not getattr(desktop, "bootcheck", True):
        return
    _mount_label(app)
    status, detail = inspect_dungeon(app)
    preset = {"dungeon_window": (status, detail, 0.0)}
    sink = _start_card(app)

    def work() -> None:
        # The live Dungeon is on the Tk thread. This worker must not be the
        # thread that drops a Tcl object, so collection stays on the main thread.
        enabled = gc.isenabled()
        gc.disable()
        try:
            report, trend = execute(preset=preset, on_result=sink)
        except Exception:
            report, trend = _empty_failure()
        try:
            app.root.after(
                0,
                lambda report=report, trend=trend, enabled=enabled: _finish_on_main(
                    app, report, trend, enabled,
                ),
            )
        except tk.TclError:
            if enabled:
                gc.enable()

    threading.Thread(target=work, name="cli-avatars-bootcheck", daemon=True).start()


def execute(
    preset: dict | None = None,
    data_dir=None,
    config_path=None,
    port: int | None = None,
    write_history: bool = True,
    on_result=None,
) -> tuple[BootReport, Trend]:
    """Run one boot check. History is appended in the data directory."""
    directory = app_data_dir() if data_dir is None else data_dir
    config = CONFIG_PATH if config_path is None else config_path
    hook_port = default_port() if port is None else port
    ready = dict(preset or {})
    spent = 0.0
    if "dungeon_window" not in ready:
        began = time.perf_counter()
        status, detail = probe_dungeon()
        spent = max(0.0, time.perf_counter() - began)
        ready["dungeon_window"] = (status, detail, spent * 1000.0)
    checks = build_checks(SPRITES_DIR, config, directory, hook_port)
    budget = max(0.0, BUDGET_S - spent)
    # The CLI probe destroys a Tk root on this thread. Check threads must not
    # be the ones that collect those Tcl objects.
    hold_gc = "dungeon_window" not in (preset or {})
    gc_was_on = gc.isenabled() if hold_gc else False
    if hold_gc:
        gc.disable()
    try:
        report = BootRunner(checks, budget_s=budget).run(
            preset=ready,
            version=VERSION,
            commit=boot_commit(),
            on_result=on_result,
        )
        history = directory / HISTORY_NAME
        previous = None
        if write_history:
            try:
                previous = load_last(history)
                append_history(history, report, cap=HISTORY_CAP)
            except OSError:
                previous = None
        else:
            try:
                previous = load_last(history)
            except OSError:
                previous = None
    finally:
        if hold_gc and gc_was_on:
            gc.collect()
            gc.enable()
    return report, compare_runs(report, previous)


def build_checks(sprites_dir, config_path, data_dir, port: int) -> list[Check]:
    """Check order. The window result is usually preset; the callable is the fallback."""
    return [
        Check("dungeon_window", _dungeon_unset),
        Check("assets", lambda: check_assets(sprites_dir)),
        Check("config", lambda: check_config(config_path)),
        Check("skins_manifest", lambda: check_manifest(sprites_dir)),
        Check("dpi", check_dpi),
        Check("monitors", check_monitors),
        Check("event_bus", check_event_bus),
        Check("hook_port", lambda: check_hook_port(port)),
        Check("board_store", lambda: check_board(data_dir)),
        Check("registry_store", lambda: check_registry(data_dir)),
        Check("app_data", lambda: check_app_data(data_dir)),
        Check("scene_tick", check_scene_tick),
        Check("sprites_40", lambda: check_sprites_40(sprites_dir)),
        Check("sprites_32", lambda: check_sprites_32(sprites_dir)),
    ]


def check_scene_tick() -> tuple[str, str]:
    """Time a few empty-floor layouts. No widgets and no avatar state."""
    began = time.perf_counter()
    tiles = floor_diamonds(960, 640)
    for _ in range(8):
        floor_diamonds(960, 640)
    elapsed = (time.perf_counter() - began) * 1000.0
    if not tiles:
        return "fail", "empty"
    if elapsed > 200.0:
        return "fail", f"{elapsed:.1f} ms"
    return "ok", f"{elapsed:.1f} ms"


def inspect_dungeon(app) -> tuple[str, str]:
    """The live Dungeon is a framed window with the scene widget."""
    dungeon = getattr(app, "dungeon", None)
    scene = getattr(dungeon, "scene", None)
    root = getattr(app, "root", None)
    if scene is None or root is None:
        return "fail", "missing"
    try:
        if not int(scene.winfo_exists()):
            return "fail", "missing"
        if int(root.overrideredirect() or 0):
            return "fail", "borderless"
        width, height = root.minsize()
        if int(width) < 720 or int(height) < 480:
            return "fail", "minsize"
    except tk.TclError:
        return "fail", "display"
    return "ok", "framed"


def probe_dungeon() -> tuple[str, str]:
    """Build the Dungeon off-screen, the same shape ``--selftest`` uses, then close it.

    Tcl objects are collected on this thread before the function returns.
    A later check thread must not be the one to drop them.
    """
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.geometry("320x200+20000+20000")
        from bubbles import BubbleBoard
        from cli_avatars.app.dungeon_window import DungeonWindow

        host = _ProbeHost(root)
        host.scanner = SimpleNamespace(bubbles=BubbleBoard())
        host.dungeon = DungeonWindow(host)
        host.dungeon.build(offscreen=True)
        root.update_idletasks()
        result = inspect_dungeon(host)
        host.dungeon = None
        host.scanner = None
        return result
    except tk.TclError:
        return "fail", "display"
    except Exception:
        return "fail", "display"
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        gc.collect()


def save_bootcheck_pref(path, enabled: bool) -> bool:
    """Store ``desktop.bootcheck``. A missing file is created. A symlink is left alone."""
    return save_config_with(path, lambda parsed: with_bootcheck(parsed, enabled))


def open_bootcheck_details(app) -> None:
    """Show the latest list in the Settings dock. No extra window."""
    dungeon = getattr(app, "dungeon", None)
    show = getattr(dungeon, "show_settings", None)
    if show is None:
        return
    show()
    host = getattr(dungeon, "_settings", None)
    if host is None:
        return
    panel = getattr(app, "_bootcheck_panel", None)
    if panel is None:
        panel = tk.Frame(host, bg=_BG)
        app._bootcheck_panel = panel
    _pack_panel(host, panel)
    _fill_panel(panel, getattr(app, "_bootcheck_report", None), getattr(app, "_bootcheck_trend", None))


def _start_card(app):
    """START-SETUP.1: the start card shows each check as it ends; ``None`` when it cannot be shown."""
    from cli_avatars.app import start_card

    names = [check.name for check in build_checks(SPRITES_DIR, CONFIG_PATH, app_data_dir(), 0)]
    try:
        return start_card.open_card(app, names, launch=True).sink
    except Exception:
        return None


def _dungeon_unset() -> tuple[str, str]:
    return "fail", "not run"


def _empty_failure() -> tuple[BootReport, Trend]:
    report = BootReport(
        timestamp=stamp_now(),
        version="",
        commit="",
        checks=[CheckResult("runner", "fail", 0.0, "error")],
        total_ms=0.0,
        budget_ms=BUDGET_S * 1000.0,
    )
    return report, Trend(None, None, (), ())


def _mount_label(app) -> None:
    parent = getattr(app, "_status_parent", None)
    if parent is None:
        return
    label = tk.Label(
        parent,
        text="Boot check …",
        bg="#111018",
        fg=_DIM,
        font=("Courier", 10),
        cursor="hand2",
    )
    label.pack(side="right", padx=(4, 10))
    label.bind("<Button-1>", lambda _event: _reopen(app))
    app._bootcheck_label = label


def _reopen(app) -> None:
    from cli_avatars.app import start_card

    start_card.reopen(app)


def _finish_on_main(app, report: BootReport, trend: Trend, enabled: bool) -> None:
    from cli_avatars.app import start_card

    gc.collect()
    if enabled:
        gc.enable()
    _apply(app, report, trend)
    found = start_card.card(app)
    if found is not None:
        for check in report.checks:
            found.boot(check)
        found.finished()


def _apply(app, report: BootReport, trend: Trend) -> None:
    app._bootcheck_report = report
    app._bootcheck_trend = trend
    label = getattr(app, "_bootcheck_label", None)
    if label is not None:
        try:
            label.config(text=status_line(report, trend), fg=_status_color(report, trend))
        except tk.TclError:
            pass
    panel = getattr(app, "_bootcheck_panel", None)
    if panel is None:
        return
    try:
        if panel.winfo_exists():
            _fill_panel(panel, report, trend)
    except tk.TclError:
        return


def _pack_panel(host, panel) -> None:
    try:
        if str(panel.winfo_manager()) == "pack":
            return
        others = [child for child in host.winfo_children() if child is not panel]
        if others:
            panel.pack(side="top", fill="x", before=others[0])
        else:
            panel.pack(side="top", fill="x")
    except tk.TclError:
        return


def _fill_panel(panel, report: BootReport | None, trend: Trend | None) -> None:
    for child in list(panel.winfo_children()):
        child.destroy()
    if report is None or trend is None or not report.checks:
        tk.Label(panel, text="  Boot check running", bg=_BG, fg=_DIM, font=("Courier", 10), anchor="w").pack(
            fill="x", padx=8, pady=6,
        )
        return
    tk.Label(
        panel, text="  " + status_line(report, trend), bg=_BG, fg=_status_color(report, trend),
        font=("Courier", 10, "bold"), anchor="w",
    ).pack(fill="x", padx=8, pady=(6, 2))
    for check in report.checks:
        note = ""
        if check.name in trend.regressions:
            note = "  regression"
        elif check.name in trend.improvements:
            note = "  new pass"
        tk.Label(
            panel,
            text=f"  {check.status:<8} {check.ms:7.1f} ms  {check.name}  {check.detail}{note}",
            bg=_BG,
            fg=_row_color(check, trend),
            font=("Courier", 9),
            anchor="w",
        ).pack(fill="x", padx=8)


def _status_color(report: BootReport, trend: Trend) -> str:
    if trend.regressions or any(check.status != "ok" for check in report.checks):
        return _BAD
    if (trend.pass_delta or 0) > 0 or trend.faster:
        return _OK
    return _INK


def _row_color(check, trend: Trend) -> str:
    if check.name in trend.regressions or check.status != "ok":
        return _BAD
    if check.name in trend.improvements:
        return _OK
    return _DIM


class _ProbeHost:
    """Enough of the shell for ``DungeonWindow.build(offscreen=True)``."""

    def __init__(self, root):
        self.root = root
        self.config: dict = {}
        self._config_path = None
        self._offscreen = True
        self._rooms_shown = False
        self._chat_shown = False
        self._rooms_btn = None
        self._chat_btn = None
        self.scanner = None
        self.dungeon = None

    def _quit(self):
        return None

    def _toggle_rooms(self):
        return None

    def _toggle_chat(self):
        return None

    def _create_hud_win(self):
        from cli_avatars.app.hud_window import _create_hud_win

        return _create_hud_win(self)
