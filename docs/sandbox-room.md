# Sandbox room (SANDBOX)

**Try it risky** on a task makes a throwaway copy of its repo on a branch of its own, with its own task chat.
A small cracked chamber appears on the Dungeon floor, and the chat's avatar works inside it. When the idea is done,
one tap keeps it (**Promote**, the seal) or drops it (**Bin**, the trapdoor).

## What Try it risky does

1. It reads the folder of the task's topic room (Folder… in its chat) and finds that folder's git repo
   (`git rev-parse --show-toplevel`) and its current commit (`git rev-parse --verify HEAD`).
2. It runs `git worktree add -b sandbox/<card8>-<slug> <repo>-sandboxes/sandbox-<card8>-<slug> <head>`.
   `<card8>` is the first 8 characters of the task id; `<slug>` comes from the title (`-2` to `-9` when taken).
   The folder sits beside the repo, never inside it.
3. It starts a new Claude task chat on the card ([task-chats.md](task-chats.md)) whose folder is the worktree,
   and opens it in the dock. No CLI starts until you press Enter there.

It refuses a task with no folder, a folder that is not a git repo with a commit, and a task that already has a live
sandbox. If the chat cannot be made, the worktree and branch are removed again.

## Promote and Bin

| Action | Git | Result |
|--------|-----|--------|
| **Promote** (seal) | `git worktree remove <folder>` (no force) | The branch stays; the card shows its name to copy. Merge or push it by hand. A worktree with uncommitted changes is kept and the card says so. |
| **Bin** (trapdoor) | `git worktree remove [--force] <folder>`, then `git branch -D sandbox/<…>` | The folder and the branch are gone. With uncommitted changes, Bin asks once more (**Bin anyway**); only then `--force`. |

Bin only deletes a branch that matches `sandbox/<8 hex>-<slug>`, that this feature recorded, and that the folder is
still on (`git worktree list --porcelain`). Anything else is left alone with a message.

Nothing here pushes, merges, fetches, checks out your own tree or touches a remote. Git runs in the runner (`cli_runner.run_git`,
reached through `chat_window.sandbox_git`) with a fixed argv, no shell, no terminal prompt and a 30 s timeout;
`cli_avatars/runner/sandbox_git.py` allows only the commands above. No AI is called.

## The chat in the sandbox

The sandbox chat is a normal task chat with two changes: its folder is the worktree, and every prompt carries the
line `sandbox: throwaway branch, may be binned` ahead of the task context, after the context pack on a fresh
session ([context-packs.md](context-packs.md)).
Once the sandbox is binned the chat has no folder, so Enter asks for one.

## Store

`sandboxes.json` in the app data dir (never in git): per sandbox its id, card, chat room, branch, repo, folder, base
commit, state (`live`, `promoted`, `binned`), times and whether the folder was kept. It survives a restart; it keeps
the newest 200. A malformed file reads as empty.

## Desktop

- **Card**: under the card's chats, the **Sandbox** slip (a cracked rune tablet) offers **⚠ Try it risky**. With a
  live sandbox it shows the branch (Copy), **Promote**, **Bin** and **Open chat**.
- **Dungeon floor**: each live sandbox is a small chamber off the Apothecary, in the ember-cistern stones, with ember
  cracks across the floor, a rune fence on its open sides and a warning brazier. Cracks, runes and the brazier
  glow steadily. The chat's avatar stands inside while the chat runs. A promoted chamber is sealed in gold and fades out;
  a binned one opens a pit and drops into the dark (1.6 s). No window opens.

## Phone

Tap a task with a sandbox: the Sandbox slip shows its state, branch (Copy) and note, live over the SSE `sandbox` and
`change` events. With `web.allow_writes`, **Promote** and **Bin** (and **Bin anyway** after a dirty refusal) post to
`/api/cards/<id>/sandbox` with the CSRF header. A sandbox is made on the desktop only. See
[phone-view.md](phone-view.md#sandbox).

## Sound

`risky` (stone cracks, a rumble, the brazier catching), `seal` (a slab sliding shut and a rune chime) and `trapdoor`
(a latch, a creak, a thud below), drawn in code in `cli_avatars/app/sandbox_cues.py`. They play on Windows only and
are held while another task is in focus ([focus-mode.md](focus-mode.md)).

## Code

| File | Role |
|------|------|
| `sandbox.py` | Store, Try it risky, Promote, Bin, the chat's folder and line |
| `cli_avatars/runner/sandbox_git.py`, `cli_runner.run_git` | The allow-list and the only place git runs |
| `cli_avatars/app/sandbox_card.py` | Card slip |
| `cli_avatars/app/sandbox_rooms.py` | Chambers in the floor layout |
| `cli_avatars/app/sandbox_art.py`, `sandbox_view.py` | Chamber art and its animation |
| `cli_avatars/app/sandbox_cues.py` | Cues and their focus gate |
| `webui/sandbox_routes.py`, `webui/static/sandbox.js`, `sandbox.css` | Phone |

Tests: `tests/test_sandbox.py` (fixture repos in a temp folder only). Evidence: `python tools/shot_sandbox.py <dir>`
under Xvfb.
