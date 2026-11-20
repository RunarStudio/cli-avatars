# CLI Avatars

Animated pixel-art characters that live on your desktop and react to your active **Claude Code** and **Grok Build** sessions in real time.

Each avatar represents one running agent. It walks on top of your open windows, speeds up when the agent is using a tool, and dangles as a sub-agent when a sub-task spawns. No browser, no VS Code extension — just a Python script you run once.

---

<p align="center">
  <img src="meowatar_preview/meowatar_walk.gif" width="96" alt="walk">
  <img src="meowatar_preview/meowatar_type.gif" width="96" alt="type">
  <img src="meowatar_preview/meowatar_read.gif" width="96" alt="read">
  <img src="meowatar_preview/meowatar_idle.gif" width="96" alt="idle">
</p>

<p align="center">
  <em>walk · type (tool use) · read · idle</em>
</p>

---

## What It Does

- **One avatar per Claude Code session** — spawns and despawns automatically as you open and close Claude terminals
- **Window terrain** — avatars walk on the top edges of your open windows (VS Code, browser, terminal, etc.)
- **Wall climbing** — avatars randomly latch onto window edges and climb up
- **Status-reactive** — animation row changes based on what the agent is doing (idle, busy, thinking, subagent)
- **Subagent physics** — a child hangs below the parent on a spring, or hovers above it when that skin flies
- **Skin picker** — pick any loaded sprite sheet and hue-shift it per agent, live
- **No sessions = single idle avatar** — Caine appears when no Claude sessions are running

---

## Quick Start

**Requirements:** Python 3.10+, Windows (Linux/macOS partial support)

```bash
# 1. Clone
git clone https://github.com/RunarStudio/cli-avatars.git
cd cli-avatars

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python overlay.py
```

Right-click on screen → **Quit**, or press **ESC**.

---

## Build a portable exe

The Windows exes are built on a developer PC. There is no GitHub Actions workflow for this.

Requirements: Windows, Python 3.10+, and PowerShell 5.1 or PowerShell 7.

```powershell
.\build.ps1
```

The script creates `.venv-build` (gitignored), installs the pinned packages in `requirements-build.txt`, and runs PyInstaller with `cli-avatars.spec`. It writes two onefile executables and deletes the PyInstaller work directories:

| Output | Window |
|--------|--------|
| `build/cli-avatars.exe` | windowed overlay |
| `build/cli-avatars-emit.exe` | console helper for hooks |

Both names are fixed. A later build overwrites the same files. Sprite sheets, talk icons, and the Caine icon are packed via the spec `datas` list. At runtime `bundle_paths.asset_path()` reads `sys._MEIPASS` when the process is frozen.

After the copy, the script runs:

```powershell
.\build\cli-avatars.exe --selftest
```

`--selftest` loads those assets, builds the HUD widgets off-screen, and exits 0 or 1 without leaving a window up. A non-zero exit fails the script.

`build/*.exe` is not gitignored. Commit the two executables on `dev` from that Windows machine when you want them in the repo. Do not commit `.venv-build`, `build/_work`, or `dist/`.

---
![Main Window for the app]({DE4B6408-288C-46FC-901B-B4045B740688}.png)

## Controls

| Action | Result |
|--------|--------|
| Left-click avatar | Open that avatar's topic in the chat window |
| Drag avatar | Move it. A short click does not |
| Right-click avatar | Focus that agent's terminal window |
| Right-click empty area | Open context menu (Skins / Config / Status / Quit) |
| Drag HUD panel | Reposition the status box |
| ESC | Quit |

---

## Skin Picker

Right-click → **Skins** to open the skin picker:

![alt text]({41383BD0-56D3-4D49-B27F-0BB4EB374140}.png)

```
[ Agent: caine ▼                    ]
[ Hue: 0° ─────────────────── 360° ]
[ Preview: [■■■■] 64×64 thumbnail   ]

  ○  bubble
  ●  caine       ← selected (blue highlight)
  ○  meowatar
  ○  amongo
  ○  michimaru

[ Apply ]
```

- **Hue slider** — rotates all colors of the sprite. Preview updates live.
- **Skin list** — click a row to select. Click **Apply** to assign.
- Per-agent assignment: each agent can have its own skin and hue.

---

## Available Skins

| Name | Type | Notes |
|------|------|-------|
| `caine` | Auto-generated | Stick-figure character (default) |
| `bubble` | Auto-generated | Round bubble character |
| `amongo` | Auto-generated | Among-Us-style cat |
| `meowatar` | `Sprites/meowatar.png` | Stream Avatars format, 60×50 cell |
| `michimaru` | `Sprites/Michimaru.png` | Stream Avatars format, 40×51 cell |
| `ponmi` | `Sprites/ponmi.png` | Stream Avatars format, 48×48 cell |

---

## Adding Your Own Skin

Any sprite sheet in **Stream Avatars row format** works. Full guide: [docs/adding-sprites.md](docs/adding-sprites.md)

**TL;DR:**

1. Place a `.png` sprite sheet in `Sprites/`
2. Add one line to the `sheets` list in `_load_sprites()` inside `overlay.py`:
   ```python
   ("myskin", "MySkin.png", frame_width, frame_height),
   ```
3. Restart — your skin appears in the picker immediately.

Row convention:

| Row | Animation | When shown |
|-----|-----------|------------|
| 0 | idle | Agent waiting |
| 1 | run / walk | Agent using a tool (busy) |
| 2 | sit | Agent thinking / waiting for response |
| 3 | stand | Done / error |
| 4 | jump | Sub-agent active |

---

## Claude Code Hooks (Real-Time Events)

By default, the overlay polls JSONL session files every 2 seconds. For instant status updates, hooks call `cli-avatars-emit`, which sends a localhost UDP packet the overlay applies on top of that poll. Full guide: [docs/claude-hooks.md](docs/claude-hooks.md)

```bash
python -m cli_avatars_emit state --source claude --id abcd1234 --state busy
python -m cli_avatars_emit say --from claude:abcd1234 --to grok:abcd1234 --icon question --note "shown in Chat"
python -m cli_avatars_emit inbox read --agent abcd1234 --json
python -m cli_avatars_emit reply --agent abcd1234 --to <message-id> --note "reply"
python -m cli_avatars_emit hooks install --apply
```

`say` draws that icon in a bubble over the sending avatar. Two different avatars also walk to meet (same window top, or both drop to the floor). A `--note` is sanitised onto the local channel log and shown in the chat window; the bubble stays an icon. The HUD Chat button opens that window. A left-click on an avatar opens its topic, addressed to the orchestrator. Trigger, HUD, and the Windows check: [docs/claude-hooks.md](docs/claude-hooks.md#meeting-walk-f4). The inbox and reply commands are in [docs/claude-hooks.md](docs/claude-hooks.md#local-chat-p3-chat-note-p3b-send). Schema: [docs/chat-schema.md](docs/chat-schema.md).

On Windows, real Claude Code sessions can load that chat themselves. From the clone:

```bat
python -m cli_avatars_emit hooks install --apply
```

That merges `SessionStart`, `UserPromptSubmit`, and `Stop` into `%USERPROFILE%\.claude\settings.json`. The hook prints new local context into the session and, unless `chat.auto_notes` is false, stores a short note when the turn ends. It does not run message text. Details: [docs/claude-hooks.md](docs/claude-hooks.md#chat-hook-p3e-hooks). Instructions to drop into `CLAUDE.md`: [docs/agent-chat-protocol.md](docs/agent-chat-protocol.md).

---

## Grok Build sessions

Grok Build sessions show up next to Claude when the sessions folder exists. The folder is `$GROK_HOME/sessions`, or `~/.grok/sessions` when `GROK_HOME` is unset (`%USERPROFILE%\.grok\sessions` on Windows).

A session is live when `updates.jsonl` or `summary.json` changed in the last 15 minutes. The avatar id is the first 8 characters of the session id, prefixed `grok:` in the overlay. The name is the summary title, or the project folder name. Pose comes from the end of `updates.jsonl`: a tool call still running is busy, a thought is thinking, and a finished turn is idle. Subagents listed in `subagents/*/meta.json` hang off that parent the same way Claude subagents do.

The chat hook is the same script. A payload that carries Grok's own fields, or a transcript path under `.grok`, is tagged `source=grok`. Claude payloads stay `source=claude`. The Grok composer writes to that live session id.

Until a Grok sprite exists, those avatars use the Caine sheet shifted by `grok.hue` degrees (`200` unless `config.json` says otherwise). `grok.skin` picks the base sheet. The HUD row for Grok uses its own mark and color. Details: [docs/grok-sessions.md](docs/grok-sessions.md).

---

## Subagent skins

A subagent wears a sheet from `Sprites/subagents/`, not the parent's skin. The manifest next to those sheets sets the frame size and `mode`: `ground` hangs below the orchestrator, `fly` hovers above its head. Both stay inside the leash (`subagent.leash_px`, or three spring-lengths when that key is absent) until the subchat closes. Each sheet is 4 columns by 3 rows: idle, working, and dying, four frames each. Busy and thinking use working. Closing plays dying once, shrinks the spring line, and then removes the child. A missing row falls back to the first row that has frames.

The shipped sheets are code-drawn placeholders (a small PH mark, `placeholder: true`). Real art replaces the PNGs later. `config.json` chooses the skin when the child spawns, and the child keeps it:

```json
{
  "subagent": {
    "leash_px": 240,
    "skins": {
      "mode": "round_robin",
      "list": ["imp", "winged_light"],
      "fixed": { "abcd1234": "dragon" }
    }
  }
}
```

`mode` is `round_robin` (the default), `random`, or `fixed`. `list` limits the pool. `fixed` maps an orchestrator id to one loaded skin. With no `subagent.skins` key, children cycle every sheet in the manifest: imp, claude4, winged_light, cat, dog, dragon, mini_drone, little_grok.

---

## Dependencies

```
pillow      # image loading, hue rotation, sprite rendering
pywinctl    # open window positions (terrain). Optional — falls back to screen floor.
numpy       # hue rotation math. Optional — skips hue shift if missing.
pystray     # system tray icon. Optional — falls back to right-click menu.
```

```bash
pip install -r requirements.txt
```

---

## Project Structure

```
cli-avatars/
├── overlay.py              ← Entry point — run this
├── bundle_paths.py         ← Asset root (sys._MEIPASS when frozen)
├── build.ps1               ← Local Windows PyInstaller build
├── cli-avatars.spec        ← Onefile spec for both exes
├── requirements-build.txt  ← Pinned packages for that build
├── events.py               ← Event bus and localhost UDP listener
├── bubbles.py              ← Icon bubble layout, queue, and talk count
├── meetings.py             ← Walk-to-meet planner (perch or floor)
├── portal.py               ← Portal on the meeting point (anchor, frames, sprite)
├── cli_avatars_emit.py     ← `python -m cli_avatars_emit` (state / say / inbox / reply / hooks)
├── claude_chat_hooks.py    ← Chat hook logic and Claude settings merge
├── inbox.py                ← Per-agent inbox, send fan-out, read cursor, reply
├── routing.py              ← Composer routes: orchestrators only
├── chat_window.py          ← Discord-style chat window
├── sprite_loader.py        ← Sprite sheet loader (SpriteSheet, SpriteRegistry)
├── subskins.py             ← Subagent manifest and skin assignment
├── hooks/
│   └── claude_chat_hook.py ← Claude Code chat hook (stdlib only)
├── tools/
│   ├── gen_ponmi.py        ← Generator for the ponmi sprite sheet
│   ├── gen_meowatar_gifs.py ← GIF previews from meowatar.png
│   └── gen_subskin_placeholders.py ← Code-drawn 32×32 stand-in sheets
├── requirements.txt
├── Sprites/                ← PNG sprite sheets
│   ├── subagents/          ← 32×32 subagent sheets + manifest.json
│   ├── caine.png
│   ├── bubble.png
│   ├── meowatar.png
│   ├── michimaru.png
│   ├── ponmi.png
│   └── talk/               ← speech-bubble frame, tail, icons
├── meowatar_preview/       ← GIF previews of animations
├── ponmi_preview/          ← Ponmi sprite GIFs
└── docs/
    ├── adding-sprites.md   ← How to add custom skins
    ├── chat-schema.md      ← Channel and inbox message schema
    ├── claude-hooks.md     ← How to use the hooks integration
    ├── grok-sessions.md    ← How Grok Build sessions are detected
    ├── agent-chat-protocol.md ← Short instructions for an agent using the local chat
    └── media/chat-window.png ← Chat window preview
```

---

## Roadmap

| Version | Focus |
|---------|-------|
| v0.4 ✅ | Real sprite sheets, skin picker, hue shift, wall climbing, subagent spring physics |
| v0.5 | UDP listener, icon speech bubbles, and the meeting walk (F2, F3, F4) |
| v0.6 | System tray, sound effects, config file |
| v1.0 | Tauri port — cross-platform binary, no Python required |

Full task board: [TASKS.md](TASKS.md)

---

## License

MIT — see [LICENSE](LICENSE) if present, otherwise treat as free to use and modify.
