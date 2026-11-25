# Needs you (NEEDS-YOU.1)

One list, on the desktop and the phone, of what waits on Daniel. Each row names the task or room, the kind and the age. A tap opens it; **Clear** hides it until it changes.

## What is listed

| Kind | Source (no second store) | Opens | Leaves when |
|------|--------------------------|-------|-------------|
| Decision | Open rows of `decisions.jsonl` ([decisions.md](decisions.md)); a task decision on an archived card is left out | The card (desktop), the question's chat with the slip (phone) | It is answered |
| Blocked | Cards in the `blocked` column of every board, not archived ([board.md](board.md)) | The card | The card leaves `blocked` |
| Reply | Channel lines to `user` in a room after Daniel's last line there (decision lines are left out) | The room chat | Daniel writes in that room |
| Run ended | The newest `prompt` event per room on the boards (room and task chat runs, [room-chat.md](room-chat.md)): `ok`, `error` or `timeout`; `stopped` is left out | The room chat | Daniel writes in that room |

- A reply and an ended run in the same room are one row; it shows as a reply.
- Order: decision, blocked, reply, run ended; inside a kind the oldest first.
- Replies and ended runs older than three days drop out; decisions and blocked cards stay until they are done.
- Text is shown as data (sanitised, 160 characters), never run.

## Clear

- Clear stores the row's last change (`needs_you.json` in the data dir: key → time). The row stays hidden after a restart.
- A newer change brings it back: another reply, another run, the card edited while still blocked.
- Keys: `decision:<id>`, `card:<id>`, `room:<room>`. At most 500 are kept, the oldest go first.

## Desktop

- The right dock has a **Needs you (N)** tab beside Chat (no new window). The count is on the tab.
- Read at most once a second from the overlay tick, and only when a source file changed. Rows change in place; only the age text moves.
- A row click: a card opens on the Tasks tab with its card panel; a room opens its chat in the dock. **Clear** on the row clears it.
- An item that enters plays the soft `arrive` cue (`cues.py`, off with `sound.cues` false; Windows plays it). A new decision rings the `decide` bell instead. The first read after a start is quiet.

## Phone

- A bell button in the map bar, lit with a count while anything waits; it rings when an item enters and the soft reply tone plays (the note button).
- The bell opens the **Needs you** sheet: one row per item, kind colour, title, age, detail. A tap opens it (a decision opens its slip, a card its task, a room its chat).
- **Clear** needs **Allow the phone to open sessions and send prompts** (`web.allow_writes`); reading works without it.
- With the page closed: decisions and blocked tasks also come as a system notification once **Alerts when closed** is on ([phone-view.md](phone-view.md#web-push-alerts-with-the-page-closed)).
- Live: a change of any source or of `needs_you.json` sends the SSE `change`, and the page reloads the list.

| Route | Answer |
|-------|--------|
| `GET /api/needs-you` | `{"items": [{key, kind, ts, title, detail, room, card}], "count": n}` |
| `POST /api/needs-you/clear` `{"key": "…"}` | `200 {"ok": true}`; `400` bad body or key; `404` no such live item. CSRF header, pairing cookie, rate limit and body cap as PHONE.2. |

## Code

- `needs_you.py`: `pending`, `collect`, `merge`, `clear`, `stamp`. No Tk.
- `cli_avatars/app/needs_panel.py`: the dock tab and its tick step.
- Tests: `tests/test_needs_you.py`, `tests/test_needs_you_desktop.py`, `tests/test_phone_needs_you.py`.
