"""ROOMS.1: the 30 room skins of ``docs/map-config.md``, dressed as layout items. No Tk, no new art.

A skin is one pick per slot (floor, wall, trim, door, light, props) from ``Sprites/dungeon_kit``.
``dress`` turns a skin and a room's size and doors into the ``structure`` items ``dungeon_rooms``
paints. A door cell on the back row ``(x, 0)`` or column ``(0, y)`` gets the skin's door when its
kind is ``"skin"``, else a plain arch.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

FLOORS = ("slab", "pale", "dark", "worn", "checker", "ring")
WALLS = ("tall", "low", "double")
TRIMS = ("cap", "pillar", "plain")
DOORS = ("arch", "door", "gate")
LIGHTS = {"amber": "b27-luz-ambar", "green": "b28-luz-verde", "red": "b29-luz-roja", "blue": "b30-luz-azul"}
PROPS = {"cage": "o01-jaula-de-hierro", "chest": "o02-cofre", "shackles": "o03-grilletes", "straw": "o04-lecho-de-paja",
         "skull": "o05-calavera", "skulls": "o06-pila-de-calaveras", "bones": "o07-huesos-cruzados",
         "vigil": "o08-calavera-con-vela", "circle": "o09-circulo-magico", "lectern": "o10-atril-con-grimorio",
         "orb": "o11-bola-de-cristal", "cauldron": "o12-caldero", "table": "o13-mesa-larga",
         "desk": "o14-mesa-con-vela", "bench": "o15-banco", "books": "o16-estanteria", "barrel": "o24-barril",
         "keg": "o25-barril-tumbado", "casks": "o26-pila-de-barriles", "crate": "o27-caja-de-madera",
         "flask": "o28-frasco-rojo", "bottle": "o29-botella-azul", "potions": "o30-estante-de-pociones"}
_WIDE = {"o04-lecho-de-paja", "o09-circulo-magico", "o13-mesa-larga", "o15-banco"}
_ON_WALL = {"o16-estanteria", "o30-estante-de-pociones"}
_DOOR_PIECES = {"arch": ("b14-arco-der", "b13-arco-izq"), "door": ("b16-puerta-der", "b15-puerta-izq"),
                "gate": ("b14-arco-der", "b13-arco-izq")}
UPPER = 19
TORCH_LIFT = {"tall": 0, "low": -5, "double": 9}

_TABLE = (
    ("Ember Hall", "slab", "tall", "cap", "arch", "amber", "table bench desk"),
    ("Cooper's Cellar", "worn", "low", "plain", "door", "amber", "casks barrel keg"),
    ("Quartermaster", "dark", "tall", "pillar", "door", "amber", "crate chest barrel"),
    ("Scribe's Nook", "pale", "tall", "cap", "door", "amber", "books desk bench"),
    ("Lantern Mess", "checker", "low", "cap", "arch", "amber", "table barrel desk"),
    ("Straw Bunk", "slab", "low", "pillar", "arch", "amber", "straw crate desk"),
    ("Gilded Vault", "ring", "double", "pillar", "gate", "amber", "chest cage crate"),
    ("Waystation", "worn", "double", "cap", "arch", "amber", "bench casks straw"),
    ("Frost Archive", "pale", "double", "cap", "arch", "blue", "books lectern orb"),
    ("Seer's Cell", "dark", "tall", "plain", "door", "blue", "circle orb bottle"),
    ("Moonwell", "ring", "low", "pillar", "arch", "blue", "circle bottle vigil"),
    ("Tide Lockup", "slab", "tall", "plain", "gate", "blue", "cage shackles straw"),
    ("Quiet Study", "checker", "tall", "pillar", "door", "blue", "lectern desk books"),
    ("Glass Pantry", "worn", "low", "cap", "door", "blue", "potions bottle crate"),
    ("Night Watch", "dark", "double", "plain", "arch", "blue", "bench barrel desk"),
    ("Sapphire Crypt", "pale", "low", "plain", "gate", "blue", "skulls vigil skull"),
    ("Brewer's Pit", "dark", "low", "cap", "arch", "green", "cauldron potions flask"),
    ("Moss Laboratory", "worn", "tall", "cap", "door", "green", "cauldron books desk"),
    ("Witchlight Ring", "slab", "double", "pillar", "arch", "green", "circle lectern cauldron"),
    ("Venom Store", "checker", "tall", "plain", "door", "green", "potions casks bottle"),
    ("Toad Hollow", "ring", "tall", "cap", "arch", "green", "cauldron keg skull"),
    ("Bone Garden", "pale", "tall", "pillar", "gate", "green", "skulls bones vigil"),
    ("Hermit's Den", "slab", "low", "plain", "door", "green", "straw lectern barrel"),
    ("Ossuary", "dark", "tall", "cap", "gate", "red", "skulls skull bones"),
    ("Crimson Chapel", "ring", "double", "cap", "arch", "red", "lectern vigil bench"),
    ("Warden's Hold", "worn", "tall", "pillar", "gate", "red", "cage shackles chest"),
    ("Cinder Stock", "slab", "tall", "plain", "arch", "red", "casks crate flask"),
    ("Red Reliquary", "checker", "double", "plain", "door", "red", "chest vigil flask"),
    ("Last Vigil", "pale", "low", "pillar", "door", "red", "desk vigil bench"),
    ("Ember Cistern", "dark", "low", "pillar", "arch", "red", "barrel flask bones"),
)


@dataclass(frozen=True)
class Skin:
    id: str
    name: str
    floor: str
    wall: str
    trim: str
    door: str
    light: str
    props: tuple[str, ...]


def _skin(row) -> Skin:
    name, floor, wall, trim, door, light, props = row
    return Skin(re.sub(r"[^a-z]+", "-", name.lower().replace("'", "")), name, floor, wall, trim, door, light,
                tuple(props.split()))


SKINS: dict[str, Skin] = {s.id: s for s in map(_skin, _TABLE)}


def _hash(u: int, v: int) -> float:
    x = math.sin(u * 127.1 + v * 311.7) * 43758.5453
    return x - math.floor(x)


def _item(piece: str, x: int, y: int, lift: int = 0, span=None) -> dict:
    out = {"piece": piece, "at": [x, y]}
    if span:
        out["span"] = list(span)
    if lift:
        out["lift"] = lift
    return out


def floor_items(skin: Skin, w: int, h: int) -> list[dict]:
    base = {"slab": "b01-losa", "pale": "b02-losa-clara", "worn": "b01-losa"}.get(skin.floor, "b03-losa-oscura")
    out = [_item(base, 0, 0, span=(w, h))]
    if skin.floor == "worn":
        out += [_item("b04-losa-agrietada", x, y) for x in range(w) for y in range(h) if _hash(x, y) < 0.3]
    elif skin.floor == "checker":
        out += [_item("b02-losa-clara", x, y) for x in range(w) for y in range(h) if (x + y) % 2]
    elif skin.floor == "ring" and w > 2 and h > 2:
        out.append(_item("b02-losa-clara", 1, 1, span=(w - 2, h - 2)))
    return out


def wall_items(skin: Skin, w: int, h: int, doors: dict) -> list[dict]:
    """Back row and column, the corner, end trim and the doors; a double wall has a low tier on top."""
    low = skin.wall == "low"
    tiers = (0, UPPER) if skin.wall == "double" else (0,)
    out = [_item("b12-esquina", 0, 0, lift) for lift in tiers]
    cells = [((x, 0), 0) for x in range(1, w)] + [((0, y), 1) for y in range(1, h)]
    for (x, y), left in cells:
        end = (x, y) == ((0, h - 1) if left else (w - 1, 0))
        kind = doors.get((x, y))
        for tier, lift in enumerate(tiers):
            top = tier == len(tiers) - 1
            if kind and tier == 0:
                continue
            if end and top and skin.trim == "cap":
                piece = "b17-remate-izq" if left else "b18-remate-der"
            elif low or tier:
                piece = "b10-muro-izq-bajo" if left else "b11-muro-der-bajo"
            else:
                piece = "b08-muro-izq" if left else "b09-muro-der"
            out.append(_item(piece, x, y, lift))
        if kind:
            style = skin.door if kind == "skin" else "arch"
            out.append(_item(_DOOR_PIECES[style][left], x, y))
            if style == "gate":
                out.append(_item("b21-reja-izq" if left else "b22-reja-der", x, y, -6))
        if end and skin.trim == "pillar" and not kind:
            out.append(_item("b25-pilar", x, y))
    return out


def torch_items(skin: Skin, w: int, h: int, doors: dict) -> list[dict]:
    lift = TORCH_LIFT[skin.wall]
    spots = [((1, 0), "b24-antorcha-der"), ((w - 2, 0), "b24-antorcha-der"), ((0, 2), "b23-antorcha-izq")]
    if h >= 8:
        spots.append(((0, h - 3), "b23-antorcha-izq"))
    seen, out = set(), []
    for cell, piece in spots:
        if cell in doors or cell in seen or min(cell) < 0 or cell[0] >= w or cell[1] >= h:
            continue
        seen.add(cell)
        out.append(_item(piece, cell[0], cell[1], lift))
    return out


def prop_items(skin: Skin, w: int, h: int, doors: dict) -> list[dict]:
    """Shelves against the left wall, a wide piece in the middle, small ones in the corners; never on a door tile."""
    lift = TORCH_LIFT[skin.wall]
    blocked = {(1, y) for (x, y) in doors if x == 0} | {(x, 1) for (x, y) in doors if y == 0}
    spots = [(w - 2, 2), (1, h - 2), (w - 2, h - 2), (2, 2)]
    pieces = [PROPS[p] for p in skin.props]
    wide = [p for p in pieces if p in _WIDE]
    if not wide:
        spots.insert(0, ((w - 1) // 2, (h - 1) // 2))
    out, shelf = [], 0
    for piece in pieces:
        if piece in _ON_WALL:
            y = 1 + shelf * 3
            y += (0, y) in doors
            out.append(_item(piece, 0, y))
            shelf += 1
        elif piece in _WIDE:
            n = wide.index(piece)
            out.append(_item(piece, w // 2 - 1, h // 2 - 1 + n * 2 - (len(wide) > 1)))
        elif piece == "o03-grilletes":
            out.append(_item(piece, 2, 0, lift))
        else:
            while spots and spots[0] in blocked:
                spots.pop(0)
            if spots:
                x, y = spots.pop(0)
                out.append(_item(piece, x, y))
    return out


def dress(skin_id: str, w: int, h: int, doors: dict, props: bool = True, torches: bool = True) -> list[dict]:
    """The structure items of a ``w`` x ``h`` room in ``skin_id``; ``[]`` for an unknown skin."""
    skin = SKINS.get(skin_id)
    if skin is None:
        return []
    out = floor_items(skin, w, h) + wall_items(skin, w, h, doors)
    if torches:
        out += torch_items(skin, w, h, doors)
    if props:
        out += prop_items(skin, w, h, doors)
    out.append(_item(LIGHTS[skin.light], w // 2, h // 2))
    return out
