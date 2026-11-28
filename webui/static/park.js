// PARK.1 + IDLE-PROPS.1 on the phone map, read-only. The park and the idle objects are in the map image; this adds
// what moves: lamp halos breathing and fireflies over the park, a soft glow at each object in use, the act under each
// idling avatar's feet and each project room's task table with its doing and todo cards.
"use strict";

const PARK_FLIES = 14;
const PARK_WORDS = { warm: "warming", dice: "dice", drink: "drinking", read: "reading", polish: "polishing",
  feed: "feeding", sit: "sitting", hit: "training", lift: "lifting", spar: "sparring", stroll: "strolling",
  work: "working" };

function parkHash(i, salt) {
  let h = (i + 1) * 2654435761 + salt * 40503;
  h = (h ^ (h >>> 13)) * 1274126177;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function drawParkUnder(now) {
  const park = state.scene && state.scene.park;
  if (!park) return;
  const t = now / 1000;
  ctx.save();
  park.lamps.forEach(([x, y]) => {
    const k = 0.75;
    const g = ctx.createRadialGradient(x, y - 31, 0, x, y - 31, 16);
    g.addColorStop(0, `rgba(255,208,115,${0.32 * k})`);
    g.addColorStop(1, "rgba(255,208,115,0)");
    ctx.fillStyle = g;
    ctx.fillRect(x - 16, y - 47, 32, 32);
  });
  if (park.box) {
    const [x0, y0, w, h] = park.box;
    for (let i = 0; i < PARK_FLIES; i++) {
      const ph = parkHash(i, 3), a = Math.PI * 2 * (t / 4 + ph);
      const x = x0 + w * (0.2 + 0.6 * parkHash(i, 1)) + 9 * Math.sin(a + i);
      const y = y0 + 40 + (h - 40) * (0.2 + 0.6 * parkHash(i, 2)) - 14 + 5 * Math.sin(2 * a);
      ctx.fillStyle = "rgba(190,240,120,.45)";
      ctx.fillRect(Math.round(x) - 1, Math.round(y), 3, 1);
      ctx.fillRect(Math.round(x), Math.round(y) - 1, 1, 3);
      ctx.fillStyle = "#e6ffaa";
      ctx.fillRect(Math.round(x), Math.round(y), 1, 1);
    }
  }
  const busy = new Set([...state.walkers.values()].filter((w) => w.a.idle).map((w) => w.a.room));
  for (const p of park.props) {
    if (!busy.has(p.room)) continue;
    const near = [...state.walkers.values()].some((w) => {
      const at = place(w, now);
      return w.a.idle === p.act && Math.hypot(at[0] - p.at[0], at[1] - p.at[1]) < 40;
    });
    if (!near) continue;
    ctx.fillStyle = "rgba(255,208,115,0.16)";
    ctx.beginPath();
    ctx.ellipse(p.at[0], p.at[1], 15, 7, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function parkChip(text, sx, sy, fill, ink, taken) {
  const tw = ctx.measureText(text).width + 8;
  // A chip that would cover one already drawn moves down a line.
  while (taken && taken.some(([x, y, w]) => Math.abs(x - sx) < (w + tw) / 2 && Math.abs(y - sy) < 13)) sy += 14;
  if (taken) taken.push([sx, sy, tw]);
  ctx.fillStyle = fill;
  ctx.fillRect(Math.round(sx - tw / 2), Math.round(sy - 13), Math.round(tw), 13);
  ctx.fillStyle = ink;
  ctx.fillText(text, Math.round(sx), Math.round(sy - 1));
}

function drawParkLabels() {
  const park = state.scene && state.scene.park, v = state.view;
  if (!park || v.s < 0.85) return;
  const now = performance.now();
  ctx.font = `600 10px ${FACE()}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  const taken = [];
  for (const w of state.walkers.values()) {
    const word = PARK_WORDS[w.a.idle];
    if (!word) continue;
    const [x, y] = place(w, now);
    parkChip(word, v.x + x * v.s, v.y + y * v.s + 15, "rgba(12,8,18,.7)", "#c9b8e8", taken);
  }
  for (const tb of park.tables) {
    if (!tb.doing.length && !tb.todo.length && !tb.blocked) continue;
    const sx = v.x + tb.at[0] * v.s, sy = v.y + (tb.at[1] - 16) * v.s;
    const parts = [];
    if (tb.doing.length) parts.push(`${tb.doing.length} doing`);
    if (tb.todo.length) parts.push(`${tb.todo.length} todo`);
    if (tb.blocked) parts.push(`${tb.blocked} blocked`);
    parkChip(parts.join(" · "), sx, sy, tb.blocked ? "rgba(90,20,14,.85)" : "rgba(40,26,14,.85)", "#ffd27a");
    if (v.s < 2) continue;
    tb.doing.concat(tb.todo).slice(0, 3).forEach((title, i) => {
      parkChip(title, sx, sy - 14 * (i + 1), "rgba(12,8,18,.7)", i < tb.doing.length ? "#f2a33a" : "#e9dcbc");
    });
  }
}
