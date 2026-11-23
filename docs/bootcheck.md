# Boot check

When the Dungeon starts, a short set of read-only checks runs on this PC. The window is already on screen. The checks run off the Tk thread with a hard budget of 2.0 seconds. A check that is still running when the budget ends is `timeout`. It does not hold startup.

This is not CI and not a git hook. Nothing here opens the network, starts Claude or Grok, or runs chat text.

Turn it off with `desktop.bootcheck` set to `false` in `config.json`, or Settings → Display → Boot check. The default is on. `--bootcheck-only` runs the checks even when the setting is off, prints the table, and exits 0 when every check passed and 1 otherwise.

## Checks

| Check | What it looks at |
|-------|------------------|
| `dungeon_window` | The Dungeon is a framed window, minimum 720×480, with a scene. The CLI flag builds that window off-screen and closes it. On Windows that build takes about 0.6 s. Inside the running app the check only inspects the window that is already up. |
| `assets` | `caine.png`, `bubble.png`, and the talk frame, tail, and icons are files. |
| `config` | `config.json` is missing (defaults) or a JSON object. `desktop.bootcheck`, when present, is a boolean. |
| `skins_manifest` | `Sprites/subagents/manifest.json` parses and each skin is `fly` or `ground`. |
| `dpi` | DPI mode is per-monitor v2, per-monitor, system, or skipped (non-Windows). |
| `monitors` | On Windows, each monitor has a sane rect and a DPI from 48 to 480. Other platforms pass with no Win32 monitors. |
| `event_bus` | A fresh in-process bus delivers one fixed `idle` state. |
| `hook_port` | The loopback UDP port is free, or already bound. The probe socket is closed. |
| `board_store` | `board/` in the data directory is absent, empty, or readable JSON. |
| `registry_store` | `registry.json` or `registry/` is absent or readable JSON. |
| `app_data` | The data directory accepts one temporary file, then that file is removed. |
| `scene_tick` | A few empty dungeon-floor layouts finish in well under 200 ms. |
| `sprites_40` | `amongo.png` loads as 40×40 frames. |
| `sprites_32` | Each subagent sheet in the manifest loads as 32×32 frames. |

## Results

The bottom status bar shows one line, for example `Boot check 14/14 ok · 1.3 s · 0.4.0 abc1234`. The version and the short commit sit on that line. A click opens the per-check list in the Settings dock. That list is not a new window.

Compared with the previous run, the line adds more passes (`+1 pass`), `faster` or `slower` when the total moves by at least 20 ms, and a regression count. A check that was `ok` and no longer is, is marked `regression` in the list. A check that newly passes is marked `new pass`.

Each run is appended to `bootcheck_history.jsonl` in the per-user data directory (`events.app_data_dir()`). On Windows that directory is `%LOCALAPPDATA%\cli-avatars\`. A line holds the UTC timestamp, app version, commit when the checkout exposes one, per-check status and milliseconds, and the total. The file keeps the newest 200 runs. Lines do not store paths.

## Windows check

From the clone, with the overlay dependencies installed:

```bat
python -m unittest tests.test_bootcheck
python -m ruff check cli_avatars
python overlay.py --selftest
python overlay.py --bootcheck-only
python overlay.py
```

`--selftest` prints `selftest: ok` and exits 0. `--bootcheck-only` prints the table and exits 0 when every check passed. On Windows the CLI `dungeon_window` check takes about 0.6 s because it builds a Tk window. The Dungeon window should appear at once. Within about two seconds the status line settles. Click it and confirm the list is in Settings, with no second top-level window. Set Boot check off, restart, and confirm the line does not run. The history file is under `%LOCALAPPDATA%\cli-avatars\bootcheck_history.jsonl`.
