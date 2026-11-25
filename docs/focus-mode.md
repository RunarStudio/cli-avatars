# Focus mode (FOCUS)

Pick one task. The Dungeon dims every other room, the board shows only that task, and alerts for other tasks
wait until you leave focus. Then they all come in at once, with one sound.

## Start and leave

| Where | Start | Leave |
|-------|-------|-------|
| Dungeon, Tasks tab | A card's right-click menu (or Shift+F10): **Focus on this task**. Or press **F** on a selected card. | **◉ Leave focus** in the board bar, **F** again on the card, or the menu's **Leave focus**. |
| Dungeon, Dungeon tab | (from the Tasks tab) | **Leave focus** on the banner at the top of the floor. |
| Phone | **◉ Focus** on a board card, or under the open task in the list. Needs **Allow the phone to open sessions and send prompts** (`web.allow_writes`). | **Leave focus** in the focus bar under the map bar, or **◉ Leave focus** on the card. Same switch. |

Focusing on another task switches focus: the new task's held alerts come in at once, the others keep waiting.
Focus and what it holds are kept in `focus.json` in the data dir, so both survive a restart. With phone writes off the
phone shows focus but cannot start or leave it.

## What waits

While a task is in focus, an alert waits when it is for another task and came after focus began:

| Alert | Held | Passes at once |
|-------|------|----------------|
| Needs you rows: decision, blocked, reply, run ended | Rows of other cards and rooms | Rows of the focused card, or of one of its task chats (`task-<8 hex>-<n>`) |
| Decision bell, its tray toast, the asker's walk to find you | Decisions on other cards and room decisions | Decisions on the focused card or its task chats |
| Web Push (decision, blocked) | Same rows as Needs you | Same |
| Phone bell, decision notice, background notification | Same rows (the server leaves them out of `/api/needs-you` and `/api/decisions`) | Same |

- A held alert is kept once per key (`decision:<id>`, `card:<id>`, `room:<room>`); a newer change of the same row does
  not add a second one. At most 200 are kept.
- A decision on another task waits too. There is no break-through setting: an agent waiting on a decision just waits.
- What already waited before focus began is not an alert: it stays out of sight in Needs you while focus lasts and comes
  back after it, without a sound.
- The **N waiting** counter shows how many alerts are held: on the Dungeon banner, in the Needs you note, in the
  phone's focus bar.

## Leaving

- Every held alert comes back once, oldest first, with no duplicates: the Needs you list, the phone bell and the
  decision seal show them again.
- One sound for the batch: the `release` cue on the desktop (and one tray toast, "N alerts waited for you"), the
  `release` tone on the phone. The released rows themselves do not ring the bell or the reply tone.
- Web Push sends the held items, oldest first; all but the last are silent, so the phone buzzes once.
- An alert whose item was answered or cleared meanwhile does not come back.

## Desktop

- **Floor**: the focused task's room stays lit (the room of its topic: its session room, else a room built with that
  topic, else the Apothecary). Every other room and corridor goes under a cool dark veil, dithered, its torches
  snuffed to soot, a little light spilling from the lit room onto its neighbours. The lit room's torches burn brighter
  with a warm flickering halo. Drawn in code from the room kit's own pixels (`focus_veil.py`); fades in over half a
  second, out over a third.
- **Banner**: a dark board with a gold rim and a lit candle, `FOCUS <task>`, a red wax seal with the number waiting,
  and a **Leave focus** button. Canvas items, no window.
- **Board**: the Tasks tab shows the focused card alone, in its column, titled `Focus · <task>`.
- **Needs you**: only the focused task's rows; the note says `N waiting (focus)`.
- Everything changes in place: images swap only when their key changes; nothing is rebuilt, nothing blinks.

## Phone

- The focus bar under the map bar: a candle, **Focus**, the task, the wax seal with **N waiting**, **Leave focus**.
- The map: every room but the focused one under a dark veil (its walls cut out with it), a warm flicker in the lit
  room; it fades in.
- Tasks: the other tasks grey out in the list and on the Board; the focused one has a gold edge.
- Live: the SSE event `focus` carries `{task, title, room, waiting}` whenever focus starts, ends or holds one more.

| Route | Answer |
|-------|--------|
| `GET /api/focus` | `{"task", "title", "room", "waiting", "writes"}`; `task` is null without focus. |
| `POST /api/focus` `{"task": "<card id>"}` | Writes on: `200` with the new state; `400` bad body or id; `404` no such card. CSRF, pairing cookie, rate limit and body cap as PHONE.2. |
| `POST /api/focus/leave` `{}` | Writes on: `200 {"ok": true, "released": n}`. |

`GET /api/needs-you` also returns `waiting`.

## Sound

| Cue | Desktop (`cues.py`, Windows, off in Settings) | Phone (note button) |
|-----|-----------------------------------------------|---------------------|
| Enter | `focus`: torches snuffed, a falling breath and a low settling two-note | Low falling two-note |
| Leave | `unfocus`: torches catching, a rising crackle and a lifting two-note | Low rising two-note |
| Leave with alerts held | `release`: `unfocus` and one soft bell strike after it, once for the batch | Rising two-note and one high note |

Held alerts make no sound at all until you leave.

## Code and tests

`focus.py` (no Tk: `start`, `leave`, `gate`, `belongs`, `room_of`, `public`), `cli_avatars/app/focus_mode.py`
(state, cues, toast, `narrow`), `cli_avatars/app/focus_veil.py` (veil, lit room, banner), `tasks_panel.py` (menu, F,
Leave focus), `needs_panel.py` and `decide_watch.py` (the gate), `webui/server.py` (routes, `focus` event),
`webui/push.py` (held pushes), `webui/static/app.js` (`drawFocus`, `setFocus`, focus bar).
Tests: `tests/test_focus_mode.py`, `tests/test_focus_desktop.py`. Evidence:
`xvfb-run -a python tools/shot_focus.py <out-dir>` (made-up data).
