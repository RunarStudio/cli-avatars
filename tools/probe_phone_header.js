// PHONEFIX: headless, muted Chrome opens the paired phone URL at each width and prints, per width, every visible
// header control of the map pane with its box and whether a tap on its centre lands on it (JSON on stdout).
//   NODE_PATH=<global node_modules> node tools/probe_phone_header.js <pair url> <width>...
"use strict";
const { chromium } = require("playwright");

async function probe(browser, url, width) {
  const ctx = await browser.newContext({ viewport: { width, height: 860 }, deviceScaleFactor: 1, hasTouch: true, isMobile: width < 1024 });
  await ctx.addInitScript(() => localStorage.setItem("cli-avatars-map-hint", "1"));  // PHONECLEAN: the hint seen
  const page = await ctx.newPage();
  await page.goto(url);
  await page.waitForFunction(() => state.scene && state.map && !document.getElementById("mapTools").hidden);
  await page.evaluate(() => document.fonts.ready);
  const found = await page.evaluate(() => {
    const box = (el) => {
      const r = el.getBoundingClientRect(), hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { id: el.id || el.className, left: r.left, right: r.right, top: r.top, bottom: r.bottom, hit: !!hit && el.contains(hit),
        over: hit && !el.contains(hit) ? (hit.id || hit.className) : "" };
    };
    const controls = [...document.querySelectorAll(".map-pane > .bar button")]
      .filter((el) => el.getClientRects().length && getComputedStyle(el).visibility !== "hidden").map(box);
    return { controls, home: box(document.getElementById("mapHome")) };
  });
  await ctx.close();
  return { width, ...found };
}

(async () => {
  const [url, ...widths] = process.argv.slice(2);
  const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  try {
    const out = [];
    for (const w of widths) out.push(await probe(browser, url, Number(w)));
    process.stdout.write(JSON.stringify(out));
  } finally {
    await browser.close();
  }
})();
