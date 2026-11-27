"""INSTALLDAY: zero-config first run, the save folder, missing-thing words, starter cards and Send that sends.

Made-up folders in a temp dir; a stub binary stands in for a CLI. Nothing starts a CLI.
"""

import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import first_run, onboarding, summon  # noqa: E402
from cli_avatars.model.room import load_binary_pin, load_room  # noqa: E402


def _stub(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + (".exe" if sys.platform == "win32" else ""))
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp)
        self.data = Path(self._tmp) / "data"
        self.data.mkdir()
        self.home = Path(self._tmp) / "home ñame"
        (self.home / "Documents").mkdir(parents=True)
        self.config = Path(self._tmp) / "config.json"
        self.bin = Path(self._tmp) / "bin"
        self._env = os.environ.get("CLI_AVATARS_DATA_DIR")
        os.environ["CLI_AVATARS_DATA_DIR"] = str(self.data)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._env is None:
            os.environ.pop("CLI_AVATARS_DATA_DIR", None)
        else:
            os.environ["CLI_AVATARS_DATA_DIR"] = self._env

    def which(self, *found):
        paths = {name: str(_stub(self.bin, name)) for name in found}
        return lambda name: paths.get(name)

    def run_first(self, *found):
        from cli_avatars.runner import cli_runner

        tools = SimpleNamespace(resolve=cli_runner.resolve_binary, confirm=cli_runner.confirm_binary,
                                rejected=cli_runner.CliRejected)
        return first_run.run(self.data, self.config, tools, which=self.which(*found), home=self.home, platform="linux")


class Paths(unittest.TestCase):
    def test_onedrive_documents_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "OneDrive - Made Up"
            (one / "Documents").mkdir(parents=True)
            env = {"USERPROFILE": str(Path(tmp) / "Usér Name"), "OneDrive": str(one)}
            self.assertEqual(first_run.documents_dir(env, platform="win32"), one / "Documents")

    def test_plain_documents_with_spaces_and_accents(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "José Ñandú"
            (home / "Documents").mkdir(parents=True)
            env = {"USERPROFILE": str(home)}
            self.assertEqual(first_run.default_save_dir(env, platform="win32"), home / "Documents" / "CLI Avatars")

    def test_no_documents_uses_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(first_run.documents_dir({}, home=Path(tmp), platform="linux"), Path(tmp))

    def test_save_dir_from_config_wins(self):
        self.assertEqual(first_run.save_dir({"files": {"dir": "/made/up/Notes vault"}}), Path("/made/up/Notes vault"))
        self.assertEqual(first_run.save_dir({"files": {"dir": "relative"}}, home=Path("/h"), platform="linux"),
                         Path("/h/CLI Avatars"))

    def test_folder_that_cannot_be_made_says_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "file"
            blocker.write_text("x")
            self.assertIn("Could not create the folder", first_run.ensure_dir(blocker / "CLI Avatars"))


class Messages(unittest.TestCase):
    def test_cli_missing_names_it_and_the_fix(self):
        text = first_run.cli_missing("claude")
        self.assertIn("Claude Code is not installed", text)
        self.assertIn("restart the app", text)
        self.assertIn("works without it", text)

    def test_git_missing_names_what_is_off_and_where_to_get_it(self):
        self.assertFalse(first_run.git_found(lambda _n: None))
        self.assertIn("https://git-scm.com/downloads", first_run.git_missing())
        self.assertIn("Update", first_run.git_missing())

    def test_pick_main(self):
        self.assertEqual(first_run.pick_main({"grok", "claude"}), "grok")
        self.assertEqual(first_run.pick_main({"claude"}), "claude")
        self.assertEqual(first_run.pick_main(set()), "grok")
        self.assertEqual(first_run.pick_main({"grok", "claude"}, "claude"), "claude")


class FirstRun(_Base):
    def test_fresh_install_sets_everything(self):
        notes = self.run_first("claude", "grok", "git")
        import json

        config = json.loads(self.config.read_text(encoding="utf-8"))
        folder = self.home / "Documents" / "CLI Avatars"
        self.assertTrue(folder.is_dir())
        self.assertEqual(config["files"]["dir"], str(folder))
        self.assertEqual(config["orchestrator"]["main"], "grok")
        self.assertIsNotNone(load_binary_pin(self.data, "claude"))
        self.assertIsNotNone(load_binary_pin(self.data, "grok"))
        topic = summon.remembered(self.data)
        self.assertTrue(topic)
        self.assertEqual(load_room(self.data, topic).working_dir, "")
        self.assertEqual(len(onboarding.steps(self.data)), len(onboarding.STEPS))
        self.assertTrue(first_run.done(self.data))
        self.assertFalse(any("not installed" in n for n in notes))

    def test_only_claude_makes_it_main(self):
        self.run_first("claude", "git")
        import json

        self.assertEqual(json.loads(self.config.read_text())["orchestrator"]["main"], "claude")

    def test_nothing_installed_still_opens_with_words(self):
        notes = self.run_first()
        self.assertTrue(any("Claude Code is not installed" in n for n in notes))
        self.assertTrue(any("Git is not installed" in n for n in notes))
        self.assertIsNone(load_binary_pin(self.data, "claude"))

    def test_user_values_win_and_second_start_does_nothing(self):
        vault = Path(self._tmp) / "Notes vault"
        self.config.write_text('{"files": {"dir": "%s"}, "orchestrator": {"main": "claude"}}' % vault.as_posix())
        self.run_first("claude", "grok", "git")
        import json

        config = json.loads(self.config.read_text())
        self.assertEqual(config["files"]["dir"], vault.as_posix())
        self.assertEqual(config["orchestrator"]["main"], "claude")
        self.assertTrue(vault.is_dir())
        self.assertEqual(self.run_first("claude"), [])


class Starter(_Base):
    def test_seeded_once_ticked_and_never_back(self):
        ids = onboarding.seed(self.data)
        self.assertEqual(len(ids), len(onboarding.STEPS))
        self.assertEqual(onboarding.seed(self.data), [])
        self.assertTrue(onboarding.tick(self.data, "chat"))
        self.assertFalse(onboarding.tick(self.data, "chat"))
        rows = {title: done for title, _b, done in onboarding.steps(self.data)}
        self.assertTrue(rows["First chat"])
        from board.store import LocalStore

        store = LocalStore(self.data)
        for card_id in ids:
            (store.root / onboarding.PROJECT / "cards" / f"{card_id}.json").unlink(missing_ok=True)
        self.assertEqual(onboarding.seed(self.data), [])
        self.assertFalse(onboarding.tick(self.data, "task"))

    def test_all_done_hides_the_guide(self):
        onboarding.seed(self.data)
        for key, _t, _b in onboarding.STEPS:
            onboarding.tick(self.data, key)
        self.assertEqual(onboarding.steps(self.data), [])

    def test_every_title_fits_the_board(self):
        from cli_avatars.app.throne_model import TITLE_CHARS

        for _key, title, body in onboarding.STEPS:
            self.assertLessEqual(len(title), TITLE_CHARS)
            self.assertTrue(body)


class SendSends(unittest.TestCase):
    """With no folder picked, Send uses the save folder and never opens a dialog; a found binary is used.

    The room pane imports Tk, so it runs in ``_installday_send_probe.py``."""

    def test_send_probe(self):
        import subprocess  # noqa: TID251  # the probe keeps Tk out of this process

        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLI_AVATARS_DATA_DIR=str(Path(tmp) / "data"), HOME=str(Path(tmp) / "home"))
            result = subprocess.run([sys.executable, str(ROOT / "tests" / "_installday_send_probe.py"), str(ROOT), tmp],
                                    capture_output=True, text=True, timeout=60, env=env)
        if result.returncode == 77:
            self.skipTest("no Tk")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok send_with_no_folder_uses_the_save_folder", result.stdout)
        self.assertIn("ok send_pins_a_binary_found_on_path", result.stdout)


class Bridge(_Base):
    def test_instructions_name_the_folders_and_the_answer_shape(self):
        from cli_avatars.app import bridge_setup

        folder = Path(self._tmp) / "Sync ñ" / "bridge"
        text = bridge_setup.instructions(folder)
        self.assertIn(str(folder / "outbox"), text)
        self.assertIn(str(folder / "inbox"), text)
        self.assertIn('"answer"', text)

    def test_bridge_check_writes_reads_back_and_cleans_up(self):
        from cli_avatars.app import bridge_setup

        folder = Path(self._tmp) / "bridge"
        ok, said = bridge_setup.test(folder)
        self.assertTrue(ok, said)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["inbox", "outbox"])

    def test_bridge_check_on_a_file_says_why(self):
        from cli_avatars.app import bridge_setup

        blocker = Path(self._tmp) / "not-a-folder"
        blocker.write_text("x")
        ok, said = bridge_setup.test(blocker)
        self.assertFalse(ok)
        self.assertIn("Pick another one", said)

    def test_git_row(self):
        from cli_avatars.app import setup_checks as sc

        self.assertEqual(sc.git_row(lambda _n: "/made/up/git").status, "ok")
        row = sc.git_row(lambda _n: None)
        self.assertEqual(row.status, "warn")
        self.assertTrue(row.optional)
        self.assertFalse(sc.needs_setup(row))


class Skins(unittest.TestCase):
    def _agent(self, aid, source="claude", parent=None, seen=0.0):
        return SimpleNamespace(agent_id=aid, source=source, parent_id=parent, last_seen=seen, name=aid)

    def tearDown(self):
        from cli_avatars.app import av_roster

        av_roster.set_main("")

    def test_main_is_caine_other_claude_is_michimaru_grok_is_amongo(self):
        from cli_avatars.app import av_roster

        agents = {"a": self._agent("a", seen=1), "b": self._agent("b", seen=2), "bot:x": self._agent("bot:x", "bot")}
        main = av_roster.main_id(agents, {"orchestrator": {"main": "grok"}})
        self.assertEqual(main, "b")
        av_roster.set_main(main, agents)
        self.assertEqual(av_roster.look_for(agents["b"], {}).skin, "caine")
        self.assertEqual(av_roster.look_for(agents["a"], {}).skin, "michimaru")
        self.assertEqual(av_roster.look_for(agents["bot:x"], {}).skin, "amongo")

    def test_a_grok_main_wears_caine(self):
        from cli_avatars.app import av_roster

        agents = {"a": self._agent("a", seen=5), "g": self._agent("g", "grok", seen=1)}
        av_roster.set_main(av_roster.main_id(agents, {"orchestrator": {"main": "grok"}}), agents)
        self.assertEqual(av_roster.look_for(agents["g"], {}).skin, "caine")
        self.assertEqual(av_roster.look_for(agents["a"], {}).skin, "michimaru")

    def test_amongo_is_70_percent_feet_on_the_floor_whole_pixels(self):
        from PIL import Image

        from cli_avatars.app import av_roster

        look = av_roster.LOOKS[av_roster.GROK]
        sheet = Image.open(ROOT / "Sprites" / "amongo.png").convert("RGBA")
        native = sheet.crop((0, 0, 40, 40))
        for scale in (1, 2, 3):
            out = av_roster.roster_frame(native, look, scale, False)
            self.assertEqual(out.size, (40 * scale, 40 * scale))
            l0, t0, r0, b0 = native.getbbox()
            l1, t1, r1, b1 = out.getbbox()
            self.assertEqual(b1, 40 * scale, "feet on the floor")
            self.assertAlmostEqual((b1 - t1) / ((b0 - t0) * scale), 0.7, delta=0.06)

    def test_michimaru_frame_is_padded_not_stretched(self):
        from PIL import Image

        from cli_avatars.app import av_roster

        look = av_roster.LOOKS[av_roster.CLAUDE]
        frame = Image.open(ROOT / "Sprites" / "Michimaru.png").convert("RGBA").crop((0, 0, 40, 51))
        out = av_roster.roster_frame(frame, look, 1, False)
        self.assertEqual(out.size, (48, 48))
        l0, t0, r0, b0 = frame.getbbox()
        l1, t1, r1, b1 = out.getbbox()
        self.assertEqual(r1 - l1, r0 - l0, "same width: padded, not stretched")

    def test_phone_sprites_for_main_and_claude(self):
        from webui import scene

        for key, w in (("orchestrator", 40), ("claude", 48), ("grok-120", 40)):
            png, fw, fh, frames = scene.sprite_png(key)
            self.assertEqual((fw, fh), (w, w), key)
            self.assertGreaterEqual(frames, 1)
        self.assertEqual(scene.sprite_key({"kind": "orchestrator", "look": "claude"}), "claude")

    def test_new_bots_default_to_amongo(self):
        from bots import roster

        self.assertEqual(roster.DEFAULT_SKIN, "amongo")


if __name__ == "__main__":
    unittest.main()
