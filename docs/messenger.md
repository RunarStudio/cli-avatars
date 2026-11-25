# Messenger between rooms (MESSENGER)

When a decision on one task affects another, a courier carries the scroll over. On the Dungeon floor a small
hooded courier leaves the deciding task's room, walks through the doors, and a wax seal flashes on arrival. The
affected task's card then glows under a "new from <room>" ribbon until you open it. The phone shows the same walk
and the lit card, read-only. No AI call, no git or PR data, no new window.

## Link rules

`messenger.py` (no Tk) links an answered decision on card A to another live card B. The first rule that matches wins:

| Rule | When |
|------|------|
| `affects` | The question or the answer says `affects <B>` (B's title as whole words, or the first 8 characters of its id) |
| `names` | The question or the answer names B anywhere |
| `depends` | A body line on A or B says one depends on, is blocked by, waits on, or comes after the other |
| `file` | A and B share a topic or a project, and both touched the same file (file names from the hook events, as in context packs) |

The decision's card is its `card`. When there is none, it is the card of the task chat that asked (`task-<8 hex>-n`).
Done and archived cards never get a courier, and neither does the deciding card itself. Only decisions from the last
24 h count, with at most 3 couriers per decision (strongest rule first). Each link is one `courier` event:

```json
{"kind": "courier", "key": "<decision 8>-<card 8>", "decision": "...", "from": "<card id>", "to": "<card id>",
 "rule": "affects", "reason": "marked: affects \"Glass apple orchard\"", "ts": 0}
```

The key dedupes the events. `couriers.json` in the data dir keeps each courier's state: `walking`, then `arrived`,
then `opened`, never a step back. The file is written only once a link exists, and it keeps the newest 200.

## Flow

1. Daniel answers a decision. Within a second the floor stores the new couriers.
2. One courier walks at a time, oldest first. It goes from the deciding task's room to the affected task's room
   along the floor's own door pathing, eased in and out. A task with no room uses the Apothecary.
3. The others queue: a `+n` pip rides on the walker, and couriers never pile on top of each other.
4. On arrival a wax seal flashes, the store marks the courier `arrived`, and the card lights up. The next courier
   leaves after a short gap.
5. Clicking the courier, the glowing card or its ribbon opens a parchment note. The note shows both tasks, the
   question, Daniel's answer and why it reached this task. "Open <task> ›" opens the task's card. Opening the note
   marks the courier `opened`, and the glow goes out.

Needs-you: an arrived courier adds a `NEWS` row only while its card waits on Daniel. That means the card is blocked,
has an open decision, or its topic is waiting on him. Clear works like any other row.

## Desktop

| Part | What |
|------|------|
| Courier | Drawn in code (`app/courier_art.py`) in the dungeon-kit look: a teal hooded cloak, a feathered cap, a satchel, and a sealed scroll under the arm. 6 walk frames, facing left or right. |
| Seal flash | A wax seal and gold sparks, 0.9 s |
| Lit card | A pulsing gold halo, a parchment card and a crimson `NEW FROM <ROOM>` ribbon at the room's back wall |
| Tasks tile | The card's tile in the Tasks center gets the same ribbon and a gold edge |
| Note | A parchment drawn on the floor canvas, sized to its text. Clicking it closes it. |

Canvas items are made once and changed in place. The courier draws above avatars and door signs.

## Phone

The map draws the courier walk read-only. It is one `courier` row in the scene's avatars (`room`, `feet`, `face`,
`walk`) on `GET /api/scene` and the SSE `avatars` event, with the sprite at `/api/sprite/courier.png`. A room whose
task was reached shows a glowing scroll. In the task list and on the board, that card glows under a
`✉ NEW FROM <ROOM>` ribbon. Tap the ribbon to read the decision, the answer and the reason. The card carries a
`courier` field (`from`, `title`, `question`, `answer`, `reason`), and the scene carries `couriers`. Opening happens
on the desktop. The phone plays no sounds.

## Sound

Two cues are drawn in code (`app/courier_cues.py`): `rustle` (footsteps and paper) when a courier leaves, and
`stamp` (a thud and a soft chime) on arrival. They play on Windows like every cue. While a task is in focus, a
courier bound to or from another task holds still and its cues wait; it moves on when focus ends.

## Settings

None.

## Code

| File | What |
|------|------|
| `messenger.py` | Link rules, `couriers.json` store, details for the note, needs-you rows (no Tk) |
| `app/courier_view.py` | The walk, queue, focus hold, cues, lit cards, note, phone rows |
| `app/courier_art.py` | Courier frames, seal flash, halo, card, ribbon, parchment (Pillow) |
| `app/courier_tiles.py` | Ribbon and gold edge on the Tasks tile |
| `app/courier_cues.py` | `rustle`, `stamp` |
| `webui/static/courier.js`, `courier.css` | Phone ribbon, slip, map glow |

Tests: `tests/test_messenger.py`, `tests/test_courier_desktop.py`, `tests/test_phone_courier.py`.
Evidence on made-up data: `tools/shot_courier.py` (GIF and desktop shot, under Xvfb),
`tools/shot_phone_courier.py` with `tools/shot_phone_courier.js` (phone at 400 px).
