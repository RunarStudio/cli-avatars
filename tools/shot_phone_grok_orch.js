// GROK-ORCH.1 evidence on the phone: starts `tools/shot_grok_orch.py --serve` (made-up data, writes on, 127.0.0.1,
// the Grok stub pinned only) and opens the Grok chats sheet in headless, muted Chrome at 400 px: the list grouped by
// project, newest first. Writes phone-400.png into <out-dir>.
//   NODE_PATH=<global node_modules> xvfb-run -a node tools/shot_phone_grok_orch.js <out-dir>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const outDir = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_grok_orch.py"), "--serve"],
    { stdio: ["pipe", "pipe", "inherit"] });
  let said = "";
  const url = await new Promise((ok) => server.stdout.on("data", (d) => {
    said += d;
    const found = said.match(/^http:\/\/127\.0\.0\.1:\d+\/pair\?t=\S+$/m);
    if (found) ok(found[0]);
  }));
  const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--mute-audio"] });
  try {
    const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 1 });
    await page.goto(url);
    await page.waitForFunction(() => state.scene && state.map && state.writes.writes);
    await page.evaluate(() => showChat("chat-2", "Wick sizes"));
    await page.locator("#grokOpen").scrollIntoViewIfNeeded();
    await page.click("#grokOpen");
    await page.waitForSelector("#grokSheet li.grok-project");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(outDir, "phone-400.png") });
    console.log("projects:", JSON.stringify(await page.$$eval("#grokSheet li.grok-project", (l) => l.map((x) => x.textContent))));
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
