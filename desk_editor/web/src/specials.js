import { api } from './api.js';

const CADENCES = ['daily', 'weekly', 'monthly', 'custom'];
const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP'];

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export async function openSpecialsBoard(onChange) {
  const authors = await api.authorsFull().catch(() => []);
  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(1040px,96vw)">
    <div class="de-modal-head"><h3>Specials</h3>
      <div class="de-tb-group" id="sp-tabs" style="margin-left:.5rem"></div>
      <span style="flex:1"></span><button class="de-mini" id="sp-close">close</button></div>
    <div class="de-modal-body de-board" id="sp-body" style="display:flex;gap:0;padding:0"></div></div>`;
  document.body.appendChild(back);
  const body = back.querySelector('#sp-body');
  const tabsEl = back.querySelector('#sp-tabs');
  const TABS = ['Columns', 'Publications', 'Broadsheets'];
  let active = 'Columns';

  const renderTabs = () => {
    tabsEl.innerHTML = '';
    TABS.forEach(t => {
      const b = document.createElement('button'); b.textContent = t; b.className = active === t ? 'is-on' : '';
      b.onclick = () => { active = t; renderTabs(); render(); };
      tabsEl.appendChild(b);
    });
  };
  function render() {
    body.innerHTML = '';
    if (active === 'Columns') return renderColumns(body);
    if (active === 'Broadsheets') return renderBroadsheets(body);
    return renderPublications(body);
  }

  async function enhancementPanel(targetType, targetKey, { css = true } = {}) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'border:1px dashed var(--de-line);border-radius:8px;padding:.7rem;margin-top:.8rem';
    const head = document.createElement('div');
    head.innerHTML = '<b>PDF enhancements</b>';
    head.style.marginBottom = '.4rem';
    const hint = document.createElement('div'); hint.className = 'de-hint';
    hint.style.marginBottom = '.5rem';
    hint.textContent = 'Applied by the next maintenance rebuild. Leaving these alone never touches an already-built PDF.';
    wrap.append(head, hint);
    let enh;
    try { enh = await api.pdfEnhancementGet(targetType, targetKey); }
    catch (e) { wrap.appendChild(Object.assign(document.createElement('div'), { className: 'de-hint', textContent: 'Unavailable: ' + e.message })); return wrap; }

    const tocRow = document.createElement('label'); tocRow.className = 'de-hint'; tocRow.style.display = 'block'; tocRow.style.margin = '.3rem 0';
    const tocCb = document.createElement('input'); tocCb.type = 'checkbox'; tocCb.checked = !!enh.toc;
    tocRow.append(tocCb, ' Table of contents / issue index');

    const pnRow = document.createElement('label'); pnRow.className = 'de-hint'; pnRow.style.display = 'block'; pnRow.style.margin = '.3rem 0 .6rem';
    const pnCb = document.createElement('input'); pnCb.type = 'checkbox'; pnCb.checked = enh.page_numbers !== false;
    pnRow.append(pnCb, ' Page numbers');

    wrap.append(tocRow, pnRow, field('Cover note', () => enh.cover_note, v => enh.cover_note = v),
                field('Accent color', () => enh.accent, v => enh.accent = v));
    if (css) wrap.appendChild(field('Extra CSS (advanced)', () => enh.extra_css, v => enh.extra_css = v, { area: true }));

    const saveBtn = btn('Save enhancements', 'de-mini de-primary', async () => {
      enh.toc = tocCb.checked; enh.page_numbers = pnCb.checked;
      saveBtn.textContent = 'Saving…';
      try { await api.pdfEnhancementSave(targetType, targetKey, enh); saveBtn.textContent = 'Saved'; }
      catch (e) { saveBtn.textContent = 'Failed: ' + e.message; }
      setTimeout(() => { saveBtn.textContent = 'Save enhancements'; }, 1400);
    });
    wrap.appendChild(saveBtn);
    return wrap;
  }

  function imagePicker(getUrl, setUrl) {
    const wrap = document.createElement('div'); wrap.className = 'de-field'; wrap.innerHTML = '<label>Cover image</label>';
    const slot = document.createElement('div'); slot.className = 'de-hero';
    const path = document.createElement('input'); path.placeholder = 'or paste a /static/uploads/… path'; path.style.marginTop = '.4rem';
    const draw = () => {
      const v = getUrl() || '';
      slot.innerHTML = v ? `<img src="${v}"><button class="de-hero-x" type="button" title="Remove">×</button>`
                         : '<span>drag an image here, or click to choose</span>';
      path.value = v;
      const x = slot.querySelector('.de-hero-x'); if (x) x.onclick = (e) => { e.stopPropagation(); setUrl(''); draw(); };
    };
    const upload = async (file) => { const r = await api.injectFile(file); setUrl(r.url); draw(); };
    slot.addEventListener('dragover', (e) => { e.preventDefault(); slot.classList.add('is-over'); });
    slot.addEventListener('dragleave', () => slot.classList.remove('is-over'));
    slot.addEventListener('drop', (e) => { e.preventDefault(); slot.classList.remove('is-over'); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
    slot.addEventListener('click', () => {
      const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*';
      inp.onchange = () => { if (inp.files[0]) upload(inp.files[0]); };
      inp.click();
    });
    path.oninput = () => { setUrl(path.value); };
    draw(); wrap.append(slot, path); return wrap;
  }

  function field(label, get, set, opts = {}) {
    const w = document.createElement('div'); w.className = 'de-field'; w.innerHTML = `<label>${label}</label>`;
    let i;
    if (opts.select) {
      i = document.createElement('select');
      i.innerHTML = opts.select.map(o => `<option value="${esc(o)}" ${get() === o ? 'selected' : ''}>${esc(o)}</option>`).join('');
    } else if (opts.area) {
      i = document.createElement('textarea'); i.value = get() || '';
    } else {
      i = document.createElement('input');
      if (opts.type) i.type = opts.type;
      if (opts.step) i.step = opts.step;
      i.value = get() ?? '';
    }
    i.oninput = i.tagName === 'SELECT' ? undefined : () => set(i.type === 'number' || opts.type === 'number' ? Number(i.value) : i.value);
    if (i.tagName === 'SELECT') i.onchange = () => set(i.value);
    w.appendChild(i); return w;
  }
  const btn = (label, cls, fn) => { const b = document.createElement('button'); b.className = cls; b.textContent = label; b.onclick = fn; return b; };

  async function renderColumns(root) {
    const list = document.createElement('div'); list.className = 'de-board-list';
    const edit = document.createElement('div'); edit.className = 'de-board-edit';
    root.append(list, edit);

    let columns = await api.columns();
    let curColumn = null;

    function drawList() {
      list.innerHTML = '';
      const addBtn = btn('+ New column', 'de-mini de-primary', async () => {
        const title = prompt('Column title'); if (!title) return;
        const r = await api.columnCreate({ title });
        columns = await api.columns();
        curColumn = columns.find(c => c.id === r.id);
        onChange && onChange(); drawList(); drawColumnEdit();
      });
      addBtn.style.width = '100%'; addBtn.style.marginBottom = '.6rem';
      list.appendChild(addBtn);
      const hint = document.createElement('div'); hint.className = 'de-hint'; hint.style.marginBottom = '.6rem';
      hint.textContent = 'Entries (dated posts) are edited in Columnroom, the standalone app.';
      list.appendChild(hint);
      columns.forEach(c => {
        const row = document.createElement('div'); row.className = 'de-mi' + (curColumn && curColumn.id === c.id ? ' is-active' : '');
        row.innerHTML = `<b>${esc(c.title)}</b><br><small style="color:var(--de-dim)">${c.status} · ${c.cadence} · ${c.entry_count} entr${c.entry_count === 1 ? 'y' : 'ies'}</small>`;
        row.onclick = () => { curColumn = c; drawList(); drawColumnEdit(); };
        list.appendChild(row);
      });
    }

    async function drawColumnEdit() {
      edit.innerHTML = '';
      if (!curColumn) { edit.innerHTML = '<div class="de-hint">Select or create a column.</div>'; return; }
      const full = await api.columnGet(curColumn.slug);
      Object.assign(curColumn, full);

      const authorRow = document.createElement('div'); authorRow.className = 'de-field'; authorRow.innerHTML = '<label>Authors</label>';
      const authorSel = document.createElement('select'); authorSel.multiple = true; authorSel.size = Math.min(6, Math.max(3, authors.length));
      authorSel.innerHTML = authors.map(a => `<option value="${a.id}" ${curColumn.authors.some(x => x.id === a.id) ? 'selected' : ''}>${esc(a.name)}</option>`).join('');
      authorRow.appendChild(authorSel);

      edit.append(
        field('Title', () => curColumn.title, v => curColumn.title = v),
        field('Subtitle', () => curColumn.subtitle, v => curColumn.subtitle = v),
        field('Description', () => curColumn.description, v => curColumn.description = v, { area: true }),
        imagePicker(() => curColumn.cover_image, v => curColumn.cover_image = v),
      );
      const row1 = document.createElement('div'); row1.className = 'de-row';
      row1.append(
        field('Cadence', () => curColumn.cadence, v => curColumn.cadence = v, { select: CADENCES }),
        field('Period (days, if custom)', () => curColumn.period_days, v => curColumn.period_days = v, { type: 'number' }),
      );
      edit.appendChild(row1);
      const row2 = document.createElement('div'); row2.className = 'de-row';
      row2.append(
        field('Accent color', () => curColumn.accent, v => curColumn.accent = v),
        field('Status', () => curColumn.status, v => curColumn.status = v, { select: ['draft', 'published'] }),
        field('Sort order', () => curColumn.sort_order, v => curColumn.sort_order = v, { type: 'number' }),
      );
      edit.appendChild(row2);
      const feat = document.createElement('label'); feat.className = 'de-hint'; feat.style.display = 'block'; feat.style.marginBottom = '.8rem';
      const featCb = document.createElement('input'); featCb.type = 'checkbox'; featCb.checked = !!curColumn.is_featured;
      featCb.onchange = () => curColumn.is_featured = featCb.checked ? 1 : 0;
      feat.append(featCb, ' Feature on homepage');
      edit.append(authorRow, feat);

      const saveBtn = btn('Save column', 'de-mini de-primary', async () => {
        curColumn.authors = [...authorSel.selectedOptions].map((o, i) => ({ author_id: Number(o.value), role: 'author', sort_order: i }));
        saveBtn.textContent = 'Saving…';
        try {
          await api.columnUpdate(curColumn.id, curColumn);
          columns = await api.columns(); curColumn = columns.find(c => c.id === curColumn.id);
          onChange && onChange(); drawList(); saveBtn.textContent = 'Saved';
        } catch (e) { saveBtn.textContent = 'Failed: ' + e.message; }
        setTimeout(() => { saveBtn.textContent = 'Save column'; }, 1400);
      });
      const delBtn = btn('Delete column', 'de-mini', async () => {
        if (!confirm(`Delete column "${curColumn.title}" and all its entries?`)) return;
        await api.columnDelete(curColumn.id);
        columns = await api.columns(); curColumn = null;
        onChange && onChange(); drawList(); drawColumnEdit();
      });
      const btnRow = document.createElement('div'); btnRow.className = 'de-row'; btnRow.style.marginTop = '.6rem';
      btnRow.append(saveBtn, delBtn); edit.appendChild(btnRow);

      edit.appendChild(await enhancementPanel('column_booklet', curColumn.id));  

      const hr = document.createElement('hr'); hr.style.cssText = 'margin:1.2rem 0;border:none;border-top:1px solid var(--de-line)';
      const entHint = document.createElement('div'); entHint.className = 'de-hint';
      entHint.textContent = `${curColumn.entry_count} entr${curColumn.entry_count === 1 ? 'y' : 'ies'} — manage in Columnroom (separate app).`;
      edit.append(hr, entHint);
    }

    drawList(); drawColumnEdit();
  }

  async function renderPublications(root) {
    const list = document.createElement('div'); list.className = 'de-board-list';
    const edit = document.createElement('div'); edit.className = 'de-board-edit';
    root.append(list, edit);

    let pubs = await api.publications();
    let cur = null;

    function drawList() {
      list.innerHTML = '';
      const addBtn = btn('+ Upload PDF', 'de-mini de-primary', () => { cur = null; drawUpload(); });
      addBtn.style.width = '100%'; addBtn.style.marginBottom = '.6rem';
      list.appendChild(addBtn);
      pubs.forEach(p => {
        const row = document.createElement('div'); row.className = 'de-mi' + (cur && cur.id === p.id ? ' is-active' : '');
        row.style.display = 'flex'; row.style.gap = '.5rem'; row.style.alignItems = 'center';
        row.innerHTML = `${p.cover_image ? `<img src="${p.cover_image}" style="width:32px;height:44px;object-fit:cover;border-radius:3px">` : ''}
          <span><b>${p.is_featured ? '★ ' : ''}${esc(p.title)}</b><br><small style="color:var(--de-dim)">${p.pub_type} · ${(p.file_size / 1024 / 1024).toFixed(1)}MB · ${p.is_visible ? 'visible' : 'hidden'}${p.is_featured ? ' · featured' : ''}</small></span>`;
        row.onclick = () => { cur = p; drawEdit(); };
        list.appendChild(row);
      });
    }

    function drawUpload() {
      edit.innerHTML = '';
      const h = document.createElement('h4'); h.textContent = 'Upload a special publication'; h.style.marginTop = '0';
      const hint = document.createElement('div'); hint.className = 'de-hint'; hint.style.marginBottom = '.6rem';
      hint.textContent = 'A complete, already-formatted PDF (or ebook) — put it straight on the Newsstand, no article composition needed.';
      const fileInp = document.createElement('input'); fileInp.type = 'file'; fileInp.accept = '.pdf';
      const state = { title: '', description: '', cover_url: '', is_visible: 1, price_min: 0, price_max: 500, price_suggested: 0, currency: 'INR', cover: null };
      edit.append(h, hint, fileInp,
        field('Title', () => state.title, v => state.title = v),
        field('Description', () => state.description, v => state.description = v, { area: true }),
        imagePicker(() => state.cover_url, v => state.cover_url = v),
      );
      const priceRow = document.createElement('div'); priceRow.className = 'de-row';
      priceRow.append(
        field('Min price', () => state.price_min, v => state.price_min = v, { type: 'number', step: '1' }),
        field('Max price', () => state.price_max, v => state.price_max = v, { type: 'number', step: '1' }),
        field('Suggested price', () => state.price_suggested, v => state.price_suggested = v, { type: 'number', step: '1' }),
        field('Currency', () => state.currency, v => state.currency = v, { select: CURRENCIES }),
      );
      edit.appendChild(priceRow);

      const upBtn = btn('Upload', 'de-mini de-primary', async () => {
        if (!fileInp.files[0]) { alert('Pick a PDF file first'); return; }
        upBtn.textContent = 'Uploading…';
        try {
          const r = await api.publicationUpload(fileInp.files[0], {
            title: state.title, description: state.description, cover_url: state.cover_url,
          });
          if (state.price_min || state.price_max || state.price_suggested || state.currency !== 'INR') {
            await api.publicationUpdate(r.id, {
              price_min: state.price_min, price_max: state.price_max,
              price_suggested: state.price_suggested, currency: state.currency,
            });
          }
          pubs = await api.publications(); cur = pubs.find(p => p.id === r.id);
          onChange && onChange(); drawList(); drawEdit();
        } catch (e) { upBtn.textContent = 'Failed: ' + e.message; setTimeout(() => upBtn.textContent = 'Upload', 1600); }
      });
      edit.appendChild(upBtn);
    }

    async function drawEdit() {
      edit.innerHTML = '';
      if (!cur) { edit.innerHTML = '<div class="de-hint">Select a publication, or upload a new one.</div>'; return; }
      edit.append(
        field('Title', () => cur.title, v => cur.title = v),
        field('Description', () => cur.description, v => cur.description = v, { area: true }),
        imagePicker(() => cur.cover_image, v => cur.cover_image = v),
      );
      const priceRow = document.createElement('div'); priceRow.className = 'de-row';
      priceRow.append(
        field('Min price', () => cur.price_min, v => cur.price_min = v, { type: 'number', step: '1' }),
        field('Max price', () => cur.price_max, v => cur.price_max = v, { type: 'number', step: '1' }),
        field('Suggested price', () => cur.price_suggested, v => cur.price_suggested = v, { type: 'number', step: '1' }),
        field('Currency', () => cur.currency, v => cur.currency = v, { select: CURRENCIES }),
      );
      edit.appendChild(priceRow);
      let curTags = (() => {
        try { return (JSON.parse(cur.metadata || '{}').tags || []).join(', '); }
        catch (e) { return ''; }
      })();
      edit.appendChild(field('Tags (comma separated)', () => curTags, v => curTags = v));

      const vis = document.createElement('label'); vis.className = 'de-hint'; vis.style.display = 'block'; vis.style.margin = '.4rem 0 .2rem';
      const visCb = document.createElement('input'); visCb.type = 'checkbox'; visCb.checked = !!cur.is_visible;
      visCb.onchange = () => cur.is_visible = visCb.checked ? 1 : 0;
      vis.append(visCb, ' Visible on the Newsstand');
      edit.appendChild(vis);

      const feat = document.createElement('label'); feat.className = 'de-hint'; feat.style.display = 'block'; feat.style.margin = '0 0 .2rem';
      const featCb = document.createElement('input'); featCb.type = 'checkbox'; featCb.checked = !!cur.is_featured;
      featCb.onchange = () => cur.is_featured = featCb.checked ? 1 : 0;
      feat.append(featCb, ' Featured — keep permanently');
      edit.appendChild(feat);
      const featHint = document.createElement('div'); featHint.className = 'de-hint';
      featHint.style.cssText = 'margin:0 0 .8rem;padding-left:1.2rem;opacity:.75';
      featHint.textContent = cur.pub_type === 'epub'
        ? 'Reader-built ebooks are pruned after 30 days unless featured.'
        : 'Promotes it on the shelf, and exempts it from any pruning.';
      edit.appendChild(featHint);

      const saveBtn = btn('Save', 'de-mini de-primary', async () => {
        saveBtn.textContent = 'Saving…';
        try {
          await api.publicationUpdate(cur.id, { ...cur, tags: curTags });
          pubs = await api.publications(); cur = pubs.find(p => p.id === cur.id);
          onChange && onChange(); drawList(); saveBtn.textContent = 'Saved';
        } catch (e) { saveBtn.textContent = 'Failed'; }
        setTimeout(() => { saveBtn.textContent = 'Save'; }, 1200);
      });
      const iconBtn = btn('Generate icon', 'de-mini', async () => {
        iconBtn.textContent = 'Generating…';
        try { const r = await api.publicationIcon(cur.id); cur.cover_image = r.cover_image; drawEdit(); }
        catch (e) { alert('Icon generation failed: ' + e.message); iconBtn.textContent = 'Generate icon'; }
      });
      const dlBtn = document.createElement('a'); dlBtn.className = 'de-mini'; dlBtn.textContent = 'Download';
      dlBtn.href = `/static/publications/${cur.filename}`; dlBtn.target = '_blank';
      const delBtn = btn('Delete', 'de-mini', async () => {
        if (!confirm(`Delete "${cur.title}"? This removes the file too.`)) return;
        await api.publicationDelete(cur.id);
        pubs = await api.publications(); cur = null;
        onChange && onChange(); drawList(); drawEdit();
      });
      const repInp = document.createElement('input');
      repInp.type = 'file'; repInp.style.display = 'none';
      repInp.accept = '.' + (cur.filename || '').split('.').pop();
      repInp.onchange = async () => {
        if (!repInp.files[0]) return;
        repBtn.textContent = 'Replacing…';
        try {
          const r = await api.publicationReplace(cur.id, repInp.files[0]);
          pubs = await api.publications(); cur = pubs.find(p => p.id === cur.id);
          onChange && onChange(); drawList(); drawEdit();
        } catch (e) {
          repBtn.textContent = 'Failed: ' + e.message;
          setTimeout(() => { repBtn.textContent = 'Replace file'; }, 2400);
        }
      };
      const repBtn = btn('Replace file', 'de-mini', () => repInp.click());

      const row = document.createElement('div'); row.className = 'de-row'; row.style.marginTop = '.6rem';
      row.append(saveBtn, iconBtn, dlBtn, repBtn, repInp, delBtn); edit.appendChild(row);

      if (cur.pub_type === 'magazine_pdf' || cur.pub_type === 'magazine_html') {
        edit.appendChild(await enhancementPanel('magazine', cur.id, { css: false }));  
      }
    }

    drawList(); drawEdit();
  }

  async function renderBroadsheets(root) {
    const list = document.createElement('div'); list.className = 'de-board-list';
    const edit = document.createElement('div'); edit.className = 'de-board-edit';
    root.append(list, edit);

    const months = await api.broadsheetMonths().catch(() => []);
    let cur = null;

    function drawList() {
      list.innerHTML = '';
      if (!months.length) { list.innerHTML = '<div class="de-hint">No published-article months yet.</div>'; return; }
      months.forEach(ym => {
        const row = document.createElement('div'); row.className = 'de-mi' + (cur === ym ? ' is-active' : '');
        row.innerHTML = `<b>${esc(ym)}</b>`;
        row.onclick = () => { cur = ym; drawList(); drawEdit(); };
        list.appendChild(row);
      });
    }

    async function drawEdit() {
      edit.innerHTML = '';
      if (!cur) { edit.innerHTML = '<div class="de-hint">Select a month to set that issue\'s broadsheet enhancements.</div>'; return; }
      const h = document.createElement('h4'); h.textContent = `Broadsheet — ${cur}`; h.style.marginTop = '0';
      edit.append(h, await enhancementPanel('broadsheet', cur));
    }

    drawList(); drawEdit();
  }

  back.querySelector('#sp-close').onclick = () => back.remove();
  back.onclick = (e) => { if (e.target === back) back.remove(); };
  renderTabs(); render();
}
