---
type: tasks
project: "[[Project - CLI Avatars]]"
status: active
tags: [cli-avatars, tasks, development]
updated: 2026-11-18
---

# CLI Avatars — Task Board

> Live task list for the `zz_cli_avatars/` overlay project.
> Full context: [[Project - CLI Avatars]] · Architecture: `CLAUDE.md` · Reference: `AI_OVERLAY.md`

---

## 📦 Portable Windows build

- [x] **BUILD-EXE** Local onefile Windows exes <!-- id: BUILD-EXE -->
  - `build.ps1` (PowerShell 5.1 and 7) creates `.venv-build`, installs pinned packages from `requirements-build.txt`, and runs the checked-in spec `cli-avatars.spec`.
  - Outputs, overwritten in place: `build/cli-avatars.exe` (windowed) and `build/cli-avatars-emit.exe` (console). PyInstaller work dirs (`build/_work`, `dist`) are deleted afterward.
  - Sprites, talk icons, and the Caine icon are spec `datas`. `bundle_paths.asset_path()` uses `sys._MEIPASS` when frozen.
  - `overlay.py --selftest` loads those assets, builds the HUD off-screen, and exits 0 or 1. The build script runs that check. No GitHub Actions job.

## 🤖 Orchestrator Queue

> Tagged `<!-- ORCHESTRATOR: ready -->` — picked up by nightly orchestrator, one per run.
> These are small, bounded code tasks. Bubble handles docs (tagged `<!-- BUBBLE: fix -->`).

- [x] Add VERSION constant to overlay.py <!-- ORCHESTRATOR: ready -->
  - Context: overlay.py has no version constant. The project is at v0.4 per CLAUDE.md and the project note.
  - Acceptance: Add `VERSION = "0.4"` as a module-level constant near the top of overlay.py (after imports, before class definitions). No other changes.
  - Guardrail: Only modify overlay.py. Do not change any logic, class, or function. One line added.

- [ ] Add config.json loader stub to overlay.py <!-- ORCHESTRATOR: ready -->
  - Context: The v0.4 roadmap calls for a config.json with fps, scale, and skins keys. overlay.py has no config loading yet.
  - Acceptance: Add a `load_config()` function that reads `config.json` from the same directory as overlay.py, returns a dict, and silently returns `{}` if the file is missing. Call it at the start of `OverlayApp.__init__()` and store the result as `self.config`. Do not yet use the config values anywhere else.
  - Guardrail: Only modify overlay.py. Do not change existing behavior. The overlay must still run correctly if config.json is absent.

---

## 📝 Documentation & Presentation Trail

> Bubble picks **one** item per run. Do not batch. Each item is one file, one change.
> Tag: `<!-- BUBBLE: fix -->`

- [ ] Reconcile stale checkboxes — check off v0.2/v0.3/v0.4 items already done per `Project - CLI Avatars.md` feature table (sprite_loader wired, click-through, HUD, system tray) <!-- BUBBLE: fix -->
- [ ] Update `CLAUDE.md` Current State section: change "v0.1" references to "v0.4 (functional)" and remove "not yet wired" notes that are now done <!-- BUBBLE: fix -->
- [ ] Fix README clone URL: replace `your-username/cli-avatars` with `RunarStudio/RuneIsaRaido` subfolder path, add note "(standalone repo coming)" <!-- BUBBLE: fix -->
- [ ] Add "Download" section to README after Quick Start — GitHub Releases as distribution channel, placeholder: `[Download latest release →](https://github.com/RunarStudio/RuneIsaRaido/releases)` <!-- BUBBLE: fix -->
- [ ] Add archive notice to top of `AI_OVERLAY.md`: "This file documents v0.1. The project is now at v0.4. See `CLAUDE.md` and `overlay.py` for current state." <!-- BUBBLE: fix -->
- [ ] Remove embedded source code blocks from `AI_OVERLAY.md` (sections 7–9: overlay.py, sprite_loader.py, claude_hooks_example.py) — replace each with one line: "See `<filename>` in the project root." <!-- BUBBLE: fix -->
- [ ] Add Changelog section to README (after Roadmap): summarize v0.1→v0.4 milestones in 4 bullet points <!-- BUBBLE: fix -->
- [ ] Create `docs/download.md`: install from source + "Prebuilt Windows executable: see GitHub Releases" + link placeholder <!-- BUBBLE: fix -->
- [ ] Add version + Windows badges to README header: `![version](https://img.shields.io/badge/version-v0.4-blue)` `![platform](https://img.shields.io/badge/platform-Windows-lightgrey)` <!-- BUBBLE: fix -->
- [ ] Tighten `CLAUDE.md` Key Files table: remove `assets/` row (assets live in `Sprites/`), add `gen_ponmi.py` row, update architecture notes to mention skin picker and hue rotation <!-- BUBBLE: fix -->

---

## ✅ Done (v0.1 Baseline)

- [x] Full-screen transparent tkinter overlay (always on top)
- [x] Physics engine: gravity, floor collision, wall bounce, idle pauses, status-reactive speed
- [x] Procedural 8×8 pixel sprite renderer (no external assets needed)
- [x] Multi-avatar management (spawn/remove as sessions appear/disappear)
- [x] HUD panel top-left: agent count, busy/thinking/subagent summary
- [x] Claude Code session scanner (`~/.claude/projects/*/sessions/*.jsonl`)
- [x] Window terrain scanner (open windows → floor platforms via pywinctl)
- [x] Demo mode: 4 agents cycling all states when no real sessions found
- [x] `sprite_loader.py`: SpriteSheet + SpriteRegistry fully implemented
- [x] `claude_hooks_example.py`: UDP notification helper

---

## 🔴 v0.2 — Sprite Integration & Click-Through

### Sprite pipeline

- [ ] **Convert JPG sprite sheets to PNG**
  - `python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png`
  - `python sprite_loader.py convert meowatar_orig.jpg assets/meowatar.png`
  - After converting: open in GIMP/Aseprite and remove solid background (make transparent)

- [ ] **Add `skin` field to `AgentInfo`**
  - `skin: str = "amongo"` in the `@dataclass` in `overlay.py`
  - Demo agents each get a different skin assigned

- [ ] **Import and wire `SpriteRegistry` into `overlay.py`**
  - `from sprite_loader import SpriteRegistry`
  - Instantiate as `REGISTRY = SpriteRegistry()` global
  - At startup (after tkinter root created): load sheets into REGISTRY with fallback if PNGs missing

- [ ] **Pass registry to `Avatar.__init__()`**
  - Add `registry: SpriteRegistry` param, store as `self.registry`
  - Update `OverlayApp._tick()` to pass registry when spawning new avatars

- [ ] **Replace procedural sprite in `Avatar.draw()`**
  - Call `self.registry.get_photo(self.agent.skin, self.agent.status, self.frame)`
  - Keep `make_photo()` as fallback when registry returns None (no PNG loaded)
  - Resize `AVATAR_W`/`AVATAR_H` constants to match actual cell size (48×48 or 60×60)

### Click-through (Windows)

- [ ] **Apply `WS_EX_TRANSPARENT` after window creation**
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

- [ ] **Create `config.json` loader**
  - Schema: `{ "fps": 20, "scale": 1.0, "skins": { "demo_0": "amongo", "demo_1": "meowatar" } }`
  - Load at startup in `OverlayApp.__init__()`, silently skip if file missing
  - Apply `fps` to `OVERLAY_FPS`, `scale` to registry `load()` calls

---

## 🟠 v0.3 — Richer Agent Interaction

- [ ] **UDP listener for instant hook events**
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

- [ ] **Subagent spawn animation**
  - On `subagent_start` event: spawn child Avatar at parent's x/y position
  - Child starts with `vy = JUMP_VEL` (falls from parent)
  - Link child to parent with a small line drawn in `draw_hud`

- [ ] **Avatar-to-avatar interaction**
  - When two idle avatars are within 60px: both stop and face each other for 2–4s
  - Emit a small speech bubble `💬` above both

- [ ] **Emotion bubbles**
  - Float above head for 1.5s then fade: 💭 thinking · 🔥 busy · ✅ done · ❌ error
  - Trigger on status transitions

- [ ] **Jump between window platforms**
  - When avatar reaches a floor edge: check if adjacent platform is within jump range
  - Calculate jump velocity to land on target; execute jump animation (row 4)

---

## 🟡 v0.4 — UX Polish

- [ ] **System tray icon** (show/hide, mute, quit)
  - Use `pystray` library: `pip install pystray`
  - Menu: Toggle Overlay / Mute Sounds / Quit

- [ ] **Name tags fade after idle timeout**
  - Track `last_active_t` on Avatar
  - After 30s idle: fade label alpha to 30% via canvas `stipple`

- [ ] **Optional sound effects**
  - Short blip on status change (busy → done)
  - Toggle via config or system tray menu
  - Use `playsound` or `winsound` (Windows only)

- [ ] **Draggable HUD panel**
  - Bind `<B1-Motion>` on HUD canvas items to move the panel

---

## 🟢 v0.5 — AIs talk to each other

- [x] **F3** Icon-only speech bubbles on `chat` <!-- id: F3 -->
  - A `chat` event draws one allowlisted icon above the sending avatar (`source:id`). The same avatar queues; the bubble holds 3 s, then fades. When two are open, the newer one sits 4 px higher. Bubbles follow the avatar while it walks or perches. Subagent children are unchanged.
  - Art is `Sprites/talk/` (16×16 9-slice frame, separate 4 px tail, 9×9 icons). `Sprites/bubble.png` is the round character sheet (192×240), not a 9-slice, so it is not reused.
  - HUD row `💬 Talks N`: avatar pairs with a chat event in the last 10 s. Grey at 0, white from 1, one blink when a new pair starts.
  - Not in F3: free-text bubbles, emotion bubbles on status changes. Walking over to meet is **F4**.

- [x] **F4** Avatars walk to meet on `chat` <!-- id: F4 -->
  - Same perch (the same window-top segment): both walk to its midpoint and stop 8 screen pixels apart, facing each other. Sprite width is already in screen pixels, so the gap is not scaled again.
  - Different windows, or either avatar on the floor: both walk off the perch and fall to the taskbar line, then meet at the midpoint of the centers they had when the chat arrived, 8 screen pixels apart. No teleport. A perch with no free edge cancels the meeting.
  - Subagent children are not a party to the meeting. While the parent is walking or talking they keep their offset on the spring line, one step behind.
  - States: IDLE, WALK_TO, MEET, TALK, RETURN. TALK holds while chat events for that pair keep arriving. About 10 s after the last one, they wander again. A pair that is already meeting does not restart. A third avatar waits until the current pair finishes.
  - A self-chat does not walk. A missing avatar or a vanished window cancels the meeting. Meeting points clamp to the screen and to the perch.
  - Bubbles still follow the speaker. The `💬 Talks N` row is unchanged. Nothing in the packet is executed.
  - Planner: `meetings.py`. Preview: `docs/media/meet-animation.gif`. Manual check: `docs/claude-hooks.md`.

- [x] **F4-BUG1** Duplicated avatar in the meeting preview <!-- id: F4-BUG1 -->
  - Complaint: in `docs/media/meet-animation.gif` the left Caine is drawn twice, almost on top of itself, both on the perch and on the floor.
  - Cause: the preview pasted a second full-size copy of the parent's walk cell about 16 px away and called it a subagent. The overlay does not. Each main avatar is drawn once in `_tick`. A real subagent is a separate avatar, skin `bubble`, and only exists when that session has subagents. During a meeting it keeps its own offset on the spring line; it is not a clone of the parent's sprite.
  - Fix: the preview child is the bubble cell, one step behind the parent on the spring. It is not a second Caine.

- [x] **F4-PORTAL** Glowing portal on the meeting point <!-- id: F4-PORTAL -->
  - A 40×40 portal opens on the surface where the pair will meet, as soon as they start walking. The anchor pixel (20, 36) sits on the perch line, or on the top edge of the floor. The same sprite is used for both. It scales with the avatars' integer factor and is drawn behind them.
  - Appear is 2 frames (ellipse 4→40 wide, beam 0→28), then a 4-frame loop while they walk, meet, and talk (ellipse height ±1, beam alpha 60%/45%). Return or cancel plays the 2-frame close. 200 ms per frame. No portal on a self-chat. One portal for the current pair.
  - Art is drawn in `portal.py` (ring `#7FDBFF`, white centre, shadow `#1B2A4A` at 50%, beam in three alpha bands, no outer glow). Ring thickness is 1 px in the app; 2 px is the light-background option. Preview: `docs/media/meet-animation.gif`. Sheet: `docs/media/meet-portal.png`.

- [x] **F2** Internal event bus, localhost listener, and `cli-avatars-emit` <!-- id: F2 -->
  - `EventBus` is in-process and thread-safe. `PollingSource` publishes each scan. `EventSource` listens on UDP `127.0.0.1` only (default port 47200). With no packets, scan results are unchanged.
  - Shared token file in the per-user data directory, mode 0600 (Windows: user-only ACL). Reject missing tokens, packets over 2 KB, and rate-limit bursts. Strict schema; unknown fields dropped. `note` / `text` go to the rotating log `events.log`. The desktop bubble does not show them. A sanitised channel copy is **P3-CHAT-NOTE**.
  - States: `idle`, `busy`, `thinking`, `subagent`. Chat icons: `speech`, `question`, `ok`, `warn`, `error`, `thought`, `typing`. Channel queue: `channel/<room>.jsonl` in that data directory, never in the repo.
  - Not in F2: bubble rendering, walking to meet, Grok transcript parsing, MCP, Discord, git channel.

## 🟣 Phase 1 — Reliable status

- [x] **P1-HUD** HUD counters per AI source <!-- id: P1-HUD -->
  - Every agent carries `source` (`claude`, `grok`, `emit`, …) from its SessionSource or from the emit event. A subagent inherits its parent's source.
  - The HUD shows one row per source that has sessions: `Claude 3 | busy 1 thinking 1 idle 1 | sub 2`. A total line counts subagents from every source, and each source row shows its own `sub` count. The `💬 Talks N` row stays.
  - `GrokBuildSource` is registered and returns no sessions until transcripts are parsed. It does not read auth or credential files. The sessions directory is `%USERPROFILE%/.grok/sessions`.
  - Preview: `docs/media/hud-per-source.png`.

## 🟣 Phase 2 — Orchestrator rooms

- [x] **P2-ROOMS** Rooms list of top-level sessions <!-- id: P2-ROOMS -->
  - A HUD button `Rooms`, next to Skins and Config, toggles a compact list. The walking desktop is unchanged and stays on screen while the list is open.
  - One card per orchestrator: the avatar's idle-frame thumbnail, its name, its source (Claude, Grok or Emit), the project folder name only, a state dot, and last activity as `Ns ago`. Subagents sit under the card as small rows with their own dots.
  - Dots, as Caine proposed: idle grey `#9a98b8`, busy blue `#4488ff`, thinking violet `#aa44ff`, subagent in the accent `#ffcf4a`.
  - Active orchestrators come first, newest activity first inside that group. Idle for more than 5 minutes is dimmed and marked `Zzz`.
  - A session whose newest result is an error (`failed`, or status `error`) shows the existing warn icon. When that signal is absent, the icon is skipped.
  - The boolean `rooms` in `config.json` is read at startup and written back only when that file already exists.
  - Model and tests: `rooms.py`. Preview: `docs/media/rooms-list.png`.

## 🟣 Phase 3 — Local chat

- [x] **P3-CHAT** Read-only local chat <!-- id: P3-CHAT -->
  - A HUD button `Chat`, next to Rooms, toggles one timeline. The walking desktop stays on screen. There is no send box.
  - The timeline is every message in the local channel logs (`channel/<room>.jsonl`), merged across rooms and sorted by time. The panel tails those files: a quiet poll reads no bytes again. A replaced file is read from the start because the old offset is no longer valid.
  - Each line shows `HH:MM`, the sender's idle thumbnail, the sender's name, its source (Claude, Grok or Emit), the allowlisted icon, and the note text when the line carries `note` or `text`. Control characters are stripped and the note is capped. The text is data. It is drawn only in this panel. Desktop bubbles stay icon-only, and nothing in a line is executed.
  - Filters: all rooms or one room, and all sources or one source. The list follows the newest line unless the reader has scrolled up.
  - `say --note` at the time of P3-CHAT stayed in the rotating log only. **P3-CHAT-NOTE** also copies a sanitised note onto the channel file. The bubble stays icon-only.
  - Model and tests: `chatlog.py`. Preview: `docs/media/local-chat.png`.

- [x] **P3-CHAT-NOTE** `say --note` is copied into the channel log <!-- id: P3-CHAT-NOTE -->
  - `cli-avatars-emit say --note` still appends the rotating log. It also appends one channel record. The note uses the Chat panel's sanitisation: control characters stripped, 240 characters, icon on the allowlist.
  - The append keeps the channel directory lock and the owner-only ACL. The note is data. Nothing in it is executed. The desktop bubble stays icon-only.
  - The Chat panel shows the line on its next tail.

- [x] **P3B-SEND** Local send box and per-agent inbox <!-- id: P3B-SEND -->
  - Inbox files are `inbox/<agent_id>.jsonl` in the per-user data directory, with the same owner-only ACL and atomic append as the channel. The Chat panel Send button writes those files and one channel line. It does not start a process and it does not open a socket.
  - To is one agent, several agents, or All. All is the rooms registry (top-level sessions and their sub rows). Demo avatars are not included.
  - Schema: `id`, `ts`, `from` (`user` or an agent id), `to` (list), `room` / `topic` (default `general`), `kind` (`msg`; `decision` and `decision_answer` are reserved), `text` (sanitised, 2000), `reply_to` optional.
  - `inbox read --agent ID [--since ID] [--json]` prints unread rows and stores the cursor at `inbox/<agent_id>.cursor`. `reply --agent ID --to MSG --note "..."` appends the reply to the channel so the panel shows it.
  - Schema: `docs/chat-schema.md`. Hook and agent instructions: `docs/claude-hooks.md`. Preview: `docs/media/chat-send.png`.

- [x] **P3C-DECISIONS** Decision cards in local chat <!-- id: P3C-DECISIONS -->
  - `cli-avatars-emit decide --agent ID --room ROOM --question "..." --option a="..." --option b="..."` stores a kind `decision` (uuid, status `open`) on the channel and in `decisions.jsonl`. Two to six options, letters a–f with no gaps. Each option is sanitised and capped at 120 characters. The question is capped at 240. The app does not execute the question or the options.
  - The Chat panel Decisions tab lists open cards (thumbnail, name, room, question, lettered buttons) and a short history of answered ones. Choosing a letter writes kind `decision_answer` (`decision_id`, `choice`, `ts`, `from` `user`, `text` the chosen label) to that agent's inbox and the channel, and marks the decision answered. A second answer, or an unknown id, is rejected.
  - `inbox read` returns `decision_answer` rows with the other messages. `decisions list [--open] [--json]` lists the index. The HUD row is `Decisions N`.
  - While a decision is open, the desktop avatar shows a `decision` bubble. The icon is on the allowlist. The glyph is a code placeholder (`TODO(Caine art)`) until the 16×16 cell arrives. No new sprite file.
  - Schema: `docs/chat-schema.md`. How an agent asks and reads the answer: `docs/claude-hooks.md`. Preview: `docs/media/chat-decisions.png`.

- [x] **P3D-TOPICS** Topics keep AI context small <!-- id: P3D-TOPICS -->
  - A topic is the room id already stored on channel, inbox, and decision records. Unknown rooms become an open topic. Files are `topics/<id>.json` in the per-user data directory, owner-only, with the same directory lock (timeout, handle closed before the lock returns).
  - Fields: id, title, project (folder name only; a path is rejected), branch, status (`open`, `waiting_on_user`, `done`), members, summary (1500), pins (at most 30, each 240, kind `fact` or `decision`), created, updated.
  - `topic show` returns only the summary, the pins, and the last 10 messages, plus `needs_summary` when more than 50 messages arrived since the summary was replaced. The Chat panel shows the last 200 messages per topic. The jsonl on disk is not deleted.
  - The Rooms list is topics grouped by project: status chip, member thumbnails, open decision count, and the existing per-orchestrator state dots. Clicking a topic filters Chat and the send box. Answered decision cards show a Pin button. Pins in the header have Unpin. Nothing is pinned silently.
  - The app stores, shows, and notifies. It does not execute text and it does not call a model. Summaries are written by an agent through emit, or by the person.
  - Schema: `docs/chat-schema.md`. Protocol: `docs/claude-hooks.md`. Preview: `docs/media/chat-topics.png`.

- [x] **P3E-HOOKS** Claude Code sessions use the local chat <!-- id: P3E-HOOKS -->
  - `hooks/claude_chat_hook.py` is a stdlib hook. It reads the official Claude Code JSON on stdin (`session_id`, `cwd`, `hook_event_name`, `transcript_path`). The agent id is the first 8 characters of `session_id`, the same id `ClaudeJsonlSource` takes from the transcript file name. The topic id defaults to the cwd folder name, as a slug.
  - SessionStart and UserPromptSubmit print a short context block (topic summary, pins, unread messages and decision answers) and mark those messages read. Nothing new prints nothing. Output is capped at 2000 characters. `needs_summary` counts as new.
  - Stop emits `idle`. When `chat.auto_notes` is true (the default), a sanitised note from the last assistant message (240 characters) is stored with `say --note`. Set `chat.auto_notes` to false to disable it. A Stop that is already continuing does not store a second note.
  - Any failure exits 0. Store locks time out. The script does not run message text.
  - `cli-avatars-emit hooks install` merges SessionStart, UserPromptSubmit, and Stop into `%USERPROFILE%\.claude\settings.json`. `--dry-run` is the default and prints a diff. `--apply` writes a timestamped backup first and is idempotent. `hooks uninstall --apply` removes only those entries.
  - Agent instructions: `docs/agent-chat-protocol.md`.

## 🔵 v0.5 — Tauri Port

- Step 1 done: SessionSource adapter layer (ClaudeJsonlSource)

- [ ] **Port rendering to PixiJS / HTML5 Canvas inside Tauri webview**
- [ ] **Rust sidecar for window enumeration** (faster than pywinctl)
- [ ] **Cross-platform binary** (no Python install required)
- [ ] **Auto-update mechanism**

---

## Reference

| Doc | Path |
|-----|------|
| Full project reference (v0.1) | `AI_OVERLAY.md` |
| Claude Code project guide | `CLAUDE.md` |
| Sprite sheet format & Stream Avatars convention | `AI_OVERLAY.md` → Sprite Sheet Format |
| Python concepts glossary | `AI_OVERLAY.md` → Python Concepts Glossary |

- [x] FIX-HUD-PADY: the overlay crashed at startup (Tk Label pady given as a tuple, TclError 'expected screen distance'), so no avatars appeared; padding moved to pack().
