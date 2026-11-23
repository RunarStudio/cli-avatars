# Room layout and agent state → dungeon kit

> Ported from Spidey_PR_Dashboard PR #23 by Agents, reviewed 2026-11-23 (PORT-AG1, source commit `e81d155`).
> Proposal only. Where it disagrees with [`docs/building-scene.md`](../building-scene.md) (BLDG-SCHEMA), BLDG-SCHEMA is the source of truth; see [Differences vs BLDG-SCHEMA](#differences-vs-bldg-schema).

Proposal for the Building view: one room per orchestrator, built from `Sprites/dungeon_kit/` at 2× integer scale (nearest neighbour). Docs only: no app code changes. Names in the previews are made up.

![one room](room_layout_preview.png)

## 1. Room grid

Kit grid (`Sprites/dungeon_kit/INDEX.md`): iso 2:1, a tile is 32×16 px, a height unit 16 px; at 2× a tile is 64×32. Tile (u, v) lands at `x = X0 + (u - v) * 16 - anchorX`, `y = Y0 + (u + v) * 8 - z * 16 - anchorY` (1×, then ×2). A room is 10 × 8 tiles, about 576 × 390 px at 2×.

| Part | Kit file | Tiles (u, v) |
|---|---|---|
| Rock base | `b07-roca-honda.png` (inner), `b06-roca.png` (all) | under every tile |
| Floor | `b01-losa`, `b02-losa-clara`, `b03-losa-oscura`, `b04-losa-agrietada` mixed | 10 × 8 |
| Floor centre | `b05-losa-rejilla.png` | (5, 4) |
| Back right wall | `b09-muro-der.png`, door `b16-puerta-der.png`, end `b18-remate-der.png` | v = 0, u = 1…9; door u = 6; end u = 9 |
| Back left wall | `b08-muro-izq.png`, arch `b13-arco-izq.png`, end `b17-remate-izq.png` | u = 0, v = 1…7; arch v = 2; end v = 7 |
| Corner | `b12-esquina.png` | (0, 0) |
| Torches | `b24-antorcha-der.png`, `b23-antorcha-izq.png`, `b26-halo-antorcha.png` on each flame | (2, 0), (8, 0); (0, 1), (0, 6) |
| Room light | one of `b27`…`b30` (section 3) | centre (5, 4), additive |

Front edges stay open so nothing hides an avatar. Paint order is the kit's: rock, floor, walls, light, decals, then props and avatars back to front by u + v, torches, gates.

## 2. Who stands where

The tree is orchestrator (depth 0) → agents (depth 1) → subagents (depth 2) → deeper (depth 3+).

| Node | Size | Place | Kit pieces |
|---|---|---|---|
| Orchestrator | 40×40 | centre of the magic circle, tile (1.5, 1.5) | `o09-circulo-magico.png` at (1, 1); lectern `o10-atril-con-grimorio.png` at (3, 1) |
| Agent slot S1 | 40×40 | stands (6, 2), desk (6, 1) | `o14-mesa-con-vela.png` |
| Agent slot S2 | 40×40 | stands (4, 5), desk (3, 5) | `o14-mesa-con-vela.png` |
| Agent slot S3 | 40×40 | stands (1, 6), desk (1, 5) | `o14-mesa-con-vela.png` |
| Agent slot S4 | 40×40 | stands (8, 7), desk (8, 6) | `o14-mesa-con-vela.png` |
| Subagent C1, C2, C3 | 32×32 | parent's tile + (2, 0), (1, 2), (-1, 1) | none (row + halo only) |
| Depth 3+ | badge | `+n` pip on its depth-2 ancestor | none (see needed sprites) |

Folding rules, so a room never fills with sprites:

| Overflow | Shown as |
|---|---|
| Agents 5+ | `+n` pip on the door `b16-puerta-der.png`; listed on click |
| Subagents 4+ of one agent | `+n` pip on that agent's third subagent |
| Any node at depth 3+ | counted into the `+n` pip of its depth-2 ancestor; never a sprite |
| Subagent slot outside the room or taken | folds into the same `+n` pip |

Labels: orchestrator and agents get a name tag in their state colour; subagents get none.

## 3. Agent state → kit

Each node carries its state with three things: a small halo at its feet, a prop next to its slot, and an avatar row. The room light shows the room's worst state: error > blocked > busy > thinking > done > idle.

| State | Room light (pool) | Node halo | Flicker (alpha of the light) | Prop | Main row (40×40, `sprite_loader.ANIM_ROW`) | Sub row (32×32, `subskins.STATUS_TO_ROW`) |
|---|---|---|---|---|---|---|
| idle | none, torches only | none | steady; dims after 5 min (`rooms.IDLE_AFTER`, `fade_image` 0.55) | `o15-banco.png` | 0 idle | idle |
| thinking | `b30-luz-azul.png` | `b26` shifted blue | slow pulse, 1.6 s, 60–100 % | `o11-bola-de-cristal.png` | 2 sit | working |
| busy | `b28-luz-verde.png` | `b26` shifted green | fast flicker, 3 levels at 120 ms | `o12-caldero.png` | 1 run | working |
| done | none | none | candle steady, fades with the linger | `o02-cofre.png` | 3 stand | dying, once, then removed |
| error | `b29-luz-roja.png` | `b26` shifted red | steady; warn icon blinks 500 ms | `o05-calavera.png` + decal `o21-mancha-de-sangre.png` | 3 stand | idle |
| blocked | `b27-luz-ambar.png` | `b26` as is (amber) | slow pulse, 0.8 s | gate `b21-reja-izq.png` + `b22-reja-der.png` on the slot's two front edges | 0 idle (no row yet) | idle |

Colours follow the thread's dungeon reading: green works, blue waits, red stopped, amber needs you. The warn icon is the existing `Sprites/talk/icons.png` cell 3 (`rooms.warn_icon`). The node halo is `b26` with a hue shift, the same method as `sprite_loader.hue_rotate_image`, until real small halos exist.

## 4. Counts plaque

One plaque per room, hung on the back right wall (`b09-muro-der.png`, between the torches): room name, then `agents · subagents · conversations · open topics`. Until a plaque sprite exists it is a text plate drawn by the app, like the Rooms list cards. The Building view header sums the same four counts over all rooms, plus the room count (= orchestrators).

## 5. Building view: 4 and 16 rooms

![four rooms](room_layout_tile4.png)

| Rooms | Layout at 2× | Fits 1920×1080 |
|---|---|---|
| 1 | full 10 × 8 room, as above | yes |
| 4 | 2 × 2 iso lattice, room origins (0, 0), (11, 0), (0, 9), (11, 9): one empty tile between rooms; drawn back to front by u + v; tag on each room's west corner in its worst-state colour | yes, 1280 × 800 |
| 16 | 4 × 4 lattice of compact 6 × 5 rooms (orchestrator and desks only, subagents only on the plaque), origins every 7 u and 6 v | yes, about 1600 × 900 |
| more | same 4 × 4 page, paged by project | yes |

Order: rooms needing the user first (blocked, error), then newest activity, the same order `rooms.build_rooms` already uses for active versus long idle. A click on a room opens it full size; Esc goes back.

## 6. Data each element reads

| Element | Reads | Status |
|---|---|---|
| Room | top-level session (`SessionInfo.parent_id` is None) → `rooms.RoomCard` | exists |
| Room name | `RoomCard.project` (`rooms.project_folder`), else `RoomCard.name` | exists |
| Orchestrator avatar | `RoomCard.skin`, `RoomCard.status` | exists |
| Agents (depth 1) | children by `parent_id` → `RoomCard.subs` (`SubRow`) | exists |
| Subagents (depth 2+) | `SessionInfo.parent_id` chain beyond one level | needs: tree reader; scanners fill one level today (Claude `<session>/subagents/` and Grok `subagents/*/meta.json` give counts) |
| Depth | walk of `parent_id` | needs: computed field |
| idle, thinking, busy | `SessionInfo.status` (`ClaudeJsonlSource._parse_tail`, `grok_state_from_updates`) | exists |
| error | `SessionInfo.failed` or status `error` (`rooms.needs_warn`) | exists |
| done | overlay `DONE` and `_task_done_at` / `_lingering_subs` (`overlay.py`); `done` already in `ANIM_ROW` and `STATUS_TO_ROW` | exists in the overlay, not in `SessionInfo` |
| blocked | needs: a `blocked` status when a session waits on the user (permission prompt or question), read from the Claude hook it already has (`hooks/claude_chat_hook.py`); topic status `waiting_on_user` (`topics.py`) is the topic-level twin | needs |
| Long idle dim | `rooms.is_long_idle` | exists |
| Count: agents | depth-1 children of the room | exists |
| Count: subagents | depth 2+ nodes, today `SessionInfo.subagents` | partial |
| Count: conversations | chat nodes in the room's tree (each chat is a node) | needs: tree reader |
| Count: open topics | `topics.list_topics(statuses=["open", "waiting_on_user"])`, matched on `project` | exists, needs the project match |

The room only reads and shows. It never executes chat content and never starts a CLI; a click opens the chat window, where sending stays an explicit user action (click or Enter).

## 7. Needed sprites (not in the kit)

| # | Sprite | Size (1×) | Stand-in today |
|---|---|---|---|
| 1 | Wall plaque for the counts, hangs on `b09` | about 40×14 | text plate |
| 2 | Small state halos: green, blue, red, amber (like `b26`) | 25×23 each | `b26` with a hue shift |
| 3 | Fold pip `+n` (badge for overflow and depth 3+) | about 12×9 | text plate |
| 4 | Main avatar row for `error` (row 5, as `sprite_loader` already notes: "add row 5 for custom error anim") | 40×40 × 4 frames | stand row |
| 5 | Main avatar row for `blocked` (row 6) | 40×40 × 4 frames | idle row |

## 8. Preview notes

`room_layout_preview.png`: one room, 1 orchestrator (busy), 3 agents (thinking, blocked, error), 4 subagents (idle, done, busy, and one at depth 3 folded into `+1`), a legend with every state, and the counts plaque. `room_layout_tile4.png`: four rooms, light = worst state. Both are composed from the kit files above, the 50 px avatar sheets cropped to 40×40 (`ember_mage`, `forest_scout`, `frost_wanderer`) and the 32×32 placeholder subagent sheets, at 2× nearest neighbour. Room pools are drawn at 1.6× alpha so they read in a still image.

## Differences vs BLDG-SCHEMA

[`docs/building-scene.md`](../building-scene.md) wins on every point below. Sections refer to the numbered sections above.

| # | Topic | This proposal | BLDG-SCHEMA |
|---|---|---|---|
| 1 | Coordinates | Kit `(u, v, z)` with the `INDEX.md` formula (section 1). | Tiles `(x, y, floor)`, integers, room-local plus room `origin`; a floor is `FLOOR_Z = 3` height units. |
| 2 | Anchor | `INDEX.md` anchors, measured from the top (north) vertex of the tile. | Manifest anchor is the bottom-centre (south vertex) of the footprint: `anchor_manifest = (ax + (w - h) * 16, ay + (w + h) * 8)`; light pieces `(+0, +8)`. |
| 3 | Orchestrator spot | Tile `(1.5, 1.5)` (section 2). | `circle.spot` is an integer tile. Fractional spots fail validation. |
| 4 | Room shape | Fixed 10 × 8 room, four agent slots. | Each room comes from a layout file: `size` 4–16 per side, up to 8 `desks`, plus `sub_spots`, `plaque`, `light_points`, `door`, `prop_slots`. The section 1 and 2 tables should be rewritten as a `building/layouts/<name>.json` (task AG-3). |
| 5 | `span` and `set` | Wall runs and floors listed tile by tile ("u = 1…9"). Object sets are not named. | Use the optional `span: [w, h]` for floors and wall runs. The manifest's optional `set` tags each `o` piece (`dungeon`, `skulls`, `spells`, `tables`, `blood`, ...). A mixed `b01`–`b04` floor needs one entry per tile or per patch, up to the 512-entry `structure` cap. |
| 6 | Tiling 16 | A 4 × 4 lattice of compact 6 × 5 rooms on one floor, then paging by project (section 5). | `"16"` is a stair building: 4 floors of 2 × 2 rooms, `slot = floor * 4 + i`, optional `stairs`. Tiling `"4"` with origins `(0, 0)`, `(11, 0)`, `(0, 9)`, `(11, 9)` is valid (rooms may not overlap; gaps are allowed). |
| 7 | Room order and overflow | Rooms that need the user (blocked, error) first, then the newest; extra rooms go to more pages. | Slots are stable by node id: a new orchestrator takes the lowest free slot. Orchestrators with no free slot are counted in `building.more_rooms`, and the last slot's plaque shows `+n rooms`. No paging. |
| 8 | Agent overflow | Agents 5+ become a `+n` pip on the door. | Agents past the last desk add 1 each (plus their subtree) to the orchestrator's `badge_more`. The door is where the `blocked` bars go. |
| 9 | Subagent overflow | Subagents 4+ go on the third subagent's pip; three fixed offsets. | Extra subagents add to the parent agent's `badge_more`. `sub_spots` has up to 4 offsets (−3..3) and a `max_per_desk`. Depth 3+ on the depth-2 ancestor matches in both. |
| 10 | Props | One prop per node, next to its slot; `thinking` gets a crystal ball (`o11`), `busy` a cauldron (`o12`). | One prop per room, chosen from the room state and placed in `prop_slots` (`chest`, `skull`, `bench`). `busy` and `thinking` have no prop. |
| 11 | `blocked` prop | Gates `b21` and `b22` on the slot's two front edges. | One bars piece (`b21-reja-izq` or `b22-reja-der`, matching `door.side`) on `door.at`. |
| 12 | `error` decal | Adds `o21-mancha-de-sangre`. | `blood` is excluded by default (decision I). A layout that uses it needs `theme.allow_sets: ["blood"]`, and the scene adds no decals. |
| 13 | Node halos and name tags | Hue-shifted `b26` halo at each node's feet, plus a name tag in the state colour. | The scene actor has no halo or label field, and `light` is limited to `b27`–`b30` or `null`. Halos and tags are renderer extras, or need a schema version bump. |
| 14 | Animation timing | Flicker, pulse, and warn-blink timings (section 3). | Out of scope: "Animation timing is not part of this format." |
| 15 | `blocked` avatar row | Main row 0 (idle). | `sprite_loader.ANIM_ROW["blocked"]` is 3 (stand), with the amber mark telling it apart from `done`. Subagent row is `idle`, the same in both. |
| 16 | `done` subagent row | "dying, once, then removed". | `subskins.STATUS_TO_ROW["done"]` is `idle`. The dying row plays when the subchat closes, which is overlay behaviour, not a scene state. |
| 17 | `blocked` state | "needs: a `blocked` status" (section 6), defined as waiting on the user (permission prompt or question). | Already in code: `sessions.BLOCKED` (Claude permission or reply waits, `_line_blocked`), `cli_avatars/model/agent.py`, `events.STATE_SEVERITY`, `ANIM_ROW`, `STATUS_TO_ROW`. The CHAT-BLOCKED task (bus event, HUD, rooms) is still open. BLDG-SCHEMA's meaning is wider: waiting on anything outside the agent, such as a decision or a review. |
| 18 | Tree and depth | "needs: tree reader" and "needs: computed field" for subagents at depth 2+ and for depth (section 6). | CHAT-TREE now exists in `cli_avatars/model/tree.py`: `build_tree` gives `Node.depth` at any depth, stable opaque node ids (`kind:` plus 16 hex characters), `Tree.worst_state` per subtree, and `Tree.counts`. `building/scene.py` reads the tree, not `SessionInfo.parent_id` chains or `rooms.RoomCard`. |
| 19 | Counts | Four counts on the plaque (agents, subagents, conversations, open topics); the orchestrator count only in the header. | Room `counts` has five keys: `orchestrators`, `agents`, `subagents`, `conversations`, `open_topics` (`tree.COUNT_KEYS`). Folded nodes are counted. |
| 20 | Conversations and open topics | Conversations are chat nodes in the room's tree; open topics are matched on `project`. | Conversations are topics with any room node in `members`; open topics are those with status `open` or `waiting_on_user` (`Tree.counts`). |
| 21 | Room name | `RoomCard.project`, else `RoomCard.name`. | Room `title`: sanitised with `events.sanitize_text`, at most 80 characters, never a path or URL. |
| 22 | Missing sprites | Five sprites not in the kit (section 7): plaque, four small halos, the `+n` pip, main `error` row 5, main `blocked` row 6. | Plaque text and `+n` are drawn by the renderer, so the schema needs no sprite for them. Halos are not in the schema (row 13). The avatar rows do not change the schema. |
