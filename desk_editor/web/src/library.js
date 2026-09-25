import { api } from './api.js';
import { showMenu } from './menus.js';

let LEAFLET;
function loadLeaflet() {
  if (LEAFLET) return LEAFLET;
  LEAFLET = new Promise((res) => {
    const css = document.createElement('link'); css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'; document.head.appendChild(css);
    const s = document.createElement('script'); s.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    s.onload = () => res(window.L); document.head.appendChild(s);
  });
  return LEAFLET;
}

export async function openLibrary(ctx) {
  const lk = ctx.lookups;
  let items = await api.library();
  const sel = new Set();

  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(1040px,96vw)">
    <div class="de-modal-head"><h3>Library</h3>
      <input id="lib-q" placeholder="search title / beat / tag / place…" style="flex:1;max-width:340px">
      <select id="lib-status"><option value="">all</option><option value="draft">draft</option><option value="published">published</option></select>
      <span id="lib-count" class="de-hint"></span>
      <span style="flex:1"></span><button class="de-mini" id="lib-close">close</button></div>
    <div id="lib-batch" class="de-lib-batch" hidden></div>
    <div class="de-modal-body" style="padding:0"><div id="lib-list" class="de-lib-list"></div></div>
    <div id="lib-map-wrap" hidden></div>
  </div>`;
  document.body.appendChild(back);
  const $ = (s) => back.querySelector(s);
  const listEl = $('#lib-list'), batchEl = $('#lib-batch'), countEl = $('#lib-count');

  const opt = (arr, vk = 'id', lk2 = 'name') => arr.map(o => `<option value="${o[vk]}">${o[lk2]}</option>`).join('');

  function filtered() {
    const q = $('#lib-q').value.trim().toLowerCase();
    const st = $('#lib-status').value;
    return items.filter(it => {
      if (st && it.status !== st) return false;
      if (!q) return true;
      const tagNames = (it.tag_ids || []).map(id => (lk.tags.find(t => t.id === id) || {}).name || '').join(' ');
      return [it.title, it.category_name, it.section_name, it.location_name, tagNames]
        .join(' ').toLowerCase().includes(q);
    });
  }

  function drawList() {
    const rows = filtered();
    countEl.textContent = `${rows.length} / ${items.length}${sel.size ? ` · ${sel.size} selected` : ''}`;
    listEl.innerHTML = '';
    const head = document.createElement('div'); head.className = 'de-lib-row de-lib-head';
    head.innerHTML = `<input type="checkbox" id="lib-all"><span>Title</span><span>Status</span><span>Beat</span><span>Place</span>`;
    listEl.appendChild(head);
    head.querySelector('#lib-all').onchange = (e) => { rows.forEach(r => e.target.checked ? sel.add(r.id) : sel.delete(r.id)); drawList(); drawBatch(); };
    rows.forEach(it => {
      const row = document.createElement('div'); row.className = 'de-lib-row';
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = sel.has(it.id);
      cb.onchange = () => { cb.checked ? sel.add(it.id) : sel.delete(it.id); drawBatch(); countEl.textContent = `${rows.length} / ${items.length}${sel.size ? ` · ${sel.size} selected` : ''}`; };
      const t = document.createElement('span'); t.className = 'lib-title'; t.textContent = it.title || 'Untitled';
      t.title = 'Open in editor'; t.onclick = () => { back.remove(); ctx.openArticle(it.id); };
      const stt = document.createElement('span'); stt.innerHTML = `<em class="lib-${it.status}">${it.status}</em>`;
      const beat = document.createElement('span'); beat.textContent = it.section_name || it.category_name || '—';
      const place = document.createElement('span'); place.textContent = it.location_name || (it.latitude ? `${(+it.latitude).toFixed(2)},${(+it.longitude).toFixed(2)}` : '—');
      row.oncontextmenu = (e) => {
        e.preventDefault();
        showMenu([
          { label: 'Open in editor', fn: () => { back.remove(); ctx.openArticle(it.id); } },
          { label: it.status === 'published' ? 'Unpublish' : 'Publish',
            fn: async () => { await api.batch({ ids: [it.id], status: it.status === 'published' ? 'draft' : 'published' }); await reload(); } },
          { sep: true },
          { label: 'Delete', danger: true, fn: async () => { if (confirm(`Delete “${it.title || 'Untitled'}”?`)) { await api.deleteArticle(it.id); sel.delete(it.id); await reload(); } } },
        ], e.clientX, e.clientY);
      };
      row.append(cb, t, stt, beat, place); listEl.appendChild(row);
    });
  }

  function drawBatch() {
    if (!sel.size) { batchEl.hidden = true; return; }
    batchEl.hidden = false;
    batchEl.innerHTML = `<span class="de-hint">${sel.size} selected →</span>
      <select id="b-cat"><option value="">set beat/format…</option><optgroup label="Category">${opt(lk.categories)}</optgroup></select>
      <select id="b-sec"><option value="">set section…</option>${opt(lk.sections)}</select>
      <select id="b-tag"><option value="">add tag…</option>${opt(lk.tags)}</select>
      <button class="de-mini" id="b-apply">Apply</button>
      <button class="de-mini" id="b-pub">Publish</button>
      <button class="de-mini" id="b-draft">Unpublish</button>
      <button class="de-mini" id="b-map">Map location…</button>
      <button class="de-mini" id="b-del" style="color:var(--de-accent)">Delete</button>`;
    $('#b-apply').onclick = async () => {
      const payload = { ids: [...sel] };
      if ($('#b-cat').value) payload.category_id = +$('#b-cat').value;
      if ($('#b-sec').value) payload.section_id = +$('#b-sec').value;
      if ($('#b-tag').value) payload.add_tag_ids = [+$('#b-tag').value];
      await api.batch(payload); await reload();
    };
    $('#b-pub').onclick = async () => { await api.batch({ ids: [...sel], status: 'published' }); await reload(); };
    $('#b-draft').onclick = async () => { await api.batch({ ids: [...sel], status: 'draft' }); await reload(); };
    $('#b-del').onclick = async () => {
      if (!confirm(`Delete ${sel.size} article(s)? This cannot be undone.`)) return;
      for (const id of [...sel]) await api.deleteArticle(id);
      sel.clear(); await reload();
    };
    $('#b-map').onclick = openMap;
  }

  async function openMap() {
    const wrap = $('#lib-map-wrap');
    wrap.hidden = false;
    wrap.innerHTML = `<div class="de-lib-maphead"><input id="m-place" placeholder="place name (optional)" style="flex:1">
      <span id="m-coord" class="de-hint">click the map to set a point</span>
      <button class="de-mini de-primary" id="m-apply">Apply to ${sel.size}</button>
      <button class="de-mini" id="m-close">×</button></div><div id="lib-map" style="height:300px"></div>`;
    const L = await loadLeaflet();
    const map = L.map('lib-map').setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map);
    let marker, lat, lng;
    map.on('click', (e) => {
      lat = e.latlng.lat; lng = e.latlng.lng;
      if (marker) marker.setLatLng(e.latlng); else marker = L.marker(e.latlng).addTo(map);
      $('#m-coord').textContent = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    });
    setTimeout(() => map.invalidateSize(), 60);
    $('#m-close').onclick = () => { wrap.hidden = true; wrap.innerHTML = ''; };
    $('#m-apply').onclick = async () => {
      if (lat == null) { alert('Click the map to set a location first.'); return; }
      await api.batch({ ids: [...sel], latitude: lat, longitude: lng, location_name: $('#m-place').value.trim() });
      wrap.hidden = true; wrap.innerHTML = ''; await reload();
    };
  }

  async function reload() { items = await api.library(); ctx.refresh && ctx.refresh(); drawList(); drawBatch(); }

  $('#lib-q').oninput = drawList;
  $('#lib-status').onchange = drawList;
  $('#lib-close').onclick = () => back.remove();
  back.onclick = (e) => { if (e.target === back) back.remove(); };
  drawList();
}
