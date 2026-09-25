import { api } from './api.js';

const LINK_TYPES = ['other', 'website', 'portfolio', 'twitter', 'instagram', 'linkedin', 'newsletter', 'substack'];

export async function openAuthorsBoard(onChange) {
  const authors = await api.authorsFull();
  let cur = authors[0] || null;

  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(900px,94vw)">
    <div class="de-modal-head"><h3>Authors</h3>
      <button class="de-mini" id="ab-new">+ New author</button>
      <span style="flex:1"></span><button class="de-mini" id="ab-close">close</button></div>
    <div class="de-modal-body" style="display:flex;gap:0;padding:0">
      <div id="ab-list" style="width:230px;border-right:1px solid var(--de-line);overflow-y:auto;max-height:72vh;padding:.4rem"></div>
      <div id="ab-edit" style="flex:1;overflow-y:auto;max-height:72vh;padding:1rem"></div>
    </div></div>`;
  document.body.appendChild(back);
  const listEl = back.querySelector('#ab-list');
  const editEl = back.querySelector('#ab-edit');

  const drawList = () => {
    listEl.innerHTML = '';
    authors.forEach(a => {
      const d = document.createElement('div'); d.className = 'de-mi' + (cur && cur.id === a.id ? ' is-active' : '');
      d.textContent = a.name;
      d.onclick = () => { cur = a; drawList(); drawEdit(); };
      listEl.appendChild(d);
    });
  };

  const fld = (label, key, area) => {
    const w = document.createElement('div'); w.className = 'de-field'; w.innerHTML = `<label>${label}</label>`;
    const i = document.createElement(area ? 'textarea' : 'input'); i.value = cur[key] || '';
    i.oninput = () => { cur[key] = i.value; };
    w.appendChild(i); return w;
  };

  function drawEdit() {
    if (!cur) { editEl.innerHTML = '<div class="de-hint">Select or create an author.</div>'; return; }
    editEl.innerHTML = '';
    editEl.append(fld('Name', 'name'), fld('Role', 'role'), fld('Author type', 'author_type'),
      fld('Bio', 'bio', true), fld('Avatar URL', 'avatar_url'),
      fld('Twitter', 'social_twitter'), fld('Instagram', 'social_instagram'));

    const lt = document.createElement('div'); lt.className = 'de-field'; lt.innerHTML = '<label>Link tree</label>';
    const rows = document.createElement('div'); cur.links = cur.links || [];
    const mk = (ph, obj, key) => { const i = document.createElement('input'); i.placeholder = ph; i.value = obj[key] || ''; i.oninput = () => obj[key] = i.value; return i; };
    const drawLinks = () => {
      rows.innerHTML = '';
      cur.links.forEach((l, i) => {
        const r = document.createElement('div'); r.className = 'de-row'; r.style.marginBottom = '.3rem';
        const ty = document.createElement('select');
        ty.innerHTML = LINK_TYPES.map(o => `<option ${l.link_type === o ? 'selected' : ''}>${o}</option>`).join('');
        ty.style.flex = '0 0 90px'; ty.onchange = () => l.link_type = ty.value;
        const x = document.createElement('button'); x.className = 'de-mini'; x.textContent = '×'; x.style.flex = '0 0 28px';
        x.onclick = () => { cur.links.splice(i, 1); drawLinks(); };
        r.append(mk('Title', l, 'title'), mk('https://…', l, 'url'), ty, x);
        rows.appendChild(r);
      });
    };
    drawLinks();
    const addL = document.createElement('button'); addL.className = 'de-mini'; addL.textContent = '+ link';
    addL.onclick = () => { cur.links.push({ title: '', url: '', link_type: 'other' }); drawLinks(); };
    lt.append(rows, addL); editEl.appendChild(lt);

    const save = document.createElement('button'); save.className = 'de-mini de-primary'; save.textContent = 'Save author';
    save.style.marginTop = '.7rem';
    save.onclick = async () => {
      save.textContent = 'Saving…';
      try { await api.authorUpdate(cur.id, cur); onChange && onChange(); save.textContent = 'Saved'; }
      catch (e) { save.textContent = 'Failed'; }
      setTimeout(() => { save.textContent = 'Save author'; }, 1200);
    };
    editEl.appendChild(save);
  }

  back.querySelector('#ab-new').onclick = async () => {
    const name = prompt('Author name'); if (!name) return;
    const r = await api.authorCreate({ name });
    const a = { id: r.id, name, bio: '', role: 'journalist', author_type: 'reporter', links: [] };
    authors.push(a); cur = a; drawList(); drawEdit(); onChange && onChange();
  };
  back.querySelector('#ab-close').onclick = () => back.remove();
  back.onclick = (e) => { if (e.target === back) back.remove(); };
  drawList(); drawEdit();
}
