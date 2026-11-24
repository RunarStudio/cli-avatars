"""Atelier pixels for the throne room: the backroom behind the right-wall door, its guest and visitors.

``ThroneArt`` calls ``back`` once and ``furnish`` when the visitors change; both draw before the
hall shell, so the hall wall hides the atelier except through the door.
"""

from __future__ import annotations

from cli_avatars.app import atelier as at
from cli_avatars.app import throne_model as tm
from cli_avatars.app.atelier_pieces import sketch_bitmap, sketches_bitmap
from cli_avatars.app.throne_px import BG, TH, Buf, plate, t35

PROPS = (("o16", 15.05, -5), ("o30", 15.05, -4), ("o30", 15.05, -3), ("scrolls", 16.1, -5.6),
         ("easel", 19.8, -5.2), ("plant", 20.1, -0.9), ("o14", 20.05, -2.6), ("o27", 17.3, -0.85),
         ("o28", 18.3, -0.5), ("o29", 18.7, -0.9), ("plant", 16.9, -5.5))
TXT, SUB, LINE = "#f4ecff", "#9a8cc0", "#6a5a94"


def back(art) -> tuple[Buf, list, list]:
    """Background, the landing beyond the door and the atelier shell, wall art, torches and rug."""
    from cli_avatars.app.throne_art import tile_key

    b = Buf(tm.WIDTH, tm.HEIGHT, tm.X0, tm.Y0, tm.TILE)
    b.rect(0, 0, b.w, b.h, BG)
    lamps, glows = [], []
    lu, lv, la, lb = at.LANDING
    for u in range(lu, lu + la):
        for v in range(lv, lv + lb):
            art._put(b, "b06", u, v, 0)
            art._put(b, tile_key(u, v), u, v, 0)
    p = b.g(12, -1, 0.8)
    lamps.append((p[0], p[1], 90, 60, 0.9, "#ffc070"))
    au, av, aa, ab = at.ROOM
    art._shell(b, au, av, 0, aa, ab, tiers=2, left={4: "b13", 5: "b13"})
    art._put(b, "b13", au, -2)
    art._put(b, "b13", au, -1)
    p = b.g(au + 0.3, -1, 0.9)
    lamps.append((p[0], p[1], 46, 36, 0.7, "#ffc070"))
    glows.append(("b26", p[0], p[1] - 4, 0.8, False, True))
    b.tex("u", 17.1, av + TH, 1.0, sketches_bitmap())
    b.tex("v", au + TH, -0.75, 1.05, sketch_bitmap())
    for u in (16.4, 20.3):
        art._wall_torch(b, lamps, glows, "r", u, av, 1.3, 0.5)
    art._put(b, "rug_teal", 16.5, -3.3)
    m = b.g(au + 3, av + 3.5, 0)
    glows.append(("b27", m[0], m[1], 0.6, False, False))
    lamps.append((m[0], m[1], 130, 78, 0.72, "#ffd9a0"))
    return b, lamps, glows


def furnish(art, b: Buf, scene, inside, lamps: list, glows: list, tags: list) -> None:
    """Props, desk, guest and the visitors in ``inside``, back to front."""
    items = []
    for key, u, v in PROPS:
        items.append((u + v + 1, lambda key=key, u=u, v=v: art._put(b, key, u, v)))

    def desk():
        art._put(b, "desk", *at.DESK)
        q = b.g(at.DESK[0] + 1.6, at.DESK[1] + 0.4, 0.95)
        lamps.append((q[0], q[1], 64, 44, 0.75, "#ffd08a"))
        glows.append(("b26", q[0] + 6, q[1] - 6, 0.9, False, True))

    items.append((sum(at.DESK) + 1.5, desk))
    guest = scene.sprites.get(at.GUEST_ID)
    if guest is not None:
        items.append((sum(at.GUEST_SPOT) + 1.1, lambda: _guest(b, guest, tags)))
    for placed in inside:
        items.append((placed.u + placed.v + 1.1,
                      art._actor_fn(b, placed, False, scene.sprites, tags, scene.marked, lamps, glows)))
    for _d, fn in sorted(items, key=lambda it: it[0]):
        fn()


def _guest(b: Buf, image, tags: list) -> None:
    from cli_avatars.app.throne_art import fit_cell

    u, v = at.GUEST_SPOT
    p = b.g(u + 0.5, v + 0.5, 0)
    b.shadow(u + 0.5, v + 0.5, 0, 0.3)
    sprite = fit_cell(image, 40)
    if sprite is not None:
        b.paste(sprite, p[0], p[1], lit=True)
    tags.append((at.GUEST_NAME, at.GUEST_COLOR, p[0], p[1] - 40, 0))


def label(b: Buf) -> None:
    """The atelier's name plate, under the task board."""
    a = b.g(20.6, at.ROOM[1] + 0.3, 2.4)
    b.line(a[0], a[1] - 2, 690, 150, LINE)
    b.px(a[0], a[1] - 2, TXT)
    plate(b, 632, 126, 120, 24, "#0e0a19", "#33274f", "#4a3a74")
    t35(b, 636, 130, "ATELIER", at.GUEST_COLOR)
    t35(b, 672, 130, "BACKROOM", TXT)
    t35(b, 636, 138, "THE GUEST HELPER OFFICE", SUB)
