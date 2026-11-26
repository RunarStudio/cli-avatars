// PHONEFIX evidence: starts tools/shot_phone_map.py (made-up data on 127.0.0.1) and shoots headless, muted Chrome at
// 360 and 400 px: phone-360.png, phone-400.png and the 400 px header strip header-<label>.png into <out dir>.
//   NODE_PATH=<global node_modules> node tools/shot_phone_header.js <out dir> [label]
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

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

(async () => {
  const [dir, label = "now"] = process.argv.slice(2);
  const out = path.resolve(dir);
  const { server, url } = await serve();
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    for (const width of [360, 400]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, deviceScaleFactor: 3, hasTouch: true, isMobile: true });
      const page = await ctx.newPage();
      await page.goto(url);
      await page.waitForFunction(() => state.scene && state.map && state.walkers.size >= 6);
      await page.waitForTimeout(900);
      await page.screenshot({ path: path.join(out, `phone-${width}.png`) });
      if (width === 400) {
        const bar = await page.locator(".map-pane > .bar").boundingBox();
        await page.screenshot({ path: path.join(out, `header-${label}.png`), clip: { x: 0, y: 0, width, height: bar.y + bar.height + 70 } });
      }
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.stdin.end();
  }
})();
