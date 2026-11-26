# Backlog boss in the Pit (BACKLOG-BOSS)

Overdue and blocked tasks merge into one monster: an oni in a pit in its own room, the Oni Pit. It grows in size and art with
the backlog. Each task you close hits it, and Friday shows its HP and the week's burn-down: a burn-down chart you
actually want to look at. The phone shows the same oni, read-only. No AI call, no git or PR data, no new window.

## HP rule

`backlog_boss.py` (no Tk) reads every card on every board. An open card (`todo`, `doing`, `review` or `blocked`, not
archived) feeds the boss when:

| Why | When |
|-----|------|
| `blocked` | The card sits in the `blocked` column |
| `overdue` | The card has had no update for 7 days (`OVERDUE_DAYS`). The board has no due date, so the card's `updated` time is its age |

HP is how many cards feed it. Blocked cards come first in its list, then the oldest overdue ones.

## Growth stages

| HP | Stage | Oni |
|----|-------|-----|
| 0-5 | 0 | KO-ONI, 32 px: a dozing cub with one scroll |
| 6-15 | 1 | AKA-ONI, 48 px: awake, tusks, a club, a tiger cloth |
| 16-30 | 2 | ONI TAISHO, 64 px: iron plates, scars, a kanabo, embers, scrolls piling at its feet |
| 31+ | 3 | DAI-ONI, 96 px: four horns, a mane of fire, a flame aura |

At HP 0 it lies knocked out (the defeated pose). The oni is drawn in code in `cli_avatars/app/boss_oni.py` (pixel
engine `boss_px.py`). It is concept art waiting for an OK, so everything it looks like lives in that one module and
can be swapped.

## Hits and the store

A card that fed the boss and then moves to `done` is one `hit`. Unblocking it or touching it only lowers HP; it is no
hit. Hits are deduped by card id. `boss.json` in the data dir is owner-only (0600) and keeps:

```json
{"feeding": ["<card id>", "..."], "hit": {"<card id>": 0.0}, "days": {"2026-11-23": 4, "2026-11-24": 12}}
```

`days` is the HP read on each day (the last reading wins). Days and hits older than 30 days are pruned. Only the
Dungeon writes the store (`backlog_boss.sync`, at most every 2 s); the phone only reads it.

## The week's burn-down

`backlog_boss.week` gives HP for Monday to Friday of the current week (a weekend shows the week that ended). A day
with no reading carries the day before; a day still to come is empty. Today's point is always the live HP. The chart
draws it as a wine-red line on parchment, over a dotted ideal line from Monday's HP down to zero on Friday.

## Rooms: the Oni Pit and the Crypt (BOSS-ROOM.1)

The oni has its own room, the **Oni Pit**, off the Apothecary's west wall through a short corridor. Next to it, off
that corridor, is the **Crypt**, with one skull per forgotten card. Both rooms are built from dungeon-kit pieces
(`wardens-hold` and `ossuary` skins); the pit, the skulls, the niches and the plaque are drawn in code. Both are pure
layout in `cli_avatars/app/boss_rooms.py` and appear when the Dungeon has a data folder.

| Oni Pit: HP | Size | Crypt: forgotten | Size |
|-------------|------|------------------|------|
| 0 | 4x4, bare: a grate, no oni, no scrolls | 0 | 4x4 |
| 1-5 | 6x5 | 1-8 | 5x5 |
| 6-15 | 8x6 | 9-16 | 7x6 |
| 16-30 | 10x8 | 17-30 | 9x7 |
| 31+ | 12x10 | 31+ | 11x8 |

The pit hole widens with the room, and the room gets more props as it grows (braziers, shackles). The HP rule is
unchanged.

**Forgotten** (`boss_rooms.forgotten`, one key `FORGOTTEN_DAYS = 30`): a card that is not done and either has had no
update for 30 days, or was archived. Deduped by card id; the longest forgotten come first.

**Growth never overlaps.** Each room's spot is picked once, at its largest size, after the session rooms, the custom
rooms and the park's spot (even while the park is off). The door wall stays fixed, and the room grows away from the
door, inside that reserved footprint. If a room you built already sits on the first spot, the next free point of the
Apothecary is tried. The Crypt tries a point off the Oni Pit's corridor first. Sandbox rooms are placed after both.

## Desktop

- **Oni Pit**: the oni sits in a round hole in the middle of its room. When HP crosses a step, the walls slide one
  tile per frame step (0.12 s), dust rises along every wall that moved, a stone grind plays, and the map, the zoom
  and the mini-map follow (a zoomed-in view stays on the same spot).
- **Crypt**: niches line the back walls, two rows per tile, lower row first; past the niches skulls pile on the floor.
  A skull keeps its niche while it stays. A new one drops in with a rattle. A carved plaque reads `12 forgotten`.
  Hover a skull: its card's title and how many days it was forgotten (and why). Click it: the card opens.
- **Idle**: the oni breathes (four frames) at the size of its stage. When it grows a stage it roars.
- **Hit**: each new hit plays in turn: the oni flashes white, shakes, a `-1` rises, and the HP bar shows the drop.
- **Defeated**: the last hit to zero plays a fanfare and the oni falls; three seconds later the room is bare and
  shrinks to 4x4.
- **Hover**: a parchment beside it shows HP and the tasks that feed it (`■` blocked, `◷` idle n days).
- **Click**: the list stays open; click a task and its card opens in the Tasks view.
- **Friday**: the HP bar and the burn-down parchment show. Any day, the small scroll button beside the oni, or `b` on
  the floor, shows or hides them for that day.
- **Standup**: the Friday standup carries `Backlog boss: HP n (Mon a > Fri n)` as a second banner in the throne room
  and in the phone's standup header.

## Phone

The map shows both rooms at the same sizes as the Dungeon: the oni in the Oni Pit with its HP bar (a bare room at HP
0), and the Crypt with a pixel skull per forgotten card and its count. Tap the Crypt for a read-only list of the
forgotten cards (tap one to pick it). When HP drops between updates, each lost point plays a hit (a white
flash, a shake, a `-1`). Tap the oni for its sheet: HP, the week's burn-down and the tasks that feed it; tap a task
to pick it. Read-only: the scene rides SSE (`boss.json` is in the page's stamp).

## Sound

`roar` (a stage up), `thud` (a hit), `fanfare` (defeated), `grind` (a boss room grows or shrinks; quiet while a boss
cue plays), `rattle` (a skull drops into the Crypt), drawn in code in `boss_cues.py` like the other cues.
Windows plays them; elsewhere there is no stdlib player and they stay silent. While a task is in focus, a cue that is
not about that task waits, and the last one plays when focus ends. Settings can switch cues off.

## Code

| File | Role |
|------|------|
| `backlog_boss.py` | Feeding, HP, stage, hits, the week, the store, the standup line (no Tk) |
| `cli_avatars/app/boss_oni.py` | The oni in four stages and the defeated pose (the one module to swap) |
| `cli_avatars/app/boss_px.py` | Its pixel engine (Torch Ink: 1-px ink outline, 3-tone ramps, torch rim) |
| `cli_avatars/app/boss_art.py` | Pit, hit flash, HP bar, damage number, scroll button, burn-down parchment |
| `cli_avatars/app/boss_view.py` | The floor view: pit spot, read, hits, hover and click list, chart toggle, cues |
| `cli_avatars/app/boss_cues.py` | `roar`, `thud`, `fanfare`, `grind`, `rattle` |
| `cli_avatars/app/boss_rooms.py` | The Oni Pit and the Crypt: size steps, the forgotten rule, spots, growth (no Tk) |
| `cli_avatars/app/boss_room_art.py` | Pit hole, niche, skull, plaque, dust |
| `cli_avatars/app/crypt_view.py`, `boss_dust.py` | The Crypt's skulls, hover and click; wall dust and the grind |
| `webui/boss_scene.py`, `webui/static/boss.js`, `boss.css` | The phone: sprite strip, state, map drawing, sheet |
| `tools/shot_boss.py`, `tools/shot_phone_boss.py` + `.js` | Made-up evidence: the week GIF, the desktop and phone shots |
| `tools/shot_boss_room.py`, `tools/shot_phone_boss_room.py` + `.js` | Made-up evidence of the rooms |

Tests: `tests/test_backlog_boss.py`, `tests/test_boss_desktop.py` (`tests/_boss_probe.py`), `tests/test_phone_boss.py`,
`tests/test_boss_rooms.py`, `tests/test_boss_room_desktop.py` (`tests/_boss_room_probe.py`), `tests/test_phone_boss_room.py`.
