"""FIX.CHAT: a strolling avatar's nameplate stays above its head; no sideways jump per tick."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import nameplates  # noqa: E402


class _Scene:
    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600


def _avatar():
    return SimpleNamespace(aw=48, ah=48, agent=SimpleNamespace(agent_id="caine"), plate_text=lambda: "Claude-1a2b\nidle")


class PlateFollowsStroll(unittest.TestCase):
    def test_plate_stays_centred_at_any_sub_pixel_spot(self):
        av = _avatar()
        with patch.object(nameplates, "plate_pixels", lambda _scene, _text: (80, 22)):
            for step in range(40):
                spot = (400.0 + step * 0.3, 300.0 + step * 0.15)
                nameplates.seat_inside(_Scene(), ["caine"], {"caine": spot}, {"caine": av}, None)
                left, top, width, _h = av._label_box
                self.assertLessEqual(abs(left + width / 2.0 - spot[0]), 1.0, f"step {step} spot {spot}")
                self.assertLess(top, spot[1] - av.ah / 2.0, f"step {step} spot {spot}")


if __name__ == "__main__":
    unittest.main()
