/* My-PI frontend. Zero external dependencies — works fully offline. */
const $ = (sel) => document.querySelector(sel);
const api = {
  async get(url) { const r = await fetch(url); return r.json(); },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(url, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json();
  },
  async del(url) { return (await fetch(url, { method: "DELETE" })).json(); },
};

let currentSlug = null;

/* ---------------- Tabs ---------------- */
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $("#tab-" + tab.dataset.tab).classList.add("active");
    if (tab.dataset.tab === "graph") graph.resize();
  });
});
function switchTab(name) {
  document.querySelector(`.tab[data-tab="${name}"]`).click();
}

/* ---------------- Status banner ---------------- */
async function refreshStatus() {
  const s = await api.get("/api/status");
  const el = $("#llm-status");
  if (s.llm && s.llm.available) {
    el.className = "status status--ok";
    el.textContent = `● LLM ready · ${s.llm.model}`;
    el.title = "";
  } else {
    el.className = "status status--bad";
    el.textContent = "● LLM offline (search still works)";
    el.title = (s.llm && s.llm.error) || "";
  }
}

/* ---------------- Note list ---------------- */
async function loadNotes(filter = "") {
  const notes = await api.get("/api/notes");
  const list = $("#note-list");
  list.innerHTML = "";
  notes
    .filter((n) => n.title.toLowerCase().includes(filter.toLowerCase()))
    .forEach((n) => {
      const li = document.createElement("li");
      if (n.slug === currentSlug) li.classList.add("active");
      li.innerHTML = `<span>${n.title}</span>` +
        (n.tags.length ? `<span class="tags">${n.tags.map((t) => "#" + t).join(" ")}</span>` : "");
      li.addEventListener("click", () => openNote(n.slug));
      list.appendChild(li);
    });
}

$("#search").addEventListener("input", (e) => loadNotes(e.target.value));

/* ---------------- Note editor ---------------- */
async function openNote(slug) {
  const note = await api.get("/api/notes/" + slug);
  currentSlug = slug;
  $("#note-title").value = note.title;
  $("#note-tags").value = note.tags.join(", ");
  $("#note-body").value = note.body;
  renderPreview(note.body);
  switchTab("note");
  loadNotes($("#search").value);
}

function newNote() {
  currentSlug = null;
  $("#note-title").value = "";
  $("#note-tags").value = "";
  $("#note-body").value = "";
  $("#note-preview").innerHTML = "";
  switchTab("note");
}
$("#new-note").addEventListener("click", newNote);

$("#note-body").addEventListener("input", (e) => renderPreview(e.target.value));

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
/* Tiny Markdown-ish preview + clickable wiki-links. */
function renderPreview(md) {
  let html = escapeHtml(md);
  html = html.replace(/^###### (.*)$/gm, "<h6>$1</h6>")
             .replace(/^##### (.*)$/gm, "<h5>$1</h5>")
             .replace(/^#### (.*)$/gm, "<h4>$1</h4>")
             .replace(/^### (.*)$/gm, "<h3>$1</h3>")
             .replace(/^## (.*)$/gm, "<h2>$1</h2>")
             .replace(/^# (.*)$/gm, "<h1>$1</h1>")
             .replace(/^\s*[-*] (.*)$/gm, "<li>$1</li>")
             .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
             .replace(/`([^`]+?)`/g, "<code>$1</code>");
  html = html.replace(/\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]/g, (m, target, alias) => {
    const label = alias || target;
    return `<a class="wikilink" data-target="${escapeHtml(target.trim())}">${escapeHtml(label)}</a>`;
  });
  html = html.replace(/\n/g, "<br>");
  const box = $("#note-preview");
  box.innerHTML = html;
  box.querySelectorAll(".wikilink").forEach((a) => {
    a.addEventListener("click", () => {
      const slug = a.dataset.target.toLowerCase().replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
      openNote(slug).catch(() => alert("That note doesn't exist yet — create it!"));
    });
  });
}

$("#save-note").addEventListener("click", async () => {
  const title = $("#note-title").value.trim();
  if (!title) return;
  const payload = {
    title,
    body: $("#note-body").value,
    tags: $("#note-tags").value.split(",").map((t) => t.trim()).filter(Boolean),
  };
  const note = currentSlug
    ? await api.put("/api/notes/" + currentSlug, payload)
    : await api.post("/api/notes", payload);
  currentSlug = note.slug;
  const msg = $("#note-msg");
  msg.textContent = "Saved ✓";
  setTimeout(() => (msg.textContent = ""), 2000);
  await loadNotes($("#search").value);
  graph.reload();
});

$("#delete-note").addEventListener("click", async () => {
  if (!currentSlug || !confirm("Delete this note?")) return;
  await api.del("/api/notes/" + currentSlug);
  newNote();
  await loadNotes();
  graph.reload();
});

/* ---------------- Ask (RAG) ---------------- */
$("#ask-btn").addEventListener("click", async () => {
  const question = $("#ask-input").value.trim();
  if (!question) return;
  const box = $("#ask-result");
  box.innerHTML = '<div class="spinner">Thinking with your local model…</div>';
  const res = await api.post("/api/query", { question, k: 5 });
  let html = "";
  if (!res.llm) {
    html += `<div class="warn">⚠ Local LLM offline — showing the most relevant notes instead.</div>`;
  }
  if (res.answer) {
    html += `<div class="answer">${escapeHtml(res.answer)}</div>`;
    if (res.reasoning) html += `<details><summary class="reasoning">reasoning</summary><div class="reasoning">${escapeHtml(res.reasoning)}</div></details>`;
  }
  html += renderSources(res.sources);
  box.innerHTML = html;
  wireSourceChips(box);
});

function renderSources(sources) {
  if (!sources || !sources.length) return "";
  return `<div class="sources">${sources
    .map((s) => `<span class="chip" data-slug="${s.slug}">${s.title}${s.score ? " · " + s.score : ""}</span>`)
    .join("")}</div>`;
}
function wireSourceChips(box) {
  box.querySelectorAll(".chip").forEach((c) =>
    c.addEventListener("click", () => openNote(c.dataset.slug)));
}

/* ---------------- Generate (custom format) ---------------- */
const DEFAULT_FORMAT =
`# {title}

## Summary
_One paragraph overview._

## Key Points
-

## Details

## Related
- [[ ]]

## References
`;
$("#gen-format").value = DEFAULT_FORMAT;

$("#gen-btn").addEventListener("click", async () => {
  const topic = $("#gen-topic").value.trim();
  if (!topic) return;
  const box = $("#gen-result");
  box.innerHTML = '<div class="spinner">Drafting with DSPy + your local model…</div>';
  const res = await api.post("/api/generate", {
    topic,
    format_spec: $("#gen-format").value,
    k: 4,
    save: $("#gen-save").checked,
  });
  if (res.detail) {
    box.innerHTML = `<div class="warn">${escapeHtml(res.detail)}</div>`;
    return;
  }
  let html = `<div class="answer">${escapeHtml(res.note)}</div>`;
  if (res.tags && res.tags.length) {
    html += `<div>${res.tags.map((t) => `<span class="tag-pill">#${t}</span>`).join("")}</div>`;
  }
  if (res.saved) {
    html += `<p class="msg">Saved to vault as "${res.saved}" ✓</p>`;
    await loadNotes();
    graph.reload();
  }
  box.innerHTML = html;
});

/* =====================================================================
   Force-directed graph (canvas, no libraries)
   ===================================================================== */
const graph = (() => {
  const canvas = $("#graph");
  const ctx = canvas.getContext("2d");
  let nodes = [], edges = [], byId = {};
  let scale = 1, offX = 0, offY = 0;
  let dragNode = null, panning = false, lastX = 0, lastY = 0;
  let hoverNode = null;
  const colors = { note: "#7aa2f7", tag: "#bb9af7", missing: "#f7768e" };

  function resize() {
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
  }
  window.addEventListener("resize", resize);

  async function reload() {
    const showTags = $("#show-tags").checked;
    const data = await api.get("/api/graph?tags=" + showTags);
    const cx = (canvas.clientWidth || 600) / 2;
    const cy = (canvas.clientHeight || 400) / 2;
    byId = {};
    nodes = data.nodes.map((n, i) => {
      const angle = (i / Math.max(1, data.nodes.length)) * Math.PI * 2;
      const node = {
        ...n,
        x: cx + Math.cos(angle) * 180 + (Math.random() - 0.5) * 40,
        y: cy + Math.sin(angle) * 180 + (Math.random() - 0.5) * 40,
        vx: 0, vy: 0,
      };
      byId[n.id] = node;
      return node;
    });
    edges = data.edges.filter((e) => byId[e.source] && byId[e.target]);
    resize();
  }

  /* One tick of a simple force simulation. */
  function tick() {
    const k = 0.01;      // repulsion
    const spring = 0.02; // attraction
    const center = 0.002;
    const cx = canvas.width / 2, cy = canvas.height / 2;

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      a.vx += (cx - a.x) * center;
      a.vy += (cy - a.y) * center;
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy || 0.01;
        const f = (k * 2000) / d2;
        const d = Math.sqrt(d2);
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
      }
    }
    for (const e of edges) {
      const a = byId[e.source], b = byId[e.target];
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const target = e.type === "tag" ? 60 : 110;
      const f = (d - target) * spring;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
    }
    for (const n of nodes) {
      if (n === dragNode) continue;
      n.vx *= 0.85; n.vy *= 0.85;
      n.x += n.vx; n.y += n.vy;
    }
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(offX, offY);
    ctx.scale(scale, scale);

    ctx.lineWidth = 1;
    for (const e of edges) {
      const a = byId[e.source], b = byId[e.target];
      ctx.strokeStyle = e.type === "tag" ? "rgba(187,154,247,0.25)" : "rgba(122,162,247,0.35)";
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    for (const n of nodes) {
      const r = n.type === "tag" ? 4 : Math.min(14, 5 + (n.degree || 0) * 1.6);
      ctx.beginPath();
      ctx.fillStyle = colors[n.type] || "#9aa5ce";
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fill();
      if (n === hoverNode) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke(); }
      if (n.type !== "tag" || n === hoverNode) {
        ctx.fillStyle = "#c0caf5";
        ctx.font = "11px sans-serif";
        ctx.fillText(n.label, n.x + r + 3, n.y + 4);
      }
    }
    ctx.restore();
  }

  function loop() { tick(); draw(); requestAnimationFrame(loop); }

  /* --- interaction --- */
  function toWorld(mx, my) { return { x: (mx - offX) / scale, y: (my - offY) / scale }; }
  function nodeAt(mx, my) {
    const p = toWorld(mx, my);
    for (const n of nodes) {
      const r = (n.type === "tag" ? 4 : 12) + 4;
      if ((n.x - p.x) ** 2 + (n.y - p.y) ** 2 < r * r) return n;
    }
    return null;
  }
  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    dragNode = nodeAt(mx, my);
    if (!dragNode) { panning = true; lastX = mx; lastY = my; }
  });
  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    if (dragNode) { const p = toWorld(mx, my); dragNode.x = p.x; dragNode.y = p.y; dragNode.vx = dragNode.vy = 0; }
    else if (panning) { offX += mx - lastX; offY += my - lastY; lastX = mx; lastY = my; }
    else { hoverNode = nodeAt(mx, my); canvas.style.cursor = hoverNode ? "pointer" : "grab"; }
  });
  window.addEventListener("mouseup", () => {
    if (dragNode && !panning) {
      // A click without much drag = open the note.
    }
    dragNode = null; panning = false;
  });
  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const n = nodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (n && (n.type === "note" || n.type === "missing")) openNote(n.slug).catch(() => {});
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    offX = mx - (mx - offX) * factor;
    offY = my - (my - offY) * factor;
    scale *= factor;
  }, { passive: false });

  $("#refresh-graph").addEventListener("click", reload);
  $("#show-tags").addEventListener("change", reload);

  loop(); // start the render/simulation loop
  return { reload, resize };
})();

/* ---------------- Boot ---------------- */
(async function init() {
  await loadNotes();
  await graph.reload();
  graph.resize();
  refreshStatus();
  setInterval(refreshStatus, 15000);
})();
