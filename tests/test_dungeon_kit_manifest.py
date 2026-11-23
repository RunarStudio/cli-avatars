"""AG-4 dungeon kit manifest: one valid entry per 1x PNG."""

import json
import unittest
from pathlib import Path

from PIL import Image

KIT = Path(__file__).resolve().parent.parent / "Sprites" / "dungeon_kit"
CATEGORIES = {"floor", "wall", "door", "stair", "light", "state", "decal", "prop", "ui", "avatar-row"}


def _pngs():
    return sorted(p.relative_to(KIT).as_posix() for p in list(KIT.glob("*.png")) + list(KIT.glob("avatar-rows/*.png")))


class DungeonKitManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
        cls.pieces = cls.data["pieces"]

    def test_top_level(self):
        self.assertIsInstance(self.data["version"], int)
        self.assertEqual(self.data["tile"], [32, 16])

    def test_one_entry_per_png(self):
        files = [e["file"] for e in self.pieces.values()]
        self.assertEqual(sorted(files), _pngs())
        for stem, e in self.pieces.items():
            with self.subTest(stem=stem):
                self.assertEqual(Path(e["file"]).stem, stem)

    def test_fields(self):
        tw, th = self.data["tile"]
        for stem, e in self.pieces.items():
            with self.subTest(stem=stem), Image.open(KIT / e["file"]) as im:
                self.assertEqual(e["size"], list(im.size))
                w, h = im.size
                ax, ay = e["anchor"]
                self.assertTrue(all(isinstance(v, int) for v in (ax, ay)))
                # A grid vertex may lie off the sprite (rock below, torch beside the wall), never more than a tile.
                self.assertTrue(-tw <= ax <= w + tw and -tw <= ay <= h + th, e["anchor"])
                self.assertIn(e["category"], CATEGORIES)
                self.assertIs(type(e["light"]), bool)
                self.assertEqual(len(e["footprint"]), 2)
                self.assertTrue(all(type(v) is int and v >= 0 for v in e["footprint"]))

    def test_x4_copies(self):
        for stem, e in self.pieces.items():
            if "x4" not in e:
                continue
            with self.subTest(stem=stem), Image.open(KIT / e["file"]) as im, Image.open(KIT / e["x4"]) as big:
                self.assertEqual(big.size, (im.width * 4, im.height * 4))

    def test_index_anchors_match(self):
        index = (KIT / "INDEX.md").read_text(encoding="utf-8")
        for stem, e in self.pieces.items():
            row = next((ln for ln in index.splitlines() if ln.startswith(f"| {e['file']} |")), None)
            if row is None:
                continue
            with self.subTest(stem=stem):
                # BLDG-SCHEMA: INDEX anchors sit on the north vertex; the manifest's on the footprint's south vertex.
                ax, ay = (int(v) for v in row.rstrip(" |").split("|")[-1].strip().split(","))
                w, h = e["footprint"]
                light = 8 if row.split("|")[5].strip() == "luz" else 0
                self.assertEqual(e["anchor"], [ax + (w - h) * 16, ay + (w + h) * 8 + light])

    def test_measured_anchors_not_clamped(self):
        # The south vertex may sit outside the image: wall bottoms, gates and torches keep their measured anchors.
        measured = {"b07-roca-honda": [16, -6], "b08-muro-izq": [16, 35], "b21-reja-izq": [16, 44],
                    "b23-antorcha-izq": [3, 15], "b24-antorcha-der": [-2, 15], "o05-calavera": [7, 16]}
        for stem, anchor in measured.items():
            with self.subTest(stem=stem):
                self.assertEqual(self.pieces[stem]["anchor"], anchor)

    def test_sorted_two_space(self):
        text = (KIT / "manifest.json").read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(self.data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    unittest.main()
