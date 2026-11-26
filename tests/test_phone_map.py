"""PHONEMAP: the phone's Dungeon map: bots carry their CLI and state; mapnav.js does the hit-test, clamp, integer
snap, saved view, jump list and active bots; phonemap.js shows the sheets read-only."""

import json
import shutil
import subprocess  # noqa: TID251  # mapnav.js runs in a node child, fixed argv
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_avatars.app.session_rooms import MAIN, SIMPLE, SessionRooms  # noqa: E402
from test_phone_writes import _Writes  # noqa: E402
from topics import set_topic  # noqa: E402
from webui import live  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"
NODE = shutil.which("node")


class PhoneMapScene(_Writes):
    writes = False

    def setUp(self):
        super().setUp()
        rooms = SessionRooms(self.dir / "ui" / "session_rooms.json")
        for topic, kind, cli in (("moon-forge", MAIN, "claude"), ("glass-orchard", SIMPLE, "grok")):
            set_topic(self.dir, topic, title=topic, project="lantern", status="open")
            rooms.open(kind, cli, topic)
        self.rows = [
            {"id": "mf01", "kind": "orchestrator", "name": "Quill", "room": "moon-forge", "feet": (3.0, -9.0),
             "face": 1, "walk": False},
            {"id": "go01", "kind": "grok", "name": "Owl", "room": "glass-orchard", "feet": (4.0, -9.0),
             "face": 1, "walk": False},
            {"id": "__you__", "kind": "user", "name": "You", "room": "moon-forge", "feet": (5.0, -8.0), "face": 1,
             "walk": False}]
        self.sessions = [{"agent_id": "mf01", "name": "Quill", "source": "claude", "project": "moon-forge",
                          "status": "busy"}]
        live.set_roster(lambda _lay, _now: self.rows)
        live.set_sessions(lambda: self.sessions)

    def tearDown(self):
        live.set_roster(None)
        live.set_sessions(None)
        super().tearDown()

    def test_bots_carry_cli_and_state_from_the_live_sessions(self):
        status, body = self.request("/api/scene")
        self.assertEqual(status, 200)
        by = {a["name"]: a for a in body["avatars"]}
        self.assertEqual((by["Quill"]["cli"], by["Quill"]["state"]), ("claude", "busy"))
        self.assertEqual((by["Owl"]["cli"], by["Owl"]["state"]), ("grok", ""))
        self.assertNotIn("cli", by["You"])
        self.assertNotIn("mf01", json.dumps(body["avatars"]))

    def test_odd_session_values_stay_out(self):
        self.sessions[0].update(status="<script>", source="rm -rf")
        by = {a["name"]: a for a in self.request("/api/scene")[1]["avatars"]}
        self.assertEqual((by["Quill"]["cli"], by["Quill"]["state"]), ("", "idle"))

    def test_page_loads_the_map_scripts_read_only(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for name in ("mapnav.js", "phonemap.js", "phonemap.css"):
            self.assertIn("/static/" + name, html)
            self.assertEqual(self.request("/static/" + name)[0], 200)
        js = (STATIC / "phonemap.js").read_text(encoding="utf-8") + (STATIC / "mapnav.js").read_text(encoding="utf-8")
        for word in ("POST", "postJSON", "XMLHttpRequest", "innerHTML"):
            self.assertNotIn(word, js)

    def test_task_view_toggle_keeps_the_map_view(self):
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('state.view = view;', app)
        self.assertNotIn('state.view !== "board"', app)


@unittest.skipUnless(NODE, "node not installed")
class MapNavMaths(unittest.TestCase):
    """mapnav.js run under node on made-up geometry."""

    def run_js(self, body: str):
        code = f"const N = require({json.dumps(str(STATIC / 'mapnav.js'))});\n" \
               f"process.stdout.write(JSON.stringify((() => {{ {body} }})()));"
        out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=20, check=True)
        return json.loads(out.stdout)

    SCENE = """const scene = {map: {w: 800, h: 400},
      rooms: [{name: "Apothecary", title: "Apothecary", kind: "apothecary", poly: [[400,100],[600,200],[400,300],[200,200]], box: [200,52,400,248]},
              {name: "moon-forge", title: "Moon forge", kind: "main", poly: [[650,250],[750,300],[650,350],[550,300]], box: [550,202,200,148]}],
      sprites: {orchestrator: {w: 32, h: 32, feet: 0.08}},
      boss: {pit_poly: [[100,300],[150,325],[100,350],[50,325]], crypt: {poly: [[100,20],[150,45],[100,70],[50,45]]}}};"""

    def test_an_avatar_wins_over_the_room_under_it(self):
        found = self.run_js(self.SCENE + """
          const spots = [{a: {id: "x", kind: "orchestrator", sprite: "orchestrator", name: "Quill"}, at: [400, 200]}];
          return [N.hit(scene, spots, 400, 190), N.hit(scene, spots, 450, 220), N.hit(scene, spots, 10, 390)];""")
        self.assertEqual(found[0]["kind"], "avatar")
        self.assertEqual(found[0]["a"]["name"], "Quill")
        self.assertEqual((found[1]["kind"], found[1]["room"]["name"]), ("room", "Apothecary"))
        self.assertIsNone(found[2])

    def test_you_and_couriers_are_not_bots_to_tap(self):
        found = self.run_js(self.SCENE + """
          const spots = [{a: {id: "c", kind: "courier", sprite: "orchestrator"}, at: [400, 200]}];
          return N.hit(scene, spots, 400, 190);""")
        self.assertEqual(found["kind"], "room")

    def test_clamp_keeps_the_view_centre_over_the_map(self):
        v = self.run_js(self.SCENE + "return N.clamp({s: 2, x: 5000, y: -5000}, scene.map, 400, 300, 0.25, 8);")
        cx, cy = (200 - v["x"]) / v["s"], (150 - v["y"]) / v["s"]
        self.assertTrue(0 <= cx <= 800 and 0 <= cy <= 400, v)
        v = self.run_js(self.SCENE + "return N.clamp({s: 50, x: 0, y: 0}, scene.map, 400, 300, 0.25, 8);")
        self.assertEqual(v["s"], 8)

    def test_scale_snaps_to_whole_device_pixels(self):
        found = self.run_js("return [N.snap(0.9, 3), N.snap(1.4, 2), N.snap(0.3, 2), N.fitScale(0.43, 3)];")
        self.assertAlmostEqual(found[0] * 3, 3)
        self.assertAlmostEqual(found[1] * 2, 3)
        self.assertAlmostEqual(found[2], 0.3)
        self.assertAlmostEqual(found[3] * 3, 1)

    def test_saved_view_comes_back_for_the_same_map_only(self):
        found = self.run_js(self.SCENE + """
          const saved = N.save({s: 2, x: -300, y: -100}, scene.map, 400, 300);
          return [N.load(JSON.parse(JSON.stringify(saved)), scene.map, 400, 300),
                  N.load(saved, {w: 900, h: 400}, 400, 300), N.load("junk", scene.map, 400, 300)];""")
        self.assertEqual(found[0], {"s": 2, "x": -300, "y": -100})
        self.assertIsNone(found[1])
        self.assertIsNone(found[2])

    def test_jump_list_has_every_room_and_the_boss_rooms(self):
        found = self.run_js(self.SCENE + "return N.places(scene).map((p) => [p.title, p.kind, p.box.length]);")
        self.assertEqual([p[0] for p in found], ["Apothecary", "Moon forge", "Oni Pit", "Crypt"])
        self.assertTrue(all(p[2] == 4 for p in found))

    def test_active_bots_run_first_without_you_or_couriers(self):
        found = self.run_js("""return N.bots([{id: "1", kind: "user", name: "You"}, {id: "2", kind: "orchestrator", name: "Bram", state: "idle"},
          {id: "3", kind: "grok", name: "Ada", state: "busy"}, {id: "4", kind: "courier", name: ""},
          {id: "5", kind: "subagent", name: "Cy", state: "thinking"}]).map((a) => [a.name, N.running(a)]);""")
        self.assertEqual(found, [["Ada", True], ["Cy", True], ["Bram", False]])


if __name__ == "__main__":
    unittest.main()
