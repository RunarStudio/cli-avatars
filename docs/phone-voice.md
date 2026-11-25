# Talk to it from the phone (PHONE-VOICE)

Hold the rune mic on the phone and speak: answer the decision you have open, or start a task chat. The phone shows what
it heard and what it would do, and nothing happens until you tap to confirm. **Speak summary** reads one short line
aloud: where a task is, or what waits on you. No AI call: the browser turns speech into text, and the PC maps that text
with fixed phrases. No new window on the desktop.

## Where the mic is

| Sheet | Mic | Speak summary reads |
|-------|-----|---------------------|
| The decision slip (a decision open in its chat) | Hold to answer it | That decision's task, else what needs you |
| The selected task (under its chats, pack and sandbox) | Hold to start a task chat or draft a reply | The task's done / now / next |
| **Needs you** (the bell) | Hold to start a task chat or draft a reply | How many things wait, by kind |

Hold the mic: the **Speak** sheet slides up with a waveform and a soft rising chime. Speak, then let go: a falling
chime plays, and the transcript and the action appear on a parchment slip. The big mic on the sheet works the same way
for another try. A quick tap without a hold (or a keyboard Enter) opens the sheet with the text box.

## What speech maps to

`voice.py` (no Tk, no I/O) reads the transcript by its first words. Case and punctuation do not matter.

| You say | Action | The confirm tap |
|---------|--------|-----------------|
| `approve`, `yes`, `go`, `go ahead`, `ok`, `accept` + an optional reason | **Answer: Approve** on the open decision | **Answer**: the decision's yes option (`Yes`, `Go`, `Approve`, ...) with the reason as its note; with no such option, the answer is the words `Approved: <reason>` |
| `reject`, `no`, `nope`, `deny`, `decline` + an optional reason | **Answer: Reject** | **Answer**: the no option, or `Rejected: <reason>` |
| `new task <title>`, `create a task <title>`, `start a chat about <x>`, `new chat about <x>` | **New task + chat** | **Create**: one `todo` card in the topic the quick-capture ranker picks from the title (two alternates in the list), with a Claude task chat on it. Claude does not start: your first Send in that chat does |
| Anything else (also `yes` with no decision open) | **Draft reply** | **Use draft**: the text goes into the reply box; you send it yourself |

A leading `because` or `since` comes off the reason: "reject because the glass cracked" is a Reject with "the glass
cracked". Words that only start alike (`nobody`, `gold`, `yesterday`) are a draft, not an answer.

## The confirm

The phone never acts on speech alone. The parsed action is one tap:

- **Answer** goes to `POST /api/decisions/<id>`, the same write as tapping an option on the decision slip (DECIDE.1).
- **Create** goes to `POST /api/capture` with `chat: true`, the same write as quick capture in Task chat mode.
- **Use draft** writes nothing.

Answer and Create need **Allow the phone to open sessions and send prompts** (`web.allow_writes`), the CSRF header and
the write rate limit, like every phone write. With it off the slip still shows, and its button is disabled with the
reason. Starting a CLI stays your own Send: the voice path never runs one.

The transcript map is a read: `GET /api/voice/parse?q=<text>&decision=<id>&current=<topic>`. It works with writes off.

## Spoken summary

`GET /api/voice/summary?task=<id>` gives one line of at most 25 words: the task's title, then `Done: ... Now: ...
Next: ...` from its "where we are" summary ([task-chats.md](task-chats.md#where-we-are-task-summary)), cut at 25 words.
Without `task` it counts the needs-you list: "3 things wait on you: 2 decisions, 1 blocked task." The phone reads the
line with the browser's speech synthesis and shows it as a caption at the bottom (tap to hide).

Focus mode holds it: while another task is in focus, the line is "Held: focus is on <task>." and nothing is spoken;
the needs-you count counts only the focused task's items. The summary of the task in focus speaks as usual.

## On the desktop

Nothing new opens. An answer or a new card lands through the existing stores (decisions, board), so the Dungeon shows
it as if you had tapped it: the decision slip clears, a courier walks the answer to a task it names
([messenger.md](messenger.md)), the new card shows in its topic. The desktop plays the cues those stores already play
(Windows only, Settings), and focus holds them as usual.

## Browser support

The mic uses the browser's Web Speech API (`SpeechRecognition`, `webkitSpeechRecognition`); the summary uses
`speechSynthesis`.

| Browser | Speech to text | Spoken summary |
|---------|----------------|----------------|
| Android Chrome | Yes, over https (`tailscale serve`) | Yes |
| iOS Safari 14.5+ (and the home-screen app) | Yes, over https; iOS asks for the microphone and speech recognition once | Yes |
| Firefox, older browsers, plain http | No: the Speak sheet opens with the text box | Usually yes |

Speech recognition needs a secure page: use the `https://<pc-name>.<tailnet>.ts.net/` address from
[phone-view.md](phone-view.md#use-it-over-tailscale-windows), not plain http.

**Privacy:** the browser may send the audio to its vendor's speech service (Google for Chrome, Apple for Safari) to
turn it into text; the app never sees the audio, only the text. If you do not want that, type in the text box on the
Speak sheet instead: it goes through the same map and the same confirm.

## Sound

On the phone: a soft rising chime when listening starts and a falling one when it stops (the note button in the map
bar turns phone sounds off; the spoken summary is its own tap). The confirm plays the usual done or capture tone.

## Files

| File | Role |
|------|------|
| `voice.py` | `parse` (transcript to action), `task_line`, `needs_line` (the spoken line, at most 25 words) |
| `webui/voice_routes.py` | `GET /api/voice/parse` and `GET /api/voice/summary` (reads) |
| `webui/static/voice.js`, `voice.css` | The rune mic, the Speak sheet, the waveform, the caption |
| `tests/test_voice.py`, `tests/test_phone_voice.py` | The map, the summary, the routes, the confirm through the existing writes |
| `tools/shot_phone_voice.py`, `.js`, `tools/shot_voice.py` | Evidence with made-up data and faked speech |
