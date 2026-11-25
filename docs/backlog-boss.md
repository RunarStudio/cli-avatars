# Backlog boss in the Pit (BACKLOG-BOSS)

Overdue and blocked tasks merge into one monster: an oni in a pit on the Dungeon floor. It grows in size and art with
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

## Desktop

- **The Pit**: the Dungeon has no pit room (START.1 opens with the Apothecary only), so a pit is drawn in code: a round
  hole in the flagstones with a broken stone lip and embers at the bottom, one tile in from the Apothecary's right
  corner. Without an Apothecary it goes in the first room.
- **Idle**: the oni breathes (four frames) at the size of its stage. When it grows a stage it roars.
- **Hit**: each new hit plays in turn: the oni flashes white, shakes, a `-1` rises, and the HP bar shows the drop.
- **Defeated**: the last hit to zero plays a fanfare and the oni falls.
- **Hover**: a parchment beside it shows HP and the tasks that feed it (`■` blocked, `◷` idle n days).
- **Click**: the list stays open; click a task and its card opens in the Tasks view.
- **Friday**: the HP bar and the burn-down parchment show. Any day, the small scroll button beside the oni, or `b` on
  the floor, shows or hides them for that day.
- **Standup**: the Friday standup carries `Backlog boss: HP n (Mon a > Fri n)` as a second banner in the throne room
  and in the phone's standup header.

## Phone

The map shows the oni in its pit with its HP bar. When HP drops between updates, each lost point plays a hit (a white
flash, a shake, a `-1`). Tap the oni for its sheet: HP, the week's burn-down and the tasks that feed it; tap a task
to pick it. Read-only: the scene rides SSE (`boss.json` is in the page's stamp).

## Sound

`roar` (a stage up), `thud` (a hit), `fanfare` (defeated), drawn in code in `boss_cues.py` like the other cues.
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
| `cli_avatars/app/boss_cues.py` | `roar`, `thud`, `fanfare` |
| `webui/boss_scene.py`, `webui/static/boss.js`, `boss.css` | The phone: sprite strip, state, map drawing, sheet |
| `tools/shot_boss.py`, `tools/shot_phone_boss.py` + `.js` | Made-up evidence: the week GIF, the desktop and phone shots |

Tests: `tests/test_backlog_boss.py`, `tests/test_boss_desktop.py` (`tests/_boss_probe.py`), `tests/test_phone_boss.py`.
