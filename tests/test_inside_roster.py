"""AV.1 in the Dungeon: roster sizes on the rooms floor, the walk to the user and back, the mark."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_avatars.app import inside_roster, place_markers  # noqa: E402
from cli_avatars.app.av_roster import LOOKS, SUBAGENT, roster_frame  # noqa: E402
from cli_avatars.app.inside_roster import Hall, dress, wearing  # noqa: E402
from cli_avatars.app.needs_walk import beside, read_rooms  # noqa: E402
from cli_avatars.model.agent import AgentInfo  # noqa: E402
from cli_avatars.world.avatar import Avatar  # noqa: E402
from registry.facade import Registry  # noqa: E402
from sprite_loader import SpriteRegistry  # noqa: E402
from topics import join_topic, set_topic  # noqa: E402

SPRITES = ROOT / "Sprites"
SHEETS = {"ember_mage": 50, "caine": 48, "amongo": 40, "bubble": 48}


def _registry():
    registry = SpriteRegistry()
    for name, cell in SHEETS.items():
        registry.load(name, str(SPRITES / f"{name}.png"), frame_w=cell, scale=2.5, quiet=True)
    return registry


class FakePhotos:
    def __init__(self):
        self.made = {}

    def get(self, key, factory):
        if key not in self.made:
            self.made[key] = factory()
        return self.made[key]


class _Scene:
    def __init__(self, scale=2):
        self._rooms_painter = SimpleNamespace(_item=1, _photo=object(), _scale=scale)
        self.images = []

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def create_image(self, x, y, **kwargs):
        self.images.append((x, y, kwargs.get("tags")))
        return len(self.images)


class Sizes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = _registry()

    def _avatar(self, aid, source="claude", parent=None):
        agent = AgentInfo(aid, aid, source=source, parent_id=parent, skin="meowatar")
        return Avatar(agent, 800, 600, 0, registry=self.registry)

    def test_avatars_are_40_and_drawn_at_the_whole_rooms_scale(self):
        for aid, source in (("orch", "claude"), ("pip", "bot")):
            for scale in (1, 2, 3):
                with self.subTest(aid=aid, scale=scale):
                    av = self._avatar(aid, source)
                    photos, look = dress(av, FakePhotos(), scale, {"pip": 150})
                    self.assertEqual((av.aw, av.ah), (40 * scale, 40 * scale))
                    with wearing(av, look):
                        image = photos.get(av.photo_key(), av.sprite_image)
                    self.assertEqual(image.size, (av.aw, av.ah))

    def test_wearing_draws_the_roster_sheet_and_gives_the_agent_back(self):
        av = self._avatar("orch")
        real = av.agent
        _photos, look = dress(av, FakePhotos(), 2, {})
        with wearing(av, look):
            self.assertEqual(av.agent.skin, "caine")
            self.assertEqual(av.agent.agent_id, "orch")
        self.assertIs(av.agent, real)
        self.assertEqual(real.skin, "meowatar")

    def test_no_rooms_keeps_the_desktop_size(self):
        av = self._avatar("orch")
        desktop = (av.aw, av.ah)
        _photos, look = dress(av, None, 0, {})
        self.assertIsNone(look)
        self.assertEqual((av.aw, av.ah), desktop)

    def test_subagents_are_32_bubbles(self):
        look = LOOKS[SUBAGENT]
        with patch.object(place_markers, "REGISTRY", self.registry):
            photo = place_markers.bubble_photo(FakePhotos(), 2, 1)
        self.assertEqual(photo.size, (64, 64))
        frame = self.registry.get_image("bubble", "idle", 1)
        self.assertEqual(photo.tobytes(), roster_frame(frame, look, 2, False).tobytes())


def _book(agents, scene):
    inside = {a.agent_id: Avatar(a, 800, 600, 0, registry=None) for a in agents}
    app = SimpleNamespace(_inside=inside, _chat_directory=lambda: "unused",
                          dungeon=SimpleNamespace(_zoom=1, _pan=(0, 0)))
    return SimpleNamespace(app=app, _scene=lambda: scene)


class WalkInDungeon(unittest.TestCase):
    HOMES = {"moth": (100.0, 100.0), "orch": (400.0, 300.0)}

    def setUp(self):
        self.scene = _Scene(scale=1)
        agents = [AgentInfo("moth", "Moth", source="bot", project="vault"), AgentInfo("orch", "Orch")]
        self.book = _book(agents, self.scene)
        self.hall = Hall(self.book)
        self.hall.walker.speed = 400.0
        self.rooms = ([], [])

    def _frames(self, start, count):
        with patch.object(inside_roster, "read_rooms", lambda _d: self.rooms):
            for n in range(count):
                self.hall._read._ready = False
                spots = self.hall.walk(dict(self.HOMES), start + n * 0.1)
        return spots

    def test_a_blocked_card_walks_the_room_avatar_to_the_user(self):
        self.rooms = ([], [{"column": "blocked", "assignee": "moth", "project": "vault"}])
        goal = beside(self.hall.user_spot(), 0, inside_roster.STEP)
        self.assertEqual(self.hall.user_spot(), (400.0, 412.0))
        spots = self._frames(0.0, 3)
        self.assertNotEqual(spots["moth"], self.HOMES["moth"])
        self.assertEqual(spots["orch"], self.HOMES["orch"])
        spots = self._frames(0.3, 20)
        self.assertEqual(spots["moth"], goal)
        self.assertTrue(self.hall.walker.marked("moth"))

    def test_clearing_walks_it_back_home(self):
        self.rooms = ([{"id": "vault-room", "status": "waiting_on_user", "members": ["moth"]}], [])
        self._frames(0.0, 20)
        self.rooms = ([{"id": "vault-room", "status": "open", "members": ["moth"]}], [])
        spots = self._frames(2.0, 2)
        self.assertNotEqual(spots["moth"], self.HOMES["moth"])
        self.assertFalse(self.hall.walker.marked("moth"))
        spots = self._frames(2.2, 20)
        self.assertEqual(spots["moth"], self.HOMES["moth"])
        self.assertEqual(self.hall.walker.walking(), set())

    def test_the_mark_shows_only_while_needed(self):
        self.rooms = ([], [{"column": "blocked", "assignee": "moth", "project": "vault"}])
        self._frames(0.0, 2)
        with patch("cli_avatars.app.render.photos_for", return_value=FakePhotos()), \
                patch("bubbles.blocked_indicator", return_value="badge"):
            self.hall.paint_marks(self.scene)
            self.assertEqual(len(self.scene.images), 1)
            self.assertEqual(self.scene.images[0][2], ("inside-sub",))
            self.rooms = ([], [])
            self._frames(0.2, 1)
            self.hall.paint_marks(self.scene)
        self.assertEqual(len(self.scene.images), 1)

    def test_the_user_spot_grows_with_the_rooms_scale(self):
        self.scene._rooms_painter._scale = 2
        self.assertEqual(self.hall.user_spot(), (400.0, 524.0))

    def test_bot_hues_follow_the_bots_inside(self):
        self._frames(0.0, 1)
        self.assertEqual(set(self.hall.hues), {"moth"})


class ReadRooms(unittest.TestCase):
    def test_reads_waiting_topics_and_blocked_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            set_topic(directory, "vault-room", title="Vault", project="vault", status="waiting_on_user")
            join_topic(directory, "vault-room", "moth")
            reg = Registry(directory)
            stuck = reg.task_create("vault", "Open the vault", topic="vault-room")
            reg.task_move(stuck["id"], "doing")
            reg.task_move(stuck["id"], "blocked")
            reg.task_create("vault", "Map the vault", topic="vault-room")
            topics, cards = read_rooms(directory)
        self.assertEqual([(t["id"], t["status"], t["members"]) for t in topics],
                         [("vault-room", "waiting_on_user", ["moth"])])
        self.assertEqual([(c["title"], c["column"]) for c in cards], [("Open the vault", "blocked")])

    def test_a_missing_directory_reads_nothing(self):
        self.assertEqual(read_rooms(Path(tempfile.gettempdir()) / "av1-missing-dir"), ([], []))


if __name__ == "__main__":
    unittest.main()
