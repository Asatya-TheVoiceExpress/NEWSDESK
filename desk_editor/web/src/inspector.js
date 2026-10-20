import { api } from './api.js';

export function initInspector(editor, ctx) {
  const lk = ctx.lookups;
  const paneDoc = document.getElementById('de-pane-doc');
  const paneBlock = document.getElementById('de-pane-block');
  const paneCites = document.getElementById('de-pane-cites');
  const paneTrans = document.getElementById('de-pane-trans');
  const paneHist = document.getElementById('de-pane-history');
  const S = () => ctx.state;

  const TRANS_LANGS = { hi: 'हिंदी', fr: 'Français', es: 'Español', ar: 'العربية', zh: '中文', de: 'Deutsch' };

  function field(label, key, { type = 'text', area = false, hint = '' } = {}) {
    const wrap = document.createElement('div'); wrap.className = 'de-field';
    wrap.innerHTML = `<label>${label}</label>`;
    const inp = document.createElement(area ? 'textarea' : 'input');
    if (!area) inp.type = type;
    inp.value = S()[key] ?? '';
    // datetime-local rejects seconds/microseconds/timezones, which made stored dates look blank
    if (type === 'datetime-local' && S()[key]) inp.value = String(S()[key]).replace(' ', 'T').slice(0, 16);
    inp.addEventListener('input', () => { S()[key] = inp.value; ctx.markDirty(); if (key === 'title') ctx.onTitle(); });
    wrap.appendChild(inp);
    if (hint) { const h = document.createElement('div'); h.className = 'de-hint'; h.textContent = hint; wrap.appendChild(h); }
    return wrap;
  }
  function select(label, key, options, valKey = 'id', labKey = 'name') {
    const wrap = document.createElement('div'); wrap.className = 'de-field';
    wrap.innerHTML = `<label>${label}</label>`;
    const sel = document.createElement('select');
    sel.innerHTML = '<option value="">—</option>' +
      options.map(o => `<option value="${escapeHTML(o[valKey])}">${escapeHTML(o[labKey])}</option>`).join('');
    sel.value = S()[key] ?? '';
    sel.addEventListener('change', () => { S()[key] = sel.value || null; ctx.markDirty(); });
    wrap.appendChild(sel); return wrap;
  }

  function renderDoc() {
    paneDoc.innerHTML = '<h4>Document</h4>';
    paneDoc.append(
      field('Title', 'title'),
      field('Slug (URL)', 'slug', { hint: 'Auto from title; edit to override' }),
      field('Strapline / subtitle', 'subtitle'),
      field('Excerpt / deck', 'excerpt', { area: true }),
      field('Byline (free text)', 'byline', { hint: 'Leave blank to auto-compose from authors' }),
    );
    const aWrap = document.createElement('div'); aWrap.className = 'de-field';
    aWrap.innerHTML = '<label>Authors</label>';
    const list = document.createElement('div'); aWrap.appendChild(list);
    function drawAuthors() {
      list.innerHTML = '';
      (S().authors || []).forEach((a, i) => {
        const row = document.createElement('div'); row.className = 'de-row'; row.style.marginBottom = '.3rem';
        const who = document.createElement('select');
        who.innerHTML = lk.authors.map(au => `<option value="${au.id}">${escapeHTML(au.name)}</option>`).join('');
        who.value = a.author_id;
        who.onchange = () => { a.author_id = +who.value; a.name = lk.authors.find(x => x.id == who.value)?.name; ctx.markDirty(); };
        const role = document.createElement('select');
        role.innerHTML = lk.roles.map(r => `<option value="${r}">${r}</option>`).join('');
        role.value = a.role || 'author';
        role.onchange = () => { a.role = role.value; ctx.markDirty(); };
        const del = document.createElement('button'); del.className = 'de-mini'; del.textContent = '×';
        del.onclick = () => { S().authors.splice(i, 1); drawAuthors(); ctx.markDirty(); };
        row.append(who, role, del); list.appendChild(row);
      });
    }
    drawAuthors();
    const addA = document.createElement('button'); addA.className = 'de-mini'; addA.textContent = '+ author';
    addA.onclick = () => { (S().authors = S().authors || []).push({ author_id: lk.authors[0]?.id, name: lk.authors[0]?.name, role: 'author', sort_order: S().authors.length }); drawAuthors(); ctx.markDirty(); };
    aWrap.appendChild(addA); paneDoc.appendChild(aWrap);

    paneDoc.append(
      select('Category (format)', 'category_id', lk.categories),
      select('Section (beat)', 'section_id', lk.sections),
      select('Series', 'series_id', lk.series, 'id', 'title'),
    );
    paneDoc.appendChild(tagField());

    paneDoc.appendChild(heroField());

    paneDoc.append(
      select('Status', 'status', [{ id: 'draft', name: 'draft' }, { id: 'published', name: 'published' }], 'id', 'name'),
      field('Publish date', 'published_at', { type: 'datetime-local' }),
      field('Language', 'language'),
    );
    const geo = document.createElement('div'); geo.className = 'de-row';
    geo.append(field('Latitude', 'latitude'), field('Longitude', 'longitude'));
    paneDoc.append(field('Location name', 'location_name'), geo);
    paneDoc.append(
      field('SEO description', 'seo_description', { area: true }),
      field('SEO keywords', 'seo_keywords'),
    );
  }

  function heroField() {
    const wrap = document.createElement('div'); wrap.className = 'de-field'; wrap.innerHTML = '<label>Featured image</label>';
    const slot = document.createElement('div'); slot.className = 'de-hero';
    const path = document.createElement('input'); path.placeholder = 'or paste a /static/uploads/… path'; path.style.marginTop = '.4rem';
    const render = () => {
      const v = S().featured_image || '';
      slot.innerHTML = v ? `<img src="${v}"><button class="de-hero-x" title="Remove">×</button>` : '<span>drag an image here, or click to choose</span>';
      path.value = v;
      const x = slot.querySelector('.de-hero-x'); if (x) x.onclick = (e) => { e.stopPropagation(); S().featured_image = ''; ctx.markDirty(); render(); };
    };
    const setUrl = (u) => { if (u) { S().featured_image = u; ctx.markDirty(); render(); } };
    slot.addEventListener('dragover', (e) => { e.preventDefault(); slot.classList.add('is-over'); });
    slot.addEventListener('dragleave', () => slot.classList.remove('is-over'));
    slot.addEventListener('drop', async (e) => { e.preventDefault(); slot.classList.remove('is-over'); setUrl(await ctx.injectFromDrop(e.dataTransfer)); });
    slot.addEventListener('click', () => { const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; inp.onchange = async () => setUrl(await ctx.injectFromDrop({ files: inp.files, getData: () => '' })); inp.click(); });
    path.oninput = () => { S().featured_image = path.value; ctx.markDirty(); };
    render(); wrap.append(slot, path); return wrap;
  }

  function tagField() {
    const wrap = document.createElement('div'); wrap.className = 'de-field';
    wrap.innerHTML = '<label>Tags</label>';
    const chips = document.createElement('div'); chips.className = 'de-chips de-tag-chips';
    const box = document.createElement('div'); box.className = 'de-tag-input';
    const input = document.createElement('input'); input.placeholder = 'type to find or create a tag…';
    const sugg = document.createElement('div'); sugg.className = 'de-tag-sugg de-menu'; sugg.hidden = true;
    box.append(input, sugg); wrap.append(chips, box);

    const drawChips = () => {
      chips.innerHTML = '';
      (S().tag_ids || []).forEach(id => {
        const t = lk.tags.find(x => x.id === id); if (!t) return;
        const c = document.createElement('span'); c.className = 'de-chip is-on';
        c.innerHTML = `${t.name}<span class="x">×</span>`;
        c.querySelector('.x').onclick = () => { S().tag_ids = (S().tag_ids || []).filter(x => x !== id); drawChips(); ctx.markDirty(); };
        chips.appendChild(c);
      });
    };
    const addTag = (id) => { const ids = S().tag_ids = S().tag_ids || []; if (!ids.includes(id)) ids.push(id); input.value = ''; sugg.hidden = true; drawChips(); ctx.markDirty(); input.focus(); };
    const createAndAdd = async (name) => { const t = await api.createTag(name); if (!lk.tags.some(x => x.id === t.id)) lk.tags.push(t); addTag(t.id); };
    const drawSugg = () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { sugg.hidden = true; return; }
      const sel = new Set(S().tag_ids || []);
      sugg.innerHTML = '';
      lk.tags.filter(t => !sel.has(t.id) && t.name.toLowerCase().includes(q)).slice(0, 8).forEach(t => {
        const d = document.createElement('div'); d.className = 'de-mi'; d.textContent = t.name;
        d.onmousedown = (e) => { e.preventDefault(); addTag(t.id); }; sugg.appendChild(d);
      });
      if (!lk.tags.some(t => t.name.toLowerCase() === q)) {
        const d = document.createElement('div'); d.className = 'de-mi'; d.innerHTML = `<span class="de-mi-icon">+</span>Create “${escapeHTML(input.value.trim())}”`;
        d.onmousedown = (e) => { e.preventDefault(); createAndAdd(input.value.trim()); }; sugg.appendChild(d);
      }
      sugg.hidden = sugg.children.length === 0;
    };
    input.addEventListener('input', drawSugg);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); const f = sugg.querySelector('.de-mi'); if (f) f.dispatchEvent(new MouseEvent('mousedown')); }
      else if (e.key === 'Escape') sugg.hidden = true;
    });
    input.addEventListener('blur', () => setTimeout(() => { sugg.hidden = true; }, 160));
    drawChips();
    return wrap;
  }

  function renderBlock() {
    paneBlock.innerHTML = '<h4>Block</h4>';
    const b = editor.activeBlock();
    if (!b) { paneBlock.insertAdjacentHTML('beforeend', '<div class="de-hint">No block selected.</div>'); return; }
    const cell = editor.activeCell();

    const type = blockLabel(b);
    paneBlock.insertAdjacentHTML('beforeend', `<div class="de-hint">Type: <b style="color:var(--de-soft)">${type}</b></div>`);

    if (b.classList?.contains('photo-unit') || b.classList?.contains('photo-group')) {
      const cur = b.dataset.type || 'captioned';
      const opts = b.classList.contains('photo-unit')
        ? ['captioned', 'portrait', 'document', 'reference', 'scene', 'narrative']
        : ['grid', 'dump', 'sequence', 'comic', 'crowd', 'collage'];
      const w = document.createElement('div'); w.className = 'de-field';
      w.innerHTML = '<label>Figure type (print layout)</label>';
      const s = document.createElement('select'); s.innerHTML = opts.map(o => `<option ${o === cur ? 'selected' : ''}>${o}</option>`).join('');
      s.onchange = () => { b.dataset.type = s.value; editor.changed(); };
      w.appendChild(s); paneBlock.appendChild(w);
      if (b.classList.contains('photo-group')) {
        const add = document.createElement('button'); add.className = 'de-mini'; add.textContent = '+ cell';
        add.onclick = () => editor.addCell(b); paneBlock.appendChild(add);
      }
    }
    if (cell) {
      const cur = cell.dataset.span || 'half';
      const w = document.createElement('div'); w.className = 'de-field';
      w.innerHTML = '<label>Cell span</label>';
      const s = document.createElement('select'); s.innerHTML = ['full', 'wide', 'half', 'third'].map(o => `<option ${o === cur ? 'selected' : ''}>${o}</option>`).join('');
      s.onchange = () => { cell.dataset.span = s.value; editor.changed(); }; w.appendChild(s); paneBlock.appendChild(w);
    }
    if (b.classList?.contains('comparison')) {
      const add = document.createElement('button'); add.className = 'de-mini'; add.textContent = '+ column';
      add.onclick = () => { const it = b.querySelector('.compare-item').cloneNode(true); b.appendChild(it);
        b.dataset.count = b.querySelectorAll('.compare-item').length; editor.changed(); renderBlock(); };
      paneBlock.appendChild(add);
    }
  }

  function renderCites() {
    paneCites.innerHTML = '<h4>Citations</h4>';
    (S().citations = S().citations || []).forEach((c, i) => {
      const box = document.createElement('div'); box.className = 'de-cite';
      box.innerHTML = `<div class="n">[${i + 1}]</div>`;
      const mk = (ph, key) => { const inp = document.createElement(key === 'reference_text' ? 'textarea' : 'input');
        inp.placeholder = ph; inp.value = c[key] || ''; inp.style.width = '100%'; inp.style.marginTop = '.25rem';
        inp.oninput = () => { c[key] = inp.value; ctx.markDirty(); }; return inp; };
      box.append(mk('Reference text', 'reference_text'), mk('URL', 'url'), mk('Author', 'author'), mk('Date', 'published_date'));
      const row = document.createElement('div'); row.className = 'de-btn-row';
      const ins = document.createElement('button'); ins.className = 'de-mini'; ins.textContent = 'Insert ref';
      ins.onclick = () => { editor.focus(); editor.insertCitationRef(i + 1); };
      const del = document.createElement('button'); del.className = 'de-mini'; del.textContent = 'Delete';
      del.onclick = () => { S().citations.splice(i, 1); editor.renumberCitations(i + 1); renderCites(); ctx.markDirty(); };
      row.append(ins, del); box.appendChild(row); paneCites.appendChild(box);
    });
    const add = document.createElement('button'); add.className = 'de-mini'; add.textContent = '+ citation';
    add.onclick = () => { S().citations.push({ reference_text: '', url: '', author: '', published_date: '' }); renderCites(); ctx.markDirty(); };
    paneCites.appendChild(add);
  }

  async function renderTrans() {
    paneTrans.innerHTML = '<h4>Translations</h4>';
    if (!S().id) { paneTrans.insertAdjacentHTML('beforeend', '<div class="de-hint">Save once to start adding translations.</div>'); return; }

    const native = S().language || 'en';
    const rows = await api.translations(S().id).catch(() => []);
    const usedLangs = rows.map(t => t.language);

    if (rows.length) {
      const wrap = document.createElement('div'); wrap.style.marginBottom = '1.1rem';
      wrap.innerHTML = '<label style="display:block;margin-bottom:.4rem">Existing</label>';
      rows.forEach(t => {
        const row = document.createElement('div'); row.className = 'de-row'; row.style.marginBottom = '.3rem'; row.style.alignItems = 'center';
        const label = document.createElement('div'); label.style.flex = '1';
        label.innerHTML = `<b>${TRANS_LANGS[t.language] || t.language}</b> <span class="de-hint" style="display:inline">${(t.title || '').slice(0, 60)}</span>`;
        const edit = document.createElement('button'); edit.className = 'de-mini'; edit.textContent = 'Edit';
        edit.onclick = () => openEditor(t);
        const del = document.createElement('button'); del.className = 'de-mini'; del.textContent = '×';
        del.onclick = async () => { if (!confirm('Delete this translation?')) return; await api.translationDelete(S().id, t.language); renderTrans(); };
        row.append(label, edit, del); wrap.appendChild(row);
      });
      paneTrans.appendChild(wrap);
    }

    const remaining = Object.keys(TRANS_LANGS).filter(c => c !== native);
    if (!remaining.length) { paneTrans.insertAdjacentHTML('beforeend', '<div class="de-hint">No supported target languages left.</div>'); return; }

    const addWrap = document.createElement('div');
    addWrap.innerHTML = '<label style="display:block;margin-bottom:.4rem">Add / Replace</label>';
    const sel = document.createElement('select');
    sel.innerHTML = remaining.map(c => `<option value="${c}">${TRANS_LANGS[c]} (${c})${usedLangs.includes(c) ? ' ✓ exists' : ''}</option>`).join('');
    addWrap.appendChild(sel);
    const openBtn = document.createElement('button'); openBtn.className = 'de-mini'; openBtn.textContent = '+ Open editor';
    openBtn.style.marginTop = '.4rem';
    openBtn.onclick = () => openEditor(rows.find(t => t.language === sel.value) || { language: sel.value, title: '', excerpt: '', content: '' });
    addWrap.appendChild(openBtn);
    paneTrans.appendChild(addWrap);
  }

  function openEditor(t) {
    const existing = paneTrans.querySelector('.de-trans-editor');
    if (existing) existing.remove();
    const box = document.createElement('div'); box.className = 'de-trans-editor';
    box.style.cssText = 'margin-top:1rem;padding:.9rem;border:1px solid var(--de-line,#333);background:var(--de-panel,rgba(255,255,255,.03))';
    const draft = { language: t.language, title: t.title || '', excerpt: t.excerpt || '', content: t.content || '' };

    const titleF = document.createElement('div'); titleF.className = 'de-field';
    titleF.innerHTML = `<label>Translated title (${TRANS_LANGS[t.language] || t.language})</label>`;
    const titleI = document.createElement('input'); titleI.value = draft.title;
    titleI.oninput = () => { draft.title = titleI.value; };
    titleF.appendChild(titleI);

    const excF = document.createElement('div'); excF.className = 'de-field';
    excF.innerHTML = '<label>Translated excerpt</label>';
    const excI = document.createElement('textarea'); excI.style.minHeight = '55px'; excI.value = draft.excerpt;
    excI.oninput = () => { draft.excerpt = excI.value; };
    excF.appendChild(excI);

    const contF = document.createElement('div'); contF.className = 'de-field';
    contF.innerHTML = '<label>Translated content (HTML)</label>';
    const contI = document.createElement('textarea'); contI.style.minHeight = '160px'; contI.style.fontFamily = 'monospace'; contI.style.fontSize = '.78rem';
    contI.value = draft.content;
    contI.oninput = () => { draft.content = contI.value; };
    contF.appendChild(contI);

    const status = document.createElement('div'); status.className = 'de-hint'; status.style.margin = '.4rem 0';

    const btnRow = document.createElement('div'); btnRow.className = 'de-btn-row';
    const autoBtn = document.createElement('button'); autoBtn.className = 'de-mini'; autoBtn.textContent = 'Auto-translate';
    autoBtn.onclick = async () => {
      autoBtn.disabled = true; status.textContent = 'Translating…';
      try {
        const r = await api.translationAuto(S().id, t.language);
        if (r.error) { status.textContent = r.error; }
        else {
          draft.title = r.title; draft.excerpt = r.excerpt; draft.content = r.content;
          titleI.value = draft.title; excI.value = draft.excerpt; contI.value = draft.content;
          status.textContent = 'Machine-translated — review before saving.';
        }
      } catch (e) { status.textContent = 'Translation failed: ' + e.message; }
      autoBtn.disabled = false;
    };
    const saveBtn = document.createElement('button'); saveBtn.className = 'de-mini'; saveBtn.textContent = 'Save translation';
    saveBtn.onclick = async () => {
      saveBtn.disabled = true; status.textContent = 'Saving…';
      try { await api.translationSave(S().id, draft); status.textContent = 'Saved.'; renderTrans(); }
      catch (e) { status.textContent = 'Save failed: ' + e.message; saveBtn.disabled = false; }
    };
    const cancelBtn = document.createElement('button'); cancelBtn.className = 'de-mini'; cancelBtn.textContent = 'Cancel';
    cancelBtn.onclick = () => box.remove();
    btnRow.append(autoBtn, saveBtn, cancelBtn);

    box.append(titleF, excF, contF, status, btnRow);
    paneTrans.appendChild(box);
  }

  async function renderHistory() {
    paneHist.innerHTML = '<h4>History</h4>';
    if (!S().id) { paneHist.insertAdjacentHTML('beforeend', '<div class="de-hint">Save once to start history.</div>'); return; }
    const vs = await api.versions(S().id);
    if (!vs.length) { paneHist.insertAdjacentHTML('beforeend', '<div class="de-hint">No versions yet.</div>'); return; }
    vs.forEach(v => {
      const d = document.createElement('div'); d.className = 'de-version';
      d.innerHTML = `<div class="m">${v.message || 'saved'}</div><div class="d">${new Date(v.created_at).toLocaleString()} · ${v.display_name || ''}</div>`;
      const r = document.createElement('button'); r.className = 'de-mini'; r.textContent = 'Restore'; r.style.marginTop = '.3rem';
      r.onclick = async () => {
        const msg = ctx.isDirty() ? 'Restore this version? Your unsaved changes in this tab will be lost.' : 'Restore this version?';
        if (confirm(msg)) { await api.restore(S().id, v.id); ctx.reload(); }
      };
      d.appendChild(r); paneHist.appendChild(d);
    });
  }

  return { renderDoc, renderBlock, renderCites, renderTrans, renderHistory };
}

const escapeHTML = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function blockLabel(b) {
  if (b.classList?.contains('article-section')) return 'Section';
  if (b.classList?.contains('photo-unit')) return 'Photo';
  if (b.classList?.contains('photo-group')) return 'Photo group';
  if (b.classList?.contains('comparison')) return 'Comparison';
  if (b.classList?.contains('pull-quote')) return 'Pull quote';
  if (b.classList?.contains('field-quote')) return 'Field quote';
  if (b.classList?.contains('spoken-quote')) return 'Spoken quote';
  if (b.classList?.contains('qa-line')) return 'Q&A line';
  if (b.classList?.contains('intro-note')) return "Editor's note";
  if (b.tagName === 'TABLE') return 'Table';
  if (b.tagName === 'HR') return 'Divider';
  const role = b.getAttribute?.('data-text-role');
  return role ? `Paragraph · ${role}` : 'Paragraph';
}
