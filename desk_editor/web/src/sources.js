import { api } from './api.js';

export function initSources(editor, ctx) {
  const pane = document.getElementById('de-pane-sources');
  let sources = [];
  const pop = document.createElement('div');
  pop.className = 'de-float de-menu'; pop.hidden = true;
  document.body.appendChild(pop);

  function render() {
    pane.innerHTML = '';
    const tools = document.createElement('div');
    tools.className = 'de-palette-tools';
    tools.innerHTML = `<button class="de-mini" id="de-add-src">+ Text source</button>
      <button class="de-mini" id="de-add-url">+ URL source</button>`;
    pane.appendChild(tools);
    tools.querySelector('#de-add-src').onclick = () => addSource({ kind: 'text', title: 'Source', body: '' });
    tools.querySelector('#de-add-url').onclick = async () => {
      const url = prompt('Source URL'); if (!url) return;
      addSource({ kind: 'url', title: url.replace(/^https?:\/\//, '').slice(0, 40), url, body: '' });
    };

    sources.forEach(s => {
      const card = document.createElement('div'); card.className = 'de-source';
      const head = document.createElement('div'); head.className = 'de-source-head';
      const t = document.createElement('input'); t.value = s.title || 'Source';
      t.onchange = () => { s.title = t.value; save(s); };
      const del = document.createElement('button'); del.className = 'de-mini'; del.textContent = '×';
      del.onclick = async () => { await api.sourceDel(s.id); sources = sources.filter(x => x !== s); render(); };
      head.appendChild(t);
      if (s.url) { const a = document.createElement('a'); a.href = s.url; a.target = '_blank'; a.textContent = '↗'; a.style.color = '#e0a'; head.appendChild(a); }
      head.appendChild(del);
      const body = document.createElement('div');
      body.className = 'de-source-body'; body.contentEditable = 'true'; body.textContent = s.body || '';
      body.dataset.id = s.id;
      body.addEventListener('blur', () => { s.body = body.innerText; save(s); });
      body.addEventListener('mouseup', () => maybePop(body, s));
      card.appendChild(head); card.appendChild(body);
      pane.appendChild(card);
    });
  }

  function maybePop(body, s) {
    const sel = window.getSelection();
    const text = sel && !sel.isCollapsed ? sel.toString().trim() : '';
    if (!text || !body.contains(sel.anchorNode)) { pop.hidden = true; return; }
    pop.innerHTML = '';
    const mk = (label, fn) => { const d = document.createElement('div'); d.className = 'de-mi'; d.textContent = label;
      d.addEventListener('mousedown', (e) => { e.preventDefault(); fn(text, s); pop.hidden = true; }); pop.appendChild(d); };
    const lbl = document.createElement('div'); lbl.className = 'de-sub-label'; lbl.textContent = 'Push to article';
    pop.appendChild(lbl);
    mk('As body prose', pushProse);
    mk('As spoken quote', (t, src) => pushQuote(t, src, 'spoken-quote'));
    mk('As field quote', (t, src) => pushQuote(t, src, 'field-quote'));
    mk('As Q&A line', pushQA);
    pop.hidden = false;
    const r = sel.getRangeAt(0).getBoundingClientRect();
    pop.style.left = Math.min(r.left, innerWidth - 220) + 'px';
    pop.style.top = (r.bottom + 4) + 'px';
  }

  function maybeCite(src) {
    if (src && src.url) ctx.addCitation({ reference_text: src.title || src.url, url: src.url });
  }
  function pushProse(text) { editor.focus(); editor.insertHTMLAtCaret(`<p>${esc(text)}</p>`); }
  function pushQuote(text, src, variant) {
    maybeCite(src); editor.focus();
    const who = src.title || (variant === 'field-quote' ? 'Source' : 'Speaker');
    editor.insertHTMLAtCaret(`<blockquote class="${variant}">${esc(text)}<cite>— ${esc(who)}</cite></blockquote>`);
  }
  function pushQA(text, src) {
    editor.focus();
    editor.insertHTMLAtCaret(`<p class="qa-line"><span class="qa-speaker">${esc(src.title || 'Q')}:</span> ${esc(text)}</p>`);
  }

  async function addSource(data) {
    const id = await ctx.ensureArticleId();
    const { id: sid } = await api.sourceAdd(id, data);
    sources.push({ ...data, id: sid }); render();
  }
  async function save(s) { await api.sourceSave(s.id, { title: s.title, url: s.url, body: s.body }); }

  document.addEventListener('mousedown', (e) => { if (!pop.contains(e.target) && !e.target.closest('.de-source-body')) pop.hidden = true; });

  return {
    async load(id) { sources = id ? await api.sourcesGet(id) : []; render(); },
  };
}

const esc = (s) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
