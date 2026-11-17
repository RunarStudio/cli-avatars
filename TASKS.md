---
type: tasks
project: "[[Project - CLI Avatars]]"
status: active
tags: [cli-avatars, tasks, development]
updated: 2026-11-17
---

# CLI Avatars — Task Board

> Live task list for the `zz_cli_avatars/` overlay project.
> Full context: [[Project - CLI Avatars]] · Architecture: `CLAUDE.md` · Reference: `AI_OVERLAY.md`

---

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

- [x] **F4-PORTAL2** Portal lower, behind the characters, wider base, rain <!-- id: F4-PORTAL2 -->
  - The ellipse was floating above the feet. Its centre now sits 4 px below the surface line, so the ring lies on the perch or the floor.
  - The base is 60×12. The solid beam is a seeded rain of 1–2 px dots and short streaks in `#7FDBFF` and white, rising up to 32 px and fading. Eight loop frames at 200 ms. Appear grows the ellipse and starts the rain; disappear stops the rain and shrinks the ellipse.
  - In the overlay the portal is raised over the floor line and then every avatar and child is raised back in front; bubbles are drawn after that. The preview pastes the portal, then the child, the two avatars, and the bubbles. Sheet: `docs/media/meet-portal.png`.

- [x] **F2** Internal event bus, localhost listener, and `cli-avatars-emit` <!-- id: F2 -->
  - `EventBus` is in-process and thread-safe. `PollingSource` publishes each scan. `EventSource` listens on UDP `127.0.0.1` only (default port 47200). With no packets, scan results are unchanged.
  - Shared token file in the per-user data directory, mode 0600 (Windows: user-only ACL). Reject missing tokens, packets over 2 KB, and rate-limit bursts. Strict schema; unknown fields dropped. `note` / `text` go to the rotating log `events.log` and are not shown.
  - States: `idle`, `busy`, `thinking`, `subagent`. Chat icons: `speech`, `question`, `ok`, `warn`, `error`, `thought`, `typing`. Channel queue: `channel/<room>.jsonl` in that data directory, never in the repo.
  - Not in F2: bubble rendering, walking to meet, Grok transcript parsing, MCP, Discord, git channel.

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
