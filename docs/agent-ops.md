# Agent ops: check, restart, update CLI Avatars (OPS.1, OPS.2)

For any Claude Code or Grok session asked to manage the running app. Run every command from a clone of this repo.

## What runs where

- One process: the **Dungeon** window plus the desktop avatars. Windows: installed `cli-avatars.exe` (`%LOCALAPPDATA%\Programs\CLI Avatars`), or `python overlay.py` from a clone. Linux: `python overlay.py` from a clone.
- Data dir (chat, settings token, logs): Windows `%LOCALAPPDATA%\cli-avatars`, Linux `~/.local/share/cli-avatars`, or `CLI_AVATARS_DATA_DIR`.
- Control channel: the app's UDP listener on `127.0.0.1:47200` (`CLI_AVATARS_PORT`), with the token from the data dir. Nothing listens beyond loopback.

## Verbs

`python -m cli_avatars_emit app <verb>` (or `cli-avatars-emit app <verb>` when installed with pip). Exit 0 done, 1 refused or failed (one line on stderr), 3 not running.

| Verb | Does |
|------|------|
| `status [--json]` | Running or not, pid, version, commit, uptime, phone view on/off, phone writes on/off, the Update line, data dir. |
| `restart [--wait 60]` | Running: the app starts a fresh copy of itself and quits; the copy waits for the old pid, then opens. Not running: starts it. Waits until it answers again (`--wait 0`: do not wait). Refused while an Update runs. |
| `update` | The **Update** button: fetch `dev`, selftest, build, swap, relaunch ([install-and-update.md](install-and-update.md#update)). Refused for the same reasons as the button (from source, git or PyInstaller missing, already running). |
| `logs [--tail 40] [--log app\|update\|events]` | End of a log in the data dir. `app`: start, stop, restart, crashes with tracebacks. `update`: every Update command and its output. `events`: the UDP listener. |
| `phone status [--json]` | Phone view on/off, port, listen address, the saved Phone address, and whether `tailscale serve` forwards https to that port (yes, no, tailscale not found). |
| `phone refresh [--reset]` | Redo `tailscale serve --bg <port>`, read it back, save the https address as the Phone address when it changed (the pairing link follows) and print it. See [Phone page down](#phone-page-down-refresh-tailscale). |

```text
$ python -m cli_avatars_emit app status
CLI Avatars: running (pid 41210, up 2h 13m)
Version 0.4.0 · commit 4e2a2bd0d82f · dev
Phone view: on · writes: on
Update: idle
Data dir: /home/<user>/.local/share/cli-avatars

$ python -m cli_avatars_emit app restart
Restarting the Dungeon (pid 41210 quits).
Back up at 09:41:07: pid 41388, up 0m 1s.
```

## Start and stop by hand

- Windows start: Start menu, **CLI Avatars**. From a clone: `python overlay.py`.
- Linux start: `python overlay.py` in the clone (needs a display).
- Stop: the window's close button, then **Close**, or tray **Quit**. Last resort: `taskkill /PID <pid>` (Windows) or `kill <pid>` (Linux), pid from `app status`.

## Update and roll back

1. `app update`, then `app status` until the Update line says up to date or the app restarted on the new commit.
2. A new build that fails its boot check is rolled back by the update helper: the old build relaunches and the phone says so. Read `app logs --log update`.
3. Roll back by hand (installed build, app stopped): rename `CLI Avatars` to `CLI Avatars.failed`, rename `CLI Avatars.old` back to `CLI Avatars`, start it. `.old` is the previous build until the next update.
4. From source: `git log --oneline -5`, check out the last good commit in a separate clone, `python overlay.py` there. Never reset a clone that has someone's uncommitted work.

## From the phone

1. In the Dungeon: Settings, **Phone**, tick **Serve the phone view** and **Allow the phone to open sessions and send prompts** ([phone-view.md](phone-view.md)).
2. Phone: gear, **App**: **Restart** (confirm) quits and relaunches the Dungeon; the page reconnects and shows "Back up at <time>". **Update app** is the Update button.
3. A task chat opened from the phone runs Claude in its room's folder. When that folder is a clone of this repo, Claude finds this file through `CLAUDE.md` and can run `app status` and `app logs`. Switch the room from `plan` to run commands. `app restart` from that chat also ends that chat's own run: say so first.

## Phone page down: refresh Tailscale

The phone reaches the page through `tailscale serve` on the PC, which forwards `https://<pc-name>.<tailnet>.ts.net/` to the app on `127.0.0.1:47280` ([phone-view.md](phone-view.md#use-it-over-tailscale-windows)).

1. `python -m cli_avatars_emit app phone status`. Phone view off: tick Settings, **Phone**, **Serve the phone view** first. Listen not `127.0.0.1`: serve is not used, set **Listen on** to Loopback or use the Tailscale address directly.
2. Tailscale serve says `no`: `python -m cli_avatars_emit app phone refresh`. It runs `tailscale serve --bg <port>`, checks `tailscale serve status`, saves the address as the Phone address when it changed and prints it. Open that address on the phone.
3. Still down: `app phone refresh --reset` runs `tailscale serve reset` first. A session that reaches the PC through that serve address (a phone page, a remote chat) loses it until the refresh ends: run it from a session on the PC, or say so first.
4. `tailscale not found`, or the commands fail: in PowerShell on the PC run `tailscale serve --bg 47280`, then `tailscale serve status`. The first time it may ask to turn on HTTPS for the tailnet; that is Daniel's click in the admin page.

```text
$ python -m cli_avatars_emit app phone status
CLI Avatars: running
Phone view: on · port 47280 · listen 127.0.0.1
Phone address: https://<pc-name>.<tailnet>.ts.net
Tailscale serve: no

$ python -m cli_avatars_emit app phone refresh
https://<pc-name>.<tailnet>.ts.net
```

Never `tailscale funnel` (it puts the page on the public internet). Never `tailscale down`, `logout` or `up` from a remote session: the session talks over that link. The verbs never run them.

## When something is wrong

| Symptom | Do |
|---------|----|
| Window gone, `app status` says running | It is minimized to the tray: click the tray icon. Still stuck: `app restart`. |
| `app status` says not running | `app logs --tail 80` for a crash, then `app restart` (starts it). |
| Crash at start | `app logs --tail 80` shows the traceback. Run `python overlay.py --selftest` and `python overlay.py --bootcheck-only` in the clone; report the failing line. |
| Phone page down | `app status`: phone view off means Settings, Phone is unticked. On but unreachable: `app phone status`, then `app phone refresh` ([Phone page down](#phone-page-down-refresh-tailscale)). |
| Phone buttons disabled | Writes off (`app status` says writes: off) or an Update is running. |
| Update stuck | `app status` shows the Update line; `app logs --log update --tail 60` shows the command it waits on (each has a timeout). Do not restart during an Update. |
| `still starting` reply | The app is loading; repeat in a few seconds. |
| Port in use | `app logs` says control off: another copy holds `127.0.0.1:47200`. Quit the other copy. |

## Hard rules

- Never `shell=True`; fixed argument lists only.
- Never start Claude or Grok yourself through the app: a CLI starts only on Daniel's click or Enter. These verbs never start one.
- Never push to `main`, never force-push. Work on `dev` or a `wip/agents-*` branch.
- No secrets in commands, logs or commits: the token stays in the data dir and is never an argument.
