import { api } from './api.js';

const TOOLS = [
  ['B', () => document.execCommand('bold')],
  ['I', () => document.execCommand('italic')],
  ['H2', () => document.execCommand('formatBlock', false, 'h2')],
  ['¶', () => document.execCommand('formatBlock', false, 'p')],
  ['• list', () => document.execCommand('insertUnorderedList')],
  ['link', () => { const url = prompt('Link URL'); if (url) document.execCommand('createLink', false, url); }],
];

export async function openPagesBoard(onChange) {
  const pages = await api.pagesList();
  let cur = pages[0] || null;
  let dirty = false;

  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(920px,94vw)">
    <div class="de-modal-head"><h3>Pages</h3>
      <button class="de-mini" id="pg-new">+ New page</button>
      <span style="flex:1"></span><button class="de-mini" id="pg-close">close</button></div>
    <div class="de-modal-body de-board">
      <div class="de-board-list" id="pg-list"></div>
      <div class="de-board-edit" id="pg-edit"></div>
    </div></div>`;
  document.body.appendChild(back);
  const listEl = back.querySelector('#pg-list');
  const editEl = back.querySelector('#pg-edit');

  const drawList = () => {
    listEl.innerHTML = '';
    pages.forEach(p => {
      const d = document.createElement('div'); d.className = 'de-mi' + (cur === p ? ' is-active' : '');
      d.textContent = p.title || p.slug;
      d.onclick = () => { if (dirty && !confirm('Discard unsaved changes?')) return; cur = p; dirty = false; drawList(); drawEdit(); };
      listEl.appendChild(d);
    });
  };

  function drawEdit() {
    if (!cur) { editEl.innerHTML = '<div class="de-hint">Select or create a page.</div>'; return; }
    editEl.innerHTML = '';

    const titleField = document.createElement('div'); titleField.className = 'de-field';
    titleField.innerHTML = '<label>Page title</label>';
    const titleInput = document.createElement('input'); titleInput.value = cur.title || '';
    titleInput.oninput = () => { cur.title = titleInput.value; dirty = true; };
    titleField.appendChild(titleInput);

    const bodyField = document.createElement('div'); bodyField.className = 'de-field';
    bodyField.innerHTML = `<label>Page content</label>`;
    const bar = document.createElement('div'); bar.className = 'de-toolbar-mini';
    const canvas = document.createElement('div');
    TOOLS.forEach(([label, fn]) => {
      const b = document.createElement('button'); b.className = 'de-mini'; b.type = 'button'; b.textContent = label;
      b.onmousedown = (e) => { e.preventDefault(); canvas.focus(); fn(); dirty = true; };
      bar.appendChild(b);
    });
    canvas.className = 'de-wysiwyg'; canvas.contentEditable = 'true'; canvas.spellcheck = true;
    canvas.dataset.placeholder = 'Write this page…';
    canvas.innerHTML = cur.content || '';
    canvas.oninput = () => { dirty = true; };
    bodyField.append(bar, canvas);

    const hint = document.createElement('div'); hint.className = 'de-hint';
    hint.textContent = `slug: /${cur.slug}${cur.updated_at ? ' · last saved ' + new Date(cur.updated_at).toLocaleString() : ' · never saved'}`;

    const save = document.createElement('button'); save.className = 'de-mini de-primary'; save.textContent = 'Save page';
    save.style.marginTop = '.8rem';
    save.onclick = async () => {
      cur.content = canvas.innerHTML;
      save.textContent = 'Saving…';
      try {
        await api.pageSave(cur.slug, { title: cur.title, content: cur.content });
        cur.updated_at = new Date().toISOString();
        dirty = false;
        save.textContent = 'Saved'; hint.textContent = `slug: /${cur.slug} · last saved just now`;
        onChange && onChange();
      } catch (e) { save.textContent = 'Failed'; }
      setTimeout(() => { save.textContent = 'Save page'; }, 1200);
    };

    editEl.append(titleField, bodyField, hint, save);
  }

  back.querySelector('#pg-new').onclick = () => {
    const slug = (prompt('Page slug (letters, numbers, dashes -- this becomes the URL)') || '').trim()
      .toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '');
    if (!slug) return;
    if (pages.some(p => p.slug === slug)) { cur = pages.find(p => p.slug === slug); drawList(); drawEdit(); return; }
    const title = prompt('Page title', slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())) || slug;
    const p = { slug, title, content: '', updated_at: null };
    pages.push(p); cur = p; dirty = true; drawList(); drawEdit();
  };
  back.querySelector('#pg-close').onclick = () => { if (dirty && !confirm('Discard unsaved changes?')) return; back.remove(); };
  back.onclick = (e) => { if (e.target === back && (!dirty || confirm('Discard unsaved changes?'))) back.remove(); };
  drawList(); drawEdit();
}
