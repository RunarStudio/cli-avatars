"""AG-2 dungeon kit pieces: counts plaque, state halos, +n badge, error and blocked rows."""

import unittest
from pathlib import Path

from PIL import Image

KIT = Path(__file__).resolve().parent.parent / "Sprites" / "dungeon_kit"

PIECES = {
    "b31-placa-recuentos.png": (40, 14),
    "b32-halo-verde.png": (25, 23),
    "b33-halo-azul.png": (25, 23),
    "b34-halo-rojo.png": (25, 23),
    "b35-halo-ambar.png": (25, 23),
    "b36-insignia-mas-n.png": (12, 9),
    "b37-cifras.png": (39, 5),
}
ROWS = ["avatar-rows/error.png", "avatar-rows/blocked.png"]


def _open(rel):
    path = KIT / rel
    if not path.is_file():
        raise AssertionError(f"missing {rel}")
    return Image.open(path)


class DungeonKitAG2Tests(unittest.TestCase):
    def test_pieces_sizes_and_mode(self):
        for name, size in PIECES.items():
            with self.subTest(name=name), _open(name) as im:
                self.assertEqual(im.size, size)
                self.assertEqual(im.mode, "RGBA")

    def test_rows_are_four_40px_frames(self):
        for rel in ROWS:
            with self.subTest(rel=rel), _open(rel) as im:
                self.assertEqual(im.size, (160, 40))
                self.assertEqual(im.mode, "RGBA")
                for f in range(4):
                    self.assertIsNotNone(im.crop((f * 40, 0, f * 40 + 40, 40)).getbbox(), f"frame {f} is blank")

    def test_4x_copies_are_exact(self):
        rels = list(PIECES) + ROWS
        for rel in rels:
            big_rel = "/".join(rel.split("/")[:-1] + ["4x", rel.split("/")[-1]])
            with self.subTest(rel=rel), _open(rel) as im, _open(big_rel) as big:
                self.assertEqual(big.mode, "RGBA")
                self.assertEqual(big.size, (im.width * 4, im.height * 4))
                self.assertEqual(big.tobytes(), im.resize(big.size, Image.NEAREST).tobytes())

    def test_index_lists_pieces(self):
        index = (KIT / "INDEX.md").read_text(encoding="utf-8")
        for name, (w, h) in PIECES.items():
            with self.subTest(name=name):
                row = next((ln for ln in index.splitlines() if ln.startswith(f"| {name} |")), None)
                self.assertIsNotNone(row)
                self.assertIn(f"| {w}x{h} |", row)


if __name__ == "__main__":
    unittest.main()
