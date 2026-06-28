"use strict";
const DATA = "data";
const el = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
const view = document.getElementById("view");

let SUMMARY = null;       // summary.json
let CHANGES = null;       // parsed changes.jsonl (lazy)
const idName = (id) => (SUMMARY.indices.find(i => i.id === id) || {}).name || id;

async function boot() {
  try {
    SUMMARY = await (await fetch(`${DATA}/summary.json?_=${Date.now()}`)).json();
  } catch (e) {
    view.innerHTML = `<p class="empty">Could not load <code>data/summary.json</code>. Run <code>python build_site.py</code> first.</p>`;
    return;
  }
  renderHealth();
  document.getElementById("foot-stats").textContent =
    `${SUMMARY.total_indices} indices · ${SUMMARY.total_stocks} stocks · last run ${fmtRun(SUMMARY.last_run_kst)}`;
  window.addEventListener("hashchange", route);
  document.getElementById("search").addEventListener("input", onSearch);
  route();
}

function fmtRun(iso){ if(!iso) return "—"; return iso.slice(0,16).replace("T"," ")+" KST"; }

function renderHealth() {
  const h = document.getElementById("health");
  const c = SUMMARY.counts || {};
  if (SUMMARY.unhealthy) {
    h.innerHTML = `<div class="banner bad">⚠️ Last run looked unhealthy (many indices failed/guarded) — data may be stale. Counts: ${esc(JSON.stringify(c))}</div>`;
  } else {
    h.innerHTML = `<div class="banner ok">✓ Last run healthy · ${c.changed||0} changed, ${c.initial||0} new, ${c.unchanged||0} unchanged, ${c.guarded||0} guarded · detected ${esc(SUMMARY.detect_date||"")}</div>`;
  }
}

/* ---------------- routing ---------------- */
function route() {
  const hash = location.hash || "#/";
  const m = hash.match(/^#\/(index|stock)\/(.+)$/);
  if (m && m[1] === "index") return renderIndex(decodeURIComponent(m[2]));
  if (m && m[1] === "stock") return renderStock(decodeURIComponent(m[2]));
  return renderHome();
}

/* ---------------- home / directory ---------------- */
function renderHome() {
  const frag = document.createDocumentFragment();

  // recent changes feed
  const recent = (SUMMARY.recent_changes || []).filter(r => r.type === "change");
  frag.appendChild(el(`<div class="section-title">Recent changes</div>`));
  if (!recent.length) {
    frag.appendChild(el(`<p class="empty">No membership changes recorded yet (only baseline snapshots). Changes appear here when an index reconstitutes.</p>`));
  } else {
    recent.slice(0, 25).forEach(r => frag.appendChild(changeCard(r)));
  }

  // directory by category
  frag.appendChild(el(`<div class="section-title">Directory</div>`));
  for (const cat of SUMMARY.categories) {
    const items = SUMMARY.indices.filter(i => i.category === cat.key);
    if (!items.length) continue;
    frag.appendChild(el(`<div class="cat"><h3 class="h2">${esc(cat.label)} <span class="chip">${items.length}</span></h3></div>`));
    const grid = el(`<div class="grid"></div>`);
    items.forEach(i => grid.appendChild(el(
      `<a class="card" href="#/index/${encodeURIComponent(i.id)}">
         <span class="nm">${esc(i.name)}</span><span class="ct">${i.count} members</span>
       </a>`)));
    frag.appendChild(grid);
  }

  if (SUMMARY.unavailable && SUMMARY.unavailable.length) {
    frag.appendChild(el(`<div class="notebox"><b>Not tracked</b> (no anonymous Naver source): ${SUMMARY.unavailable.map(esc).join(" · ")}. These official KRX indices are only published via data.krx.co.kr, which requires a KRX account (signup needs Korean phone/identity verification). They can be added later if KRX access becomes available.</div>`));
  }
  view.replaceChildren(frag);
}

function changeCard(r) {
  const head = `<div class="hd">
      <span><a href="#/index/${encodeURIComponent(r.index)}">${esc(r.name || r.index)}</a>
        <span class="tag ${esc(r.type)}">${esc(r.type)}</span></span>
      <span class="dt">${esc(r.date)}</span>
    </div>`;
  // 'initial' = baseline snapshot; don't dump every member as a pill.
  if (r.type === "initial") {
    return el(`<div class="change">${head}
      <div class="muted">Baseline snapshot — ${esc(r.count != null ? r.count : (r.added || []).length)} members at first tracking.</div>
    </div>`);
  }
  const adds = (r.added || []).map(a => pill(a, "add")).join("");
  const rems = (r.removed || []).map(a => pill(a, "rem")).join("");
  return el(`<div class="change">${head}
    ${adds ? `<div><span class="add">＋ Added</span> ${adds}</div>` : ""}
    ${rems ? `<div><span class="rem">－ Removed</span> ${rems}</div>` : ""}
  </div>`);
}
function pill(a, cls) {
  const sym = typeof a === "string" ? a : a.symbol;
  const nm = typeof a === "string" ? "" : a.name;
  return `<a class="pill ${cls}" href="#/stock/${encodeURIComponent(sym)}">${esc(nm)}<span class="code">${esc(sym)}</span></a>`;
}

/* ---------------- index detail ---------------- */
async function renderIndex(id) {
  view.innerHTML = `<a class="back" href="#/">← Directory</a><p class="muted">Loading ${esc(id)}…</p>`;
  let d;
  try { d = await (await fetch(`${DATA}/current/${encodeURIComponent(id)}.json?_=${Date.now()}`)).json(); }
  catch (e) { view.innerHTML = `<a class="back" href="#/">← Directory</a><p class="empty">No data for ${esc(id)}.</p>`; return; }

  const hist = await indexHistory(id);
  const frag = document.createDocumentFragment();
  frag.appendChild(el(`<a class="back" href="#/">← Directory</a>`));
  frag.appendChild(el(`<h2 class="h2">${esc(d.name)} <span class="chip">${esc(d.category)}</span></h2>`));
  frag.appendChild(el(`<p class="sub">${d.members.length} members · index id <span class="code">${esc(id)}</span></p>`));

  if (hist.length) {
    frag.appendChild(el(`<div class="section-title">Change history</div>`));
    hist.forEach(r => frag.appendChild(changeCard(r)));
  }

  frag.appendChild(el(`<div class="section-title">Current members (${d.members.length})</div>`));
  const tbl = el(`<table><thead><tr><th>#</th><th>Name</th><th>Code</th></tr></thead><tbody></tbody></table>`);
  const tb = tbl.querySelector("tbody");
  d.members.forEach((m, i) => tb.appendChild(el(
    `<tr><td class="muted">${i + 1}</td>
        <td><a href="#/stock/${encodeURIComponent(m.symbol)}">${esc(m.name)}</a></td>
        <td class="code">${esc(m.symbol)}</td></tr>`)));
  frag.appendChild(tbl);
  view.replaceChildren(frag);
}

async function loadChanges() {
  if (CHANGES) return CHANGES;
  try {
    const txt = await (await fetch(`${DATA}/changes.jsonl?_=${Date.now()}`)).text();
    CHANGES = txt.split("\n").filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  } catch { CHANGES = []; }
  return CHANGES;
}
async function indexHistory(id) {
  const all = await loadChanges();
  return all.filter(r => r.index === id).reverse();
}

/* ---------------- stock detail ---------------- */
function renderStock(sym) {
  const name = SUMMARY.stock_names[sym];
  const ids = SUMMARY.stock_index[sym] || [];
  const frag = document.createDocumentFragment();
  frag.appendChild(el(`<a class="back" href="#/">← Directory</a>`));
  if (!name && !ids.length) {
    frag.appendChild(el(`<p class="empty">No stock <span class="code">${esc(sym)}</span> in any tracked index.</p>`));
    view.replaceChildren(frag); return;
  }
  frag.appendChild(el(`<h2 class="h2">${esc(name || sym)} <span class="code">${esc(sym)}</span></h2>`));
  frag.appendChild(el(`<p class="sub">Appears in ${ids.length} tracked ${ids.length === 1 ? "index" : "indices"}.</p>`));
  const grid = el(`<div class="grid"></div>`);
  ids.forEach(id => {
    const i = SUMMARY.indices.find(x => x.id === id) || { name: id, count: "" };
    grid.appendChild(el(`<a class="card" href="#/index/${encodeURIComponent(id)}">
      <span class="nm">${esc(i.name)}</span><span class="ct">${i.count} members</span></a>`));
  });
  frag.appendChild(grid);
  view.replaceChildren(frag);
}

/* ---------------- search ---------------- */
function onSearch(e) {
  const q = e.target.value.trim().toLowerCase();
  if (!q) { route(); return; }
  const idxHits = SUMMARY.indices.filter(i => i.name.toLowerCase().includes(q) || i.id.includes(q)).slice(0, 40);
  const stockHits = Object.keys(SUMMARY.stock_names)
    .filter(s => s.includes(q) || SUMMARY.stock_names[s].toLowerCase().includes(q)).slice(0, 40);

  const frag = document.createDocumentFragment();
  frag.appendChild(el(`<div class="section-title">Indices (${idxHits.length})</div>`));
  if (idxHits.length) {
    const grid = el(`<div class="grid"></div>`);
    idxHits.forEach(i => grid.appendChild(el(`<a class="card" href="#/index/${encodeURIComponent(i.id)}">
      <span class="nm">${esc(i.name)}</span><span class="ct">${i.count} members</span></a>`)));
    frag.appendChild(grid);
  } else frag.appendChild(el(`<p class="empty">No matching index.</p>`));

  frag.appendChild(el(`<div class="section-title">Stocks (${stockHits.length})</div>`));
  if (stockHits.length) {
    const grid = el(`<div class="grid"></div>`);
    stockHits.forEach(s => grid.appendChild(el(`<a class="card" href="#/stock/${encodeURIComponent(s)}">
      <span class="nm">${esc(SUMMARY.stock_names[s])}</span><span class="ct code">${esc(s)}</span></a>`)));
    frag.appendChild(grid);
  } else frag.appendChild(el(`<p class="empty">No matching stock.</p>`));
  view.replaceChildren(frag);
}

boot();
