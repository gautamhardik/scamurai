// Scamurai front end. No framework, no innerHTML with data: everything is built with textContent.
// Motion (flip words, vanish input, moving cards, tracing beam, gauge, meteors) is plain DOM/CSS and
// switches off under prefers-reduced-motion.

const $ = (sel, root = document) => root.querySelector(sel);
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Next frame, with a timer fallback: rAF pauses in background tabs and must never stall a check.
const frame = () => new Promise((r) => { requestAnimationFrame(r); setTimeout(r, 60); });

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const ICONS = {
  check: ["M5 12.5l4.2 4.2L19 7"],
  x: ["M6 6l12 12", "M18 6L6 18"],
  dash: ["M7 12h10"],
  alert: ["M12 3.5L2.5 20h19L12 3.5z", "M12 10v4.5", "M12 17.3v.2"],
  octagon: ["M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z", "M12 8v5", "M12 16.3v.2"],
  shield: ["M12 2.8l7.6 3.1v5.6c0 4.8-3.2 8.9-7.6 10.7-4.4-1.8-7.6-5.9-7.6-10.7V5.9z", "M8.3 12.2l2.6 2.6 5-5.2"],
  help: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.6", "M12 16.8v.2"],
  search: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "M20 20l-4-4"],
  news: ["M5 5h11v14H6a1 1 0 0 1-1-1V5z", "M16 9h3v9a1 1 0 0 1-1 1h-2", "M8 9h5", "M8 12h5", "M8 15h3"],
  lens: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 10a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z"],
  tag: ["M3 12V4h8l10 10-8 8L3 12z", "M7.5 7.5v.2"],
  briefcase: ["M4 8h16v11H4z", "M9 8V5h6v3"],
  pin: ["M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11z", "M12 8a2 2 0 1 0 0 4a2 2 0 1 0 0-4z"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M18 14v6H4V6h6"],
  copy: ["M8 8h11v12H8z", "M5 16V4h11"],
  chevron: ["M9 6l6 6-6 6"],
  message: ["M4 5h16v11H9l-5 4z"],
  image: ["M4 5h16v14H4z", "M4 16l5-5 4 4 3-3 4 4"],
  refresh: ["M20 11a8 8 0 1 0-2.3 5.7", "M20 5v6h-6"],
  arrow: ["M5 12h14", "M13 6l6 6-6 6"],
  globe: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M3.5 12h17", "M12 3c2.6 3 2.6 15 0 18", "M12 3c-2.6 3-2.6 15 0 18"],
};

function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ICONS[name] || []) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}

const ENGINES = {
  google: ["Google Search", "search"],
  google_news: ["Google News", "news"],
  google_lens: ["Google Lens", "lens"],
  google_shopping: ["Google Shopping", "tag"],
  google_jobs: ["Google Jobs", "briefcase"],
  google_maps: ["Google Maps", "pin"],
};

const SOURCE = {
  official: "Official site", government: "Government", news: "News", complaint_forum: "Complaint site",
  registry: "Company registry", marketplace: "Shop listing", job_board: "Job listing", maps_place: "Google Maps",
  social: "Social media", message: "In the message", other: "Web",
};

// Section headings follow the report's language.
const T = {
  en: {
    now: "What to do now", why: "Why", ok: "What checks out", checked: "What Scamurai checked", how: "How Scamurai decided",
    read: "What Scamurai read", sources: (n) => `${n} source${n === 1 ? "" : "s"}`, again: "Check another message",
    copy: "Copy summary", copied: "Copied", confidence: "Confidence", conf: { high: "High", medium: "Medium", low: "Low" },
    points: "risk points",
  },
  hi: {
    now: "अब क्या करें", why: "क्यों", ok: "क्या सही निकला", checked: "Scamurai ने क्या जाँचा", how: "Scamurai ने कैसे तय किया",
    read: "Scamurai ने मैसेज से क्या पढ़ा", sources: (n) => `${n} स्रोत`, again: "दूसरा मैसेज जाँचें",
    copy: "सारांश कॉपी करें", copied: "कॉपी हो गया", confidence: "भरोसा", conf: { high: "ज़्यादा", medium: "मध्यम", low: "कम" },
    points: "जोखिम अंक",
  },
  hinglish: {
    now: "Ab kya karein", why: "Kyun", ok: "Kya sahi nikla", checked: "Scamurai ne kya check kiya", how: "Scamurai ne kaise decide kiya",
    read: "Scamurai ne message se kya padha", sources: (n) => `${n} source`, again: "Doosra message check karein",
    copy: "Summary copy karein", copied: "Copy ho gaya", confidence: "Bharosa", conf: { high: "High", medium: "Medium", low: "Low" },
    points: "risk points",
  },
};

const SEVERITY = {
  en: { critical: "Critical", high: "High", medium: "Medium", low: "Low", trust: "Checks out" },
  hi: { critical: "गंभीर", high: "ज़्यादा", medium: "मध्यम", low: "कम", trust: "सही" },
  hinglish: { critical: "Critical", high: "High", medium: "Medium", low: "Low", trust: "Sahi" },
};
const CAPS = {
  message_only_cap: "Capped at 55: only message patterns were found, no web evidence.",
  contradiction_cap: "Limited to “Be careful”: official confirmation conflicts with other evidence.",
  gate_demotion: "High score, but no single strong piece of web evidence, so shown as “Be careful”.",
};
// The report's language switch. Every report carries its text in each language (built from the same evidence).
const LANG_NAME = { en: "English", hi: "हिंदी", hinglish: "Hinglish" };
const LANG_TAG = { en: "en", hi: "hi", hinglish: "hi-Latn" };
let QUIET = false; // re-rendering for a language switch: no score count-up

const VERDICT_ICON = { HIGH_RISK: "octagon", SUSPICIOUS: "alert", LOW_RISK: "shield", UNVERIFIED: "help" };

const FLIP_WORDS = ["message", "SMS", "KYC link", "job offer", "₹1,499 deal", "screenshot", "helpline", "बिजली बिल"];
const PLACEHOLDERS = [
  "Paste the message here — English, हिंदी or Hinglish. You can also paste a screenshot (Ctrl+V).",
  "“Dear customer, your electricity will be disconnected tonight at 9:30 PM. Call our officer…”",
  "“प्रिय उपभोक्ता, आपका बिजली कनेक्शन आज रात काट दिया जाएगा…”",
  "“Aapka KYC pending hai. Account block ho jayega, is link par update karein…”",
  "“Congratulations! Selected for work from home. Earn ₹5,000/day. Pay ₹499 registration…”",
  "“Nike Air Jordan 1 at ₹1,499 only. 85% off, today only!”",
];

// ------------------------------------------------------------------ state
const state = { file: null, imageUrl: null, exampleId: null, health: null, controller: null, lastForm: null, busy: false, flipFit: null };

// ------------------------------------------------------------------ boot
document.addEventListener("DOMContentLoaded", () => {
  bindForm();
  bindPointerFx();
  flipWords($("#flip"), FLIP_WORDS);
  cyclePlaceholders();
  loadHealth();
  loadExamples();
  openFromHash();
});
window.addEventListener("hashchange", openFromHash);

// Reports are stored locally for 7 days; #r=<id> reopens one (reload-safe, linkable on this machine).
async function openFromHash() {
  const m = location.hash.match(/^#r=([a-z0-9]{6,32})$/);
  if (!m) { if (!location.hash) show("view-home"); return; }
  try {
    const res = await fetch(`/api/investigations/${m[1]}`);
    if (!res.ok) throw new Error();
    renderReport(await res.json());
  } catch { history.replaceState(null, "", "/"); }
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const j = await res.json();
    state.health = j;
    const status = $("#status");
    status.replaceChildren();
    const live = j.mode === "live";
    status.append(h("span", { class: `pill ${live ? "live" : "replay"}`, title: live ? "Live web searches" : "Recorded evidence" },
      h("span", { class: "dot" }), live ? "Live" : "Replay"));
    if (live && j.serpapi && j.serpapi.credits_left !== null && j.serpapi.credits_left !== undefined) {
      status.append(h("span", { class: "pill", title: "SerpApi searches left this month" }, `${j.serpapi.credits_left} searches left`));
    }
    if (!live) {
      const b = $("#mode-banner");
      b.textContent = "Replay mode: these examples run on evidence recorded from live SerpApi searches, so no keys are needed. Run `scamurai serve` for live checks.";
      b.hidden = false;
    } else if (!j.serpapi.configured) {
      const b = $("#mode-banner");
      b.textContent = "SERPAPI_API_KEY is not set. Add it to .env, or run `scamurai demo` to try the recorded examples.";
      b.hidden = false;
    }
  } catch { /* health is informational */ }
}

// Examples scroll past as a slow marquee (after Aceternity's "Infinite Moving Cards"). The second
// copy exists only to make the loop seamless, so it is hidden from assistive tech and the tab order.
async function loadExamples() {
  try {
    const list = await (await fetch("/api/examples")).json();
    const track = h("div", { class: "marquee-track" },
      list.map((ex) => exampleCard(ex, false)), list.map((ex) => exampleCard(ex, true)));
    $("#examples").replaceChildren(track);
  } catch { /* optional */ }
}

function exampleCard(ex, clone) {
  const [ic, kind] = ex.kind === "screenshot" ? ["image", "Screenshot"] : ex.image_url ? ["tag", "Product photo"] : ["message", "Message"];
  const snippet = ex.text ? ex.text.replace(/\s+/g, " ") : "A Hindi SMS screenshot, read by an AI vision model.";
  const thumb = ex.image_url || ex.image;
  return h("button", { class: "ex-card", type: "button", onclick: () => useExample(ex), "aria-hidden": clone ? "true" : null, tabindex: clone ? "-1" : null },
    h("span", { class: "ex-top" }, h("span", { class: "ex-ic" }, icon(ic)), kind),
    h("span", { class: "ex-title", text: ex.title }),
    h("span", { class: "ex-snippet", text: snippet }),
    thumb ? h("img", { class: "ex-thumb", src: thumb, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : null);
}

async function useExample(ex) {
  if (state.busy) return;
  state.busy = true;
  try {
    clearForm();
    $("#form").scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "center" });
    await sleep(REDUCED ? 0 : 320);
    if (ex.image) {
      const blob = await (await fetch(ex.image)).blob();
      setFile(new File([blob], ex.image.split("/").pop(), { type: blob.type || "image/jpeg" }));
    }
    if (ex.image_url) {
      state.imageUrl = ex.image_url;
      showAttachment(ex.image_url, "Product photo", "Image link · searched with Google Lens");
    }
    await typeInto($("#text"), ex.text || "");
    state.exampleId = ex.id;
    await sleep(REDUCED ? 0 : 280);
  } finally {
    state.busy = false;
  }
  $("#form").requestSubmit();
}

async function typeInto(ta, text) {
  if (REDUCED || !text) { ta.value = text; syncPlaceholder(); return; }
  const chunk = Math.max(1, Math.ceil(text.length / 36));
  for (let i = chunk; i < text.length + chunk; i += chunk) {
    ta.value = text.slice(0, i);
    syncPlaceholder();
    ta.scrollTop = ta.scrollHeight;
    await frame();
  }
}

// ------------------------------------------------------------------ hero motion
// Container text flip: one word visible at a time, the slot's width eases to fit it.
function flipWords(el, words, every = 2600) {
  if (!el) return;
  const items = words.map((w, i) => h("span", { class: `flip-word${i === 0 ? " on" : ""}`, text: w }));
  el.replaceChildren(...items);
  let i = 0;
  const fit = () => {
    const w = items[i].offsetWidth;
    if (w) el.style.setProperty("--w", `${w}px`);
    else el.style.removeProperty("--w");
  };
  state.flipFit = fit;
  fit();
  document.fonts?.ready.then(fit); // local display fonts can load after the first measure
  window.addEventListener("resize", fit);
  if (REDUCED) return;
  setInterval(() => {
    if (document.hidden || $("#view-home").hidden) return;
    const prev = items[i];
    prev.classList.replace("on", "off");
    setTimeout(() => prev.classList.remove("off"), 600);
    i = (i + 1) % items.length;
    items[i].classList.add("on");
    fit();
  }, every);
}

// Placeholders that slide through real scam openings (after Aceternity's "Placeholders and Vanish Input").
function cyclePlaceholders() {
  const ph = $("#ph");
  let i = 0;
  let cur = null;
  const set = () => {
    const next = h("span", { text: PLACEHOLDERS[i] });
    if (cur) {
      const old = cur;
      old.classList.add("out");
      setTimeout(() => old.remove(), 420);
    }
    ph.append(next);
    cur = next;
  };
  set();
  syncPlaceholder();
  if (REDUCED) return;
  setInterval(() => {
    if (document.hidden || $("#text").value || $("#view-home").hidden) return;
    i = (i + 1) % PLACEHOLDERS.length;
    set();
  }, 3400);
}

function syncPlaceholder() {
  $("#ph").classList.toggle("gone", $("#text").value.length > 0);
}

// Pointer-driven light: the input card's glowing edge turns toward the cursor, cards get a
// spotlight under it, and product cards tilt a little.
function bindPointerFx() {
  const card = $("#form");
  let target = 0;
  let cur = 0;
  let raf = 0;
  const step = () => {
    const d = ((target - cur + 540) % 360) - 180;
    cur += d * 0.2;
    card.style.setProperty("--start", cur.toFixed(1));
    raf = Math.abs(d) > 0.5 ? requestAnimationFrame(step) : 0;
  };
  card.addEventListener("pointermove", (e) => {
    const r = card.getBoundingClientRect();
    target = (Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180) / Math.PI + 90;
    if (!raf) raf = requestAnimationFrame(step);
  }, { passive: true });

  document.addEventListener("pointermove", (e) => {
    const spot = e.target.closest?.(".spot-card");
    if (spot) {
      const r = spot.getBoundingClientRect();
      spot.style.setProperty("--mx", `${e.clientX - r.left}px`);
      spot.style.setProperty("--my", `${e.clientY - r.top}px`);
    }
    const p = !REDUCED && e.target.closest?.(".product");
    if (p) {
      const r = p.getBoundingClientRect();
      p.style.setProperty("--ry", `${((e.clientX - r.left) / r.width - 0.5) * 14}deg`);
      p.style.setProperty("--rx", `${(0.5 - (e.clientY - r.top) / r.height) * 14}deg`);
    }
  }, { passive: true });
  document.addEventListener("pointerout", (e) => {
    const p = e.target.closest?.(".product");
    if (p && !p.contains(e.relatedTarget)) { p.style.removeProperty("--rx"); p.style.removeProperty("--ry"); }
  });
}

// ------------------------------------------------------------------ form
function bindForm() {
  const form = $("#form");
  const file = $("#file");
  file.addEventListener("change", () => file.files[0] && setFile(file.files[0]));
  $("#pick-file").addEventListener("click", () => file.click()); // a real button, so it's keyboard-reachable
  $("#attach-remove").addEventListener("click", () => { state.file = null; state.imageUrl = null; file.value = ""; $("#attachment").hidden = true; });
  $("#toggle-extra").addEventListener("click", (e) => {
    const extra = $("#extra");
    extra.hidden = !extra.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!extra.hidden));
    if (!extra.hidden) $("#url").focus();
  });
  $("#text").addEventListener("input", () => { state.exampleId = null; syncPlaceholder(); });
  $("#text").addEventListener("paste", (e) => {
    const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) { e.preventDefault(); setFile(item.getAsFile()); }
  });
  form.addEventListener("dragover", (e) => { e.preventDefault(); form.classList.add("dragging"); });
  form.addEventListener("dragleave", (e) => { if (!form.contains(e.relatedTarget)) form.classList.remove("dragging"); });
  form.addEventListener("drop", (e) => {
    e.preventDefault(); form.classList.remove("dragging");
    const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith("image/"));
    if (f) setFile(f);
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
}

function setFile(f) {
  if (!f) return;
  if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return formError("Scamurai can read PNG, JPG or WebP screenshots only.");
  if (f.size > 5 * 1024 * 1024) return formError("That image is over 5 MB. Try a smaller screenshot.");
  state.file = f;
  state.imageUrl = null;
  formError(null);
  showAttachment(URL.createObjectURL(f), f.name || "Screenshot", `${Math.round(f.size / 1024)} KB · will be read and checked`);
}

function showAttachment(src, name, meta) {
  $("#attach-thumb").src = src;
  $("#attach-name").textContent = name;
  $("#attach-meta").textContent = meta;
  $("#attachment").hidden = false;
}

function clearForm() {
  $("#text").value = ""; $("#url").value = ""; $("#phone").value = "";
  state.file = null; state.imageUrl = null; state.exampleId = null;
  $("#file").value = ""; $("#attachment").hidden = true; formError(null);
  syncPlaceholder();
}

function formError(msg) {
  const el = $("#form-error");
  el.textContent = msg || "";
  el.hidden = !msg;
}

async function submit() {
  if (state.submitting) return;
  const text = $("#text").value.trim();
  const url = $("#url").value.trim();
  const phone = $("#phone").value.trim();
  if (!text && !url && !phone && !state.file && !state.imageUrl) {
    return formError("Paste a message, add a screenshot, a link or a phone number.");
  }
  const fd = new FormData();
  if (text) fd.append("text", text);
  if (url) fd.append("url", url);
  if (phone) fd.append("phone", phone);
  if (state.file) fd.append("image", state.file, state.file.name || "screenshot.png");
  if (state.imageUrl) fd.append("image_url", state.imageUrl);
  if (state.exampleId) fd.append("example_id", state.exampleId);
  fd.append("lang", "auto");
  state.lastForm = { fd, text, preview: state.file ? URL.createObjectURL(state.file) : state.imageUrl };
  state.submitting = true;
  try { await vanish(); } finally { state.submitting = false; }
  run(fd);
}

// The message dissolves into particles, swept from right to left, before the check starts.
async function vanish() {
  const ta = $("#text");
  const canvas = $("#vanish");
  if (REDUCED || !ta.value.trim() || !canvas.getContext) return;
  const w = ta.clientWidth;
  const ht = ta.clientHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(ht * dpr);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const cs = getComputedStyle(ta);
  const size = parseFloat(cs.fontSize);
  const lh = parseFloat(cs.lineHeight) || size * 1.55;
  const padL = parseFloat(cs.paddingLeft);
  const padT = parseFloat(cs.paddingTop);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  ctx.textBaseline = "top";
  ctx.fillStyle = "#fff";
  const lines = wrapText(ctx, ta.value, w - padL - parseFloat(cs.paddingRight));
  const first = Math.floor(ta.scrollTop / lh);
  lines.slice(first, first + Math.ceil(ht / lh)).forEach((ln, i) => ctx.fillText(ln, padL, padT + i * lh + (lh - size) / 2));

  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  const pts = [];
  const gap = Math.max(1, Math.round(2 * dpr));
  for (let y = 0; y < canvas.height; y += gap) {
    for (let x = 0; x < canvas.width; x += gap) {
      if (data[(y * canvas.width + x) * 4 + 3] > 110) pts.push({ x: x / dpr, y: y / dpr, r: 1.7, hue: 185 + (x / canvas.width) * 95 });
    }
  }
  ta.classList.add("vanishing");
  let sweep = w;
  const speed = w / 28;
  const animation = new Promise((resolve) => {
    let resolved = false;
    const tick = () => {
      ctx.clearRect(0, 0, w, ht);
      sweep -= speed;
      let alive = 0;
      for (const p of pts) {
        if (p.r <= 0) continue;
        if (p.x > sweep) {
          p.x += Math.random() * 2.6 - 0.8;
          p.y += Math.random() * 2.4 - 1.2;
          p.r -= 0.05 + Math.random() * 0.06;
          if (p.r <= 0) continue;
          ctx.fillStyle = `hsl(${p.hue} 90% 72%)`;
        } else {
          ctx.fillStyle = "#f4f4f6";
        }
        alive++;
        ctx.fillRect(p.x, p.y, p.r, p.r);
      }
      if (!resolved && sweep < -30) { resolved = true; resolve(); }
      if (alive) requestAnimationFrame(tick);
      else { ctx.clearRect(0, 0, w, ht); ta.classList.remove("vanishing"); if (!resolved) resolve(); }
    };
    requestAnimationFrame(tick);
  });
  await Promise.race([animation, sleep(900)]);
}

function wrapText(ctx, text, maxW) {
  const out = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const word of para.split(/(\s+)/)) {
      const next = line + word;
      if (line.trim() && ctx.measureText(next).width > maxW) { out.push(line.trimEnd()); line = word.trimStart(); }
      else line = next;
    }
    out.push(line);
  }
  return out;
}

// ------------------------------------------------------------------ investigation stream
function show(view) {
  for (const id of ["view-home", "view-run", "view-report"]) $("#" + id).hidden = id !== view;
  if (view === "view-home") { $("#text").classList.remove("vanishing"); $("#vanish").width = 0; state.flipFit?.(); }
  window.scrollTo({ top: 0, behavior: REDUCED ? "auto" : "smooth" });
}

async function run(fd) {
  const view = $("#view-run");
  const timeline = h("ol", { class: "timeline" });
  const card = h("div", { class: "card timeline-card" }, h("span", { class: "beam", "aria-hidden": "true" }), timeline);
  const steps = {};
  // The tracing beam fills as checks finish.
  const progress = () => {
    const all = Object.values(steps);
    const finished = all.filter((li) => /\b(done|empty|failed)\b/.test(li.className)).length;
    card.style.setProperty("--p", all.length ? (finished / all.length).toFixed(3) : "0");
  };
  const addStep = (id, label, opts = {}) => {
    const li = h("li", { class: `step ${opts.status || "pending"}` },
      h("span", { class: "ic" }), h("div", { class: "label" }, opts.engine ? engineTag(opts.engine) : null, label),
      h("span", { class: "meta" }));
    steps[id] = li;
    timeline.append(li);
    progress();
    return li;
  };
  const setStep = (id, status, meta) => {
    const li = steps[id];
    if (!li) return;
    li.className = `step ${status}`;
    const ic = li.querySelector(".ic");
    ic.replaceChildren(status === "done" ? icon("check") : status === "empty" ? icon("dash") : status === "failed" ? icon("x") : "");
    if (meta !== undefined) li.querySelector(".meta").textContent = meta;
    progress();
  };

  const cancel = h("button", { class: "btn ghost", type: "button", onclick: () => { state.controller?.abort(); show("view-home"); } }, "Cancel");
  view.replaceChildren(...[
    h("div", { class: "run-head" },
      h("div", { class: "scanner", "aria-hidden": "true" }, icon("shield")),
      h("div", {}, h("h2", { class: "shimmer", text: "Checking…" }), h("p", { class: "run-sub", text: "Reading the claims, then searching the live web" })),
      cancel),
    inputPreview(),
    card,
  ].filter(Boolean));
  addStep("read", "Reading the message", { status: "running" });
  show("view-run");
  const slow = setTimeout(() => {
    if (steps.read?.classList.contains("running")) setStep("read", "running", "free AI models can take ~30 s…");
  }, 8000);
  // A visible clock: free models can take a minute, and a still screen looks frozen.
  const sub = view.querySelector(".run-sub");
  const t0 = Date.now();
  const clock = setInterval(() => {
    if (!sub.isConnected) return clearInterval(clock);
    sub.textContent = `Reading the claims, then searching the live web · ${Math.round((Date.now() - t0) / 1000)} s`;
  }, 1000);

  state.controller = new AbortController();
  let res;
  try {
    res = await fetch("/api/investigations", { method: "POST", body: fd, signal: state.controller.signal });
  } catch (err) {
    clearInterval(clock);
    if (err.name === "AbortError") return;
    return renderError("Couldn't reach Scamurai", "Check that the server is running and try again.");
  }
  if (!res.ok) {
    clearInterval(clock);
    const j = await res.json().catch(() => ({}));
    show("view-home");
    return formError(j.error?.message || "Something went wrong. Please try again.");
  }

  let weighAdded = false;
  const handle = (ev) => {
    switch (ev.type) {
      case "queued":
        setStep("read", "running", "waiting for a free slot…"); break;
      case "claims": {
        clearTimeout(slow);
        view.querySelector(".thumb.scan")?.classList.remove("scan");
        setStep("read", "done", ev.extraction === "llm" ? "" : "basic reading");
        const chips = h("div", { class: "claim-chips" }, (ev.chips || []).map((c) => h("span", { class: "claim" }, h("b", { text: c.label }), c.value)));
        if (!ev.chips?.length) chips.append(h("span", { class: "claim" }, "No phone, link or organisation found"));
        steps.read.querySelector(".label").append(chips);
        break;
      }
      case "plan":
        for (const c of ev.checks || []) addStep(c.id, c.label, { engine: c.engine });
        if (!(ev.checks || []).length && !steps.none) addStep("none", "Nothing in the message can be searched", { status: "empty" });
        break;
      case "check": {
        if (ev.status === "running") { setStep(ev.id, "running"); break; }
        const meta = ev.status === "done" ? `${ev.n_results} result${ev.n_results === 1 ? "" : "s"}${ev.cached ? " · cached" : ""}`
          : ev.status === "no_results" ? `no results${ev.cached ? " · cached" : ""}`
          : ev.status === "skipped_quota" ? "skipped (search limit)"
          : ev.status === "skipped_budget" ? "skipped" : "couldn't run";
        setStep(ev.id, ev.status === "done" ? "done" : ev.status === "no_results" ? "empty" : "failed", meta);
        break;
      }
      case "stage":
        if (ev.name === "weigh" && !weighAdded) { weighAdded = true; addStep("weigh", "Weighing the evidence", { status: "running" }); }
        if (ev.name === "weigh" && ev.status === "done") setStep("weigh", "done");
        break;
      case "report":
        renderReport(ev.report); break;
      case "error":
        renderError("Scamurai couldn't finish this check", ev.message || "Please try again.", ev.retryable); break;
    }
  };

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (line) { try { handle(JSON.parse(line)); } catch (e) { console.error(e); } }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") renderError("The connection was interrupted", "Please try again.", true);
  } finally {
    clearInterval(clock);
  }
}

function inputPreview() {
  const lf = state.lastForm || {};
  if (!lf.text && !lf.preview) return null;
  return h("div", { class: "card input-preview" },
    lf.preview ? h("div", { class: "thumb scan" }, h("img", { src: lf.preview, alt: "Your screenshot", referrerpolicy: "no-referrer" })) : null,
    lf.text ? h("p", { text: lf.text }) : h("p", { text: "Screenshot" }));
}

function engineTag(engine) {
  const [label, ic] = ENGINES[engine] || [engine, "search"];
  return h("span", { class: `engine ${engine}` }, icon(ic), label);
}

function renderError(title, message, retryable = true) {
  const view = $("#view-report");
  view.replaceChildren(h("div", { class: "card error-card" },
    h("h2", { text: title }), h("p", { text: message }),
    h("div", { class: "report-actions" },
      retryable && state.lastForm ? h("button", { class: "btn primary", type: "button", onclick: () => run(state.lastForm.fd) }, icon("refresh"), "Try again") : null,
      h("button", { class: "btn ghost", type: "button", onclick: () => show("view-home") }, "Back"))));
  show("view-report");
}

// ------------------------------------------------------------------ report motion
function gauge(score, label) {
  const C = 2 * Math.PI * 52;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 120 120");
  svg.setAttribute("aria-hidden", "true");
  const circle = (cls) => {
    const c = document.createElementNS(SVG_NS, "circle");
    for (const [k, v] of Object.entries({ cx: 60, cy: 60, r: 52, class: cls })) c.setAttribute(k, v);
    return c;
  };
  const arc = circle("arc");
  arc.setAttribute("stroke-dasharray", C.toFixed(2));
  const still = REDUCED || QUIET;
  arc.style.strokeDashoffset = still ? C * (1 - score / 100) : C;
  svg.append(circle("track"), arc);
  const num = h("b", { text: still ? String(score) : "0" });
  if (!still) {
    requestAnimationFrame(() => requestAnimationFrame(() => { arc.style.strokeDashoffset = C * (1 - score / 100); }));
    const t0 = performance.now();
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / 1300);
      num.textContent = String(Math.round(score * (1 - Math.pow(1 - k, 3))));
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  return h("div", { class: "gauge", role: "img", "aria-label": `${score} ${label} / 100` }, svg,
    h("div", { class: "gauge-num", "aria-hidden": "true" }, num, h("small", { text: label })));
}

// Meteors for risky verdicts, sparkles for the rest (after Aceternity's "Meteors" and "Sparkles").
function verdictFx(level) {
  const box = h("div", { class: "verdict-fx", "aria-hidden": "true" });
  if (REDUCED) return box;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const meteors = level === "HIGH_RISK" ? 16 : level === "SUSPICIOUS" ? 8 : 0;
  for (let i = 0; i < meteors; i++) {
    const m = h("span", { class: "meteor" });
    m.style.setProperty("--t", `${rnd(-15, 35).toFixed(1)}%`);
    m.style.setProperty("--l", `${rnd(-10, 90).toFixed(1)}%`);
    m.style.setProperty("--d", `${rnd(0, 7).toFixed(2)}s`);
    m.style.setProperty("--dur", `${rnd(4, 9).toFixed(2)}s`);
    box.append(m);
  }
  for (let i = 0; i < (meteors ? 0 : 28); i++) {
    const s = h("span", { class: "sparkle" });
    s.style.setProperty("--t", `${rnd(4, 96).toFixed(1)}%`);
    s.style.setProperty("--l", `${rnd(2, 98).toFixed(1)}%`);
    s.style.setProperty("--s", `${rnd(1.5, 3.4).toFixed(1)}px`);
    s.style.setProperty("--d", `${rnd(0, 4).toFixed(2)}s`);
    s.style.setProperty("--dur", `${rnd(2, 4.5).toFixed(2)}s`);
    box.append(s);
  }
  return box;
}

// Words fade in from a blur, one after another (after Aceternity's "Text Generate Effect").
function textGenerate(text, cls) {
  const p = h("p", { class: cls });
  if (REDUCED) { p.textContent = text; return p; }
  let n = 0;
  for (const part of text.split(/(\s+)/)) {
    if (!part) continue;
    if (/^\s+$/.test(part)) { p.append(part); continue; }
    const s = h("span", { class: "tg", text: part });
    s.style.setProperty("--d", `${(0.3 + n++ * 0.045).toFixed(3)}s`);
    p.append(s);
  }
  return p;
}

function reveal(el, delay = 0) {
  if (!el || REDUCED) return el;
  el.classList.add("reveal");
  if (delay) el.style.setProperty("--d", `${delay.toFixed(2)}s`);
  return el;
}

function observeReveals(root) {
  const els = root.querySelectorAll(".reveal:not(.in)");
  if (!("IntersectionObserver" in window)) { els.forEach((e) => e.classList.add("in")); return; }
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
  }, { rootMargin: "0px 0px -6% 0px" });
  els.forEach((e) => io.observe(e));
}

// ------------------------------------------------------------------ report
function localize(r, code, orig) {
  const tr = r.translations[code];
  return {
    ...r, _orig: orig, language: code, level_title: tr.level_title, level_subtitle: tr.level_subtitle,
    headline: tr.headline, confidence_reason: tr.confidence_reason,
    flags: r.flags.map((f) => ({ ...f, ...(tr.flags[f.signal_id] || {}) })),
    recommendations: r.recommendations.map((x) => ({ ...x, text: tr.recommendations[x.id] ?? x.text })),
  };
}

function langSwitch(r) {
  const orig = r._orig || r.language;
  const langs = ["en", "hi", ...(orig === "hinglish" ? ["hinglish"] : [])].filter((c) => r.translations?.[c]);
  if (langs.length < 2) return null;
  return h("div", { class: "lang-switch", role: "group", "aria-label": "Report language" }, icon("globe"),
    langs.map((c) => h("button", {
      type: "button", lang: LANG_TAG[c], "aria-pressed": String(c === r.language),
      onclick: () => {
        if (c === r.language) return;
        QUIET = true;
        try { renderReport(localize(r, c, orig)); } finally { QUIET = false; }
        $("#view-report .lang-switch [aria-pressed=true]")?.focus();
      },
    }, LANG_NAME[c])));
}

function renderReport(r) {
  if (location.hash !== `#r=${r.id}`) history.replaceState(null, "", `#r=${r.id}`);
  const t = { ...(T[r.language] || T.en), sev: SEVERITY[r.language] || SEVERITY.en };
  const ev = Object.fromEntries((r.evidence || []).map((e) => [e.id, e]));
  const view = $("#view-report");
  view.lang = r.language === "hi" ? "hi" : r.language === "hinglish" ? "hi-Latn" : "en"; // right voice for screen readers
  const risk = r.flags.filter((f) => f.polarity === "risk");
  const trust = r.flags.filter((f) => f.polarity === "trust");

  const verdict = h("div", { class: `verdict ${r.level}` },
    verdictFx(r.level),
    h("div", { class: "verdict-main" },
      gauge(r.score, t.points),
      h("div", {},
        h("div", { class: "verdict-kicker" }, icon(VERDICT_ICON[r.level]), h("span", { text: r.level_subtitle })),
        h("h2", { text: r.level_title }))),
    textGenerate(r.headline, "headline"),
    h("div", { class: "confidence" },
      h("span", {}, `${t.confidence}: `, h("span", { class: "conf-badge", text: t.conf[r.confidence] || r.confidence })),
      h("span", { text: r.confidence_reason }),
      r.mode === "replay" ? h("span", { class: "mode-note", text: `Recorded evidence${r.recorded_at ? " · " + r.recorded_at.slice(0, 10) : ""}` }) : null));

  const todo = reveal(h("section", { class: "section" }, h("h3", { text: t.now }),
    h("div", { class: "card todo" }, h("ol", {}, r.recommendations.map((rec) =>
      h("li", {}, rec.text, rec.link ? [" ", h("a", { href: rec.link, target: "_blank", rel: "noopener noreferrer", "aria-label": "Open link" }, icon("external"))] : null))))));

  const why = risk.length ? h("section", { class: "section" }, reveal(h("h3", { text: t.why })),
    h("div", { class: "flags" }, risk.map((f, i) => reveal(flagCard(f, ev, t), Math.min(i, 6) * 0.06)))) : null;
  const ok = trust.length ? h("section", { class: "section" }, reveal(h("h3", { text: t.ok })),
    h("div", { class: "flags" }, trust.map((f, i) => reveal(flagCard(f, ev, t), Math.min(i, 6) * 0.06)))) : null;

  const checked = reveal(h("section", { class: "section" }, h("h3", { text: t.checked }),
    h("div", { class: "card checks" }, h("ol", { class: "timeline" },
      r.checks.length ? r.checks.map((c) => {
        const status = c.status === "done" ? "done" : c.status === "no_results" ? "empty" : "failed";
        const meta = c.status === "done" ? `${c.n_results} result${c.n_results === 1 ? "" : "s"}${c.cached ? " · cached" : ""}`
          : c.status === "no_results" ? "no results" : c.status === "skipped_quota" ? "skipped (search limit)"
          : c.status === "skipped_budget" ? "skipped" : "couldn't run";
        return h("li", { class: `step ${status}` }, h("span", { class: "ic" }, status === "done" ? icon("check") : status === "empty" ? icon("dash") : icon("x")),
          h("div", { class: "label" }, engineTag(c.engine), c.label), h("span", { class: "meta", text: meta }));
      }) : h("li", { class: "step empty" }, h("span", { class: "ic" }, icon("dash")), h("div", { class: "label", text: r.confidence_reason }), h("span"))))));

  const decided = reveal(h("section", { class: "section" }, h("details", { class: "card decided" },
    h("summary", {}, icon("chevron"), t.how),
    h("div", { class: "decided-body" },
      h("p", {}, "Scamurai adds up independent pieces of evidence. Each has a fixed weight (w) and a confidence (c) based on how strong its sources are. The AI only reads the message; it never sets the score."),
      h("div", { class: "formula-term" },
        h("div", { class: "term-bar" }, h("i"), h("i"), h("i"), h("span", { text: "scamurai · risk engine" })),
        h("div", { class: "formula", text: `risk   = 1 − Π(1 − w·c)\ntrust  = 1 − Π(1 − w·c)\npoints = 100 · risk · (1 − 0.75 · trust) = ${r.score}` })),
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", { text: "Signal" }), h("th", { class: "num", text: "w" }), h("th", { class: "num", text: "c" }), h("th", { class: "num", text: "w·c" }))),
        h("tbody", {}, r.flags.map((f) => h("tr", {},
          h("td", {}, h("span", { class: "code", text: f.code }), f.title),
          h("td", { class: "num", text: f.weight.toFixed(2) }), h("td", { class: "num", text: f.confidence.toFixed(2) }),
          h("td", { class: "num", text: (f.polarity === "trust" ? "−" : "+") + f.contribution.toFixed(2) })))))),
      h("p", {}, `Risk points: ${r.score}/100. This is a weighted total of evidence, not a probability. High risk needs 65+ points and at least one strong web or identity signal.`),
      (r.caps_applied || []).map((c) => h("p", { text: CAPS[c] || c })),
      h("p", { class: "mode-note", text: `Searches: ${r.stats.searches_run} (${r.stats.cache_hits} from cache, ${r.stats.credits_spent} live) · reading: ${r.stats.llm_model || r.stats.extraction} · ${Math.round(r.stats.latency_ms / 100) / 10}s` })))));

  const read = r.claims_summary.length ? reveal(h("section", { class: "section" }, h("details", { class: "card decided" },
    h("summary", {}, icon("chevron"), t.read),
    h("div", { class: "decided-body" }, h("div", { class: "claim-chips" },
      r.claims_summary.map((c) => h("span", { class: "claim" }, h("b", { text: c.label }), c.value))))))) : null;

  const copyBtn = h("button", { class: "btn ghost", type: "button" }, icon("copy"), h("span", { text: t.copy }));
  copyBtn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(summaryText(r, ev)); copyBtn.lastChild.textContent = t.copied; } catch { /* clipboard blocked */ }
  });
  const again = h("span", { class: "cta-wrap" }, h("button", { class: "btn primary", type: "button",
    onclick: () => { clearForm(); history.replaceState(null, "", "/"); show("view-home"); $("#text").focus(); } }, t.again, icon("arrow")));
  const actions = reveal(h("div", { class: "report-actions" }, again, copyBtn));

  const llmDown = r.stats.extraction !== "llm" && (r.notes || []).some((n) => n.startsWith("llm:"));
  const notice = llmDown ? h("p", { class: "notice", text: r.mode === "replay"
    ? "Replay mode only has the recorded examples, so this message was read with basic rules and couldn't be searched."
    : "The AI reader was busy, so Scamurai read this with basic rules. If you uploaded a screenshot, paste its text for a fuller check." }) : null;
  if (notice) verdict.append(notice);
  const urgentFirst = r.level === "HIGH_RISK" || r.level === "SUSPICIOUS";
  const tools = langSwitch(r);
  view.replaceChildren(...[tools ? h("div", { class: "report-tools" }, tools) : null, verdict, urgentFirst ? todo : null, why, ok,
    urgentFirst ? null : todo, checked, decided, read, actions].filter(Boolean));
  show("view-report");
  observeReveals(view);
}

function flagCard(f, ev, t) {
  const items = f.evidence_ids.map((id) => ev[id]).filter(Boolean);
  const products = items.filter((e) => (e.kind === "lens_match" || e.kind === "shopping_offer") && e.thumbnail);
  const others = items.filter((e) => !products.includes(e));
  const list = h("div", { hidden: true },
    products.length ? h("ul", { class: "products" }, products.map(productCard)) : null,
    others.length ? h("ul", { class: "evidence" }, others.map(evidenceItem)) : null);
  const toggle = h("button", { class: "toggle", type: "button", "aria-expanded": "false" }, icon("chevron"), t.sources(items.length));
  toggle.addEventListener("click", () => {
    list.hidden = !list.hidden;
    toggle.setAttribute("aria-expanded", String(!list.hidden));
  });
  // The strongest visual evidence is open by default.
  if (products.length || f.severity === "critical") { list.hidden = false; toggle.setAttribute("aria-expanded", "true"); }
  return h("article", { class: `card flag spot-card ${f.severity}` },
    h("div", { class: "flag-head" }, h("span", { class: "flag-title", text: f.title }), h("span", { class: "sev", text: (t.sev || SEVERITY.en)[f.severity] || f.severity })),
    h("p", { text: f.explanation }),
    items.length ? toggle : null, list);
}

function productCard(e) {
  const price = e.data?.price_inr ? "₹" + Math.round(e.data.price_inr).toLocaleString("en-IN") : (e.data?.price_text || "");
  const body = [h("img", { src: e.thumbnail, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }),
    h("div", { class: "p-body" }, h("div", { class: "p-price", text: price || "—" }), h("div", { class: "p-src", text: e.data?.source || e.domain || "" }))];
  return h("li", {}, e.clickable && e.url
    ? h("a", { class: "product", href: e.url, target: "_blank", rel: "noopener noreferrer nofollow", title: e.title }, body)
    : h("div", { class: "product", title: e.title }, body));
}

function evidenceItem(e) {
  if (e.kind === "message_span") {
    return h("li", { class: "ev quote" }, h("div", { class: "ev-top" }, h("span", { class: "src message", text: SOURCE.message })),
      h("div", { class: "ev-title", text: `“${e.title}”` }));
  }
  if (e.kind === "search") { // cited by "not found" findings: let the reader re-run the exact search
    return h("li", { class: "ev" },
      h("div", { class: "ev-top" }, h("span", { class: "src search", text: "Search Scamurai ran" }),
        h("span", { class: "ev-site", text: (ENGINES[e.engine] || ["Google Search"])[0] })),
      h("a", { class: "ev-title mono", href: e.url, target: "_blank", rel: "noopener noreferrer nofollow" }, e.title, icon("external")),
      h("p", { class: "ev-snippet", text: "Open it to run the same search on Google and check for yourself." }));
  }
  const site = e.data?.source || e.domain || "";
  const date = e.published_at ? new Date(e.published_at).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" }) : "";
  const title = e.clickable && e.url
    ? h("a", { class: "ev-title", href: e.url, target: "_blank", rel: "noopener noreferrer nofollow" }, e.title, icon("external"))
    : h("div", { class: "ev-title" }, e.title, e.url ? h("div", { class: "defanged", text: "Not linked: " + defang(e.url) }) : null);
  const extra = e.kind === "place" ? [e.data?.type, e.snippet].filter(Boolean).join(" · ")
    : e.kind === "job" ? [e.data?.company, e.data?.location, e.data?.via].filter(Boolean).join(" · ")
    : e.snippet;
  return h("li", { class: "ev" },
    h("div", { class: "ev-top" }, h("span", { class: `src ${e.source_class}`, text: SOURCE[e.source_class] || "Web" }),
      h("span", { class: "ev-site", text: [site, date].filter(Boolean).join(" · ") })),
    title, extra ? h("p", { class: "ev-snippet", text: extra }) : null);
}

function defang(url) {
  try { const u = new URL(url); return u.hostname.replace(/\.(?=[^.]+$)/, "[.]"); } catch { return "link"; }
}

function summaryText(r, ev) {
  const lines = [`Scamurai check: ${r.level_title.toUpperCase()}`, r.headline, ""];
  for (const f of r.flags.filter((x) => x.polarity === "risk").slice(0, 5)) {
    const src = f.evidence_ids.map((id) => ev[id]).find((e) => e && e.url && e.clickable && (e.data?.source || e.domain));
    lines.push(`• ${f.title}${src ? ` (${src.data?.source || src.domain})` : ""}`);
  }
  if (r.recommendations.length) { lines.push(""); for (const rec of r.recommendations.slice(0, 4)) lines.push(`→ ${rec.text}`); }
  lines.push("", "Checked with Scamurai against live web evidence.");
  return lines.join("\n");
}
