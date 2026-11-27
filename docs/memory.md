# Memory (notes, inbox, curator, Topic rooms)

MEMORY.1. Your notes live in a private git repo on your PC. The app adds to one inbox file and shows the rest read only.
A separate curator script merges the inbox, makes one commit and pushes to your private remote. Your notes never leave
your PC and that remote: nothing from them goes into this repo, a PR or a chat.

## Layout

The notes root is `memory.root` in `config.json` (Settings › Memory). Empty means the save folder's `memory/`
(`files.dir`, see install-and-update.md). **Create** lays it out:

| Path | What |
|------|------|
| `MEMORY.md` | Index: links to every Learnings and Topics note the curator touched |
| `inbox/cli-avatars-NOW.md` | The app's own inbox. Append only, one writer (the app) |
| `Learnings/<category>.md` | Learnings, decisions and ideas of a category, one line each |
| `Topics/<category>/<topic>.md` | One topic: `Goal:`, `Status:` and `Next action:` on top, then `## Log` with links to chats and tasks |
| `_log/YYYY-MM.md` | Audit trail: one line per consolidation |
| `_app/` | Gitignored: `memory_curator.py`, `status.json` (last run), `consolidate.request` |

`.gitignore` holds `_app/` and `inbox/`. Every note starts with frontmatter:

```yaml
---
type: topic          # topic, resource, learning or index
name: tomatoes
description: ""
topic: Garden/tomatoes
status: active
updated: 2031-04-09
---
```

## Inbox format

The app only appends. Each block:

```
## 2031-04-09 12:00 · topic: Garden/tomatoes · cat: Garden
- type: todo
- text: stake the vines
- source: chat:garden@09:10
```

`type` is `learning`, `decision`, `todo` or `idea`. `text` is one line (300 characters at most). A category that is
not a `Learnings/<category>.md` or `Topics/<category>/` yet goes to **Ideas**. No topic means `general`. The write
holds `inbox/.lock`, the same lock the curator takes to clear what it merged.

**Remember**: right-click a chat message, or **Remember** on a task card. The Memory tab opens with the form filled.
Pick the type and the category, then Save. A soft cue plays unless a task is in focus.

## Curator

`tools/memory_curator.py` is stdlib only. **Create** copies it to `_app/`. It runs nightly from the OS scheduler at
`memory.consolidate_at` (default 03:00). **Consolidate now** only asks it to run: the app writes `_app/consolidate.request`
and `cli_runner.start_curator` starts `python _app/memory_curator.py --root <notes root>` (fixed argv, shell false). With
no Python found, the request waits for the nightly run. The app never edits a note.

One run:

1. `git pull --ff-only` when the repo has a remote and an upstream.
2. Merge the inbox blocks. A topic note gets a log line per new item, deduplicated. A `todo` becomes its `Next action`.
   Learnings, decisions and ideas also go to `Learnings/<category>.md`, deduplicated. `MEMORY.md` gets new links.
3. Append to `_log/YYYY-MM.md`.
4. One commit `memory: consolidate N items` (only the files it changed).
5. `git push` (`-u <remote> HEAD` the first time).
6. Clear the merged blocks from the inbox. Blocks the app appended during the run stay.

Any conflict or failure stops the run. The inbox stays byte-identical, and `_app/status.json` says why. The Memory tab
and the phone show it as a warning. A failed push leaves the commit local. The next run pushes it, and merging the
same blocks again adds nothing. No remote: it commits only and says so. Not a git repo yet: it runs `git init`.

Scheduler lines (Settings › Memory shows them with your paths, with Copy):

```
schtasks /Create /F /SC DAILY /ST 03:00 /TN "CLI Avatars memory curator" /TR "\"<python>\" \"<root>\_app\memory_curator.py\" --root \"<root>\""
0 3 * * * "<python>" "<root>/_app/memory_curator.py" --root "<root>"
```

## Never read

`cli_avatars/app/memory_notes.py` is the one reader. It skips any file or folder whose name (or parent/name) matches:

`.env*`, `.mcp.json`, `.claude/settings.local.json`, `*secret*`, `*token*`, `*password*`, `*credential*`,
`.obsidian/workspace*`, `.git/`, `node_modules/`. Links and anything outside the root are skipped too.

What it reads is data. It is shown with plain labels (desktop) or `textContent` (phone). It is never run, and never
sent anywhere as instructions.

## Memory tab (desktop) and phone

The **Memory** tab in the Dungeon's centre is read only. It has the category and topic tree, topic cards (next action
on top, then goal, status and updated), the inbox count, the last run with its commit hash, any warning,
**Consolidate now** and **Open in Obsidian** (`obsidian://open?path=…`, opened as a URL, no shell). The one write is
Remember. A soft cue plays when a consolidation finishes.

On the phone, the header's notebook button opens the same view read only (`GET /api/memory`). It shows the folder name,
never the path, over the tailnet. There is no write route.

## Tasks rooms and Topic rooms

Every room has a type. **Tasks** rooms are the ones the app had before: session rooms, the rooms you build and
sandboxes. They work as before. A **Topic** room comes from a topic note with `type: topic` or `type: resource`
(topics are resources). It stands off the Apothecary, as a small room in the Scribe's Nook skin, only while its topic is:

- **active**: an open task card or a live session room has that topic;
- **recent**: its note's `updated` is within `rooms.topic_recent_days` (default 7);
- **pinned**: **Pin room** on its card (`ui/topic_rooms.json` in the data folder).

At most four stand at once: pinned first, then active, then most recent. Double-click a Topic room to open its card in
the Memory tab. The card's **Go to room** glides back to it. The phone map shows the same rooms.

## Inactive bots

A roster bot whose status file has not updated for more than `bots.hide_after_hours` (default 3) leaves the Dungeon
and the phone map. It comes back on its next update. Settings › Bots greys it, with when it was last seen, and keeps an
**Always show** pin per bot (`always_show` in `bots/roster.json`). A bot with no status file yet stays shown.

## Settings keys

| Key | Default |
|-----|---------|
| `memory.root` | save folder's `memory/` |
| `memory.consolidate_at` | `03:00` |
| `rooms.topic_recent_days` | `7` |
| `bots.hide_after_hours` | `3` |
