// PARK.1 + PROJECTS.1 evidence on the phone: starts tools/shot_phone_park.py (made-up data on 127.0.0.1), opens the
// map at 400 px in headless, muted Chrome, zooms to the park (lights, fireflies, who idles where, task tables) and
// shoots it, then opens the Projects sheet, expands Lantern and shoots that.
//   CLI_AVATARS_DATA_DIR=<temp dir> NODE_PATH=<node_modules with playwright> node tools/shot_phone_park.js <out-dir>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_phone_park.py")], { stdio: ["pipe", "pipe", "inherit"] });
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
    await page.waitForFunction(() => state.scene && state.map && state.walkers.size >= 6 && state.scene.park);
    await page.evaluate(() => zoomToRoom("Park", true));
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(out, "phone-400.png") });
    await page.evaluate(() => zoomToRoom("glass-orchard", true));
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(out, "phone-tables-400.png") });
    await page.click("#projectsBtn");
    await page.waitForSelector(".pj-row");
    await page.click(".pj-row .pj-head");
    await page.waitForSelector(".pj-details");
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(out, "phone-projects-400.png") });
    console.log(out);
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
