import { BLOCKS, PROSE_ROLES } from './blocks.js';

const $ = (id) => document.getElementById(id);

export function initMenus(editor, ctx) {
  const selbar = $('de-seltoolbar');
  const slash = $('de-slash');
  const ctxm = $('de-context');
  const tip = $('de-tooltip');
  const canvas = editor.canvas;

  const hideAll = () => { [selbar, slash, ctxm].forEach(m => m.hidden = true); };
  const place = (elm, x, y) => {
    elm.hidden = false;
    const w = elm.offsetWidth, h = elm.offsetHeight, vw = innerWidth, vh = innerHeight;
    elm.style.left = Math.max(6, Math.min(x, vw - w - 6)) + 'px';
    elm.style.top = Math.max(6, Math.min(y, vh - h - 6)) + 'px';
  };

  function refreshSelToolbar() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { selbar.hidden = true; return; }
    const r = sel.getRangeAt(0);
    if (!canvas.contains(r.commonAncestorContainer)) { selbar.hidden = true; return; }
    selbar.innerHTML = '';
    const add = (label, fn, title) => {
      const b = document.createElement('button'); b.innerHTML = label; if (title) b.title = title;
      b.addEventListener('mousedown', (e) => { e.preventDefault(); fn(); });
      selbar.appendChild(b);
    };
    add('<b>B</b>', () => { editor.exec('bold'); });
    add('<i>I</i>', () => { editor.exec('italic'); });
    add('link', () => editor.makeLink());
    add('“ quote', (e) => openQuoteMenu());
    add('cite', () => openCiteMenu(lastRectXY().x, lastRectXY().y));
    add('fn', () => editor.insertFootnote());
    const rect = r.getBoundingClientRect();
    place(selbar, rect.left + rect.width / 2 - selbar.offsetWidth / 2, rect.top - 42);
  }
  function lastRectXY() {
    const r = editor.range(); const b = r ? r.getBoundingClientRect() : { left: 200, bottom: 200 };
    return { x: b.left, y: b.bottom + 6 };
  }
  function openQuoteMenu() {
    const { x, y } = lastRectXY();
    buildMenu(ctxm, [
      { label: 'Make pull quote', fn: () => editor.convertSelectionTo('pull-quote') },
      { label: 'Make field quote', fn: () => { const a = prompt('Source'); editor.convertSelectionTo('field-quote', a); } },
      { label: 'Make spoken quote', fn: () => { const a = prompt('Speaker'); editor.convertSelectionTo('spoken-quote', a); } },
    ]);
    place(ctxm, x, y);
  }
  function openCiteMenu(x, y) {
    const cites = ctx.getCitations();
    const items = cites.length
      ? cites.map((c, i) => ({ label: `[${i + 1}] ${(c.reference_text || c.url || 'source').slice(0, 40)}`,
          fn: () => editor.insertCitationRef(i + 1) }))
      : [{ label: 'No citations yet', fn: () => {} }];
    items.push({ sep: true });
    items.push({ label: '+ New citation…', fn: () => ctx.newCitationInline() });
    buildMenu(ctxm, items);
    place(ctxm, x, y);
  }

  let slashBlock = null;  
  function maybeSlash() {
    const b = editor.activeBlock();
    if (!b || b.tagName !== 'P') { slash.hidden = true; slashBlock = null; return; }
    const t = b.textContent || '';
    if (!t.startsWith('/')) { slash.hidden = true; slashBlock = null; return; }
    slashBlock = b;
    const q = t.slice(1).toLowerCase();
    const matches = BLOCKS.filter(bl =>
      bl.label.toLowerCase().includes(q) || bl.keywords.includes(q) || q === '');
    buildMenu(slash, matches.map(m => ({
      icon: m.icon, label: m.label,
      fn: () => { slashBlock.remove(); slash.hidden = true; const ins = editor.insertBlock(m.id); slashBlock = null; }
    })), true);
    const rect = b.getBoundingClientRect();
    place(slash, rect.left, rect.bottom + 4);
  }

  canvas.addEventListener('contextmenu', (e) => {
    const cellBtn = e.target.closest?.('.de-cell-tools');
    if (cellBtn) return;  
    e.preventDefault();
    const items = [];
    const sel = window.getSelection();
    const hasSel = sel && !sel.isCollapsed && canvas.contains(sel.anchorNode);
    const block = editor.activeBlock();

    if (block && block.tagName === 'P') {
      items.push({ subLabel: 'Paragraph role' });
      items.push({ label: 'Body (plain)', fn: () => editor.applyRole('') });
      PROSE_ROLES.forEach(r => items.push({ label: cap(r), fn: () => editor.applyRole(r) }));
      items.push({ sep: true });
    }
    if (hasSel) {
      items.push({ subLabel: 'Make from selection' });
      items.push({ label: 'Pull quote', fn: () => editor.convertSelectionTo('pull-quote') });
      items.push({ label: 'Field quote', fn: () => { const a = prompt('Source'); editor.convertSelectionTo('field-quote', a); } });
      items.push({ label: 'Spoken quote', fn: () => { const a = prompt('Speaker'); editor.convertSelectionTo('spoken-quote', a); } });
      items.push({ label: 'Section heading', fn: () => editor.convertSelectionTo('section') });
      items.push({ label: 'Link…', fn: () => editor.makeLink() });
      items.push({ label: 'Footnote', fn: () => editor.insertFootnote() });
      items.push({ label: 'Annotation…', fn: () => ctx.annotate(sel.toString()) });
      items.push({ label: 'Cite ▸', fn: () => openCiteMenu(e.clientX, e.clientY) });
      items.push({ sep: true });
    }
    const fig = e.target.closest?.('figure');
    if (fig) {
      const hasCredit = !!fig.querySelector('.photo-credit');
      items.push({
        label: hasCredit ? 'Edit photo credit' : 'Add photo credit',
        fn: () => {
          let cap = fig.querySelector('figcaption');
          if (!cap) {
            cap = document.createElement('figcaption');
            cap.setAttribute('data-text-role', 'caption');
            cap.setAttribute('contenteditable', 'true');
            fig.appendChild(cap);
          }
          let cite = cap.querySelector('.photo-credit');
          if (!cite) {
            cite = document.createElement('cite');
            cite.className = 'photo-credit';
            cite.setAttribute('contenteditable', 'true');
            cap.appendChild(cite);
          }
          cite.focus();
          editor.changed();
        },
      });
      items.push({ sep: true });
    }
    if (block && block.parentElement === canvas) {
      items.push({ label: 'Duplicate block', fn: () => { const c = block.cloneNode(true); block.after(c); editor.changed(); } });
      items.push({ label: 'Move up', fn: () => { const p = block.previousElementSibling; if (p) canvas.insertBefore(block, p); editor.changed(); } });
      items.push({ label: 'Move down', fn: () => { const n = block.nextElementSibling; if (n) canvas.insertBefore(n, block); editor.changed(); } });
      items.push({ label: 'Delete block', fn: () => { block.remove(); editor.changed(); }, danger: true });
    }
    buildMenu(ctxm, items);
    place(ctxm, e.clientX, e.clientY);
  });

  canvas.addEventListener('mouseover', (e) => {
    const sup = e.target.closest?.('sup[data-fn]');
    if (!sup) return;
    const n = parseInt(sup.dataset.fn, 10);
    const c = ctx.getCitations()[n - 1];
    const fnp = canvas.querySelector(`#fn${n}`);
    const txt = c ? (c.reference_text || '') + (c.url ? ` — ${c.url}` : '') : (fnp ? fnp.textContent : '');
    if (!txt) return;
    tip.innerHTML = `<strong>[${n}]</strong> ${escapeHTML(txt)}`;
    const r = sup.getBoundingClientRect();
    tip.hidden = false; place(tip, r.left, r.bottom + 4);
  });
  canvas.addEventListener('mouseout', (e) => { if (e.target.closest?.('sup[data-fn]')) tip.hidden = true; });

  const setActive = (opts, i) => { opts.forEach(o => o.classList.remove('is-active')); opts[i]?.classList.add('is-active'); opts[i]?.scrollIntoView({ block: 'nearest' }); };
  canvas.addEventListener('keydown', (e) => {
    if (slash.hidden) return;
    const opts = [...slash.querySelectorAll('.de-mi')];
    if (!opts.length) return;
    let idx = opts.findIndex(o => o.classList.contains('is-active')); if (idx < 0) idx = 0;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(opts, (idx + 1) % opts.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(opts, (idx - 1 + opts.length) % opts.length); }
    else if (e.key === 'Enter') { e.preventDefault(); (opts[idx] || opts[0]).dispatchEvent(new MouseEvent('mousedown')); }
    else if (e.key === 'Escape') { e.preventDefault(); slash.hidden = true; slashBlock = null; }
  }, true);

  canvas.addEventListener('input', () => { maybeSlash(); });
  document.addEventListener('selectionchange', () => { if (!slash.hidden) return; refreshSelToolbar(); });
  document.addEventListener('mousedown', (e) => {
    if (![selbar, slash, ctxm].some(m => m.contains(e.target))) hideAll();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideAll(); });

  return { hideAll };
}

export function showMenu(items, x, y) {
  const m = document.getElementById('de-context');
  buildMenu(m, items);
  m.hidden = false;
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = Math.max(6, Math.min(x, innerWidth - w - 6)) + 'px';
  m.style.top = Math.max(6, Math.min(y, innerHeight - h - 6)) + 'px';
}

function buildMenu(menu, items, activeFirst = false) {
  menu.innerHTML = '';
  items.forEach((it, i) => {
    if (it.sep) { menu.appendChild(document.createElement('hr')); return; }
    if (it.subLabel) { const d = document.createElement('div'); d.className = 'de-sub-label'; d.textContent = it.subLabel; menu.appendChild(d); return; }
    const row = document.createElement('div');
    row.className = 'de-mi' + (activeFirst && i === 0 ? ' is-active' : '');
    row.innerHTML = (it.icon ? `<span class="de-mi-icon">${it.icon}</span>` : '')
      + `<span>${it.label}</span>` + (it.hint ? `<small>${it.hint}</small>` : '');
    if (it.danger) row.style.color = 'var(--de-accent)';
    row.addEventListener('mousedown', (e) => { e.preventDefault(); menu.hidden = true; it.fn && it.fn(); });
    menu.appendChild(row);
  });
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const escapeHTML = (s) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
