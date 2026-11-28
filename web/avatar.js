"use strict";

/* Animated assistant that lives in the bottom-right corner.
   It can speak (mouth moves), smile, wave, listen, and carry out small
   interface commands such as changing the theme. Commands are handled in the
   browser and never reach the agent server, so they cannot touch a group. */

const THEMES = ["light", "dark", "ocean", "sunset"];

const MOUTHS = {
  smile: ["M54 78 Q70 92 86 78", false],
  grin: ["M52 76 Q70 102 88 76 Z", true],
  closed: ["M60 82 Q70 84 80 82", false],
  half: ["M58 78 Q70 94 82 78 Z", true],
  wide: ["M55 75 Q70 103 85 75 Z", true],
  o: ["M64 82 a6 7 0 1 0 12 0 a6 7 0 1 0 -12 0", true],
};

/* Turns a short spoken or typed sentence into a command, or null when the
   sentence is not a command (so it goes to the agent as usual).
   Long sentences are never treated as commands: "dark horse stokvel for
   twelve people, light penalty" must reach the agent. */
function parseCommand(text) {
  const t = String(text).toLowerCase().replace(/[^a-z\s]/g, " ").replace(/\s+/g, " ").trim();
  if (!t || t.split(" ").length > 10) return null;

  if (/\b(hide|remove|dismiss)\b.*\b(avatar|face|character|assistant|yourself)\b/.test(t)) return { type: "hide" };
  if (/\b(show|bring back|unhide)\b.*\b(avatar|face|character|assistant|yourself)\b/.test(t)) return { type: "show" };
  if (/\bwave\b|\bsay (hi|hello)\b/.test(t)) return { type: "wave" };
  if (/\bsmile\b/.test(t)) return { type: "smile" };

  const asksTheme =
    /\b(theme|mode|colou?rs?|appearance)\b/.test(t) ||
    /\b(go|switch to|turn on|make it|use)\s+(dark|light|ocean|sunset)\b/.test(t);
  if (!asksTheme) return null;

  if (/\b(auto|automatic|system|default)\b/.test(t)) return { type: "theme", theme: "auto" };
  if (/\b(light|bright|day|white)\b/.test(t)) return { type: "theme", theme: "light" };
  if (/\b(dark|night|black)\b/.test(t)) return { type: "theme", theme: "dark" };
  if (/\b(ocean|blue|sea)\b/.test(t)) return { type: "theme", theme: "ocean" };
  if (/\b(sunset|warm|orange|sunrise)\b/.test(t)) return { type: "theme", theme: "sunset" };
  if (/\b(change|switch|next|another|different|new)\b/.test(t)) return { type: "theme", theme: "next" };
  return { type: "theme-help" };
}

function createAvatar(root, mouthEl) {
  let talkTimer = null, waveTimer = null, happyTimer = null, last = "smile";

  function setMouth(name) {
    const [d, open] = MOUTHS[name];
    mouthEl.setAttribute("d", d);
    mouthEl.classList.toggle("open", open);
    last = name;
  }

  function setSpeaking(on) {
    clearInterval(talkTimer); talkTimer = null;
    root.dataset.speaking = on ? "true" : "false";
    if (!on) { setMouth("smile"); return; }
    const shapes = ["half", "wide", "o", "closed", "half", "wide"];
    talkTimer = setInterval(() => {
      let n; do { n = shapes[Math.floor(Math.random() * shapes.length)]; } while (n === last);
      setMouth(n);
    }, 120);
  }

  function smile() {
    if (root.dataset.speaking === "true") return;
    clearTimeout(happyTimer);
    root.dataset.mood = "happy"; setMouth("grin");
    happyTimer = setTimeout(() => { root.dataset.mood = "smile"; if (root.dataset.speaking !== "true") setMouth("smile"); }, 1800);
  }

  function wave() {
    clearTimeout(waveTimer);
    root.dataset.wave = "false";
    void root.getBoundingClientRect();           // restart the CSS animation
    root.dataset.wave = "true";
    smile();
    waveTimer = setTimeout(() => { root.dataset.wave = "false"; }, 3000);
  }

  function listen(on) { root.dataset.listening = on ? "true" : "false"; }
  function think(on) { root.dataset.thinking = on ? "true" : "false"; }
  function celebrate() { wave(); }

  setMouth("smile");
  return { setSpeaking, smile, wave, listen, think, celebrate };
}

if (typeof module !== "undefined") module.exports = { parseCommand, THEMES };
