const PROSE_ROLE_OPTS = ['', 'lede', 'analysis', 'context', 'scene', 'testimony', 'resolution', 'note', 'dateline'];
const QUOTE_VARIANTS_OPTS = ['pull-quote', 'field-quote', 'spoken-quote'];
const PHOTO_TYPE_OPTS = ['captioned', 'portrait', 'document', 'reference', 'scene'];
const GROUP_TYPE_OPTS = ['grid', 'dump', 'sequence', 'comic', 'crowd'];
const esc = s => (s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

let _bid = 0;
const nbid = () => 'b' + (++_bid);

function parseBlocks(htmlStr) {
  const doc = new DOMParser().parseFromString('<div id="ve-root">' + (htmlStr || '') + '</div>', 'text/html');
  const root = doc.getElementById('ve-root');
  const out = [];
  const figInfo = fig => {
    const img = fig.querySelector('img');
    const cap = fig.querySelector('figcaption,.panel-caption,.photo-caption');
    return { src: img ? img.getAttribute('src') || '' : '', alt: img ? img.getAttribute('alt') || '' : '',
             caption: cap ? cap.innerHTML.trim() : '' };
  };
  const elBlock = el => {
    const tag = el.tagName.toLowerCase();
    const cls = el.classList;
    if (tag === 'div' && cls.contains('article-section')) { [...el.children].forEach(c => out.push(elBlock(c))); return null; }
    if (tag === 'div' && cls.contains('photo-group'))
      return { id: nbid(), type: 'gallery', gtype: el.getAttribute('data-type') || 'grid', items: [...el.querySelectorAll('figure')].map(figInfo) };
    if (tag === 'div' && (cls.contains('photo-unit') || cls.contains('photo-narrative-unit'))) {
      const f = figInfo(el); return { id: nbid(), type: 'photo', ptype: el.getAttribute('data-type') || 'captioned', ...f };
    }
    if (tag === 'div' && cls.contains('comparison'))
      return { id: nbid(), type: 'comparison', items: [...el.querySelectorAll('.compare-item')].map(ci => ({ label: (ci.querySelector('.compare-label') || {}).textContent || '', text: ci.innerHTML.replace(/<div class="compare-label">.*?<\/div>/s, '').trim() })) };
    if (tag === 'figure') { const f = figInfo(el); return { id: nbid(), type: 'photo', ptype: 'captioned', ...f }; }
    if (/^h[1-6]$/.test(tag)) return { id: nbid(), type: 'heading', level: +tag[1], text: el.innerHTML.trim() };
    if (tag === 'blockquote') {
      const cite = el.querySelector('cite'); const variant = QUOTE_VARIANTS_OPTS.find(v => cls.contains(v)) || 'field-quote';
      const c = cite ? cite.textContent : ''; if (cite) cite.remove();
      return { id: nbid(), type: 'quote', variant, text: el.innerHTML.replace(/<cite.*?<\/cite>/s, '').trim(), cite: c };
    }
    if (tag === 'hr') return { id: nbid(), type: 'divider' };
    if (tag === 'ul' || tag === 'ol') return { id: nbid(), type: 'list', ordered: tag === 'ol', html: el.innerHTML };
    if (tag === 'p' && cls.contains('qa-line')) {
      const sp = el.querySelector('.qa-speaker'); const s = sp ? sp.textContent : ''; if (sp) sp.remove();
      return { id: nbid(), type: 'qa', speaker: s.replace(/:$/, ''), text: el.innerHTML.trim() };
    }
    if (tag === 'p' && (cls.contains('intro-note') || cls.contains('italic-note')))
      return { id: nbid(), type: 'note', text: el.innerHTML.trim() };
    if (tag === 'p') return { id: nbid(), type: 'paragraph', role: el.getAttribute('data-text-role') || '', text: el.innerHTML.trim() };
    return { id: nbid(), type: 'raw', html: el.outerHTML };
  };
  [...root.children].forEach(c => { const b = elBlock(c); if (b) out.push(b); });
  return out;
}

function blockToHtml(b) {
  switch (b.type) {
    case 'paragraph': return `<p${b.role ? ` data-text-role="${b.role}"` : ''}>${b.text || ''}</p>`;
    case 'note': return `<p class="intro-note">${b.text || ''}</p>`;
    case 'heading': return `<h${b.level || 2} class="section-heading">${b.text || ''}</h${b.level || 2}>`;
    case 'quote': return `<blockquote class="${b.variant || 'field-quote'}">${b.text || ''}${b.cite ? `<cite>${esc(b.cite)}</cite>` : ''}</blockquote>`;
    case 'qa': return `<p class="qa-line"><span class="qa-speaker">${esc(b.speaker)}:</span> ${b.text || ''}</p>`;
    case 'divider': return `<hr class="section-divider">`;
    case 'list': return `<${b.ordered ? 'ol' : 'ul'}>${b.html || ''}</${b.ordered ? 'ol' : 'ul'}>`;
    case 'photo': return `<div class="photo-unit" data-type="${b.ptype || 'captioned'}"><figure><img src="${esc(b.src)}" alt="${esc(b.alt)}"/>${b.caption ? `<figcaption data-text-role="caption" class="photo-caption">${b.caption}</figcaption>` : ''}</figure></div>`;
    case 'gallery': return `<div class="photo-group" data-type="${b.gtype || 'grid'}">${(b.items || []).map(it => `<figure><img src="${esc(it.src)}" alt="${esc(it.alt)}"/>${it.caption ? `<figcaption${b.gtype === 'comic' ? ' class="panel-caption"' : ''}>${it.caption}</figcaption>` : ''}</figure>`).join('')}</div>`;
    case 'comparison': return `<div class="comparison" data-count="${(b.items || []).length}">${(b.items || []).map(it => `<div class="compare-item"><div class="compare-label">${esc(it.label)}</div>${it.text || ''}</div>`).join('')}</div>`;
    case 'raw': return b.html || '';
    default: return '';
  }
}
function blocksToHtml(blocks) {
  const out = []; let sec = null;
  const flush = () => { if (sec) { out.push(`<div class="article-section">${sec.join('')}</div>`); sec = null; } };
  for (const b of blocks) {
    const h = blockToHtml(b);
    if (b.type === 'heading') { flush(); sec = [h]; }
    else if (sec) sec.push(h);
    else out.push(h);
  }
  flush();
  return out.join('\n');
}

function CBtn({ on, title, children }) {
  return <button type="button" onClick={on} title={title}
    style={{ fontFamily: 'var(--fm)', fontSize: '.62rem', padding: '.2rem .4rem', border: 'var(--rt)', background: 'var(--paper)', color: 'var(--ink)', cursor: 'pointer' }}>{children}</button>;
}

const _strip = h => (h || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
function blockPreview(b) {
  switch (b.type) {
    case 'paragraph': case 'note': case 'heading': case 'quote': return _strip(b.text);
    case 'qa': return (b.speaker ? b.speaker + ': ' : '') + _strip(b.text);
    case 'list': return _strip(b.html);
    case 'photo': return _strip(b.caption) || b.alt || (b.src ? '1 image' : 'empty photo');
    case 'gallery': return ((b.items || []).length) + ' image' + ((b.items || []).length === 1 ? '' : 's');
    case 'comparison': return (b.items || []).map(i => i.label).filter(Boolean).join(' vs ');
    case 'raw': return _strip(b.html);
    case 'divider': return '— divider —';
    default: return '';
  }
}
const BLOCK_LBL = { paragraph: 'Paragraph', note: 'Editor note', heading: 'Section heading', quote: 'Quote', qa: 'Q&A', divider: 'Divider', list: 'List', photo: 'Photo', gallery: 'Photo set', comparison: 'Comparison', raw: 'Raw HTML' };

function RichField({ html, onChange, placeholder, minHeight }) {
  const ref = React.useRef(null);
  React.useEffect(() => { if (ref.current) ref.current.innerHTML = html || ''; }, []);
  const sync = () => onChange(ref.current ? ref.current.innerHTML : '');
  const exec = (cmd, val) => { if (ref.current) ref.current.focus(); document.execCommand(cmd, false, val); sync(); };
  const onKey = e => {
    if (e.ctrlKey || e.metaKey) {
      const k = e.key.toLowerCase();
      if (k === 'b') { e.preventDefault(); exec('bold'); }
      else if (k === 'i') { e.preventDefault(); exec('italic'); }
      else if (k === 'u') { e.preventDefault(); exec('underline'); }
      else if (k === 'k') { e.preventDefault(); const u = prompt('Link URL:'); if (u) exec('createLink', u); }
    }
  };
  const tbtn = (label, fn, title) => <button type="button" className="rf-btn" title={title} onMouseDown={e => { e.preventDefault(); fn(); }}>{label}</button>;
  return (
    <div className="rf-wrap">
      <div className="rf-bar">
        {tbtn(<b>B</b>, () => exec('bold'), 'Bold (Ctrl+B)')}
        {tbtn(<i>I</i>, () => exec('italic'), 'Italic (Ctrl+I)')}
        {tbtn(<u>U</u>, () => exec('underline'), 'Underline (Ctrl+U)')}
        {tbtn('↗', () => { const u = prompt('Link URL:'); if (u) exec('createLink', u); }, 'Link (Ctrl+K)')}
        {tbtn('⌫', () => exec('removeFormat'), 'Clear formatting')}
      </div>
      <div ref={ref} className="rich-field" contentEditable suppressContentEditableWarning
        data-ph={placeholder || ''} style={minHeight ? { minHeight } : null}
        onInput={sync} onBlur={sync} onKeyDown={onKey} />
    </div>
  );
}

function BlockCard({ block, idx, total, collapsed, onToggle, onChange, onMove, onDel, onInsert, onUpload, onUploadMulti }) {
  const b = block, set = patch => onChange({ ...b, ...patch });
  const lbl = BLOCK_LBL[b.type] || b.type;
  const ta = { width: '100%', minHeight: 56, fontFamily: 'var(--fb)', fontSize: '.92rem', border: 'var(--rt)', padding: '.4rem .5rem', background: 'var(--paper)', color: 'var(--ink)' };
  const setItem = (i, patch) => set({ items: b.items.map((it, j) => j === i ? { ...it, ...patch } : it) });
  const stop = fn => e => { e.stopPropagation(); fn(); };
  const pv = blockPreview(b);
  const role = b.type === 'heading' ? 'cmp-blk-head' : b.type === 'photo' || b.type === 'gallery' ? 'cmp-blk-media' : '';
  return (
    <div className={'cmp-blk ' + role} style={{ border: 'var(--rule)', marginBottom: '.42rem', background: 'var(--paper)' }}>
      <div onClick={onToggle} style={{ display: 'flex', alignItems: 'center', gap: '.45rem', padding: '.34rem .5rem', background: 'var(--g100)', borderBottom: collapsed ? 'none' : 'var(--rt)', cursor: 'pointer' }}>
        <span style={{ fontSize: '.6rem', color: 'var(--g500)', width: '.8rem' }}>{collapsed ? '▸' : '▾'}</span>
        <span style={{ fontFamily: 'var(--fm)', fontSize: '.55rem', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--g600)', flexShrink: 0, minWidth: '5.4rem' }}>{lbl}</span>
        {(b.type === 'photo' || b.type === 'gallery') && (() => {
          const thumbs = b.type === 'photo' ? (b.src ? [b.src] : []) : (b.items || []).map(i => i.src).filter(Boolean);
          return thumbs.slice(0, 4).map((s, i) => <img key={i} src={s} alt="" className="cmp-thumb" />);
        })()}
        {collapsed && <span style={{ flex: 1, fontFamily: 'var(--fb)', fontSize: '.82rem', color: 'var(--g600)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{pv || '—'}</span>}
        {!collapsed && <span style={{ flex: 1 }} />}
        <CBtn on={stop(() => onInsert(idx))} title="Insert paragraph below">＋</CBtn>
        <CBtn on={stop(() => onMove(idx, -1))} title="Move up">↑</CBtn>
        <CBtn on={stop(() => onMove(idx, 1))} title="Move down">↓</CBtn>
        <CBtn on={stop(() => onDel(idx))} title="Delete">✕</CBtn>
      </div>
      {!collapsed && <div style={{ padding: '.5rem' }}>
        {(b.type === 'paragraph' || b.type === 'note') && <RichField html={b.text} onChange={v => set({ text: v })} placeholder="Write…" minHeight={48} />}
        {b.type === 'paragraph' && <div style={{ marginTop: '.35rem' }}><label style={{ fontFamily: 'var(--fm)', fontSize: '.58rem', textTransform: 'uppercase', color: 'var(--g500)', marginRight: '.4rem' }}>Role</label>
          <select value={b.role} onChange={e => set({ role: e.target.value })} style={{ width: 'auto', fontSize: '.8rem' }}>{PROSE_ROLE_OPTS.map(r => <option key={r} value={r}>{r || 'body'}</option>)}</select></div>}
        {b.type === 'heading' && <input value={b.text} onChange={e => set({ text: e.target.value })} placeholder="Section heading" />}
        {b.type === 'quote' && <>
          <RichField html={b.text} onChange={v => set({ text: v })} placeholder="Quote…" minHeight={44} />
          <div style={{ display: 'flex', gap: '.4rem', marginTop: '.35rem' }}>
            <select value={b.variant} onChange={e => set({ variant: e.target.value })} style={{ width: 'auto', fontSize: '.8rem' }}>{QUOTE_VARIANTS_OPTS.map(v => <option key={v} value={v}>{v}</option>)}</select>
            <input value={b.cite || ''} onChange={e => set({ cite: e.target.value })} placeholder="— Source / attribution" />
          </div></>}
        {b.type === 'qa' && <>
          <input value={b.speaker || ''} onChange={e => set({ speaker: e.target.value })} placeholder="Speaker" style={{ marginBottom: '.35rem' }} />
          <RichField html={b.text} onChange={v => set({ text: v })} placeholder="What they said…" minHeight={44} /></>}
        {b.type === 'list' && <textarea style={ta} value={b.html} onChange={e => set({ html: e.target.value })} placeholder="<li>item</li>…" />}
        {b.type === 'raw' && <textarea style={{ ...ta, fontFamily: 'var(--fm)', fontSize: '.78rem' }} value={b.html} onChange={e => set({ html: e.target.value })} />}
        {b.type === 'divider' && <div style={{ fontFamily: 'var(--fm)', fontSize: '.6rem', color: 'var(--g500)' }}>— section divider —</div>}
        {b.type === 'photo' && <>
          <div style={{ display: 'flex', gap: '.4rem', alignItems: 'flex-start' }}>
            {b.src && <img src={b.src} alt="" style={{ width: 90, height: 60, objectFit: 'cover', border: 'var(--rt)' }} />}
            <div style={{ flex: 1 }}>
              <input value={b.src} onChange={e => set({ src: e.target.value })} placeholder="image URL" style={{ marginBottom: '.3rem' }} />
              <input type="file" accept="image/*" onChange={e => onUpload(e, url => set({ src: url }))} style={{ border: 'none', padding: 0, fontSize: '.7rem' }} />
            </div>
          </div>
          <input value={b.alt || ''} onChange={e => set({ alt: e.target.value })} placeholder="alt text (describe the image)" style={{ margin: '.35rem 0' }} />
          <input value={b.caption || ''} onChange={e => set({ caption: e.target.value })} placeholder="caption" style={{ marginBottom: '.35rem' }} />
          <select value={b.ptype} onChange={e => set({ ptype: e.target.value })} style={{ width: 'auto', fontSize: '.8rem' }}>{PHOTO_TYPE_OPTS.map(t => <option key={t} value={t}>{t}</option>)}</select>
        </>}
        {b.type === 'gallery' && <>
          <div style={{ marginBottom: '.4rem' }}><label style={{ fontFamily: 'var(--fm)', fontSize: '.58rem', textTransform: 'uppercase', color: 'var(--g500)', marginRight: '.4rem' }}>Layout</label>
            <select value={b.gtype} onChange={e => set({ gtype: e.target.value })} style={{ width: 'auto', fontSize: '.8rem' }}>{GROUP_TYPE_OPTS.map(t => <option key={t} value={t}>{t}</option>)}</select></div>
          {(b.items || []).map((it, i) => <div key={i} style={{ display: 'flex', gap: '.4rem', alignItems: 'center', marginBottom: '.3rem' }}>
            {it.src && <img src={it.src} alt="" style={{ width: 54, height: 40, objectFit: 'cover', border: 'var(--rt)' }} />}
            <input value={it.src} onChange={e => setItem(i, { src: e.target.value })} placeholder="image URL" style={{ flex: 1 }} />
            <input value={it.caption || ''} onChange={e => setItem(i, { caption: e.target.value })} placeholder="caption" style={{ flex: 1 }} />
            <CBtn on={() => set({ items: b.items.filter((_, j) => j !== i) })} title="Remove">✕</CBtn>
          </div>)}
          <div style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
            <CBtn on={() => set({ items: [...(b.items || []), { src: '', alt: '', caption: '' }] })}>+ image</CBtn>
            <label style={{ fontFamily: 'var(--fm)', fontSize: '.58rem', color: 'var(--g500)' }}>add many:
              <input type="file" accept="image/*" multiple onChange={async e => { const urls = []; await onUploadMulti(e, u => urls.push(u)); if (urls.length) set({ items: [...(b.items || []), ...urls.map(u => ({ src: u, alt: '', caption: '' }))] }); }} style={{ border: 'none', padding: 0, fontSize: '.7rem' }} /></label>
          </div>
        </>}
        {b.type === 'comparison' && <>
          {(b.items || []).map((it, i) => <div key={i} style={{ border: 'var(--rt)', padding: '.4rem', marginBottom: '.3rem' }}>
            <input value={it.label || ''} onChange={e => setItem(i, { label: e.target.value })} placeholder="label (e.g. Now / Then)" style={{ marginBottom: '.3rem' }} />
            <RichField html={it.text} onChange={v => setItem(i, { text: v })} placeholder="column text…" minHeight={44} />
            <CBtn on={() => set({ items: b.items.filter((_, j) => j !== i) })} title="Remove column">✕ column</CBtn>
          </div>)}
          <CBtn on={() => set({ items: [...(b.items || []), { label: '', text: '' }] })}>+ column</CBtn>
        </>}
      </div>}
    </div>
  );
}

const _blkTemplate = type => ({
  paragraph: { type: 'paragraph', role: '', text: '' }, note: { type: 'note', text: '' },
  heading: { type: 'heading', level: 2, text: 'Section title' },
  quote: { type: 'quote', variant: 'pull-quote', text: '', cite: '' },
  qa: { type: 'qa', speaker: '', text: '' }, divider: { type: 'divider' },
  photo: { type: 'photo', ptype: 'captioned', src: '', alt: '', caption: '' },
  gallery: { type: 'gallery', gtype: 'grid', items: [] },
  comparison: { type: 'comparison', items: [{ label: 'Now', text: '' }, { label: 'Then', text: '' }] },
}[type]);

function SemanticComposer({ value, onChange }) {
  const [blocks, setBlocks] = React.useState(() => parseBlocks(value));
  const [collapsed, setCollapsed] = React.useState(() => { 
    const ids = parseBlocks(value).map(b => b.id);
    return new Set(ids.length > 6 ? ids : []);
  });
  const lastSerialized = React.useRef(value);
  React.useEffect(() => {
    if (value !== lastSerialized.current) {
      const nb = parseBlocks(value); setBlocks(nb); lastSerialized.current = value;
      setCollapsed(new Set(nb.length > 6 ? nb.map(b => b.id) : []));
    }
  }, [value]);
  const push = next => { setBlocks(next); const html = blocksToHtml(next); lastSerialized.current = html; onChange(html); };
  const upd = b => push(blocks.map(x => x.id === b.id ? b : x));
  const move = (i, d) => { const j = i + d; if (j < 0 || j >= blocks.length) return; const n = [...blocks];[n[i], n[j]] = [n[j], n[i]]; push(n); };
  const del = i => { const id = blocks[i] && blocks[i].id; push(blocks.filter((_, j) => j !== i)); if (id) setCollapsed(s => { const n = new Set(s); n.delete(id); return n; }); };
  const insertAt = (type, index) => {
    const nb = { id: nbid(), ..._blkTemplate(type) };
    const n = [...blocks]; n.splice(index, 0, nb); push(n);
    setCollapsed(s => { const x = new Set(s); x.delete(nb.id); return x; }); 
  };
  const add = type => insertAt(type, blocks.length);
  const toggle = id => setCollapsed(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allCollapsed = blocks.length > 0 && blocks.every(b => collapsed.has(b.id));
  const toggleAll = () => setCollapsed(allCollapsed ? new Set() : new Set(blocks.map(b => b.id)));
  const onUpload = async (e, cb) => {
    const f = e.target.files && e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    const d = await API.upload('/api/upload', fd).catch(() => ({}));
    if (d.url) cb(d.url); e.target.value = '';
  };
  const onUploadMulti = async (e, cbEach) => {
    const files = [...(e.target.files || [])]; if (!files.length) return;
    for (const f of files) {
      const fd = new FormData(); fd.append('file', f);
      const d = await API.upload('/api/upload', fd).catch(() => ({}));
      if (d.url) cbEach(d.url);
    }
    e.target.value = '';
  };
  const dumpRef = React.useRef(null);
  const dumpMedia = async (e) => {
    const files = [...(e.target.files || [])]; if (!files.length) return;
    const items = [];
    for (const f of files) {
      const fd = new FormData(); fd.append('file', f);
      const d = await API.upload('/api/upload', fd).catch(() => ({}));
      if (d.url) items.push({ src: d.url, alt: '', caption: '' });
    }
    if (items.length) { const nb = { id: nbid(), type: 'gallery', gtype: 'grid', items }; push([...blocks, nb]); }
    e.target.value = '';
  };
  const ADDS = [['paragraph', 'Paragraph'], ['heading', 'Section'], ['quote', 'Quote'], ['qa', 'Q&A'], ['photo', 'Photo'], ['gallery', 'Photo set'], ['comparison', 'Comparison'], ['note', 'Note'], ['divider', 'Divider']];
  return (
    <div>
      <input ref={dumpRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={dumpMedia} />
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '.3rem', marginBottom: '.6rem', padding: '.42rem .5rem', border: 'var(--rt)', background: 'var(--g100)' }}>
        <span style={{ fontFamily: 'var(--fm)', fontSize: '.55rem', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--g500)', marginRight: '.15rem' }}>Add block</span>
        {ADDS.map(([t, l]) => <CBtn key={t} on={() => add(t)}>{l}</CBtn>)}
        <button type="button" onClick={() => dumpRef.current && dumpRef.current.click()} title="Upload many images at once into an ordered photo set" style={{ fontFamily: 'var(--fm)', fontSize: '.58rem', padding: '.2rem .55rem', border: 'var(--rt)', background: 'var(--ink)', color: 'var(--paper)', cursor: 'pointer' }}>Dump media</button>
        {blocks.length > 1 && <button type="button" onClick={toggleAll} style={{ marginLeft: 'auto', fontFamily: 'var(--fm)', fontSize: '.58rem', padding: '.2rem .5rem', border: 'var(--rt)', background: 'var(--paper)', color: 'var(--ink)', cursor: 'pointer' }}>{allCollapsed ? 'Expand all' : 'Collapse all'}</button>}
      </div>
      {blocks.length === 0 && <div style={{ fontFamily: 'var(--fm)', fontSize: '.62rem', color: 'var(--g400)', fontStyle: 'italic', padding: '.5rem' }}>Empty — add a block to begin typesetting.</div>}
      {blocks.map((b, i) => <BlockCard key={b.id} block={b} idx={i} total={blocks.length} collapsed={collapsed.has(b.id)} onToggle={() => toggle(b.id)} onChange={upd} onMove={move} onDel={del} onInsert={idx => insertAt('paragraph', idx + 1)} onUpload={onUpload} onUploadMulti={onUploadMulti} />)}
    </div>
  );
}

const LiveEditor = React.forwardRef(function LiveEditor({ value, onChange, onRequestImage }, ref) {
  const el = React.useRef(null);
  const last = React.useRef(null);
  const lock = root => { if (root) root.querySelectorAll('figure,.photo-unit,.photo-group,.comparison,hr,.compare-item').forEach(n => n.setAttribute('contenteditable', 'false')); };
  const seed = v => { const e = el.current; if (!e) return; e.innerHTML = v || ''; last.current = v || ''; lock(e); };
  React.useEffect(() => { seed(value); try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch (_) {} }, []);
  React.useEffect(() => { if ((value || '') !== (last.current || '')) seed(value); }, [value]);
  const emit = () => { const e = el.current; if (!e) return; last.current = e.innerHTML; onChange && onChange(e.innerHTML); };
  const exec = (cmd, val) => { document.execCommand(cmd, false, val); el.current && el.current.focus(); emit(); };
  const fmtBlock = (tag, cls) => {
    document.execCommand('formatBlock', false, tag);
    if (cls) {
      const s = window.getSelection();
      if (s && s.rangeCount) {
        let n = s.getRangeAt(0).startContainer; if (n.nodeType === 3) n = n.parentNode;
        const want = tag.replace(/[<>]/g, '').toUpperCase();
        while (n && n !== el.current) { if (n.tagName === want) { n.className = cls; break; } n = n.parentNode; }
      }
    }
    el.current && el.current.focus(); emit();
  };
  React.useImperativeHandle(ref, () => ({
    focus: () => el.current && el.current.focus(),
    insertHtml: html => { el.current && el.current.focus(); document.execCommand('insertHTML', false, html); lock(el.current); emit(); },
    root: () => el.current,
  }));
  const blockOf = node => { const ee = el.current; if (!ee || !node) return null; if (node.nodeType === 3) node = node.parentNode; while (node && node.parentNode !== ee && node !== ee) node = node.parentNode; return node === ee ? null : node; };
  const onKey = e => {
    if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
      const s0 = window.getSelection();
      const before = s0 && s0.rangeCount ? blockOf(s0.getRangeAt(0).startContainer) : null;
      setTimeout(() => {
        const s = window.getSelection();
        const after = s && s.rangeCount ? blockOf(s.getRangeAt(0).startContainer) : null;
        if (after && after !== before && after.hasAttribute && after.hasAttribute('data-text-role')) {
          after.removeAttribute('data-text-role');
          emit();
        }
      }, 0);
      return;
    }
    if (!(e.ctrlKey || e.metaKey)) return;
    const k = e.key.toLowerCase();
    if (k === 'a') {
      e.preventDefault();
      const s = window.getSelection();
      const n = blockOf(s && s.rangeCount ? s.getRangeAt(0).startContainer : el.current && el.current.firstChild) || (el.current && el.current.firstChild);
      if (n && s) {
        const range = document.createRange();
        range.selectNodeContents(n);
        s.removeAllRanges();
        s.addRange(range);
      }
    }
    else if (k === 'b') { e.preventDefault(); exec('bold'); }
    else if (k === 'i') { e.preventDefault(); exec('italic'); }
    else if (k === 'u') { e.preventDefault(); exec('underline'); }
    else if (k === 'k') { e.preventDefault(); const u = prompt('Link URL'); if (u) exec('createLink', u); }
  };
  const B = (label, fn, title) => <button type="button" className="le-btn" title={title || label} onMouseDown={e => { e.preventDefault(); fn(); }}>{label}</button>;
  return (
    <div className="le-wrap">
      <div className="le-bar">
        {B('B', () => exec('bold'), 'Bold (Ctrl+B)')}
        {B('I', () => exec('italic'), 'Italic (Ctrl+I)')}
        {B('U', () => exec('underline'), 'Underline (Ctrl+U)')}
        <span className="le-sep" />
        {B('H2', () => fmtBlock('<h2>', 'section-heading'), 'Section heading')}
        {B('¶', () => fmtBlock('<p>', ''), 'Plain paragraph')}
        {B('Lede', () => { fmtBlock('<p>', ''); const s = window.getSelection(); if (s && s.rangeCount) { let n = s.getRangeAt(0).startContainer; if (n.nodeType === 3) n = n.parentNode; while (n && n !== el.current && n.tagName !== 'P') n = n.parentNode; if (n && n.tagName === 'P') { n.setAttribute('data-text-role', 'lede'); emit(); } } }, 'Mark lede paragraph')}
        {B('Quote', () => fmtBlock('<blockquote>', 'pull-quote'), 'Pull quote')}
        {B('• List', () => exec('insertUnorderedList'), 'Bulleted list')}
        {B('1. List', () => exec('insertOrderedList'), 'Numbered list')}
        <span className="le-sep" />
        {B('Link', () => { const u = prompt('Link URL'); if (u) exec('createLink', u); }, 'Link (Ctrl+K)')}
        {B('Unlink', () => exec('unlink'), 'Remove link')}
        {B('Image', () => onRequestImage && onRequestImage(), 'Insert image')}
        {B('Divider', () => exec('insertHorizontalRule'), 'Section divider')}
        <span className="le-sep" />
        {B('Clear', () => exec('removeFormat'), 'Clear inline formatting')}
      </div>
      <div ref={el} className="le-edit art-content" contentEditable suppressContentEditableWarning
        onInput={emit} onBlur={emit} onKeyDown={onKey} spellCheck={true} />
    </div>
  );
});

function TagInput({ allTags, value, onChange, onCreated }) {
  const [q, setQ] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [focus, setFocus] = React.useState(false);
  const sel = value || [];
  const tags = allTags || [];
  const byId = id => tags.find(t => t.id === id);
  const norm = s => (s || '').trim().replace(/^#+/, '');
  const ql = norm(q).toLowerCase();
  const matches = tags.filter(t => !sel.includes(t.id) && t.name.toLowerCase().includes(ql)).slice(0, 8);
  const exact = tags.find(t => t.name.toLowerCase() === ql);
  const add = id => { if (!sel.includes(id)) onChange([...sel, id]); setQ(''); };
  const create = async () => {
    const name = norm(q); if (!name || busy) return;
    if (exact) return add(exact.id);
    setBusy(true);
    const r = await API.post('/api/tags', { name }).catch(() => ({ error: 'Failed' }));
    setBusy(false);
    if (r && r.id) { onCreated && onCreated(r); onChange([...sel, r.id]); setQ(''); }
  };
  const onKey = e => {
    if (e.key === 'Enter') { e.preventDefault(); exact ? add(exact.id) : create(); }
    else if (e.key === 'Backspace' && !q && sel.length) onChange(sel.slice(0, -1));
  };
  return (
    <div className="taginput">
      <div className="taginput-box">
        {sel.map(id => { const t = byId(id); return (
          <span key={id} className="ti-chip">#{t ? t.name : ('#' + id)}<i onClick={() => onChange(sel.filter(x => x !== id))}>×</i></span>
        ); })}
        <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey}
          onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder={sel.length ? 'add a tag…' : '#type to search or create a tag…'} />
      </div>
      {focus && ql && (
        <div className="taginput-drop">
          {matches.map(t => (
            <div key={t.id} className="ti-opt" onMouseDown={e => { e.preventDefault(); add(t.id); }}>
              #{t.name}{t.article_count != null && <span className="ti-cnt">{t.article_count}</span>}
            </div>
          ))}
          {!exact && norm(q) && <div className="ti-opt ti-new" onMouseDown={e => { e.preventDefault(); create(); }}>{busy ? 'Creating…' : `Create “#${norm(q)}”`}</div>}
          {exact && !matches.length && <div className="ti-opt" style={{ opacity: .55 }}>already added</div>}
        </div>
      )}
    </div>
  );
}
