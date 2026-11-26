// PHONECLEAN: headless, muted Chrome with touch opens the paired phone URL at each width on a fresh profile and prints,
// per width, the first-open hint, the boxes drawn on the map and the controls over it, running looped animations,
// idle redraws, the scale in device pixels, and what the zoom, Whole map and hint buttons do (JSON on stdout).
//   NODE_PATH=<global node_modules> node tools/probe_phone_clean.js <pair url> <width>...
"use strict";
const { chromium } = require("playwright");

const settled = (page) => page.waitForFunction(() => state.fitted && !state.anim && !state.dirty);

async function probe(browser, url, width) {
  const phone = width < 1024;
  const ctx = await browser.newContext({ viewport: { width, height: 800 }, deviceScaleFactor: phone ? 3 : 1, hasTouch: phone, isMobile: phone });
  const page = await ctx.newPage();
  await page.goto(url);
  await page.waitForFunction(() => state.scene && state.map && !document.getElementById("mapTools").hidden);
  await page.evaluate(() => document.fonts.ready);
  await settled(page);
  const seen = (id) => page.evaluate((i) => { const n = document.getElementById(i); return !!n && n.getClientRects().length > 0 && getComputedStyle(n).visibility !== "hidden"; }, id);
  const hint = await page.evaluate(() => { const n = document.getElementById("mapHint"); return n && !n.hidden ? n.innerText : ""; });
  const legendInHint = await page.evaluate(() => document.querySelectorAll("#mapHintTiers li").length);
  if (await seen("mapHintOk")) await page.tap("#mapHintOk");
  const drawn = await page.evaluate(() => state.draws);
  await page.waitForFunction((t) => state.draws > t, drawn);
  const found = await page.evaluate(() => {
    const c = document.getElementById("map").getBoundingClientRect();
    const marks = (state.marks || []).map((m) => ({ kind: m.kind, left: c.left + m.left, top: c.top + m.top, right: c.left + m.right, bottom: c.top + m.bottom }));
    for (const r of state.tierLegend || []) marks.push({ kind: "legend", left: c.left + r.left, top: c.top + r.top, right: c.left + r.right, bottom: c.top + r.bottom });
    const tools = [...document.querySelectorAll(".stage button, .stage canvas.mini")]
      .filter((n) => n.getClientRects().length && getComputedStyle(n).visibility !== "hidden")
      .map((n) => { const r = n.getBoundingClientRect(); return { kind: "tool:" + (n.id || n.className), left: r.left, top: r.top, right: r.right, bottom: r.bottom }; });
    const loops = document.getAnimations().filter((a) => a.playState === "running" && a.effect && a.effect.getTiming().iterations === Infinity)
      .map((a) => (a.effect.target.id || a.effect.target.className) + ":" + a.animationName);
    return { marks, tools, loops, scale: state.view.s * devicePixelRatio, whole: state.view.s / wholeMap().s,
      full: document.getElementById("mapFull").innerText.trim(), rooms: document.getElementById("mapRooms").innerText.trim() };
  });
  const d0 = await page.evaluate(() => state.draws);
  await page.waitForTimeout(2000);
  const idle = (await page.evaluate(() => state.draws)) - d0;
  const mini = await seen("mini");
  const out = { width, hint, legendInHint, ...found, idle, mini, zoom: {} };
  for (const id of ["mapIn", "mapOut", "mapHelp"]) out.zoom[id] = await seen(id);
  if (phone && out.zoom.mapIn) {
    const s0 = await page.evaluate(() => state.view.s);
    await page.tap("#mapIn");
    await settled(page);
    out.zoom.inRatio = (await page.evaluate(() => state.view.s)) / s0;
    out.zoom.inScale = await page.evaluate(() => state.view.s * devicePixelRatio);
    out.zoom.miniIn = await seen("mini");
    await page.tap("#mapOut");
    await settled(page);
    out.zoom.outRatio = (await page.evaluate(() => state.view.s)) / s0;
    await page.tap("#mapIn");
    await settled(page);
    await page.tap("#mapHome");
    await settled(page);
    out.zoom.homeRatio = (await page.evaluate(() => state.view.s)) / s0;
    await page.reload();
    await page.waitForFunction(() => state.scene && state.map && !document.getElementById("mapTools").hidden);
    await settled(page);
    out.hintAfterReload = await seen("mapHint");
    await page.tap("#mapHelp");
    out.hintAgain = await seen("mapHint");
  }
  await ctx.close();
  return out;
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
