"""Demo takes (exec'd by stage.py with app, d, DATA, WORK, seed). Marks: cap (caption n), zoom (box or None), in."""
# ruff: noqa: F821  (app, d, seed, DATA, WORK, PICK, clock, log come from stage.py)
import beats

ORRIN, VESSA, PELL, LUMEN = "a1b2c3d4", "e5f6a7b8", "c9d0e1f2", "b3c4d5e6"


def around(x, y, w=960, h=540):
    return [int(x - w / 2), int(y - h / 2), w, h]


def d_map():
    yield 0.8
    d.mark("cap", i=0)
    yield 2.6
    yield from d.click_at(*d.room_xy("forja-lunar", -2.5, 1.5), seconds=0.9, double=True)
    yield 1.8
    d.mark("cap", i=1)
    d.mark("zoom", box=around(*d.avatar_xy(ORRIN), 1120, 630), ease=1.4)
    yield 3.6
    d.mark("zoom", box=None, ease=1.0)
    yield from d.click_at(*d.nav_xy("fit"), seconds=0.9)
    yield 1.6
    yield from d.click_at(*d.room_xy("torre-reloj", -2, 1.5), seconds=0.9, double=True)
    yield 2.6


def d_states():
    yield 0.6
    d.mark("cap", i=0)
    d.mark("zoom", box=around(*d.avatar_xy(LUMEN), 960, 540), ease=1.0)
    yield 1.6
    lumen = beats.agent(seed, LUMEN)
    lumen.update(status="busy", tool="Write", file="reloj.py")
    yield 3.2
    d.mark("zoom", box=None, ease=0.9)
    yield from d.click_at(*d.room_xy("archivo-brasas", -2, 1.5), seconds=0.8, double=True)
    yield 3.0


def d_needs():
    yield from d.click_at(*d.room_xy("jardin-cristal", 2, -1.5), seconds=0.4, double=True)
    yield 2.0
    d.mark("in")
    yield 0.6
    beats.ask(DATA)
    d.mark("cap", i=0)
    yield 0.4
    d.mark("zoom", box=around(*d.avatar_xy(VESSA), 1280, 720), ease=1.0)
    yield 3.4
    d.mark("zoom", box=None, ease=0.7)
    d.mark("cap", i=1)
    yield from d.click_text("Needs you", exact=False)
    yield 0.8
    d.mark("zoom", box=[1240, 40, 680, 383], ease=0.8)
    yield from d.click(d.rightmost("Jardín de cristal"))
    yield 1.2
    yield from d.click(d.find("Cobre", exact="in", nth=1))  # nth 0 is the question line
    yield 2.4
    d.mark("zoom", box=None, ease=0.8)
    yield 1.0


def all_topics():
    yield from d.click_text("Tasks", seconds=0.3)
    yield 1.2
    yield from d.menu_pick("Chat topic", 1)
    yield 0.8


def d_board():
    yield from all_topics()
    d.mark("in")
    d.mark("cap", i=0)
    yield 2.2
    card = d.find("Campana al terminar", exact=False)
    done = d.find("done (", exact=False)
    cx, cy = d.centre(card)
    dx, dy = d.centre(done)
    d.mark("cap", i=1)
    d.mark("zoom", box=[880, 60, 1080, 608], ease=0.9)
    yield from d.drag(cx, cy, dx, dy + 60, 1.1)
    yield 2.2
    d.mark("zoom", box=None, ease=0.8)
    yield 0.8


def d_chat():
    yield from all_topics()
    yield from d.click_text("Mapa de mazmorras", exact=False, seconds=0.3)
    yield 1.0
    d.mark("in")
    d.mark("cap", i=0)
    d.mark("zoom", box=[960, 40, 960, 540], ease=0.8)
    yield 0.6
    yield from d.click_text("New chat · Claude")
    yield 1.4
    yield from d.click(app._chat_window._entry)
    yield from d.type("Sigue con el minimapa, por favor")
    yield from d.key("Return")
    d.mark("cap", i=1)
    d.mark("zoom", box=[1140, 300, 780, 439], ease=0.8)
    yield 4.2
    d.mark("zoom", box=[960, 40, 960, 540], ease=0.8)
    yield 2.4


def d_phone():
    yield from d.click_at(*d.room_xy("forja-lunar", -2.5, 1.5), seconds=0.4, double=True)
    yield 1.0
    proc = beats.phone(DATA, WORK, "demo")
    d.mark("phone")
    d.mark("cap", i=0)
    while proc.poll() is None:
        yield 0.5
    d.mark("phone_end")


def d_update():
    yield 0.8
    beats.stub_update(app, WORK)
    d.mark("cap", i=0)
    yield from d.click_text("Update")
    d.mark("zoom", box=[1280, 860, 640, 220], ease=0.6)
    yield 9.0
    d.mark("zoom", box=None, ease=0.6)
    yield 0.6


TAKES = {name: fn for name, fn in globals().items() if name.startswith("d_") and callable(fn)}
