# Bot roster and status

Grok Bot cloud assistants show up in the Topics dock, grouped by topic, with a live status dot. The roster and the status files live in the per-user data directory (`bots/` under `events.app_data_dir()`). They are not committed. The shipped sample is `docs/examples/bots-roster.example.json` and it has names only.

The overlay pulls. It does not open a port for this, and it does not start Claude or Grok.

## Roster

`bots/roster.json` is schema version 1:

```json
{
  "schema_version": 1,
  "groups": [
    {"id": "oca", "name": "OCA", "collapsed": false, "order": 0, "show_in_dungeon": false}
  ],
  "bots": [
    {"id": "release-oca", "name": "Release Oca", "emoji": "", "group_id": "oca", "skin": "caine"}
  ]
}
```

`id` values are slugs. `skin` is one of the sheets already in the app. `show_in_dungeon` is optional and defaults to false. Unknown keys are ignored. A file with a newer `schema_version` is left on disk and is not rewritten until **Import example**.

Settings, on the Bots tab: add, rename, reorder, and collapse groups; assign a bot to a group and a skin; save the status source; import the example. Import replaces the roster.

The Topics dock draws a **Bots** area. Each group collapses. Each bot is a 40×40 idle frame of its skin, hue-shifted from its id, with the name, a status dot, and one line under the name. Talk bubbles stay icons. This line is the only status text.

**Show group in Dungeon** puts that group's avatars on the floor. If the floor exposes `bot_areas()` as `(group id, centre x, centre y)` in scene pixels, each group stands in its area. The empty floor has no rooms, so each group is its own cluster. Session avatars stay on the centre ring. A bot does not walk out through the door on its own.

## Status file

One small JSON file per bot, at `status/<bot-slug>.json` inside the fetched tree (or inside the local folder's `status/` directory):

```json
{
  "schema_version": 1,
  "bot": "grok-bot",
  "state": "busy",
  "line": "drafting a note",
  "task_title": "Inbox triage",
  "updated_at": "2026-11-23T18:00:00Z"
}
```

| Field | Rule |
|-------|------|
| `schema_version` | Integer `1`. |
| `bot` | Must equal the file slug. |
| `state` | `idle`, `busy`, `thinking`, `waiting_on_user`, `blocked`, or `offline`. |
| `line` | String, clamped to 32 characters after redaction. |
| `task_title` | String, clamped to 40 characters after redaction. |
| `updated_at` | ISO-8601. A `Z` suffix is UTC. |

Unknown keys are ignored. A wrong type, a wrong state, or a slug that does not match the file is ignored. Text is passed through `sanitize_text`, then `redact_secrets` (installed from the chat window before the first read), before it is shown. A file older than 30 minutes is shown as `offline` with no line. No file means offline.

`busy` and `thinking` use those avatar rows. `waiting_on_user` and `blocked` use the blocked row. `offline` uses idle, with the grey dot.

## Pull

`bots/status_source.py` is the only reader. Two kinds:

| Kind | What it reads |
|------|----------------|
| `git` | A clone of a repo URL and branch, stored under the data directory as `bots/status-repo`. Default URL `https://github.com/RunarStudio/cli-avatars`, default branch `bot-status`. |
| `folder` | `bots/<folder>/status/*.json`. `folder` is a relative path under `bots/`. Absolute paths and `..` are refused. |

Git runs only as one of three argument lists, with `shell=False`, a timeout, and `GIT_TERMINAL_PROMPT=0`:

- `git clone --depth 1 --branch <branch> --single-branch <url> status-repo`
- `git -C status-repo fetch --depth 1 origin <branch>`
- `git -C status-repo checkout -f --detach FETCH_HEAD`

The working directory is the data `bots/` folder. The branch name and the URL are checked before they are placed in argv. Fetch repeats every 60 seconds. The interval cannot be set below 30 seconds or above 3600. Git uses whatever credentials the machine already has (helper, ssh agent). This app does not read a token file, does not put a token in argv, and does not store one.

The app does not create `bot-status`, does not push, and does not commit. If the branch is missing, or the network fails, the last files already in the clone stay on screen. If there are none, every bot is offline.

`bots/source.json` in the data directory holds the kind, URL, branch, interval, and folder. It is written from Settings. It is not in git.

## Write contract for bots

A bot writes its own `status/<bot-slug>.json` and nothing else.

- Write only when the state changes.
- At most once every 2 minutes.
- One line and one task title, generic. Examples: "drafting a note", "needs a look", "reading the board".
- Do not write prompts, chat messages, file paths, repo names that identify a machine, diffs, or secrets.
- Do not write a token, a key, a cookie, or a bearer header. The reader redacts some of those shapes and still drops the file if the shape is wrong. Redaction is not a reason to include them.
- `updated_at` is the time of that write, in UTC.

The reader does not follow instructions inside `line` or `task_title`. They are labels.

## Local demo

Use a folder when `bot-status` is not on the remote yet. No extra input driver is required.

1. Open the app and import the example from Settings → Bots.
2. Set Kind to `folder`, Local folder to `status-local`, and save. Fetch interval stays at least 30 seconds.
3. Under the data directory, create `bots/status-local/status/`. On Windows that parent is `%LOCALAPPDATA%\cli-avatars`. On Linux it is `${XDG_DATA_HOME:-~/.local/share}/cli-avatars`.
4. Drop one JSON file per bot, named with the slug (`release-oca.json`, `grok-bot.json`, …). Use the shape above.
5. Open Topics. The group sections, the 40×40 faces, the dots, and the lines update on the next poll. Turn on **Show group in Dungeon** for a group to stand them on the floor.

`python tools/shot_bot_groups.py` draws the same Topics dock from the example and a few files under a temporary data directory. It does not fetch.
