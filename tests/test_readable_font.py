"""FONT.1: one readable text face from config, bundled OFL files, no hard-coded Courier, phone serves the face."""

import http.client
import json
import re
import subprocess  # noqa: TID251  # the Tk fonts run in a child, like test_door_plaque
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

import text_fonts as fonts  # noqa: E402
from cli_avatars.app.config_file import save_config_with  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from webui import auth  # noqa: E402

HARD = re.compile(r"""\(\s*["'](Courier|Courier New|Consolas)["']\s*,|family["']?\s*[=:]\s*["'](Courier|Consolas)""")
ALLOWED = {ROOT / "text_fonts.py"}


class Choice(unittest.TestCase):
    def test_default_is_atkinson_medium_spaced(self):
        self.assertEqual(fonts.choice({}), fonts.Choice("atkinson", "M", True))

    def test_config_keys_pick_the_face(self):
        got = fonts.choice({"text": {"font": "lexend", "size": "L", "spacing": False}})
        self.assertEqual(got, fonts.Choice("lexend", "L", False))

    def test_bad_values_fall_back(self):
        got = fonts.choice({"text": {"font": "comic", "size": "XL", "spacing": "yes"}})
        self.assertEqual(got, fonts.Choice("atkinson", "M", True))
        self.assertEqual(fonts.choice({"text": "pixel"}), fonts.Choice("atkinson", "M", True))

    def test_saved_per_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"sound": {"cues": True}}), encoding="utf-8")
            picked = fonts.Choice("opendyslexic", "S", False)
            self.assertTrue(save_config_with(path, lambda data: fonts.with_choice(data, picked)))
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["text"], {"font": "opendyslexic", "size": "S", "spacing": False})
        self.assertEqual(data["sound"], {"cues": True})

    def test_readable_sizes_and_pixel_keeps_the_old_ones(self):
        medium = fonts.Choice("atkinson", "M", True)
        self.assertGreaterEqual(fonts.spec(10, choice=medium)["size"], 12)
        self.assertGreaterEqual(fonts.spec(9, choice=medium)["size"], 12)
        self.assertLess(fonts.spec(10, choice=fonts.Choice("atkinson", "S", True))["size"],
                        fonts.spec(10, choice=fonts.Choice("atkinson", "L", True))["size"])
        pixel = fonts.spec(9, True, choice=fonts.Choice("pixel", "M", True))
        self.assertEqual((pixel["size"], pixel["weight"]), (9, "bold"))

    def test_caps_only_under_pixel(self):
        self.assertEqual(fonts.caps("WHERE WE ARE", fonts.Choice("atkinson", "M", True)), "Where we are")
        self.assertEqual(fonts.caps("WHERE WE ARE", fonts.Choice("pixel", "M", True)), "WHERE WE ARE")


class Files(unittest.TestCase):
    def test_each_face_is_bundled_with_its_licence(self):
        for name in ("atkinson", "lexend", "opendyslexic"):
            regular, bold = fonts.files(name)
            for path in (regular, bold):
                with self.subTest(path=path.name):
                    self.assertTrue(path.is_file())
                    self.assertTrue((path.parent / "OFL.txt").is_file())
                    self.assertIn("SIL Open Font License", (path.parent / "OFL.txt").read_text(encoding="utf-8"))
            self.assertTrue(fonts.web_file(regular.stem + ".woff2").is_file())
        self.assertEqual(fonts.files("pixel"), ())

    def test_pillow_uses_the_same_file(self):
        face = fonts.pil_font(16, choice=fonts.Choice("lexend", "M", True))
        self.assertEqual(face.getname()[0], "Lexend")
        self.assertIsNone(fonts.pil_font(16, choice=fonts.Choice("pixel", "M", True)))

    def test_windows_registers_privately(self):
        calls = []

        class Gdi:
            def AddFontResourceExW(self, path, flags, reserved):  # noqa: N802
                calls.append((path, flags))
                return 1

        with patch.object(fonts.sys, "platform", "win32"), patch.object(fonts, "_gdi32", lambda: Gdi()):
            added = fonts.register_files()
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(flags == fonts.FR_PRIVATE for _p, flags in calls))
        self.assertEqual(added, 6)

    def test_linux_without_fontconfig_falls_back_with_a_log_line(self):
        with patch.object(fonts.sys, "platform", "linux"), patch.object(fonts, "_fontconfig", lambda: None):
            self.assertEqual(fonts.register_files(), 0)
        with self.assertLogs("cli_avatars.fonts", "WARNING") as seen:
            family = fonts.resolve("atkinson", {"DejaVu Sans", "Courier"})
        self.assertEqual(family, "DejaVu Sans")
        self.assertIn("Atkinson Hyperlegible", seen.output[0])
        self.assertEqual(fonts.resolve("atkinson", {"Atkinson Hyperlegible"}), "Atkinson Hyperlegible")
        self.assertEqual(fonts.resolve("pixel", set()), "Courier")


class NoHardCodedFaces(unittest.TestCase):
    def test_no_widget_keeps_courier_or_consolas(self):
        found = []
        files = list((ROOT / "cli_avatars").rglob("*.py")) + list((ROOT / "webui").glob("*.py"))
        files += [ROOT / "chat_window.py", ROOT / "hud.py"]
        for path in files:
            if path in ALLOWED:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if HARD.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{n}")
        self.assertEqual(found, [])


class Phone(unittest.TestCase):
    def test_page_links_the_text_css(self):
        html = (ROOT / "webui" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertTrue('href="/static/text.css"' in html, "index.html has no text.css link")

    def test_css_serves_the_chosen_face(self):
        css = fonts.css(fonts.Choice("lexend", "L", True))
        self.assertIn("@font-face", css)
        self.assertIn("/static/fonts/Lexend-Regular.woff2", css)
        self.assertIn('"Lexend"', css)
        self.assertIn("letter-spacing", css)
        self.assertIn("line-height: 1.5", css)
        self.assertNotIn("@font-face", fonts.css(fonts.Choice("pixel", "M", True)))



class PhoneServer(_Writes):
    def raw(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.request("GET", path, headers={"Cookie": f"{auth.COOKIE}={auth.session_value(self.token)}"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data, resp.getheader("Content-Type") or ""

    def test_server_serves_css_and_font(self):
        from webui import font_routes

        with patch.object(font_routes, "_config", lambda: {"text": {"font": "opendyslexic"}}):
            status, raw, ctype = self.raw("/static/text.css")
            self.assertEqual((status, ctype.split(";")[0]), (200, "text/css"))
            self.assertIn("OpenDyslexic-Regular.woff2", raw.decode())
            status, raw, ctype = self.raw("/static/fonts/OpenDyslexic-Regular.woff2")
            self.assertEqual((status, ctype), (200, "font/woff2"))
            self.assertEqual(raw[:4], b"wOF2")
            self.assertEqual(self.raw("/static/fonts/OFL.txt")[0], 404)
            self.assertEqual(self.raw("/static/fonts/x.woff2")[0], 404)


class Desktop(unittest.TestCase):
    def test_named_fonts_follow_config(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "_font_probe.py"), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
        )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("text lexend L", "title bold", "bubble", "face 9 bold", "pixel courier", "live switch",
                     "text spacing", "settings row", "settings saves", "sample line"):
            self.assertIn(f"ok {name}", proc.stdout)


class Art(unittest.TestCase):
    def test_door_sign_words_use_the_face(self):
        from cli_avatars.app import door_signs

        lines = ("Forge", "Doing: oil the hinges", "Blocked")
        with fonts.using(fonts.Choice("pixel", "M", True)):
            pixel = door_signs.sign_image(lines, False, None, 2)
        with fonts.using(fonts.Choice("atkinson", "M", True)):
            readable = door_signs.sign_image(lines, False, None, 2)
        self.assertGreater(readable.height, pixel.height)
        self.assertGreaterEqual(fonts.px(11), 15)

    def test_standup_bubble_and_plaque_tip_use_the_face(self):
        from cli_avatars.app import door_plaque, standup_art

        with fonts.using(fonts.Choice("pixel", "M", True)):
            old = standup_art.bubble("Ash", "done: hinges oiled · next: paint the gate", "ok")
            tip = door_plaque.tip_image("Apothecary", {"agents": 2})
        with fonts.using(fonts.Choice("atkinson", "M", True)):
            new = standup_art.bubble("Ash", "done: hinges oiled · next: paint the gate", "ok")
            tip2 = door_plaque.tip_image("Apothecary", {"agents": 2})
        self.assertNotEqual(old.size, new.size)
        self.assertGreater(tip2.height, tip.height)


if __name__ == "__main__":
    unittest.main()
