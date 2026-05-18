"""
Web UI for browsing the fanfic knowledge base.

    python tools/db_explorer.py             # http://localhost:7860
    python tools/db_explorer.py --port 8000
"""

import argparse
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from mcp_scraper import database, vector_store
from mcp_scraper.config import CACHE_TTL_DAYS

database.init_db()

app = FastAPI(title="Fanfic Knowledge Base Explorer", docs_url=None, redoc_url=None)


@app.middleware("http")
async def no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/api/stats")
def api_stats():
    entities = database.list_entities()
    total_chunks = vector_store.count()

    fandom_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for e in entities:
        fandom_counts[e.fandom] = fandom_counts.get(e.fandom, 0) + 1
        type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1

    fresh = sum(1 for e in entities if database.is_cache_fresh(e))
    return {
        "entity_count":  len(entities),
        "vector_chunks": total_chunks,
        "fandom_count":  len(fandom_counts),
        "fresh_count":   fresh,
        "stale_count":   len(entities) - fresh,
        "cache_ttl_days": CACHE_TTL_DAYS,
        "by_fandom": dict(sorted(fandom_counts.items(), key=lambda x: -x[1])),
        "by_type":   type_counts,
    }


@app.get("/api/fandoms")
def api_fandoms():
    entities = database.list_entities()
    return {"fandoms": sorted({e.fandom for e in entities})}


@app.get("/api/entities")
def api_entities(
    fandom: str = Query(default=""),
    type: str = Query(default=""),
    q: str = Query(default=""),
):
    entities = database.list_entities(fandom=fandom or None, entity_type=type or None)
    if q:
        ql = q.lower()
        entities = [e for e in entities if ql in e.name.lower() or ql in (e.description or "").lower()]

    return {
        "entities": [
            {
                "id":           e.id,
                "name":         e.name,
                "fandom":       e.fandom,
                "entity_type":  e.entity_type,
                "description":  (e.description or "")[:200],
                "source_url":   e.source_url,
                "source_type":  e.source_type,
                "last_scraped": e.last_scraped_at.isoformat() if e.last_scraped_at else None,
                "cache_fresh":  database.is_cache_fresh(e),
            }
            for e in entities
        ],
        "count": len(entities),
    }


@app.get("/api/entities/{entity_id}")
def api_entity_detail(entity_id: int):
    with database._get_conn() as conn:
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = database._row_to_entity(row)
    attrs  = database.get_attributes(entity_id)

    try:
        chunks = vector_store.search(entity.name, n_results=20, fandom=entity.fandom)
    except (ValueError, ModuleNotFoundError):
        chunks = []

    return {
        "id":           entity.id,
        "name":         entity.name,
        "fandom":       entity.fandom,
        "entity_type":  entity.entity_type,
        "description":  entity.description,
        "source_url":   entity.source_url,
        "source_type":  entity.source_type,
        "last_scraped": entity.last_scraped_at.isoformat() if entity.last_scraped_at else None,
        "cache_fresh":  database.is_cache_fresh(entity),
        "attributes":   attrs,
        "chunk_count":  len(chunks),
    }


@app.get("/api/entities/{entity_id}/chunks")
def api_entity_chunks(entity_id: int):
    with database._get_conn() as conn:
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = database._row_to_entity(row)
    try:
        chunks = vector_store.search(entity.name, n_results=50, fandom=entity.fandom)
    except (ValueError, ModuleNotFoundError):
        chunks = []
    return {"entity_id": entity_id, "chunks": chunks, "count": len(chunks)}


@app.get("/api/search")
def api_search(
    q: str = Query(..., min_length=1),
    fandom: str = Query(default=""),
    type: str = Query(default=""),
    n: int = Query(default=10, ge=1, le=50),
):
    try:
        hits = vector_store.search(query=q, n_results=n, fandom=fandom or None, chunk_type=type or None)
    except (ValueError, ModuleNotFoundError) as e:
        if "sentence_transformers" in str(e):
            return {
                "query": q, "results": [], "count": 0,
                "error": "sentence_transformers not installed — run: pip install sentence_transformers",
            }
        raise
    return {"query": q, "results": hits, "count": len(hits)}


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fanfic Knowledge Base</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2d3148;
    --accent: #7c6ff7; --accent2: #5eead4;
    --text: #e2e4f0; --muted: #8b8fa8; --danger: #f87171;
    --success: #4ade80; --warning: #fbbf24;
    --card-hover: #222538;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }

  .layout { display: grid; grid-template-columns: 260px 1fr; grid-template-rows: 56px 1fr; height: 100vh; }
  .topbar { grid-column: 1/-1; background: var(--surface); border-bottom: 1px solid var(--border);
            display: flex; align-items: center; gap: 12px; padding: 0 20px; }
  .sidebar { background: var(--surface); border-right: 1px solid var(--border); overflow-y: auto; padding: 16px 12px; }
  .main { overflow-y: auto; padding: 20px; }

  .logo { font-size: 1.1rem; font-weight: 700; color: var(--accent); letter-spacing: .5px; white-space: nowrap; }
  .search-bar { flex: 1; max-width: 500px; position: relative; }
  .search-bar input { width: 100%; padding: 7px 14px; background: var(--bg); border: 1px solid var(--border);
                      border-radius: 8px; color: var(--text); font-size: .9rem; outline: none; }
  .search-bar input:focus { border-color: var(--accent); }
  .tab-btns { display: flex; gap: 4px; margin-left: auto; }
  .tab-btn { padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border);
             background: transparent; color: var(--muted); cursor: pointer; font-size: .85rem; transition: all .15s; }
  .tab-btn.active, .tab-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
  .refresh-btn { padding: 6px 12px; border-radius: 7px; border: 1px solid var(--border);
                 background: transparent; color: var(--muted); cursor: pointer; font-size: .85rem;
                 transition: all .15s; display: flex; align-items: center; gap: 5px; }
  .refresh-btn:hover { border-color: var(--accent2); color: var(--accent2); }
  .refresh-btn.spinning svg { animation: spin .6s linear infinite; }

  .sidebar-section { margin-bottom: 20px; }
  .sidebar-label { font-size: .7rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 8px; }
  .stat-row { display: flex; justify-content: space-between; align-items: center;
              padding: 5px 0; font-size: .85rem; border-bottom: 1px solid var(--border); }
  .stat-val { font-weight: 600; color: var(--accent2); }
  .fandom-chip { display: flex; align-items: center; justify-content: space-between;
                 padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: .82rem;
                 transition: background .12s; border: 1px solid transparent; margin-bottom: 3px; }
  .fandom-chip:hover { background: var(--card-hover); }
  .fandom-chip.active { background: var(--accent)22; border-color: var(--accent); color: var(--accent); }
  .fandom-chip .cnt { font-size: .72rem; background: var(--border); border-radius: 4px; padding: 1px 5px; }
  .type-filters { display: flex; flex-wrap: wrap; gap: 5px; }
  .type-btn { padding: 3px 10px; border-radius: 20px; border: 1px solid var(--border);
              background: transparent; color: var(--muted); cursor: pointer; font-size: .78rem; transition: all .12s; }
  .type-btn.active { background: var(--accent2)22; border-color: var(--accent2); color: var(--accent2); }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
  .entity-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
                 padding: 14px; cursor: pointer; transition: all .15s; }
  .entity-card:hover { border-color: var(--accent); background: var(--card-hover); transform: translateY(-1px); }
  .card-header { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
  .card-name { font-weight: 600; font-size: .95rem; flex: 1; }
  .badge { font-size: .68rem; padding: 2px 7px; border-radius: 20px; font-weight: 500; white-space: nowrap; }
  .badge-character { background: #7c6ff722; color: #a89ef8; border: 1px solid #7c6ff744; }
  .badge-place     { background: #5eead422; color: #5eead4; border: 1px solid #5eead444; }
  .badge-concept   { background: #fbbf2422; color: #fbbf24; border: 1px solid #fbbf2444; }
  .badge-event     { background: #f8717122; color: #f87171; border: 1px solid #f8717144; }
  .card-fandom { font-size: .75rem; color: var(--muted); margin-bottom: 6px; }
  .card-desc { font-size: .8rem; color: var(--muted); line-height: 1.45; display: -webkit-box;
               -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .card-footer { margin-top: 10px; display: flex; justify-content: space-between; align-items: center; font-size: .72rem; }
  .fresh-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 4px; }
  .fresh { background: var(--success); }
  .stale { background: var(--warning); }

  .panel-overlay { display: none; position: fixed; inset: 0; background: #000a; z-index: 100; }
  .panel-overlay.open { display: flex; align-items: stretch; justify-content: flex-end; }
  .panel { width: min(700px, 95vw); background: var(--surface); border-left: 1px solid var(--border);
           overflow-y: auto; display: flex; flex-direction: column; }
  .panel-head { padding: 20px 24px 16px; border-bottom: 1px solid var(--border); position: sticky; top: 0;
                background: var(--surface); z-index: 1; }
  .panel-title { font-size: 1.3rem; font-weight: 700; margin-bottom: 4px; }
  .panel-meta { font-size: .8rem; color: var(--muted); display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .close-btn { margin-left: auto; background: var(--border); border: none; color: var(--text);
               width: 28px; height: 28px; border-radius: 6px; cursor: pointer; font-size: 1rem;
               display: flex; align-items: center; justify-content: center; }
  .close-btn:hover { background: var(--danger); }
  .panel-body { padding: 20px 24px; flex: 1; }
  .attr-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
  .attr-tab { padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border);
              background: transparent; color: var(--muted); cursor: pointer; font-size: .8rem; transition: all .12s; }
  .attr-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .attr-content { font-size: .88rem; line-height: 1.6; color: var(--text); white-space: pre-wrap; word-break: break-word; }
  .source-link { display: inline-flex; align-items: center; gap: 5px; color: var(--accent); font-size: .8rem; text-decoration: none; }
  .source-link:hover { text-decoration: underline; }

  .search-results { display: flex; flex-direction: column; gap: 12px; }
  .result-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
  .result-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .result-entity { font-weight: 600; font-size: .92rem; }
  .score-badge { font-size: .72rem; padding: 2px 8px; border-radius: 20px; margin-left: auto; }
  .score-high  { background: #4ade8022; color: #4ade80; border: 1px solid #4ade8044; }
  .score-mid   { background: #fbbf2422; color: #fbbf24; border: 1px solid #fbbf2444; }
  .score-low   { background: #f8717122; color: #f87171; border: 1px solid #f8717144; }
  .result-text { font-size: .83rem; color: var(--muted); line-height: 1.5; }

  .empty-state { text-align: center; padding: 60px 20px; color: var(--muted); }
  .empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
  .count-label { font-size: .8rem; color: var(--muted); margin-bottom: 14px; }
  .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid var(--border);
             border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  a { color: inherit; }

  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="layout">

  <header class="topbar">
    <span class="logo">&#9997; Fanfic KB</span>
    <div class="search-bar">
      <input id="search-input" type="text" placeholder="Semantic search across all stored knowledge…" autocomplete="off">
    </div>
    <div class="tab-btns">
      <button class="tab-btn active" onclick="showTab('entities')">Entities</button>
      <button class="tab-btn" onclick="showTab('search')">Search</button>
    </div>
    <button class="refresh-btn" id="refresh-btn" title="Reload from database">
      <svg id="refresh-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M1 4v6h6M23 20v-6h-6"/>
        <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
      </svg>
      Refresh
    </button>
  </header>

  <aside class="sidebar">
    <div class="sidebar-section">
      <div class="sidebar-label">Overview</div>
      <div id="stats-panel"><div class="spinner"></div></div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">Type</div>
      <div class="type-filters" id="type-filters">
        <button class="type-btn active" data-type="">All</button>
        <button class="type-btn" data-type="character">Character</button>
        <button class="type-btn" data-type="place">Place</button>
        <button class="type-btn" data-type="concept">Concept</button>
        <button class="type-btn" data-type="event">Event</button>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">Fandoms</div>
      <div id="fandom-list"><div class="spinner"></div></div>
    </div>
  </aside>

  <main class="main">
    <div id="tab-entities">
      <div class="count-label" id="entity-count"></div>
      <div class="grid" id="entity-grid"></div>
    </div>
    <div id="tab-search" style="display:none">
      <p class="count-label" id="search-count">Type a query above and press Enter.</p>
      <div class="search-results" id="search-results"></div>
    </div>
  </main>

</div>

<div class="panel-overlay" id="panel-overlay">
  <div class="panel" id="detail-panel" onclick="event.stopPropagation()">
    <div class="panel-head">
      <div style="display:flex;align-items:flex-start;gap:10px">
        <div style="flex:1">
          <div class="panel-title" id="panel-title">—</div>
          <div class="panel-meta" id="panel-meta"></div>
        </div>
        <button class="close-btn" onclick="closePanelDirect()">&#x2715;</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="attr-tabs" id="attr-tabs"></div>
      <div class="attr-content" id="attr-content"></div>
    </div>
  </div>
</div>

<script>
let activeFandom = '';
let activeType   = '';
let activeTab    = 'entities';
let panelData    = {};

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function relativeDate(iso) {
  if (!iso) return 'never';
  const d = Math.floor((Date.now() - new Date(iso)) / 86400000);
  return d === 0 ? 'today' : d === 1 ? 'yesterday' : d + 'd ago';
}
function apiUrl(path, params) {
  const p = new URLSearchParams(params || {});
  p.set('_t', Date.now());
  return path + '?' + p.toString();
}
async function apiFetch(path, params) {
  const r = await fetch(apiUrl(path, params), { cache: 'no-store' });
  if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + path);
  return r.json();
}

async function doReload() {
  await loadStats().catch(e => showSectionError('stats-panel', e));
  await loadFandoms().catch(e => showSectionError('fandom-list', e));
  await loadEntities().catch(e => showSectionError('entity-grid', e));
}

function showSectionError(elId, err) {
  const el = document.getElementById(elId);
  if (el) el.innerHTML = '<span style="color:var(--danger);font-size:.78rem">Error: ' + esc(err.message) + '</span>';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('refresh-btn').addEventListener('click', async () => {
    const btn = document.getElementById('refresh-btn');
    btn.classList.add('spinning'); btn.disabled = true;
    await doReload();
    btn.classList.remove('spinning'); btn.disabled = false;
  });

  document.getElementById('search-input').addEventListener('keydown', ev => {
    if (ev.key === 'Enter') runSearch(ev.target.value);
  });
  let searchTimer;
  document.getElementById('search-input').addEventListener('input', ev => {
    clearTimeout(searchTimer);
    const v = ev.target.value;
    if (v.length > 2) searchTimer = setTimeout(() => runSearch(v), 600);
    else if (!v) showTab('entities');
  });

  document.querySelectorAll('.type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeType = btn.dataset.type;
      document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (activeTab === 'entities') loadEntities().catch(console.error);
    });
  });

  document.getElementById('panel-overlay').addEventListener('click', ev => {
    if (ev.target === ev.currentTarget) closePanelDirect();
  });

  doReload();
});

async function loadStats() {
  const d = await apiFetch('/api/stats');
  document.getElementById('stats-panel').innerHTML =
    row('Entities',      d.entity_count) +
    row('Vector chunks', d.vector_chunks) +
    row('Fandoms',       d.fandom_count) +
    row('Fresh',         d.fresh_count,  'var(--success)') +
    row('Stale',         d.stale_count,  'var(--warning)') +
    row('Cache TTL',     d.cache_ttl_days + 'd');
}
function row(label, val, color) {
  const style = color ? ' style="color:' + color + '"' : '';
  return '<div class="stat-row"><span>' + label + '</span><span class="stat-val"' + style + '>' + val + '</span></div>';
}

async function loadFandoms() {
  const d = await apiFetch('/api/stats');
  const list = document.getElementById('fandom-list');
  const entries = Object.entries(d.by_fandom || {});
  if (!entries.length) {
    list.innerHTML = '<span style="color:var(--muted);font-size:.8rem">No fandoms yet</span>';
    return;
  }
  list.innerHTML = chip('', 'All', entries.reduce((s,[,v])=>s+v,0)) +
    entries.map(([f,c]) => chip(f, f, c)).join('');
  list.querySelectorAll('.fandom-chip').forEach(el =>
    el.addEventListener('click', () => setFandom(el.dataset.fandom))
  );
}
function chip(fandom, label, count) {
  const active = activeFandom === fandom ? ' active' : '';
  return '<div class="fandom-chip' + active + '" data-fandom="' + esc(fandom) + '">' +
    '<span>' + esc(label) + '</span><span class="cnt">' + count + '</span></div>';
}

async function loadEntities() {
  const params = {};
  if (activeFandom) params.fandom = activeFandom;
  if (activeType)   params.type   = activeType;
  const d = await apiFetch('/api/entities', params);

  document.getElementById('entity-count').textContent =
    d.count + ' entit' + (d.count === 1 ? 'y' : 'ies');

  const grid = document.getElementById('entity-grid');
  if (!d.entities || !d.entities.length) {
    grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1">' +
      '<div class="empty-icon">&#128237;</div>No entities stored yet.</div>';
    return;
  }

  grid.innerHTML = '';
  d.entities.forEach(e => {
    const card = document.createElement('div');
    card.className = 'entity-card';
    card.innerHTML =
      '<div class="card-header">' +
        '<div class="card-name">' + esc(e.name) + '</div>' +
        '<span class="badge badge-' + esc(e.entity_type) + '">' + esc(e.entity_type) + '</span>' +
      '</div>' +
      '<div class="card-fandom">' + esc(e.fandom) + ' &middot; ' + esc(e.source_type||'unknown') + '</div>' +
      '<div class="card-desc">' + esc(e.description || 'No description available.') + '</div>' +
      '<div class="card-footer">' +
        '<span><span class="fresh-dot ' + (e.cache_fresh?'fresh':'stale') + '"></span>' +
        (e.cache_fresh ? 'Fresh' : 'Stale') + '</span>' +
        '<span>' + relativeDate(e.last_scraped) + '</span>' +
      '</div>';
    card.addEventListener('click', () => openEntity(e.id));
    grid.appendChild(card);
  });
}

async function openEntity(id) {
  document.getElementById('panel-overlay').classList.add('open');
  document.getElementById('panel-title').textContent = '…';
  document.getElementById('panel-meta').innerHTML = '<div class="spinner"></div>';
  document.getElementById('attr-tabs').innerHTML = '';
  document.getElementById('attr-content').textContent = '';

  let e, chunks;
  try {
    [e, chunks] = await Promise.all([
      apiFetch('/api/entities/' + id),
      apiFetch('/api/entities/' + id + '/chunks').catch(() => ({ chunks: [] }))
    ]);
  } catch (err) {
    document.getElementById('panel-title').textContent = 'Failed to load';
    document.getElementById('panel-meta').innerHTML =
      '<span style="color:var(--danger);font-size:.8rem">' + esc(err.message) + '</span>';
    return;
  }

  document.getElementById('panel-title').textContent = e.name;
  document.getElementById('panel-meta').innerHTML =
    '<span class="badge badge-' + esc(e.entity_type) + '">' + esc(e.entity_type) + '</span>' +
    '<span>' + esc(e.fandom) + '</span>' +
    (e.source_url ? '<a href="' + esc(e.source_url) + '" target="_blank" class="source-link">&#x2197; ' + esc(e.source_type||'source') + '</a>' : '') +
    '<span style="margin-left:auto;color:' + (e.cache_fresh?'var(--success)':'var(--warning)') + '">' +
    (e.cache_fresh ? '&#x2713; Fresh' : '&#x26A0; Stale') + ' &middot; ' + (chunks.count||0) + ' chunks</span>';

  panelData = { attrs: { description: e.description || '', ...e.attributes }, chunks: chunks.chunks || [] };

  const attrKeys = Object.keys(panelData.attrs).filter(k => panelData.attrs[k]);
  const tabs = [...attrKeys.map((k,i) =>
    '<button class="attr-tab' + (i===0?' active':'') + '" data-key="' + esc(k) + '">' + esc(k) + '</button>'
  ), '<button class="attr-tab" data-key="__chunks__">vectors (' + (chunks.count||0) + ')</button>'].join('');

  document.getElementById('attr-tabs').innerHTML = tabs;
  document.querySelectorAll('.attr-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.attr-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      showPanelContent(btn.dataset.key);
    });
  });
  showPanelContent(attrKeys[0] || '__chunks__');
}

function showPanelContent(key) {
  const el = document.getElementById('attr-content');
  if (key === '__chunks__') {
    const ch = panelData.chunks;
    if (!ch.length) { el.textContent = 'No vectors stored for this entity.'; return; }
    el.innerHTML = ch.map(c => {
      const pct = c.score != null ? Math.round((1 - c.score) * 100) + '% match' : '';
      const cls = c.score < 0.3 ? 'score-high' : c.score < 0.6 ? 'score-mid' : 'score-low';
      return '<div style="margin-bottom:12px;padding:10px;background:var(--bg);border-radius:6px;border:1px solid var(--border)">' +
        '<div style="display:flex;gap:8px;margin-bottom:6px;font-size:.75rem;color:var(--muted)">' +
        '<span>' + esc(c.chunk_type||'') + '</span>' +
        (pct ? '<span class="badge ' + cls + '" style="margin-left:auto">' + pct + '</span>' : '') +
        '</div>' +
        '<div style="font-size:.83rem;line-height:1.55;white-space:pre-wrap;word-break:break-word">' + esc(c.text) + '</div>' +
        '</div>';
    }).join('');
    return;
  }
  el.textContent = (panelData.attrs[key] || '(empty)');
}

function closePanelDirect() {
  document.getElementById('panel-overlay').classList.remove('open');
}

async function runSearch(q) {
  if (!q.trim()) return;
  showTab('search');
  document.getElementById('search-count').innerHTML = '<div class="spinner"></div>';
  document.getElementById('search-results').innerHTML = '';

  let d;
  try {
    d = await apiFetch('/api/search', { q, n: 20,
      ...(activeFandom ? {fandom: activeFandom} : {}),
      ...(activeType   ? {type:   activeType}   : {}),
    });
  } catch(err) {
    document.getElementById('search-count').textContent = 'Search failed: ' + err.message;
    return;
  }

  if (d.error) {
    document.getElementById('search-count').textContent = '';
    document.getElementById('search-results').innerHTML =
      '<div class="empty-state"><div class="empty-icon">&#x26A0;&#xFE0F;</div>' +
      '<strong>Search unavailable</strong><br><code style="font-size:.8rem;color:var(--warning)">' + esc(d.error) + '</code></div>';
    return;
  }

  document.getElementById('search-count').textContent = d.count + ' results for "' + d.query + '"';
  if (!d.results.length) {
    document.getElementById('search-results').innerHTML =
      '<div class="empty-state"><div class="empty-icon">&#x1F50D;</div>No matching chunks found.</div>';
    return;
  }

  document.getElementById('search-results').innerHTML = d.results.map(r => {
    const pct = Math.round((1 - r.score) * 100);
    const cls = r.score < 0.3 ? 'score-high' : r.score < 0.6 ? 'score-mid' : 'score-low';
    return '<div class="result-card">' +
      '<div class="result-header">' +
        '<span class="result-entity">' + esc(r.entity_name) + '</span>' +
        '<span class="badge badge-' + esc(r.entity_type||'character') + '">' + esc(r.fandom||'') + '</span>' +
        '<span class="badge ' + cls + '" style="margin-left:auto">' + pct + '% &middot; ' + esc(r.chunk_type||'') + '</span>' +
      '</div>' +
      '<div class="result-text">' + esc(r.text) + '</div>' +
      '</div>';
  }).join('');
}

function setFandom(f) {
  activeFandom = f;
  loadFandoms().catch(console.error);
  if (activeTab === 'entities') loadEntities().catch(console.error);
}

function showTab(tab) {
  activeTab = tab;
  document.getElementById('tab-entities').style.display = tab === 'entities' ? '' : 'none';
  document.getElementById('tab-search').style.display   = tab === 'search'   ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.textContent.toLowerCase() === tab)
  );
}

document.querySelectorAll('.tab-btn').forEach(btn =>
  btn.addEventListener('click', () => showTab(btn.textContent.toLowerCase()))
);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=_HTML, headers={"Cache-Control": "no-store, no-cache"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fanfic Knowledge Base Explorer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    print(f"\n  Fanfic Knowledge Base Explorer")
    print(f"  Open: http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
