// BUGFIX: headless, muted Chrome opens the paired phone URL at each width and prints, per width, each row of the map's
// tier legend with its box on the page and what a tap on a 5×3 grid of its points lands on (JSON on stdout).
// --shot=<dir> also saves the stage as legend-<width>.png.
//   NODE_PATH=<global node_modules> node tools/probe_tier_legend.js <pair url> [--shot=<dir>] <width>...
"use strict";
const path = require("path");
const { chromium } = require("playwright");

async function probe(browser, url, width, shot) {
  const ctx = await browser.newContext({ viewport: { width, height: 860 }, deviceScaleFactor: 1, hasTouch: true, isMobile: width < 1024 });
  const page = await ctx.newPage();
  await page.goto(url);
  await page.waitForFunction(() => state.scene && state.map && !document.getElementById("mapTools").hidden);
  await page.evaluate(() => document.fonts.ready);
  const drawn = await page.evaluate(() => state.drawn || 0);
  await page.waitForFunction((t) => state.drawn > t && (innerWidth < 1024 || (state.tierLegend || []).length === 4), drawn);
  const found = await page.evaluate(() => {
    const c = document.getElementById("map").getBoundingClientRect();
    const rows = state.tierLegend.map((r) => {
      const box = { left: c.left + r.left, right: c.left + r.right, top: c.top + r.top, bottom: c.top + r.bottom };
      const over = new Set();
      for (const fx of [0.02, 0.25, 0.5, 0.75, 0.98]) for (const fy of [0.15, 0.5, 0.85]) {
        const hit = document.elementFromPoint(box.left + (box.right - box.left) * fx, box.top + (box.bottom - box.top) * fy);
        if (!hit || hit.id !== "map") over.add(hit ? hit.id || hit.className || hit.tagName : "nothing");
      }
      return { ...box, over: [...over] };
    });
    return { canvas: { left: c.left, right: c.right, top: c.top, bottom: c.bottom }, rows };
  });
  if (shot) await page.locator(".stage").screenshot({ path: path.join(shot, `legend-${width}.png`) });
  await ctx.close();
  return { width, ...found };
}

(async () => {
  const args = process.argv.slice(2), url = args.shift();
  const shot = (args.find((a) => a.startsWith("--shot=")) || "").slice(7);
  const widths = args.filter((a) => !a.startsWith("--")).map(Number);
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    const out = [];
    for (const w of widths) out.push(await probe(browser, url, w, shot));
    process.stdout.write(JSON.stringify(out));
  } finally {
    await browser.close();
  }
})();
