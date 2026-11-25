# Body language = status (BODY)

Read an agent's state from across the room. On the Dungeon floor and the phone map, flowing agents stride, stuck
ones slump on a bench, one waiting on you taps its foot by the door, and a room whose run has gone on a long time
smokes, thicker with time. No AI, no git or PR data, no new window: it reads what the app already holds.

## Signals and thresholds

`app/body.py` (no Tk) maps each agent to one pose, first match wins:

| Pose | Word on hover | When |
|------|---------------|------|
| Slump | stuck | A blocked card on its room's task, a failed or timed-out run (needs-you), hook status `error`, or a failed turn |
| Tap | waiting | A topic waiting on you, an open decision, an unread reply or an ended run in its room, or hook status `blocked` |
| Stride | flowing | Hook status `busy`, `thinking` or `subagent` with activity in the last `flow_s` (120 s) |
| Idle | idle | Anything else: the avatar wanders as before |

Smoke: a run starts when an agent starts working and ends after 90 s without work (start times live in memory, not
on disk). Past `smoke_min` (20 min) the room smokes at 0.2; it thickens to 1.0 at `thick_min` (60 min). A room
takes the longest run inside it.

A pose change eases over 0.4 s (ease-out cubic); the pose before fades as the new one comes in.

## Desktop

| Part | What |
|------|------|
| Stride | The sprite leans into its facing, bobs, and kicks heel dust; it paces its room with a short pause. |
| Slump | Walks the doors to the bench of its own room and sits: head forward, shoulders down, colours cooled, a sigh puff. |
| Tap | Walks to the inside of its room's door on the way to you and taps its front foot, toe marks on the beat. |
| Bench | Drawn in code on the back wall of every room (a `prop_slots.bench` slot wins), one seat per sitter. |
| Smoke | From the room's brazier, else from a chimney on the back wall that rises while the room smokes; puffs drift. |
| Hover | The word (FLOWING, STUCK, WAITING, IDLE) on a small plate over the avatar. |

Avatars walk with the floor's own pathing (`Hall` trips through the doors). On the rooms floor a stuck or waiting
avatar goes to its bench or door instead of walking to you; with `body.enabled: false` the old needs-me walk is back.
Canvas items are made once and changed in place.

Sounds, drawn in code (`app/body_cues.py`): `sigh` on a slump, `knock` when waiting starts, `crackle` when a room
starts to smoke. They play on Windows like every cue and wait while a task is in focus.

## Phone

The map draws the same poses, benches and smoke, read-only. The scene's avatars carry `pose` (`stride`, `slump`,
`tap`, `idle`) and `smoke` (0..1); each room carries `smoke` (`at`, `chimney`). They ride `GET /api/scene` and the
SSE `avatars` event. No phone sounds.

## Settings (`config.json`)

```json
"body": {"enabled": true, "flow_s": 120, "smoke_min": 20, "thick_min": 60}
```

A missing or bad value keeps its default; `thick_min` is at least `smoke_min` + 1.

## Code

| File | What |
|------|------|
| `app/body.py` | Status to pose, smoke level, runs, eased shifts (no Tk) |
| `app/body_art.py` | Posed frames, bench, chimney, smoke, hover plate (Pillow) |
| `app/body_spots.py` | Bench, seat, door and smoke spots in a room |
| `app/body_view.py` | Floor targets, cues, canvas items, phone rows |
| `app/body_cues.py` | `sigh`, `knock`, `crackle` |
| `webui/static/body.js` | Phone poses, benches, smoke |

Tests: `tests/test_body.py`, `tests/test_body_art.py`, `tests/test_body_desktop.py`, `tests/test_phone_body.py`.
Evidence on made-up data: `tools/shot_body.py`, `tools/shot_phone_body.js`.
