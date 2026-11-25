// YOU-AVATAR: on the phone map, a bobbing kind-coloured "!" / "?" bubble over every avatar that needs you, and a
// crown with the count badge over your own avatar. Read-only: the scene's avatars carry `need` and `badge`.
"use strict";

const YOU_COLOURS = { decision: "#ffcf4a", blocked: "#e0566a", reply: "#7aa8ff", run: "#6ad08a" };
const YOU_GLYPHS = {
  "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
  "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
};
const YOU_GLYPH = { decision: "?", blocked: "!", reply: "?", run: "!" };

function youPixels(rows, x, y, fill) {
  ctx.fillStyle = fill;
  rows.forEach((row, j) => [...row].forEach((c, i) => { if (c === "#") ctx.fillRect(x + i, y + j, 1, 1); }));
}

// a 13x15 balloon whose tail tip sits on (0, 0)
function youBubble(kind) {
  ctx.fillStyle = "#140a14";
  ctx.fillRect(-6, -15, 13, 12);
  ctx.fillRect(-2, -3, 5, 1);
  ctx.fillRect(-1, -2, 3, 1);
  ctx.fillRect(0, -1, 1, 1);
  ctx.fillStyle = "#fffaec";
  ctx.fillRect(-5, -14, 11, 10);
  ctx.fillStyle = YOU_COLOURS[kind];
  ctx.fillRect(-4, -13, 9, 8);
  ctx.fillRect(-1, -4, 3, 1);
  youPixels(YOU_GLYPHS[YOU_GLYPH[kind]].filter((_r, j) => j !== 5), -2, -13, "#140a14");
}

function youCrown() {
  ctx.fillStyle = "#140a14";
  ctx.fillRect(-6, -7, 13, 6);
  ctx.fillStyle = "#e8b240";
  ctx.fillRect(-5, -4, 11, 2);
  for (const x of [-5, 0, 5]) ctx.fillRect(x, -6, 1, 2);
  ctx.fillStyle = "#ffeea0";
  for (const x of [-5, 0, 5]) ctx.fillRect(x, -7, 1, 1);
  ctx.fillStyle = "#dc283c";
  ctx.fillRect(-3, -3, 1, 1);
  ctx.fillRect(3, -3, 1, 1);
  ctx.fillStyle = "#468cff";
  ctx.fillRect(0, -3, 1, 1);
}

function youBadge(n) {
  const text = n > 9 ? "9+" : String(n);
  ctx.fillStyle = "#140a14";
  ctx.beginPath();
  ctx.arc(0, 0, 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#d6344a";
  ctx.beginPath();
  ctx.arc(0, 0, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.font = "700 7px ui-monospace, Menlo, Consolas, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 0, 0.5);
}

// over the room labels and plates, in the map's own frame
function drawYouOver(now) {
  if (!state.scene || !state.scene.sprites) return;
  const v = state.view, k = Math.max(1, 1.6 / v.s);
  ctx.save();
  ctx.translate(v.x, v.y);
  ctx.scale(v.s, v.s);
  for (const w of state.walkers.values()) {
    const a = w.a, meta = state.scene.sprites[a.sprite];
    if (!meta || (!a.need && a.kind !== "user")) continue;
    const [x, y] = place(w, now);
    const head = y - meta.h * (1 - meta.feet);
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    if (a.kind === "user") {
      ctx.save();
      ctx.translate(Math.round(x), Math.round(head + 2));
      youCrown();
      ctx.restore();
      if (a.badge) {
        ctx.translate(Math.round(x + 9 * k), Math.round(head + 2));
        ctx.scale(k, k);
        youBadge(a.badge);
      }
    } else if (YOU_COLOURS[a.need]) {
      const bob = Math.sin(now / 160 + (hashNum(a.id) % 7)) * 1.5;
      ctx.translate(Math.round(x), Math.round(head - 1 + bob));
      ctx.scale(k, k);
      youBubble(a.need);
    }
    ctx.restore();
  }
  ctx.restore();
}
