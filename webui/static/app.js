// PHONE.1/2/3/4: the Dungeon map, its tasks and the room chat; with writes on, open sessions, send prompts,
// build and customize rooms, and Update. DECIDE.1: decisions waiting on Daniel, answered in their chat.
// Every text goes in with textContent.
"use strict";

const $ = (id) => document.getElementById(id);
const canvas = $("map");
const ctx = canvas.getContext("2d");
const LABELS = { todo: "TODO", doing: "DOING", review: "REVIEW", done: "DONE", blocked: "BLOCKED" };
const state = { scene: null, cards: [], sel: null, room: null, map: null, mapKey: "", sprites: {},
  view: { x: 0, y: 0, s: 1 }, anim: null, fitted: false, chatKey: "", glow: 0, walkers: new Map(),
  writes: { writes: false, sessions: [], folders: [] }, lastReply: "", sending: false, pick: { kind: "simple", cli: "claude", topic: "" },
  builds: null, rise: new Map(), prevMap: null, prevOrigin: [0, 0], rooms: { writes: false, rooms: [], points: [], skins: [] }, form: null };

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

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CLI-Avatars-CSRF": state.writes.csrf || "" },
    body: JSON.stringify(body || {}),
  });
  let data = {};
  try { data = await res.json(); } catch (_e) { /* empty body */ }
  return { ok: res.ok, status: res.status, data };
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
  $("editRoom").hidden = false;
  if (!quiet) chime();
}

function leaveRoom() {
  state.room = null;
  $("here").textContent = "";
  $("editRoom").hidden = true;
  animateTo(wholeMap());
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
canvas.addEventListener("dblclick", leaveRoom);

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
  if (room.name === state.room && !state.anim) return openRooms(room.id);
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
    if (state.rise.size && state.prevMap) {
      ctx.drawImage(state.prevMap, state.prevOrigin[0] - state.scene.map.origin[0], state.prevOrigin[1] - state.scene.map.origin[1]);
      ctx.shadowBlur = 0;
      ctx.drawImage(riseLayer(now), 0, 0);
    } else ctx.drawImage(state.map, 0, 0);
    ctx.shadowBlur = 0;
    drawFlare(now);
    drawGlow(now);
    drawAvatars(now);
    ctx.restore();
    drawLabels();
    drawNames();
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

// avatars glide from their last position to the newest one over one SSE tick
const TICK = 260;
function setAvatars(list, now) {
  const next = new Map();
  for (const a of list) {
    const was = state.walkers.get(a.id);
    const from = was ? place(was, now) : a.at;
    next.set(a.id, { a, from, to: a.at, t0: now });
  }
  state.walkers = next;
}

function place(w, now) {
  const k = Math.min(1, (now - w.t0) / TICK);
  return [w.from[0] + (w.to[0] - w.from[0]) * k, w.from[1] + (w.to[1] - w.from[1]) * k];
}

function drawAvatars(now) {
  const shown = [...state.walkers.values()].map((w) => ({ w, at: place(w, now) })).sort((p, q) => p.at[1] - q.at[1]);
  for (const { w, at } of shown) {
    const a = w.a, sheet = state.sprites[a.sprite], meta = state.scene.sprites[a.sprite];
    const [x, y] = at;
    ctx.fillStyle = "rgba(0,0,0,.38)";
    ctx.beginPath();
    ctx.ellipse(x, y, a.kind === "subagent" ? 8 : 11, 4, 0, 0, Math.PI * 2);
    ctx.fill();
    if (!sheet || !meta) continue;
    const walking = a.walk || Math.hypot(w.to[0] - at[0], w.to[1] - at[1]) > 0.3;
    const f = Math.floor((now + hashNum(a.id) * 37) / (walking ? 110 : 190)) % meta.frames;
    const top = Math.round(y - meta.h * (1 - meta.feet));
    ctx.save();
    ctx.translate(Math.round(x), 0);
    if (a.face < 0) ctx.scale(-1, 1);
    ctx.drawImage(sheet, f * meta.w, walking ? meta.h : 0, meta.w, meta.h, -Math.round(meta.w / 2), top, meta.w, meta.h);
    ctx.restore();
    if (a.kind === "user") {
      ctx.strokeStyle = "rgba(255,210,122,.75)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(x, y, 13, 5, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}

function drawNames() {
  const v = state.view;
  if (v.s < 1.7) return;
  ctx.font = `600 11px ui-monospace, Menlo, Consolas, monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  const now = performance.now();
  for (const w of state.walkers.values()) {
    const meta = state.scene.sprites[w.a.sprite];
    if (!meta || !w.a.name) continue;
    const [x, y] = place(w, now);
    const sx = v.x + x * v.s, sy = v.y + (y - meta.h * (1 - meta.feet)) * v.s - 3;
    const tw = ctx.measureText(w.a.name).width + 8;
    ctx.fillStyle = "rgba(12,8,18,.72)";
    ctx.fillRect(Math.round(sx - tw / 2), Math.round(sy - 14), Math.round(tw), 14);
    ctx.fillStyle = w.a.kind === "user" ? "#ffd27a" : "#e9dcbc";
    ctx.fillText(w.a.name, Math.round(sx), Math.round(sy));
  }
}

function hashNum(text) {
  let h = 7;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return Math.abs(h) % 97;
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
    if (r.sign) drawSign(r.sign, x, y + th, px);
  }
  ctx.globalAlpha = 1;
}

// ORCH.ROOM door sign: the doing card and its note under the room's name, amber while a card is blocked
function drawSign(sign, x, y, px) {
  const words = [sign.lines[1], sign.lines[2]].filter(Boolean).join(" · ");
  const text = words.length > 34 ? words.slice(0, 33) + "\u2026" : words;
  const tw = ctx.measureText(text).width + px * 1.2, th = px * 1.5;
  ctx.fillStyle = "rgba(23,16,34,.9)";
  ctx.fillRect(Math.round(x - tw / 2), Math.round(y - th / 2), Math.round(tw), Math.round(th));
  ctx.strokeStyle = sign.amber ? "#ffbe3c" : "#8a5a34";
  ctx.lineWidth = 2;
  ctx.strokeRect(Math.round(x - tw / 2) + 1, Math.round(y - th / 2) + 1, Math.round(tw) - 2, Math.round(th) - 2);
  ctx.fillStyle = sign.amber ? "#ffbe3c" : "#f0e6c8";
  ctx.fillText(text, Math.round(x), Math.round(y) + 1);
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
    if (c.decisions) meta.prepend(el("span", "badge decide", c.decisions > 1 ? "DECIDE \u00d7" + c.decisions : "DECIDE"));
    b.append(meta);
    const note = c.column === "done" && c.learnt ? "learnt: " + c.learnt : c.status_note;
    if (note) b.append(el("span", "note", note));
    b.addEventListener("click", () => pickTask(c.id));
    li.append(b);
    if (c.id === state.sel) li.append(taskChats(c));
    list.append(li);
  }
}

// TASK-CHAT.1: the selected task's chats; with writes on, start a Claude one (it runs on the first Send)
function taskChats(c) {
  const row = el("div", "task-chats");
  row.append(el("span", "tc-label", "Chats"));
  (c.chats || []).forEach((ch, i) => {
    const b = el("button", "tc-chip " + ch.cli + (state.chatKey === ch.room ? " sel" : ""), "chat " + (i + 1));
    b.type = "button";
    b.addEventListener("click", () => { showChat(ch.room, c.title + " · chat " + (i + 1)); renderTasks(); });
    row.append(b);
  });
  if (state.writes.writes) {
    const add = el("button", "tc-chip tc-new", "+ Claude chat");
    add.type = "button";
    add.addEventListener("click", () => newTaskChat(c));
    row.append(add);
  } else if (!(c.chats || []).length) row.append(el("span", "tc-none", "none yet"));
  return row;
}

async function newTaskChat(c) {
  const res = await postJSON("/api/cards/" + c.id + "/chats", { cli: "claude" }).catch(() => ({ ok: false, data: {} }));
  if (!res.ok) { $("composeHint").textContent = res.data.why || "Not started (" + (res.status || "offline") + ")."; return; }
  tone("done");
  const board = await getJSON("/api/board").catch(() => null);
  if (board) state.cards = board.cards;
  const card = state.cards.find((x) => x.id === c.id);
  await showChat(res.data.room, c.title + " · chat " + (card ? card.chats.length : ""));
  renderTasks();
}

function pickTask(id) {
  const c = state.cards.find((x) => x.id === id);
  if (!c) return;
  const asked = state.decisions.find((d) => d.card === id);
  if (asked) { openAsk(asked); return; }
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
  paintComposer(false);
  const list = $("chat");
  if (!topic) {
    list.replaceChildren(el("li", "empty", state.writes.writes ? "Open a session (+) or tap a room to chat." : "This task has no room chat yet."));
    $("typing").hidden = true;
    return;
  }
  let data;
  try { data = await getJSON("/api/chat/" + encodeURIComponent(topic) + "?tail=40"); } catch (_e) { return; }
  if (state.chatKey !== topic) return;
  const seen = new Set([...list.children].map((n) => n.dataset.key));
  const stick = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
  list.replaceChildren();
  if (!data.messages.length) list.append(el("li", "empty", "No messages in this room yet."));
  let reply = "";
  for (const m of data.messages) {
    const who = String(m.from || "").split(":")[0];
    const key = m.ts + m.from;
    const li = el("li", "msg " + who + (m.icon === "error" ? " error" : "") + (seen.size && !seen.has(key) ? " fresh" : ""));
    li.dataset.key = key;
    const head = el("div", "who", who || "?");
    const t = el("time", "", clock(m.ts));
    head.append(t);
    li.append(el("span", "pip"), head, m.media ? shot(m.media) : el("div", "text", m.text));
    list.append(li);
    if (who !== "user") reply = key;
  }
  if (reply && state.lastReply && reply !== state.lastReply && state.lastReply.startsWith(topic + "|")) tone("reply");
  state.lastReply = topic + "|" + reply;
  state.running = !!data.running;
  $("typing").hidden = !state.running;
  $("typingText").textContent = state.running ? "Answering in " + (title || topic) + "…" : "";
  paintComposer(false);
  if (stick || seen.size === 0) list.scrollTop = list.scrollHeight;
  paintAsk();
}

// --- media a turn made: inline, tap for the full view ------------------------------------------------
function mediaNode(media, full) {
  const src = "/api/media/" + encodeURIComponent(media.id);
  if (media.type === "video") {
    const v = document.createElement("video");
    v.src = src;
    v.muted = true;
    v.loop = true;
    v.playsInline = true;
    v.setAttribute("playsinline", "");
    v.preload = "metadata";
    v.controls = !!full;
    if (full) v.autoplay = true;
    return v;
  }
  const img = new Image();
  img.alt = media.name;
  img.decoding = "async";
  img.onload = () => {
    if (img.naturalWidth > 256 && img.naturalHeight > 256) return;
    img.classList.add("pixel");
    // whole-number zoom keeps pixel art crisp
    const room = full ? Math.min(window.innerWidth - 24, window.innerHeight * 0.78) : 132;
    const k = Math.max(1, Math.floor(room / Math.max(img.naturalWidth, img.naturalHeight)));
    img.style.width = img.naturalWidth * k + "px";
    img.style.maxWidth = "none";
    img.style.maxHeight = "none";
  };
  img.src = src;
  return img;
}

const shots = new Map();
function shot(media) {
  if (shots.has(media.id)) return shots.get(media.id);
  const b = el("button", "shot");
  b.type = "button";
  b.title = media.name;
  const node = mediaNode(media, false);
  b.append(node);
  if (node.tagName === "VIDEO") node.addEventListener("loadeddata", () => node.play().catch(() => {}), { once: true });
  b.addEventListener("click", () => openViewer(media));
  shots.set(media.id, b);
  return b;
}

function openViewer(media) {
  $("viewerStage").replaceChildren(mediaNode(media, true));
  $("viewerName").textContent = media.name;
  $("viewer").hidden = false;
}
function closeViewer() { $("viewer").hidden = true; $("viewerStage").replaceChildren(); }
$("viewerClose").addEventListener("click", closeViewer);
$("viewer").addEventListener("click", (e) => { if (e.target === $("viewer") || e.target === $("viewerStage")) closeViewer(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("viewer").hidden) closeViewer(); });

// --- writes: composer and sessions sheet -----------------------------------------------------------
function paintComposer(busy) {
  const on = state.writes.writes, topic = state.chatKey;
  const form = $("composer"), hint = $("composeHint");
  form.hidden = !on;
  $("sessions").hidden = false;
  if (!on) { hint.textContent = "Sending from the phone is off (Dungeon: Settings › Phone)."; return; }
  const can = !!topic && !state.running && !busy && !state.sending;
  const asking = !!state.ask && state.ask.room === topic;
  $("prompt").disabled = !topic;
  $("send").disabled = asking ? busy || state.sending : !can;
  $("send").textContent = asking ? "Answer" : "Send";
  $("prompt").placeholder = asking ? "Your answer\u2026" : topic ? "Ask in " + ($("chatRoom").textContent || topic) + "\u2026" : "Tap a room or open a session (+)";
  hint.textContent = topic ? "" : "";
}

async function loadWrites() {
  try { state.writes = await getJSON("/api/sessions"); } catch (_e) { return; }
  paintComposer(false);
  if (!$("sheet").hidden) paintSheet();
}

$("composer").addEventListener("submit", (e) => { e.preventDefault(); sendPrompt(); });
$("prompt").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(pointer: fine)").matches) {
    e.preventDefault();
    sendPrompt();
  }
});
$("prompt").addEventListener("input", growPrompt);
// tapping Send keeps the keyboard up, as chat apps do
$("send").addEventListener("pointerdown", (e) => { if (document.activeElement === $("prompt")) e.preventDefault(); });
$("prompt").addEventListener("focus", () => { document.body.classList.add("composing"); setTimeout(() => { $("chat").scrollTop = $("chat").scrollHeight; }, 250); });
$("prompt").addEventListener("blur", () => { setTimeout(() => { if (document.activeElement !== $("prompt")) document.body.classList.remove("composing"); }, 150); });

function growPrompt() {
  const t = $("prompt");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight + 4, window.innerHeight * 0.3) + "px";
}

async function sendPrompt() {
  if (state.ask && state.ask.room === state.chatKey) { answerAsk(null); return; }
  const text = $("prompt").value, topic = state.chatKey;
  if (!text.trim() || !topic || state.sending || state.running) return;
  state.sending = true;
  paintComposer(true);
  tone("send");
  const res = await postJSON("/api/chat/" + encodeURIComponent(topic), { text }).catch(() => ({ ok: false, data: {} }));
  state.sending = false;
  if (res.ok) {
    $("prompt").value = "";
    growPrompt();
    state.running = true;
    showChat(topic, $("chatRoom").textContent);
  } else {
    $("composeHint").textContent = res.data.why || (res.status === 429 ? "Too many sends: wait a minute." : "Not sent (" + (res.status || "offline") + ").");
    paintComposer(false);
  }
}

function openSheet() {
  $("sheet").hidden = false;
  $("sheetStatus").textContent = "";
  paintSheet();
  loadWrites();
}
function closeSheet() { $("sheet").hidden = true; }
$("sessions").addEventListener("click", openSheet);
$("sheetClose").addEventListener("click", closeSheet);
$("sheet").addEventListener("click", (e) => { if (e.target === $("sheet")) closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) closeSheet(); });
for (const b of document.querySelectorAll(".seg button")) {
  b.addEventListener("click", () => {
    if (b.dataset.kind) state.pick.kind = b.dataset.kind;
    if (b.dataset.cli) state.pick.cli = b.dataset.cli;
    paintSheet();
  });
}

function paintSheet() {
  const w = state.writes, open = new Set(w.sessions.map((x) => x.sid));
  $("sheetOff").hidden = !!w.writes;
  $("sheetOff").textContent = "Sending from the phone is off. In the Dungeon: Settings › Phone › Allow the phone to open sessions and send prompts.";
  $("newSession").hidden = !w.writes;
  for (const b of document.querySelectorAll(".seg button")) {
    b.classList.toggle("on", b.dataset.kind ? b.dataset.kind === state.pick.kind : b.dataset.cli === state.pick.cli);
    b.setAttribute("aria-checked", b.classList.contains("on") ? "true" : "false");
  }
  const list = $("openSessions");
  list.replaceChildren();
  for (const x of w.sessions) {
    const li = el("li");
    li.append(el("span", "", (x.kind === "main" ? "♛ " : "• ") + titleOf(x.sid)), el("small", "", x.kind + " · " + x.cli));
    const go = el("button", "end", "Chat");
    go.type = "button";
    go.addEventListener("click", () => { closeSheet(); goRoom(x.sid); });
    li.append(go);
    if (w.writes) {
      const end = el("button", "end", "End");
      end.type = "button";
      end.addEventListener("click", () => endSession(x.sid));
      li.append(end);
    }
    list.append(li);
  }
  const folders = $("folders");
  folders.replaceChildren();
  const free = w.folders.filter((f) => !open.has(f.topic));
  if (!free.includes(w.folders.find((f) => f.topic === state.pick.topic))) state.pick.topic = free.length ? free[0].topic : "";
  if (!free.length) folders.append(el("li", "empty", w.folders.length ? "Every room with a folder is open." : "No room has a folder yet: pick one in the Dungeon's chat (Folder…) once."));
  for (const f of free) {
    const li = el("li"), b = el("button", f.topic === state.pick.topic ? "on" : "");
    b.type = "button";
    b.append(el("span", "", f.title), el("small", "", f.folder));
    b.addEventListener("click", () => { state.pick.topic = f.topic; paintSheet(); });
    li.append(b);
    folders.append(li);
  }
  $("openSession").disabled = !state.pick.topic;
}

function titleOf(topic) {
  const room = state.scene && state.scene.rooms.find((r) => r.name === topic);
  return room ? room.title : topic;
}

async function goRoom(topic) {
  await load().catch(() => {});
  zoomToRoom(topic);
  showChat(topic, titleOf(topic));
}

$("openSession").addEventListener("click", async () => {
  const p = state.pick;
  if (!p.topic) return;
  $("openSession").disabled = true;
  const res = await postJSON("/api/sessions", { kind: p.kind, cli: p.cli, topic: p.topic }).catch(() => ({ ok: false, data: {} }));
  if (!res.ok) {
    $("sheetStatus").textContent = res.data.why || "Not opened (" + (res.status || "offline") + ").";
    $("openSession").disabled = false;
    return;
  }
  tone("send");
  closeSheet();
  await loadWrites();
  goRoom(p.topic);
});

async function endSession(sid) {
  const res = await postJSON("/api/sessions/" + encodeURIComponent(sid) + "/end", {}).catch(() => ({ ok: false, data: {} }));
  $("sheetStatus").textContent = res.ok ? titleOf(sid) + " ended. Its avatars walk back to the Apothecary." : "Not ended (" + (res.status || "offline") + ").";
  loadWrites();
}

async function load() {
  const [scene, board] = await Promise.all([getJSON("/api/scene"), getJSON("/api/board"), loadWrites(), loadDecisions()]);
  const oldOrigin = state.scene && state.scene.map ? state.scene.map.origin : null;
  state.scene = scene;
  state.cards = board.cards;
  if (scene.map) {
    const key = JSON.stringify([scene.map, scene.rooms.map((r) => [r.name, r.build])]);
    if (key !== state.mapKey) {
      const img = await loadImage("/api/map.png?v=" + encodeURIComponent(key.length + ":" + hash(key)));
      const risen = state.builds ? scene.rooms.filter((r) => state.builds.get(r.name) !== r.build) : [];
      if (risen.length && state.map) {
        state.prevMap = state.map;
        state.prevOrigin = oldOrigin || [0, 0];
        const t0 = performance.now();
        for (const r of risen) state.rise.set(r.name, { t0, box: r.box, poly: r.poly });
        tone("build");
      }
      state.map = img;
      state.mapKey = key;
    }
    state.builds = new Map(scene.rooms.map((r) => [r.name, r.build]));
    for (const skin of Object.keys(scene.sprites)) {
      if (!state.sprites[skin]) state.sprites[skin] = await loadImage("/api/sprite/" + skin + ".png");
    }
    setAvatars(scene.avatars, performance.now());
  }
  if (!state.fitted && scene.map) { state.view = wholeMap(); state.fitted = true; }
  if (state.room && !scene.rooms.some((r) => r.name === state.room)) { state.room = null; $("editRoom").hidden = true; }
  renderTasks();
  if (state.chatKey) showChat(state.chatKey, $("chatRoom").textContent);
  else if (!$("chat").children.length) $("chat").append(el("li", "empty", "Tap a task to open its room."));
}

function hash(text) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// --- PHONE.4: Update app, as the Dungeon's toolbar; the page reconnects after the relaunch --------
const STEPS = [["checking dev", "Check"], ["pulling", "Pull"], ["selftest", "Selftest"], ["boot check", "Boot"],
  ["building", "Build"], ["restarting", "Restart"]];
const DONE = { up_to_date: "ok", updated: "ok", failed: "bad", rolled_back: "bad", blocked: "bad" };
state.upd = null;
state.restarting = false;

async function loadUpdate() {
  try { paintUpdate(await getJSON("/api/update")); } catch (_e) { /* offline */ }
}

function stepOf(u) {
  if (u.phase === "staged" || u.phase === "rolled_back" || state.restarting) return STEPS.length - 1;
  if (u.phase === "updated") return STEPS.length;
  const line = (u.line || "").toLowerCase(), found = STEPS.findIndex(([key]) => line.includes(key));
  if (u.running) return (state.updStep = Math.max(0, found));
  return u.phase === "failed" ? (found >= 0 ? found : state.updStep || 0) : -1;
}

function paintUpdate(u) {
  const was = state.upd;
  state.upd = u;
  // the old app may stop before its last event leaves, so its "restarting" line is the signal
  if (u.phase === "staged" || (u.running && /restarting/i.test(u.line))) state.restarting = true;
  $("updVer").textContent = "v" + u.version;
  $("updCommit").textContent = u.commit || "no commit";
  const checked = Date.parse(u.last_checked);
  $("updChecked").textContent = "Last checked " + (isNaN(checked) ? u.last_checked || "not yet"
    : new Date(checked).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }));
  const at = stepOf(u), bad = !u.running && DONE[u.phase] === "bad", list = $("updSteps");
  list.hidden = at < 0;
  list.replaceChildren(...STEPS.map(([, label], i) => el("li", i < at ? "done" : i === at ? (bad ? "bad" : "now") : "", label)));
  const line = $("updLine");
  line.className = "upd-line " + (u.running || state.restarting ? "busy" : DONE[u.phase] || "");
  if (state.restarting) line.textContent = state.retry || "Restarting the Dungeon. The page reconnects on its own.";
  else if (u.running) line.textContent = u.line || "Update: checking dev";
  else if (u.phase === "up_to_date") line.textContent = "Up to date on " + (u.commit || "dev");
  else if (u.phase === "updated" || u.phase === "rolled_back") line.textContent = u.note;
  else if (u.phase === "failed") line.textContent = "Update stopped: " + (u.note || "update failed");
  else line.textContent = "";
  const writes = state.writes.writes;
  $("updGo").disabled = !u.enabled || !writes || state.restarting;
  $("updGo").textContent = u.running || state.restarting ? "Updating…" : "Update app";
  $("updWhy").textContent = u.running || state.restarting ? "" : u.reason
    || (writes ? "" : "Updating from the phone is off. In the Dungeon: Settings › Phone › Allow the phone to open sessions and send prompts.");
  $("appBtn").classList.toggle("busy", !!u.running || state.restarting);
  if (was && (was.running || was.phase === "staged") && !u.running && DONE[u.phase]) tone(DONE[u.phase] === "ok" ? "done" : "failed");
}

$("appBtn").addEventListener("click", () => { $("upd").hidden = false; loadWrites().then(loadUpdate); });
$("updClose").addEventListener("click", () => { $("upd").hidden = true; });
$("upd").addEventListener("click", (e) => { if (e.target === $("upd")) $("upd").hidden = true; });
$("updGo").addEventListener("click", () => { $("updAsk").hidden = false; $("updYes").focus(); });
$("updNo").addEventListener("click", () => { $("updAsk").hidden = true; });
$("updAsk").addEventListener("click", (e) => { if (e.target === $("updAsk")) $("updAsk").hidden = true; });
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("updAsk").hidden) $("updAsk").hidden = true;
  else if (!$("upd").hidden) $("upd").hidden = true;
});
$("updYes").addEventListener("click", async () => {
  $("updAsk").hidden = true;
  $("updGo").disabled = true;
  tone("send");
  const res = await postJSON("/api/update", {}).catch(() => ({ ok: false, data: {} }));
  if (!res.ok) $("updWhy").textContent = res.data.why || (res.status === 429 ? "Too many taps: wait a minute." : "Not started (" + (res.status || "offline") + ").");
  loadUpdate();
});

// after Update the old app quits and the new one serves again: try with backoff until it answers
async function reconnect(src) {
  src.close();
  $("live").classList.remove("on");
  for (let n = 1, wait = 1000; state.restarting; n++, wait = Math.min(wait * 2, 15000)) {
    state.retry = "Restarting. Reconnecting (try " + n + ")…";
    if (state.upd) paintUpdate(state.upd);
    await new Promise((ok) => setTimeout(ok, wait));
    try {
      const res = await fetch("/api/update", { credentials: "same-origin", cache: "no-store" });
      if (!res.ok) continue;
      const u = await res.json();
      if (u.phase === "staged") continue;
      state.restarting = false;
      state.retry = "";
      paintUpdate(u);
      $("upd").hidden = false;
      load().then(live).catch(() => {});
      return;
    } catch (_e) { /* still down */ }
  }
}

// --- PHONE.3: a new or changed room rises out of the dark, as the Dungeon's build-in does -------------
const BUILD_MS = 1400, CELL = 4;
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
let riseCanvas = null;
function riseLayer(now) {
  const map = state.map;
  riseCanvas = riseCanvas || document.createElement("canvas");
  if (riseCanvas.width !== map.width || riseCanvas.height !== map.height) { riseCanvas.width = map.width; riseCanvas.height = map.height; }
  const o = riseCanvas.getContext("2d");
  o.clearRect(0, 0, map.width, map.height);
  o.drawImage(map, 0, 0);
  for (const [name, r] of state.rise) {
    const t = (now - r.t0) / BUILD_MS;
    if (t >= 1) { state.rise.delete(name); continue; }
    const [bx, by, bw, bh] = r.box, front = t * 1.3 - 0.05, step = Math.floor(t * 12);
    for (let y = 0; y < bh; y += CELL) {
      for (let x = 0; x < bw; x += CELL) {
        const cx = x / CELL, cy = y / CELL;
        const order = (1 - y / Math.max(1, bh - 1)) * 0.78 + BAYER[(cy & 3) * 4 + (cx & 3)] / 16 * 0.22;
        if (order < front) continue;
        o.clearRect(bx + x, by + y, CELL, CELL);
        const seed = ((cx * 73856093) ^ (cy * 19349663) ^ (step * 83492791)) & 1023;
        if (order < front + 0.09 && seed < 380 && inside(r.poly, bx + x + 2, by + y + 2)) {
          o.fillStyle = "#d6c6a8";
          o.fillRect(bx + x + 1, by + y + 1, 2, 2);
        }
      }
    }
  }
  return riseCanvas;
}

function drawFlare(now) {
  for (const r of state.rise.values()) {
    const t = (now - r.t0) / BUILD_MS;
    const k = Math.sin(Math.PI * Math.min(1, Math.max(0, (t - 0.25) / 0.75))) * 0.32;
    if (k <= 0) continue;
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.beginPath();
    r.poly.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.fillStyle = `rgba(242,163,58,${k})`;
    ctx.fill();
    ctx.restore();
  }
}

// --- PHONE.3: Rooms sheet: list, add, edit, re-skin, resize, delete ------------------------------------
const SIDES = { n: "north", e: "east", s: "south", w: "west" };
const SIZE_NAMES = { S: "small", M: "mid", L: "large" };
const KIND_TAG = { apothecary: "Apothecary", main: "Throne", simple: "Session", custom: "Custom" };

async function loadRooms() {
  try { state.rooms = await getJSON("/api/rooms"); } catch (_e) { /* keep the last */ }
  if (state.rooms.writes && !state.writes.csrf) await loadWrites();
  return state.rooms;
}

async function openRooms(id) {
  $("rooms").hidden = false;
  $("roomStatus").textContent = "";
  await loadRooms();
  const room = id && state.rooms.rooms.find((r) => r.id === id);
  if (room) editRoom(room); else paintRoomList();
}
function closeRooms() { $("rooms").hidden = true; $("roomAsk").hidden = true; }
$("roomsBtn").addEventListener("click", () => openRooms());
$("editRoom").addEventListener("click", () => {
  const room = state.scene && state.scene.rooms.find((r) => r.name === state.room);
  openRooms(room ? room.id : null);
});
$("roomsClose").addEventListener("click", closeRooms);
$("roomsBack").addEventListener("click", () => { state.form = null; paintRoomList(); });
$("rooms").addEventListener("click", (e) => { if (e.target === $("rooms")) closeRooms(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("rooms").hidden) closeRooms(); });

function skinName(id) {
  const s = state.rooms.skins.find((k) => k.id === id);
  return s ? s.name : "Kit look";
}

function paintRoomList() {
  const w = state.rooms.writes;
  $("roomsTitle").textContent = "Rooms";
  $("roomsBack").hidden = true;
  $("roomList").hidden = false;
  $("roomForm").hidden = true;
  $("roomsOff").hidden = w;
  $("roomsOff").textContent = "Building from the phone is off. In the Dungeon: Settings › Phone › Allow the phone to open sessions and send prompts.";
  $("addRoom").hidden = !w;
  const list = $("roomRows");
  list.replaceChildren();
  for (const r of state.rooms.rooms) {
    const li = el("li"), b = el("button");
    b.type = "button";
    const tag = el("span", "tag " + (r.kind === "custom" ? "custom" : "lock"), KIND_TAG[r.kind] || r.kind);
    b.append(tag, el("b", "", r.name), el("span", "size", r.size));
    b.append(el("small", "", skinName(r.skin) + (r.topic ? " · " + r.topic : "")));
    b.addEventListener("click", () => editRoom(r));
    li.append(b);
    list.append(li);
  }
}

$("addRoom").addEventListener("click", () => {
  const point = state.rooms.points.find((p) => p.points.length);
  editRoom(null, point ? { at: point.id, point: point.points[0] } : { at: "", point: "" });
});

function editRoom(room, where) {
  const custom = !room || room.kind === "custom";
  state.form = room
    ? { mode: "edit", id: room.id, kind: room.kind, name: room.name, topic: room.topic, size: room.size, skin: room.skin || "",
      sizes: room.sizes, deletable: room.deletable, renamable: room.renamable }
    : { mode: "add", name: "", topic: "", size: "S", skin: state.rooms.skins[0].id, sizes: ["S", "M", "L"],
      deletable: false, renamable: true, at: where.at, point: where.point };
  state.form.start = { ...state.form };
  $("roomsTitle").textContent = room ? room.name : "New room";
  $("roomsBack").hidden = false;
  $("roomList").hidden = true;
  $("roomForm").hidden = false;
  $("roomsOff").hidden = state.rooms.writes;
  $("nameField").hidden = !custom;
  $("topicField").hidden = !custom;
  $("roomName").value = state.form.name;
  $("roomTopic").value = state.form.topic;
  $("connectBlock").hidden = !!room;
  $("roomDelete").hidden = !state.form.deletable;
  $("roomSave").textContent = room ? "Save" : "Build";
  $("roomStatus").textContent = "";
  for (const id of ["roomName", "roomTopic", "roomSave"]) $(id).disabled = !state.rooms.writes;
  paintSkins();
  paintForm(true);
}

function paintForm(rise) {
  const f = state.form;
  const sizes = $("roomSizes");
  sizes.replaceChildren();
  for (const k of ["S", "M", "L"]) {
    const b = el("button", k === f.size ? "on" : "", k);
    b.type = "button";
    b.append(el("small", "", SIZE_NAMES[k]));
    b.disabled = !f.sizes.includes(k) || !state.rooms.writes;
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", k === f.size ? "true" : "false");
    b.addEventListener("click", () => { f.size = k; paintForm(true); });
    sizes.append(b);
  }
  for (const b of $("skins").children) {
    const on = b.dataset.skin === f.skin;
    b.classList.toggle("on", on);
    b.setAttribute("aria-checked", on ? "true" : "false");
  }
  $("skinName").textContent = f.skin ? skinName(f.skin) : "the kit look";
  const preview = $("roomPreview");
  preview.parentElement.hidden = !f.skin;
  const src = "/api/skins/" + f.skin + "/" + (f.kind === "apothecary" ? "M" : f.size) + ".png";
  if (f.skin && preview.dataset.src !== src) {
    preview.dataset.src = src;
    preview.onload = () => {
      const room = preview.parentElement.clientWidth - 16;
      const k = Math.max(1, Math.floor(room / preview.naturalWidth));
      preview.width = preview.naturalWidth * Math.min(k, 3);
      preview.height = preview.naturalHeight * Math.min(k, 3);
      if (rise) { preview.classList.remove("rise"); void preview.offsetWidth; preview.classList.add("rise"); }
    };
    preview.src = src;
  }
  if (f.mode === "add") paintPoints();
  checkFit();
}

function paintSkins() {
  const box = $("skins");
  box.replaceChildren();
  for (const s of state.rooms.skins) {
    const b = el("button");
    b.type = "button";
    b.dataset.skin = s.id;
    b.setAttribute("role", "radio");
    b.title = s.name;
    const img = el("img");
    img.alt = "";
    img.loading = "lazy";
    img.src = "/api/skins/" + s.id + "/T.png";
    b.append(img, el("i", s.light), el("span", "", s.name));
    b.disabled = !state.rooms.writes;
    b.addEventListener("click", () => { state.form.skin = s.id; paintForm(true); });
    box.append(b);
  }
  const on = box.querySelector(`[data-skin="${state.form.skin}"]`);
  if (on) setTimeout(() => on.scrollIntoView({ block: "nearest", inline: "center" }), 60);
}

function paintPoints() {
  const f = state.form, list = $("points");
  list.replaceChildren();
  for (const row of state.rooms.points) {
    for (const p of row.points) {
      const on = f.at === row.id && f.point === p;
      const b = el("button", on ? "on" : "", row.name + " · " + SIDES[p[0]] + " " + p.slice(1));
      b.type = "button";
      b.disabled = !state.rooms.writes;
      b.addEventListener("click", () => { f.at = row.id; f.point = p; paintForm(false); });
      const li = el("li");
      li.append(b);
      list.append(li);
    }
  }
  if (!list.children.length) list.append(el("li", "empty", "No free point left: delete a room first."));
}

let fitSeq = 0;
async function checkFit() {
  const f = state.form, line = $("roomFit"), seq = ++fitSeq;
  line.className = "fit";
  if (f.mode !== "add") {
    line.textContent = f.kind === "custom" ? "A new size is placed again from the same point." : "";
    return;
  }
  if (!f.at) { line.textContent = ""; return; }
  const q = new URLSearchParams({ size: f.size, at: f.at, point: f.point });
  try {
    const res = await getJSON("/api/rooms/plan?" + q.toString());
    if (seq !== fitSeq) return;
    line.className = "fit " + (res.fits ? "ok" : "bad");
    line.textContent = res.fits ? "Fits: a corridor joins it to " + titleOfRoom(f.at) + "." : res.why;
  } catch (_e) { line.textContent = ""; }
}

function titleOfRoom(id) {
  const r = state.rooms.rooms.find((x) => x.id === id);
  return r ? r.name : id;
}

$("roomForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = state.form;
  f.name = $("roomName").value.trim();
  f.topic = $("roomTopic").value.trim();
  let url = "/api/rooms", body;
  if (f.mode === "add") body = { name: f.name, topic: f.topic, size: f.size, skin: f.skin, at: f.at, point: f.point };
  else {
    url = "/api/rooms/" + encodeURIComponent(f.id);
    body = {};
    for (const k of ["name", "topic", "size", "skin"]) if (f[k] !== f.start[k] && (k !== "name" && k !== "topic" || f.renamable)) body[k] = f[k];
    if (!Object.keys(body).length) { $("roomStatus").textContent = "Nothing changed."; return; }
  }
  $("roomSave").disabled = true;
  const res = await postJSON(url, body).catch(() => ({ ok: false, data: {} }));
  $("roomSave").disabled = false;
  if (!res.ok) {
    $("roomStatus").textContent = res.data.why || "Not saved (" + (res.status || "offline") + ").";
    return;
  }
  const name = f.renamable ? f.name : f.start.name;
  closeRooms();
  await load().catch(() => {});
  zoomToRoom(name, true);
});

$("roomDelete").addEventListener("click", () => { $("roomAsk").hidden = false; $("roomAskYes").focus(); });
$("roomAskNo").addEventListener("click", () => { $("roomAsk").hidden = true; });
$("roomAsk").addEventListener("click", (e) => { if (e.target === $("roomAsk")) $("roomAsk").hidden = true; });
$("roomAskYes").addEventListener("click", async () => {
  $("roomAsk").hidden = true;
  const res = await postJSON("/api/rooms/" + encodeURIComponent(state.form.id) + "/delete", {}).catch(() => ({ ok: false, data: {} }));
  if (!res.ok) { $("roomStatus").textContent = res.data.why || "Not deleted (" + (res.status || "offline") + ")."; return; }
  state.form = null;
  await loadRooms();
  paintRoomList();
  $("roomStatus").textContent = "";
  leaveRoom();
  load().catch(() => {});
});

// --- DECIDE.1: decisions waiting on Daniel: seal badge, sheet, the slip over the chat, the notice --------
state.decisions = [];
state.decSeen = null;
state.ask = null;

async function loadDecisions() {
  let data;
  try { data = await getJSON("/api/decisions"); } catch (_e) { return; }
  const rows = data.decisions || [];
  const fresh = state.decSeen ? rows.filter((d) => !state.decSeen.has(d.id)) : [];
  state.decSeen = new Set(rows.map((d) => d.id));
  state.decisions = rows;
  if (state.ask && !rows.some((d) => d.id === state.ask.id)) state.ask = null;
  paintDecisions();
  if (fresh.length) announce(fresh[fresh.length - 1], fresh.length);
}

function asker(from) { return String(from || "").split(":")[0] || "agent"; }

function paintDecisions() {
  const n = state.decisions.length;
  $("decideCount").hidden = !n;
  $("decideCount").textContent = String(n);
  $("decideBtn").classList.toggle("on", n > 0);
  $("decideBtn").title = n ? n + (n > 1 ? " decisions wait" : " decision waits") + " on you" : "No decisions waiting";
  if (!$("decide").hidden) paintDecideSheet();
  paintAsk();
}

function paintDecideSheet() {
  const list = $("decideRows");
  list.replaceChildren();
  if (!state.decisions.length) list.append(el("li", "empty", "Nothing waits on you."));
  for (const d of state.decisions) {
    const li = el("li"), b = el("button");
    b.type = "button";
    const opts = d.options.length ? " \u00b7 " + d.options.map((o) => o.text).join(" / ") : "";
    b.append(el("span", "seal"), el("b", "", d.title), el("span", "q", d.question),
      el("small", "", asker(d.from) + " \u00b7 " + clock(d.ts) + opts));
    b.addEventListener("click", () => { $("decide").hidden = true; openAsk(d); });
    li.append(b);
    list.append(li);
  }
  $("decideNote").textContent = state.writes.writes ? "Tap one to answer it in its chat."
    : "Reading only: answering from the phone is off (Dungeon: Settings \u203a Phone).";
}

async function openAsk(d) {
  state.ask = d;
  const card = state.cards.find((c) => c.id === d.card);
  if (card) { state.sel = card.id; renderTasks(); zoomToRoom(card.room, true); }
  await showChat(d.room, d.chat ? d.title + " \u00b7 chat" : titleOf(d.room));
}

function paintAsk() {
  const d = state.ask, on = !!d && d.room === state.chatKey;
  $("ask").hidden = !on;
  document.body.classList.toggle("asking", on);
  paintComposer(false);
  if (!on) return;
  $("askWho").textContent = asker(d.from) + " asks \u00b7 " + d.title;
  $("askQ").textContent = d.question;
  const opts = $("askOpts");
  opts.replaceChildren();
  for (const o of d.options) {
    const b = el("button");
    b.type = "button";
    b.disabled = !state.writes.writes || state.sending;
    b.append(el("b", "", o.letter), document.createTextNode(o.text));
    b.addEventListener("click", () => answerAsk(o.letter));
    opts.append(b);
  }
  $("askHint").textContent = !state.writes.writes ? "Answering from the phone is off (Dungeon: Settings \u203a Phone)."
    : d.options.length ? "Tap one; what you type below goes with it. Or write your own answer." : "Write your answer below.";
}

async function answerAsk(choice) {
  const d = state.ask;
  if (!d || state.sending) return;
  const text = $("prompt").value.trim(), body = {};
  if (choice) body.choice = choice;
  if (text) body.text = text;
  if (!choice && !text) return;
  state.sending = true;
  paintAsk();
  tone("send");
  const res = await postJSON("/api/decisions/" + d.id, body).catch(() => ({ ok: false, data: {} }));
  state.sending = false;
  if (!res.ok) {
    $("composeHint").textContent = res.data.why || (res.status === 429 ? "Too many sends: wait a minute." : "Not answered (" + (res.status || "offline") + ").");
    paintAsk();
    return;
  }
  $("prompt").value = "";
  growPrompt();
  state.ask = null;
  tone("done");
  if (res.data.sent) state.running = true;
  $("composeHint").textContent = res.data.sent ? "Answered: " + asker(d.from) + " goes on with it here." : "Answered: it is in " + asker(d.from) + "'s inbox.";
  await loadDecisions();
  showChat(res.data.room, $("chatRoom").textContent);
}

// in the page: the notice and the bell; page in the background over https: a system notification
function announce(d, n) {
  tone("decide");
  $("noticeTitle").textContent = (n > 1 ? n + " new decisions \u00b7 " : "New decision \u00b7 ") + d.title;
  $("noticeText").textContent = d.question;
  $("notice").hidden = false;
  state.noticeFor = d.id;
  clearTimeout(state.noticeTimer);
  state.noticeTimer = setTimeout(() => { $("notice").hidden = true; }, 9000);
  if (document.hidden && window.isSecureContext && "Notification" in window && Notification.permission === "granted") {
    try {
      const note = new Notification("Decision \u00b7 " + d.title, { body: d.question, tag: "decide-" + d.id });
      note.onclick = () => { window.focus(); note.close(); openAsk(d); };
    } catch (_e) { /* no system notification on this browser */ }
  }
}

function askPermission() {
  if (!window.isSecureContext || !("Notification" in window) || Notification.permission !== "default") return;
  const asked = Notification.requestPermission();
  if (asked && asked.catch) asked.catch(() => {});
}

$("decideBtn").addEventListener("click", () => { askPermission(); $("decide").hidden = false; paintDecideSheet(); });
$("decideClose").addEventListener("click", () => { $("decide").hidden = true; });
$("decide").addEventListener("click", (e) => { if (e.target === $("decide")) $("decide").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("decide").hidden) $("decide").hidden = true; });
$("notice").addEventListener("click", () => {
  $("notice").hidden = true;
  askPermission();
  const d = state.decisions.find((x) => x.id === state.noticeFor);
  if (d) openAsk(d);
});
$("askClose").addEventListener("click", () => { state.ask = null; paintAsk(); });
// browsers hold sound until the first tap: open the audio then, so a later bell can ring
document.addEventListener("pointerdown", () => {
  try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); } catch (_e) { /* no audio */ }
}, { once: true });

// --- live updates --------------------------------------------------------------------------------
let pending = null;
function live() {
  const src = new EventSource("/api/events");
  src.onopen = () => { $("live").classList.add("on"); loadUpdate(); };
  src.onerror = () => {
    $("live").classList.remove("on");
    if (state.upd && state.upd.running) state.restarting = true;
    if (state.restarting) reconnect(src);
  };
  src.addEventListener("update", (e) => {
    try { paintUpdate(JSON.parse(e.data)); } catch (_e) { /* bad frame */ }
  });
  src.addEventListener("change", () => {
    clearTimeout(pending);
    pending = setTimeout(() => load().catch(() => {}), 150);
  });
  src.addEventListener("avatars", (e) => {
    if (!state.scene) return;
    let data;
    try { data = JSON.parse(e.data); } catch (_e) { return; }
    const fresh = data.avatars.filter((a) => !state.scene.sprites[a.sprite]);
    if (fresh.length) { clearTimeout(pending); pending = setTimeout(() => load().catch(() => {}), 150); }
    setAvatars(data.avatars, performance.now());
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

// a soft blip on send, a low two-note on a reply; same toggle as the zoom chime. The decision bell rings
// unless sound was switched off by hand (DECIDE.1: sound by default).
function tone(kind) {
  if (!soundOn && !(kind === "decide" && localStorage.getItem(soundKey) === null)) return;
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const t = audio.currentTime, out = audio.createGain();
    out.gain.setValueAtTime(0.0001, t);
    out.gain.exponentialRampToValueAtTime(0.05, t + 0.02);
    out.gain.exponentialRampToValueAtTime(0.0001, t + (kind === "build" || kind === "decide" ? 1.1 : 0.45));
    out.connect(audio.destination);
    const notes = kind === "send" ? [[659.25, 0], [987.77, 0.06]] : kind === "done" ? [[523.25, 0], [659.25, 0.09], [783.99, 0.18]]
      : kind === "build" ? [[130.81, 0], [196.0, 0.16], [261.63, 0.34], [392.0, 0.52]]
      : kind === "failed" ? [[329.63, 0], [261.63, 0.12]]
      : kind === "decide" ? [[659.25, 0], [830.61, 0.11], [987.77, 0.22], [1318.5, 0.22]] : [[392.0, 0], [523.25, 0.09]];
    for (const [f, d] of notes) {
      const o = audio.createOscillator();
      o.type = kind === "send" ? "square" : "triangle";
      o.frequency.setValueAtTime(f, t + d);
      const g = audio.createGain();
      g.gain.value = kind === "send" ? 0.35 : 1;
      o.connect(g).connect(out);
      o.start(t + d);
      o.stop(t + (kind === "build" || kind === "decide" ? 1.1 : 0.46));
    }
  } catch (_e) { soundOn = false; paintSound(); }
}

// the keyboard never covers the composer: the app is as tall as the visible viewport
function fitViewport() {
  const vv = window.visualViewport;
  if (vv) document.documentElement.style.setProperty("--app-h", Math.round(vv.height) + "px");
}
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", fitViewport);
  fitViewport();
}

$("fit").addEventListener("click", leaveRoom);
paintSound();
load().then(loadUpdate).then(live).catch(() => {});
requestAnimationFrame(frame);
