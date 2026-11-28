"use strict";

const STAGES = ["Listen", "Draft rules", "Preview and edit", "Approve", "Test", "Deploy", "Verify and share"];
const LATER_FROM = 4; // stages 5-7 arrive in later phases

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
  const progress = { none: [0, 0], drafting: [1, 1], awaiting_approval: [3, 3], approved: [LATER_FROM, 4] };
  const [active, done] = progress[state] || progress.none;
  els.stages.replaceChildren();
  STAGES.forEach((label, i) => {
    const li = document.createElement("li");
    li.textContent = label;
    if (i < done) li.className = "done";
    else if (i === active && state !== "approved") li.className = "active";
    else if (i >= LATER_FROM) { li.className = "later"; li.title = "Arrives in a later phase"; }
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
  addMessage("agent", "Hi! Tell me about the stokvel you want to start: its name, how many members, and how much each pays.");
}

/* ---------- speaking ---------- */
function stopSpeaking() {
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

async function speak(text) {
  if (!els.voiceReplies.checked) return;
  stopSpeaking();
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
  busy = true; els.send.disabled = true;
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

/* ---------- listening ---------- */
function setMic(on) {
  els.mic.setAttribute("aria-pressed", on ? "true" : "false");
  els.mic.setAttribute("aria-label", on ? "Stop listening" : "Start listening");
  els.mic.textContent = on ? "Listening" : "Mic";
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
  rec.lang = "en-ZA"; rec.interimResults = true; rec.continuous = false;
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
els.mic.addEventListener("click", () => { recognition ? stopListening() : startListening(); });
els.reset.addEventListener("click", () => { stopSpeaking(); stopListening(); setNote(""); resetUi(); });
els.voiceReplies.addEventListener("change", () => { if (!els.voiceReplies.checked) stopSpeaking(); });

fetch("/voice/config").then((r) => r.json()).then((c) => { serverVoice = !!c.elevenlabs; }).catch(() => {});
if (!SpeechRecognition) setNote("Voice input needs Chrome or Edge. You can still type.");
resetUi();
