# Mailroom (MAILROOM)

Every new thought, message to you or question from a hook lands in one place, the Mailroom. A sorter reads each
letter and proposes where it goes: a topic, whether to open a task chat, and a draft decision when the letter asks
something. Nothing is filed until you approve. You only approve, bounce, or change the topic first.

## What lands here

| Source | What | Not taken |
|--------|------|-----------|
| `capture` | A thought sent with **Mail**: the Dungeon's capture strip (Ctrl+Space, then **Mail**) or the phone's quick capture (**Mailroom**). | Empty text. Card and Chat captures still file at once, as before. |
| `message` | A channel line addressed to you (`to: user`): an agent's inbox message, `cli-avatars-emit say --to user`, an MCP `say` to you. | Lines in a task chat (`task-<8 hex>-<n>`: they belong to a task); your own lines; `emit:*` notes (the board's own); decisions (they have their own card); a line in a room where you wrote in the last 10 minutes (you are in that conversation). |
| `hook` | An agent's Stop note (the hook's `say` to itself) that contains a question. | Stop notes without a question: they are status, not mail. |

- New lines are taken from the channel logs as they come (`mailroom.ingest`, at most once a second on the desktop and
  on each phone read). The first start sets a cursor and takes no backlog.
- Each line is taken once (by its id, else room, time and sender), even after it is filed or dropped.
- The Mailroom keeps at most 200 letters in `mailroom.json` in the data dir, so it survives a restart.

## The sorter

Local code only: no AI call, no CLI, no network (`mailroom.propose`).

| Proposal | Rule |
|----------|------|
| Topic | The quick-capture ranker (`registry.capture`): the letter's words against each open topic's name and title, its open task titles and its recent chat lines. On a tie or no match, the room the message came from; else the first topic by id. |
| Task chat | Yes when a sentence starts with a work verb (fix, add, build, write, check, review, update, plan, research, …). |
| Draft decision | The first question in the letter: a sentence ending in `?`, or one that opens with a question word (should, can, which, what, …). |

## Approve, edit, bounce

| Action | Desktop | Phone | What happens |
|--------|---------|-------|--------------|
| Approve | **✓ Approve**, Enter or **A** | **✓ Approve** | One `todo` card in the topic, written as Daniel through the same path as a capture (`registry.capture`); a Claude task chat on it when proposed (no CLI starts: the first Enter in the chat does); the draft decision asked on the card, by the agent that wrote the letter (else `emit:mailroom`), so the card's topic waits on you. The letter leaves the Mailroom; the `filed` cue plays. |
| Change topic | **T** (the next ranked topic) or a click on the topic chip (all topics) | The topic list on the slip | Only that letter's topic changes. Task-chat rooms are not topics to file in. |
| Bounce | **↩ Bounce**, **B** or Delete | **↩ Bounce** | A new letter goes to **Unsorted** (kept, still fileable). A letter already in Unsorted is dropped (**✕ Drop**). Nothing is filed. |

A letter is taken out of the store before it is filed, so a second Approve (another device, a double tap) cannot file it
twice; if filing fails the letter goes back.

## Focus mode

While a task is in focus ([focus-mode.md](focus-mode.md)), letters that arrive after focus began wait, unless the
sorter put them in the focused task's topic. They are not shown, make no sound, and the room says **N held (focus)**.
When focus ends they appear with one `letter` cue. The Needs you row for the Mailroom is held the same way.

## Desktop

The **Mailroom** tab in the Dungeon's centre (beside Recap), drawn in code (`mail_art.py`): a brass plaque, a wooden
pigeonhole shelf whose cubbies fill with letters as the count grows (one per cubby, then stacking), a burlap mail sack
with envelopes peeking out, a wall torch, and a plank sorting board. Each letter hangs on the board as a parchment
slip: source, room, sender and age; the text; `Decide: …` when there is a draft; `+ task chat` when one is proposed;
the topic chip; **✓ Approve** and **↩ Bounce**. Unsorted letters sit below as smaller grey slips. The tab reads
`Mailroom (N)`.

- Keys (the room has focus after a click or on opening): ↑/↓ select, Enter or A approve, B or Delete bounce, T next
  topic. They live on the room's canvas only, so they do not clash with the board's F or the capture strip's
  Ctrl+Space.
- Everything changes in place: slips are keyed by letter; only text, position and the shelf image change.
- **Needs you** gets one `MAILROOM` row, "N letters to sort", while letters wait; a click opens the tab. Clear hides it
  until a new letter comes.

## Phone

The envelope in the map bar (beside the bell) shows the count and opens the **Mailroom** sheet: the same slips on a
plank board, each with its topic list, **✓ Approve** and **↩ Bounce** (**✕ Drop** in Unsorted). The quick capture
sheet has a third mode, **Mailroom**, that drops the thought there unfiled. Writes need **Allow the phone to open
sessions and send prompts** (`web.allow_writes`) and the CSRF header; with it off the sheet only reads. The SSE event
`mailroom` keeps it live.

| Route | Answer |
|-------|--------|
| `GET /api/mailroom` | `{"items", "unsorted", "count", "held", "topics", "writes"}`; each letter has `id`, `source`, `ts`, `text`, `from`, `room`, `topic`, `topic_title`, `chat`, `draft`, `state`. |
| `POST /api/mailroom` `{"text"}` | Writes on: one letter (`capture`); 400 empty, 413 over 2,000 characters. |
| `POST /api/mailroom/<id>/topic` `{"topic"}` | Writes on: 200, 404 no such letter or topic, 400 bad body. |
| `POST /api/mailroom/<id>/approve` `{}` | Writes on: 200 with the card `id`, `topic`, `room` (or null) and `decision` (or null); 404 no such letter. |
| `POST /api/mailroom/<id>/bounce` `{}` | Writes on: 200 with `now`: `unsorted` or `dropped`; 404 no such letter. |

## Sound

| Cue | Desktop (`cues.py`, Windows, off in Settings) | Phone (note button) |
|-----|-----------------------------------------------|---------------------|
| Letters arrive | `letter`: a letter slid into a pigeonhole (a papery swish, a muted wooden tap), once per batch | Soft falling two-note |
| Filed | `filed`: a wax seal pressed (a thud and a knock) and a small bright pluck | Low then high note |

Silent while a task is in focus.

## Code and tests

`mailroom.py` (no Tk: `post`, `ingest`, `propose`, `approve`, `retopic`, `bounce`, `public`, `counts`, `needs_row`),
`cli_avatars/app/mail_panel.py` (tab, keys, cues), `cli_avatars/app/mail_art.py` (room, shelf, sack, slips),
`capture_strip.py` (Mail), `needs_you.py` and `needs_panel.py` (the `mail` row), `webui/mail_routes.py` (routes),
`webui/server.py` (the `mailroom` event), `webui/static/mailroom.js` and `mailroom.css`.
Tests: `tests/test_mailroom.py`, `tests/test_mailroom_desktop.py`. Evidence:
`xvfb-run -a python tools/shot_mailroom.py <out-dir>` (made-up data).
