"use strict";

const STAGES = ["Listen", "Draft rules", "Preview and edit", "Approve", "Test", "Deploy", "Verify and share"];

const $ = (id) => document.getElementById(id);
const els = {
  log: $("log"), text: $("text"), send: $("send"), mic: $("mic"), form: $("composer"),
  note: $("note"), stages: $("stages"), voiceReplies: $("voiceReplies"), handsFree: $("handsFree"),
  reset: $("reset"), name: $("pv-name"), members: $("pv-members"), amount: $("pv-amount"),
};

let sessionId = null;
let busy = false;
let recognition = null;
let currentAudio = null;
let serverVoice = false;
let stage = "none"; // none | approved | tested | deployed

/* ---------- assistant avatar and interface commands ---------- */
const avatar = createAvatar($("avatar"), $("av-mouth"));

function currentTheme() { return document.documentElement.dataset.theme || "auto"; }

function applyTheme(name) {
  if (name === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = name;
  try { name === "auto" ? localStorage.removeItem("stokvel-theme") : localStorage.setItem("stokvel-theme", name); } catch (_) {}
  $("themeBtn").textContent = "Theme: " + name;
}

function nextTheme() {
  const order = THEMES, i = order.indexOf(currentTheme());
  return order[(i + 1) % order.length];
}

function setAvatarVisible(on) {
  $("avatar").hidden = !on;
  $("avatarOn").checked = on;
}

/* Returns the reply text if the sentence was an interface command, else null. */
function runLocalCommand(text) {
  const cmd = parseCommand(text);
  if (!cmd) return null;
  switch (cmd.type) {
    case "theme": {
      const name = cmd.theme === "next" ? nextTheme() : cmd.theme;
      applyTheme(name); avatar.smile();
      return name === "auto" ? "Done. I am following your device's theme now." : "Done. Switched to the " + name + " theme.";
    }
    case "theme-help": return "I can do light, dark, ocean or sunset. Which one would you like?";
    case "wave": avatar.wave(); return "Hi there!";
    case "smile": avatar.smile(); return "Happy to help!";
    case "hide": setAvatarVisible(false); return "Okay, I will hide. Tick Assistant below to bring me back.";
    case "show": setAvatarVisible(true); avatar.wave(); return "I'm back!";
  }
  return null;
}

function renderActions() {
  const box = $("actions");
  const cfg = {
    approved: ["Safety tests", "Run automated attack tests on the group before anything is deployed.", "Run safety tests"],
    tested: ["Deploy", "Tests passed. Create the group on Solana devnet (test network, no real money).", "Deploy to devnet"],
  }[stage];
  box.hidden = !cfg;
  if (!cfg) return;
  $("actions-title").textContent = cfg[0];
  $("actions-help").textContent = cfg[1];
  $("act").textContent = cfg[2];
}

async function action(path) {
  const res = await fetch("/sessions/" + sessionId + path, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "Request failed (" + res.status + ")");
  return body;
}

async function runAction() {
  if (busy || !sessionId) return;
  busy = true; $("act").disabled = true;
  try {
    if (stage === "approved") {
      setNote("Running tests. This can take a few minutes...");
      const r = await action("/test");
      if (r.tests_passed) {
        stage = "tested"; renderStages("tested");
        addMessage("agent", "All safety tests passed. Shall I deploy it to devnet? Press the Deploy button.");
      } else {
        addMessage("agent", "The safety tests failed, so I will not deploy. Nothing was created.");
      }
    } else if (stage === "tested") {
      setNote("Deploying to devnet...");
      await action("/deploy");
      stage = "deployed"; renderStages("shared");
      await showShare();
      avatar.celebrate();
      addMessage("agent", "Your stokvel is live on devnet. Share the link below with members.");
    }
    setNote("");
  } catch (err) {
    setNote(String(err.message || err));
  } finally {
    busy = false; $("act").disabled = false; renderActions();
  }
}

async function showShare() {
  const res = await fetch("/sessions/" + sessionId + "/share");
  if (!res.ok) return;
  const d = await res.json();
  $("share-summary").textContent = d.summary;
  $("share-hash").textContent = d.rules_hash;
  const ul = $("share-links"); ul.replaceChildren();
  const labels = { transaction: "Creation transaction", group_account: "Group account", rules_memo: "Rules fingerprint record" };
  Object.entries(d.links).forEach(([k, href]) => {
    const li = document.createElement("li"), a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener"; a.textContent = labels[k] || k;
    li.appendChild(a); ul.appendChild(li);
  });
  const qr = $("share-qr");
  if (d.links.group_account) {
    qr.src = "/sessions/" + sessionId + "/qr.svg?url=" + encodeURIComponent(d.links.group_account);
    qr.hidden = false;
  } else qr.hidden = true;
  $("share").hidden = false;
  $("actions").hidden = true;
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

/* ---------- rendering (textContent only: never inject user text as HTML) ---------- */
function addMessage(who, text) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.textContent = text;
  els.log.appendChild(div);
  els.log.scrollTop = els.log.scrollHeight;
}

function setNote(text) { els.note.textContent = text || ""; }

function renderStages(state) {
  // index of the active stage, and how many are done, for each backend state
  const progress = {
    none: [0, 0], drafting: [1, 1], awaiting_approval: [3, 3],
    approved: [4, 4], tested: [5, 5], deployed: [6, 6], shared: [7, 7],
  };
  const [active, done] = progress[state] || progress.none;
  els.stages.replaceChildren();
  STAGES.forEach((label, i) => {
    const li = document.createElement("li");
    li.textContent = label;
    if (i < done) li.className = "done";
    else if (i === active) li.className = "active";
    els.stages.appendChild(li);
  });
}

function renderPreview(spec) {
  if (!spec) return;
  els.name.textContent = spec.group_name || "-";
  els.members.textContent = spec.max_members != null ? String(spec.max_members) : "-";
  els.amount.textContent = spec.contribution_lamports != null
    ? (spec.contribution_lamports / 1e9).toLocaleString("en", { maximumFractionDigits: 9 }) + " SOL"
    : "-";
}

function resetUi() {
  sessionId = null;
  els.log.replaceChildren();
  renderStages("none");
  renderPreview({});
  stage = "none";
  $("actions").hidden = true; $("share").hidden = true;
  addMessage("agent", "Hi! Tell me about the stokvel you want to start: its name, how many members, and how much each pays.");
}

/* ---------- speaking ---------- */
function cancelPlayback() {
  if (currentAudio) {
    const a = currentAudio; currentAudio = null;
    a.pause(); a.dispatchEvent(new Event("ended"));   // lets a waiting speak() finish
  }
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

function stopSpeaking() { avatar.setSpeaking(false); cancelPlayback(); }

async function speak(text) {
  if (!els.voiceReplies.checked) { avatar.smile(); return; }
  avatar.setSpeaking(true);
  try { await speakInner(text); } finally { avatar.setSpeaking(false); }
}

async function speakInner(text) {
  cancelPlayback();
  if (serverVoice) {
    try {
      const res = await fetch("/tts", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      });
      if (res.ok) {
        const audio = new Audio(URL.createObjectURL(await res.blob()));
        currentAudio = audio;
        await new Promise((resolve) => { audio.onended = resolve; audio.onerror = resolve; audio.play().catch(resolve); });
        return;
      }
    } catch (_) { /* fall through to browser voice */ }
  }
  if ("speechSynthesis" in window) {
    await new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "en-ZA";
      u.onend = resolve; u.onerror = resolve;
      window.speechSynthesis.speak(u);
    });
  }
}

/* ---------- chat ---------- */
async function post(message, withSession) {
  return fetch("/chat", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: withSession ? sessionId : null }),
  });
}

async function send(message) {
  if (busy || !message.trim()) return;
  const local = runLocalCommand(message);
  if (local) {
    addMessage("user", message); addMessage("agent", local);
    await speak(local);
    if (els.handsFree.checked && SpeechRecognition) startListening();
    return;
  }
  busy = true; els.send.disabled = true; avatar.think(true);
  addMessage("user", message);
  try {
    let res = await post(message, true);
    if (res.status === 404 && sessionId) {   // server restarted: start fresh
      sessionId = null;
      setNote("The server restarted, so I started a new group.");
      res = await post(message, false);
    }
    if (!res.ok) throw new Error("Request failed (" + res.status + ")");
    const data = await res.json();
    sessionId = data.session_id;
    addMessage("agent", data.reply);
    renderPreview(data.group_spec);
    renderStages(data.state);
    stage = data.state === "approved" ? "approved" : "none";
    renderActions();
    busy = false; els.send.disabled = false;
    await speak(data.reply);
    if (els.handsFree.checked && SpeechRecognition) startListening();
  } catch (err) {
    addMessage("agent", "Sorry, something went wrong. Please try again.");
    setNote(String(err.message || err));
  } finally {
    busy = false; els.send.disabled = false;
  }
}

/* ---------- microphone diagnostics ---------- */
async function micCheck() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const label = (stream.getAudioTracks()[0] || {}).label || "unknown device";
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const an = ctx.createAnalyser();
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    let peak = 0;
    const end = Date.now() + 2000;
    while (Date.now() < end) {
      an.getByteTimeDomainData(buf);
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      await new Promise((r) => setTimeout(r, 50));
    }
    stream.getTracks().forEach((t) => t.stop());
    ctx.close();
    return { label, peak };
  } catch (e) { return { error: e.name }; }
}

function explainNoSpeech() {
  setNote("Checking your microphone... speak now.");
  micCheck().then((r) => {
    if (r.error) setNote("Microphone error: " + r.error + ". Allow the mic in the browser and your system settings.");
    else if (r.peak < 3) setNote("Chrome is using '" + r.label + "' but it hears silence. Pick another mic in the address bar mic icon, or unmute it in system settings.");
    else setNote("Your mic works ('" + r.label + "'). Tap Mic, then speak straight away.");
  });
}

/* ---------- listening ---------- */
let recLang = "en-ZA";
function setMic(on) {
  els.mic.setAttribute("aria-pressed", on ? "true" : "false");
  els.mic.setAttribute("aria-label", on ? "Stop listening" : "Start listening");
  els.mic.textContent = on ? "Listening" : "Mic";
  avatar.listen(on);
}

function startListening() {
  if (!SpeechRecognition) {
    setNote("Voice input needs Chrome or Edge. You can still type.");
    return;
  }
  if (busy || recognition) return;
  stopSpeaking();
  const rec = new SpeechRecognition();
  recognition = rec;
  rec.lang = recLang; rec.interimResults = true; rec.continuous = false;
  let finalText = "";
  rec.onstart = () => { setMic(true); setNote("Listening..."); };
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t; else interim += t;
    }
    els.text.value = (finalText + interim).trim();
  };
  rec.onerror = (e) => {
    if (e.error === "no-speech") { explainNoSpeech(); return; }
    if (e.error === "language-not-supported" && recLang !== "en-US") {
      recLang = "en-US"; setNote("English (South Africa) is not supported here, switched to US English. Tap Mic again."); return;
    }
    const msg = {
      "not-allowed": "Microphone blocked. Allow it in the browser, and use localhost or https.",
      "no-speech": "I didn't hear anything. Tap Mic and try again.",
      "network": "Speech recognition lost its connection.",
    }[e.error] || "Speech recognition error: " + e.error;
    setNote(msg);
  };
  rec.onend = () => {
    recognition = null; setMic(false);
    const t = finalText.trim();
    if (t) { els.text.value = ""; setNote(""); send(t); }
  };
  rec.start();
}

function stopListening() { if (recognition) recognition.stop(); }

/* ---------- wiring ---------- */
els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const t = els.text.value; els.text.value = "";
  send(t);
});
$("act").addEventListener("click", runAction);
els.mic.addEventListener("click", () => { recognition ? stopListening() : startListening(); });
els.reset.addEventListener("click", () => { stopSpeaking(); stopListening(); setNote(""); resetUi(); });
$("avatar").addEventListener("click", () => { avatar.wave(); });
$("avatarOn").addEventListener("change", (e) => setAvatarVisible(e.target.checked));
$("themeBtn").addEventListener("click", () => applyTheme(nextTheme()));
els.voiceReplies.addEventListener("change", () => { if (!els.voiceReplies.checked) stopSpeaking(); });

fetch("/voice/config").then((r) => r.json()).then((c) => { serverVoice = !!c.elevenlabs; }).catch(() => {});
if (!SpeechRecognition) setNote("Voice input needs Chrome or Edge. You can still type.");
resetUi();
$("themeBtn").textContent = "Theme: " + currentTheme();
setTimeout(() => avatar.wave(), 500);
