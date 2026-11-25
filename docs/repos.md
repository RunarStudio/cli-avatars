# Repos (REPOS.1)

The **Repos** tab in the Dungeon's centre lists the folders your agents work in and shows, live, which of them are
working in each one right now: Caine (the main orchestrator), sub-orchestrators and subagents. It answers "is the
app using my repo for Caine and the others?".

## Add and remove

- **Name** and **Folder**: type a full path, or pick it with **Browse…**. The folder must exist on this PC; a
  relative path or one with `..` is refused with the reason.
- The folder is stored as the `path` of the project record named after the repo (`projects/<slug>.json`, the
  same store the MCP project tools use). An existing project keeps its requirements, key files and topics.
- **Remove** clears the record's `path`; the project record and its other fields stay.
- Rows show the folder name only, never the full path.

No git command is run and nothing inside the folder is read: no commits, branches or pull requests.

## In use

Once a second (`cli_avatars/app/repos_live.py`) every live session's working folder is compared with each repo's
folder. A session is in a repo when its folder is the repo's folder or below it. The working folder comes from the
session transcript's `cwd` (Claude) or summary (Grok) and is kept in memory only (`sessions.agent_cwd`).

- **Caine**: the session in the throne (main) room; with no main room, the first top-level session.
- **Sub-orchestrator**: any other top-level session.
- **Subagent**: the children of a session in the repo.

A row with agents shows a lit wax seal, `IN USE`, and one line per agent: role, name, and since when. Rooms whose
agents are in a repo carry a small hanging badge on the map with the repo's folder name (two at most, then `+n`).

A repo going in use plays a soft `rune` cue on Windows (a low hum and a glassy ping). It waits while a task is in
focus, stays quiet for repos already in use when the app starts, and `sound.cues: false` turns it off.

## Phone

The App sheet lists the repos read-only, with the same seal, roles and times (`GET /api/repos`, folder names only).
With **Allow the phone to open sessions and send prompts** on, it can also add (`POST /api/repos` with `name` and
`path`) and remove (`POST /api/repos/<slug>/remove`), with the pairing cookie and the CSRF header like other writes.
The phone server alone (`python -m webui`) shows every repo idle.
