import { api } from './api.js';

const TABS = ['Categories', 'Sections', 'Tags', 'Series'];

export async function openTaxonomyBoard(onChange) {
  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(760px,94vw)">
    <div class="de-modal-head"><h3>Taxonomy</h3>
      <div class="de-tb-group" id="tx-tabs" style="margin-left:.5rem"></div>
      <span style="flex:1"></span><button class="de-mini" id="tx-close">close</button></div>
    <div class="de-modal-body" id="tx-body"></div></div>`;
  document.body.appendChild(back);
  const body = back.querySelector('#tx-body');
  const tabsEl = back.querySelector('#tx-tabs');
  let active = 'Categories';

  const renderTabs = () => {
    tabsEl.innerHTML = '';
    TABS.forEach(t => {
      const b = document.createElement('button'); b.textContent = t; b.className = active === t ? 'is-on' : '';
      b.onclick = () => { active = t; renderTabs(); render(); };
      tabsEl.appendChild(b);
    });
  };

  async function render() {
    body.innerHTML = '<div class="de-hint">Loading…</div>';
    if (active === 'Categories') return renderCategories();
    if (active === 'Sections') return renderSections();
    if (active === 'Tags') return renderTags();
    if (active === 'Series') return renderSeries();
  }

  async function renderCategories() {
    const items = await api.categories();
    body.innerHTML = '';
    const addRow = document.createElement('div'); addRow.className = 'de-row'; addRow.style.marginBottom = '.8rem';
    const nameInput = document.createElement('input'); nameInput.placeholder = 'New category name';
    const addBtn = document.createElement('button'); addBtn.className = 'de-mini de-primary'; addBtn.textContent = '+ Add';
    addBtn.style.flex = '0 0 auto';
    addBtn.onclick = async () => {
      if (!nameInput.value.trim()) return;
      await api.categoryCreate({ name: nameInput.value.trim() });
      nameInput.value = ''; onChange && onChange(); renderCategories();
    };
    addRow.append(nameInput, addBtn); body.appendChild(addRow);

    items.forEach(c => {
      const row = rowShell(c.name, `${c.article_count} published article${c.article_count === 1 ? '' : 's'} · /${c.slug}`);
      const nameEl = row.querySelector('.tx-name'); nameEl.contentEditable = 'true';
      nameEl.onblur = async () => { if (nameEl.textContent.trim() && nameEl.textContent.trim() !== c.name) { await api.categoryUpdate(c.id, { name: nameEl.textContent.trim() }); onChange && onChange(); } };
      const mergeSel = otherSelect(items, c.id);
      const mergeBtn = miniBtn('merge into →', async () => {
        if (!mergeSel.value) return;
        if (!confirm(`Move all articles from "${c.name}" into the selected category and delete "${c.name}"?`)) return;
        await api.categoryMerge(c.id, mergeSel.value); onChange && onChange(); renderCategories();
      });
      const delBtn = miniBtn('delete', async () => {
        if (!confirm(`Delete category "${c.name}"? Articles keep their other fields but lose this category.`)) return;
        await api.categoryDelete(c.id); onChange && onChange(); renderCategories();
      });
      row.append(mergeSel, mergeBtn, delBtn);
      body.appendChild(row);
    });
  }

  async function renderSections() {
    const items = await api.sections();
    body.innerHTML = '<div class="de-hint" style="margin-bottom:.6rem">Sections are the site\'s fixed beats -- rename or reorder them here.</div>';
    items.forEach(s => {
      const row = rowShell(s.name, `${s.article_count} published article${s.article_count === 1 ? '' : 's'} · /${s.slug}`);
      const nameEl = row.querySelector('.tx-name'); nameEl.contentEditable = 'true';
      const order = document.createElement('input'); order.type = 'number'; order.value = s.sort_order || 0;
      order.style.width = '4rem'; order.title = 'Sort order';
      const save = async () => {
        await api.sectionUpdate(s.id, { name: nameEl.textContent.trim() || s.name, description: s.description || '', sort_order: Number(order.value) || 0 });
        onChange && onChange();
      };
      nameEl.onblur = save; order.onchange = save;
      row.append(order);
      body.appendChild(row);
    });
  }

  async function renderTags() {
    const items = await api.tagsFull();
    body.innerHTML = '';
    const hint = document.createElement('div'); hint.className = 'de-hint'; hint.style.marginBottom = '.6rem';
    hint.textContent = 'New tags are created inline while writing an article (Document → Tags). Manage duplicates and unused tags here.';
    body.appendChild(hint);
    items.forEach(t => {
      const row = rowShell(t.name, `${t.article_count} use${t.article_count === 1 ? '' : 's'} · /${t.slug}`);
      const nameEl = row.querySelector('.tx-name'); nameEl.contentEditable = 'true';
      nameEl.onblur = async () => { if (nameEl.textContent.trim() && nameEl.textContent.trim() !== t.name) { await api.tagUpdate(t.id, { name: nameEl.textContent.trim() }); onChange && onChange(); } };
      const mergeSel = otherSelect(items, t.id, x => x.name);
      const mergeBtn = miniBtn('merge into →', async () => {
        if (!mergeSel.value) return;
        if (!confirm(`Move everything tagged "${t.name}" onto the selected tag and delete "${t.name}"?`)) return;
        await api.tagMerge(t.id, mergeSel.value); onChange && onChange(); renderTags();
      });
      const delBtn = miniBtn('delete', async () => {
        if (!confirm(`Delete tag "${t.name}"?`)) return;
        await api.tagDelete(t.id); onChange && onChange(); renderTags();
      });
      row.append(mergeSel, mergeBtn, delBtn);
      body.appendChild(row);
    });
  }

  async function renderSeries() {
    const items = await api.seriesList();
    body.innerHTML = '';
    const addRow = document.createElement('div'); addRow.className = 'de-row'; addRow.style.marginBottom = '.8rem';
    const titleInput = document.createElement('input'); titleInput.placeholder = 'New series title';
    const addBtn = document.createElement('button'); addBtn.className = 'de-mini de-primary'; addBtn.textContent = '+ Add';
    addBtn.style.flex = '0 0 auto';
    addBtn.onclick = async () => {
      if (!titleInput.value.trim()) return;
      try { await api.seriesCreate({ title: titleInput.value.trim() }); titleInput.value = ''; onChange && onChange(); renderSeries(); }
      catch (e) { alert(e.message); }
    };
    addRow.append(titleInput, addBtn); body.appendChild(addRow);

    items.forEach(s => {
      const row = rowShell(s.title, `${s.article_count} article${s.article_count === 1 ? '' : 's'} · /${s.slug}`);
      const nameEl = row.querySelector('.tx-name'); nameEl.contentEditable = 'true';
      nameEl.onblur = async () => { if (nameEl.textContent.trim() && nameEl.textContent.trim() !== s.title) { await api.seriesUpdate(s.id, { title: nameEl.textContent.trim(), description: s.description || '', cover_image: s.cover_image || '' }); onChange && onChange(); } };
      const delBtn = miniBtn('delete', async () => {
        if (!confirm(`Delete series "${s.title}"? Its articles stay published, just unlinked from the series.`)) return;
        await api.seriesDelete(s.id); onChange && onChange(); renderSeries();
      });
      row.append(delBtn);
      body.appendChild(row);
    });
  }

  function rowShell(name, sub) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:.5rem;padding:.5rem .2rem;border-bottom:1px solid var(--de-line)';
    row.innerHTML = `<div style="flex:1;min-width:0">
      <div class="tx-name" style="font-weight:600;outline:none;border-bottom:1px dashed transparent" onfocus="this.style.borderBottomColor='var(--de-focus)'" onblur="this.style.borderBottomColor='transparent'">${esc(name)}</div>
      <div style="font-size:.72rem;color:var(--de-dim);font-family:var(--de-mono)">${esc(sub)}</div>
    </div>`;
    return row;
  }
  function miniBtn(label, fn) {
    const b = document.createElement('button'); b.className = 'de-mini'; b.textContent = label;
    b.style.cssText = 'flex:0 0 auto;white-space:nowrap';
    b.onclick = fn; return b;
  }
  function otherSelect(items, excludeId, labelFn = x => x.name) {
    const sel = document.createElement('select');
    sel.style.cssText = 'flex:0 0 140px;width:140px;max-width:140px';
    sel.innerHTML = '<option value="">— pick target —</option>' +
      items.filter(x => x.id !== excludeId).map(x => `<option value="${x.id}">${esc(labelFn(x))}</option>`).join('');
    return sel;
  }
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  back.querySelector('#tx-close').onclick = () => back.remove();
  back.onclick = (e) => { if (e.target === back) back.remove(); };
  renderTabs(); render();
}
