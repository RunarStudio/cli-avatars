# Projects dashboard (PROJECTS.1)

A **Projects** tab in the Dungeon's centre, beside Repos (no new window), and a read-only Projects sheet on the
phone.

## The table

One row per project record (`projects/<slug>.json`, the store REPOS.1 and the MCP project tools use): name,
status, card counts by column, how many topics and chats, and the folder name (never the path). The column chips
(all, doing, todo, review, blocked, done) keep the projects with a card in that column and show only that column's
cards.

The arrow expands a row:

- **Tasks** by column, with the assignee.
- **Topics**: the topics the record lists and those whose project is its slug, name or folder.
- **Chats**: each card's task chats, the per-task CLI sessions with their turns, and Grok topics.
- **Repos**: the folder name and `owner/repo` of the record's repo URL (no host).
- **Decisions**: the five newest asked on its cards or topics.

## Start chat

On a project, topic or task row, with the CLI picked at the top (Claude, Grok, Cursor):

- **Task**: opens that card's task chat in the chat dock (`docs/task-chats.md`); its context pack and task context
  go on stdin at the first Enter.
- **Topic**: opens the topic; the project context block (name, folder, repo, open cards, decisions; redacted, at
  most 1500 characters) is the composer's draft.
- **Project**: the same on its first topic, or a new topic named after it.

Nothing runs: the CLI starts only on your Send or Enter, with its fixed argv and the prompt on stdin.

## Phone

The ledger button opens the sheet: the same rows, tap to expand, the same column chips. Read-only
(`GET /api/projects[?column=]`, `GET /api/projects/<slug>`); start chats from the desktop.

## Code

`cli_avatars/app/projects_view.py` (rows, related, context, Start chat; no Tk), `projects_panel.py` (the tab, reads
through a `StoreThrottle` every 2 s while shown), `webui/projects_routes.py`, `webui/static/projects.js`,
`projects.css`. Tests: `tests/test_projects_view.py`, `tests/test_projects_desktop.py`,
`tests/test_phone_projects.py`.
