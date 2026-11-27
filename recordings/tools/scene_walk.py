"""Part B takes, 2026-11-27 (exec'd by stage.py). Each narration sentence is a ``vo`` mark; the take waits for it."""
# ruff: noqa: F821  (app, d, seed, DATA, WORK, PICK, clock, log come from stage.py)
import json
import os
from pathlib import Path

exec(compile((Path(seed.__file__).parent / "scene_common.py").read_text(), "scene_common.py", "exec"))

TAKE = os.environ.get("REC_TAKE", "")
DUR = json.load(open(os.environ["REC_VO"])) if os.environ.get("REC_VO") else {}


def vo(i, tail=0.5):
    """Mark narration sentence i of this take (its caption too); returns the clock time it ends."""
    key = f"{TAKE}_{i}"
    d.mark("vo", key=key, i=i)
    return clock() + DUR.get(key, 4.0) + tail


def answer(text):
    """A decision's answer button (not the question line that also holds the word)."""
    hits = [w for w in d.widgets() if text in text_of(w) and "?" not in text_of(w) and w.winfo_ismapped()]
    hits.sort(key=lambda w: (w.winfo_rooty(), w.winfo_rootx()))
    return hits[0] if hits else None


def b_first():
    yield 0.6
    end = vo(0)
    yield 2.0
    yield from d.click_text("Skip tour", seconds=0.8)
    yield from d.until(end)
    end = vo(1)
    yield from d.click(app._bootcheck_label, 0.8)
    yield 1.0
    d.mark("zoom", box=span(d.find("Claude CLI"), d.find("Grok CLI"), d.find("Save chats and files in"), pad=60),
           ease=0.9)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.7)
    yield from d.click_text("Close", seconds=0.6)
    end = vo(2)
    yield 0.6
    d.mark("zoom", box=[900, 60, 1000, 562], ease=1.0)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def b_chat():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    d.mark("in")
    end = vo(0)
    yield from d.click_text("New chat", seconds=0.7)
    yield 0.8
    card = app._new_chat_card
    d.mark("zoom", box=span(card.start_btn, card.name, pad=80), ease=0.9)
    yield from d.click(card.name, 0.6)
    yield from d.type("Tower bell")
    yield 0.3
    yield from d.click(card.chips.get("grok"), 0.5)
    yield 0.4
    yield from d.click(card.start_btn, 0.6)
    d.mark("zoom", box=None, ease=0.8)
    yield from d.until(end)
    end = vo(1)
    yield 0.3
    yield from chat_send("Plan the tower bell")
    d.mark("zoom", box=[1380, 230, 540, 304], ease=0.8)
    yield from d.until(end)
    stop = clock() + 8.0
    while clock() < stop and not any("Plan for the bell" in w.get("1.0", "end") for w in d.widgets()
                                     if w.winfo_class() == "Text" and w.winfo_ismapped()):
        yield 0.3
    yield 2.4
    d.mark("zoom", box=None, ease=0.8)
    yield 0.6


def b_board():
    yield 0.4
    quiet()
    yield from to_tab("Tasks")
    d.mark("in")
    end = vo(0)
    panel = app._tasks_panel
    d.mark("zoom", box=[100, 40, 1500, 844], ease=0.9)
    yield from d.click(panel.new_button, 0.6)
    yield 0.6
    yield from d.type("Tower bell chime")
    yield 0.3
    yield from d.click(panel.card_panel.create_button, 0.5)
    yield 1.0
    panel.close_card()
    yield from d.until(end)
    end = vo(1)
    for column in ("doing (", "review (", "done ("):
        tile, head = d.find("Tower bell chime"), d.find(column, exact=False)
        if tile is None or head is None:
            d.mark("missing", what=column)
            break
        (cx, cy), (hx, hy) = d.centre(tile), d.centre(head)
        yield from d.drag(cx, cy, hx, hy + 70, 0.9)
        yield 0.9
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def b_needs():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    yield from d.click_at(*d.room_xy("glass-garden", 2, -1.5), seconds=0.4, double=True)
    yield 2.0
    d.mark("in")
    beats.ask(DATA, who=VESSA, room="glass-garden", question="Copper or silver for the garden gate?",
              options=("a=Copper", "b=Silver"))
    yield 0.5
    end = vo(0)
    d.mark("zoom", box=around(*d.avatar_xy(VESSA), 1280, 720), ease=1.0)
    yield from d.until(end)
    end = vo(1)
    d.mark("zoom", box=[1240, 40, 680, 383], ease=0.8)
    yield from d.click(app.dungeon._rtab_needs.button, 0.6)
    yield 0.8
    rows = [w for w in d.widgets() if "Copper or silver" in text_of(w) and w.winfo_ismapped()]
    if rows:
        yield from d.click(rows[0], 0.6)
        yield 0.5
    else:
        d.mark("missing", what="needs row")
    inbox = in_dock("Inbox", exact=False)
    if inbox is not None:
        yield from d.click(inbox, 0.5)
        d.mark("zoom", box=[1240, 150, 680, 383], ease=0.8)
        yield 1.0
    pick = answer("Silver")
    if pick is not None:
        yield from d.click(pick, 0.6)
    else:
        d.mark("missing", what="Silver")
    yield from d.until(end)
    yield 1.6
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def b_memory():
    yield 0.4
    quiet()
    yield from to_tab("Tasks")
    yield from d.menu_pick("Chat topic", 1)
    yield 0.8
    d.mark("in")
    end = vo(0)
    yield from d.click_text("Dungeon map per project", exact=False, seconds=0.7)
    yield 1.0
    yield from d.wheel(*d.centre(d.find("Checklist")), -12, gap=0.06)
    yield 0.3
    hits = [w for w in d.widgets() if text_of(w) == "Remember" and w.winfo_ismapped() and w.winfo_rooty() < H - 80]
    if hits:
        yield from d.click(hits[0], 0.7)
    else:
        d.mark("missing", what="Remember")
    yield 1.2
    panel = app._memory_panel
    d.mark("zoom", box=[290, 80, 1260, 709], ease=0.9)
    yield from d.click(panel.text, 0.5)
    panel.text.delete(0, "end")
    yield from d.type("Ring the active room in gold", delay_ms=40)
    panel.kind.set("todo")
    panel.category.set("Dungeon")
    panel.topic.delete(0, "end")
    panel.topic.insert(0, "mini-map")
    yield 0.5
    yield from d.click(panel.save_button, 0.6)
    yield from d.until(end)
    end = vo(1)
    yield from d.click(panel.consolidate_button, 0.7)
    yield 3.0
    panel._at = 0
    panel.watch(True)
    panel.selected = "Dungeon/mini-map"
    panel.refresh(force=True)
    yield from d.until(end)
    yield 1.0
    d.mark("zoom", box=None, ease=0.8)
    yield 0.6


def b_phone():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    yield 1.0
    d.mark("in")
    proc = beats.phone(DATA, WORK, "walk", Path(beats.__file__).parent / "phone_touch.js")
    d.mark("phone")
    yield 1.5
    end = vo(0)
    yield from d.until(end)
    vo(1)
    while proc.poll() is None:
        yield 0.5
    d.mark("phone_end")


def b_update():
    yield 0.4
    quiet()
    yield from to_tab("Dungeon")
    beats.stub_update(app, WORK)
    yield 0.6
    d.mark("in")
    end = vo(0)
    check = d.find("Check for updates", exact="in")
    d.mark("zoom", box=span(check, d.find("Update"), pad=120, min_w=720), ease=0.9)
    yield from d.glide(*d.centre(check), 0.8)
    yield from d.until(end)
    end = vo(1)
    yield from d.click_text("Update")
    d.mark("zoom", box=[1280, 860, 640, 220], ease=0.6)
    yield from d.until(end)
    yield 3.4
    d.mark("zoom", box=None, ease=0.6)
    yield 0.6


TAKES = {name: fn for name, fn in globals().items() if name.startswith("b_") and callable(fn)}
