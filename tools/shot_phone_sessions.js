// CHAT-CTX.1 evidence on the phone: starts tools/shot_chat_context.py serve (made-up data on 127.0.0.1), picks the task
// at 400 px in headless, muted Chrome: its chats, then its CLI sessions (Claude, Grok, Cursor), read-only.
//   NODE_PATH=<global node_modules> node tools/shot_phone_sessions.js <out.png>
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const out = path.resolve(process.argv[2]);
  const server = spawn("python3", [path.join(__dirname, "shot_chat_context.py"), "serve"],
    { stdio: ["pipe", "pipe", "inherit"] });
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
    await page.waitForFunction(() => [...document.querySelectorAll("#tasks button.task")]
      .some((b) => b.textContent.includes("Light the west torches")));
    await page.evaluate(() => [...document.querySelectorAll("#tasks button.task")]
      .find((b) => b.textContent.includes("Light the west torches")).click());
    await page.waitForSelector(".task-sessions .ts-chip.cursor");
    await page.evaluate(() => document.querySelector(".task-sessions").scrollIntoView({ block: "center" }));
    await page.waitForTimeout(600);
    await page.screenshot({ path: out });
    console.log(out);
  } finally {
    await browser.close();
    server.stdin.end();
  }
})().catch((e) => { console.error(e); process.exit(1); });
