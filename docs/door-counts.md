# Door counts (DOOR-COUNTS, CHAT-COUNTS)

What is behind each room's door, at a glance: a small plaque on every room of the Dungeon floor, the
same plaque per project and in total at the top of Topics, and the same counts on the phone map. Read-only.

## The counts

| Count | Icon | What it counts |
|-------|------|----------------|
| Orchestrators | gold crown | Top-level live sessions (CHAT-TREE depth 1). |
| Agents | figure | Their children (depth 2). A Claude session's subagents are agents here. |
| Subagents | violet spark | Deeper children (depth 3 and more). |
| Conversations | blue bubble | Room chats (every topic that is not a task chat) and task chats (`task-<8 hex>-<n>`) of cards still on a board. |
| Open topics | green pennant | Room-chat topics `open` or `waiting_on_user`. |
| Pending decisions | red wax seal | Open decisions (`decisions.jsonl`), card decisions and chat decisions alike. |

## Which room

- An orchestrator and everything under it live in the session room of the same CLI and project folder (the
  START.1 binding), else in the Apothecary. Where an avatar walks (meetings, Move to room) does not move its counts.
- A topic lives in its session room, else in a room you built with that topic, else in the Apothecary.
- A task chat and a card decision live where the card's topic lives; another decision where its room's topic lives.
- So every item is in exactly one room, and the rooms add up to the total.

Projects: a topic counts for its `project`; a task chat or card decision for its card's project; an orchestrator for
its folder's topic's project, else for the folder name.

## Steady

`door_counts.build` is pure and reads no clock, status or position, so the counts change only when a session, topic,
chat or decision comes or goes. Inputs are read at most every 2 seconds (`StoreThrottle`); the plaque image changes
only when its numbers change, so nothing blinks.

## Desktop

- **Door plaque**: a wooden board on two iron chains, code-drawn (`door_plaque.py`), hanging under a session room's door
  sign, on a built room's door, and on the Apothecary's back wall. Five icons with their numbers (a zero dims); a
  pending decision turns the rim red and adds a wax seal with the count.
- **Breakdown**: hover a plaque for a parchment on the floor with the room and every count in words; a click pins it,
  a second click unpins it. It is a canvas item, not a window.
- **Behind the doors**: a strip at the top of the Topics dock, built once: **All projects** and up to six projects, each
  with its plaque. Hover a row for the breakdown in words. Rows are added or dropped only when a project comes or goes.

## Phone

- Each room's label on the map has its plaque above it: the non-zero icons and the red seal; an empty room shows none.
- A totals line under the map bar (**All**, every count, the seal). Tap it for one line per project.
- The Rooms sheet shows each room's counts under its name.
- `/api/scene` has `counts` on every room and `counts.total` / `counts.projects`; the SSE stream sends `counts` with
  every room, project and the total when they change, sessions included (`live.set_sessions`, set by the app).

## Sound

None for steady counts. A room's first decision already rings: the `decide` bell on the desktop (DECIDE.1) and the
rising bell on the phone, so the plaque adds no cue of its own.

## Code and tests

`cli_avatars/app/door_counts.py` (no Tk: `build`, `read`, `breakdown`), `door_plaque.py` (plaque, parchment, floor
items), `door_totals.py` (Topics strip), `webui/scene.py` (`counts_now`), `webui/server.py` (the `counts` event),
`webui/static/app.js` (`drawCounts`, `paintTotals`). Tests: `tests/test_door_counts.py`, `tests/test_door_plaque.py`,
`tests/test_phone_counts.py`. Evidence: `xvfb-run -a python tools/shot_door_counts.py <out-dir>` (made-up data).
