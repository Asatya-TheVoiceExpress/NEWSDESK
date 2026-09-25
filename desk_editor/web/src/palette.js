import { api } from './api.js';
import { showMenu } from './menus.js';

const DT = 'application/x-ve-palette';

export function initPalette(editor, ctx) {
  const pane = document.getElementById('de-pane-media');
  let items = [];           
  let mounts = [];

  function render() {
    pane.innerHTML = '';
    const tools = document.createElement('div');
    tools.className = 'de-palette-tools';
    tools.innerHTML = `<button class="de-mini" id="de-pick-files">Add files</button>
      <button class="de-mini" id="de-mount-folder">Mount folder…</button>`;
    pane.appendChild(tools);

    const drop = document.createElement('div');
    drop.className = 'de-dropzone';
    drop.textContent = 'Drop images here to stage them';
    pane.appendChild(drop);

    mounts.forEach((m, mi) => {
      const row = document.createElement('div');
      row.className = 'de-mount';
      row.innerHTML = `<span>📁 ${m.split(/[\\/]/).pop()}</span>`;
      const x = document.createElement('button'); x.className = 'de-mini'; x.textContent = '×';
      x.title = m; x.onclick = () => { mounts.splice(mi, 1); persistMounts(); reloadMounts(); };
      row.appendChild(x);
      pane.appendChild(row);
    });

    const grid = document.createElement('div');
    grid.className = 'de-grid-thumbs';
    grid.id = 'de-thumbgrid';
    pane.appendChild(grid);
    const count = document.createElement('div');
    count.className = 'de-hint';
    count.textContent = `${items.length} staged`;
    pane.appendChild(count);

    const io = new IntersectionObserver((entries) => {
      entries.forEach(en => { if (en.isIntersecting) { const im = en.target; im.src = im.dataset.src; io.unobserve(im); } });
    }, { root: pane, rootMargin: '200px' });

    items.forEach((it) => {
      const cell = document.createElement('div');
      cell.className = 'de-thumb';
      cell.draggable = true;
      cell.title = it.name || '';
      const img = document.createElement('img');
      img.dataset.src = it.thumb; io.observe(img);
      cell.appendChild(img);
      cell.addEventListener('dragstart', (e) => { e.dataTransfer.setData(DT, it.key); e.dataTransfer.effectAllowed = 'copy'; });
      cell.addEventListener('dblclick', () => injectAndInsert(it));
      cell.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showMenu([
          { label: 'Insert as photo', fn: () => injectAndInsert(it) },
          { label: 'Set as featured image', fn: async () => ctx.setFeatured && ctx.setFeatured(await inject(it)) },
          { sep: true },
          { label: 'Remove from palette', danger: true, fn: () => { items = items.filter(x => x !== it); render(); } },
        ], e.clientX, e.clientY);
      });
      grid.appendChild(cell);
    });

    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('is-over'); };
    drop.ondragleave = () => drop.classList.remove('is-over');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('is-over'); addFiles(e.dataTransfer.files); };
    tools.querySelector('#de-pick-files').onclick = pickFiles;
    tools.querySelector('#de-mount-folder').onclick = mountFolder;
  }

  function addFiles(fileList) {
    [...fileList].filter(f => f.type.startsWith('image/')).forEach(f => {
      items.unshift({ key: 'f' + Math.random().toString(36).slice(2), kind: 'file', file: f,
        thumb: URL.createObjectURL(f), name: f.name });
    });
    render();
  }
  function pickFiles() {
    const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; inp.multiple = true;
    inp.onchange = () => addFiles(inp.files); inp.click();
  }
  async function mountFolder() {
    const path = prompt('Absolute folder path on this machine (its images stay referenced, not copied):');
    if (!path) return;
    if (!mounts.includes(path)) mounts.push(path);
    await persistMounts();
    await reloadMounts();
  }
  async function persistMounts() {
    const id = ctx.getArticleId(); if (id) await api.palettePost(id, { mounts });
  }
  async function reloadMounts() {
    items = items.filter(it => it.kind === 'file');
    for (const m of mounts) {
      try {
        const res = await api.scanFolder(m);
        res.items.forEach(f => items.push({ key: 'p:' + f.path, kind: 'path', path: f.path, thumb: f.thumb, name: f.name }));
      } catch (e) { console.warn('scan failed', m, e); }
    }
    render();
  }

  async function inject(it) {
    const id = ctx.getArticleId();
    if (it.kind === 'file') return (await api.injectFile(it.file, id)).url;
    return (await api.injectPath(it.path, id)).url;
  }
  async function injectAndInsert(it) {
    const url = await inject(it);
    const b = editor.insertBlock('photo');
    const cell = b.querySelector('figure');
    editor.setImage(cell, url, it.name);
  }
  const byKey = (k) => items.find(i => i.key === k);

  editor.canvas.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes(DT)) e.preventDefault(); });
  editor.canvas.addEventListener('drop', async (e) => {
    const key = e.dataTransfer.getData(DT);
    if (!key) return;
    e.preventDefault();
    const it = byKey(key); if (!it) return;
    const url = await inject(it);
    const cell = e.target.closest('.de-grid-cell, .photo-unit figure');
    if (cell) { editor.setImage(cell, url, it.name); }
    else { const b = editor.insertBlock('photo'); editor.setImage(b.querySelector('figure'), url, it.name); }
  });

  editor.canvas.addEventListener('click', (e) => {
    const btn = e.target.closest('.de-cell-tools button'); if (!btn) return;
    const cell = btn.closest('.de-grid-cell'); const grid = cell?.parentElement;
    if (btn.dataset.cell === 'add' && grid) editor.addCell(grid);
    if (btn.dataset.cell === 'del') editor.removeCell(cell);
  });

  return {
    async load(article) {
      mounts = article.folder_mounts || [];
      items = items.filter(i => i.kind === 'file');  
      await reloadMounts();
    },
    inject,
    injectByKey: async (key) => { const it = byKey(key); return it ? await inject(it) : null; },
  };
}
