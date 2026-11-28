// MESSENGER: news from another task's decision, read-only over SSE. The courier walks the map as a roster row
// (sprite "courier"); when it arrives a wax seal flashes over the room, the room's card glows steadily and the
// task card carries a "NEW FROM <room>" ribbon. A tap on the ribbon shows the decision and why it is news here.
"use strict";

const COURIER_FLASH = 900;
state.courier = { seen: null, flashes: [] };

function courierMark(node, c) {
  if (!c.courier) return;
  node.classList.add("courier-lit");
  const n = c.courier, rib = el("button", "courier-ribbon", "✉ NEW FROM " + n.from.toUpperCase());
  rib.type = "button";
  const slip = el("div", "courier-slip");
  slip.hidden = true;
  slip.append(el("b", "", n.title), el("span", "", n.question || "A decision"),
    el("span", "", "Daniel: " + (n.answer || "answered")), el("small", "", "Why here: " + n.reason));
  rib.addEventListener("click", (e) => { e.stopPropagation(); slip.hidden = !slip.hidden; });
  node.prepend(rib);
  rib.after(slip);
}

function courierSeen(now) {
  const list = (state.scene && state.scene.couriers) || [];
  const keys = new Set(list.map((c) => c.key));
  if (state.courier.seen) {
    for (const c of list) if (!state.courier.seen.has(c.key)) state.courier.flashes.push({ room: c.room, t0: now });
  }
  state.courier.seen = keys;
}

// halfway between the room's top corner and its middle, inside its own floor
function courierSpot(r) {
  const xs = r.poly.map((p) => p[0]), ys = r.poly.map((p) => p[1]);
  const cx = xs.reduce((a, b) => a + b, 0) / xs.length, cy = ys.reduce((a, b) => a + b, 0) / ys.length;
  const top = Math.min(...ys);
  return [cx, top + (cy - top) * 0.35];
}

function drawCourierOver(now) {
  if (!state.scene || !state.scene.rooms) return;
  courierSeen(now);
  const rooms = new Map(state.scene.rooms.map((r) => [r.name, r]));
  const pulse = 0.5;
  const shown = new Set();
  for (const c of state.scene.couriers || []) {
    const r = rooms.get(c.room);
    if (!r || shown.has(c.room)) continue;
    shown.add(c.room);
    const [x, y] = courierSpot(r), k = Math.max(1, 1.2 / state.view.s);
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(k, k);
    courierCard(pulse);
    ctx.restore();
  }
  courierFlashes(now, rooms);
}

// the lit card at the origin: a steady warm glow, parchment with a wax seal (the ribbon is on the list card)
function courierCard(pulse) {
  const glow = ctx.createRadialGradient(0, 0, 2, 0, 0, 26);
  glow.addColorStop(0, `rgba(255,206,110,${0.55 + 0.35 * pulse})`);
  glow.addColorStop(1, "rgba(255,206,110,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(-28, -28, 56, 56);
  ctx.fillStyle = "#ecdeb8";
  ctx.fillRect(-8, -10, 16, 20);
  ctx.fillStyle = "#b8a074";
  for (const ly of [-6, -3, 0]) ctx.fillRect(-5, ly, 10, 1);
  ctx.fillStyle = "#c4282e";
  ctx.fillRect(1, 3, 5, 5);
  ctx.strokeStyle = `rgba(255,206,110,${0.6 + 0.4 * pulse})`;
  ctx.lineWidth = 1;
  ctx.strokeRect(-8.5, -10.5, 17, 21);
}

function courierFlashes(now, rooms) {
  state.courier.flashes = state.courier.flashes.filter((f) => now - f.t0 < COURIER_FLASH);
  for (const f of state.courier.flashes) {
    const r = rooms.get(f.room);
    if (!r) continue;
    const t = (now - f.t0) / COURIER_FLASH, [x, y] = courierSpot(r);
    ctx.strokeStyle = `rgba(255,206,110,${1 - t})`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.ellipse(x, y, 6 + 18 * t, (6 + 18 * t) * 0.8, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = `rgba(196,40,46,${1 - t * 0.6})`;
    ctx.beginPath();
    ctx.arc(x, y, 5 * (1 + 0.5 * Math.sin(Math.min(1, t * 2.5) * Math.PI)), 0, Math.PI * 2);
    ctx.fill();
  }
}
