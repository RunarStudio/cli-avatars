# CLI Avatars

Animated pixel-art characters that live on your desktop and react to your active **Claude Code** sessions in real time.

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
- **Subagent physics** — when a Task sub-agent spawns, a child avatar appears and hangs from the parent via an elastic spring line
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
```

`say` draws that icon in a bubble over the sending avatar. Two different avatars also walk to meet (same window top, or both drop to the floor). A `--note` is sanitised onto the local channel log and shown in the Chat panel; the bubble stays an icon. Trigger, HUD, and the Windows check: [docs/claude-hooks.md](docs/claude-hooks.md#meeting-walk-f4). The inbox and reply commands are in [docs/claude-hooks.md](docs/claude-hooks.md#local-chat-p3-chat-note-p3b-send). Schema: [docs/chat-schema.md](docs/chat-schema.md).

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
├── cli_avatars_emit.py     ← `python -m cli_avatars_emit` (state / say / inbox / reply)
├── inbox.py                ← Per-agent inbox, send fan-out, read cursor, reply
├── sprite_loader.py        ← Sprite sheet loader (SpriteSheet, SpriteRegistry)
├── claude_hooks_example.py ← Hook helper that calls cli-avatars-emit
├── gen_ponmi.py            ← Generator for the ponmi sprite sheet
├── requirements.txt
├── Sprites/                ← PNG sprite sheets
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
    └── claude-hooks.md     ← How to use the hooks integration
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
