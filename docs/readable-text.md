# Readable text (FONT.1)

Every piece of text in the Dungeon (panels, tabs, chat, cards, door signs, plaques, standup bubbles, Settings) and on the phone uses one text face, chosen in Settings. The pixel-art frames, kit art and colours stay as they are; only the letters change.

## The faces

| Choice | Why |
|--------|-----|
| **Atkinson Hyperlegible** (default) | Made by the Braille Institute for low-vision readers: `I l 1`, `O 0` and `b d p q` all have distinct shapes. |
| Lexend | Built to reduce visual stress, with wide letters and open spacing. |
| OpenDyslexic | Heavy bottoms keep letters from flipping or rotating. Some readers prefer it. |
| Pixel | The old look: Courier and the 3x5 pixel font on signs. |

All three readable faces are SIL Open Font License 1.1. The files and each font's `OFL.txt` sit in `assets/fonts/<font>/`. They were fetched from upstream (Google Fonts for Atkinson Hyperlegible, `googlefonts/lexend`, `antijingoist/opendyslexic`). The WOFF2 copies of Atkinson and Lexend were converted from those TTFs with fontTools.

## Switch it

Settings → Display → **Text font**. Every name is drawn in its own face, followed by **Text size** (S, M, L), **Letter spacing** (on or off) and a live sample line. A change applies at once and is saved in `config.json`:

```json
{"text": {"font": "atkinson", "size": "M", "spacing": true}}
```

The phone reads the same keys from `/static/text.css` (read-only) and gets the same face as WOFF2.

## How it works

- `text_fonts.py` owns the family, sizes and spacing. It registers the files for this process only: on Windows with `AddFontResourceExW` (private), on Linux as a fontconfig app font. Nothing is installed and no admin rights are needed. If Tk cannot see the face, it falls back to a system sans and logs one line.
- Widgets use named Tk fonts (`DungeonText`, `DungeonTitle`, `DungeonBubble`, and `fonts.face(pt, ...)` for the rest), so a switch restyles the window in place. There is no hard-coded Courier or Consolas; `tests/test_readable_font.py` checks this.
- Sizes: at M, body text is 12 pt or larger. Text widgets get a line height near 1.5, and chat lines wrap to the dock at no more than about 70 characters. Short caps labels become sentence case unless Pixel is chosen. Pure white text is now off-white (`fonts.OFF_WHITE`).
- Signs, plaques and standup bubbles build their frame at 1x, scale it with nearest-neighbour, then write the words with Pillow at full resolution using the same font file (`art_words.py`).
- Letter spacing: Tk cannot space letters, so in the desktop window the toggle adds paragraph room in text boxes. Pillow-drawn words and the phone get real letter spacing.

Evidence: `python tools/shot_fonts.py <out-dir>` under Xvfb.
