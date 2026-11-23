"""``python overlay.py`` and ``--selftest``. The shell owns the window."""

# DPI awareness runs at import, before tkinter and before any tk.Tk().
import cli_avatars.desktop.capabilities  # noqa: F401  # isort: skip
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from bubbles import BubbleBoard
from bundle_paths import asset_path
from chat_window import ChatWindow
from cli_avatars.app.shell import OverlayApp
from cli_avatars.sprites.registry import REGISTRY
from cli_avatars.sprites.registry import load_sprites as _load_sprites


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
        host._create_hud_win()
        root.update_idletasks()
        hud = getattr(host, "_hud_win", None)
        if hud is None or not hud.winfo_exists():
            problems.append("HUD window was not created")
        else:
            hud.withdraw()
        import tempfile

        from chat_window import seed_simulated, simulated_agents
        from events import close_logging

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


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if "--selftest" in args:
        return run_selftest()
    app = OverlayApp()
    app.run()
    return 0
