// TIMELAPSE: scrub a day over the map and watch the avatars walk between rooms, read-only. The sand-glass opens it;
// the sundial strip scrubs (a soft tick), play runs at x1/x4/x16, ◀ ▶ go through the 30 kept days. A gem or a ghost
// opens that chat at the message nearest the moment (a chime). Sounds wait while a task is in focus. SSE
// "timelapse" reloads only today. Every text goes in with textContent.
"use strict";

const LAPSE_SPEEDS = [["x1", 4], ["x4", 16], ["x16", 64]];
const LAPSE_TRAIL = 90;
const LAPSE_GLOW = { user: "#ffd27a", orchestrator: "#b48cff", grok: "#7fe0c0" };
const LAPSE_SKY = [[0, [14, 16, 44]], [300, [22, 22, 62]], [360, [150, 80, 120]], [420, [236, 160, 110]],
  [540, [150, 186, 222]], [1020, [156, 182, 214]], [1110, [238, 140, 70]], [1170, [128, 60, 112]], [1260, [24, 20, 58]],
  [1440, [14, 16, 44]]];
const LAPSE_LIGHT = [[0, 0.34], [330, 0.38], [420, 0.74], [540, 1], [1020, 1], [1140, 0.7], [1260, 0.38], [1440, 0.34]];
const LAPSE_CAST = [[0, [0.5, 0.6, 1]], [330, [0.55, 0.6, 1]], [390, [1, 0.7, 0.74]], [450, [1, 0.88, 0.76]],
  [540, [1, 0.98, 0.93]], [1020, [1, 0.96, 0.88]], [1110, [1, 0.7, 0.46]], [1190, [0.78, 0.56, 0.86]],
  [1260, [0.5, 0.6, 1]], [1440, [0.5, 0.6, 1]]];

state.lapse = { on: false, day: null, data: null, minute: 0, playing: false, speed: 1, last: 0, ticked: 0,
  tint: null, tintKey: "", drag: false };

function lapseLerp(keys, m) {
  m = Math.min(1440, Math.max(0, m));
  for (let i = 1; i < keys.length; i++) {
    const [m0, a] = keys[i - 1], [m1, b] = keys[i];
    if (m > m1) continue;
    const t = (m - m0) / Math.max(1e-6, m1 - m0);
    return Array.isArray(a) ? a.map((v, k) => v + (b[k] - v) * t) : a + (b - a) * t;
  }
  return keys[keys.length - 1][1];
}

function lapseClock(m) {
  const h = Math.floor(m / 60) % 24, mm = Math.floor(m % 60);
  return String(h).padStart(2, "0") + ":" + String(mm).padStart(2, "0");
}

function lapseQuiet() { return Boolean(state.focus && state.focus.task); }

function lapseEnd() {
  const d = state.lapse.data;
  if (!d || d.day !== d.today) return 1439;
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

async function loadLapse(keep) {
  const L = state.lapse;
  let data;
  try { data = await getJSON("/api/timelapse" + (L.day ? "?day=" + L.day : "")); } catch (_e) { return; }
  L.data = data;
  for (const key of Object.keys(data.sprites)) {
    if (!state.sprites[key]) state.sprites[key] = await loadImage("/api/sprite/" + key + ".png");
  }
  if (!keep) L.minute = data.day === data.today ? lapseEnd() : (data.busy.length ? data.busy[0] : 0);
  paintLapse();
}

function lapseEvent() {
  const L = state.lapse;
  if (L.on && L.data && L.data.day === L.data.today) loadLapse(true);
}

function lapseStart() {
  const L = state.lapse;
  L.on = true;
  L.day = null;
  L.playing = false;
  $("lapse").hidden = false;
  $("lapseBtn").setAttribute("aria-pressed", "true");
  if (!lapseQuiet()) tone("tick");
  if (!state.room && state.scene && state.scene.map) {
    const m = state.scene.map, { w, h } = size(), free = h - $("lapse").offsetHeight - 6;
    const s = Math.min(w * 0.96 / m.w, free * 0.96 / m.h, 6);
    animateTo({ s, x: w / 2 - m.w / 2 * s, y: free / 2 - m.h / 2 * s });
  }
  loadLapse(false);
}

function lapseLeave() {
  const L = state.lapse;
  L.on = false;
  L.playing = false;
  $("lapse").hidden = true;
  $("lapseBtn").setAttribute("aria-pressed", "false");
  if (!state.room) animateTo(wholeMap());
  if (state.chatAt && state.chatKey) { state.chatAt = null; showChat(state.chatKey, $("chatRoom").textContent); }
}

function lapseGo(delta) {
  const d = state.lapse.data;
  if (!d) return;
  const next = new Date(d.day + "T12:00:00");
  next.setDate(next.getDate() + delta);
  const day = next.getFullYear() + "-" + String(next.getMonth() + 1).padStart(2, "0") + "-" + String(next.getDate()).padStart(2, "0");
  if (day < d.first || day > d.today) return;
  state.lapse.day = day === d.today ? null : day;
  state.lapse.playing = false;
  loadLapse(false);
}

function lapseSeek(m, tick) {
  const L = state.lapse;
  L.minute = Math.min(lapseEnd(), Math.max(0, m));
  const t = performance.now();
  if (tick && t - L.ticked > 90 && !lapseQuiet()) { L.ticked = t; tone("tick"); }
  paintLapse();
}

function lapseMoment(m) {
  const card = state.cards.find((c) => c.id === m.card);
  showChat(m.chat, (card ? card.title : m.who) + " · " + lapseClock(m.minute), m.ts);
  if (!lapseQuiet()) tone("moment");
}

function lapseNearest(list, ts) {
  let best = null;
  for (const m of list) if (!best || Math.abs(m.ts - ts) < Math.abs(best.ts - ts)) best = m;
  return best;
}

// --- where a ghost is: the step it stands on, or along the route it walks into the next one ------------------
function lapseRouteAt(route, t) {
  let total = 0;
  for (let i = 1; i < route.length; i++) total += Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]);
  let left = Math.min(1, Math.max(0, t)) * total;
  for (let i = 1; i < route.length; i++) {
    const [x0, y0] = route[i - 1], [x1, y1] = route[i], seg = Math.hypot(x1 - x0, y1 - y0);
    if (left <= seg && seg > 0) return [[x0 + (x1 - x0) * left / seg, y0 + (y1 - y0) * left / seg], x1 < x0 ? -1 : 1];
    left -= seg;
  }
  return [route[route.length - 1], 1];
}

function lapseWhere(steps, m) {
  let i = -1;
  while (i + 1 < steps.length && steps[i + 1].m <= m) i++;
  if (i < 0) return null;
  const next = steps[i + 1];
  if (next && next.route && next.span > 0 && m >= next.m - next.span) {
    const [at, face] = lapseRouteAt(next.route, (m - (next.m - next.span)) / next.span);
    return { at, face, walk: true };
  }
  return { at: steps[i].at, face: 1, walk: false };
}

// --- drawing on the map: the map tinted to the hour, trails, ghosts ------------------------------------------
function lapseTint(m) {
  const L = state.lapse, key = state.mapKey + "|" + Math.round(m / 15);
  if (L.tintKey === key && L.tint) return L.tint;
  const c = L.tint || document.createElement("canvas"), g = c.getContext("2d");
  c.width = state.map.width;
  c.height = state.map.height;
  const light = lapseLerp(LAPSE_LIGHT, m), cast = lapseLerp(LAPSE_CAST, m);
  g.globalCompositeOperation = "source-over";
  g.drawImage(state.map, 0, 0);
  g.globalCompositeOperation = "multiply";
  g.fillStyle = "rgb(" + cast.map((v) => Math.round(255 * Math.min(1, v * light))).join(",") + ")";
  g.fillRect(0, 0, c.width, c.height);
  g.globalCompositeOperation = "destination-in";
  g.drawImage(state.map, 0, 0);
  L.tint = c;
  L.tintKey = key;
  return c;
}

function drawLapse(now) {
  const L = state.lapse, d = L.data;
  if (!L.on) return false;
  if (L.playing) {
    const dt = Math.min(250, now - (L.last || now)) / 1000;
    L.minute += dt * LAPSE_SPEEDS[L.speed][1];
    if (L.minute >= lapseEnd()) { L.minute = lapseEnd(); L.playing = false; }
    paintLapse();
  }
  L.last = now;
  ctx.shadowBlur = 0;
  ctx.drawImage(lapseTint(L.minute), 0, 0);
  if (!d || !d.map) return true;
  const shown = [];
  for (const a of d.avatars) {
    const steps = d.tracks[a.id], at = lapseWhere(steps, L.minute);
    if (!at) continue;
    lapseTrail(steps, a.kind, now);
    shown.push({ a, ...at });
  }
  shown.sort((p, q) => p.at[1] - q.at[1]);
  for (const g of shown) lapseGhost(g, now);
  return true;
}

function lapseTrail(steps, kind, now) {
  const m = state.lapse.minute;
  ctx.fillStyle = LAPSE_GLOW[kind] || "#e9dcbc";
  for (const s of steps) {
    if (!s.route || s.m - s.span > m || s.m < m - LAPSE_TRAIL) continue;
    const done = Math.min(1, (m - (s.m - s.span)) / Math.max(1, s.span)), fade = 1 - (m - s.m) / LAPSE_TRAIL;
    for (let k = 0; k <= 10; k++) {
      const t = k / 10;
      if (t > done) break;
      const [[x, y]] = lapseRouteAt(s.route, t), r = 1.4 + 1.6 * t;
      ctx.globalAlpha = Math.max(0, Math.min(1, fade)) * (0.25 + 0.55 * t) * (0.8 + 0.2 * Math.sin(now / 240 + k));
      ctx.beginPath();
      ctx.moveTo(x, y - r);
      ctx.lineTo(x + r, y);
      ctx.lineTo(x, y + r);
      ctx.lineTo(x - r, y);
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
}

function lapseGhost(g, now) {
  const a = g.a, [x, y] = g.at, glow = LAPSE_GLOW[a.kind] || "#e9dcbc";
  const halo = ctx.createRadialGradient(x, y, 1, x, y, 16);
  halo.addColorStop(0, glow + "aa");
  halo.addColorStop(1, glow + "00");
  ctx.fillStyle = halo;
  ctx.beginPath();
  ctx.ellipse(x, y, 16, 6, 0, 0, Math.PI * 2);
  ctx.fill();
  const sheet = state.sprites[a.sprite], meta = state.lapse.data.sprites[a.sprite];
  if (sheet && meta) {
    const f = Math.floor((now + hashNum(a.id) * 37) / (g.walk ? 110 : 190)) % meta.frames;
    const top = Math.round(y - meta.h * (1 - meta.feet));
    ctx.save();
    ctx.globalAlpha = 0.92;
    ctx.translate(Math.round(x), 0);
    if (g.face < 0) ctx.scale(-1, 1);
    ctx.drawImage(sheet, f * meta.w, g.walk ? meta.h : 0, meta.w, meta.h, -Math.round(meta.w / 2), top, meta.w, meta.h);
    ctx.restore();
  }
  const h = meta ? meta.h * (1 - meta.feet) : 30;
  ctx.font = `600 8px ${FACE()}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  const tw = ctx.measureText(a.name).width + 6;
  ctx.fillStyle = "rgba(12,8,18,.78)";
  ctx.fillRect(Math.round(x - tw / 2), Math.round(y - h - 11), Math.round(tw), 10);
  ctx.fillStyle = glow;
  ctx.fillRect(Math.round(x - tw / 2), Math.round(y - h - 2), Math.round(tw), 1);
  ctx.fillText(a.name, Math.round(x), Math.round(y - h - 2));
}

// a tap on a ghost opens its chat at the playhead; false lets the map take the tap
function lapseTap(x, y) {
  const L = state.lapse, d = L.data;
  if (!L.on || !d || !d.map) return false;
  let hit = null;
  for (const a of d.avatars) {
    const at = lapseWhere(d.tracks[a.id], L.minute);
    if (at && Math.abs(at.at[0] - x) < 14 && at.at[1] - y > -6 && at.at[1] - y < 44) hit = a;
  }
  if (!hit) return false;
  const ts = d.start + L.minute * 60, own = d.moments.filter((m) => m.aid === hit.id);
  const m = lapseNearest(own.length ? own : d.moments, ts);
  if (m) lapseMoment(m);
  return true;
}

// --- the sundial strip ---------------------------------------------------------------------------------------
const LAPSE_PAD = 14;
function lapseX(m, w) { return LAPSE_PAD + (w - 2 * LAPSE_PAD) * m / 1440; }
function lapseMinute(x, w) { return Math.round(1440 * (x - LAPSE_PAD) / (w - 2 * LAPSE_PAD)); }

function paintLapse() {
  const L = state.lapse, d = L.data, c = $("lapseTrack");
  if (!d || $("lapse").hidden) return;
  $("lapseDay").textContent = d.label;
  $("lapsePrev").disabled = d.day <= d.first;
  $("lapseNext").disabled = d.day >= d.today;
  $("lapseClock").textContent = lapseClock(L.minute);
  $("lapsePlay").textContent = L.playing ? "❚❚" : "▶";
  $("lapsePlay").setAttribute("aria-label", L.playing ? "Pause" : "Play");
  $("lapseSpeed").textContent = LAPSE_SPEEDS[L.speed][0];
  const near = lapseNearest(d.moments, d.start + L.minute * 60);
  $("lapseNow").textContent = !d.avatars.length ? "Nothing logged this day."
    : near && Math.abs(near.minute - L.minute) <= 20 ? near.who + " in " + lapseRoom(near.room) + " · tap a gem to open the chat"
    : d.avatars.length + (d.avatars.length === 1 ? " avatar" : " avatars") + " · " + d.moments.length + " chat moments";
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
  if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const band = g.createLinearGradient(lapseX(0, w), 0, lapseX(1440, w), 0);
  for (let m = 0; m <= 1440; m += 60) band.addColorStop(m / 1440, "rgb(" + lapseLerp(LAPSE_SKY, m).map(Math.round).join(",") + ")");
  g.fillStyle = "#120d19";
  g.fillRect(0, 0, w, h);
  g.fillStyle = band;
  g.fillRect(lapseX(0, w), 6, lapseX(1440, w) - lapseX(0, w), 16);
  g.fillStyle = "#fff6d8";
  for (let i = 0; i < 26; i++) {
    const m = (i * 97) % 1440;
    if (lapseLerp(LAPSE_LIGHT, m) < 0.5) g.fillRect(Math.round(lapseX(m, w)), 8 + (i * 7) % 11, 1, 1);
  }
  const sx = lapseX(720, w);
  g.fillStyle = "#fff2b0";
  g.beginPath();
  g.arc(sx, 14, 4, 0, Math.PI * 2);
  g.fill();
  g.font = `9px ${FACE()}`;
  g.textAlign = "center";
  g.textBaseline = "top";
  for (let hr = 0; hr <= 24; hr++) {
    const x = Math.round(lapseX(hr * 60, w));
    g.fillStyle = hr % 6 ? "#5a4e66" : "#9d8fae";
    g.fillRect(x, 22, 1, hr % 6 ? 3 : 5);
    if (hr % 6 === 0 && hr < 24) g.fillText(String(hr).padStart(2, "0"), x + (hr ? 0 : 6), 28);
  }
  g.fillStyle = "#f2a33a";
  for (const m of d.busy) g.fillRect(Math.round(lapseX(m, w)), 4, 1, 2);
  for (const m of d.moments) {
    const x = Math.round(lapseX(m.minute, w));
    g.fillStyle = "#3a0f1e";
    g.fillRect(x - 3, 12, 7, 5);
    g.fillStyle = Math.abs(m.minute - L.minute) <= 20 ? "#ff6a8a" : "#c0305a";
    g.beginPath();
    g.moveTo(x, 10); g.lineTo(x + 3, 14); g.lineTo(x, 18); g.lineTo(x - 3, 14);
    g.fill();
  }
  if (d.day === d.today) {
    const nx = lapseX(lapseEnd(), w);
    g.fillStyle = "rgba(7,5,11,.62)";
    g.fillRect(nx, 6, lapseX(1440, w) - nx, 16);
    g.fillStyle = "#e0475e";
    g.fillRect(Math.round(nx), 4, 1, 20);
  }
  lapseGlass(g, lapseX(L.minute, w));
}

function lapseGlass(g, x) {
  x = Math.round(x);
  g.fillStyle = "#ffd27a";
  g.fillRect(x - 5, 2, 11, 2);
  g.fillRect(x - 5, 24, 11, 2);
  g.fillStyle = "rgba(233,220,188,.85)";
  g.beginPath();
  g.moveTo(x - 4, 4); g.lineTo(x + 4, 4); g.lineTo(x + 1, 14); g.lineTo(x + 4, 24); g.lineTo(x - 4, 24); g.lineTo(x - 1, 14);
  g.fill();
  const sand = Math.min(1, state.lapse.minute / 1440);
  g.fillStyle = "#f2a33a";
  g.beginPath();
  g.moveTo(x - 3 + 2 * sand, 5 + 8 * sand); g.lineTo(x + 3 - 2 * sand, 5 + 8 * sand); g.lineTo(x, 13);
  g.fill();
  g.fillRect(x - 3, 23 - Math.round(8 * sand), 7, Math.round(8 * sand));
  g.fillRect(x, 13, 1, 10);
}

function lapseRoom(name) {
  const room = state.scene && state.scene.rooms.find((r) => r.name === name);
  return room ? room.title : name;
}

function lapseGem(x, w) {
  const d = state.lapse.data;
  let best = null, gap = 9;
  for (const m of d.moments) {
    const off = Math.abs(lapseX(m.minute, w) - x);
    if (off < gap) { gap = off; best = m; }
  }
  return best;
}

const lapseTrack = $("lapseTrack");
lapseTrack.addEventListener("pointerdown", (e) => {
  const d = state.lapse.data;
  if (!d) return;
  const box = lapseTrack.getBoundingClientRect(), x = e.clientX - box.left, y = e.clientY - box.top;
  const gem = y >= 6 && y <= 22 ? lapseGem(x, box.width) : null;
  if (gem) { lapseSeek(gem.minute, false); lapseMoment(gem); return; }
  state.lapse.drag = true;
  state.lapse.playing = false;
  lapseTrack.setPointerCapture(e.pointerId);
  lapseSeek(lapseMinute(x, box.width), true);
});
lapseTrack.addEventListener("pointermove", (e) => {
  if (!state.lapse.drag) return;
  const box = lapseTrack.getBoundingClientRect();
  lapseSeek(lapseMinute(e.clientX - box.left, box.width), true);
});
for (const kind of ["pointerup", "pointercancel"]) lapseTrack.addEventListener(kind, () => { state.lapse.drag = false; });
$("lapseBtn").addEventListener("click", () => (state.lapse.on ? lapseLeave() : lapseStart()));
$("lapseLeave").addEventListener("click", lapseLeave);
$("lapsePrev").addEventListener("click", () => lapseGo(-1));
$("lapseNext").addEventListener("click", () => lapseGo(1));
$("lapsePlay").addEventListener("click", () => {
  const L = state.lapse;
  if (!L.playing && L.minute >= lapseEnd()) L.minute = L.data && L.data.busy.length ? L.data.busy[0] : 0;
  L.playing = !L.playing;
  L.last = performance.now();
  paintLapse();
});
$("lapseSpeed").addEventListener("click", () => { state.lapse.speed = (state.lapse.speed + 1) % LAPSE_SPEEDS.length; paintLapse(); });
document.addEventListener("keydown", (e) => {
  if (!state.lapse.on || e.target.closest("input, textarea, select") || document.querySelector(".sheet:not([hidden])")) return;
  if (e.key === "Escape") lapseLeave();
  else if (e.key === "ArrowLeft") lapseGo(-1);
  else if (e.key === "ArrowRight") lapseGo(1);
  else if (e.key === " ") { e.preventDefault(); $("lapsePlay").click(); }
});
window.addEventListener("resize", paintLapse);
