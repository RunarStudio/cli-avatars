"""TIERS-SETTINGS.1: model and effort per chat tier from Settings (desktop and phone), kept across an Update.

Made-up data only: temp config files, a fake install folder pair and the phone server on loopback.
"""

import json
import subprocess  # noqa: TID251  # the Tk probe runs in a child, like test_grok_orch_ui
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cli_avatars.app import tiers  # noqa: E402
from cli_avatars.update.swap import apply_swap  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from webui import tier_routes  # noqa: E402

CLAUDE_MAIN = {"orchestrator": {"main": "claude"}}


class SaveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "config.json"
        self.path.write_text(json.dumps({**CLAUDE_MAIN, "text": {"size": 12},
                                         "chat": {"auto_notes": False, "tiers": {"task": {"cli": "cursor"}}}}),
                             encoding="utf-8")

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_settings_write_each_tier_and_the_table_reads_it_back(self):
        self.assertTrue(tiers.save_tier(self.path, "main", "opus", "medium"))
        self.assertTrue(tiers.save_tier(self.path, "topic", "opus", "medium"))
        self.assertTrue(tiers.save_tier(self.path, "task", "my-model.2", "high"))
        saved = self.read()
        self.assertEqual(saved["chat"]["tiers"]["main"], {"model": "opus", "effort": "medium"})
        self.assertEqual(saved["chat"]["tiers"]["task"], {"cli": "cursor", "model": "my-model.2", "effort": "high"})
        self.assertEqual((saved["text"], saved["chat"]["auto_notes"], saved["orchestrator"]),
                         ({"size": 12}, False, {"main": "claude"}))
        table = tiers.table(saved)
        self.assertEqual(table["main"], {"cli": "claude", "model": "opus", "effort": "medium"})
        self.assertEqual(table["topic"], {"cli": "claude", "model": "opus", "effort": "medium"})
        self.assertEqual(table["task"], {"cli": "cursor", "model": "my-model.2", "effort": "high"})
        self.assertEqual(table["subagent"], tiers.DEFAULTS["subagent"])

    def test_bad_values_save_nothing(self):
        before = self.path.read_text(encoding="utf-8")
        for tier, model, effort in (("main", "x; rm -rf", "low"), ("main", "opus", "insane"), ("main", "", "low"),
                                    ("throne", "opus", "low"), ("topic", 5, "low")):
            with self.subTest(tier=tier, model=model, effort=effort):
                self.assertFalse(tiers.save_tier(self.path, tier, model, effort))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_reset_drops_model_and_effort_and_keeps_the_cli(self):
        tiers.save_tier(self.path, "task", "sonnet", "low")
        self.assertTrue(tiers.reset_tier(self.path, "task"))
        self.assertEqual(self.read()["chat"]["tiers"]["task"], {"cli": "cursor"})
        tiers.save_tier(self.path, "topic", "opus", "low")
        tiers.reset_tier(self.path, "topic")
        self.assertEqual(tiers.table(self.read())["topic"], tiers.DEFAULTS["topic"])

    def test_sample_line_and_suggestions(self):
        rows = tiers.table(tiers.with_tier(CLAUDE_MAIN, "main", "opus", "medium"))
        self.assertEqual(tiers.sample("main", rows), "Main orchestrator: claude opus, medium effort")
        self.assertEqual(tiers.sample("main", tiers.table({})), "Main orchestrator: grok's own model")
        self.assertEqual(tiers.models("claude"), ("fable", "opus", "sonnet", "haiku"))
        self.assertEqual(tiers.models("bash"), ())

    def test_defaults_stay_as_they_are(self):
        self.assertEqual(tiers.DEFAULTS, {
            "main": {"cli": "claude", "model": "fable", "effort": "high"},
            "topic": {"cli": "claude", "model": "fable", "effort": "high"},
            "task": {"cli": "claude", "model": "opus", "effort": "medium"},
            "subagent": {"cli": "claude", "model": "haiku", "effort": "low"},
        })


class UpdateKeepsTest(unittest.TestCase):
    """The installed config.json lives in the install folder (``cli_avatars.paths``), which Update swaps."""

    MINE = {"orchestrator": {"main": "claude"},
            "chat": {"tiers": {"main": {"model": "opus", "effort": "medium"},
                               "topic": {"model": "opus", "effort": "medium"}}}}

    def _pair(self, root, mine, shipped=None):
        install, staging = root / "CLI Avatars", root / "CLI Avatars.staging"
        for folder, exe in ((install, "old"), (staging, "new")):
            (folder / "_internal").mkdir(parents=True)
            (folder / "cli-avatars.exe").write_text(exe, encoding="utf-8")
        (install / "_internal" / "config.json").write_text(json.dumps(mine), encoding="utf-8")
        if shipped is not None:
            (staging / "_internal" / "config.json").write_text(json.dumps(shipped), encoding="utf-8")
        return install, staging

    def _swap(self, install, staging, code=0):
        seen = []

        def boot(exe):
            seen.append(json.loads((exe.parent / "_internal" / "config.json").read_text(encoding="utf-8")))
            return code

        outcome = apply_swap(install, staging, exe_name="cli-avatars.exe", bootcheck=boot, relaunch=lambda exe: None,
                             attempts=2, pause_s=0)
        return outcome, seen

    def test_update_keeps_the_tiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, staging = self._pair(Path(tmp), self.MINE)
            outcome, seen = self._swap(install, staging)
            kept = json.loads((install / "_internal" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(outcome, "relaunched")
        self.assertEqual(kept, self.MINE)
        self.assertEqual(seen, [self.MINE])
        self.assertEqual(tiers.table(kept)["main"], {"cli": "claude", "model": "opus", "effort": "medium"})

    def test_user_values_win_and_only_missing_keys_get_defaults(self):
        shipped = {"chat": {"tiers": {"main": {"model": "fable", "effort": "high"}, "subagent": {"model": "haiku"}},
                            "auto_notes": True}, "animation": "smooth"}
        with tempfile.TemporaryDirectory() as tmp:
            install, staging = self._pair(Path(tmp), self.MINE, shipped)
            self._swap(install, staging)
            kept = json.loads((install / "_internal" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(kept["chat"]["tiers"]["main"], {"model": "opus", "effort": "medium"})
        self.assertEqual(kept["chat"]["tiers"]["topic"], {"model": "opus", "effort": "medium"})
        self.assertEqual(kept["chat"]["tiers"]["subagent"], {"model": "haiku"})
        self.assertEqual((kept["chat"]["auto_notes"], kept["animation"]), (True, "smooth"))

    def test_rolled_back_build_still_has_its_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, staging = self._pair(Path(tmp), self.MINE)
            outcome, _seen = self._swap(install, staging, code=1)
            kept = json.loads((install / "_internal" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual((outcome, kept), ("rolled_back", self.MINE))


class PhoneTiers(_Writes):
    def setUp(self):
        super().setUp()
        self.config = self.dir / "config.json"
        self.config.write_text(json.dumps(CLAUDE_MAIN), encoding="utf-8")
        self.live = {}
        tier_routes.set_target(self.config, lambda config: self.live.update(config=config))
        self.addCleanup(tier_routes.set_target, None, None)

    def test_rows_read_and_edit(self):
        status, body = self.request("/api/tiers")
        self.assertEqual((status, body["writes"], body["efforts"]), (200, True, list(tiers.EFFORTS)))
        main = body["tiers"][0]
        self.assertEqual((main["tier"], main["name"], main["where"], main["model"], main["effort"]),
                         ("main", "Main orchestrator", "throne room", "fable", "high"))
        self.assertEqual(main["suggest"], ["fable", "opus", "sonnet", "haiku"])
        self.assertEqual(main["sample"], "Main orchestrator: claude fable, high effort")
        status, body = self.request("/api/tiers/main", "POST", {"model": "opus", "effort": "medium"})
        self.assertEqual((status, body["tier"]["sample"]), (200, "Main orchestrator: claude opus, medium effort"))
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["chat"]["tiers"]["main"], {"model": "opus", "effort": "medium"})
        self.assertEqual(tiers.table(self.live["config"])["main"]["model"], "opus")
        status, body = self.request("/api/tiers/main", "POST", {"reset": True})
        self.assertEqual((status, body["tier"]["model"]), (200, "fable"))

    def test_bad_writes(self):
        for path, body in (("/api/tiers/main", {"model": "x y", "effort": "low"}),
                           ("/api/tiers/main", {"model": "opus"}), ("/api/tiers/main", {"reset": False}),
                           ("/api/tiers/throne", {"model": "opus", "effort": "low"})):
            with self.subTest(path=path, body=body):
                self.assertIn(self.request(path, "POST", body)[0], (400, 404))
        self.assertEqual(self.request("/api/tiers/main", "POST", {"model": "opus", "effort": "low"}, csrf=False)[0],
                         403)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")), CLAUDE_MAIN)

    def test_the_page_has_the_tier_rows(self):
        static = ROOT / "webui" / "static"
        html = (static / "index.html").read_text(encoding="utf-8")
        js = (static / "tier_settings.js").read_text(encoding="utf-8")
        for needle in ('id="tierRows"', 'src="/static/tier_settings.js"', 'href="/static/tier_settings.css"'):
            self.assertIn(needle, html)
        for needle in ('"/api/tiers"', "textContent", "reset"):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)


class PhoneTiersOff(_Writes):
    writes = False

    def test_reading_works_and_writing_is_off(self):
        status, body = self.request("/api/tiers")
        self.assertEqual((status, body["writes"], len(body["tiers"])), (200, False, 4))
        self.assertEqual(self.request("/api/tiers/main", "POST", {"model": "opus", "effort": "low"})[0], 405)


class Desktop(unittest.TestCase):
    def test_settings_rows_save_on_change_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            proc = subprocess.run([sys.executable, str(ROOT / "tests" / "_tier_settings_probe.py"), str(ROOT),
                                   str(data)], cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False)
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("one row per tier", "row shows name and where", "claude suggestions", "pick saves config.json",
                     "pick is live", "orchestrator note follows", "sample line follows", "door chip follows", "typed model saves",
                     "bad typed model saves nothing", "reset to default", "main row follows the orchestrator switch",
                     "no new toplevel"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
