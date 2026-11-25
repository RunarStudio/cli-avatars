// BODY: the Dungeon's body language on the phone map, read-only over SSE. Flowing avatars stride (lean, bob, heel
// dust), stuck ones slump on a bench, one waiting on you taps its foot by the door, and a room whose run is long
// smokes from its brazier or chimney, thicker with time. Pose changes ease in over 0.4 s.
"use strict";

const BODY_EASE = 400;
const BODY_PUFFS = 18;
state.body = { poses: new Map(), smoke: new Map(), last: 0 };

function bodyBlend(a, now) {
  const have = state.body.poses.get(a.id);
  if (!have || have.pose !== a.pose) {
    const was = have ? have.pose : a.pose;
    state.body.poses.set(a.id, { pose: a.pose, was, t0: have ? now : now - BODY_EASE });
  }
  const p = state.body.poses.get(a.id);
  const t = Math.min(1, (now - p.t0) / BODY_EASE);
  return { pose: p.pose, was: p.was, k: 1 - Math.pow(1 - t, 3) };
}

function bodyAmount(b, pose) {
  return (b.pose === pose ? b.k : 0) + (b.was === pose && b.pose !== pose ? 1 - b.k : 0);
}

// a plank bench behind a slumped avatar, along the back wall (the map's u axis)
function bodyBench(x, y, alpha) {
  const g = (du, dv, z) => [x + (du - dv) * 16, y + (du + dv) * 8 - z];
  const quad = (pts, fill) => {
    ctx.beginPath();
    pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
  };
  ctx.save();
  ctx.globalAlpha = alpha;
  const v0 = -0.72, v1 = -0.3, z = 8;
  ctx.fillStyle = "#46301a";
  for (const [du, dv] of [[-0.9, v0 + 0.06], [0.9, v0 + 0.06], [-0.9, v1 - 0.08], [0.9, v1 - 0.08]]) {
    const [lx, ly] = g(du, dv, 0);
    ctx.fillRect(Math.round(lx) - 1, Math.round(ly) - z, 2, z);
  }
  quad([g(-1, v0, z + 7), g(1, v0, z + 7), g(1, v0, z + 3), g(-1, v0, z + 3)], "#46301a");
  quad([g(-1, v0, z), g(1, v0, z), g(1, v1, z), g(-1, v1, z)], "#8a5a34");
  quad([g(-1, v1, z), g(1, v1, z), g(1, v1, z - 1.5), g(-1, v1, z - 1.5)], "#b0804c");
  ctx.restore();
}

function drawBodyUnder(now) {
  for (const w of state.walkers.values()) {
    if (w.a.pose !== "slump") continue;
    const at = place(w, now), b = bodyBlend(w.a, now);
    bodyBench(at[0], at[1], Math.max(0.25, b.k));
  }
}

// the sprite in its pose; called inside drawAvatars' feet-centred, facing-flipped frame
function drawPosed(a, sheet, meta, f, walking, top, now) {
  const b = bodyBlend(a, now);
  const stride = bodyAmount(b, "stride"), slump = bodyAmount(b, "slump"), tap = bodyAmount(b, "tap");
  if (stride + slump + tap < 0.01) return false;
  const feet = top + meta.h * (1 - meta.feet);
  const beat = Math.floor(now / 160) % 2;
  ctx.save();
  ctx.translate(0, feet);
  ctx.transform(1, 0, -0.09 * stride + 0.05 * tap - 0.07 * slump, 1 - 0.24 * slump, 0, 0);
  if (stride > 0.5 && Math.floor(now / 110) % 2) ctx.translate(0, -1);
  if (tap > 0.5 && beat) ctx.translate(0, -1);
  if (slump > 0.01) ctx.filter = `saturate(${1 - 0.45 * slump}) brightness(${1 - 0.2 * slump})`;
  ctx.drawImage(sheet, f * meta.w, walking ? meta.h : 0, meta.w, meta.h, -Math.round(meta.w / 2), top - feet, meta.w, meta.h);
  ctx.restore();
  ctx.save();
  ctx.translate(0, feet);
  if (stride > 0.3) {
    for (let i = 0; i < 3; i++) {
      ctx.fillStyle = `rgba(170,150,120,${(0.5 * stride) / (i + 1)})`;
      ctx.fillRect(-meta.w * 0.28 - i * 3 - (Math.floor(now / 110) % 2), -1 - (i % 2), 2, 2);
    }
  }
  if (tap > 0.5 && !beat) {
    ctx.fillStyle = "rgba(255,214,140,.8)";
    ctx.fillRect(meta.w * 0.3, -2, 2, 1);
    ctx.fillRect(meta.w * 0.3 + 2, -4, 1, 1);
  }
  if (slump > 0.6) {
    const s = (now / 260) % 8;
    if (s < 5) {
      ctx.fillStyle = `rgba(206,196,224,${0.7 * (1 - s / 5)})`;
      ctx.beginPath();
      ctx.arc(meta.w * 0.22, -meta.h * 0.62 - s * 2, 1.6 + s * 0.3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
  return true;
}

function bodySmokeLevels(now) {
  const want = new Map();
  for (const w of state.walkers.values()) {
    if (w.a.smoke > 0 && w.a.room) want.set(w.a.room, Math.max(want.get(w.a.room) || 0, w.a.smoke));
  }
  const dt = Math.min(0.5, Math.max(0, (now - (state.body.last || now)) / 1000));
  state.body.last = now;
  for (const room of state.scene.rooms) {
    const goal = want.get(room.name) || 0, have = state.body.smoke.get(room.name) || 0;
    const next = have + (goal - have) * Math.min(1, dt * 3.75);
    if (next < 0.02 && goal === 0) state.body.smoke.delete(room.name);
    else state.body.smoke.set(room.name, next);
  }
}

function bodyChimney(x, y, level) {
  ctx.fillStyle = "#5c5270";
  ctx.fillRect(x - 6, y + 4, 12, 16);
  ctx.fillStyle = "#807496";
  ctx.fillRect(x - 6, y + 4, 2, 16);
  ctx.fillRect(x - 8, y + 1, 16, 3);
  ctx.fillStyle = `rgba(255,150,60,${0.35 + 0.5 * level})`;
  ctx.fillRect(x - 3, y, 6, 1);
}

function drawBodyOver(now) {
  bodySmokeLevels(now);
  for (const room of state.scene.rooms) {
    const level = state.body.smoke.get(room.name);
    if (!level || !room.smoke) continue;
    const [x, y] = room.smoke.at;
    if (room.smoke.chimney) bodyChimney(x, y + 18, level);
    const rise = 120 * (0.55 + 0.45 * level), count = Math.max(3, Math.round(BODY_PUFFS * (0.35 + 0.65 * level)));
    for (let i = 0; i < count; i++) {
      const life = ((now / 4000) + i / count) % 1;
      const px = x + Math.sin(life * 5 + i * 1.7) * (2 + 7 * life);
      const py = y - life * rise;
      const r = 2.4 + life * (4 + 6 * level);
      const alpha = (0.35 + 0.5 * level) * Math.min(1, life * 6) * Math.pow(1 - life, 1.3);
      const grad = ctx.createRadialGradient(px - r * 0.3, py - r * 0.35, 0, px, py, r);
      grad.addColorStop(0, `rgba(236,230,246,${alpha})`);
      grad.addColorStop(1, "rgba(206,196,224,0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
