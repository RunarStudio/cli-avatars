"""STANDUP desktop: the throne room show (horn, gather, one bubble each, return; next, skip, replay), the pixel
bubble, the gather and blip cues, and the Throne tab in an off-screen Dungeon (Tk runs in a child process).
"""

import subprocess  # noqa: TID251  # the Tk tab runs in a child, like test_mailroom_desktop
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_standup import seed  # noqa: E402

from cli_avatars.app import standup_show as ss  # noqa: E402
from cli_avatars.app import throne_model as tm  # noqa: E402


def entries(n: int, stuck=()) -> list[dict]:
    return [{"agent": f"claude:{i:08x}", "name": f"Agent{i}", "card": None, "title": f"Task {i}",
             "done": "a", "next": "b", "stuck": "why" if i in stuck else "", "line": f"line {i}",
             "tone": "stuck" if i in stuck else "ok"} for i in range(n)]


class Timeline(unittest.TestCase):
    def test_horn_gather_talk_return_done(self):
        show = ss.Show(entries(3), start=100.0)
        self.assertEqual(show.frame(100.0).phase, "horn")
        self.assertEqual(show.frame(100.0 + ss.HORN_S + 0.1).phase, "gather")
        talk = 100.0 + ss.HORN_S + ss.WALK_S + 0.1
        self.assertEqual((show.frame(talk).phase, show.frame(talk).speaker), ("talk", 0))
        self.assertEqual(show.frame(talk + ss.LINE_S).speaker, 1)
        end = show.frame(talk + 3 * ss.LINE_S)
        self.assertEqual(end.phase, "return")
        self.assertTrue(show.frame(talk + 3 * ss.LINE_S + ss.WALK_S + 0.1).phase == "done")
        self.assertTrue(show.over(talk + 3 * ss.LINE_S + ss.WALK_S + 0.1))

    def test_a_stuck_line_stays_longer(self):
        show = ss.Show(entries(2, stuck={0}), start=0.0)
        talk = ss.HORN_S + ss.WALK_S
        self.assertEqual(show.frame(talk + ss.LINE_S + 0.1).speaker, 0)
        self.assertEqual(show.frame(talk + ss.STUCK_S + 0.1).speaker, 1)

    def test_next_skip_replay(self):
        show = ss.Show(entries(3), start=0.0)
        talk = ss.HORN_S + ss.WALK_S + 0.1
        show.next(talk)
        self.assertEqual(show.frame(talk).speaker, 1)
        show.next(talk)
        show.next(talk)
        self.assertEqual(show.frame(talk).phase, "return")
        show.replay(talk)
        self.assertEqual(show.frame(talk).phase, "horn")
        show.skip(talk + 0.5)
        self.assertEqual(show.frame(talk + 0.6).phase, "return")
        show.next(talk + 0.6)
        self.assertEqual(show.frame(talk + 0.6).phase, "return")

    def test_next_during_horn_or_gather_jumps_to_the_first_line(self):
        show = ss.Show(entries(2), start=0.0)
        show.next(0.5)
        frame = show.frame(0.6)
        self.assertEqual((frame.phase, frame.speaker), ("talk", 0))
        self.assertEqual(frame.walk, 1.0)

    def test_cues_once_each(self):
        show = ss.Show(entries(2), start=0.0)
        self.assertEqual(show.cues(0.0), ["gather"])
        self.assertEqual(show.cues(0.5), [])
        talk = ss.HORN_S + ss.WALK_S
        self.assertEqual(show.cues(talk + 0.1), ["blip"])
        self.assertEqual(show.cues(talk + ss.LINE_S + 0.1), ["blip"])
        self.assertEqual(show.cues(talk + 10 * ss.LINE_S), [])

    def test_agents_walk_from_the_door_to_their_spots_and_back(self):
        show = ss.Show(entries(2), start=0.0)
        lord = tm.Actor("claude:0a0b0c0d", "Orrin")
        actors = {e["agent"]: tm.Actor(e["agent"], e["name"]) for e in show.entries}
        door = ss.route(0)[0]
        at_horn = ss.seat(show.frame(0.1), lord, show.entries, actors)
        self.assertEqual([p.actor.id for p in at_horn.placed], [lord.id])
        mid = ss.seat(show.frame(ss.HORN_S + 0.01), lord, show.entries, actors)
        first = next(p for p in mid.placed if p.actor.id == show.entries[0]["agent"])
        self.assertAlmostEqual(first.u, door[0], delta=0.5)
        self.assertAlmostEqual(first.v, door[1], delta=0.5)
        talk = ss.seat(show.frame(ss.HORN_S + ss.WALK_S + 0.1), lord, show.entries, actors)
        spots = [(p.u, p.v) for p in talk.placed[1:]]
        self.assertEqual(spots, [ss.spot(0), ss.spot(1)])
        self.assertEqual((talk.placed[0].u, talk.placed[0].v), tm.THRONE_SEAT[:2])

    def test_spots_are_on_the_hall_floor_and_apart(self):
        seen = [ss.spot(i) for i in range(ss.MAX_SPOTS)]
        self.assertEqual(len(set(seen)), ss.MAX_SPOTS)
        for u, v in seen:
            self.assertTrue(2.0 < u < tm.HALL[0] - 0.5 and 0.8 < v < tm.HALL[1] - 0.8, (u, v))

    def test_more_than_the_spots_wait_at_the_door(self):
        show = ss.Show(entries(ss.MAX_SPOTS + 3), start=0.0)
        actors = {e["agent"]: tm.Actor(e["agent"], e["name"]) for e in show.entries}
        seating = ss.seat(show.frame(ss.HORN_S + ss.WALK_S + 0.1), None, show.entries, actors)
        self.assertEqual((len(seating.placed), seating.more), (ss.MAX_SPOTS, 3))

    def test_the_lord_speaks_from_the_throne(self):
        rows = entries(2)
        lord = tm.Actor(rows[1]["agent"], "Orrin")
        show = ss.Show(rows, start=0.0)
        actors = {e["agent"]: tm.Actor(e["agent"], e["name"]) for e in rows}
        seating = ss.seat(show.frame(ss.HORN_S + ss.WALK_S + 0.1), lord, rows, actors)
        self.assertEqual([p.actor.id for p in seating.placed], [lord.id, rows[0]["agent"]])
        self.assertEqual(ss.speaker_spot(1, rows, lord), tm.THRONE_SEAT[:2])


class Art(unittest.TestCase):
    def test_bubble_is_pixel_art_and_stuck_is_wax_red(self):
        from cli_avatars.app import standup_art

        ok = standup_art.bubble("ASH", "done: hinges oiled · next: paint the gate", "ok")
        stuck = standup_art.bubble("BIRCH", "done: - · stuck: waiting on the shears", "stuck")
        self.assertEqual(ok.mode, "RGBA")
        self.assertLessEqual(ok.width, standup_art.MAX_W)
        self.assertGreater(len({tuple(px) for px in np.asarray(ok).reshape(-1, 4)}), 3)

        def reds(img):
            r, g, b, a = np.asarray(img).astype(int).transpose(2, 0, 1)
            return int(((a > 0) & (r > 150) & (g < 80) & (b < 80)).sum())

        self.assertGreater(reds(stuck), reds(ok))

    def test_long_lines_wrap_inside_the_bubble(self):
        from cli_avatars.app import standup_art

        short = standup_art.bubble("ASH", "done: a", "ok")
        long = standup_art.bubble("ASH", "done: " + "word " * 60, "ok")
        self.assertGreater(long.height, short.height)
        self.assertLessEqual(long.width, standup_art.MAX_W)
        self.assertLessEqual(len(standup_art.wrap("word " * 200)), standup_art.MAX_LINES)


class Cues(unittest.TestCase):
    def test_gather_and_blip_are_their_own_short_wavs(self):
        from cli_avatars.app import cues

        gather, blip = cues.wav("gather"), cues.wav("blip")
        self.assertEqual((gather[:4], blip[:4]), (b"RIFF", b"RIFF"))
        self.assertNotEqual(gather, blip)
        self.assertNotIn(gather, (cues.wav("arrive"), cues.wav("decide"), cues.wav("letter")))
        self.assertLess(len(blip), cues.RATE * 2 * 0.3)
        self.assertLess(len(gather), cues.RATE * 2 * 2.0)
        self.assertEqual(blip, cues.wav.__wrapped__("blip"))


class Tab(unittest.TestCase):
    def test_standup_in_the_throne_tab_off_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed(Path(tmp))
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tests" / "_standup_probe.py"), str(ROOT), tmp],
                cwd=ROOT, capture_output=True, text=True, timeout=120, shell=False,
            )
        if proc.returncode == 77:
            self.skipTest("tkinter has no display")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("not before the hour", "held while focused", "runs after focus", "throne tab opens",
                     "gather cue", "agents gather", "bubble shown", "space next", "blip per line", "stuck bubble",
                     "s skips", "r replays", "u runs again", "pinned on the cards", "not twice a day",
                     "silent while focused", "no new toplevel", "no callback errors"):
            self.assertIn(f"ok {name}", proc.stdout)


if __name__ == "__main__":
    unittest.main()
