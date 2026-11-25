# Decisions on tasks (DECIDE.1)

An agent asks Daniel a decision on a task. The task shows it waits on him, he is told on the PC and on
the phone, and he answers by tapping an option or typing. The answer goes back to the agent that asked.

The question, options and answer are data: stored and shown, never run.

## Asking

| Path | Call | Who may ask |
|------|------|-------------|
| MCP | `task_decide(agent_id, card_id, question, options?)` | An agent that may change the card (Decision D): assigned to it, or unassigned in a topic that lists it. |
| Task chat | A reply line `TASK ask <question> \| <option> \| <option>` | The chat's CLI, on its own card only ([task-chats.md](task-chats.md)). |
| Python | `AgentApi.decision_ask(agent, card_id, question, options=None)` | Same as MCP. |

- `question`: redacted (`redaction.redact`), absolute and home paths hashed (Decision K), at most 240 characters. Empty is `schema`.
- `options`: none, or two to six labels of at most 120 characters each, stored as `a`–`f`. Seven, or an empty label, is `schema`.
- Refused: another agent's card or a topic the agent is not in (`not_owner`), `daniel` or `user` as the asker (`not_agent`), a missing card (`missing`), a card that is done, archived or has no topic (`not_allowed`), more than 10 asks an hour per agent or 30 writes a minute (`rate_limited`). A refusal writes nothing.
- The MCP arguments are capped at 4 KiB, like every task tool.

## What an ask writes

1. One open row in `decisions.jsonl` (the same store as the chat's decision cards) with `card` set. Its `room` is the card's topic, or the task chat that asked.
2. The question on that room's channel, so it shows in the room chat.
3. A `decision` event on the card: `asks: <question>`, actor the agent, `via` `mcp` or `chat`.
4. The card's topic `open` → `waiting_on_user` (Decision F). A `done` topic stays `done`.

## Answering

`Registry.decision_answer(decision_id, choice=None, text=None)`: a letter, free text (at most 1,000), or both (the text is a note on the choice).

1. The answer goes to the asker's inbox as `decision_answer` (`text` is the label, the note, or `label: note`) and to the room's channel.
2. The row turns `answered` with `choice`, `answer` and `answered_ts`.
3. A `decision` event on the card: `answered: <answer>`, actor `daniel`.
4. When no open decision is left in that topic, it goes back `waiting_on_user` → `open`.

A second answer is `answered`; an unknown id is `missing`; a letter that is not an option, or neither a letter nor text, is `schema`.

A task chat sees its card's newest three decisions in the task context on every prompt: `- waiting on Daniel: <question> (a) …, b) …)` or `- <question> -> Daniel: <answer>`.

## Reading

- `registry.task_decisions.pending(directory)`: open decisions on live cards, oldest first, with the card's `title`, `topic`, `project`, `column`.
- `open_by_card(directory)`: card id → open count. `for_card(directory, card_id)`: every decision on one card.
- MCP `decisions_list(open_only)` lists them too (with `card` and `answer`).

## Desktop

- **Tasks tab** ([board.md](board.md)): a gold DECIDE tag on the card (`DECIDE ×2` for two), `◆<n>` on the column head, and the "Decisions (N)" filter. It turns wine while any decision is open and gold while on; it shows the waiting cards from every topic.
- **Card panel**: one gold slip per open decision at the top: `<agent> asks`, the question, a button per option, a text box and "Answer" (Enter works). An option click sends the typed text as its note. A decision from a task chat opens that chat in the dock after the answer. The history shows `asks: …` and `answered: …`.
- **Notice** (`cli_avatars/app/decide_watch.py`, read twice a second from the overlay tick): when a new decision arrives,
  - the `decide` cue plays: three rising bell strikes, distinct from the `arrive` knock (`cues.py`, off with `sound.cues` false; Windows plays it, elsewhere it is silent);
  - the tray icon shows a toast `Decision · <task title>` with the question (pystray `notify`; no tray, no toast);
  - the asking agent needs Daniel (DOOR.1): on the desktop its avatar walks to the pointer, inside the Dungeon it waits at the door and the closed arch flashes; its topic is `waiting_on_user`, so the AV.1 walk brings it beside him there. A click on the avatar stops the walk until the next decision.
  The first read after a start learns what is already open and stays quiet. No new window.
- The chat panel shows a task decision with options like any decision card; one without options says to answer on the task card or the phone.
