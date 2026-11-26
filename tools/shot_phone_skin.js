// PHONESKIN evidence: starts tools/shot_phone_map.py --writes (made-up data on 127.0.0.1) and drives headless, muted
// Chrome with touch at 400 px: tap a room, its edit button, scroll the sheet, swipe the skins, tap one, Save; the map
// behind stays still while the picker is open. Writes skin-picker.gif (ffmpeg) and phone-400.png into <out dir>.
//   NODE_PATH=<global node_modules> node tools/shot_phone_skin.js <out dir>
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
  const server = spawn("python3", [path.join(__dirname, "shot_phone_map.py"), "--writes"], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  return { server, url };
}

let id = 0;  // a fresh id per touch
async function touch(cdp, type, pts) {
  await cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y]) => ({ x, y, id })) });
}
async function tap(page, cdp, at) {
  id++;
  await touch(cdp, "touchStart", [at]);
  await page.waitForTimeout(60);
  await touch(cdp, "touchEnd", []);
}
async function drag(page, cdp, from, to, steps) {
  id++;
  await touch(cdp, "touchStart", [from]);
  for (let i = 1; i <= steps; i++) {
    await touch(cdp, "touchMove", [[from[0] + (to[0] - from[0]) * i / steps, from[1] + (to[1] - from[1]) * i / steps]]);
    await page.waitForTimeout(16);
  }
  await page.waitForTimeout(150);
  await touch(cdp, "touchEnd", []);
}
async function click(page, cdp, sel) {
  const b = await page.locator(sel).first().boundingBox();
  await tap(page, cdp, [b.x + b.width / 2, b.y + b.height / 2]);
}
const room = (page, name) => page.evaluate((n) => {
  const b = canvas.getBoundingClientRect(), v = state.view, r = state.scene.rooms.find((q) => q.name === n);
  const cx = r.poly.reduce((a, p) => a + p[0], 0) / 4, cy = r.poly.reduce((a, p) => a + p[1], 0) / 4;
  const [x, y] = [cx + (r.poly[3][0] - cx) * 0.45, cy + (r.poly[3][1] - cy) * 0.45];
  return [b.left + v.x + x * v.s, b.top + v.y + y * v.s];
}, name);

(async () => {
  const out = path.resolve(process.argv[2]);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "phoneskin-shot-"));
  const { server, url } = await serve();
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    const size = { width: 400, height: 860 };
    const ctx = await browser.newContext({ viewport: size, deviceScaleFactor: 3, hasTouch: true, isMobile: true, recordVideo: { dir: tmp, size } });
    await ctx.addInitScript(() => localStorage.setItem("cli-avatars-map-hint", "1"));
    await ctx.addInitScript(FINGERS);
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await page.goto(url);
    await page.waitForFunction(() => state.fitted && state.walkers.size >= 6 && !document.getElementById("mapTools").hidden);
    await page.waitForTimeout(1500);
    await tap(page, cdp, await room(page, "moon-forge"));
    await page.waitForTimeout(1600);
    await click(page, cdp, "#editRoom");
    await page.waitForFunction(() => !document.getElementById("rooms").hidden && state.form);
    await page.waitForTimeout(1200);
    const card = await page.locator("#rooms .sheet-card").boundingBox();
    await drag(page, cdp, [200, card.y + card.height - 60], [200, card.y + 140], 20);
    await page.waitForTimeout(900);
    const strip = await page.locator("#skins").boundingBox();
    await drag(page, cdp, [strip.x + strip.width - 30, strip.y + 60], [strip.x + 40, strip.y + 60], 20);
    await page.waitForTimeout(900);
    const pick = await page.evaluate(() => {
      const s = document.getElementById("skins").getBoundingClientRect(), v = document.querySelector("#rooms .sheet-body").getBoundingClientRect();
      const b = [...document.querySelectorAll("#skins button")].reverse().find((n) => {
        const r = n.getBoundingClientRect();
        return n.dataset.skin !== state.form.skin && r.left >= s.left && r.right <= s.right && r.top >= v.top && r.bottom <= v.bottom;
      });
      const r = b.getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    });
    await tap(page, cdp, pick);
    await page.waitForTimeout(1300);
    await page.screenshot({ path: path.join(out, "phone-400.png") });
    await drag(page, cdp, [200, card.y + card.height - 60], [200, card.y + 140], 20);
    await page.waitForTimeout(700);
    await click(page, cdp, "#roomSave");
    await page.waitForFunction(() => document.getElementById("rooms").hidden);
    await page.waitForTimeout(2200);
    const video = await page.video().path();
    await ctx.close();
    execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", video, "-vf",
      "fps=9,split[a][b];[a]palettegen=max_colors=80:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
      path.join(out, "skin-picker.gif")]);
    for (const f of ["skin-picker.gif", "phone-400.png"]) console.log(f, fs.statSync(path.join(out, f)).size);
  } finally {
    await browser.close();
    server.stdin.end();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
