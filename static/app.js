// static/app.js
const PHASE_PRESETS = [
  { name: "Seedling",   abbr: "SEED" },
  { name: "Vegetative", abbr: "VEG" },
  { name: "Bloom",      abbr: "BLOOM" },
];

let state = {
  cam: null, frames: [], config: null,
  playheadIdx: 0, minDate: null, maxDate: null,
};

// ── API ──────────────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const r = await fetch(path, {
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`);
  return r.json();
}

// ── Date helpers ─────────────────────────────────────────────────────────────

function dateToFrac(d) {
  if (!state.minDate || !state.maxDate) return 0;
  const min = new Date(state.minDate), max = new Date(state.maxDate);
  return (new Date(d) - min) / (max - min);
}

function fracToDate(f) {
  const min = new Date(state.minDate), max = new Date(state.maxDate);
  return new Date(min.getTime() + f * (max - min)).toISOString().slice(0, 10);
}

function frameToDate(filename) {
  const m = filename.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

// ── Render ───────────────────────────────────────────────────────────────────

function renderRuler() {
  const el = document.getElementById("ruler");
  el.innerHTML = "";
  if (!state.minDate) return;
  const min = new Date(state.minDate), max = new Date(state.maxDate);
  const days = (max - min) / 86400000;
  const step = days < 14 ? 1 : days < 60 ? 7 : 30;
  for (let d = new Date(min); d <= max; d.setDate(d.getDate() + step)) {
    const frac = (d - min) / (max - min);
    const tick = document.createElement("span");
    tick.className = "rtick";
    tick.style.left = `${frac * 100}%`;
    tick.textContent = d.toISOString().slice(5, 10);
    el.appendChild(tick);
  }
}

function renderPhases() {
  const track = document.getElementById("phase-track");
  track.innerHTML = "";
  if (!state.config) return;
  const phases = state.config.phases;
  phases.forEach((p, i) => {
    const startFrac = dateToFrac(p.start);
    const endDate = i + 1 < phases.length ? phases[i + 1].start : state.maxDate;
    const endFrac = dateToFrac(endDate);
    const seg = document.createElement("div");
    seg.className = `phase-seg ${p.abbr}`;
    seg.style.left = `${startFrac * 100}%`;
    seg.style.width = `${(endFrac - startFrac) * 100}%`;
    seg.textContent = p.name;
    // Drag handle on right edge
    const handle = document.createElement("div");
    handle.className = "phase-handle";
    handle.textContent = "⋮";
    makeDraggable(handle, (frac) => {
      const newDate = fracToDate(frac);
      if (i + 1 < phases.length) phases[i + 1].start = newDate;
      else phases[i].start = newDate;
      saveConfig();
    });
    seg.appendChild(handle);
    track.appendChild(seg);
  });
}

function renderSlowZones() {
  const track = document.getElementById("speed-track");
  track.innerHTML = "";
  if (!state.config) return;
  state.config.slow_zones.forEach((z, i) => {
    const sf = dateToFrac(z.start), ef = dateToFrac(z.end);
    const el = document.createElement("div");
    el.className = "slow-zone";
    el.style.left = `${sf * 100}%`;
    el.style.width = `${(ef - sf) * 100}%`;
    el.title = `${z.label} · ${z.fps}fps`;
    el.textContent = z.label || `${z.fps}fps`;
    // Drag whole zone
    makeDraggable(el, (frac, startFrac) => {
      const width = ef - sf;
      z.start = fracToDate(Math.max(0, frac - width / 2));
      z.end   = fracToDate(Math.min(1, frac + width / 2));
      saveConfig();
    }, true);
    // Right handle (resize end)
    const rh = document.createElement("div");
    rh.className = "phase-handle";
    rh.style.right = "0"; rh.style.position = "absolute";
    makeDraggable(rh, (frac) => { z.end = fracToDate(frac); saveConfig(); });
    el.appendChild(rh);
    track.appendChild(el);
  });
}

function renderNotes() {
  const track = document.getElementById("note-track");
  track.innerHTML = "";
  if (!state.config) return;
  state.config.notes.forEach((n, i) => {
    const sf = dateToFrac(n.start);
    // Approximate width: duration_s / total estimated output seconds
    const totalDays = (new Date(state.maxDate) - new Date(state.minDate)) / 86400000;
    const estTotalS = (totalDays * 288) / state.config.normal_fps; // rough
    const widthFrac = Math.max(0.01, n.duration_s / estTotalS);
    const el = document.createElement("div");
    el.className = "note-bar";
    el.style.left = `${sf * 100}%`;
    el.style.width = `${widthFrac * 100}%`;
    el.innerHTML = `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${n.text}</span>
                    <span class="nb-dur">${n.duration_s}s</span>`;
    const rh = document.createElement("div");
    rh.className = "note-handle";
    makeDraggable(rh, (frac) => {
      const startFrac = dateToFrac(n.start);
      const newWidthFrac = Math.max(0.005, frac - startFrac);
      n.duration_s = Math.round(newWidthFrac * estTotalS * 10) / 10;
      saveConfig();
    });
    el.appendChild(rh);
    track.appendChild(el);
  });
}

function renderThumbs() {
  const strip = document.getElementById("thumbstrip");
  strip.innerHTML = "";
  const sample = state.frames.filter((_, i) => i % Math.max(1, Math.floor(state.frames.length / 30)) === 0);
  sample.forEach((filename, i) => {
    const div = document.createElement("div");
    div.className = "thumb" + (i === 0 ? " active" : "");
    const img = document.createElement("img");
    img.src = `/api/cameras/${state.cam}/frames/${filename}`;
    img.loading = "lazy";
    div.appendChild(img);
    div.onclick = () => setPlayhead(state.frames.indexOf(filename));
    strip.appendChild(div);
  });
}

function renderAll() {
  renderRuler();
  renderPhases();
  renderSlowZones();
  renderNotes();
  renderEstimate();
}

function renderEstimate() {
  const el = document.getElementById("estimate-text");
  const tot = document.getElementById("estimate-total");
  if (!state.config || !state.frames.length) { el.textContent = "No frames"; return; }
  const normalFrames = state.frames.length;
  const slowS = state.config.slow_zones.reduce((acc, z) => {
    const days = (new Date(z.end) - new Date(z.start)) / 86400000;
    const frameCount = days * 288; // ~288 frames/day at 5min intervals
    return acc + frameCount * (state.config.normal_fps / z.fps - 1) / state.config.normal_fps;
  }, 0);
  const totalS = normalFrames / state.config.normal_fps + slowS;
  const mm = Math.floor(totalS / 60), ss = Math.round(totalS % 60);
  el.textContent = `${state.frames.length} frames`;
  tot.textContent = `≈ ${mm}:${String(ss).padStart(2, "0")} output`;
}

// ── Drag helper ──────────────────────────────────────────────────────────────

function makeDraggable(el, onFrac, wholeEl = false) {
  el.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    e.preventDefault();
    const track = el.closest(".track") || el.parentElement.closest(".track");
    const rect = track.getBoundingClientRect();
    const move = (ev) => {
      const frac = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
      onFrac(frac);
      renderAll();
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
}

// ── State mutations ──────────────────────────────────────────────────────────

function setPlayhead(idx) {
  state.playheadIdx = Math.max(0, Math.min(idx, state.frames.length - 1));
  const filename = state.frames[state.playheadIdx];
  document.getElementById("preview-img").src = `/api/cameras/${state.cam}/frames/${filename}`;
  document.getElementById("preview-time").textContent = filename.replace(".jpg", "").replace(".webp", "");
  // Highlight active thumb
  document.querySelectorAll(".thumb").forEach((t, i) => t.classList.toggle("active", i === state.playheadIdx));
}

async function saveConfig() {
  await api("PUT", `/api/cameras/${state.cam}/config`, state.config);
  renderAll();
}

// ── App actions ──────────────────────────────────────────────────────────────

window.App = {
  addPhase() {
    const cur = state.frames[state.playheadIdx];
    const d = cur ? frameToDate(cur) : state.minDate;
    const preset = PHASE_PRESETS[state.config.phases.length % PHASE_PRESETS.length];
    state.config.phases.push({ ...preset, start: d });
    state.config.phases.sort((a, b) => a.start.localeCompare(b.start));
    saveConfig();
  },
  addSlowZone() {
    const cur = state.frames[state.playheadIdx];
    const d = cur ? frameToDate(cur) : state.minDate;
    const end = new Date(new Date(d).getTime() + 2 * 86400000).toISOString().slice(0, 10);
    state.config.slow_zones.push({ label: "Slow Zone", start: d, end, fps: 3, ramp_in_s: 4, ramp_out_s: 4 });
    saveConfig();
  },
  addNote() {
    const cur = state.frames[state.playheadIdx];
    const d = cur ? frameToDate(cur) : state.minDate;
    const text = prompt("Note text:") || "Note";
    state.config.notes.push({ text, start: d, duration_s: 5 });
    saveConfig();
  },
  async encode() {
    const status = document.getElementById("encode-status");
    status.textContent = "Starting encode…";
    const es = new EventSource(`/api/cameras/${state.cam}/encode`);
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.status === "encoding") status.textContent = `Encoding… ${d.pct}%`;
      if (d.status === "done") { status.textContent = `Done: ${d.output}`; es.close(); }
      if (d.status === "error") { status.textContent = `Error: ${d.message}`; es.close(); }
    };
  },
};

// ── Init ─────────────────────────────────────────────────────────────────────

async function selectCamera(cam) {
  state.cam = cam;
  const [framesRes, cfg] = await Promise.all([
    api("GET", `/api/cameras/${cam}/frames`),
    api("GET", `/api/cameras/${cam}/config`),
  ]);
  state.frames = framesRes.frames;
  state.config = cfg;
  state.minDate = frameToDate(state.frames[0]);
  state.maxDate = frameToDate(state.frames[state.frames.length - 1]);
  document.getElementById("frame-stat").textContent = `${state.frames.length} frames`;
  document.getElementById("date-stat").textContent = `${state.minDate} – ${state.maxDate}`;
  renderThumbs();
  setPlayhead(0);
  renderAll();
}

async function init() {
  const cams = await api("GET", "/api/cameras");
  const sel = document.getElementById("cam-select");
  cams.cameras.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.name; opt.textContent = `${c.name} (${c.frame_count} frames)`;
    sel.appendChild(opt);
  });
  sel.onchange = () => selectCamera(sel.value);
  if (cams.cameras.length) selectCamera(cams.cameras[0].name);
}

init();
