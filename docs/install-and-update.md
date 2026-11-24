# Install and update

CLI Avatars installs per user on Windows and can rebuild itself from the `dev` branch. The installer does not need an administrator account. Updating uses the git credentials already on the machine. The app does not read those credentials, does not store tokens, and does not put them on a command line.

## First install on your PC

1. Install Python 3, git, PyInstaller (`python -m pip install -r requirements-build.txt`), and Inno Setup 6.6 or newer.
2. Clone dev: `git clone --branch dev https://github.com/RunarStudio/cli-avatars.git`, then `python -m pip install -r requirements.txt` in it.
3. Build the installer: `python tools/build_installer.py`.
4. Run `dist\CLI-Avatars-Setup.exe` and start CLI Avatars from the Start menu.
5. To get the latest dev later, press **Update** on the toolbar.

## Your Claude and Grok sessions, and the chat (Windows)

1. Run `claude` and `grok` in a normal Windows terminal, not in WSL. The app reads `%USERPROFILE%\.claude\projects` and `%USERPROFILE%\.grok\sessions` (`%GROK_HOME%\sessions` when `GROK_HOME` is set). A session shows while it was active in the last 15 minutes: send an idle one a prompt. If `.grok\sessions` does not exist after a Grok run, your Grok CLI keeps its sessions elsewhere: set `GROK_HOME` to that folder's parent.
2. For live status and chat context, run this once in the clone, then restart your sessions: `python -m cli_avatars_emit hooks install --apply` (`python` must be on `PATH`; details in [claude-hooks.md](claude-hooks.md)).
3. Press **Chat** on the toolbar, or click an avatar. In the **Run** row, pick **Claude**.
4. The first time, the row shows the Claude CLI it found on `PATH`. Press **Use this binary**. If it says not found, run `where claude` in a terminal and fix `PATH` first.
5. Type a prompt and press Enter. The first time, pick the project folder in the dialog. Runs start in `plan` mode; click `plan` to switch.
6. Grok in the chat comes with ROOM-CHAT.6. Until then Grok sessions show as avatars and in the status bar only.

Check: the status bar lists `Claude 1` and `◆ Grok 1` (your counts), and the chat shows your prompt, `… claude is answering`, the reply, and `[ok]`.

## Install

`tools/build_installer.py` builds an onedir app with PyInstaller (`packaging/cli_avatars.spec`) and then compiles `packaging/installer.iss` with Inno Setup 6.6 or newer. The version string comes from `cli_avatars/__version__.py`. The build writes the current commit into `version.json` beside the executable and into `build_stamp.json` inside the bundle. A frozen boot check reads that `version.json` and shows the first 12 characters of the commit on the status line.

The installer chooses:

| | |
|---|---|
| Scope | Current user (`PrivilegesRequired=lowest`) |
| Program files | `%LOCALAPPDATA%\Programs\CLI Avatars` |
| Start menu | CLI Avatars |
| Desktop shortcut | Optional, off by default |
| App data | The existing per-user directory, `%LOCALAPPDATA%\cli-avatars` |

App data is not inside the program folder. Uninstall removes the program folder. It deletes app data only when the uninstall checkbox is ticked. A silent uninstall leaves app data in place. That directory holds chat, settings, the boot-check history, the update log, and the source clone.

The portable onefile executables from `build.ps1` are unchanged.

## Update

**Update** on the Dungeon toolbar, in the WINDOW group, starts the update. Settings, in the Dungeon dock, shows the version, the short commit, and the last time an update was checked. **Update app** in Settings and in the tray menu does the same. Progress is a line on the status bar. The button does not open a window.

The buttons stay disabled, with the reason beside the Settings button and as the toolbar button's tooltip, when `git` is not on `PATH` or when `python -m PyInstaller --version` fails. A source checkout shows "Running from source" because there is no install folder to swap.

An installed build keeps a clone at `%LOCALAPPDATA%\cli-avatars\src`. The first update clones `https://github.com/RunarStudio/cli-avatars.git` on branch `dev`. `config.json` may set `update.repo_url` to another `https://github.com/<owner>/<repo>.git` URL. A URL with a username, a token, or a non-https scheme is rejected and git is not started. `update.channel`, when present, must be `dev`.

Update runs only these commands, each as an argument list with `shell` false and a timeout. Combined output is appended to `update.log` in the data directory. Userinfo in an https URL is stripped from that log.

1. `git fetch origin dev`
2. Compare `origin/dev` with the installed commit (`version.json`, else the bundled stamp).
3. If that commit is the same, stop. The status line says up to date.
4. If the installed commit is not an ancestor of `dev`, stop. The pull is fast-forward only.
5. `git pull --ff-only origin dev`
6. `python overlay.py --selftest` and `python overlay.py --bootcheck-only` in the clone. A failure does not build.
7. `python -m PyInstaller` using `packaging/cli_avatars.spec`, into a staging folder beside the install directory.

The app then starts `python -m cli_avatars.update.helper` from the clone and exits. The helper renames the current folder to `CLI Avatars.old`, renames staging into place, and runs `cli-avatars.exe --bootcheck-only`. If that fails, it moves the new folder aside as `CLI Avatars.failed`, puts `.old` back, and relaunches the previous build. If it passes, it relaunches the new build.

Git inherits the environment, including an existing credential helper, and `GIT_TERMINAL_PROMPT` is set to `0` so a missing login fails instead of waiting. Chat, inbox, hooks, and MCP arguments are not commands and are not passed to these processes.

## Build the installer

From the repository root, with PyInstaller and Inno Setup 6.6 or newer installed:

```bat
python -m pip install -r requirements-build.txt
python tools/build_installer.py
```

`requirements-build.txt` installs PyInstaller. Inno Setup 6.6 or newer provides `ISCC`. The uninstall dialog calls `CreateCustomForm` with a client width, a client height, and two keep-size flags, which is the signature from 6.6 onward. Put `ISCC` on `PATH`, or install it in the normal per-user Programs folder or in Program Files. If either tool is missing, the script names it and exits 2. It does not download the tools and it does not install the app.

The setup program is `dist\CLI-Avatars-Setup.exe`.

## Windows check (SpiderHost)

Use a temporary program folder and a temporary data directory. Do not point this check at the real `%LOCALAPPDATA%\Programs\CLI Avatars` unless that install is a separate, intentional one.

PyInstaller and Inno Setup 6.6 or newer have to be installed on that machine before `tools/build_installer.py` can produce the setup program. Git has to be on `PATH` before **Update app** will enable. The machine's existing git credentials are used; do not paste a token into config or into the command.

```bat
git clone --branch wip/installer --single-branch https://github.com/RunarStudio/cli-avatars.git %TEMP%\cli-avatars-installer-src
cd /d %TEMP%\cli-avatars-installer-src
python -m pip install -r requirements.txt -r requirements-build.txt
python -m unittest discover -s tests
python -m ruff check cli_avatars tests tools
python overlay.py --selftest
python overlay.py --bootcheck-only
python tools/build_installer.py
set CLI_AVATARS_DATA_DIR=%TEMP%\cli-avatars-installer-data
dist\CLI-Avatars-Setup.exe /DIR=%TEMP%\cli-avatars-install-check /CURRENTUSER
```

Launch `cli-avatars.exe` from that temporary folder. The status line includes the version and commit. Settings shows the same version, the commit, and **Update app**. If git or PyInstaller is missing, the button is disabled and the reason is next to it. Quit, uninstall from that temporary folder, and leave the app-data checkbox unticked. `%TEMP%\cli-avatars-installer-data` can be deleted afterwards; it is not the real data directory when `CLI_AVATARS_DATA_DIR` is set.
