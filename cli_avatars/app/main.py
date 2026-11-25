"""``python overlay.py`` and ``--selftest``. The shell owns the window."""

# DPI awareness runs at import, before tkinter and before any tk.Tk().
import cli_avatars.desktop.capabilities  # noqa: F401  # isort: skip
import os
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from bubbles import BubbleBoard
from bundle_paths import asset_path
from chat_window import ChatWindow
from cli_avatars.app.bootcheck import run_bootcheck_only
from cli_avatars.app.shell import OverlayApp
from cli_avatars.sprites.registry import REGISTRY
from cli_avatars.sprites.registry import load_sprites as _load_sprites
from webui import phone_ui


def run_selftest() -> int:
    """Load bundled sprites and build the HUD and chat window off-screen.

    Returns 0 when the widgets construct, 1 when an asset or Tk option fails.
    Used by ``build.ps1`` as ``cli-avatars.exe --selftest``. The chat window
    is filled from simulated store rows. It does not start a CLI.
    """
    problems: list[str] = []
    required = (
        asset_path("Sprites", "caine.png"),
        asset_path("Sprites", "bubble.png"),
        asset_path("Sprites", "talk", "frame.png"),
        asset_path("Sprites", "talk", "tail.png"),
        asset_path("Sprites", "talk", "icons.png"),
    )
    for path in required:
        if not path.is_file():
            problems.append("missing " + path.name)
    if REGISTRY is None:
        problems.append("sprite registry unavailable")
    else:
        try:
            _load_sprites(REGISTRY)
        except Exception as exc:
            problems.append("sprites: " + str(exc))
        else:
            if not REGISTRY.has("caine"):
                problems.append("caine sheet did not load")
    try:
        from activity import line_from_agent
        from bubbles import render_text_frame

        if line_from_agent("busy", "Read", "TASKS.md", 0) != "Reading TASKS.md":
            problems.append("activity line")
        frame = render_text_frame(48, 12)
        if frame.size[0] < 16 or frame.size[1] < 16:
            problems.append("activity frame")
    except Exception as exc:
        problems.append("activity: " + type(exc).__name__)
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.geometry("320x200+20000+20000")
        host = OverlayApp.__new__(OverlayApp)
        host.root = root
        host._offscreen = True
        host.scanner = SimpleNamespace(bubbles=BubbleBoard())
        host._rooms_shown = False
        host._chat_shown = False
        host._rooms_btn = None
        host._chat_btn = None
        host._hud_drag_origin = None
        host.config = {}
        host._decision_count = 0
        host._config_path = None
        from cli_avatars.app.dungeon_window import DungeonWindow

        host.dungeon = DungeonWindow(host)
        host.dungeon.build(offscreen=True)
        root.update_idletasks()
        scene = getattr(host.dungeon, "scene", None)
        if scene is None or not scene.winfo_exists():
            problems.append("Dungeon was not created")
        else:
            try:
                if int(root.overrideredirect() or 0):
                    problems.append("Dungeon is borderless")
                minimum = root.minsize()
                if int(minimum[0]) < 720 or int(minimum[1]) < 480:
                    problems.append("Dungeon minsize is below 720x480")
            except tk.TclError as exc:
                problems.append("dungeon: " + str(exc))
        import tempfile

        from chat_window import seed_simulated, simulated_agents
        from events import close_logging

        problems += _selftest_memmap(host)

        data = tempfile.TemporaryDirectory()
        try:
            seed_simulated(data.name)
            window = ChatWindow(
                root,
                directory=Path(data.name),
                agents=simulated_agents(),
                config={},
                config_path=Path(data.name) / "missing-config.json",
                offscreen=True,
            )
            window.open(topic_id="hooks", address_id="abcd1234_sub_0")
            root.update_idletasks()
            if window.win is None or not window.win.winfo_exists():
                problems.append("chat window was not created")
            elif window.recipient_ids() != ["abcd1234"]:
                problems.append("chat composer did not address the orchestrator")
            else:
                window.win.withdraw()
        finally:
            close_logging(Path(data.name))
            data.cleanup()
    except tk.TclError as exc:
        problems.append("tk: " + str(exc))
    except Exception as exc:
        problems.append(type(exc).__name__ + ": " + str(exc))
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    if problems:
        for item in problems:
            print("selftest: " + item, file=sys.stderr)
        return 1
    print("selftest: ok")
    return 0


def _selftest_memmap(host) -> list[str]:
    """Memory map section under Topics, filled from fixture records in a temp data dir."""
    import tempfile
    import time

    from cli_avatars.app.memmap_feed import Request
    from cli_avatars.app.memmap_panel import MemmapPanel
    from memmap import store
    from memmap.demo import records

    left = getattr(host.dungeon, "_left", None)
    topics = getattr(host.dungeon, "_topics", None)
    if left is None or topics is None:
        return ["memmap: no left dock"]
    with tempfile.TemporaryDirectory() as tmp:
        store.append_records(tmp, "selftest", records(time.time()))
        panel = MemmapPanel(host, directory=tmp, threaded=False)
        panel.mount(left, topics)
        host.root.update_idletasks()
        result = panel.compute_now(Request(window="7d"))
        if result is None or not result.graph.nodes or not panel._nodes:
            return ["memmap: panel drew no nodes"]
        if panel.last_draw_ms > 16.0:
            return [f"memmap: first build {panel.last_draw_ms:.2f} ms over 16 ms"]
        best = min(panel.draw(force=True) for _ in range(3))
        if best > 2.0:
            return [f"memmap: redraw {best:.2f} ms over 2 ms"]
    return []


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if "--activity-demo" in args:
        os.environ["CLI_AVATARS_ACTIVITY_DEMO"] = "1"
    if "--bootcheck-only" in args:
        return run_bootcheck_only()
    if "--selftest" in args:
        return run_selftest()
    from cli_avatars.app import ops
    from events import app_data_dir

    data = app_data_dir()
    if "--wait-pid" in args:
        # OPS.1 restart: the old Dungeon still holds the event port until it exits
        try:
            old = int(args[args.index("--wait-pid") + 1])
        except (IndexError, ValueError):
            old = 0
        if not ops.wait_for_exit(old):
            ops.log_line(data, f"pid {old} still running after 30 s; starting anyway")
    try:
        app = OverlayApp()
    except Exception as exc:
        ops.log_crash(data, "start", exc)
        raise
    ops.attach(app, data)
    phone_ui.start_from_config(app)
    try:
        app.run()
    except Exception as exc:
        ops.log_crash(data, "run", exc)
        raise
    finally:
        phone_ui.stop(app)
        ops.log_line(data, f"stopped pid {os.getpid()}")
    return 0
