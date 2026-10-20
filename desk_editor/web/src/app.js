import { api } from './api.js';
import { Editor, sanitizePaste } from './editor.js';
import { BLOCKS } from './blocks.js';
import { initMenus, showMenu } from './menus.js';
import { initPalette } from './palette.js';
import { initSources } from './sources.js';
import { initInspector } from './inspector.js';
import { openAuthorsBoard } from './authors.js';
import { openLibrary } from './library.js';
import { openPagesBoard } from './pages.js';
import { openConfigBoard, openPublishBoard } from './config.js';
import { openTaxonomyBoard } from './taxonomy.js';
import { openSpecialsBoard } from './specials.js';

const $ = (id) => document.getElementById(id);
const META_KEYS = ['title', 'slug', 'subtitle', 'excerpt', 'byline', 'seo_description', 'seo_keywords',
  'category_id', 'section_id', 'series_id', 'series_order', 'language', 'status', 'published_at',
  'is_featured', 'latitude', 'longitude', 'location_name', 'featured_image'];

const blankState = () => ({ id: null, title: '', slug: '', subtitle: '', excerpt: '', byline: '',
  seo_description: '', seo_keywords: '', category_id: null, section_id: null, series_id: null,
  series_order: 0, language: 'en', status: 'draft', published_at: '', is_featured: 0,
  latitude: '', longitude: '', location_name: '', featured_image: '',
  authors: [], tag_ids: [], citations: [] });

let lookups, editor, palette, sources, inspector, menus;
let tabs = [], active = -1;
let loading = false;

const ctx = {
  get lookups() { return lookups; },
  state: blankState(),
  getArticleId: () => ctx.state.id,
  async ensureArticleId() { if (!ctx.state.id) await save(tabs[active], { silent: true }); return ctx.state.id; },
  markDirty() { markTabDirty(tabs[active]); updateStats(); },
  onTitle() { renderTabs(); updateStats(); },
  getCitations: () => ctx.state.citations,
  addCitation(c) { if (!ctx.state.citations.some(x => x.url && x.url === c.url)) { ctx.state.citations.push(c); ctx.markDirty(); inspector.renderCites(); } },
  newCitationInline() { ctx.state.citations.push({ reference_text: '', url: '', author: '', published_date: '' }); showRightPane('cites'); inspector.renderCites(); ctx.markDirty(); },
  annotate(text) { const note = prompt(`Annotation on "${text.slice(0, 30)}…"`); if (note) { editor.focus(); const n = editor.canvas.querySelectorAll('p.fn[id^="fn"]').length + 1; editor.insertCitationRef(n); editor.canvas.insertAdjacentHTML('beforeend', `<p class="fn" id="fn${n}">${n}. ${escapeHTML(note)}</p>`); ctx.markDirty(); } },
  reload() { if (ctx.state.id) openArticle(ctx.state.id, true); },
  isDirty: () => !!tabs[active]?.dirty,
  setFeatured(url) { if (!url) return; ctx.state.featured_image = url; ctx.markDirty(); if (!$('de-pane-doc').hidden) inspector.renderDoc(); },
  async injectFromDrop(dt) {
    const id = await ctx.ensureArticleId();
    if (dt.files && dt.files.length) return (await api.injectFile(dt.files[0], id)).url;
    const key = dt.getData('application/x-ve-palette');
    if (key && palette) return await palette.injectByKey(key);
    return null;
  },
};

async function boot() {
  lookups = await api.lookups();
  editor = new Editor($('de-canvas'), { onChange, onCaret });
  menus = initMenus(editor, ctx);
  palette = initPalette(editor, ctx);
  sources = initSources(editor, ctx);
  inspector = initInspector(editor, ctx);
  buildToolbar();
  wireRails();
  wireSplitters();
  wireShortcuts();
  wireTopButtons();
  wireBlockDrag();
  editor.canvas.addEventListener('click', (e) => {
    if (e.target.closest('.photo-unit, .photo-group, .comparison, table.article-table')) showRightPane('block');  
  });
  newTab();
  editor.focus();
}

function onChange() {
  if (!loading) markTabDirty(tabs[active]);
  updateStats();
}
function markTabDirty(t) {
  if (!t) return;
  t.dirty = true; t.rev = (t.rev || 0) + 1;
  if (t === tabs[active]) setSave('unsaved', 'is-dirty');
  scheduleAutosave(t);
}
function onCaret() {
  editor.canvas.querySelectorAll('.de-active-block').forEach(n => n.classList.remove('de-active-block'));
  const b = editor.activeBlock(); if (b) b.classList?.add('de-active-block');
  syncRoleSelect();
  inspector.renderBlock();
}
function syncRoleSelect() {
  const b = editor.activeBlock();
  const role = (b && b.tagName === 'P') ? (b.getAttribute('data-text-role') || '') : '';
  $('de-role-select').value = role;
}

function buildToolbar() {
  const ins = $('de-insert-group');
  BLOCKS.forEach(b => {
    const btn = document.createElement('button'); btn.textContent = b.label; btn.title = `Insert ${b.label}`;
    btn.onmousedown = (e) => { e.preventDefault(); editor.focus(); editor.insertBlock(b.id); };
    ins.appendChild(btn);
  });
  document.querySelectorAll('#de-toolbar [data-mark]').forEach(btn =>
    btn.onmousedown = (e) => { e.preventDefault(); editor.exec(btn.dataset.mark); });
  document.querySelectorAll('#de-toolbar [data-cmd]').forEach(btn =>
    btn.onmousedown = (e) => { e.preventDefault();
      if (btn.dataset.cmd === 'link') editor.makeLink();
      else if (btn.dataset.cmd === 'footnote') editor.insertFootnote();
      else if (btn.dataset.cmd === 'cite') ctx.newCitationInline(); });

  const roleSel = $('de-role-select');
  ['', ...lookups.prose_roles].forEach(r => { if (r === '') return; const o = document.createElement('option'); o.value = r; o.textContent = r; roleSel.appendChild(o); });
  roleSel.onchange = () => { editor.applyRole(roleSel.value); editor.focus(); };

  let measure = 46;
  const setMeasure = () => { $('de-canvas').style.width = measure + 'rem'; $('de-measure').innerHTML = `${measure}<small>rem</small>`; };
  $('de-zoom-in').onclick = () => { measure = Math.min(72, measure + 2); setMeasure(); };
  $('de-zoom-out').onclick = () => { measure = Math.max(30, measure - 2); setMeasure(); };
}

function wireRails() {
  document.querySelectorAll('.de-rail').forEach(rail => {
    rail.querySelectorAll('.de-rail-tab').forEach(tab => {
      tab.onclick = () => showPane(rail, tab.dataset.pane);
    });
    rail.querySelector('.de-rail-collapse').onclick = () => setRail(rail, true);
  });
  $('de-edge-left').onclick = () => setRail($('de-rail-left'), false);
  $('de-edge-right').onclick = () => setRail($('de-rail-right'), false);
}
function setRail(rail, collapsed) {
  rail.classList.toggle('is-collapsed', collapsed);
  const edge = rail.id === 'de-rail-left' ? $('de-edge-left') : $('de-edge-right');
  edge.hidden = !collapsed;
}
function showPane(rail, name) {
  rail.querySelectorAll('.de-rail-tab').forEach(t => t.classList.toggle('is-on', t.dataset.pane === name));
  rail.querySelectorAll('.de-pane').forEach(p => p.hidden = (p.id !== `de-pane-${name}`));
  if (name === 'block') inspector.renderBlock();
  if (name === 'cites') inspector.renderCites();
  if (name === 'trans') inspector.renderTrans();
  if (name === 'history') inspector.renderHistory();
}
const showRightPane = (name) => showPane($('de-rail-right'), name);

function wireSplitters() {
  document.querySelectorAll('.de-split').forEach(sp => {
    sp.onmousedown = (e) => {
      e.preventDefault();
      const side = sp.dataset.split;
      const rail = side === 'left' ? $('de-rail-left') : $('de-rail-right');
      const startX = e.clientX, startW = rail.offsetWidth;
      const move = (ev) => { const d = ev.clientX - startX; rail.style.width = Math.max(0, Math.min(560, startW + (side === 'left' ? d : -d))) + 'px'; };
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
      document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
    };
  });
}

function wireBlockDrag() {
  const handle = $('de-bhandle'), line = $('de-dropline'), canvas = editor.canvas;
  let hover = null, dragging = false, dragBlock = null, over = null, after = false;
  const topBlock = (node) => { let n = node; while (n && n.parentElement !== canvas) n = n.parentElement; return (n && n !== canvas && canvas.contains(n)) ? n : null; };

  canvas.addEventListener('mousemove', (e) => {
    if (dragging) return;
    const blk = topBlock(e.target);
    if (!blk) { handle.hidden = true; return; }
    hover = blk; const r = blk.getBoundingClientRect();
    handle.hidden = false; handle.style.left = (r.left - 24) + 'px'; handle.style.top = (r.top + 3) + 'px';
  });
  canvas.addEventListener('mouseleave', () => { if (!dragging) handle.hidden = true; });

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault(); dragBlock = hover; if (!dragBlock) return;
    dragging = true; document.body.style.userSelect = 'none';
    const move = (ev) => {
      const o = topBlock(document.elementFromPoint(ev.clientX, ev.clientY));
      if (!o) return; over = o; const r = o.getBoundingClientRect(); after = ev.clientY > r.top + r.height / 2;
      line.hidden = false; line.style.left = r.left + 'px'; line.style.width = r.width + 'px';
      line.style.top = (after ? r.bottom : r.top) + 'px';
    };
    const up = () => {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
      dragging = false; document.body.style.userSelect = ''; line.hidden = true; handle.hidden = true;
      if (dragBlock && over && over !== dragBlock) editor.moveBlock(dragBlock, after ? over.nextElementSibling : over);
      dragBlock = over = null;
    };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
}

function wireShortcuts() {
  document.addEventListener('keydown', (e) => {
    const mod = e.ctrlKey || e.metaKey;
    const editing = ['INPUT', 'TEXTAREA'].includes(e.target.tagName) || e.target.isContentEditable;
    if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); save(tabs[active], { manual: true }); }
    else if (mod && e.key.toLowerCase() === 'o') { e.preventDefault(); openWIP(); }
    else if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); editor.makeLink(); }
    else if (e.key === 'F1') { e.preventDefault(); openHelp(); }
    else if (e.key === '?' && !editing) { e.preventDefault(); openHelp(); }
    else if (e.key === 'Escape') { if (document.querySelector('.de-app').classList.contains('de-zen')) toggleZen(false); }
  });
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) toggleZen(false); });
}

function toggleZen(on) {
  const app = document.querySelector('.de-app');
  const want = on === undefined ? !app.classList.contains('de-zen') : on;
  app.classList.toggle('de-zen', want);
  $('de-zen-exit').hidden = !want;
  if (want) { document.documentElement.requestFullscreen?.().catch(() => {}); editor.focus(); }
  else if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
}

const HELP = [
  ['Editing', [['Ctrl+B / Ctrl+I', 'Bold / italic'], ['Ctrl+K', 'Link'],
    ['Ctrl+Z / Ctrl+Y', 'Undo / redo (incl. block ops)'], ['/', 'Insert-block menu (then ↑ ↓ Enter)']]],
  ['Document', [['Ctrl+S', 'Save draft'], ['Ctrl+O', 'Open / Library'],
    ['⤢ / Esc', 'Focus mode on / off'], ['F1 or ?', 'This help']]],
  ['Markdown (start of line)', [['## ', 'Section heading'], ['> ', 'Spoken quote'], ['"" ', 'Pull quote'],
    ['- or *', 'Bulleted list'], ['1. ', 'Numbered list'], ['---', 'Divider']]],
  ['Mouse', [['Right-click ¶', 'Assign role / block actions'], ['Right-click selection', 'Quote / link / cite / annotate'],
    ['Drag ⠿ gutter handle', 'Move a block'], ['Drag palette thumb', 'Insert image / drop in a grid cell']]],
];
function openHelp() {
  if (document.getElementById('de-help-back')) return;
  const back = document.createElement('div'); back.className = 'de-modal-back'; back.id = 'de-help-back';
  back.innerHTML = `<div class="de-modal" style="width:min(640px,94vw)">
    <div class="de-modal-head"><h3>Keyboard & mouse</h3><span style="flex:1"></span>
      <button class="de-mini" id="help-close">close</button></div>
    <div class="de-modal-body de-help">${HELP.map(([sec, rows]) =>
      `<h4>${sec}</h4>` + rows.map(([k, v]) => `<div class="de-help-row"><kbd>${k}</kbd><span>${v}</span></div>`).join('')).join('')}</div></div>`;
  document.body.appendChild(back);
  const close = () => back.remove();
  back.querySelector('#help-close').onclick = close;
  back.onclick = (e) => { if (e.target === back) close(); };
}
function wireTopButtons() {
  $('de-tab-new').onclick = openWIP;
  $('de-btn-save').onclick = () => save(tabs[active], { manual: true });
  $('de-btn-preview').onclick = doPreview;
  $('de-btn-publish').onclick = doPublish;
  $('de-btn-ingest').onclick = () => $('de-ingest-input').click();
  $('de-ingest-input').onchange = async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (file) await doIngest(file);
  };
  $('de-btn-authors').onclick = () => openAuthorsBoard(refreshLookups);
  $('de-btn-taxonomy').onclick = () => openTaxonomyBoard(refreshLookups);
  $('de-btn-specials').onclick = () => openSpecialsBoard(refreshLookups);
  $('de-btn-pages').onclick = () => openPagesBoard();
  $('de-btn-config').onclick = () => openConfigBoard();
  $('de-btn-rebuild').onclick = () => openPublishBoard();
  const lib = () => openLibrary({ lookups, openArticle, currentId: () => ctx.state.id, refresh: refreshLookups });
  $('de-btn-library').onclick = lib;
  $('de-brand').onclick = lib;
  $('de-btn-help').onclick = openHelp;
  $('de-btn-zen').onclick = () => toggleZen();
  $('de-zen-exit').onclick = () => toggleZen(false);
}
async function doIngest(file) {
  const isBlank = editor.canvas.textContent.trim() === '' && !editor.canvas.querySelector('img');
  setSave('importing…', 'is-dirty');
  try {
    const id = await ctx.ensureArticleId();
    const { html, title } = await api.ingest(file, id);
    const clean = sanitizePaste(html);
    if (isBlank) editor.load(clean);
    else editor.pasteHTML(document.createRange().createContextualFragment(clean));
    if (title && !ctx.state.title) { ctx.state.title = title; ctx.onTitle(); if (!$('de-pane-doc').hidden) inspector.renderDoc(); }
    ctx.markDirty();
    editor.focus();
  } catch (e) {
    setSave('unsaved', 'is-dirty');
    alert('Import failed: ' + e.message);
  }
}
async function doPublish() {
  if (!confirm('Publish to the live site? This sets the article live for the print + publishing pipelines.')) return;
  ctx.state.status = 'published';
  if (!ctx.state.published_at) ctx.state.published_at = localNow();
  await save(tabs[active], { manual: true, message: 'published' });
  inspector.renderDoc();
}
async function refreshLookups() {
  Object.assign(lookups, await api.lookups());
  if (!$('de-pane-doc').hidden) inspector.renderDoc();
}

function makeTab(state, html) {
  return { key: 'k' + Math.random().toString(36).slice(2), state: state || blankState(),
    html: html || '<p><br></p>', dirty: false, rev: 0, saving: null, again: false, timer: null };
}
function newTab(state) {
  tabs.push(makeTab(state)); switchTo(tabs.length - 1);
}
function isBlankTab(t) {
  if (!t || t.state.id || t.dirty || t.saving) return false;
  const html = t === tabs[active] ? editor.serialize() : t.html;
  return !t.state.title && !html.replace(/<[^>]+>/g, '').trim() && !/<img/i.test(html);
}
function captureActive() {
  if (active < 0 || !tabs[active]) return;
  tabs[active].state = ctx.state;
  tabs[active].html = editor.serialize();
}
function switchTo(i, force = false) {
  if (i === active && !force) return;
  if (i !== active) {
    captureActive();
    const prev = tabs[active];
    if (prev && prev.dirty && canAutosave(prev)) save(prev, { silent: true });
  }
  active = i;
  const t = tabs[i];
  ctx.state = t.state;
  loading = true;
  try { editor.load(t.html); } finally { loading = false; }
  inspector.renderDoc();
  if (!$('de-pane-cites').hidden) inspector.renderCites();
  palette.load(t.state).catch(() => {});
  sources.load(t.state.id).catch(() => {});
  renderTabs(); updateStats();
  setSave(t.dirty ? 'unsaved' : 'saved', t.dirty ? 'is-dirty' : 'is-saved');
}
function renderTabs() {
  const strip = $('de-tabstrip'); strip.innerHTML = '';
  tabs.forEach((t, i) => {
    const el = document.createElement('div'); el.className = 'de-tab' + (i === active ? ' is-on' : '');
    el.innerHTML = `${t.dirty ? '<span class="de-dirty">•</span>' : ''}<span class="de-tab-title">${escapeHTML(t.state.title || 'Untitled')}</span><span class="de-tab-x">×</span>`;
    el.onclick = (e) => { if (e.target.classList.contains('de-tab-x')) closeTab(i); else switchTo(i); };
    el.oncontextmenu = (e) => {
      e.preventDefault();
      showMenu([
        { label: 'Close', fn: () => closeTab(i) },
        { label: 'Close others', fn: () => { const keep = tabs[i]; tabs = tabs.filter(t => t === keep || t.dirty); active = -1; switchTo(tabs.indexOf(keep), true); } },
      ], e.clientX, e.clientY);
    };
    strip.appendChild(el);
  });
}
function closeTab(i) {
  if (tabs[i].dirty && !confirm('Close without saving?')) return;
  clearTimeout(tabs[i].timer);
  const wasActive = i === active;
  tabs.splice(i, 1);
  if (!tabs.length) { active = -1; newTab(); return; }
  if (wasActive) { const ni = Math.min(i, tabs.length - 1); active = -1; switchTo(ni); }
  else { if (i < active) active--; renderTabs(); }
}

async function openArticle(id, replace = false) {
  const existing = tabs.findIndex(t => t.state.id === id);
  if (existing >= 0 && !replace) { switchTo(existing); return; }
  const a = await api.article(id);
  const st = blankState();
  META_KEYS.forEach(k => { if (a[k] != null) st[k] = a[k]; });
  st.id = a.id; st.authors = a.authors || []; st.tag_ids = a.tag_ids || []; st.citations = a.citations || [];
  st.folder_mounts = a.folder_mounts || [];
  const html = a.content || '<p><br></p>';
  if (replace && existing >= 0) {
    const t = tabs[existing]; clearTimeout(t.timer);
    t.state = st; t.html = html; t.dirty = false; t.rev = (t.rev || 0) + 1; switchTo(existing, true);
  } else if (isBlankTab(tabs[active])) {
    tabs[active] = makeTab(st, html); switchTo(active, true);
  } else { tabs.push(makeTab(st, html)); switchTo(tabs.length - 1); }
}

function buildPayload(t) {
  const s = t.state;
  const content = t === tabs[active] ? editor.serialize() : t.html;
  const p = { content, authors: s.authors, tag_ids: s.tag_ids, citations: s.citations };
  META_KEYS.forEach(k => p[k] = s[k]);
  return p;
}
// A never-saved article is created once it has a title or ~20 characters of text.
function canAutosave(t) {
  if (t.state.id) return true;
  const html = t === tabs[active] ? editor.serialize() : t.html;
  return !!(t.state.title || '').trim() || html.replace(/<[^>]+>/g, '').trim().length >= 20;
}
// One request in flight per tab; edits made meanwhile trigger one follow-up save.
function save(t = tabs[active], { silent = false, manual = false, message = '' } = {}) {
  if (!t) return Promise.resolve();
  clearTimeout(t.timer);
  if (t.saving) { t.again = true; if (manual) t.againManual = true; return t.saving; }
  const startRev = t.rev || 0;
  const payload = buildPayload(t);
  if (manual) { payload.version = true; payload.version_message = message || 'saved'; }
  if (t === tabs[active]) setSave('saving…', 'is-dirty');
  t.saving = (async () => {
    try {
      if (t.state.id) await api.update(t.state.id, payload);
      else {
        const r = await api.create(payload);
        t.state.id = r.id;
        if (t === tabs[active]) sources.load(r.id).catch(() => {});
      }
      if ((t.rev || 0) === startRev) t.dirty = false;
      if (t === tabs[active]) {
        setSave(t.dirty ? 'unsaved' : 'saved', t.dirty ? 'is-dirty' : 'is-saved');
        if (!$('de-pane-history').hidden) inspector.renderHistory();
      }
      renderTabs();
    } catch (e) {
      console.error(e);
      if (t === tabs[active]) setSave('save failed', 'is-dirty');
      if (!silent) alert('Save failed: ' + e.message);
    } finally {
      t.saving = null;
      if (t.again) {
        const m = t.againManual; t.again = t.againManual = false;
        if (t.dirty || m) save(t, { silent: true, manual: m });
      }
    }
  })();
  return t.saving;
}
function scheduleAutosave(t) {
  clearTimeout(t.timer);
  t.timer = setTimeout(() => { if (t.dirty && tabs.includes(t) && canAutosave(t)) save(t, { silent: true }); }, 1500);
}
async function doPreview() {
  await save(tabs[active], { silent: true });
  if (!ctx.state.id) return;
  await api.preview(ctx.state.id).catch(() => {});
  window.open(`/previews/${ctx.state.id}.html`, '_blank');
}
const localNow = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
window.addEventListener('beforeunload', (e) => {
  if (tabs.some(t => t.dirty || t.saving)) { e.preventDefault(); e.returnValue = ''; }
});

async function openWIP() {
  const drafts = await api.drafts();
  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal"><div class="de-modal-head"><h3>Open project</h3>
    <button class="de-mini" id="de-new-blank">+ New article</button><span class="de-tabs-spacer" style="flex:1"></span>
    <button class="de-mini" id="de-wip-close">close</button></div>
    <div class="de-modal-body"><div class="de-wip-grid" id="de-wip-grid"></div></div></div>`;
  document.body.appendChild(back);
  const grid = back.querySelector('#de-wip-grid');
  drafts.forEach(d => {
    const card = document.createElement('div'); card.className = 'de-wip';
    const thumb = d.featured_image ? `<img src="${escapeHTML(d.featured_image)}" alt="" loading="lazy">`
      : `<span class="de-wip-sub">${escapeHTML(d.subtitle || '')}</span>`;
    card.innerHTML = `<div class="de-wip-thumb">${thumb}</div>
      <div class="de-wip-meta"><div class="t">${escapeHTML(d.title || 'Untitled')}</div>
      <div class="d">${escapeHTML(d.status || '')} · ${d.updated_at ? new Date(d.updated_at).toLocaleDateString() : ''}</div></div>`;
    card.onclick = () => { close(); openArticle(d.id); };
    grid.appendChild(card);
  });
  const close = () => back.remove();
  back.querySelector('#de-wip-close').onclick = close;
  back.querySelector('#de-new-blank').onclick = () => { close(); newTab(); };
  back.onclick = (e) => { if (e.target === back) close(); };
}

function updateStats() {
  const s = editor.stats();
  $('de-stat-words').textContent = `${s.words} words`;
  $('de-stat-read').textContent = `${s.reading} min`;
  $('de-stat-slug').textContent = ctx.state.title ? slugish(ctx.state.title) : '';
  const sec = lookups.sections.find(x => x.id == ctx.state.section_id);
  $('de-stat-section').textContent = sec ? sec.name : '';
}
function setSave(text, cls) {
  const a = $('de-savestate'), b = $('de-stat-save');
  [a, b].forEach(n => { n.textContent = text; n.className = (n.id === 'de-stat-save' ? cls : ''); });
}
const slugish = (t) => t.toLowerCase().replace(/[^\w\s-]/g, '').replace(/[\s_-]+/g, '-').slice(0, 40);
const escapeHTML = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

boot().catch(e => { console.error(e); alert('Failed to start: ' + e.message); });
