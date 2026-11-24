# Throne room

The orchestrator's hall, centre of the building. It is the **Throne** tab of the Dungeon window, beside
Dungeon and Skins. It follows the approved preview (`docs/img/throne-room-preview.png`, PR #22).

![preview](img/throne-room-preview.png)

In the app (made-up data, `tools/shot_throne_room.py`):

![app](img/throne-room-app.png)

## What it shows

| Part | Source |
|------|--------|
| Hall, walls, floor, props, walkway, stairs, two far rooms | `Sprites/dungeon_kit` tiles, anchors from its `INDEX.md` |
| Throne, dais, carpets, banners, door sign, crystals, wall board | Drawn in code (`throne_pieces.py`), captured once as sprites |
| Lord on the throne (40x40) | First top-level agent by id |
| Agents in the hall (40x40) | Other top-level agents, six spots; more show as `+n MORE` at the door |
| Subagents (32x32) | Two beside each parent; extras and deeper nodes add `+n` to the parent's tag. `fly` skins float |
| Task board (wall and readable panel) | The lord's project board (`board.store.LocalStore`), five columns, newest four cards each |
| State crystals | One per state. A crystal lights when an actor is in that state. The worst state is `NOW` and sets the room light (same pieces as BLDG-SCHEMA) |
| Door | Click it to go back to the Dungeon tab |

## Atelier (ATELIER.1)

A backroom through the right-wall door (plaque `ATELIER`), from the approved preview (`docs/img/atelier-preview.png`, PR #28).
The guest helper (`frost_wanderer`) sits at the desk. The guest is a helper, not the user.

| Rule | Detail |
|------|--------|
| Trigger | A card in `blocked` with the label `guest`. Its assignee walks; else the card topic's members; else the agents of its project (same resolution as AV.1's needs-me walk). Such a card does not send the bot to the user |
| Walk | Hall spot, door lane, through the door, across the landing, to the desk. Amber mark and halo while it waits. Back home when the card leaves `blocked` or loses the label |
| Who walks | Hall agents. The orchestrator stays on the throne. Up to five wait side by side at the desk |
| Code | `atelier.py` (no Tk, reuses `needs_walk.needing` and `Walker`), `atelier_pieces.py`, `atelier_art.py` (drawn before the hall shell) |

![atelier in the app](img/atelier-app.png)

`python tools/shot_atelier.py` shows it with made-up data: Ash's guest card sends Ash to the desk.

## Drawing

- One 760x460 image at 1x, shown at the largest integer scale that fits (nearest neighbour).
- Light: ambient plus lamps, multiplied in and dithered to twelfths; actors stay bright. Torch and crystal
  halos are added after. Four frames move the torch glow and the sparks.
- The tab reads agents and the board once a second while it shows. A changed room is drawn on a worker
  thread (about 0.3 s for four frames); the Tk thread only swaps images.

## Screenshot

`python tools/shot_throne_room.py` opens the Dungeon on the Throne tab with made-up agents and a made-up board
in a temporary data directory.
