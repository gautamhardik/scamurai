// Asli front end. No framework, no innerHTML with data: everything is built with textContent.

const $ = (sel, root = document) => root.querySelector(sel);

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
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ICONS[name] || []) {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
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
    now: "What to do now", why: "Why", ok: "What checks out", checked: "What Asli checked", how: "How Asli decided",
    read: "What Asli read", sources: (n) => `${n} source${n === 1 ? "" : "s"}`, again: "Check another message",
    copy: "Copy summary", copied: "Copied", confidence: "Confidence", conf: { high: "High", medium: "Medium", low: "Low" },
  },
  hi: {
    now: "अब क्या करें", why: "क्यों", ok: "क्या सही निकला", checked: "Asli ने क्या जाँचा", how: "Asli ने कैसे तय किया",
    read: "Asli ने मैसेज से क्या पढ़ा", sources: (n) => `${n} स्रोत`, again: "दूसरा मैसेज जाँचें",
    copy: "सारांश कॉपी करें", copied: "कॉपी हो गया", confidence: "भरोसा", conf: { high: "ज़्यादा", medium: "मध्यम", low: "कम" },
  },
  hinglish: {
    now: "Ab kya karein", why: "Kyun", ok: "Kya sahi nikla", checked: "Asli ne kya check kiya", how: "Asli ne kaise decide kiya",
    read: "Asli ne message se kya padha", sources: (n) => `${n} source`, again: "Doosra message check karein",
    copy: "Summary copy karein", copied: "Copy ho gaya", confidence: "Bharosa", conf: { high: "High", medium: "Medium", low: "Low" },
  },
};

const SEVERITY = { critical: "Critical", high: "High", medium: "Medium", low: "Low", trust: "Checks out" };
const CAPS = {
  message_only_cap: "Capped at 55: only message patterns were found, no web evidence.",
  contradiction_cap: "Limited to “Be careful”: official confirmation conflicts with other evidence.",
  gate_demotion: "High score, but no single strong piece of web evidence, so shown as “Be careful”.",
};
const VERDICT_ICON = { HIGH_RISK: "octagon", SUSPICIOUS: "alert", LOW_RISK: "shield", UNVERIFIED: "help" };

// ------------------------------------------------------------------ state
const state = { file: null, imageUrl: null, exampleId: null, health: null, controller: null, lastForm: null };

// ------------------------------------------------------------------ boot
document.addEventListener("DOMContentLoaded", () => {
  bindForm();
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
      b.textContent = "Replay mode: these examples run on evidence recorded from live SerpApi searches, so no keys are needed. Run `asli serve` for live checks.";
      b.hidden = false;
    } else if (!j.serpapi.configured) {
      const b = $("#mode-banner");
      b.textContent = "SERPAPI_API_KEY is not set. Add it to .env, or run `asli demo` to try the recorded examples.";
      b.hidden = false;
    }
  } catch { /* health is informational */ }
}

async function loadExamples() {
  try {
    const list = await (await fetch("/api/examples")).json();
    const box = $("#examples");
    for (const ex of list) {
      const ic = ex.kind === "screenshot" ? "image" : ex.image_url ? "tag" : "message";
      box.append(h("button", { class: "chip", type: "button", onclick: () => useExample(ex) }, icon(ic), ex.title));
    }
  } catch { /* optional */ }
}

async function useExample(ex) {
  clearForm();
  state.exampleId = ex.id;
  $("#text").value = ex.text || "";
  if (ex.image) {
    const blob = await (await fetch(ex.image)).blob();
    setFile(new File([blob], ex.image.split("/").pop(), { type: blob.type || "image/jpeg" }));
  }
  if (ex.image_url) {
    state.imageUrl = ex.image_url;
    showAttachment(ex.image_url, "Product photo", "Image link · searched with Google Lens");
  }
  setTimeout(() => $("#form").requestSubmit(), 350);
}

// ------------------------------------------------------------------ form
function bindForm() {
  const form = $("#form");
  const file = $("#file");
  file.addEventListener("change", () => file.files[0] && setFile(file.files[0]));
  $("#attach-remove").addEventListener("click", () => { state.file = null; state.imageUrl = null; file.value = ""; $("#attachment").hidden = true; });
  $("#toggle-extra").addEventListener("click", (e) => {
    const extra = $("#extra");
    extra.hidden = !extra.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!extra.hidden));
    if (!extra.hidden) $("#url").focus();
  });
  $("#text").addEventListener("input", () => { state.exampleId = null; });
  $("#text").addEventListener("paste", (e) => {
    const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) { e.preventDefault(); setFile(item.getAsFile()); }
  });
  form.addEventListener("dragover", (e) => { e.preventDefault(); form.classList.add("dragging"); });
  form.addEventListener("dragleave", () => form.classList.remove("dragging"));
  form.addEventListener("drop", (e) => {
    e.preventDefault(); form.classList.remove("dragging");
    const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith("image/"));
    if (f) setFile(f);
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
}

function setFile(f) {
  if (!f) return;
  if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return formError("Asli can read PNG, JPG or WebP screenshots only.");
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
}

function formError(msg) {
  const el = $("#form-error");
  el.textContent = msg || "";
  el.hidden = !msg;
}

function submit() {
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
  run(fd);
}

// ------------------------------------------------------------------ investigation stream
function show(view) {
  for (const id of ["view-home", "view-run", "view-report"]) $("#" + id).hidden = id !== view;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function run(fd) {
  const view = $("#view-run");
  const timeline = h("ol", { class: "timeline" });
  const steps = {};
  const addStep = (id, label, opts = {}) => {
    const li = h("li", { class: `step ${opts.status || "pending"}` },
      h("span", { class: "ic" }), h("div", { class: "label" }, opts.engine ? engineTag(opts.engine) : null, label),
      h("span", { class: "meta" }));
    steps[id] = li;
    timeline.append(li);
    return li;
  };
  const setStep = (id, status, meta) => {
    const li = steps[id];
    if (!li) return;
    li.className = `step ${status}`;
    const ic = li.querySelector(".ic");
    ic.replaceChildren(status === "done" ? icon("check") : status === "empty" ? icon("dash") : status === "failed" ? icon("x") : "");
    if (meta !== undefined) li.querySelector(".meta").textContent = meta;
  };

  const cancel = h("button", { class: "btn ghost", type: "button", onclick: () => { state.controller?.abort(); show("view-home"); } }, "Cancel");
  view.replaceChildren(...[
    h("div", { class: "run-head" }, h("h2", { text: "Checking…" }), cancel),
    inputPreview(),
    h("div", { class: "card" }, timeline),
  ].filter(Boolean));
  addStep("read", "Reading the message", { status: "running" });
  show("view-run");

  state.controller = new AbortController();
  let res;
  try {
    res = await fetch("/api/investigations", { method: "POST", body: fd, signal: state.controller.signal });
  } catch (err) {
    if (err.name === "AbortError") return;
    return renderError("Couldn't reach Asli", "Check that the server is running and try again.");
  }
  if (!res.ok) {
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
        renderError("Asli couldn't finish this check", ev.message || "Please try again.", ev.retryable); break;
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
  }
}

function inputPreview() {
  const lf = state.lastForm || {};
  if (!lf.text && !lf.preview) return null;
  return h("div", { class: "card input-preview" },
    lf.preview ? h("img", { src: lf.preview, alt: "Your screenshot" }) : null,
    lf.text ? h("p", { text: lf.text }) : h("p", { text: "Screenshot" }));
}

function engineTag(engine) {
  const [label, ic] = ENGINES[engine] || [engine, "search"];
  return h("span", { class: "engine" }, icon(ic), label);
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

// ------------------------------------------------------------------ report
function renderReport(r) {
  if (location.hash !== `#r=${r.id}`) history.replaceState(null, "", `#r=${r.id}`);
  const t = T[r.language] || T.en;
  const ev = Object.fromEntries((r.evidence || []).map((e) => [e.id, e]));
  const view = $("#view-report");
  const risk = r.flags.filter((f) => f.polarity === "risk");
  const trust = r.flags.filter((f) => f.polarity === "trust");

  const verdict = h("div", { class: `verdict ${r.level}` },
    h("div", { class: "verdict-top" },
      h("div", { class: "verdict-icon" }, icon(VERDICT_ICON[r.level])),
      h("div", {}, h("h2", { text: r.level_title }), h("div", { class: "sub", text: r.level_subtitle }))),
    h("p", { class: "headline", text: r.headline }),
    h("div", { class: "confidence" },
      h("span", {}, `${t.confidence}: `, h("span", { class: "conf-badge", text: t.conf[r.confidence] || r.confidence })),
      h("span", { text: r.confidence_reason }),
      r.mode === "replay" ? h("span", { class: "mode-note", text: `Recorded evidence${r.recorded_at ? " · " + r.recorded_at.slice(0, 10) : ""}` }) : null));

  const todo = h("section", { class: "section" }, h("h3", { text: t.now }),
    h("div", { class: "card todo" }, h("ol", {}, r.recommendations.map((rec) =>
      h("li", {}, rec.text, rec.link ? [" ", h("a", { href: rec.link, target: "_blank", rel: "noopener noreferrer" }, icon("external"))] : null)))));

  const why = risk.length ? h("section", { class: "section" }, h("h3", { text: t.why }),
    h("div", { class: "flags" }, risk.map((f) => flagCard(f, ev, t)))) : null;
  const ok = trust.length ? h("section", { class: "section" }, h("h3", { text: t.ok }),
    h("div", { class: "flags" }, trust.map((f) => flagCard(f, ev, t)))) : null;

  const checked = h("section", { class: "section" }, h("h3", { text: t.checked }),
    h("div", { class: "card checks" }, h("ol", { class: "timeline" },
      r.checks.length ? r.checks.map((c) => {
        const status = c.status === "done" ? "done" : c.status === "no_results" ? "empty" : "failed";
        const meta = c.status === "done" ? `${c.n_results} result${c.n_results === 1 ? "" : "s"}${c.cached ? " · cached" : ""}`
          : c.status === "no_results" ? "no results" : c.status === "skipped_quota" ? "skipped (search limit)" : "couldn't run";
        const li = h("li", { class: `step ${status}` }, h("span", { class: "ic" }, status === "done" ? icon("check") : status === "empty" ? icon("dash") : icon("x")),
          h("div", { class: "label" }, engineTag(c.engine), c.label), h("span", { class: "meta", text: meta }));
        return li;
      }) : h("li", { class: "step empty" }, h("span", { class: "ic" }, icon("dash")), h("div", { class: "label", text: r.confidence_reason }), h("span")))));

  const decided = h("section", { class: "section" }, h("details", { class: "card decided" },
    h("summary", {}, icon("chevron"), t.how),
    h("div", { class: "decided-body" },
      h("p", {}, "Asli adds up independent pieces of evidence. Each has a fixed weight (w) and a confidence (c) based on how strong its sources are. The AI only reads the message; it never sets the score."),
      h("div", { class: "formula", text: `risk = 1 − Π(1 − w·c)   trust = 1 − Π(1 − w·c)\npoints = 100 · risk · (1 − 0.75 · trust) = ${r.score}` }),
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", { text: "Signal" }), h("th", { class: "num", text: "w" }), h("th", { class: "num", text: "c" }), h("th", { class: "num", text: "w·c" }))),
        h("tbody", {}, r.flags.map((f) => h("tr", {},
          h("td", {}, h("span", { class: "code", text: f.code }), f.title),
          h("td", { class: "num", text: f.weight.toFixed(2) }), h("td", { class: "num", text: f.confidence.toFixed(2) }),
          h("td", { class: "num", text: (f.polarity === "trust" ? "−" : "+") + f.contribution.toFixed(2) })))))),
      h("p", {}, `Risk points: ${r.score}/100. This is a weighted total of evidence, not a probability. High risk needs 65+ points and at least one strong web or identity signal.`),
      (r.caps_applied || []).map((c) => h("p", { text: CAPS[c] || c })),
      h("p", { class: "mode-note", text: `Searches: ${r.stats.searches_run} (${r.stats.cache_hits} from cache, ${r.stats.credits_spent} live) · reading: ${r.stats.llm_model || r.stats.extraction} · ${Math.round(r.stats.latency_ms / 100) / 10}s` }))));

  const read = r.claims_summary.length ? h("section", { class: "section" }, h("details", { class: "card decided" },
    h("summary", {}, icon("chevron"), t.read),
    h("div", { class: "decided-body" }, h("div", { class: "claim-chips" },
      r.claims_summary.map((c) => h("span", { class: "claim" }, h("b", { text: c.label }), c.value)))))) : null;

  const copyBtn = h("button", { class: "btn ghost", type: "button" }, icon("copy"), t.copy);
  copyBtn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(summaryText(r, ev)); copyBtn.lastChild.textContent = t.copied; } catch { /* clipboard blocked */ }
  });
  const actions = h("div", { class: "report-actions" },
    h("button", { class: "btn primary", type: "button", onclick: () => { clearForm(); history.replaceState(null, "", "/"); show("view-home"); $("#text").focus(); } }, t.again),
    copyBtn);

  const urgentFirst = r.level === "HIGH_RISK" || r.level === "SUSPICIOUS";
  view.replaceChildren(...[verdict, urgentFirst ? todo : null, why, ok, urgentFirst ? null : todo, checked, decided, read, actions].filter(Boolean));
  show("view-report");
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
  return h("article", { class: `card flag ${f.severity}` },
    h("div", { class: "flag-head" }, h("span", { class: "flag-title", text: f.title }), h("span", { class: "sev", text: SEVERITY[f.severity] || f.severity })),
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
  const lines = [`Asli check: ${r.level_title.toUpperCase()}`, r.headline, ""];
  for (const f of r.flags.filter((x) => x.polarity === "risk").slice(0, 5)) {
    const src = f.evidence_ids.map((id) => ev[id]).find((e) => e && e.url && e.clickable);
    lines.push(`• ${f.title}${src ? ` (${src.data?.source || src.domain})` : ""}`);
  }
  if (r.recommendations.length) { lines.push(""); for (const rec of r.recommendations.slice(0, 4)) lines.push(`→ ${rec.text}`); }
  lines.push("", "Checked with Asli against live web evidence.");
  return lines.join("\n");
}
