"""Part A takes, 2026-11-27 (exec'd by stage.py). Marks: cap (caption i), zoom (box or None), in."""
# ruff: noqa: F821  (app, d, seed, DATA, WORK, PICK, clock, log come from stage.py)
from pathlib import Path

exec(compile((Path(seed.__file__).parent / "scene_common.py").read_text(), "scene_common.py", "exec"))


def a_first():
    yield 0.6
    d.mark("cap", i=0)
    yield 2.4
    d.mark("cap", i=1)
    d.mark("zoom", box=[900, 60, 1000, 562], ease=1.0)
    yield 3.4
    d.mark("zoom", box=None, ease=0.8)
    yield from d.click_text("Skip tour", seconds=0.7)
    yield 0.6
    yield from d.click(app._bootcheck_label, 0.8)
    yield 1.6
    d.mark("cap", i=2)
    d.mark("zoom", box=span(d.find("Claude CLI"), d.find("Grok CLI"), d.find("Start check"), pad=60), ease=0.9)
    yield 3.0
    d.mark("cap", i=3)
    save = d.find("Save chats and files in")
    d.mark("zoom", box=span(save, d.find("/home/you/Documents", exact=False), pad=60), ease=0.8)
    yield 3.2
    d.mark("zoom", box=None, ease=0.8)
    yield from d.click_text("Close", seconds=0.6)
    yield 1.0


def a_first_send():
    yield 0.4
    quiet()
    yield 1.2
    d.mark("in")
    d.mark("cap", i=0)
    d.mark("zoom", box=[1280, 560, 640, 360 + 160], ease=0.9)
    yield from chat_send("What can you do?")
    yield 3.4
    d.mark("cap", i=1)
    d.mark("zoom", box=[900, 60, 1020, 574], ease=0.9)
    yield 3.4
    d.mark("zoom", box=None, ease=0.8)
    yield 1.2


def a_setup():
    from cli_avatars.app import start_card

    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    start_card.reopen(app)
    yield 1.4
    d.mark("in")
    d.mark("cap", i=0)
    save = d.find("Save chats and files in")
    d.mark("zoom", box=span(save, d.find("New chats work and save", exact=False), pad=50), ease=0.9)
    target = Path("/home/you/Documents/Agent desk")
    target.mkdir(parents=True, exist_ok=True)
    PICK[0] = str(target)
    yield 0.8
    yield from d.click(d.find("Browse…", nth=2) or d.find("Browse…"), 0.8)
    yield 1.0
    yield from d.click(d.find("Save", nth=2) or d.find("Save"), 0.6)
    yield 2.0
    d.mark("cap", i=1)
    bridge = d.find("Bot bridge (optional)")
    d.mark("zoom", box=span(bridge, d.find("Test bridge"), d.find("Copy folder"), pad=50), ease=0.9)
    yield 1.6
    yield from d.click_text("Copy instructions", seconds=0.7)
    yield 1.2
    d.mark("cap", i=2)
    yield from d.click_text("Test bridge", seconds=0.6)
    yield 3.0
    d.mark("zoom", box=None, ease=0.8)
    yield 0.8


def card_id(title):
    from registry.facade import Registry

    reg = Registry(DATA)
    for room, *_ in seed.ROOMS:
        for card in reg.task_list(room):
            if card["title"].startswith(title):
                return reg, card["id"]
    return reg, None


def all_topics():
    yield from to_tab("Tasks")
    yield from d.menu_pick("Chat topic", 1)
    yield 0.8


def a_looks():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    yield 1.2
    d.mark("in")
    d.mark("cap", i=0)
    d.mark("zoom", box=around(*d.avatar_xy(ORRIN), 800, 450), ease=1.2)
    yield 2.6
    d.mark("zoom", box=around(*d.avatar_xy(VESSA), 800, 450), ease=1.2)
    yield 2.4
    d.mark("cap", i=1)
    d.mark("zoom", box=around(*d.avatar_xy(PELL), 640, 360), ease=1.2)
    yield 3.4
    d.mark("zoom", box=None, ease=1.0)
    yield 1.4


def a_edits():
    yield 0.4
    quiet()
    yield from all_topics()
    d.mark("in")
    tile = d.find("Bell when a task ends", exact=False)
    yield from d.click(tile, 0.7)
    yield 1.0
    d.mark("cap", i=0)
    d.mark("zoom", box=span(tile, pad=60, min_w=960), ease=0.9)
    reg, cid = card_id("Bell when a task ends")
    yield 1.6
    reg.task_edit(cid, title="Bell when a task ends: soft chime")
    yield 1.6
    reg.task_progress(cid, 95, "Volume set to 40 %")
    yield 1.4
    d.mark("cap", i=1)
    reg.task_edit(cid, body="Chime at 40 %, muted in focus mode.")
    yield 1.6
    reg.task_progress(cid, 100, "Ready for review")
    yield 2.2
    d.mark("zoom", box=None, ease=0.8)
    yield 0.8


def a_memory():
    yield 0.4
    quiet()
    yield from all_topics()
    d.mark("in")
    d.mark("cap", i=0)
    yield from d.click_text("Dungeon map per project", exact=False, seconds=0.7)
    yield 1.0
    x, y = d.centre(d.find("Checklist"))
    yield from d.wheel(x, y, -12, gap=0.08)
    yield 0.4
    hits = [w for w in d.widgets() if text_of(w) == "Remember" and w.winfo_ismapped() and w.winfo_rooty() < H - 80]
    if hits:
        yield from d.click(hits[0], 0.7)
    yield 1.4
    panel = app._memory_panel
    d.mark("zoom", box=[290, 80, 1260, 709], ease=0.9)
    yield from d.click(panel.text, 0.6)
    panel.text.delete(0, "end")
    yield from d.type("Ring the active room in gold")
    panel.kind.set("todo")
    panel.category.set("Dungeon")
    panel.topic.delete(0, "end")
    panel.topic.insert(0, "mini-map")
    yield 0.8
    yield from d.click(panel.save_button, 0.6)
    d.mark("cap", i=1)
    yield 2.4
    d.mark("cap", i=2)
    yield from d.click(panel.consolidate_button, 0.7)
    yield 3.0
    panel._at = 0
    panel.watch(True)
    panel.refresh(force=True)
    yield 1.0
    d.mark("cap", i=3)
    panel.selected = "Dungeon/mini-map"
    panel.refresh(force=True)
    yield 3.4
    d.mark("zoom", box=None, ease=0.8)
    yield 0.8


def a_rooms():
    yield 0.4
    quiet()
    yield from to_tab("Memory")
    d.mark("in")
    d.mark("cap", i=0)
    panel = app._memory_panel
    panel.selected = "Dungeon/bell-sounds"
    panel.refresh(force=True)
    yield 1.6
    pin = d.find("Pin room")
    if pin is not None:
        d.mark("zoom", box=span(pin, d.find("Go to room") or pin, pad=200), ease=0.9)
        yield 0.6
        yield from d.click(pin, 0.6)
        yield 1.6
    d.mark("cap", i=1)
    go = d.find("Go to room")
    if go is not None:
        yield from d.click(go, 0.6)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.8
    yield from zoom_topic_room()
    yield 3.0


def zoom_topic_room():
    """Zoom on the Topic room (the map draws no room names), as tools/shot_memory.py rings it."""
    from cli_avatars.app import topic_rooms as tr
    from cli_avatars.app.room_floor import Plan

    scene = app.dungeon.scene
    painter = scene._rooms_painter
    for room in painter.layout.get("rooms") or []:
        if tr.room_type(room) == tr.TOPIC:
            x, y = painter.to_canvas(*Plan.from_layout(painter.layout).floor(room["name"]).centre())
            d.mark("zoom", box=around(x + scene.winfo_rootx(), y + scene.winfo_rooty(), 960, 540), ease=1.0)
            break
    yield 0.0


def a_bots():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    yield from settings_tab("Bots")
    no_urls()
    yield 0.3
    d.mark("in")
    d.mark("cap", i=0)
    owl = in_dock("Night Owl")
    d.mark("zoom", box=span(owl, pad=120, min_w=640) if owl is not None else None, ease=0.9)
    yield 3.0
    d.mark("cap", i=1)
    pins = [w for w in d.widgets() if text_of(w) == "Always show" and w.winfo_ismapped()]
    below = [w for w in pins if owl is not None and w.winfo_rooty() > owl.winfo_rooty()]
    near = min(below, key=lambda w: w.winfo_rooty()) if below else None
    if near is not None:
        yield from d.click(near, 0.6)
    yield 1.4
    d.mark("zoom", box=None, ease=0.8)
    yield 3.2


def a_tiers():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    yield from settings_tab("Chat")
    d.mark("in")
    d.mark("cap", i=0)
    tabs = [in_dock(n) for n in ("Physics", "Behavior")]
    d.mark("zoom", box=span(*tabs, pad=60, min_w=560), ease=0.9)
    yield 2.6
    d.mark("cap", i=1)
    head = in_dock("Chat tiers")
    yield from d.wheel(*d.centre(head), -4, gap=0.12)
    yield 0.4
    row = in_dock("Topic orchestrator · simple room")
    if row is not None:
        d.mark("zoom", box=span(in_dock("Chat tiers"), row, pad=110, min_w=560), ease=0.9)
        yield 1.2
        effort = row.master.master.winfo_children()[1].winfo_children()[1]
        yield from d.click(effort, 0.6)
        yield 0.7
        yield from d.key("Down")
        yield 0.4
        yield from d.key("Return")
    yield 3.0
    d.mark("zoom", box=None, ease=0.8)
    yield 0.8


def a_update():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    beats.stub_update(app, WORK)
    yield 0.6
    d.mark("in")
    d.mark("cap", i=0)
    yield from d.click_text("Update")
    d.mark("zoom", box=[1280, 860, 640, 220], ease=0.6)
    yield 4.0
    d.mark("cap", i=1)
    yield 4.4
    d.mark("zoom", box=None, ease=0.6)
    yield 0.6


def a_leftovers():
    yield 0.4
    quiet()
    yield from to_tab("Memory")
    d.mark("in")
    d.mark("zoom", box=[0, 0, W, H], ease=0.05)
    d.mark("cap", i=0)
    app.dungeon.set_left(True)
    app.dungeon.set_right(True, "settings")
    panel = app._memory_panel
    panel.selected = "Dungeon/mini-map"
    panel.refresh(force=True)
    yield 2.0
    pop = d.find("Pop out", exact="in")
    if pop is not None:
        yield from d.glide(*d.centre(pop), 0.8)
    yield 1.6
    d.mark("cap", i=1)
    yield from d.glide(W - 200, 180, 0.8)
    yield 3.4


TAKES = {name: fn for name, fn in globals().items() if name.startswith("a_") and callable(fn)}


def a_phone():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    yield 0.8
    d.mark("in")
    proc = beats.phone(DATA, WORK, "changes", Path(beats.__file__).parent / "phone_touch.js")
    d.mark("phone")
    t = clock() + 1.5
    for i, at in enumerate((0.0, 4.4, 8.0, 14.6)):
        yield from d.until(t + at)
        d.mark("cap", i=i)
    while proc.poll() is None:
        yield 0.5
    d.mark("phone_end")


TAKES["a_phone"] = a_phone
