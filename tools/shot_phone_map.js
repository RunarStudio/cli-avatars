// PHONEMAP evidence: starts tools/shot_phone_map.py (made-up data on 127.0.0.1) and drives headless, muted Chrome
// with touch at 400 px: drag, pinch, jump to a room, tap a room, tap a bot, Active bots. Writes phone-map.gif (from
// the recorded video, ffmpeg), phone-400.png, phone-768.png and desktop-1366.png into <out dir>.
//   NODE_PATH=<global node_modules> node tools/shot_phone_map.js <out dir>
"use strict";
const { spawn, execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

// finger dots so the recording shows the touches
const FINGERS = `addEventListener("DOMContentLoaded", () => {
  const dots = new Map();
  const put = (e) => { if (e.pointerType !== "touch") return; let d = dots.get(e.pointerId);
    if (!d) { d = document.createElement("i"); d.style.cssText = "position:fixed;z-index:99;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;background:rgba(255,255,255,.35);border:2px solid #fff;pointer-events:none"; document.body.append(d); dots.set(e.pointerId, d); }
    d.style.left = e.clientX + "px"; d.style.top = e.clientY + "px"; };
  addEventListener("pointerdown", put, true); addEventListener("pointermove", put, true);
  const off = (e) => { const d = dots.get(e.pointerId); if (d) setTimeout(() => d.remove(), 120); dots.delete(e.pointerId); };
  addEventListener("pointerup", off, true); addEventListener("pointercancel", off, true);
});`;

async function serve() {
  const server = spawn("python3", [path.join(__dirname, "shot_phone_map.py")], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  return { server, url };
}

// the map is up and the once-only how-to hint (PHONECLEAN) is closed: it covers the map and takes every tap
async function ready(page) {
  await page.waitForFunction(() => state.scene && state.map && state.walkers.size >= 6);
  if (await page.locator("#mapHintOk").isVisible()) await page.locator("#mapHintOk").click();
  await page.waitForTimeout(900);
}

// screen point of a map point, or of a room's floor centre, or of a bot's body
const roomAt = (page, name) => page.evaluate((n) => {
  const r = state.scene.rooms.find((x) => x.name === n), b = canvas.getBoundingClientRect(), v = state.view;
  const cx = r.poly.reduce((a, p) => a + p[0], 0) / 4, cy = r.poly.reduce((a, p) => a + p[1], 0) / 4;
  const [x, y] = [cx + (r.poly[3][0] - cx) * 0.45, cy + (r.poly[3][1] - cy) * 0.45];
  return [b.left + v.x + x * v.s, b.top + v.y + y * v.s];
}, name);
const botAt = (page, name) => page.evaluate((n) => {
  const w = [...state.walkers.values()].find((x) => x.a.name === n), b = canvas.getBoundingClientRect(), v = state.view;
  const [x, y] = place(w, performance.now());
  return [b.left + v.x + x * v.s, b.top + v.y + (y - 12) * v.s];
}, name);

async function touch(cdp, type, pts) {
  await cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
}
async function tap(page, cdp, [x, y]) {
  await touch(cdp, "touchStart", [[x, y]]);
  await page.waitForTimeout(60);
  await touch(cdp, "touchEnd", []);
}
async function drag(page, cdp, from, to, steps) {
  await touch(cdp, "touchStart", [from]);
  for (let i = 1; i <= steps; i++) {
    const k = i / steps;
    await touch(cdp, "touchMove", [[from[0] + (to[0] - from[0]) * k, from[1] + (to[1] - from[1]) * k]]);
    await page.waitForTimeout(16);
  }
  await touch(cdp, "touchEnd", []);
}
async function pinch(page, cdp, c, d0, d1, steps) {
  for (let i = 0; i <= steps; i++) {
    const d = d0 + (d1 - d0) * i / steps, pts = [[c[0] - d / 2, c[1]], [c[0] + d / 2, c[1]]];
    await touch(cdp, i ? "touchMove" : "touchStart", pts);
    await page.waitForTimeout(16);
  }
  await touch(cdp, "touchEnd", []);
}
async function click(page, cdp, sel) {
  await page.locator(sel).first().scrollIntoViewIfNeeded();
  const b = await page.locator(sel).first().boundingBox();
  await tap(page, cdp, [b.x + b.width / 2, b.y + b.height / 2]);
}

(async () => {
  const out = path.resolve(process.argv[2]);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "phonemap-shot-"));
  const { server, url } = await serve();
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    const phone = { viewport: { width: 400, height: 860 }, deviceScaleFactor: 3, hasTouch: true, isMobile: true };
    const ctx = await browser.newContext({ ...phone, recordVideo: { dir: tmp, size: { width: 400, height: 860 } } });
    await ctx.addInitScript(FINGERS);
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await page.goto(url);
    await ready(page);
    await click(page, cdp, "#mapFull");
    await page.waitForTimeout(700);
    await drag(page, cdp, [200, 420], [110, 330], 24);
    await page.waitForTimeout(500);
    await pinch(page, cdp, [200, 420], 80, 230, 26);
    await page.waitForTimeout(700);
    await click(page, cdp, "#mapRooms");
    await page.waitForTimeout(900);
    await click(page, cdp, ".pm-place >> text=Glass orchard");
    await page.waitForTimeout(1000);
    await click(page, cdp, "#mapHome");
    await page.waitForTimeout(900);
    await tap(page, cdp, await roomAt(page, "moon-forge"));
    await page.waitForTimeout(1600);
    await page.screenshot({ path: path.join(out, "phone-400.png") });
    await click(page, cdp, "#drawerClose");
    await page.waitForTimeout(800);
    await tap(page, cdp, await botAt(page, "Quill"));
    await page.waitForTimeout(1800);
    await click(page, cdp, "#drawerClose");
    await page.waitForTimeout(400);
    await click(page, cdp, "#botsChip");
    await page.waitForTimeout(1000);
    await click(page, cdp, ".pm-bot >> text=Owl");
    await page.waitForTimeout(1800);
    await click(page, cdp, "#mapHome");
    await page.waitForTimeout(1200);
    const video = await page.video().path();
    await ctx.close();
    execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", video, "-vf",
      "fps=9,split[a][b];[a]palettegen=max_colors=80:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
      path.join(out, "phone-map.gif")]);

    for (const [name, opts, act] of [
      ["phone-768.png", { viewport: { width: 768, height: 1024 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true }, "room"],
      ["desktop-1366.png", { viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 }, "bot"]]) {
      const c = await browser.newContext(opts);
      const p = await c.newPage();
      await p.goto(url);
      await ready(p);
      if (act === "room") await p.evaluate(() => openRoomSheet(state.scene.rooms.find((r) => r.name === "glass-orchard")));
      else await p.evaluate(() => { const w = [...state.walkers.values()].find((x) => x.a.name === "Owl"); glideToBot(w.a); setTimeout(() => openBot(w.a), 700); });
      await p.waitForTimeout(1800);
      await p.screenshot({ path: path.join(out, name) });
      await c.close();
    }
    for (const f of fs.readdirSync(out)) console.log(f, fs.statSync(path.join(out, f)).size);
  } finally {
    await browser.close();
    server.stdin.end();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
