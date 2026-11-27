// STATUSCOLOR evidence: the phone's Active bots list at 400 px on tools/shot_phone_map.py's made-up data, after two
// bots change state live (their chips repaint and pulse). Headless, muted Chrome. Writes status-400.png into <out dir>.
//   NODE_PATH=<global node_modules> node tools/shot_status_phone.js <out dir>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_phone_map.py")], { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 3, hasTouch: true,
      isMobile: true });
    await page.goto(url);
    await page.waitForFunction(() => state.scene && state.map && state.walkers.size >= 6);
    if (await page.locator("#mapHintOk").isVisible()) await page.locator("#mapHintOk").click();
    await page.locator("#botsChip").click();
    await page.waitForTimeout(600);
    const pulsed = await page.evaluate(() => {
      const list = [...state.walkers.values()].map((w) => ({ ...w.a }));
      for (const a of list) {
        if (a.name === "Scout") a.state = "subagent";
        if (a.name === "Bram") a.state = "error";
      }
      setAvatars(list, performance.now());
      return [...document.querySelectorAll(".pm-state.pulse")].map((c) => c.textContent);
    });
    console.log("pulsed:", pulsed.join(", "));
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(out, "status-400.png") });
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
