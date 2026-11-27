// STATUSCOLOR: a bot's state chip in the Dungeon's state colour (scene.inks, from cli_avatars/app/status_ink.py),
// repainted only for a bot whose state changed, with one short CSS pulse; the word stays, so colour only adds.
"use strict";

const StateInk = (() => {
  const WORDS = { busy: "working", thinking: "thinking", subagent: "subagent", blocked: "needs you", error: "error",
    done: "done", idle: "idle" };

  function paint(chip, state, inks, pulse) {
    chip.textContent = WORDS[state] || "here";
    chip.className = "pm-state " + (state || "here");
    chip.style.setProperty("--st", (inks && inks[state]) || "");
    if (pulse) {
      void chip.offsetWidth;  // restart the animation
      chip.classList.add("pulse");
    }
  }

  // bots of ``list`` whose state differs from the walker map ``before``
  function changed(before, list) {
    return list.filter((a) => before.has(a.id) && before.get(a.id).a.state !== a.state);
  }

  return { WORDS, paint, changed };
})();

if (typeof module === "object" && module.exports) module.exports = StateInk;
