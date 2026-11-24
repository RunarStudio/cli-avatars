// PHONE.1: the Dungeon map, its tasks and the room chat. Read-only; every text goes in with textContent.
"use strict";

const $ = (id) => document.getElementById(id);
const canvas = $("map");
const ctx = canvas.getContext("2d");
const LABELS = { todo: "TODO", doing: "DOING", review: "REVIEW", done: "DONE", blocked: "BLOCKED" };
const state = { scene: null, cards: [], sel: null, room: null, map: null, mapKey: "", sprites: {},
  view: { x: 0, y: 0, s: 1 }, anim: null, fitted: false, chatKey: "", glow: 0 };

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

async function getJSON(url) {
  const res = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (res.status === 401) { location.reload(); throw new Error("unpaired"); }
  if (!res.ok) throw new Error(url + " " + res.status);
  return res.json();
}

function loadImage(src) {
  return new Promise((ok, fail) => { const img = new Image(); img.onload = () => ok(img); img.onerror = fail; img.src = src; });
}

// --- view: fit, zoom to a room, pan and pinch ---------------------------------------------------
function size() {
  const r = canvas.getBoundingClientRect();
  return { w: r.width, h: r.height };
}

function fitView(box, fill) {
  const { w, h } = size();
  const s = Math.min(w * fill / box[2], h * fill / box[3], 6);
  return { s, x: w / 2 - (box[0] + box[2] / 2) * s, y: h / 2 - (box[1] + box[3] / 2) * s };
}

function wholeMap() {
  const m = state.scene && state.scene.map;
  return m ? fitView([0, 0, m.w, m.h], 0.96) : state.view;
}

function animateTo(target, ms) {
  state.anim = { from: { ...state.view }, to: target, t0: performance.now(), ms: ms || 650 };
}

function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

function zoomToRoom(name, quiet) {
  const room = state.scene && state.scene.rooms.find((r) => r.name === name);
  if (!room) return;
  state.room = name;
  state.glow = performance.now();
  animateTo(fitView(room.box, 0.82));
  $("here").textContent = room.title;
  if (!quiet) chime();
}

const pointers = new Map();
let gesture = null;

canvas.addEventListener("pointerdown", (e) => {
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
  state.anim = null;
  gesture = { view: { ...state.view }, start: [...pointers.values()].map((p) => ({ ...p })), moved: false, t: performance.now() };
});
canvas.addEventListener("pointermove", (e) => {
  if (!pointers.has(e.pointerId) || !gesture) return;
  pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
  const now = [...pointers.values()];
  const a = gesture.start;
  if (now.length >= 2 && a.length >= 2) {
    const d0 = Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y) || 1;
    const d1 = Math.hypot(now[0].x - now[1].x, now[0].y - now[1].y);
    const m0 = { x: (a[0].x + a[1].x) / 2, y: (a[0].y + a[1].y) / 2 };
    const m1 = { x: (now[0].x + now[1].x) / 2, y: (now[0].y + now[1].y) / 2 };
    zoomAround(gesture.view, d1 / d0, m0, m1);
    gesture.moved = true;
  } else if (now.length === 1 && a.length === 1) {
    const dx = now[0].x - a[0].x, dy = now[0].y - a[0].y;
    if (Math.abs(dx) + Math.abs(dy) > 6) gesture.moved = true;
    if (gesture.moved) state.view = { s: gesture.view.s, x: gesture.view.x + dx, y: gesture.view.y + dy };
  }
});
function endPointer(e) {
  if (!pointers.has(e.pointerId)) return;
  const wasTap = gesture && !gesture.moved && pointers.size === 1 && performance.now() - gesture.t < 400;
  pointers.delete(e.pointerId);
  if (wasTap) tapMap(e.offsetX, e.offsetY);
  gesture = pointers.size ? { view: { ...state.view }, start: [...pointers.values()].map((p) => ({ ...p })), moved: true, t: 0 } : null;
}
canvas.addEventListener("pointerup", endPointer);
canvas.addEventListener("pointercancel", endPointer);
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  state.anim = null;
  const p = { x: e.offsetX, y: e.offsetY };
  zoomAround({ ...state.view }, Math.exp(-e.deltaY * 0.0015), p, p);
}, { passive: false });
canvas.addEventListener("dblclick", () => { state.room = null; $("here").textContent = ""; animateTo(wholeMap()); });

function zoomAround(base, factor, from, to) {
  const s = Math.max(0.3, Math.min(8, base.s * factor));
  const wx = (from.x - base.x) / base.s, wy = (from.y - base.y) / base.s;
  state.view = { s, x: to.x - wx * s, y: to.y - wy * s };
}

function inside(poly, x, y) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

function tapMap(sx, sy) {
  if (!state.scene) return;
  const x = (sx - state.view.x) / state.view.s, y = (sy - state.view.y) / state.view.s;
  const room = state.scene.rooms.find((r) => inside(r.poly, x, y));
  if (!room) return;
  const card = state.cards.find((c) => c.room === room.name);
  state.sel = card ? card.id : null;
  renderTasks();
  zoomToRoom(room.name);
  showChat(room.name === "Apothecary" ? null : room.name, room.title);
}

// --- drawing -------------------------------------------------------------------------------------
function frame(now) {
  const dpr = window.devicePixelRatio || 1;
  const { w, h } = size();
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    if (!state.room && state.scene) state.view = wholeMap();
    else if (state.room) state.view = fitView(state.scene.rooms.find((r) => r.name === state.room).box, 0.82);
  }
  if (state.anim) {
    const t = Math.min(1, (now - state.anim.t0) / state.anim.ms), k = ease(t);
    const a = state.anim.from, b = state.anim.to;
    // zoom in log space so the move feels even
    const s = Math.exp(Math.log(a.s) + (Math.log(b.s) - Math.log(a.s)) * k);
    const cx = w / 2, cy = h / 2;
    const ax = (cx - a.x) / a.s, ay = (cy - a.y) / a.s, bx = (cx - b.x) / b.s, by = (cy - b.y) / b.s;
    const wx = ax + (bx - ax) * k, wy = ay + (by - ay) * k;
    state.view = { s, x: cx - wx * s, y: cy - wy * s };
    if (t >= 1) state.anim = null;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (state.map) {
    const v = state.view;
    ctx.save();
    ctx.translate(v.x, v.y);
    ctx.scale(v.s, v.s);
    ctx.imageSmoothingEnabled = false;
    ctx.shadowColor = "rgba(0,0,0,.6)";
    ctx.shadowBlur = 24 * v.s;
    ctx.drawImage(state.map, 0, 0);
    ctx.shadowBlur = 0;
    drawGlow(now);
    drawAvatars(now);
    ctx.restore();
    drawLabels();
  }
  requestAnimationFrame(frame);
}

function drawGlow(now) {
  const room = state.room && state.scene.rooms.find((r) => r.name === state.room);
  if (!room) return;
  const pulse = 0.5 + 0.5 * Math.sin((now - state.glow) / 380);
  const intro = Math.min(1, (now - state.glow) / 600);
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  ctx.beginPath();
  room.poly.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.fillStyle = `rgba(242,163,58,${(0.10 + 0.08 * pulse) * intro})`;
  ctx.fill();
  ctx.lineWidth = 2 / state.view.s + 1;
  ctx.strokeStyle = `rgba(255,210,122,${(0.55 + 0.35 * pulse) * intro})`;
  ctx.stroke();
  ctx.restore();
}

function drawAvatars(now) {
  for (const a of state.scene.avatars) {
    const sheet = state.sprites[a.skin], meta = state.scene.sprites[a.skin];
    const [x, y] = a.at;
    ctx.fillStyle = "rgba(0,0,0,.35)";
    ctx.beginPath();
    ctx.ellipse(x, y, 12, 5, 0, 0, Math.PI * 2);
    ctx.fill();
    if (!sheet || !meta) continue;
    const f = Math.floor(now / 160) % meta.frames;
    ctx.drawImage(sheet, f * meta.w, 0, meta.w, meta.h, Math.round(x - meta.w / 2), Math.round(y - meta.h + 4), meta.w, meta.h);
  }
}

function drawLabels() {
  const v = state.view;
  const px = parseFloat(getComputedStyle(document.body).fontSize) * 0.8;
  ctx.font = `600 ${px}px ui-monospace, Menlo, Consolas, monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const r of state.scene.rooms) {
    // on the front half of the room's own floor, so it never lands on a neighbour
    const cx = r.poly.reduce((a, p) => a + p[0], 0) / 4, cy = r.poly.reduce((a, p) => a + p[1], 0) / 4;
    const x = v.x + cx * v.s, y = v.y + (cy + (r.poly[2][1] - cy) * 0.5) * v.s;
    const text = r.title.length > 22 ? r.title.slice(0, 21) + "\u2026" : r.title;
    const tw = ctx.measureText(text).width + px * 1.2, th = px * 1.7;
    const on = r.name === state.room;
    ctx.globalAlpha = state.room && !on ? 0.55 : 1;
    ctx.fillStyle = on ? "rgba(58,36,14,.92)" : "rgba(12,8,18,.8)";
    ctx.fillRect(Math.round(x - tw / 2), Math.round(y - th / 2), Math.round(tw), Math.round(th));
    ctx.strokeStyle = on ? "#f2a33a" : "#3d2f50";
    ctx.lineWidth = 2;
    ctx.strokeRect(Math.round(x - tw / 2) + 1, Math.round(y - th / 2) + 1, Math.round(tw) - 2, Math.round(th) - 2);
    ctx.fillStyle = on ? "#ffd27a" : "#e9dcbc";
    ctx.fillText(text, Math.round(x), Math.round(y) + 1);
  }
  ctx.globalAlpha = 1;
}

// --- tasks and chat ------------------------------------------------------------------------------
function renderTasks() {
  const list = $("tasks");
  list.replaceChildren();
  $("count").textContent = state.cards.length ? String(state.cards.length) : "";
  if (!state.cards.length) list.append(el("li", "empty", "No tasks yet. Add them in the Dungeon's Tasks tab."));
  const rooms = new Map((state.scene ? state.scene.rooms : []).map((r) => [r.name, r.title]));
  for (const c of state.cards) {
    const li = el("li");
    const b = el("button", "task" + (c.id === state.sel ? " sel" : ""));
    b.type = "button";
    b.append(el("span", "badge " + c.column, LABELS[c.column] || c.column), el("span", "title", c.title));
    const meta = el("span", "meta");
    meta.append(el("span", "room-chip", rooms.get(c.room) || c.room));
    if (c.assignee) meta.append(el("span", "who-chip", c.assignee));
    if (c.progress !== null && c.progress !== undefined) {
      const wrap = el("span", "bar-wrap"), fill = el("span", "bar-fill");
      fill.style.display = "block";
      fill.style.width = Math.max(0, Math.min(100, c.progress)) + "%";
      wrap.append(fill);
      meta.append(wrap, el("span", "", c.progress + "%"));
    }
    if (c.checks[1]) meta.append(el("span", "", c.checks[0] + "/" + c.checks[1]));
    b.append(meta);
    const note = c.column === "done" && c.learnt ? "learnt: " + c.learnt : c.status_note;
    if (note) b.append(el("span", "note", note));
    b.addEventListener("click", () => pickTask(c.id));
    li.append(b);
    list.append(li);
  }
}

function pickTask(id) {
  const c = state.cards.find((x) => x.id === id);
  if (!c) return;
  state.sel = id;
  renderTasks();
  zoomToRoom(c.room);
  const room = state.scene.rooms.find((r) => r.name === c.room);
  showChat(c.topic || (c.room !== "Apothecary" ? c.room : null), room ? room.title : c.room);
}

function clock(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function showChat(topic, title) {
  $("chatRoom").textContent = title || "";
  state.chatKey = topic || "";
  const list = $("chat");
  if (!topic) {
    list.replaceChildren(el("li", "empty", "This task has no room chat yet."));
    return;
  }
  let data;
  try { data = await getJSON("/api/chat/" + encodeURIComponent(topic) + "?tail=40"); } catch (_e) { return; }
  if (state.chatKey !== topic) return;
  const seen = new Set([...list.children].map((n) => n.dataset.key));
  list.replaceChildren();
  if (!data.messages.length) list.append(el("li", "empty", "No messages in this room yet."));
  for (const m of data.messages) {
    const who = String(m.from || "").split(":")[0];
    const key = m.ts + m.from;
    const li = el("li", "msg " + who + (seen.size && !seen.has(key) ? " fresh" : ""));
    li.dataset.key = key;
    const head = el("div", "who", who || "?");
    const t = el("time", "", clock(m.ts));
    head.append(t);
    li.append(el("span", "pip"), head, el("div", "text", m.text));
    list.append(li);
  }
  list.scrollTop = list.scrollHeight;
}

async function load() {
  const [scene, board] = await Promise.all([getJSON("/api/scene"), getJSON("/api/board")]);
  state.scene = scene;
  state.cards = board.cards;
  if (scene.map) {
    const key = JSON.stringify([scene.map, scene.rooms.map((r) => r.name)]);
    if (key !== state.mapKey) {
      state.map = await loadImage("/api/map.png?v=" + encodeURIComponent(key.length + ":" + hash(key)));
      state.mapKey = key;
    }
    for (const skin of Object.keys(scene.sprites)) {
      if (!state.sprites[skin]) state.sprites[skin] = await loadImage("/api/sprite/" + skin + ".png");
    }
  }
  if (!state.fitted && scene.map) { state.view = wholeMap(); state.fitted = true; }
  if (state.room && !scene.rooms.some((r) => r.name === state.room)) state.room = null;
  renderTasks();
  if (state.chatKey) showChat(state.chatKey, $("chatRoom").textContent);
  else if (!$("chat").children.length) $("chat").append(el("li", "empty", "Tap a task to open its room."));
}

function hash(text) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// --- live updates --------------------------------------------------------------------------------
let pending = null;
function live() {
  const src = new EventSource("/api/events");
  src.onopen = () => $("live").classList.add("on");
  src.onerror = () => $("live").classList.remove("on");
  src.addEventListener("change", () => {
    clearTimeout(pending);
    pending = setTimeout(() => load().catch(() => {}), 150);
  });
}

// --- sound: a soft chime on zoom, off by default on phones ----------------------------------------
let audio = null;
const soundKey = "cli-avatars-sound";
let soundOn = localStorage.getItem(soundKey) !== null ? localStorage.getItem(soundKey) === "1"
  : window.matchMedia("(pointer: fine)").matches;
function paintSound() { $("sound").setAttribute("aria-pressed", soundOn ? "true" : "false"); }
$("sound").addEventListener("click", () => { soundOn = !soundOn; localStorage.setItem(soundKey, soundOn ? "1" : "0"); paintSound(); if (soundOn) chime(); });
function chime() {
  if (!soundOn) return;
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const t = audio.currentTime, out = audio.createGain();
    out.gain.setValueAtTime(0.0001, t);
    out.gain.exponentialRampToValueAtTime(0.06, t + 0.03);
    out.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
    out.connect(audio.destination);
    for (const [f, d] of [[523.25, 0], [783.99, 0.07]]) {
      const o = audio.createOscillator();
      o.type = "triangle";
      o.frequency.setValueAtTime(f, t + d);
      o.connect(out);
      o.start(t + d);
      o.stop(t + 0.72);
    }
  } catch (_e) { soundOn = false; paintSound(); }
}

$("fit").addEventListener("click", () => { state.room = null; $("here").textContent = ""; animateTo(wholeMap()); });
paintSound();
load().then(live).catch(() => {});
requestAnimationFrame(frame);
