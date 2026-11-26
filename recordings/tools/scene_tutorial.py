"""Tutorial takes (exec'd by stage.py). Each narration sentence is a ``vo`` mark; the take waits for it to end."""
# ruff: noqa: F821  (app, d, seed, DATA, WORK, PICK, clock, log come from stage.py)
import json
import os

import beats

ORRIN, VESSA, PELL, LUMEN = "a1b2c3d4", "e5f6a7b8", "c9d0e1f2", "b3c4d5e6"
TAKE = os.environ.get("REC_TAKE", "")
DUR = json.load(open(os.environ["REC_VO"])) if os.environ.get("REC_VO") else {}


def vo(i, tail=0.5):
    """Mark narration sentence i of this take (its caption too); returns the clock time it ends."""
    key = f"{TAKE}_{i}"
    d.mark("vo", key=key, i=i)
    return clock() + DUR.get(key, 4.0) + tail


def around(x, y, w=1280, h=720):
    return [int(x - w / 2), int(y - h / 2), w, h]


def span(*widgets, pad=40, min_w=800):
    """A 16:9 box holding the widgets."""
    app.root.update_idletasks()
    ws = [w for w in widgets if w is not None]
    x0 = min(w.winfo_rootx() for w in ws) - pad
    y0 = min(w.winfo_rooty() for w in ws) - pad
    x1 = max(w.winfo_rootx() + w.winfo_width() for w in ws) + pad
    y1 = max(w.winfo_rooty() + w.winfo_height() for w in ws) + pad
    w = max(x1 - x0, (y1 - y0) * 16 / 9, min_w)
    h = w * 9 / 16
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [int(cx - w / 2), int(cy - h / 2), int(w), int(h)]


def option(text):
    """A decision's answer button (not the question line that also holds the word)."""
    hits = [w for w in d.widgets() if text in str(_text(w)) and "¿" not in str(_text(w)) and w.winfo_ismapped()]
    hits.sort(key=lambda w: (w.winfo_rooty(), w.winfo_rootx()))
    return hits[0] if hits else None


def _text(w):
    try:
        return w.cget("text")
    except Exception:
        return ""


def you_xy():
    from cli_avatars.app.you_view import view_for

    box = view_for(app.places)._box
    sc = app.dungeon.scene
    return int(sc.winfo_rootx() + (box[0] + box[2]) / 2), int(sc.winfo_rooty() + (box[1] + box[3]) / 2)


def all_topics():
    yield from d.click_text("Tasks", seconds=0.5)
    yield 1.2
    yield from d.menu_pick("Chat topic", 1)
    yield 0.8


def t_start():
    yield 1.2
    end = vo(0)
    d.mark("zoom", box=span(d.find("Start check"), d.find("Close")), ease=1.0)
    yield from d.until(end)
    end = vo(1)
    gone = WORK / "proyectos" / "faro"
    gone.mkdir(parents=True, exist_ok=True)
    PICK[0] = str(gone)
    yield from d.click_text("Browse…", seconds=0.9, nth=1)  # nth 0 is the optional Cursor CLI row
    yield 1.2
    yield from d.click_text("Save", seconds=0.6, nth=1)
    yield from d.until(end)
    end = vo(2)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.5


def next_or_done():
    w = d.find("Next") or d.find("Done")
    if w is not None:
        yield from d.click(w, 0.5)


def t_tour():
    from cli_avatars.app import tour

    tour.start(app)  # what the launch does after the start card closes (Help → Take the tour replays it)
    yield 0.8
    end = vo(0)
    yield 2.4
    yield from d.click_text("Next", seconds=0.6)
    yield from d.until(end)
    end = vo(1)
    for _ in range(3):
        yield 0.9
        yield from next_or_done()
    yield from d.until(end)
    yield from next_or_done()
    yield 1.2
    yield from next_or_done()
    yield 1.0


def t_map():
    yield 0.6
    end = vo(0)
    yield 1.2
    yield from d.glide(*d.room_xy("archivo-brasas", 1, 1), 1.4)
    yield from d.glide(*d.room_xy("jardin-cristal", 1, -1), 1.4)
    yield from d.until(end)
    end = vo(1)
    yield from d.wheel(*d.room_xy("forja-lunar", -2.5, 1.5), 3, gap=0.3)
    yield 0.6
    yield from d.click_at(*d.room_xy("jardin-cristal", 2, -1.5), seconds=0.8, double=True)
    yield from d.until(end)
    end = vo(2)
    x, y = d.nav_xy("map")
    d.mark("zoom", box=around(x - 200, y - 120, 960, 540), ease=0.9)
    yield 1.4
    yield from d.click_at(*d.nav_xy("fit"), seconds=0.7)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.2


def t_states():
    yield 0.6
    end = vo(0)
    d.mark("zoom", box=around(*d.avatar_xy(LUMEN), 960, 540), ease=1.0)
    yield 1.8
    beats.agent(seed, LUMEN).update(status="busy", tool="Write", file="reloj.py")
    yield from d.until(end)
    end = vo(1)
    d.mark("zoom", box=None, ease=0.7)
    yield from d.click_at(*d.room_xy("forja-lunar", -2.5, 1.5), seconds=0.8, double=True)
    yield 1.6
    d.mark("zoom", box=around(*d.avatar_xy(ORRIN), 1120, 630), ease=0.9)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def t_you():
    yield from d.click_at(*d.room_xy("forja-lunar", -2.5, 1.5), seconds=0.4, double=True)
    yield 2.0
    d.mark("in")
    end = vo(0)
    d.mark("zoom", box=around(*you_xy(), 1280, 720), ease=1.0)
    yield from d.until(end)
    end = vo(1)
    d.mark("zoom", box=None, ease=0.8)
    yield from d.click_at(*d.room_xy("forja-lunar", 2.5, 2.0), seconds=0.8)
    yield 2.0
    yield from d.click_at(*you_xy(), seconds=0.6)
    yield 0.4
    yield from d.hold(["Right"], 0.9)
    yield from d.hold(["Up"], 0.7)
    yield from d.until(end)
    end = vo(2)
    yield from d.key("Escape")
    yield 0.4
    yield from d.hold(["Left"], 0.9)
    yield from d.until(end)
    yield 0.8


def t_needs():
    yield from d.click_at(*d.room_xy("jardin-cristal", 2, -1.5), seconds=0.4, double=True)
    yield 2.0
    d.mark("in")
    beats.ask(DATA)
    yield 0.5
    end = vo(0)
    d.mark("zoom", box=around(*d.avatar_xy(VESSA), 1280, 720), ease=1.0)
    yield from d.until(end)
    end = vo(1)
    d.mark("zoom", box=[1240, 40, 680, 383], ease=0.8)
    yield from d.click_text("Needs you", exact=False)
    yield from d.until(end)
    end = vo(2)
    yield from d.click(d.rightmost("Jardín de cristal"))
    yield 1.4
    yield from d.click(option("Plata"))
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def t_rooms():
    yield 0.8
    end = vo(0)
    d.mark("zoom", box=[0, 40, 720, 405], ease=1.0)
    yield from d.until(end)
    end = vo(1)
    yield from d.click_text("Simple room", seconds=0.6)
    yield 0.3
    yield from d.click_text("Claude", seconds=0.4)
    PICK[0] = str(WORK / "proyectos" / "torre-reloj")
    yield 0.3
    yield from d.click_text("Folder…", seconds=0.4)
    yield 0.6
    yield from d.click_text("Open session", seconds=0.5)
    yield from d.until(end)
    end = vo(2)
    d.mark("zoom", box=None, ease=0.8)
    beats.agent(seed, LUMEN)["live"] = True
    yield 0.6
    yield from d.click_at(*d.room_xy("torre-reloj", -2, 1.5), seconds=0.6, double=True)
    yield from d.until(end)
    end = vo(3)
    doors = d.find("Behind the doors", exact=False)
    d.mark("zoom", box=span(doors, pad=30, min_w=560), ease=0.8)
    yield from d.glide(doors.winfo_rootx() + 100, doors.winfo_rooty() + 60, 0.8)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def t_newchat():
    yield 0.6
    end = vo(0)
    yield from d.click_text("New chat", seconds=0.7)
    yield 0.8
    card = app._new_chat_card
    d.mark("zoom", box=span(card.start_btn, card.name, *card.recent_buttons[:1], pad=60), ease=0.9)
    yield from d.until(end)
    end = vo(1)
    if card.recent_buttons:
        yield from d.glide(*d.centre(card.recent_buttons[0]), 0.7)
        yield 0.6
    yield from d.click(card.name, 0.6)
    yield from d.type("Faro")
    yield 0.3
    yield from d.click(card.chips.get("grok"), 0.5)
    yield from d.until(end)
    end = vo(2)
    yield from d.click(card.start_btn, 0.6)
    yield 0.8
    d.mark("zoom", box=[1240, 40, 680, 1000 * 9 // 16 + 300], ease=0.8)
    yield from d.until(end)
    d.mark("zoom", box=None, ease=0.8)
    yield 0.8


def t_board():
    yield from all_topics()
    d.mark("in")
    end = vo(0)
    yield from d.until(end)
    end = vo(1)
    card = d.find("Campana al terminar", exact=False)
    done = d.find("done (", exact=False)
    (cx, cy), (dx, dy) = d.centre(card), d.centre(done)
    d.mark("zoom", box=[880, 60, 1080, 608], ease=0.8)
    yield from d.drag(cx, cy, dx, dy + 60, 1.0)
    yield from d.until(end)
    end = vo(2)
    d.mark("zoom", box=None, ease=0.7)
    yield from d.click_text("Atajos de teclado", exact=False, seconds=0.6)
    yield 0.8
    d.mark("zoom", box=[960, 40, 960, 540], ease=0.8)
    yield from d.until(end)
    yield 1.4
    d.mark("zoom", box=None, ease=0.8)
    yield 0.6


def t_taskchat():
    yield from all_topics()
    yield from d.click_text("Mapa de mazmorras", exact=False, seconds=0.4)
    yield 1.0
    d.mark("in")
    end = vo(0)
    d.mark("zoom", box=[960, 40, 960, 540], ease=0.8)
    yield 0.4
    yield from d.click_text("New chat · Claude")
    yield from d.until(end)
    end = vo(1)
    yield from d.click(app._chat_window._entry)
    yield from d.type("Sigue con el minimapa, por favor")
    yield from d.key("Return")
    d.mark("zoom", box=[1140, 300, 780, 439], ease=0.8)
    yield from d.until(end)
    yield 1.0
    end = vo(2)
    d.mark("zoom", box=None, ease=0.7)
    yield from d.click_text("Resumen diario", exact=False, seconds=0.6)
    yield 1.0
    claude = d.find("New chat · Claude")
    grok = next(w for w in claude.master.winfo_children() if _text(w) == "Grok")
    yield from d.click(grok)
    yield 1.0
    yield from d.click(app._chat_window._entry)
    yield from d.type("Resume el día")
    yield from d.key("Return")
    d.mark("zoom", box=[1140, 300, 780, 439], ease=0.8)
    yield from d.until(end)
    yield 2.4
    d.mark("zoom", box=None, ease=0.8)
    yield 0.6


def t_skins():
    yield 0.6
    end = vo(0)
    x, y = d.avatar_xy(LUMEN)
    d.mark("zoom", box=around(x + 200, y + 60, 1280, 720), ease=0.9)
    yield from d.click_at(x, y, seconds=0.7)
    yield 0.8
    yield from d.click_text("Skin", seconds=0.6)
    yield from d.until(end)
    end = vo(1)
    d.mark("zoom", box=None, ease=0.7)
    yield 0.6
    yield from d.click_text("forest scout", exact="in", seconds=0.7)
    yield 1.2
    yield from d.click_text("APPLY SKIN", seconds=0.7)
    yield from d.until(end)
    yield 1.2


def t_phone():
    yield from d.click_at(*d.room_xy("forja-lunar", -2.5, 1.5), seconds=0.4, double=True)
    beats.ask(DATA)
    yield 1.0
    proc = beats.phone(DATA, WORK, "tutorial")
    d.mark("phone")
    yield 1.5
    end = vo(0)
    yield from d.until(end)
    vo(1)
    while proc.poll() is None:
        yield 0.5
    d.mark("phone_end")


def t_settings():
    beats.stub_update(app, WORK)
    yield 0.6
    end = vo(0)
    yield from d.click_text("Settings", exact="in", seconds=0.6)
    yield 0.8
    nb = next((w for w in d.widgets() if w.winfo_class() == "TNotebook" and w.winfo_ismapped()), None)
    if nb is not None:
        d.mark("zoom", box=span(nb, pad=20, min_w=720), ease=0.8)
        tabs = {}
        for x in range(2, nb.winfo_width(), 6):
            try:
                tabs.setdefault(nb.index(f"@{x},10"), x)
            except Exception:
                pass
        for i in sorted(tabs)[1:]:
            if nb.tab(i, "text").strip() in ("Phone", "Bots"):  # a pairing token and QR, a repo URL: never on screen
                continue
            yield 0.9
            yield from d.click_at(nb.winfo_rootx() + tabs[i] + 20, nb.winfo_rooty() + 10, 0.5)
    yield from d.until(end)
    yield 0.8
    d.mark("zoom", box=None, ease=0.8)
    yield 0.6


def t_update():
    yield 0.6
    end = vo(0)
    yield from d.click(app._bootcheck_label, 0.8)
    yield 1.0
    d.mark("zoom", box=span(d.find("Start check"), d.find("Close")), ease=0.8)
    yield from d.until(end)
    yield from d.click_text("Close", seconds=0.5)
    end = vo(1)
    beats.stub_update(app, WORK)
    d.mark("zoom", box=None, ease=0.6)
    yield from d.click_text("Update")
    d.mark("zoom", box=[1280, 860, 640, 220], ease=0.6)
    yield from d.until(end)
    yield 3.4
    d.mark("zoom", box=None, ease=0.6)
    yield 0.6






TAKES = {name: fn for name, fn in globals().items() if name.startswith("t_") and callable(fn)}
