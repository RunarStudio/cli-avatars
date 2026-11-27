// Phone view at 400 px with real touch (CDP) in headless, muted Chrome against the running app (loopback only).
//   NODE_PATH=<dir with playwright> node phone_touch.js <pair-url> <out-dir> <changes|walk>
// Records the page (Playwright video), then writes <out-dir>/f00000.png… at 25 fps and frames.json (seconds since
// this script started, per frame). Finger dots show each touch.
"use strict";
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const FINGERS = `addEventListener("DOMContentLoaded", () => {
  const dots = new Map();
  const put = (e) => { if (e.pointerType !== "touch") return; let d = dots.get(e.pointerId);
    if (!d) { d = document.createElement("i"); d.style.cssText = "position:fixed;z-index:9999;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;background:rgba(255,255,255,.35);border:2px solid #fff;pointer-events:none"; document.body.append(d); dots.set(e.pointerId, d); }
    d.style.left = e.clientX + "px"; d.style.top = e.clientY + "px"; };
  addEventListener("pointerdown", put, true); addEventListener("pointermove", put, true);
  const off = (e) => { const d = dots.get(e.pointerId); if (d) setTimeout(() => d.remove(), 160); dots.delete(e.pointerId); };
  addEventListener("pointerup", off, true); addEventListener("pointercancel", off, true);
});`;

const FPS = 25;
const t0 = Date.now();
const wait = (page, ms) => page.waitForTimeout(ms);

async function touch(cdp, type, pts) {
  await cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
}
async function tap(page, cdp, [x, y]) {
  await touch(cdp, "touchStart", [[x, y]]);
  await wait(page, 70);
  await touch(cdp, "touchEnd", []);
}
async function drag(page, cdp, from, to, steps) {
  await touch(cdp, "touchStart", [from]);
  for (let i = 1; i <= steps; i++) {
    const k = i / steps, e = k * k * (3 - 2 * k);
    await touch(cdp, "touchMove", [[from[0] + (to[0] - from[0]) * e, from[1] + (to[1] - from[1]) * e]]);
    await wait(page, 22);
  }
  await touch(cdp, "touchEnd", []);
}
async function pinch(page, cdp, c, d0, d1, steps) {
  for (let i = 0; i <= steps; i++) {
    const d = d0 + (d1 - d0) * i / steps, pts = [[c[0] - d / 2, c[1]], [c[0] + d / 2, c[1]]];
    await touch(cdp, i ? "touchMove" : "touchStart", pts);
    await wait(page, 22);
  }
  await touch(cdp, "touchEnd", []);
}
async function press(page, cdp, sel) {
  const el = page.locator(sel).first();
  if (!(await el.count()) || !(await el.isVisible())) return false;
  await el.scrollIntoViewIfNeeded();
  const b = await el.boundingBox();
  await tap(page, cdp, [b.x + b.width / 2, b.y + b.height / 2]);
  return true;
}
const roomAt = (page, name) => page.evaluate((n) => {
  const r = state.scene.rooms.find((x) => x.name === n), b = canvas.getBoundingClientRect(), v = state.view;
  if (!r) return null;
  const cx = r.poly.reduce((a, p) => a + p[0], 0) / 4, cy = r.poly.reduce((a, p) => a + p[1], 0) / 4;
  return [b.left + v.x + cx * v.s, b.top + v.y + cy * v.s];
}, name);
// a tap on a room (or a bot); the sheet opens by the page's own call when the tap missed it
async function openRoom(page, cdp, name) {
  const at = await roomAt(page, name);
  if (at) await tap(page, cdp, at);
  await wait(page, 500);
  if (!(await page.locator("#drawer").isVisible())) {
    await page.evaluate((n) => openRoomSheet(state.scene.rooms.find((r) => r.name === n)), name);
  }
}
async function openBotSheet(page, cdp, name) {
  const at = await botAt(page, name);
  if (at) await tap(page, cdp, at);
  await wait(page, 500);
  if (!(await page.locator("#drawer").isVisible())) {
    await page.evaluate((n) => openBot([...state.walkers.values()].find((x) => x.a.name === n).a), name);
  }
}
const botAt = (page, name) => page.evaluate((n) => {
  const w = [...state.walkers.values()].find((x) => x.a.name === n), b = canvas.getBoundingClientRect(), v = state.view;
  if (!w) return null;
  const [x, y] = place(w, performance.now());
  return [b.left + v.x + x * v.s, b.top + v.y + (y - 12) * v.s];
}, name);

async function changes(page, cdp) {
  await wait(page, 2600); // the once-only hint
  await press(page, cdp, "#mapHintOk");
  await wait(page, 1200);
  await drag(page, cdp, [220, 300], [140, 240], 30);
  await wait(page, 600);
  await pinch(page, cdp, [200, 280], 70, 220, 30);
  await wait(page, 1000);
  await openRoom(page, cdp, "moon-forge");
  await wait(page, 2200);
  await press(page, cdp, "#drawerClose");
  await wait(page, 600);
  await press(page, cdp, "#mapRooms");
  await wait(page, 1300);
  await press(page, cdp, ".pm-place >> text=Glass garden");
  await wait(page, 1600);
  await openBotSheet(page, cdp, "Vessa");
  await wait(page, 2400);
  await press(page, cdp, "#drawerClose");
  await wait(page, 600);
  await press(page, cdp, "#memoryBtn");
  await wait(page, 2600);
  await press(page, cdp, "#memoryClose");
  await wait(page, 500);
}

async function walk(page, cdp) {
  await wait(page, 1800);
  await press(page, cdp, "#mapHintOk");
  await wait(page, 900);
  await pinch(page, cdp, [200, 280], 80, 200, 26);
  await wait(page, 900);
  await openRoom(page, cdp, "glass-garden");
  await wait(page, 2000);
  await press(page, cdp, "#drawerClose");
  await wait(page, 500);
  await press(page, cdp, "#mapRooms");
  await wait(page, 1100);
  await press(page, cdp, ".pm-place >> text=Moon forge");
  await wait(page, 1800);
  await press(page, cdp, "#memoryBtn");
  await wait(page, 2400);
  await press(page, cdp, "#memoryClose");
  await wait(page, 800);
}

(async () => {
  const [url, out, kind] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  const raw = path.join(out, "video");
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio", "--no-proxy-server"] });
  let start = 0;
  try {
    const ctx = await browser.newContext({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2, hasTouch: true,
      isMobile: true, recordVideo: { dir: raw, size: { width: 400, height: 860 } } });
    await ctx.addInitScript(FINGERS);
    const page = await ctx.newPage();
    start = (Date.now() - t0) / 1000;
    const cdp = await ctx.newCDPSession(page);
    await page.goto(url);
    await page.waitForFunction(() => typeof state !== "undefined" && state.scene && state.map, null, { timeout: 20000 });
    await (kind === "walk" ? walk : changes)(page, cdp);
    const video = await page.video().path();
    await ctx.close();
    execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", video, "-vf", `fps=${FPS}`, path.join(out, "f%05d.png")]);
  } finally {
    await browser.close();
  }
  const frames = fs.readdirSync(out).filter((f) => /^f\d{5}\.png$/.test(f)).sort();
  for (const [i, f] of frames.entries()) fs.renameSync(path.join(out, f), path.join(out, `f${String(i).padStart(5, "0")}.png`));
  fs.writeFileSync(path.join(out, "frames.json"), JSON.stringify(frames.map((_f, i) => start + i / FPS)));
  fs.rmSync(raw, { recursive: true, force: true });
})().catch((e) => { console.error(e); process.exit(1); });
