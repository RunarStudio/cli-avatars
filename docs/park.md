# The park and idle objects (PARK.1, IDLE-PROPS.1)

Avatars that are online but not working now spend their time somewhere: at an object in their room first, then
out in a small night park. Work calls them back.

## The park

- A lawn (12x9 tiles) joined to the Apothecary by a corridor, east of it, else south. It is placed like a room you
  build, so it never overlaps a session room, a sandbox or your rooms.
- Drawn in code in the kit's pixel style: grass with tufts, a few flowers and glowing mushrooms, a stepping-stone
  path, low garden walls. Three dark stone sculptures (a hooded statue, a broken obelisk with runes, a crouching
  gargoyle), two stone benches, two straw training dummies, a weight rack, a sparring post, four lanterns. Lamp
  halos and the obelisk's runes glow steadily and fireflies drift over the grass.
- What an avatar does there: **sit** on a bench (two each), **hit** a dummy, **lift** at the rack, **spar** at the
  post, or **stroll** the loop around the lawn.

## Idle objects

Six objects, drawn in code, each with a loop while someone uses it:

| Object | Where | Act | Seats |
| --- | --- | --- | --- |
| Hearth | Apothecary | warm hands (flames rise, sparks) | 2 |
| Dice table | Apothecary | play dice (dice tumble) | 2 |
| Well | Apothecary | drink (the bucket swings) | 1 |
| Lectern | first other room | read (pages turn) | 1 |
| Weapon rack | second other room | polish (a glint runs along a blade) | 1 |
| Cat and bowl | third other room | feed (the cat wakes and eats) | 1 |

With fewer rooms the rest go to the Apothecary. Each object stands on a free floor tile away from the back wall,
the front edges, furniture, every door path (2 tiles) and the other objects, so doors and corridors stay clear.
Each project room also gets its task table (`docs/orchestrator-rooms.md`).

## Who goes where

On top of BODY's idle pose (`docs/body-language.md`), for top-level avatars only:

- **Short idle**: quiet for 60 s (`idle_props.after_s`) → the nearest free object in its room or up to two rooms
  away. One avatar per seat; the reservation holds while the tier does.
- **Long idle**: quiet for `park.after_min` minutes (default 10) → a free park station. With the park off or full,
  an object instead.
- **Busy**: work (busy, thinking, a running subagent), a blocked card, an error or a wait on you releases the spot;
  the avatar walks home through the doors.

Quiet time counts from the session's last activity. Everything walks the Hall's own trips through the doors.

## Settings

`config.json`, read at most every 2 s:

```json
{"park": {"enabled": true, "after_min": 10}, "idle_props": {"enabled": true, "after_s": 60}}
```

`park.enabled: false` removes the park from the map; `idle_props.enabled: false` removes the objects and the short
tier.

## Phone

The map image carries the park and the objects at rest. The page adds the lamp halos and fireflies, a soft glow at
an object in use, the act under each idling avatar (`sitting`, `lifting`, `reading`…) and the task tables' counts.
Read-only (`scene.park`, each avatar's `idle`).

## Sound

On Windows, an avatar reaching the park plays a soft **night** ambience (wind, two far owl hoots, crickets); one
that trains (hit, lift, spar) adds a padded **train** thud. Both wait while a task is in focus; `sound.cues: false`
turns them off.

## Code

`cli_avatars/app/park.py` (placement, pieces, stations, settings; no Tk), `park_px.py`, `park_art.py` (the
art), `idle_props.py` (objects and tables; no Tk), `idle_art.py`, `idle_life.py` (the tiers; no Tk), `life_view.py`
(the Dungeon floor: trips, holds, overlays, cues), `park_cues.py`, `webui/park_scene.py`, `webui/static/park.js`.
Tests: `tests/test_park_idle.py`, `tests/test_park_desktop.py`, `tests/test_phone_park.py`.
