// HIERARCHY.1 / SUMMON.1, read-only: each session room's tier chip (crown for the throne, banner for a topic room)
// with its model and effort, a legend of the four tiers, and while no main orchestrator is open a note to summon
// it on the PC. The phone never starts a CLI here: no buttons, no writes.
"use strict";

function tierGlyph(rows, color, x, y, k) {
  ctx.fillStyle = "#08060c";
  rows.forEach((row, dy) => { for (let dx = 0; dx < row.length; dx++) if (row[dx] === "1") ctx.fillRect(x + dx * k, y + (dy + 1) * k, k, k); });
  ctx.fillStyle = color;
  rows.forEach((row, dy) => { for (let dx = 0; dx < row.length; dx++) if (row[dx] === "1") ctx.fillRect(x + dx * k, y + dy * k, k, k); });
}

function tierChip(t, x, y, px) {
  const text = t.label, k = Math.max(1, Math.round(px / 6));
  const tw = ctx.measureText(text).width, w = tw + 7 * k + px * 1.4, h = px * 1.5;
  const left = Math.round(x - w / 2), top = Math.round(y - h / 2);
  ctx.fillStyle = "rgba(18,13,31,.94)";
  ctx.fillRect(left, top, Math.round(w), Math.round(h));
  ctx.strokeStyle = t.color;
  ctx.lineWidth = 2;
  ctx.strokeRect(left + 1, top + 1, Math.round(w) - 2, Math.round(h) - 2);
  tierGlyph(t.rows, t.color, left + px * 0.5, Math.round(y - 2.5 * k), k);
  ctx.fillStyle = t.color;
  ctx.textAlign = "left";
  ctx.fillText(text, left + px * 0.9 + 7 * k, Math.round(y) + 1);
  ctx.textAlign = "center";
}

function drawTiers() {
  const s = state.scene, h = s && s.hierarchy;
  if (!h) return;
  const by = {};
  for (const t of h.tiers) by[t.tier] = t;
  const v = state.view, px = parseFloat(getComputedStyle(document.body).fontSize) * 0.7;
  ctx.font = `600 ${px}px ${FACE()}`;
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  for (const r of s.rooms) {
    const t = r.kind === "main" ? by.main : r.kind === "simple" ? by.topic : null;
    if (!t || v.s < SIGN_S) continue;
    const cx = r.poly.reduce((a, p) => a + p[0], 0) / 4, cy = r.poly.reduce((a, p) => a + p[1], 0) / 4;
    const y = v.y + (cy + (r.poly[2][1] - cy) * 0.5) * v.s;
    tierChip(t, v.x + cx * v.s, y + px * (r.sign ? 3.75 : 1.9), px);
  }
  const { w, h: ch } = size();
  const widest = 6 + Math.max(...h.tiers.map((t) => ctx.measureText(t.name + "  " + t.label).width + px * 2.6));
  const tools = document.querySelector("#mapTools:not([hidden]) .mt-row"), c = canvas.getBoundingClientRect();
  const r = tools && tools.getBoundingClientRect();
  const lift = r && r.width && widest > r.left - c.left;  // a phone: the legend sits just over the Rooms row
  let y = (lift ? r.top - c.top - 6 + px * 0.6 : ch - px) - px * 1.2 * h.tiers.length;
  ctx.textAlign = "left";
  state.tierLegend = [];
  for (const t of h.tiers) {
    const lw = Math.round(ctx.measureText(t.name + "  " + t.label).width + px * 2.6);
    state.tierLegend.push({ left: 6, top: Math.round(y - px * 0.6), right: 6 + lw, bottom: Math.round(y - px * 0.6) + Math.round(px * 1.2) });
    ctx.fillStyle = "rgba(12,8,18,.72)";
    ctx.fillRect(6, Math.round(y - px * 0.6), lw, Math.round(px * 1.2));
    tierGlyph(t.rows, t.color, 10, Math.round(y - px * 0.4), Math.max(1, Math.round(px / 9)));
    ctx.fillStyle = "#e9dcbc";
    ctx.fillText(t.name, 14 + px * 1.2, Math.round(y) + 1);
    ctx.fillStyle = t.color;
    ctx.fillText(t.label, 14 + px * 1.2 + ctx.measureText(t.name + "  ").width, Math.round(y) + 1);
    y += px * 1.2;
  }
  ctx.textAlign = "center";
  if (!h.main) {
    const text = "No orchestrator: summon it on the PC", tw = ctx.measureText(text).width + px * 3.2, bh = px * 2;
    const left = Math.round(w / 2 - tw / 2), top = Math.round(px * 3.2);
    ctx.fillStyle = "rgba(42,15,28,.94)";
    ctx.fillRect(left, top, Math.round(tw), Math.round(bh));
    ctx.strokeStyle = "#7a1f3d";
    ctx.lineWidth = 2;
    ctx.strokeRect(left + 1, top + 1, Math.round(tw) - 2, Math.round(bh) - 2);
    tierGlyph(by.main.rows, "#8a7a50", left + px * 0.6, Math.round(top + bh / 2 - px * 0.35), Math.max(1, Math.round(px / 7)));
    ctx.fillStyle = "#ffcf4a";
    ctx.fillText(text, Math.round(w / 2 + px * 0.8), Math.round(top + bh / 2) + 1);
  }
}
