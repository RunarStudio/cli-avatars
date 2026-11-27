"""LEFTOVERS: ``rooms.write_rooms_preview`` draws its state dots from the one palette (``status_ink``)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import status_ink  # noqa: E402
from rooms import DOT_COLOR, write_rooms_preview  # noqa: E402


def _rgb(color: str) -> tuple:
    text = color.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


class RoomsPreviewInk(unittest.TestCase):
    def test_preview_dots_use_the_one_palette(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as name:
            path = write_rooms_preview(Path(name) / "rooms-list.png")
            with Image.open(path) as image:
                colours = {rgb for _count, rgb in image.convert("RGB").getcolors(1 << 20)}
        for state in ("busy", "thinking", "subagent"):
            self.assertTrue(_rgb(status_ink.colour(state)) in colours, f"{state} palette dot missing")
            if DOT_COLOR[state].lower() != status_ink.colour(state).lower():
                self.assertFalse(_rgb(DOT_COLOR[state]) in colours, f"{state} old dot shown")


if __name__ == "__main__":
    unittest.main()
