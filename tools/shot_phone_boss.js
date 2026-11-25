// BACKLOG-BOSS evidence on the phone: starts tools/shot_phone_boss.py (made-up data on 127.0.0.1), opens the map at
// 400 px in headless, muted Chrome, zooms to the oni's pit, then taps it open: HP, the week's burn-down, the tasks.
//   NODE_PATH=<global node_modules> node tools/shot_phone_boss.js <out.png>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_phone_boss.py")], { stdio: ["pipe", "pipe", "inherit"] });
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
    await page.waitForFunction(() => state.scene && state.map && state.scene.boss && state.sprites[state.scene.boss.sprite]);
    await page.evaluate(() => zoomToRoom("Apothecary"));
    await page.waitForTimeout(2000);
    await page.screenshot({ path: out.replace(/\.png$/, "-map.png") });
    await page.evaluate(() => openBoss());
    await page.waitForTimeout(600);
    await page.screenshot({ path: out });
    console.log(out);
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
