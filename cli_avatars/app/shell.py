"""Overlay shell: Tk root, canvas, scanner, terrain, and the controllers.

Shared lists (avatars, sub-avatars, bursts, the drag) stay on this object.
Controllers read them here. They do not keep copies.

CLICK-THROUGH: after the root exists, Win32 click-through is wired from
``cli_avatars.desktop``. Not from the tick. See ``docs/architecture.md``.
"""

# DPI awareness runs at import, before tkinter and before any tk.Tk().
import cli_avatars.desktop.capabilities  # noqa: F401  # isort: skip
import random
import threading
import tkinter as tk
from typing import Optional

from bundle_paths import asset_path
from cli_avatars.app.bootcheck import start_bootcheck
from cli_avatars.app.bubbles_view import (
    BubblesView,
    _draw_blocked_marks,
    _draw_decision_bubbles,
    _draw_talk_bubbles,
)
from cli_avatars.app.chat import ChatController
from cli_avatars.app.config_screen import ConfigScreen
from cli_avatars.app.dungeon_window import DungeonWindow
from cli_avatars.app.hud_window import HudWindow
from cli_avatars.app.input import InputController
from cli_avatars.app.overlays import OverlayBoard, read_monitors
from cli_avatars.app.places import PlaceBook
from cli_avatars.app.pool import PoolController
from cli_avatars.app.portal_view import PortalView, _draw_portal
from cli_avatars.app.render import RenderController
from cli_avatars.app.render import color_for as avatar_color
from cli_avatars.app.rooms_panel import RoomsPanel
from cli_avatars.app.skin_picker import PICK, PICK_ANIMS, PICK_FRAME_MS, SkinPicker
from cli_avatars.app.subagents import SubagentController
from cli_avatars.app.tick import TickLoop
from cli_avatars.desktop.capabilities import desktop_escape_available
from cli_avatars.desktop.focus import focus_linked_console
from cli_avatars.desktop.settings import desktop_settings
from cli_avatars.desktop.tray import setup_tray
from cli_avatars.paths import CONFIG_PATH, images_dir
from cli_avatars.sprites.registry import REGISTRY, load_sprites
from cli_avatars.tuning import TUNING
from cli_avatars.world.scanner import SessionScanner
from cli_avatars.world.terrain import WindowTerrain
from portal import PortalPlayer
from rooms import load_config, rooms_from_config
from routing import PointerGesture


class OverlayApp:
    TITLE = "Dungeon"
    PICK = PICK
    PICK_ANIMS = PICK_ANIMS
    PICK_FRAME_MS = PICK_FRAME_MS

    def _ctrl(self, name, factory):
        """Controller built in ``__init__``, or on first use from ``__new__``."""
        ctrl = getattr(self, name, None)
        if ctrl is None:
            ctrl = factory(self)
            setattr(self, name, ctrl)
        return ctrl

    def __init__(self):
        self._config_path = CONFIG_PATH
        self.config = load_config(self._config_path)
        self.desktop = desktop_settings(self.config)
        self._subskin_rng = random.Random()
        self._rooms_shown = rooms_from_config(self.config)
        self._rooms_win = None
        self._rooms_btn = None
        self._rooms_sig = None
        self._rooms_thumbs = {}
        self._rooms_warns = {}
        self._rooms_drag = None
        self._chat_shown = False
        self._chat_win = None
        self._chat_btn = None
        self._chat_window = None
        self._decision_count = 0
        self._topics_stamp = None
        self._gesture = PointerGesture()
        self._press_av = None
        self.root = tk.Tk()
        self.root.title(self.TITLE)
        _ico = asset_path("Caine_Icon.ico")
        if not _ico.exists():
            _ico = images_dir() / "Caine_Icon.ico"
        if _ico.exists():
            try:
                self.root.wm_iconbitmap(str(_ico))
            except Exception:
                pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.sw, self.sh = sw, sh
        # The root is the Dungeon. Overlay canvases are created per monitor.
        self.canvas = None

        self.scanner = SessionScanner()
        self.scanner._grok_config = self.config
        self.terrain = WindowTerrain(self.TITLE, (0, 0, sw, sh))
        self._last_win_pos: dict[int, tuple] = {}
        self.avatars: dict = {}
        self._inside: dict = {}
        self.sub_avatars: dict = {}   # parent_id → [sub Avatar, …]
        self._lingering_subs: list = []         # task-done subs waiting to float away
        self._dying_subs: list = []             # closing subchat, dying row then gone
        self._dismissed_subs: dict = {}         # parent_id → manually dismissed count
        self._cidx = 0
        self._picker = None
        self._bursts: list = []
        self._glitches: list = []

        # Avatar drag state
        self._drag_av = None
        self._drag_off: tuple = (0, 0)
        self._drag_prev: tuple = (0, 0)

        self._config_win = None

        # HUD status window — separate, not topmost, draggable
        self._hud_win = None
        self._hud_drag_origin: Optional[tuple] = None
        self._bubble_icon_photo = None
        self._bubble_icon_id = None
        self._tray = None
        self._portal = PortalPlayer()
        self._portal_cache = {}

        self.pool = PoolController(self)
        self.subagents = SubagentController(self)
        self.render = RenderController(self)
        self.portal = PortalView(self)
        self.bubbles = BubblesView(self)
        self.pointer = InputController(self)
        self.hud = HudWindow(self)
        self.rooms = RoomsPanel(self)
        self.chat = ChatController(self)
        self.skin_picker = SkinPicker(self)
        self.config_screen = ConfigScreen(self)
        self.tick_loop = TickLoop(self)

        self.desktop_escape = desktop_escape_available()
        self.dungeon = DungeonWindow(self)
        self.dungeon.build()
        self.overlays = OverlayBoard(self)
        found = read_monitors()
        try:
            self.overlays.sync(found, self.desktop)
            screen, monitors = self.overlays.screen((0, 0, self.sw, self.sh))
            self.terrain.set_world(screen, monitors)
            self.terrain.note_monitors(found, self.desktop.monitor_poll_s)
            self.dungeon.place(found)
        except Exception as exc:
            print(f"[WARN] Monitor layout: {exc}")
            try:
                self.overlays._enter_legacy()
            except Exception:
                pass
            self.dungeon.place([])

        self.places = PlaceBook(self)
        self.places.attach()
        try:
            self.dungeon._door_btn.config(text=f"Door: {self.places.door()}")
        except Exception:
            pass

        threading.Thread(target=self.scanner.loop, daemon=True).start()
        threading.Thread(target=self.terrain.loop, daemon=True).start()

        # Load sprites and set up UI in background so window appears immediately
        threading.Thread(target=self._deferred_init, daemon=True).start()
        try:
            start_bootcheck(self)
        except Exception:
            print("[WARN] Boot check did not start")
        self._tick()

    def _deferred_init(self):
        if REGISTRY:
            load_sprites(REGISTRY)
        self.root.after(0, self._load_bubble_icon)
        self.root.after(0, self._create_hud_win)
        self.root.after(0, self._setup_tray)

    def _tick(self):
        self.tick_loop.step()

    def _quit(self):
        places = getattr(self, "places", None)
        if places is not None:
            try:
                places.save_now()
            except Exception:
                pass
        dungeon = getattr(self, "dungeon", None)
        if dungeon is not None:
            try:
                dungeon.save_now()
            except Exception:
                pass
        events = getattr(getattr(self, "scanner", None), "_events", None)
        if events is not None:
            events.close()
        if getattr(self, "_tray", None):
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.quit()

    def run(self) -> None:
        print(f"[Dungeon v0.4] overlay {self.sw}x{self.sh} @ {TUNING.overlay_fps}fps")
        print("[Dungeon] Close the window to quit. ESC closes a dock or cancels a drag.")
        self.root.mainloop()

    # Pool / spring. Names stay so a bare ``OverlayApp.__new__`` still runs them.
    def _refresh_activity(self, av):
        return self._ctrl("pool", PoolController)._refresh_activity(av)

    def _meeting_stage(self, floors, floor_hwnds):
        return self._ctrl("pool", PoolController)._meeting_stage(floors, floor_hwnds)

    def color_for(self, av: object) -> str:
        return avatar_color(av)

    def _drive_subagent(self, sv, parent_av, floors, walls, dt=1.0):
        return self._ctrl("subagents", SubagentController)._drive_subagent(
            sv, parent_av, floors, walls, dt)

    def _begin_dying(self, sv, now=None):
        return self._ctrl("subagents", SubagentController)._begin_dying(sv, now)

    def _release_finished_dying(self, now=None):
        return self._ctrl("subagents", SubagentController)._release_finished_dying(now=now)

    def _apply_spring(self, sv, parent_av, dt=1.0):
        return self._ctrl("subagents", SubagentController)._apply_spring(sv, parent_av, dt)

    def _apply_fly_spring(self, sv, parent_av, dt=1.0):
        return self._ctrl("subagents", SubagentController)._apply_fly_spring(sv, parent_av, dt)

    def _subagent_skin_pool(self):
        return self._ctrl("subagents", SubagentController)._subagent_skin_pool()

    def _leash_px(self):
        return self._ctrl("subagents", SubagentController)._leash_px()

    def _constrain_leash(self, sv, parent_av):
        return self._ctrl("subagents", SubagentController)._constrain_leash(sv, parent_av)

    def _draw_elastic(self, parent_av, sv, shrink=1.0):
        return self._ctrl("render", RenderController).draw_elastic(parent_av, sv, shrink)

    # HUD, tray, rooms, chat.
    def _load_bubble_icon(self):
        return self._ctrl("hud", HudWindow)._load_bubble_icon()

    def _bring_all_to_front(self):
        return self._ctrl("hud", HudWindow)._bring_all_to_front()

    def _setup_tray(self):
        return setup_tray(self)

    def _show_hud_win(self):
        return self._ctrl("hud", HudWindow)._show_hud_win()

    def _create_hud_win(self):
        return self._ctrl("hud", HudWindow)._create_hud_win()

    def _paint_hud_rows(self, rows):
        return self._ctrl("hud", HudWindow)._paint_hud_rows(rows)

    def _update_hud_win(self, agents):
        return self._ctrl("hud", HudWindow)._update_hud_win(agents)

    def _draw_portal(self, floors, floor_hwnds):
        return _draw_portal(self, floors, floor_hwnds)

    def _draw_talk_bubbles(self):
        return _draw_talk_bubbles(self)

    def _draw_decision_bubbles(self):
        return _draw_decision_bubbles(self)

    def _draw_blocked_marks(self):
        return _draw_blocked_marks(self)

    def _remember_rooms(self):
        return self._ctrl("rooms", RoomsPanel)._remember_rooms()

    def _paint_rooms_button(self):
        return self._ctrl("rooms", RoomsPanel)._paint_rooms_button()

    def _toggle_rooms(self):
        return self._ctrl("rooms", RoomsPanel)._toggle_rooms()

    def _close_rooms(self):
        return self._ctrl("rooms", RoomsPanel)._close_rooms()

    def _open_rooms_win(self):
        return self._ctrl("rooms", RoomsPanel)._open_rooms_win()

    def _rooms_records(self):
        return self._ctrl("rooms", RoomsPanel)._rooms_records()

    def _scroll_rooms(self, event):
        return self._ctrl("rooms", RoomsPanel)._scroll_rooms(event)

    def _bind_rooms_scroll(self, widget):
        return self._ctrl("rooms", RoomsPanel)._bind_rooms_scroll(widget)

    def _room_thumb(self, skin, dimmed):
        return self._ctrl("rooms", RoomsPanel)._room_thumb(skin, dimmed)

    def _room_warn(self, dimmed):
        return self._ctrl("rooms", RoomsPanel)._room_warn(dimmed)

    def _build_rooms_win(self):
        return self._ctrl("rooms", RoomsPanel)._build_rooms_win()

    def _update_rooms_win(self, force=False):
        return self._ctrl("rooms", RoomsPanel)._update_rooms_win(force)

    def _topic_rows(self):
        return self._ctrl("rooms", RoomsPanel)._topic_rows()

    def _sync_topics(self, force):
        return self._ctrl("rooms", RoomsPanel)._sync_topics(force)

    def _render_topic_groups(self, groups, cards, counts):
        return self._ctrl("rooms", RoomsPanel)._render_topic_groups(groups, cards, counts)

    def _render_topic_card(self, parent, topic, decisions):
        return self._ctrl("rooms", RoomsPanel)._render_topic_card(parent, topic, decisions)

    def _bind_topic_click(self, widget, topic_id):
        return self._ctrl("rooms", RoomsPanel)._bind_topic_click(widget, topic_id)

    def _select_topic(self, topic_id):
        return self._ctrl("rooms", RoomsPanel)._select_topic(topic_id)

    def _member_face(self, agent_id):
        return self._ctrl("rooms", RoomsPanel)._member_face(agent_id)

    def _live_agent(self, agent_id):
        return self._ctrl("rooms", RoomsPanel)._live_agent(agent_id)

    def _render_orchestrator_dot(self, parent, card):
        return self._ctrl("rooms", RoomsPanel)._render_orchestrator_dot(parent, card)

    def _chat_directory(self):
        return self._ctrl("chat", ChatController)._chat_directory()

    def _remember_chat_box(self, box):
        return self._ctrl("chat", ChatController)._remember_chat_box(box)

    def _ensure_chat_window(self):
        return self._ctrl("chat", ChatController)._ensure_chat_window()

    def _show_chat(self, topic_id=None, address_id=None):
        return self._ctrl("chat", ChatController)._show_chat(topic_id, address_id)

    def _paint_chat_button(self):
        return self._ctrl("chat", ChatController)._paint_chat_button()

    def _toggle_chat(self):
        return self._ctrl("chat", ChatController)._toggle_chat()

    def _close_chat(self):
        return self._ctrl("chat", ChatController)._close_chat()

    def _update_chat_win(self, force=False):
        return self._ctrl("chat", ChatController)._update_chat_win(force)

    def _open_chat_for_avatar(self, avatar):
        return self._ctrl("chat", ChatController)._open_chat_for_avatar(avatar)

    # Pointer.
    def _avatar_at(self, x, y):
        return self._ctrl("pointer", InputController)._avatar_at(x, y)

    def _on_left_press(self, event):
        return self._ctrl("pointer", InputController).on_left_press(event)

    def _on_left_drag(self, event):
        return self._ctrl("pointer", InputController).on_left_drag(event)

    def _on_left_release(self, event):
        return self._ctrl("pointer", InputController).on_left_release(event)

    def _on_double_click(self, event):
        return self._ctrl("pointer", InputController).on_double_click(event)

    def _on_right_click(self, event):
        return self._ctrl("pointer", InputController).on_right_click(event)

    def _door_label(self, _item=None) -> str:
        book = getattr(self, "places", None)
        door = book.door() if book is not None and hasattr(book, "door") else "open"
        return f"Door: {door}"

    def _toggle_door(self) -> None:
        book = getattr(self, "places", None)
        if book is not None:
            book.toggle_door()

    def _call_home(self) -> None:
        book = getattr(self, "places", None)
        if book is not None:
            book.call_everyone()

    def _on_scene_press(self, event):
        return self._ctrl("pointer", InputController).on_scene_press(event)

    def _on_scene_drag(self, event):
        return self._ctrl("pointer", InputController).on_scene_drag(event)

    def _on_scene_release(self, event):
        return self._ctrl("pointer", InputController).on_scene_release(event)

    def _on_scene_double(self, event):
        return self._ctrl("pointer", InputController).on_scene_double(event)

    def _on_scene_right(self, event):
        return self._ctrl("pointer", InputController).on_scene_right(event)

    def _focus_linked_console(self, pid):
        return focus_linked_console(pid)

    # Skin picker and config.
    def _open_skin_picker(self):
        return self._ctrl("skin_picker", SkinPicker)._open_skin_picker()

    def _picker_sheet(self, name):
        return self._ctrl("skin_picker", SkinPicker)._picker_sheet(name)

    def _picker_frame(self, cache, name, row, t_ms, box, hue=0):
        return self._ctrl("skin_picker", SkinPicker)._picker_frame(
            cache, name, row, t_ms, box, hue)

    def _build_picker_ui(self, win):
        return self._ctrl("skin_picker", SkinPicker)._build_picker_ui(win)

    def _apply_skin(self, agent_id, skin):
        return self._ctrl("skin_picker", SkinPicker)._apply_skin(agent_id, skin)

    def _open_config_screen(self):
        return self._ctrl("config_screen", ConfigScreen)._open_config_screen()

    def _build_config_ui(self, win):
        return self._ctrl("config_screen", ConfigScreen)._build_config_ui(win)
