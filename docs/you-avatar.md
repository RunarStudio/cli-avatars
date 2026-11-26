# Your avatar and who needs you (YOU-AVATAR.1)

You have your own avatar on the Dungeon floor, the **keeper**, and every avatar that needs you says so over its
head. Made-up names below.

## Why nothing showed before

A needs-you row reached an avatar only through its topic's `members`. A fresh session never joins a topic, so a
decision, a reply or an ended run reached nobody, and the BODY pose never fired without hook status. When it did
fire, the foot tap was a few pixels at the whole-map zoom, and BODY skipped the old amber mark. Your avatar was a
plain sprite at the Apothecary's centre that moved only by right-click > Move me to room.

## The keeper

| What | How |
|------|-----|
| Look | Drawn in code (`app/you_art.py`): crimson cloak, ermine collar, a small gold crown, a lantern on a staff with a flickering glow. Two idle and four walk frames. |
| Start | The centre of the throne room while the main session is open, else the Apothecary. |
| Click-to-walk | A click on the floor walks it there through the doors, like the agents (`Plan.route`). Drag still pans; a click on a courier, the boss, a plaque or the map control is theirs. |
| Select | Click the keeper: a gold ring pulses under it. Click it again or press **Esc** to let go. |
| Keys | While selected, arrow keys and WASD walk it the way they point on screen; walls stop it, doors let it through. Not selected, the keys pan the camera as before (NAV.1). |
| Camera | Follows it while it walks; zoom and pan are saved as before. |
| Kept | Room and feet in `ui/you_avatar.json` (no paths); it comes back there after a restart. Move me to room still works. |

## Who needs you

`app/you_needs.py` (no Tk) maps the Needs you rows ([needs-you.md](needs-you.md)) and the hook state to avatars:

| Kind | Bubble | Reaches |
|------|--------|---------|
| Decision | yellow `?` | Its asker, else the room's members, else the agents of the room's project |
| Blocked | red `!` | The card's assignee, else members, else the project's agents |
| Reply | blue `?` | Members, else the project's agents; also any agent whose hook state is `blocked` |
| Run ended | green `!` | Members, else the project's agents; also a hook `error` or a failed turn |

- The most urgent kind wins (decision, blocked, reply, run). Bots and subagents get no bubble.
- The bubble bobs over the head, above the nameplate, at least 2x so it reads at every zoom.
- A count badge over the keeper says how many avatars wait on you.
- The same mapping feeds BODY: the avatar slumps (blocked, failed run) or taps at its door (the rest).
- A click on a bubble, or walking the keeper up to that avatar (within about two tiles), opens its row as the Needs
  you tab does: a card on the Tasks tab, a room's chat in the dock. A hook-only need opens the avatar's chat. It
  opens once per approach.
- While a task is in focus only that task's rows bubble; hook-state bubbles stay.

## Sound

A bubble from a new row already rings that row's cue (`arrive`, or `decide` for a decision). A bubble from the hook
state alone plays `arrive`. A pose that only a row's bubble causes adds no `knock` or `sigh`. Cues are off with `sound.cues: false`, play on Windows, and wait while a task is in
focus.

## Phone

The map shows the same bubbles over the avatars and a crown and the badge over you, read-only. The scene's avatars
carry `need` (`decision`, `blocked`, `reply`, `run`) and yours `badge`; they ride `GET /api/scene` and the SSE
`avatars` event. Code: `webui/static/you.js`.

## Code

| File | What |
|------|------|
| `app/you_needs.py` | Rows and hook state to avatars, kinds, glyphs, colours (no Tk) |
| `app/you_walk.py` | Key directions, wall slides, home room, the saved spot (no Tk) |
| `app/you_art.py` | Keeper frames, bubbles, badge, ring (Pillow) |
| `app/you_view.py` | Floor glue: walk, keys, camera follow, bubbles, clicks, cue |
| `webui/static/you.js` | Phone bubbles, crown and badge |

Tests: `tests/test_you_needs.py`, `tests/test_you_walk.py`, `tests/test_you_desktop.py`, `tests/test_phone_you.py`.
Evidence on made-up data: `tools/shot_you.py`, `tools/shot_phone_you.py` with `tools/shot_phone_you.js`.
