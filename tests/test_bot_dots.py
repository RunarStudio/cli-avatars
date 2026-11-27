"""LEFTOVERS: a bot row's dot in the Topics dock reads the one palette (``status_ink``) by the bot's avatar state."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bots.roster import Bot, Group  # noqa: E402
from bots.status import STATES, BotStatus  # noqa: E402
from cli_avatars.app import bots_ui, status_ink  # noqa: E402
from rooms import fade_hex  # noqa: E402

WANT = {
    "idle": status_ink.colour("idle"),
    "busy": status_ink.colour("busy"),
    "thinking": status_ink.colour("thinking"),
    "waiting_on_user": status_ink.colour("blocked"),
    "blocked": status_ink.colour("blocked"),
    "offline": fade_hex(status_ink.colour("idle")),
}


class BotDots(unittest.TestCase):
    def test_bot_dots_use_the_one_palette(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception:
            self.skipTest("tkinter has no display")
        self.addCleanup(root.destroy)
        group = Group("g1", "Moon forge", False, 0)
        rows = [(Bot(f"b{i}", f"Fern-{i}", "", "g1", "caine"), BotStatus(f"b{i}", state, "", "", 0.0))
                for i, state in enumerate(STATES)]
        app = SimpleNamespace(bots=SimpleNamespace(sections=lambda: [(group, rows)]))
        bots_ui.render_bot_sections(app, root)
        shown, todo = [], [root]
        while todo:
            for child in todo.pop(0).winfo_children():
                todo.append(child)
                if isinstance(child, tk.Label) and child.cget("text") == "●":
                    shown.append(child.cget("fg").lower())
        self.assertEqual(shown, [WANT[state].lower() for state in STATES])


if __name__ == "__main__":
    unittest.main()
