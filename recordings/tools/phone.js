// Phone view at 400 px in headless, muted Chrome against the running app (loopback only); one PNG per frame.
//   NODE_PATH=<dir with playwright> node phone.js <pair-url> <out-dir> <demo|tutorial>
// Writes <out-dir>/f00000.png… and <out-dir>/frames.json (time of each frame in seconds).
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const [url, out, kind] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio", "--no-proxy-server"] });
  const times = [];
  let shooting = true;
  const t0 = Date.now();
  try {
    const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2 });
    await page.goto(url);
    await page.waitForFunction(() => typeof state !== "undefined" && state.scene && state.map, null, { timeout: 20000 });
    await page.waitForTimeout(1500);
    const shoot = (async () => {
      let n = 0;
      while (shooting) {
        const t = (Date.now() - t0) / 1000;
        await page.screenshot({ path: path.join(out, `f${String(n).padStart(5, "0")}.png`) });
        times.push(t);
        n += 1;
      }
    })();
    const tap = async (sel) => { const el = page.locator(sel).first(); if (await el.count()) await el.click({ timeout: 3000 }).catch(() => {}); };
    await page.waitForTimeout(2500);
    await tap("#tasks li");
    await page.waitForTimeout(2500);
    await page.evaluate(() => document.querySelector("#taskView").scrollIntoView({ behavior: "smooth", block: "start" }));
    await page.waitForTimeout(1200);
    await tap('#taskView button[data-view="board"]');
    await page.waitForTimeout(1800);
    if (kind === "tutorial") {
      await page.evaluate(() => { const l = document.querySelector("#lanes"); if (l) l.scrollBy({ left: l.clientWidth, behavior: "smooth" }); });
      await page.waitForTimeout(1800);
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
      await page.waitForTimeout(1200);
      await tap("#decideBtn");
      await page.waitForTimeout(2500);
    } else {
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
      await page.waitForTimeout(1200);
    }
    shooting = false;
    await shoot;
  } finally {
    fs.writeFileSync(path.join(out, "frames.json"), JSON.stringify(times));
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
