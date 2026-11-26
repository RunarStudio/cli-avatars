// BOSS-ROOM.1 evidence on the phone: starts tools/shot_phone_boss_room.py (made-up data on 127.0.0.1), opens the map
// at 400 px in headless, muted Chrome, frames the Oni Pit and the Crypt (<out>-map.png), then taps the Crypt open:
// its forgotten cards (<out>).
//   NODE_PATH=<global node_modules> node tools/shot_phone_boss_room.js <out.png>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_phone_boss_room.py")], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio"] });
  try {
    const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2 });
    await page.goto(url);
    await page.waitForFunction(() => state.scene && state.map && state.scene.boss && state.scene.boss.crypt
      && state.scene.boss.crypt.count > 0 && state.scene.boss.stage >= 2 && state.sprites[state.scene.boss.sprite]);
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      const b = state.scene.boss, pts = [...b.pit_poly, ...b.crypt.poly];
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const box = [Math.min(...xs), Math.min(...ys) - 60, Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys) + 160];
      animateTo(fitView(box, 1));
    });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: out.replace(/\.png$/, "-map.png") });
    await page.evaluate(() => openCrypt());
    await page.waitForTimeout(600);
    await page.screenshot({ path: out });
    console.log(out);
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
