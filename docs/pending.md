# What is left to do

Snapshot of `dev` at `ee22171` (27 Nov 2026). Planning input for the next round; it replaces no spec.

## State today

CLI Avatars runs as one Dungeon window plus a phone view on the LAN. Chats work with Claude Code and Grok Build
(room chats, task chats, New chat with resume, Grok as the default main orchestrator, Ask a bot through the file
bridge), each send starts the CLI with a fixed command and streams the reply. Tasks live on local boards with cards,
summaries, decisions, Needs you, quick capture, recap, standup and the backlog boss; the map shows rooms per topic and
orchestrator, the Throne Room start, the Oni Pit and the Crypt. The phone mirrors the map, tasks, decisions and chats
with writes behind a setting. Memory notes, usage per session and status colours landed this week. The Windows
installer and in-app Update work; the last pre-release is from this morning. `overlay.py` and the core modules are
frozen until the split sync (~30 Nov), so a few fixes wait for that.

Status words: **ready** (can start now), **waits** (who, for what), **frozen** (after ~30 Nov), **later** (not planned
yet). Size: S (hours), M (a day), L (several days).

## Chat

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Both lanes: one prompt to Claude and Grok, two tagged lanes; the composer's target gains **Both** | compare answers without retyping | waits maintainers for `grok login` on the PC | M | [room-chat.md](room-chat.md), [grok-chat.md](grok-chat.md) |
| Baton pass: hand a chat's context from Claude to Grok or back | switch CLI mid-task without losing the thread | waits maintainers for `grok login` | M | [grok-chat.md](grok-chat.md) |
| Send into a live Claude Code session started in a terminal, delivered by the hook or MCP | reach sessions the app did not start | waits maintainers to install the chat hook on the PC | M | [claude-hooks.md](claude-hooks.md) |
| Room summary pin (task chats have one, rooms do not) | reopen a room and see where it stands | ready | S | [room-chat.md](room-chat.md) |
| Confirm the Claude runner flags and env allowlist on Windows, then clear the 4 check markers in `cli_runner.py` | real chats already run; the markers are stale | waits maintainers for one Windows check | S | [room-chat.md](room-chat.md) |

## Tasks and board

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Board git store: one JSON per card, sync only on **Sync**, secret and path scan before commit | one board on several PCs | waits maintainers: still wanted (git as storage only)? | L | [board.md](board.md) |
| Agents addressed as `agent@machine`, notes relayed by the git store | multi-PC agents | waits the git store decision | M | [board.md](board.md) |
| `cli-avatars-emit board add/list/show/move/assign` | scripts without MCP (agents already have MCP task tools) | ready | S | [board.md](board.md) |
| `cli-avatars-emit doctor`: dry-run check of hook, MCP registration, token, UDP port | faster first-run support | ready, waits OK on the order of focuses | S | [mcp.md](mcp.md) |
| Calm layout inside the original skin: tasks and chats first, Dungeon as the summary | less noise, no restyle | waits maintainers: layout-only change or leave as is | M | [windowed-dungeon.md](windowed-dungeon.md) |

## Dungeon map and rooms

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Map config: rooms placed by hand in one file, door spots, generated corridors, 30 room skins | the map you design, not a fixed one | waits maintainers' OK on the 30-skin sheet | L | [map-config.md](map-config.md) |
| Create your room: custom rooms in small, mid, large | rooms for your own topics | waits OK on the size and flow preview | M | [orchestrator-rooms.md](orchestrator-rooms.md) |
| Object sets `torture` and `blood` off by default, opt-in per layout (`theme.allow_sets`, not built) | taste of the default map | waits maintainers' decision | S | [building-scene.md](building-scene.md) |
| Two orchestrator-room defaults were taken (meeting in the asker's room; orchestrators may add `proposed` cards to their own topic) | flip either if unwanted | waits maintainers to confirm | S | [orchestrator-rooms.md](orchestrator-rooms.md) |
| Wander: agents leave by the open door and come back (default off) | life on the map; lowest priority | later | S | [windowed-dungeon.md](windowed-dungeon.md) |

## Avatars and art

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Dungeon cast: goblin boss, original spider hero, rune warrior, spirits, samurai, onis, the boss oni in 4 stages | avatars that fit the Dungeon | waits OK on the cast preview | L | [adding-sprites.md](adding-sprites.md) |
| Magic circles: 4 elements plus a 4-frame loop | room floors with meaning | waits OK on both previews and the pick of the 4th element (light or earth) | M | [adding-sprites.md](adding-sprites.md) |
| Smooth animation for BunnyLot (8 of 9 sheets done) | same smoothness for every skin | waits `Sprites/BunnyLot.png` on `dev` | S | [adding-sprites.md](adding-sprites.md) |
| Grok sprite sheet with its own busy row (6 code markers use a hue-shifted stand-in) | Grok looks like Grok | waits the maintainers' artist | M | [grok-sessions.md](grok-sessions.md) |
| 16×16 decision bubble cell (5 code markers draw a stand-in) | decisions read at a glance | waits the maintainers' artist | S | [claude-hooks.md](claude-hooks.md) |
| 8 subagent skins (imp, mini Claude, winged light, cat, dog, dragon, drone, mini Grok), then swap the placeholders | subagents are told apart | waits the maintainers' artist | M | [adding-sprites.md](adding-sprites.md) |
| Dungeon kit assets still marked placeholder | the kit becomes official | waits maintainers' OK | S | [building-scene.md](building-scene.md) |
| 5 pixel UI touches (kit-framed docks, torch lamps, room badges, notification scroll, pixel cursor) | already proposed | waits maintainers' pick | S each | — |

## Phone

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| No phone-only items open; Both lanes, baton pass and the room summary come to the phone with their desktop item | parity | — | — | [phone-view.md](phone-view.md) |

## Bots and Grok

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Default Grok command taken from the real `grok --help` | Grok works with no `config.json` edit | waits maintainers for `grok --help` | S | [grok-chat.md](grok-chat.md) |
| Status for your bots: a small writer, or derived from `.grok/sessions` with no tool call | bot dots show the truth | waits maintainers: where bots run, Grok Build CLI or not | M | [bot-status.md](bot-status.md) |
| Grok adapter for the memory map (which `.md` files Grok reads) | memory map covers both CLIs | waits `grok login` and one hook check | M | [task-backend-and-memory-map.md](task-backend-and-memory-map.md) |
| MCP live on the PC: `pip install mcp`, register, smoke test | agents use the task tools for real | waits maintainers' OK | S | [mcp.md](mcp.md) |

## Memory

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Curator push to a real private remote (tested on a local repo only) | notes reach your other machines | waits maintainers to name the remote or run it once | S | [memory.md](memory.md) |

## Installer and release

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| New pre-release from current `dev` (the last one is from this morning, before usage and status colours) | testers get today's fixes | ready | S | [install-and-update.md](install-and-update.md) |
| Rebuild the committed `build/` exes | they predate Grok chat, MCP and the phone | waits maintainers (Windows build) | S | [install-and-update.md](install-and-update.md) |
| Tauri port: canvas rendering, window sidecar, one binary, auto-update | v1.0, no Python on the PC | later | L | — |

## Tests and flakes

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| Memory-map graph speed test fails under heavy load (23 ms vs 20 ms budget) | false reds in the full suite | frozen (core) | S | [task-backend-and-memory-map.md](task-backend-and-memory-map.md) |
| Spacing typo `rows =hall.snapshot` in `tests/_body_probe.py` | tidy; fix on the next touch of that file | ready | S | — |

## Docs

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| `TASKS.md`: about 20 open lines already shipped (list below) | the board misleads planning | ready | S | `TASKS.md` |
| `install-and-update.md` still says Grok chat "comes with ROOM-CHAT.6" | it shipped | ready | S | [install-and-update.md](install-and-update.md) |
| README: Download section, changelog, badges; `docs/download.md`; README docs tree is partial | new users find the installer | ready | S | `README.md` |
| `AI_OVERLAY.md`: archive notice, drop the embedded source; `CLAUDE.md` current state and key files | old docs say v0.1 | ready | S | `CLAUDE.md` |

Shipped but still open in `TASKS.md`: NEEDS-YOU.1 (`c22ed87`), WEB-PUSH (`63aad20`), QUICK-CAPTURE (`ebdc126`), BOARD.4
(`1b4ba32`), BODY (`3c07f0f`), PHONE-VOICE (`89e12cf`), MESSENGER (`00f40a7`), DAILY-RECAP (`f2c0cfb`), TIMELAPSE
(`3307594`), BACKLOG-BOSS (`71f9f58`), TASK-SUMMARY (`a67a1f9`), PROJECTS-P5 (`5a3d290`), ROOM-CHAT.6 Grok runner
(`f036631`), CLICK-THROUGH (`02e1029`), WEB.2 (`04cac5e`), WEB.4 (`584e0af`), UPDATE-VERSION (`6e4c01c`); TASKBACK.6
except Both; MIGRATE-REPO, SYNC-COPY and PORT-AG (the repo moved, commits go to `dev`); BLDG.1-3 and WIN-DUNGEON.4
(replaced by the Dungeon map).

## Frozen till ~30 Nov

| What | Why it matters | Status | Size | Doc |
|---|---|---|---|---|
| amongo shows at 100% on the desktop overlay (Dungeon and phone already 70%) | same size everywhere | frozen (`overlay.py`) | S | [adding-sprites.md](adding-sprites.md) |
| Sessions found on disk get no model or usage (`sessions.py`) | usage totals miss them | frozen (core) | S | [usage.md](usage.md) |
| Topic chip colour comes from core `AGENT_STATUS_COLOR`, not the shared palette | one palette everywhere | frozen (core) | S | [bot-status.md](bot-status.md) |
| Overlay features: pose map from hook events, avatar interaction, emotion bubbles, platform jump, name fade, sounds, portal v2, `fps`/`scale` keys | desktop overlay life | frozen, after the overlay split | M each | [architecture.md](architecture.md) |

## Waiting on you

1. OK or changes on the previews: 30 room skins, Create your room, Dungeon cast, magic circles (and light or earth).
2. `Sprites/BunnyLot.png` on `dev`.
3. `grok login` on the PC and the output of `grok --help`.
4. Where your bots run, and whether they use the Grok Build CLI.
5. Calm layout inside the original skin: yes, or leave as is.
6. Small calls: object sets on or off, the two orchestrator-room defaults, the memory remote, MCP install, the 5 UI
   touches, the order of the ready focuses.

## Open questions for Tuesday

1. What feels slow in chat today: the wait for the first words, the CLI start on each message, scrolling and redraw,
   or switching chats? A 20-second screen recording pins it down.
2. One CLI process kept alive per open chat (faster replies, more memory), or one start per message with resume (today)?
3. Typing while a reply streams: queue the next message, or stop the reply and send?
4. Where should chat live: the dock beside the Dungeon, a full-width chat view, or both; and is the phone equal?
5. Do you use Claude and Grok every day? That decides whether Both lanes and baton pass come first.
6. Order for the functional version: chat first, then tasks, then map and art, or another order?
