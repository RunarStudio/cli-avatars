# Orchestrator rooms (ORCH.ROOM, proposal)

> Preview only: three images and this plan. No app code yet; it waits for the OK. Made-up names, topics and cards.

## The asks

1. A way to create an orchestrator.
2. Each orchestrator gets its own room.
3. When chats talk to each other, their avatars meet in one room.
4. At a glance: what each orchestrator and topic is working on now.
5. Each orchestrator runs its topic and that topic's task board.

## Today (from the repo docs)

- An orchestrator is a top-level session: Claude (`sessions.py`, `parent_id` None) or a live Grok session. Its topic is the project folder as a slug (`agent-chat-protocol.md`). Subagents follow their parent.
- The Throne tab shows one hall. Its lord is the first top-level agent by id (`throne-room.md`, `throne_model.seat`).
- Rooms: MAP.1/ROOMS.1 (`map-config.md`, not built yet) put rooms in `building/maps/main.json`. A room has an optional `topic`. **Create your room** puts a room on the nearest free spot, with a corridor and a door. `large` is 14x10, the throne hall's size.
- Room chat (`room-chat.md`): one orchestrator chat per topic, `room_chat/<topic>.json`.
- Board (`board.md`, TASKBACK): cards have `topic`, `assignee`, `column` and `status_note`. An AI changes only the column, progress, status note and checklist (Agent API).

## 1 + 2. Create an orchestrator, one room each

![one throne room per orchestrator](img/orch-rooms-preview.png)

- **New orchestrator** is a panel inside the Dungeon tab, next to Create your room. No new window. Fields: name, CLI (Claude or Grok), topic (the project folder slug), skin, connect to. Create adds a `large` throne room using the ROOMS.1 rule: nearest free spot, generated corridor, door facing the chosen point. It is saved in `main.json`. It starts no CLI; you start one with the Send click or Enter.
- The room has the throne-room pieces: throne, dais, carpet, banners, state crystals, door sign.
- One orchestrator has one room, and one topic has one room. Deleting the room deletes the orchestrator. Its board and topic stay.
- **Binding.** A live top-level session whose topic and CLI match a room sits on that room's throne. If several match, the newest `last_seen` is the lord and the others stand in the room. Its subagents stand beside it.
- **Running session with no room.** A top-level session in a folder that has no room shows in the Topics dock with **+ Give it a room**. One click fills the panel. Rooms are never created automatically: a short session would leave a permanent room on the map.
- The Throne tab shows the room the camera is on, or the selected Topics row, instead of the first agent by id.

New field on a room in `building/maps/main.json`:

```json
{"id": "orrin", "standard": false, "skin": "crimson-chapel", "at": [-18, -3], "size": "large",
 "door": "e6", "topic": "release-train", "orchestrator": {"name": "orrin", "cli": "claude"}}
```

| Field | Rule |
|-------|------|
| `orchestrator` | Optional. Allowed only on a `large` room with a `topic`. At most one room per topic. |
| `orchestrator.name` | `^[a-z0-9][a-z0-9-]{0,23}$`. Shown on the name tag and the Topics row. |
| `orchestrator.cli` | `claude` or `grok`. With the topic, it picks the session to bind. |

## 3. Chats interacting: avatars meet

![two orchestrators meet in the asker's room](img/orch-meeting-preview.png)

| Rule | Detail |
|------|--------|
| Trigger | A `say --to` or `reply` from orchestrator A to orchestrator B, answered by B within 5 minutes. A and B are bound to different rooms. Data: the chat store's channel rows (`from`, `to`, `ts`). A one-way note makes nobody walk. |
| Which room | Two orchestrators meet in **the asker's room**: B walks and A stays on its throne as host. Three or more orchestrators in one thread within 5 minutes meet in **the Hall**, and they all walk. |
| Walk | MOVE.1 paths: through doors and corridors, never through walls. The guest's throne shows as empty. Subagents stay home. |
| Home | After 3 minutes with no message between them. Also when the guest goes `blocked` or `error`: the needs-me walk wins. A manual MOVE.1 move wins and ends the meeting. |
| Stored | Nothing. A meeting exists only while it runs. `ui/avatar_places.json` keeps the home room. |

## 4. Tracker: what each orchestrator is on

![Topics dock and door signs](img/orch-tracker-preview.png)

- **Topics dock.** This is today's left dock (`rooms_panel.py`, TASKBACK 1.1) with bigger rows. No new tab or store. Each row shows: orchestrator, topic, CLI, the `doing` card, its `status_note`, the counts (todo, doing, review, blocked) and the last board line. Clicking a row moves the camera to that room, frames the room and selects the topic everywhere.
- **Door sign** over each room's door: the topic, the `doing` card title, and the `status_note` (amber when a card is blocked).
- **Data.** Board cards by `topic` (`LocalStore.list`), the doing card's `status_note`, and the newest event in `events.jsonl`. "Last activity" is the newer of the newest board event and the session's `last_seen`. These are read with the existing `StoreThrottle`, the same way as the throne board.
- **Who writes.** The AI writes the column, progress, status note and checklist. You do the rest.

## 5. The orchestrator runs its board

Same paths as today. No new process, and nothing executes chat text.

1. Your ask reaches its inbox through the chat window or room chat (To: orchestrator of the topic). It reads the ask with `inbox read` or the hook block.
2. It turns the ask into a card with MCP `task_propose`: a `todo` card labelled `proposed`, with the topic and the orchestrator as assignee. **Proposed change to Decision C:** an orchestrator room switches propose on **for its own topic only**. The limit of 5 per hour stays.
3. It moves cards with `task_status` (todo, doing, review, blocked), writes where it is with `task_progress --note` (this is the door sign's third line), and ticks steps with `task_check`.
4. Subagents have no inbox and no stable id. Their work is checklist lines on the orchestrator's card, not assignees.
5. It reports with `say` or `reply` on the topic.
6. Only you can do these: `done`, archive, retitle, reassign, and delete or empty the archive (Decisions B, C, D).

## Freeze and the code ticket

- **Frozen** until about 30 Nov: `overlay.py` and the core packages (`model/`, `world/`, `physics/`). None of them change. All the work is in `cli_avatars/app/`, `registry/` and `building/`.
- **Depends on** MAP.1 and ROOMS.1 landing first: `map_config.py` and `main.json`.
- **Files the code ticket touches:**
  - New `cli_avatars/app/orch_rooms.py`, with no Tk: binding, the meeting and home rules, and sign text.
  - `map_config.py`: the `orchestrator` field.
  - `dungeon_rooms.py`: throne pieces and door signs per room.
  - `dungeon_window.py`: the New orchestrator panel.
  - `rooms_panel.py`: Topics rows.
  - `throne_model.py` and `throne_panel.py`: the lord per room.
  - `inside_roster.py` and `room_floor.py`: the meeting walks.
  - `registry/agent_api.py` and `registry/policy.py`: propose limited to the orchestrator's own topic.
  - Tests beside the existing ones.

## Open questions

1. Meeting room: the asker's room (proposed), or always the Hall?
2. May an orchestrator add `proposed` cards to its own topic without asking (proposed), or only suggest them in chat so you click Add?
3. A running session with no room: one click to give it a room (proposed), or create the room automatically?

The images are drawn in code from `Sprites/dungeon_kit` and `throne_pieces.py`. Each has an `@4x` copy.
