---
type: tasks
project: "[[Project - CLI Avatars]]"
status: active
tags: [cli-avatars, tasks, development]
updated: 2026-11-19
---

# CLI Avatars — Task Board

> Live task list for the `zz_cli_avatars/` overlay project.
> Full context: [[Project - CLI Avatars]] · Architecture: `CLAUDE.md` · Reference: `AI_OVERLAY.md`

## Scope

CLI Avatars helps Daniel manage tasks, follow the chats tied to each task and juggle many topics without overwhelm. It is not Watchtower and does not use Bitbucket or git PR data. The only PR-related features allowed: (a) reading a PR that Daniel explicitly tags on a task, and (b) an "Update version" button that pulls the latest app version, which comes only after a functional version exists. The Spidey_PR_Dashboard branch assets/dungeon-kit is only a shared workspace for Oscar's agents.

Process items (SYNC-COPY, PORT-AG, MIGRATE-REPO) are team workflow, not product features, and stay in scope.

---

## How tasks are tagged

Every task line is `- [ ] [EPIC][type] ID: description` (or `- [x]` when it is done). Each line has one epic and one type. Existing IDs stay. A done line keeps its checkbox. Commit and PR citations stay on the line.

### Epics (`[EPIC]`)

| Tag | Covers |
|-----|--------|
| CHAT | Chat and topics: P3 send box, decisions, topics, chat window |
| SRC | Sources: Claude hooks, Grok sessions, other CLI adapters |
| MCP | MCP server M1, M2, and M3 |
| OVL | Overlay and behaviors: walk, perches, portal, bubbles, HUD, spring, tray, sounds |
| ART | Skins, icons, 9-slice frame, sprite loader art rows |
| BUILD | Exe build, selftest, tests, flaky test |
| WS | Workspace: projects-by-status phase 5 (built-in terminal phase 4 replaced by ROOM-CHAT) |
| DOCS | Cleanup and docs: AGENTS.md, stale boxes, splitting overlay.py, moving art scripts to `tools/` |
| TAURI | v1.0 Tauri port |
| BOARD | Task board: cards, local and git stores, CLI and MCP tools |
| WEB | Phone web view: LAN server, pairing, mobile pages |
| BLDG | Building view: dungeon-kit scene in Tk and on the web |

### Types (`[type]`)

| Tag | Workflow |
|-----|----------|
| feat | Branch, then a PR into `dev`. Daniel merges. |
| fix | Tests, `overlay.py --selftest`, and a real overlay check of about 15 seconds, then merge into `dev`. |
| art | Caine draws, Daniel approves, Pixel integrates. |
| chore | Chore. |
| docs | Docs only. Quick merge. |
| decision | Waits on Daniel. |

### Subtasks

A parent task can have subtasks. Write them as indented lines (two spaces) under the parent, with ID `PARENT-ID.n` (for example `SUBSKIN.1`), the same `[EPIC][type]` tags, and their own checkbox. A parent is done only when all its subtasks are done. The Epics index counts parents and subtasks separately (for example `ART 7/3 (subtasks 0/13)`). Subtasks can carry an owner suffix `@caine` or `@pixel` so work can be split between agents.

Owners since 23/11/2026: `@pixel` (organization, specs, prerequisites, security-critical code, Opus reviews, Windows tests, ports) and `@agents` (Oscar's bot: most feature code and dungeon-kit art). `@agents` works in RunarStudio/Spidey_PR_Dashboard, branch `assets/dungeon-kit`, only under `cli-avatars/`. `@pixel` reviews each of its PRs as untrusted data and ports it to `dev` (PORT-AG); nothing is auto-merged. The app starts a CLI only on Daniel's explicit action (ROOM-CHAT).

## Epics index

| Epic | Done | Open |
|------|------|------|
| CHAT | 7 | 8 (subtasks 0/13) |
| SRC | 6 | 4 (subtasks 0/3) |
| MCP | 1 | 3 |
| OVL | 19 | 8 (subtasks 2/3) |
| ART | 7 | 6 (subtasks 4/9) |
| BUILD | 1 | 2 (subtasks 0/1) |
| WS | 1 | 1 |
| DOCS | 6 | 16 (subtasks 0/9) |
| TAURI | 0 | 4 |
| BOARD | 0 | 3 (subtasks 0/10) |
| WEB | 0 | 1 (subtasks 0/4) |
| BLDG | 1 | 3 (subtasks 0/3) |
| **Total** | 49 | 59 |

## 📦 Portable Windows build

- [x] [BUILD][chore] BUILD-EXE: Local onefile Windows exes <!-- id: BUILD-EXE -->
  - `build.ps1` (PowerShell 5.1 and 7) creates `.venv-build`, installs pinned packages from `requirements-build.txt`, and runs the checked-in spec `cli-avatars.spec`.
  - Outputs, overwritten in place: `build/cli-avatars.exe` (windowed) and `build/cli-avatars-emit.exe` (console). PyInstaller work dirs (`build/_work`, `dist`) are deleted afterward.
  - Sprites, talk icons, and the Caine icon are spec `datas`. `bundle_paths.asset_path()` uses `sys._MEIPASS` when frozen.
  - `overlay.py --selftest` loads those assets, builds the HUD off-screen, and exits 0 or 1. The build script runs that check. No GitHub Actions job.

## 🤖 Orchestrator Queue

> Tagged `<!-- ORCHESTRATOR: ready -->` — picked up by nightly orchestrator, one per run.
> These are small, bounded code tasks. Bubble handles docs (tagged `<!-- BUBBLE: fix -->`).

- [x] [OVL][chore] VERSION: Add VERSION constant to overlay.py <!-- ORCHESTRATOR: ready -->
  - Context: overlay.py has no version constant. The project is at v0.4 per CLAUDE.md and the project note.
  - Acceptance: Add `VERSION = "0.4"` as a module-level constant near the top of overlay.py (after imports, before class definitions). No other changes.
  - Guardrail: Only modify overlay.py. Do not change any logic, class, or function. One line added.

- [x] [OVL][feat] CONFIG-STUB: Add config.json loader stub to overlay.py (verified shipped, TASKS-EPICS) <!-- ORCHESTRATOR: ready -->
  - Context: The v0.4 roadmap calls for a config.json with fps, scale, and skins keys. overlay.py has no config loading yet.
  - Acceptance: Add a `load_config()` function that reads `config.json` from the same directory as overlay.py, returns a dict, and silently returns `{}` if the file is missing. Call it at the start of `OverlayApp.__init__()` and store the result as `self.config`. Do not yet use the config values anywhere else.
  - Guardrail: Only modify overlay.py. Do not change existing behavior. The overlay must still run correctly if config.json is absent.

---

## 📝 Documentation & Presentation Trail

> Bubble picks **one** item per run. Do not batch. Each item is one file, one change.
> Tag: `<!-- BUBBLE: fix -->`

- [ ] [DOCS][docs] DOCS-STALE-BOXES @agents: Reconcile stale checkboxes — check off v0.2/v0.3/v0.4 items already done per `Project - CLI Avatars.md` feature table (sprite_loader wired, click-through, HUD, system tray) <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-CLAUDE-STATE @agents: Update `CLAUDE.md` Current State section: change "v0.1" references to "v0.4 (functional)" and remove "not yet wired" notes that are now done <!-- BUBBLE: fix -->
- [x] [DOCS][docs] DOCS-README-CLONE: Verified 23/11: README already clones RunarStudio/cli-avatars. No change needed.
- [ ] [DOCS][docs] DOCS-README-DOWNLOAD @agents: Add "Download" section to README after Quick Start — GitHub Releases as distribution channel, placeholder: `[Download latest release →](https://github.com/RunarStudio/cli-avatars/releases)` <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-AI-OVERLAY-ARCHIVE @agents: Add archive notice to top of `AI_OVERLAY.md`: "This file documents v0.1. The project is now at v0.4. See `CLAUDE.md` and `overlay.py` for current state." <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-AI-OVERLAY-SOURCE @agents: Remove embedded source code blocks from `AI_OVERLAY.md` (sections 7–9: overlay.py, sprite_loader.py, claude_hooks_example.py) — replace each with one line: "See `<filename>` in the project root." <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-CHANGELOG @agents: Add Changelog section to README (after Roadmap): summarize v0.1→v0.4 milestones in 4 bullet points <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-DOWNLOAD-MD @agents: Create `docs/download.md`: install from source + "Prebuilt Windows executable: see GitHub Releases" + link placeholder <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-BADGES @agents: Add version + Windows badges to README header: `![version](https://img.shields.io/badge/version-v0.4-blue)` `![platform](https://img.shields.io/badge/platform-Windows-lightgrey)` <!-- BUBBLE: fix -->
- [ ] [DOCS][docs] DOCS-CLAUDE-FILES @agents: Tighten `CLAUDE.md` Key Files table: remove `assets/` row (assets live in `Sprites/`), add `tools/gen_ponmi.py` row, update architecture notes to mention skin picker and hue rotation <!-- BUBBLE: fix -->

---

## ✅ Done (v0.1 Baseline)

- [x] [OVL][feat] V01-OVERLAY: Full-screen transparent tkinter overlay (always on top)
- [x] [OVL][feat] V01-PHYSICS: Physics engine: gravity, floor collision, wall bounce, idle pauses, status-reactive speed
- [x] [ART][feat] V01-PROC-SPRITE: Procedural 8×8 pixel sprite renderer (no external assets needed)
- [x] [OVL][feat] V01-MULTI: Multi-avatar management (spawn/remove as sessions appear/disappear)
- [x] [OVL][feat] V01-HUD: HUD panel top-left: agent count, busy/thinking/subagent summary
- [x] [SRC][feat] V01-CLAUDE-SCAN: Claude Code session scanner (`~/.claude/projects/*/sessions/*.jsonl`)
- [x] [OVL][feat] V01-TERRAIN: Window terrain scanner (open windows → floor platforms via pywinctl)
- [x] [OVL][feat] V01-DEMO: Demo mode: 4 agents cycling all states when no real sessions found
- [x] [ART][feat] V01-SPRITE-LOADER: `sprite_loader.py`: SpriteSheet + SpriteRegistry fully implemented
- [x] [SRC][feat] V01-HOOKS-EXAMPLE: `claude_hooks_example.py`: UDP notification helper

---

## 🔴 v0.2 — Sprite Integration & Click-Through

### Sprite pipeline

- [x] [ART][chore] SPRITE-PNG: Convert JPG sprite sheets to PNG (verified shipped, TASKS-EPICS)
  - `python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png`
  - `python sprite_loader.py convert meowatar_orig.jpg assets/meowatar.png`
  - After converting: open in GIMP/Aseprite and remove solid background (make transparent)

- [x] [ART][feat] SPRITE-SKIN: Add `skin` field to `AgentInfo` (verified shipped, TASKS-EPICS)
  - `skin: str = "amongo"` in the `@dataclass` in `overlay.py`
  - Demo agents each get a different skin assigned

- [x] [ART][feat] SPRITE-REGISTRY: Import and wire `SpriteRegistry` into `overlay.py` (verified shipped, TASKS-EPICS)
  - `from sprite_loader import SpriteRegistry`
  - Instantiate as `REGISTRY = SpriteRegistry()` global
  - At startup (after tkinter root created): load sheets into REGISTRY with fallback if PNGs missing

- [x] [ART][feat] SPRITE-AVATAR: Pass registry to `Avatar.__init__()` (verified shipped, TASKS-EPICS)
  - Add `registry: SpriteRegistry` param, store as `self.registry`
  - Update `OverlayApp._tick()` to pass registry when spawning new avatars

- [x] [ART][feat] SPRITE-DRAW: Replace procedural sprite in `Avatar.draw()` (verified shipped, TASKS-EPICS)
  - Call `self.registry.get_photo(self.agent.skin, self.agent.status, self.frame)`
  - Keep `make_photo()` as fallback when registry returns None (no PNG loaded)
  - Resize `AVATAR_W`/`AVATAR_H` constants to match actual cell size (48×48 or 60×60)

### Click-through (Windows)

- [ ] [OVL][feat] CLICK-THROUGH @agents: Apply `WS_EX_TRANSPARENT` per hit-test so empty overlay passes clicks through and avatars stay clickable (after SPLIT.4)
  - Not done as of 23/11: no WS_EX_TRANSPARENT in the code. A global flag would break left-click on avatars.
  - File: `overlay.py`, in `OverlayApp.__init__()` after `overrideredirect(True)`
  - Guard: `if sys.platform == "win32":`
  - Code:
    ```python
    import ctypes, sys
    hwnd  = ctypes.windll.user32.GetParent(self.root.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)
    ```
  - Note: right-click to quit still works via canvas binding; left-click passes through to apps below

### Config

- [ ] [OVL][feat] CONFIG-LOADER @agents: Create `config.json` loader. overlay.py already reads config.json; finish the `fps` and `scale` keys if VERIFY-TICK finds gaps (after SPLIT.4)
  - Schema: `{ "fps": 20, "scale": 1.0, "skins": { "demo_0": "amongo", "demo_1": "meowatar" } }`
  - Load at startup in `OverlayApp.__init__()`, silently skip if file missing
  - Apply `fps` to `OVERLAY_FPS`, `scale` to registry `load()` calls

---

## 🟠 v0.3 — Richer Agent Interaction

- [x] [SRC][feat] UDP-LISTENER: UDP listener for instant hook events. Verified 23/11: shipped as F2 in events.py. The pose map below moves to POSE-MAP.
  - Superseded by **F2** (`<!-- id: F2 -->`): localhost listener, shared token, and `cli-avatars-emit`. The pose map below is still open.
  - Add `UDPListener` thread in `overlay.py` listening on port 47200
  - Parse events from `claude_hooks_example.py` and update `AgentInfo` directly (bypass poll delay)

  **Available Claude Code hooks (all safe if script exits 0):**

  | Hook | When | Can block? |
  |------|------|-----------|
  | `PreToolUse` | before each tool call | yes (exit ≠ 0 blocks) |
  | `PostToolUse` | after tool completes | no |
  | `Stop` | turn finished | no |
  | `Notification` | push notification sent | no |
  | `UserPromptSubmit` | user hits submit | yes (can modify input) |

  **Proposed avatar action map:**

  | Event | Payload | Avatar action |
  |-------|---------|---------------|
  | `PreToolUse` — Bash | tool name | run animation, speed boost |
  | `PreToolUse` — Read | tool name | lean / open-book pose |
  | `PreToolUse` — Edit/Write | tool name | pencil pose |
  | `PreToolUse` — Grep/Glob | tool name | crouch / search pose |
  | `PreToolUse` — Agent | tool name | look sideways (subagent spawn hint) |
  | `PostToolUse` | tool name + exit code | small bounce (success) or wince (error) |
  | `Stop` | — | sit down, yawn, go idle |
  | `Notification` | message | wave arms, speech bubble |
  | `UserPromptSubmit` | — | snap to attention |

- [ ] [SRC][feat] POSE-MAP @agents: Map hook events to avatar poses per the action map above (after SPLIT.4). (M)

- [x] [OVL][feat] SUBAGENT-SPAWN: Subagent spawn animation (fix/subagent-spring)
  - A child spawned for a live subagent uses `spring_mode` and `_apply_spring` every tick.
  - It hangs under the parent at `SPRING_REST`, damped. A fast or dragged parent cannot fling it, and a large `dt` stays finite.
  - When the task ends or the parent is gone, the child leaves spring mode and walks again.

- [x] [OVL][fix] SUBAGENT-LEASH: Keep a subagent inside a leash of its orchestrator (fix/subagent-spring)
  - `SUBAGENT_LEASH_MAX` is `3 * SPRING_REST`, measured from the parent's center. `config.json` `subagent.leash_px` overrides it when that value is a positive number.
  - Past the leash, the child is placed on the circle. Outward speed is removed so the correction does not jitter. This holds in spring mode, while the parent is dragged, and when the child walks or lands.
  - A walking child whose parent is still on screen turns around at ± leash on x. An orchestrator is not leashed.

- [ ] [OVL][feat] AVATAR-INTERACT @agents: Avatar-to-avatar interaction (after SPLIT.4)
  - When two idle avatars are within 60px: both stop and face each other for 2–4s
  - Emit a small speech bubble `💬` above both

- [ ] [OVL][feat] EMOTION-BUBBLES @agents: Emotion bubbles (after SPLIT.4)
  - Float above head for 1.5s then fade: 💭 thinking · 🔥 busy · ✅ done · ❌ error
  - Trigger on status transitions

- [ ] [OVL][feat] PLATFORM-JUMP @agents: Jump between window platforms (after SPLIT.4)
  - When avatar reaches a floor edge: check if adjacent platform is within jump range
  - Calculate jump velocity to land on target; execute jump animation (row 4)

---

## 🟡 v0.4 — UX Polish

- [x] [OVL][feat] TRAY: System tray icon (show/hide, mute, quit) (verified shipped, TASKS-EPICS)
  - Use `pystray` library: `pip install pystray`
  - Menu: Toggle Overlay / Mute Sounds / Quit

- [ ] [OVL][feat] NAME-FADE @agents: Name tags fade after idle timeout (after SPLIT.4)
  - Track `last_active_t` on Avatar
  - After 30s idle: fade label alpha to 30% via canvas `stipple`

- [ ] [OVL][feat] SOUNDS @agents: Optional sound effects (after SPLIT.4)
  - Short blip on status change (busy → done)
  - Toggle via config or system tray menu
  - Use `playsound` or `winsound` (Windows only)

- [x] [OVL][feat] HUD-DRAG: Draggable HUD panel (verified shipped, TASKS-EPICS)
  - Bind `<B1-Motion>` on HUD canvas items to move the panel

---

## 🟢 v0.5 — AIs talk to each other

- [x] [OVL][feat] F3: Icon-only speech bubbles on `chat` <!-- id: F3 -->
  - A `chat` event draws one allowlisted icon above the sending avatar (`source:id`). The same avatar queues; the bubble holds 3 s, then fades. When two are open, the newer one sits 4 px higher. Bubbles follow the avatar while it walks or perches. Subagent children are unchanged.
  - Art is `Sprites/talk/` (16×16 9-slice frame, separate 4 px tail, 9×9 icons). `Sprites/bubble.png` is the round character sheet (192×240), not a 9-slice, so it is not reused.
  - HUD row `💬 Talks N`: avatar pairs with a chat event in the last 10 s. Grey at 0, white from 1, one blink when a new pair starts.
  - Not in F3: free-text bubbles, emotion bubbles on status changes. Walking over to meet is **F4**.

- [x] [OVL][feat] F4: Avatars walk to meet on `chat` <!-- id: F4 -->
  - Same perch (the same window-top segment): both walk to its midpoint and stop 8 screen pixels apart, facing each other. Sprite width is already in screen pixels, so the gap is not scaled again.
  - Different windows, or either avatar on the floor: both walk off the perch and fall to the taskbar line, then meet at the midpoint of the centers they had when the chat arrived, 8 screen pixels apart. No teleport. A perch with no free edge cancels the meeting.
  - Subagent children are not a party to the meeting. While the parent is walking or talking they keep their offset on the spring line, one step behind.
  - States: IDLE, WALK_TO, MEET, TALK, RETURN. TALK holds while chat events for that pair keep arriving. About 10 s after the last one, they wander again. A pair that is already meeting does not restart. A third avatar waits until the current pair finishes.
  - A self-chat does not walk. A missing avatar or a vanished window cancels the meeting. Meeting points clamp to the screen and to the perch.
  - Bubbles still follow the speaker. The `💬 Talks N` row is unchanged. Nothing in the packet is executed.
  - Planner: `meetings.py`. Preview: `docs/media/meet-animation.gif`. Manual check: `docs/claude-hooks.md`.

- [x] [OVL][fix] F4-BUG1: Duplicated avatar in the meeting preview <!-- id: F4-BUG1 -->
  - Complaint: in `docs/media/meet-animation.gif` the left Caine is drawn twice, almost on top of itself, both on the perch and on the floor.
  - Cause: the preview pasted a second full-size copy of the parent's walk cell about 16 px away and called it a subagent. The overlay does not. Each main avatar is drawn once in `_tick`. A real subagent is a separate avatar, skin `bubble`, and only exists when that session has subagents. During a meeting it keeps its own offset on the spring line; it is not a clone of the parent's sprite.
  - Fix: the preview child is the bubble cell, one step behind the parent on the spring. It is not a second Caine.

- [x] [OVL][feat] F4-PORTAL: Glowing portal on the meeting point <!-- id: F4-PORTAL -->
  - A 40×40 portal opens on the surface where the pair will meet, as soon as they start walking. The anchor pixel (20, 36) sits on the perch line, or on the top edge of the floor. The same sprite is used for both. It scales with the avatars' integer factor and is drawn behind them.
  - Appear is 2 frames (ellipse 4→40 wide, beam 0→28), then a 4-frame loop while they walk, meet, and talk (ellipse height ±1, beam alpha 60%/45%). Return or cancel plays the 2-frame close. 200 ms per frame. No portal on a self-chat. One portal for the current pair.
  - Art is drawn in `portal.py` (ring `#7FDBFF`, white centre, shadow `#1B2A4A` at 50%, beam in three alpha bands, no outer glow). Ring thickness is 1 px in the app; 2 px is the light-background option. Preview: `docs/media/meet-animation.gif`. Sheet: `docs/media/meet-portal.png`.

- [x] [SRC][feat] F2: Internal event bus, localhost listener, and `cli-avatars-emit` <!-- id: F2 -->
  - `EventBus` is in-process and thread-safe. `PollingSource` publishes each scan. `EventSource` listens on UDP `127.0.0.1` only (default port 47200). With no packets, scan results are unchanged.
  - Shared token file in the per-user data directory, mode 0600 (Windows: user-only ACL). Reject missing tokens, packets over 2 KB, and rate-limit bursts. Strict schema; unknown fields dropped. `note` / `text` go to the rotating log `events.log`. The desktop bubble does not show them. A sanitised channel copy is **P3-CHAT-NOTE**.
  - States: `idle`, `busy`, `thinking`, `subagent`. Chat icons: `speech`, `question`, `ok`, `warn`, `error`, `thought`, `typing`. Channel queue: `channel/<room>.jsonl` in that data directory, never in the repo.
  - Not in F2: bubble rendering, walking to meet, Grok transcript parsing, MCP, Discord, git channel.

## 🟣 Phase 1 — Reliable status

- [x] [OVL][feat] P1-HUD: HUD counters per AI source <!-- id: P1-HUD -->
  - Every agent carries `source` (`claude`, `grok`, `emit`, …) from its SessionSource or from the emit event. A subagent inherits its parent's source.
  - The HUD shows one row per source that has sessions: `Claude 3 | busy 1 thinking 1 idle 1 | sub 2`. A total line counts subagents from every source, and each source row shows its own `sub` count. The `💬 Talks N` row stays.
  - `GrokBuildSource` is registered beside Claude. Live parsing is **GROK-SESSIONS**. It does not read auth or credential files. The sessions directory is `$GROK_HOME/sessions` or `~/.grok/sessions`.
  - Preview: `docs/media/hud-per-source.png`.

- [x] [SRC][feat] GROK-SESSIONS: Avatars for live Grok Build sessions <!-- id: GROK-SESSIONS -->
  - `GrokBuildSource` reads `<GROK_HOME or ~/.grok>/sessions/<encoded-cwd>/<session-id>/`. A session is live when `updates.jsonl` or `summary.json` changed within `STALE_AFTER` (the Claude constant). The agent id is the first 8 characters of the session id. The label is the summary title (`title`, `generated_title`, then `session_summary`), or the cwd folder name.
  - State comes from the tail of `updates.jsonl`: a tool call still in progress is busy, a thought chunk is thinking, a turn-ended update is idle. Unknown lines are skipped. Only that tail is read.
  - `subagents/*/meta.json` counts as children of the parent, the same model as Claude subagents. A child session in the tree is not a second orchestrator.
  - When the encoded cwd is a slug plus a hash, the folder name comes from the group's `.cwd` file. The stored project is that folder name only.
  - The HUD Grok row has its own mark and color. Until Caine's Grok sheet exists, new Grok avatars use a configurable hue (`grok.hue`, `grok.skin` in `config.json`). `TODO(Caine art)`.
  - `hooks/claude_chat_hook.py` tags `source=grok` when the payload has Grok fields or a transcript path under `.grok`. Claude payloads stay `source=claude`.
  - Never opened: auth, credential, and token files, `system_prompt.txt`, `prompt_context.json`, `chat_history.jsonl`, `signals.json`.

## 🟣 Phase 2 — Orchestrator rooms

- [x] [OVL][feat] P2-ROOMS: Rooms list of top-level sessions <!-- id: P2-ROOMS -->
  - A HUD button `Rooms`, next to Skins and Config, toggles a compact list. The walking desktop is unchanged and stays on screen while the list is open.
  - One card per orchestrator: the avatar's idle-frame thumbnail, its name, its source (Claude, Grok or Emit), the project folder name only, a state dot, and last activity as `Ns ago`. Subagents sit under the card as small rows with their own dots.
  - Dots, as Caine proposed: idle grey `#9a98b8`, busy blue `#4488ff`, thinking violet `#aa44ff`, subagent in the accent `#ffcf4a`.
  - Active orchestrators come first, newest activity first inside that group. Idle for more than 5 minutes is dimmed and marked `Zzz`.
  - A session whose newest result is an error (`failed`, or status `error`) shows the existing warn icon. When that signal is absent, the icon is skipped.
  - The boolean `rooms` in `config.json` is read at startup and written back only when that file already exists.
  - Model and tests: `rooms.py`. Preview: `docs/media/rooms-list.png`.

## 🟣 Phase 3 — Local chat

- [x] [CHAT][feat] P3-CHAT: Read-only local chat <!-- id: P3-CHAT -->
  - A HUD button `Chat`, next to Rooms, toggles one timeline. The walking desktop stays on screen. There is no send box.
  - The timeline is every message in the local channel logs (`channel/<room>.jsonl`), merged across rooms and sorted by time. The panel tails those files: a quiet poll reads no bytes again. A replaced file is read from the start because the old offset is no longer valid.
  - Each line shows `HH:MM`, the sender's idle thumbnail, the sender's name, its source (Claude, Grok or Emit), the allowlisted icon, and the note text when the line carries `note` or `text`. Control characters are stripped and the note is capped. The text is data. It is drawn only in this panel. Desktop bubbles stay icon-only, and nothing in a line is executed.
  - Filters: all rooms or one room, and all sources or one source. The list follows the newest line unless the reader has scrolled up.
  - `say --note` at the time of P3-CHAT stayed in the rotating log only. **P3-CHAT-NOTE** also copies a sanitised note onto the channel file. The bubble stays icon-only.
  - Model and tests: `chatlog.py`. Preview: `docs/media/local-chat.png`.

- [x] [CHAT][feat] P3-CHAT-NOTE: `say --note` is copied into the channel log <!-- id: P3-CHAT-NOTE -->
  - `cli-avatars-emit say --note` still appends the rotating log. It also appends one channel record. The note uses the Chat panel's sanitisation: control characters stripped, 240 characters, icon on the allowlist.
  - The append keeps the channel directory lock and the owner-only ACL. The note is data. Nothing in it is executed. The desktop bubble stays icon-only.
  - The Chat panel shows the line on its next tail.

- [x] [CHAT][feat] P3B-SEND: Local send box and per-agent inbox <!-- id: P3B-SEND -->
  - Inbox files are `inbox/<agent_id>.jsonl` in the per-user data directory, with the same owner-only ACL and atomic append as the channel. The Chat panel Send button writes those files and one channel line. It does not start a process and it does not open a socket.
  - To is one agent, several agents, or All. All is the rooms registry (top-level sessions and their sub rows). Demo avatars are not included.
  - Schema: `id`, `ts`, `from` (`user` or an agent id), `to` (list), `room` / `topic` (default `general`), `kind` (`msg`; `decision` and `decision_answer` are reserved), `text` (sanitised, 2000), `reply_to` optional.
  - `inbox read --agent ID [--since ID] [--json]` prints unread rows and stores the cursor at `inbox/<agent_id>.cursor`. `reply --agent ID --to MSG --note "..."` appends the reply to the channel so the panel shows it.
  - Schema: `docs/chat-schema.md`. Hook and agent instructions: `docs/claude-hooks.md`. Preview: `docs/media/chat-send.png`.

- [x] [CHAT][feat] P3C-DECISIONS: Decision cards in local chat <!-- id: P3C-DECISIONS -->
  - `cli-avatars-emit decide --agent ID --room ROOM --question "..." --option a="..." --option b="..."` stores a kind `decision` (uuid, status `open`) on the channel and in `decisions.jsonl`. Two to six options, letters a–f with no gaps. Each option is sanitised and capped at 120 characters. The question is capped at 240. The app does not execute the question or the options.
  - The Chat panel Decisions tab lists open cards (thumbnail, name, room, question, lettered buttons) and a short history of answered ones. Choosing a letter writes kind `decision_answer` (`decision_id`, `choice`, `ts`, `from` `user`, `text` the chosen label) to that agent's inbox and the channel, and marks the decision answered. A second answer, or an unknown id, is rejected.
  - `inbox read` returns `decision_answer` rows with the other messages. `decisions list [--open] [--json]` lists the index. The HUD row is `Decisions N`.
  - While a decision is open, the desktop avatar shows a `decision` bubble. The icon is on the allowlist. The glyph is a code placeholder (`TODO(Caine art)`) until the 16×16 cell arrives. No new sprite file.
  - Schema: `docs/chat-schema.md`. How an agent asks and reads the answer: `docs/claude-hooks.md`. Preview: `docs/media/chat-decisions.png`.

- [x] [CHAT][feat] P3D-TOPICS: Topics keep AI context small <!-- id: P3D-TOPICS -->
  - A topic is the room id already stored on channel, inbox, and decision records. Unknown rooms become an open topic. Files are `topics/<id>.json` in the per-user data directory, owner-only, with the same directory lock (timeout, handle closed before the lock returns).
  - Fields: id, title, project (folder name only; a path is rejected), branch, status (`open`, `waiting_on_user`, `done`), members, summary (1500), pins (at most 30, each 240, kind `fact` or `decision`), created, updated.
  - `topic show` returns only the summary, the pins, and the last 10 messages, plus `needs_summary` when more than 50 messages arrived since the summary was replaced. The Chat panel shows the last 200 messages per topic. The jsonl on disk is not deleted.
  - The Rooms list is topics grouped by project: status chip, member thumbnails, open decision count, and the existing per-orchestrator state dots. Clicking a topic filters Chat and the send box. Answered decision cards show a Pin button. Pins in the header have Unpin. Nothing is pinned silently.
  - The app stores, shows, and notifies. It does not execute text and it does not call a model. Summaries are written by an agent through emit, or by the person.
  - Schema: `docs/chat-schema.md`. Protocol: `docs/claude-hooks.md`. Preview: `docs/media/chat-topics.png`.

- [x] [SRC][feat] P3E-HOOKS: Claude Code sessions use the local chat <!-- id: P3E-HOOKS -->
  - `hooks/claude_chat_hook.py` is a stdlib hook. It reads the official Claude Code JSON on stdin (`session_id`, `cwd`, `hook_event_name`, `transcript_path`). The agent id is the first 8 characters of `session_id`, the same id `ClaudeJsonlSource` takes from the transcript file name. The topic id defaults to the cwd folder name, as a slug.
  - SessionStart and UserPromptSubmit print a short context block (topic summary, pins, unread messages and decision answers) and mark those messages read. Nothing new prints nothing. Output is capped at 2000 characters. `needs_summary` counts as new.
  - Stop emits `idle`. When `chat.auto_notes` is true (the default), a sanitised note from the last assistant message (240 characters) is stored with `say --note`. Set `chat.auto_notes` to false to disable it. A Stop that is already continuing does not store a second note.
  - Any failure exits 0. Store locks time out. The script does not run message text.
  - `cli-avatars-emit hooks install` merges SessionStart, UserPromptSubmit, and Stop into `%USERPROFILE%\.claude\settings.json`. `--dry-run` is the default and prints a diff. `--apply` writes a timestamped backup first and is idempotent. `hooks uninstall --apply` removes only those entries.
  - Agent instructions: `docs/agent-chat-protocol.md`.

- [x] [CHAT][feat] P3F-CHATWIN: Discord-style chat window <!-- id: P3F-CHATWIN -->
  - `ChatWindow` is the main chat window: topics grouped by project (status chip, unread count, open-decision count), the selected thread (clock, thumbnail, name, source, icon, note, decision cards with lettered buttons and Pin), a collapsible summary and pins, and a composer. The right column lists active avatars, with subagents under their orchestrator. The window is resizable. When `config.json` already exists, `chat.window` remembers x, y, width, and height.
  - Daniel talks to orchestrators. `routing.py` resolves the composer. Defaults: a Claude avatar or a Claude subagent writes to the top-level Claude session (the parent id). The Grok avatar writes to the live Grok session id, or the stable id `grok` until a session exists. `chat.routes` in `config.json` overrides this. The To chip shows the resolved recipient and can pick another orchestrator or All orchestrators. Subagents never receive the person's message directly.
  - A left-click on an avatar, without dragging, opens that avatar's topic addressed to its orchestrator. A click on a subagent opens the parent's topic. Dragging and right-click stay as they were. The HUD Chat button opens the same window.
  - The orchestrator forwards work onward and posts the result with `cli-avatars-emit say --note` or `reply`. The app stores and shows that text. It does not execute it and it does not start a CLI.
  - `--selftest` builds the window off-screen from simulated rows. Preview: `docs/media/chat-window.png`. Protocol: `docs/agent-chat-protocol.md`.

## 🔌 Phase 4 — Local MCP

- [x] [MCP][feat] MCP-M1: Phase 1 local MCP server <!-- id: MCP-M1 -->
  - `python -m cli_avatars_mcp` is a stdio FastMCP server. It does not open a port.
  - Project records are `projects/<slug>.json` in the per-user data directory (`%LOCALAPPDATA%\cli-avatars`, or the platform directory `events.app_data_dir()` already uses). Writes take `directory_lock`.
  - Fields: slug, name, path (folder, stored and not opened), repo url, branch, status (`idea`, `active`, `paused`, `done`), requirements, key files, key-values, linked topic slugs.
  - Read tools: `projects_list`, `project_get`, `topics_list`, `topic_show`, `decisions_list`, `kv_get`.
  - Caller writes: `status_set` emits the same loopback state event the avatars consume. `say` posts one topic-channel message as `emit:mcp`.
  - Resources: `project://<slug>` and `project://<slug>/requirements`.
  - `python -m cli_avatars_mcp install` is a dry-run. `--apply` backs up, then merges the Claude user config and `~/.grok/config.toml`. `uninstall` removes only that registration. Nothing in a tool argument is executed.
  - Docs: `docs/mcp.md`.

- [ ] [MCP][feat] MCP-M2 @agents: Project, requirements, and key-value writes <!-- id: MCP-M2 -->
- [ ] [MCP][feat] MCP-M3 @agents: Local memories add and search <!-- id: MCP-M3 -->

## 🔵 v0.5 — Tauri Port

- Step 1 done: SessionSource adapter layer (ClaudeJsonlSource)

- [ ] [TAURI][feat] TAURI-PIXI: Port rendering to PixiJS / HTML5 Canvas inside Tauri webview
- [ ] [TAURI][feat] TAURI-SIDECAR: Rust sidecar for window enumeration (faster than pywinctl)
- [ ] [TAURI][feat] TAURI-BINARY: Cross-platform binary (no Python install required)
- [ ] [TAURI][feat] TAURI-UPDATE: Auto-update mechanism

---

## Out of scope (Daniel 2026-11-23)

Product features only (see Scope). Team process items remain on the board elsewhere.

- [ ] [BOARD][feat] BOARD.2 @agents: GitStore (one JSON file per card, union-merged events.jsonl), store auto-detect, local commits, pull/push only on explicit Sync, secret scan before commit. (M) (pending Daniel confirmation: git used only as storage/sync, not PR data)
- [ ] [SRC][feat] NOTIFY.2 @agents: Machine id in the data dir; agents addressed as agent@machine; the git store relays notes for other machines on their next Sync. (M) (pending Daniel confirmation: git used only as storage/sync, not PR data)

---

## Reference

| Doc | Path |
|-----|------|
| Full project reference (v0.1) | `AI_OVERLAY.md` |
| Claude Code project guide | `CLAUDE.md` |
| Sprite sheet format & Stream Avatars convention | `AI_OVERLAY.md` → Sprite Sheet Format |
| Local MCP server (M1) | `docs/mcp.md` |
| Python concepts glossary | `AI_OVERLAY.md` → Python Concepts Glossary |

- [x] [OVL][fix] FIX-HUD-PADY: the overlay crashed at startup (Tk Label pady given as a tuple, TclError 'expected screen distance'), so no avatars appeared; padding moved to pack().

- [x] [CHAT][fix] FIX-CHATWIN-COLS: the chat window's centre column collapsed because the side frames grew to fit their packed children; use pack_propagate(False).

## Backlog

- [ ] [BUILD][chore] REBUILD-EXE @pixel: Rebuild the `build/` executables. They are stale after Grok and MCP. Repeat after SPLIT.5, after batch 2 ports, and at the end.
- [ ] [ART][feat] SUBSKIN: subagent skins, 32×32 sprites, 6-colour palette; flying skins float above the parent, ground skins hang below (spec from Daniel, DD thread 19/11/2026)
  - [x] [ART][feat] SUBSKIN.1 @pixel: 32×32 subagent sheets with a fly or ground mode (feat/subagent-skins)
    - The sprite registry reads `Sprites/subagents/manifest.json`. Each skin has its own frame size (these sheets are 32×32, not a hard-coded 40) and `mode` of `fly` or `ground`.
    - Rows follow the Stream Avatars layout. A missing row falls back to the first row that has frames.
  - [x] [OVL][feat] SUBSKIN.2 @pixel: fly children hover above the parent, ground children hang below (feat/subagent-skins)
    - A fly child's rest point is `SPRING_REST` above the parent's head, with a small bob. The spring line is drawn upward from the head.
    - Ground children hang under the parent as before. `SUBAGENT_LEASH_MAX` and `subagent.leash_px` apply to both. Orchestrators are not spring-driven.
  - [x] [ART][feat] SUBSKIN.3 @pixel: placeholder sheets for the eight planned subagent skins (feat/subagent-skins)
    - `tools/gen_subskin_placeholders.py` draws the sheets. They are code, not commissioned art. `TODO(Caine art)`.
    - imp, 4-legged Claude (`claude4`), cat, dog, and little Grok are ground. Winged light, dragon, and mini drone fly. Six colours max, a PH mark, and `placeholder: true` in the manifest.
  - [x] [OVL][feat] SUBSKIN.4 @pixel: assign a subagent skin from config and keep it (feat/subagent-skins)
    - `config.json` key `subagent.skins` has `mode` of `random`, `round_robin`, or `fixed`, an optional `list`, and a per-orchestrator `fixed` map.
    - Default is round-robin over the available subagent skins, by child index. A child keeps the skin it was spawned with.
  - [x] [ART][decision] SUBSKIN.5: Decided 21/11: Caine already drew the skins; integration parked until he pushes.
  - [ ] [ART][art] SUBSKIN.6 @caine: imp (ground)
  - [ ] [ART][art] SUBSKIN.7 @caine: mini 4-legged Claude (ground)
  - [ ] [ART][art] SUBSKIN.8 @caine: little light with wings (fly)
  - [ ] [ART][art] SUBSKIN.9 @caine: cat (ground)
  - [ ] [ART][art] SUBSKIN.10 @caine: dog (ground)
  - [ ] [ART][art] SUBSKIN.11 @caine: dragon (fly)
  - [ ] [ART][art] SUBSKIN.12 @caine: mini drone (fly)
  - [ ] [ART][art] SUBSKIN.13 @caine: mini Grok (ground)
  - [ ] [ART][feat] SUBSKIN.14 @pixel: integrate each delivered sheet and remove its placeholder
  - [x] [ART][feat] SUBSKIN.15 @pixel: idle / working / dying states for subagent skins (dying = subchat closing) (feat/subagent-dying)
    - Subagent sheets use three rows: idle (4), working (4), dying (4). Busy and thinking play working. A missing row falls back to the first row that has frames.
    - When the subchat closes, or the parent avatar goes away, the child plays dying once (4 frames at 120 ms). The spring line shrinks. The child ignores the leash and is not pulled if the parent is dragged. Then the avatar is removed.
- [ ] [ART][art] BLDG-KIT: dungeon kit imported to Sprites/dungeon_kit/ (placeholder, pending owner OK)
- [ ] [ART][feat] GROK-SKIN-BUSY: Sprite loader uses its own busy row per `docs/grok-skin-spec.md` once Caine's sheet lands. Sheet 40×40, 4 cols × 6 rows: idle 4, walk 4, thinking 2, done 2, subagent 2, busy 2.
- [ ] [ART][art] CAINE-SKIN: Caine draws the skin sheet.
  - Each subagent sheet needs idle, working, and dying rows (4 frames each). Dying plays when the subchat closes.
- [ ] [OVL][feat] PORTAL-V2 @agents: Portal ring 2px plus a particle burst (Daniel 21/11) (after SPLIT.4). (M)
- [x] [BUILD][fix] FLAKY-TEST @pixel: Fix the flaky test. (daily 2026-11-23)
- [x] [DOCS][docs] AGENTS-MD: Add `AGENTS.md`. (chore/cleanup-agents-md)
- [x] [WS][decision] TERMINAL-P4: Replaced by ROOM-CHAT (Daniel 23/11).
- [ ] [WS][feat] PROJECTS-P5 @agents: Projects by status, workspace phase 5 (after MCP-M2 and CHAT-TREE). (L)
- [ ] [SRC][chore] CLAUDE-HOOK-INSTALL @pixel: Approved 21/11. On SpiderHost: back up ~/.claude/settings.json, apply the chat hook, live check.
- [ ] [MCP][chore] MCP-LIVE @pixel: Approved 21/11. On SpiderHost: pip install mcp, stdio smoke test, `python -m cli_avatars_mcp install --apply` (backs up first). The Grok half waits on GROK-LOGIN.
- [x] [DOCS][chore] CLEAN-HOOKS-EXAMPLE: Drop `claude_hooks_example.py`. (chore/cleanup-agents-md)
- [x] [DOCS][chore] CLEAN-ART-SCRIPTS: Move `gen_ponmi.py` and `gen_meowatar_gifs.py` to `tools/`. (chore/cleanup-agents-md)
- [x] [DOCS][decision] SPLIT-OVERLAY: Yes, modular and optimized (Daniel 21/11). Work is SPLIT.1–.5.
  - [x] [DOCS][docs] SPLIT.1 @pixel: Design doc docs/architecture.md: nested package map, import rules, overlay.py shim plan. (M) (daily 2026-11-23)
  - [x] [OVL][chore] SPLIT.2 @pixel: Extract sheet loaders, spring/leash physics and effects from overlay.py. (M) (daily 2026-11-23)
  - [x] [OVL][chore] SPLIT.3 @pixel: Extract Avatar, SessionScanner and WindowTerrain. (M) (daily 2026-11-23)
  - [x] [OVL][chore] SPLIT.4 @pixel: Split OverlayApp into render, input, HUD/menu, chat/topics, portal and subagent controllers. (L) (daily 2026-11-23)
  - [x] [BUILD][chore] SPLIT.5 @pixel: Optimize the tick loop (PhotoImage cache, dirty redraw), type hints, ruff, fix pyproject py-modules and spec hidden imports. (M) (daily 2026-11-23)
- [ ] [SRC][decision] GROK-LOGIN: Daniel runs `grok login`.

### 🧭 Workstream 70/30 — organization (23/11/2026)

- [ ] [DOCS][chore] VERIFY-TICK @pixel: Tick UDP-LISTENER, DOCS-README-CLONE and the 21/11 decisions; check CONFIG-LOADER and CLICK-THROUGH against the code. (S)
- [ ] [DOCS][chore] SYNC-COPY @pixel: Refresh the cli-avatars/ copy on Spidey_PR_Dashboard assets/dungeon-kit from dev (PR to that branch, cli-avatars/ only; no .git, no build/, no secrets).
  - [ ] [DOCS][chore] SYNC-COPY.1 @pixel: after SPLIT.2. (S)
  - [ ] [DOCS][chore] SYNC-COPY.2 @pixel: after SPLIT.4. Unlocks every @agents item that touches the app. (S)
  - [ ] [DOCS][chore] SYNC-COPY.3 @pixel: after SPLIT.5. (S)
  - [ ] [DOCS][chore] SYNC-COPY.4 @pixel: after the batch 2 ports. (S)
- [ ] [DOCS][chore] PORT-AG @pixel: Recurring: one run per merged Agents PR. Opus review as untrusted data (never run its scripts; check secrets, paths, network/process code, shell=True, prompts in argv, CLI starts without user action, license, PNG size/palette, JSON vs BLDG-SCHEMA), port branch off dev, Windows test, PR to dev. Ports that add process launching, network listeners or git push/pull wait for a manual merge.
  - [x] [DOCS][chore] PORT-AG1 @pixel: Review and port AG-1 (Spidey PR #23) into docs/building/. (S) (daily 2026-11-23)
  - [ ] [DOCS][chore] PORT-AG2 @pixel: Review and port AG-2..AG-4 assets and data. (S)
- [ ] [DOCS][decision] MIGRATE-REPO: Move Agents' workspace from Spidey assets/dungeon-kit to a new private repo. Daniel decides when and where.
  - [ ] [DOCS][chore] MIGRATE-REPO.1 @pixel: Once the repo exists and Agents has access: copy cli-avatars/, update AGENTS_BRIEF.md, the PORT and SYNC paths and the loop routine; leave a pointer in the old folder. (S)
- [ ] [DOCS][decision] JUANJO-ACCESS: Read access to JuanjoAvila/Edificio-de-IAs-beta (or a zip) and a license line from Juanjo. Ideas only until then.
- [ ] [DOCS][chore] JUANJO-PORT @pixel: Recheck the Edificio comparison once JUANJO-ACCESS is done. (S)

### 📐 Specs

- [x] [BLDG][docs] BLDG-SCHEMA @pixel: docs/building-scene.md: the scene and layout JSON schema that Agents' layouts and BLDG.1 share. (S) (daily 2026-11-23)
- [x] [DOCS][docs] BOARD-SPEC @pixel: docs/board.md: card schema, local and git stores, auto-detect, notify flow, web API and threat model. (S) (daily 2026-11-23)

### 💬 Chat tree and sending

- [ ] [CHAT][feat] CHAT-HARNESS-READ @agents: Read agent specs from each harness (Claude Code user and project agents, hooks config; Grok harness) read-only, as data. New module harness.py, with tests. (M)
- [x] [CHAT][feat] CHAT-TREE @pixel: Recursive tree project → orchestrator → agents → subagents at any depth, built from live sessions, with a pluggable spec source that CHAT-HARNESS-READ fills; stable node ids; one API for rooms, Building and web. (M) (daily 2026-11-23)
- [x] [CHAT][feat] CHAT-BLOCKED @pixel: New 'blocked' agent state (waiting on a decision, permission or reply), emitted on the bus and shown in the HUD and rooms. (S) (daily 2026-11-23)
- [ ] [CHAT][feat] CHAT-COUNTS @agents: Counts of orchestrators, agents, subagents, conversations and open topics per project and in total, from CHAT-TREE. (S)
- [ ] [CHAT][feat] CHAT-SEND-CLAUDE @agents: MVP1: send to a live Claude Code session through its inbox, delivered by the hook or MCP; explicit click or Enter only (after CLAUDE-HOOK-INSTALL). (M)
- [ ] [CHAT][feat] CHAT-SEND-GROK @agents: MVP2: the same for Grok sessions. Blocked by GROK-LOGIN. (M)

### 🗨️ Room chat (replaces TERMINAL-P4)

- [ ] [CHAT][feat] ROOM-CHAT: One orchestrator chat per room/topic. Clicking an avatar or room opens it; it starts Claude Code and/or Grok CLI only on Daniel's explicit action, and everything is logged to the topic and board.
  - [x] [DOCS][docs] ROOM-CHAT.0 @pixel: docs/room-chat.md spec and threat model; update the CLI rule in AGENTS.md, CLAUDE.md and README. (S) (daily 2026-11-23)
  - [ ] [CHAT][feat] ROOM-CHAT.1 @agents: Room model: topic, participants (claude, grok), working dir picked by Daniel and stored only in the per-user data dir. (S)
  - [x] [CHAT][feat] ROOM-CHAT.2 @pixel: cli_runner: allowlisted binaries, fixed argv, shell=False, prompt on stdin, cwd = room dir, one process per room, timeout, Stop, output cap; fake-CLI tests. Security-critical. (M) (daily 2026-11-23)
  - [ ] [CHAT][feat] ROOM-CHAT.3 @agents: Parse stream-json into sanitised topic messages and a board log entry per prompt; nothing executed. (M)
  - [ ] [CHAT][feat] ROOM-CHAT.4 @agents: Chat pane opened by clicking an avatar or room; target picker Claude / Grok / Both; Enter sends the typed prompt (after SPLIT.4). (M)
  - [ ] [CHAT][feat] ROOM-CHAT.5 @agents: 'Both' sends one prompt to both CLIs, shown in two separate tagged lanes. (S)
  - [ ] [CHAT][feat] ROOM-CHAT.6 @agents: Grok runner (MVP2). Blocked by GROK-LOGIN. (M)
  - [ ] [CHAT][feat] ROOM-CHAT.7 @agents: Resume the room's session and pin a room summary. (S)

### 📋 Board (no Slack)

- [ ] [BOARD][feat] BOARD: Local task board of cards linked to topics. No Slack.
  - [ ] [BOARD][feat] BOARD.1 @agents: board/ package, Card model and LocalStore in the per-user data dir (owner-only ACL, directory lock, atomic writes), tests. Optional `pr` field: GitHub URL Daniel tags on the card only; read that tagged PR when implemented — no automatic forge/CI fetch. (M)
  - [ ] [BOARD][feat] BOARD.3 @agents: cli-avatars-emit board add|list|show|move|assign, and MCP tools board_list, card_get, card_add, card_move. (M)
  - [ ] [BOARD][feat] BOARD.4 @agents: Board tab in ChatWindow: columns, filter by topic and project, move a card (after SPLIT.4). (M)
- [ ] [SRC][feat] NOTIFY: Grok and Claude on this machine get board, inbox and decision news.
  - [ ] [SRC][feat] NOTIFY.1 @agents: The chat hook adds the agent's open cards to the SessionStart / UserPromptSubmit context block (capped at 2,000 chars). (S)
  - [ ] [SRC][feat] NOTIFY.3 @agents: cli-avatars-emit doctor: dry-run check of the hook, MCP registration, token and UDP port. Prints fixes, writes nothing. (S)

### 📱 Phone view

- [ ] [WEB][feat] WEB: Phone view served by the app on the LAN. Off by default.
  - [ ] [WEB][feat] WEB.1 @agents: webui/ on stdlib ThreadingHTTPServer: read-only JSON API plus SSE, binds 127.0.0.1, its own web token, pairing to an HttpOnly cookie, tests. Runs standalone with python -m webui. (M)
  - [ ] [WEB][feat] WEB.2 @agents: Mobile pages in vanilla JS, no build step: topics, chat timeline, board, decisions, agents. Read-only. (M)
  - [ ] [WEB][feat] WEB.3 @agents: LAN opt-in: one interface IP, QR pairing link in the HUD, rotate token, firewall doc (after SPLIT.4). (S)
  - [ ] [WEB][feat] WEB.4 @agents: Writes behind web.allow_writes: send, answer a decision, move a card; CSRF header, rate limit, same sanitisers. (M)

### 🏰 Building view

- [ ] [BLDG][feat] BLDG: Isometric building view of orchestrators and subagents.
  - [ ] [BLDG][feat] BLDG.1 @agents: building/scene.py from CHAT-TREE and the BLDG-SCHEMA layouts: one room per orchestrator, worst-state light, +n badge past depth 2, counts plaque; scene JSON shared by Tk and web; tests. (M)
  - [ ] [BLDG][feat] BLDG.2 @agents: Tk Building window (a Toplevel): 2x integer scale, cached room bitmaps with lights prebaked by Pillow, avatars redrawn on top (after SPLIT.4). (L)
  - [ ] [BLDG][feat] BLDG.3 @agents: Web Building view: canvas renderer of the same scene JSON, additive lights, live over SSE. (M)
- [x] [BLDG][docs] AG-1 @agents: Room layout and state→kit map (Spidey PR #23). Port pending: PORT-AG1.
- [ ] [ART][art] AG-2 @agents: Five sprites: counts wall plaque, 4 small state halos, +n badge, avatar rows for error and blocked.
- [ ] [BLDG][docs] AG-3 @agents: 4-room and 16-room building layouts as JSON in the BLDG-SCHEMA format.
- [ ] [ART][docs] AG-4 @agents: Sprites/dungeon_kit/manifest.json: anchor, footprint, category and light flag for each piece.

### 🗂️ Task backend and memory map

See [`docs/task-backend-and-memory-map.md`](docs/task-backend-and-memory-map.md) (design, mockup `docs/img/dungeon-tasks-memmap-mockup.png`). Order and fit with WIN-DUNGEON.4–.8: section 5.1 of that doc.

- [ ] [BOARD][decision] TASKBACK-DEC: Daniel picks decisions A–M in section 6 of docs/task-backend-and-memory-map.md (each has a recommended default).
- [ ] [BOARD][feat] TASKBACK: One registry owns tasks (board cards), topics and chats; AIs only change status and progress through a narrow Agent API; chat dock calls one CLI or the topic orchestrator.
  - [ ] [BOARD][chore] TASKBACK.1 @pixel: Port BOARD.1 (board/model.py, board/store.py, tests) from Spidey PR #27 via PORT-AG; amend docs/board.md with `progress`, `status_note`, kinds `progress`/`status`, optional `via`. Done when the ported and new board tests pass and bad progress/via values are rejected. (S)
  - [ ] [BOARD][feat] TASKBACK.2 @pixel: `registry/` package: full API, AgentApi, policy (agent transitions, ownership, rate limits), lock order. Security-critical. Done when tests prove agents cannot create (switch off), delete, retitle, reassign, reach `done` or touch cards they do not own, and two processes serialise on one card. (after TASKBACK.1) (M)
  - [ ] [BOARD][feat] TASKBACK.3 @agents: MCP tools task_list, task_get, task_status, task_progress, task_check, topic_state; emit `task status|progress|check`; task_propose behind `registry.agents_may_create`. Replaces the MCP half of BOARD.3. Done when every tool is tested, calls AgentApi only, and docs/mcp.md lists them. (after TASKBACK.2 and the MCP-M2 port) (M)
  - [ ] [BOARD][feat] TASKBACK.4 @agents: Repoint emit, MCP say, the hook note and chat send to the registry; agent updates show as one `emit:registry` thread line; folds in NOTIFY.1 (open cards with progress in the hook context, 2,000 chars). Done when existing tests stay green and a progress call shows one line. (after TASKBACK.2) (S)
  - [ ] [BOARD][feat] TASKBACK.5 @agents: Tasks centre tab in the Dungeon (BOARD.4 retargeted): columns, filters, Daniel's edits and drag, live agent updates, card click opens Chat. Done when selftest builds it off-screen, a move writes one `moved` event, and draw is ≤ 2 ms. (after TASKBACK.2 and WIN-DUNGEON.4) (M)
  - [ ] [BOARD][feat] TASKBACK.6 @agents: Chat dock task card and target chip (Orchestrator via inbox or resume, one-shot Claude/Grok, Both); `prompt` event carries the card id; runner header gains the task lines. Done when fake-CLI tests show constant argv, the card line in the header, and no process from the inbox path or a status update. (after ROOM-CHAT.1/.3/.4, CHAT-SEND-CLAUDE) (M)
- [ ] [CHAT][feat] MEMMAP: Memory map in the left dock: an Obsidian-like graph of which .md files each session reads and how often, with metrics to check memory is optimised. Relative paths only, never content, local only.
  - [ ] [CHAT][feat] MEMMAP.1 @pixel: Pure memmap/model.py: path normaliser (relative, outside-root tokens, hashing), kind classifier, record validator, project root finder. Done when tests cover Windows/POSIX/UNC/`..`/drive paths and no absolute path survives. (S)
  - [ ] [CHAT][feat] MEMMAP.2 @pixel: Hook capture of PostToolUse Read on *.md/*.mdc, UserPromptSubmit turn markers, SessionStart inferred auto-loads into memmap/<project>/reads.jsonl (lock, caps, rotation, retention, `memmap.enabled`); update docs/claude-hooks.md. Done when fake payload tests show one record per .md Read, no content stored, and the hook stays in budget. (after MEMMAP.1; live check after CLAUDE-HOOK-INSTALL) (S)
  - [ ] [CHAT][feat] MEMMAP.3 @agents: Aggregator (pure): nodes, co-read and link edges, recency fade, window and topic filters, metrics (reads per task, duplicates, never read, hot large files, token estimate). Done when fixture tests pass and 10,000 records aggregate in < 20 ms. (after MEMMAP.1) (M)
  - [ ] [CHAT][feat] MEMMAP.4 @agents: Collapsible memory map section under Topics in the left dock: force layout on a worker thread, kind colours, read-count size, hover, click highlight, metrics strip. Done when selftest builds it with fixture data, collapse state survives a relaunch, and draw is ≤ 2 ms. (after MEMMAP.3) (M)
  - [ ] [CHAT][feat] MEMMAP.5 @agents: Per-task memory metrics on the task card and Tasks tab, joined through the registry's task-topic-session links. Done when two cards in two topics get separate counts. (after MEMMAP.3 and TASKBACK.2) (S)
  - [ ] [CHAT][feat] MEMMAP.6 @agents: MemReadSource adapter protocol, Grok adapter, MCP-M3 memories as a virtual node (counts only). Done when a fake Grok payload yields the same record and memory_search stores no query. (after MEMMAP.2, GROK-LOGIN, MCP-M3 port) (S)

### Windowed dungeon

See [`docs/windowed-dungeon.md`](docs/windowed-dungeon.md).

- [x] [OVL][feat] WIN-DUNGEON.1 @pixel: `desktop/monitors.py` and pure `world/monitors.py` (5.1); signature. (S)
- [x] [OVL][feat] WIN-DUNGEON.2 @pixel: One overlay per monitor (5.2–5.5); avatars in virtual px; terrain over all monitors; drag clamp to the monitor union; hot-plug polling. Dungeon not yet involved. (M)
- [x] [OVL][feat] WIN-DUNGEON.3 @pixel: Dungeon root window (3.1–3.3): framed, resizable, pin, close = quit, ESC change, tray items; docks for Topics, Chat (with pop out), Settings, Skins; status bar replaces the HUD; geometry per signature in the data dir. Scene area shows an empty dungeon floor. Door toggle is not in this step. (M)
- [ ] [BLDG][feat] WIN-DUNGEON.4 @agents: Scene in the Dungeon: `building_view.py` renders BLDG.1 scene JSON with zoom auto and pan; inside actors at their spots; click opens the chat dock, double-click focuses the console. (M)
- [x] [OVL][feat] WIN-DUNGEON.5 @pixel: `model/place.py`, `app/dungeon_map.py`, drag out / drag in with grab hand-off and the occlusion check, subagents follow their parent, `ui/avatar_places.json`, overlays withdrawn when empty. Drag-out works with the door open or closed. (M)
- [x] [OVL][feat] WIN-DUNGEON.6 @agents: Door toggle lands here (toolbar and tray, default open). Escape and return animations (4.2). Door open: blocked/error may escape and return when it clears. Door closed: drag-out only. `idle_return_s`. Call home. (S)
- [ ] [OVL][feat] WIN-DUNGEON.7 @pixel: Click-through per overlay (8.3), per-monitor sprite scale and Dungeon `tk scaling` (5.4), Linux/macOS dungeon-only fallback (5.6), README controls and the `architecture.md` extension table. (S)
- [ ] [OVL][feat] WIN-DUNGEON.8 @agents: Last, low priority. `dungeon.wander` (default off): while the door is open, agents may leave after 30–120 s and return after a random walk. A closed door blocks it. (S)
- [ ] [BUILD][chore] UPDATE-VERSION: 'Update version' button that pulls the latest release. Blocked until a functional version exists.

- [x] [DOCS][docs] TASKS-EPICS: tag TASKS.md with epics and workflow types
