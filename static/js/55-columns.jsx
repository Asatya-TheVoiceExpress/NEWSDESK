
const CADENCE_OPTS = ['daily', 'weekly', 'monthly', 'custom'];
const ENTRY_LAYOUTS = ['prose', 'comic', 'slideshow', 'grid'];
const fmtEntryDate = d => { try { return new Date(d + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); } catch { return d; } };

function bookletUrl(id, period) {
  const now = new Date(), iso = d => d.toISOString().slice(0, 10);
  let from, to;
  if (period === 'week') { const off = (now.getDay() + 6) % 7, mon = new Date(now); mon.setDate(now.getDate() - off); const sun = new Date(mon); sun.setDate(mon.getDate() + 6); from = iso(mon); to = iso(sun); }
  else if (period === 'month') { from = iso(new Date(now.getFullYear(), now.getMonth(), 1)); to = iso(new Date(now.getFullYear(), now.getMonth() + 1, 0)); }
  else if (period === 'year') { from = iso(new Date(now.getFullYear(), 0, 1)); to = iso(new Date(now.getFullYear(), 11, 31)); }
  let u = '/api/columns/' + id + '/booklet?period=' + period;
  if (from && to) u += '&from=' + from + '&to=' + to;
  return u;
}
function BookletPicker({ id, label, colTitle }) {
  const [prebuilt, setPrebuilt] = React.useState(null);
  React.useEffect(() => {
    if (hasCap('server_render')) return;
    const prefix = String(colTitle || '') + ' ';
    API.get('/api/publications').then(d => {
      const all = (d && d.publications) || [];
      setPrebuilt(all.filter(p => (p.pub_type === 'booklet' || p.type === 'booklet')
        && String(p.title || '').indexOf(prefix) === 0 && p.download_url));
    }).catch(() => setPrebuilt([]));
  }, [colTitle]);

  if (hasCap('server_render')) {
    return (
      <select className="bs-divider-act" defaultValue="" style={{ marginLeft: 'auto', cursor: 'pointer' }}
        onChange={e => { if (e.target.value) { window.open(bookletUrl(id, e.target.value)); e.target.value = ''; } }}>
        <option value="">{label || 'Booklet ↓'}</option>
        <option value="week">This week</option>
        <option value="month">This month</option>
        <option value="year">This year</option>
        <option value="all">All time</option>
      </select>
    );
  }
  if (!prebuilt || !prebuilt.length) return null;
  const trim = t => { const i = String(t).indexOf('Booklet,'); return i < 0 ? t : String(t).slice(i + 8).trim(); };
  return (
    <select className="bs-divider-act" defaultValue="" style={{ marginLeft: 'auto', cursor: 'pointer' }}
      onChange={e => { if (e.target.value) { window.open(e.target.value, '_blank'); e.target.value = ''; } }}>
      <option value="">{label || 'Booklet ↓'}</option>
      {prebuilt.map(p => <option key={p.id} value={p.download_url.replace(/^\//, '')}>{trim(p.title)}</option>)}
    </select>
  );
}

function ColumnsPage({ setView, go }) {
  const [cols, setCols] = React.useState(null);
  React.useEffect(() => { API.get('/api/columns').then(d => setCols(safe(d))).catch(() => setCols([])); }, []);
  if (!cols) return <div className="loading">Loading columns</div>;
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-kicker">Periodicals</div>
        <h1 className="page-title">Columns</h1>
        <div className="page-sub">Running series from the desk — read as cards, browse by calendar, collected into booklets.</div>
      </div>
      {cols.length === 0
        ? <div className="empty"><div className="empty-icon">¶</div><div className="empty-title">No columns yet.</div><div className="empty-sub">{hasCap('admin')?'Start one in Admin → Columns.':'Check back soon.'}</div></div>
        : <div className="cols-grid">{cols.map(c => <ColumnNameplate key={c.id} col={c} onOpen={() => setView('col:' + c.slug)} />)}</div>}
    </div>
  );
}

function ColumnNameplate({ col, onOpen, compact }) {
  return (
    <div className={'col-plate' + (compact ? ' compact' : '')} onClick={onOpen} style={col.accent ? { '--accent': col.accent } : null}>
      {col.cover_image && <div className="col-plate-cover"><img src={col.cover_image} alt={col.title} /></div>}
      <div className="col-plate-body">
        <div className="col-plate-cadence">{col.cadence}{col.entry_count ? ` · ${col.entry_count} ${col.entry_count === 1 ? 'entry' : 'entries'}` : ''}</div>
        <div className="col-plate-title">{col.title}</div>
        {col.subtitle && <div className="col-plate-sub">{col.subtitle}</div>}
        {col.byline_auto && <div className="col-plate-by">By {col.byline_auto}</div>}
      </div>
    </div>
  );
}

function ColumnPage({ slug, setView, entryId, onOpenEntry, onCloseEntry, goBack }) {
  const [col, setCol] = React.useState(null);
  const [mode, setMode] = React.useState('cards');
  React.useEffect(() => { API.get('/api/columns/' + slug).then(setCol).catch(() => setCol(false)); }, [slug]);
  if (col === null) return <div className="loading">Loading column</div>;
  if (col === false || col.error) return <div className="empty"><div className="empty-title">Column not found.</div></div>;
  const entry = entryId ? (col.entries || []).find(e => String(e.id) === String(entryId)) : null;
  if (entryId && entry) return <ColumnEntryView entry={entry} col={col} onBack={onCloseEntry} />;
  return (
    <div className="page" style={col.accent ? { '--accent': col.accent } : null}>
      <div className="col-navbar">
        <button className="art-back" onClick={goBack}>‹ Back</button>
        <button className="art-back" onClick={() => setView('columns')}>All columns</button>
      </div>
      {entryId && !entry && <div className="empty"><div className="empty-title">That entry is no longer here.</div></div>}
      <div className="col-head">
        {col.cover_image && <img className="col-head-cover" src={col.cover_image} alt={col.title} />}
        <div>
          <div className="page-kicker">{col.cadence} column{col.byline_auto ? ` · by ${col.byline_auto}` : ''}</div>
          <h1 className="page-title">{col.title}</h1>
          {col.subtitle && <div className="page-sub">{col.subtitle}</div>}
          {col.description && <p className="col-desc">{col.description}</p>}
        </div>
      </div>
      <div className="col-viewbar">
        <div className="ed-tabs">
          {[['cards', 'Cards'], ['calendar', 'Calendar']].map(([m, l]) => <div key={m} className={`ed-tab${mode === m ? ' on' : ''}`} onClick={() => setMode(m)}>{l}</div>)}
        </div>
        {col.entries && col.entries.length > 0 && <BookletPicker id={col.id} colTitle={col.title} label="Booklet ↓" />}
      </div>
      {mode === 'cards'
        ? (col.entries && col.entries.length
          ? <div className="cols-grid">{col.entries.map(e => <EntryCard key={e.id} entry={e} onOpen={() => onOpenEntry(e.id)} />)}</div>
          : <div className="empty"><div className="empty-title">No entries yet.</div></div>)
        : <ColumnCalendar columnId={col.id} entries={col.entries || []} onOpen={e => onOpenEntry(e && e.id)} />}
    </div>
  );
}

function EntryCard({ entry, onOpen }) {
  return (
    <div className="col-plate" onClick={onOpen}>
      {entry.cover_image && <div className="col-plate-cover"><img src={entry.cover_image} alt={entry.title} /></div>}
      <div className="col-plate-body">
        <div className="col-plate-cadence">{fmtEntryDate(entry.entry_date)}</div>
        <div className="col-plate-title">{entry.title}</div>
        {entry.subtitle && <div className="col-plate-sub">{entry.subtitle}</div>}
        {(entry.tags || []).length > 0 && <div className="tags">{entry.tags.map(t => <span key={t} className="tag">{t}</span>)}</div>}
      </div>
    </div>
  );
}

function ColumnCalendar({ entries, onOpen }) {
  const [cursor, setCursor] = React.useState(() => { const d = entries[0] ? new Date(entries[0].entry_date + 'T12:00:00') : new Date(); return { y: d.getFullYear(), m: d.getMonth() }; });
  const byDate = {}; entries.forEach(e => { (byDate[e.entry_date] = byDate[e.entry_date] || []).push(e); });
  const first = new Date(cursor.y, cursor.m, 1); const start = first.getDay(); const days = new Date(cursor.y, cursor.m + 1, 0).getDate();
  const cells = []; for (let i = 0; i < start; i++) cells.push(null); for (let d = 1; d <= days; d++) cells.push(d);
  const ymd = d => `${cursor.y}-${String(cursor.m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const mname = new Date(cursor.y, cursor.m).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  const shift = n => setCursor(c => { const d = new Date(c.y, c.m + n, 1); return { y: d.getFullYear(), m: d.getMonth() }; });
  return (
    <div className="col-cal">
      <div className="col-cal-head"><button className="art-back" onClick={() => shift(-1)}>‹</button><span className="col-cal-month">{mname}</span><button className="art-back" onClick={() => shift(1)}>›</button></div>
      <div className="col-cal-grid">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => <div key={i} className="col-cal-dow">{d}</div>)}
        {cells.map((d, i) => <div key={i} className={'col-cal-cell' + (d && byDate[ymd(d)] ? ' has' : '')}>
          {d && <><span className="col-cal-num">{d}</span>{(byDate[ymd(d)] || []).map(e => <div key={e.id} className="col-cal-ev" onClick={() => onOpen(e)} title={e.title}>{e.title}</div>)}</>}
        </div>)}
      </div>
    </div>
  );
}

function ColumnEntryView({ entry, col, onBack }) {
  const ref = React.useRef(null);
  const [lb, setLb] = React.useState(null);
  React.useEffect(() => {
    const root = ref.current; if (!root) return;
    root.querySelectorAll('figure img').forEach(img => img.addEventListener('click', () => {
      const grp = img.closest('.photo-group'); const imgs = grp ? [...grp.querySelectorAll('img')] : [img];
      setLb({ items: imgs.map(im => ({ src: im.src, cap: (im.closest('figure')?.querySelector('figcaption')?.textContent) || '' })), index: Math.max(0, imgs.indexOf(img)) });
    }));
  }, [entry.id]);
  const panels = safe(entry.panels);
  const panelHtml = panels.length ? `<div class="photo-group" data-type="${entry.layout === 'prose' ? 'grid' : entry.layout}">` +
    panels.map(p => `<figure>${p.image ? `<img src="${p.image}" alt="">` : ''}${p.caption ? `<figcaption${entry.layout === 'comic' ? ' class="panel-caption"' : ''}>${p.caption}</figcaption>` : ''}${p.text ? `<div class="panel-text">${p.text}</div>` : ''}</figure>`).join('') + '</div>' : '';
  return (
    <div className="art-wrap" style={col.accent ? { '--accent': col.accent } : null}>
      <div className="art-nav-row"><button className="art-back" onClick={onBack}>‹ {col.title}</button>
        <div className="breadcrumb"><a onClick={onBack}>{col.title}</a><span>›</span><span>{fmtEntryDate(entry.entry_date)}</span></div></div>
      <div className="art-cat-lbl">{col.title} · {col.cadence}</div>
      <h1 className="art-title">{entry.title}</h1>
      {entry.subtitle && <div className="art-deck">{entry.subtitle}</div>}
      <div className="art-byline"><span>{fmtEntryDate(entry.entry_date)}</span></div>
      {entry.cover_image && <div className="art-fimg"><img src={entry.cover_image} alt={entry.title} /></div>}
      <div className="art-content dropcap" ref={ref} dangerouslySetInnerHTML={{ __html: (entry.body || '') + panelHtml }} />
      {(entry.tags || []).length > 0 && <div className="tags-sect tags" style={{ paddingTop: '.8rem', borderTop: 'var(--rt)' }}>{entry.tags.map(t => <span key={t} className="tag">{t}</span>)}</div>}
      {lb && <MediaLightbox items={lb.items} index={lb.index} onClose={() => setLb(null)} />}
    </div>
  );
}

function ColumnsRail({ setView }) {
  const [cols, setCols] = React.useState([]);
  React.useEffect(() => { API.get('/api/columns').then(d => setCols(safe(d).filter(c => c.is_featured).slice(0, 4))).catch(() => { }); }, []);
  if (!cols.length) return null;
  return (
    <div className="cols-rail">
      <div className="cols-rail-head"><span className="cols-rail-lbl">Columns</span><button className="bs-divider-act" onClick={() => setView('columns')}>All columns ↗</button></div>
      <div className="cols-rail-grid">{cols.map(c => <ColumnNameplate key={c.id} col={c} compact onOpen={() => setView('col:' + c.slug)} />)}</div>
    </div>
  );
}

function AdminColumns({ toast }) {
  const [cols, setCols] = React.useState([]);
  const [form, setForm] = React.useState(null);
  const [sel, setSel] = React.useState(null);
  const blank = { title: '', subtitle: '', description: '', cover_image: '', cadence: 'weekly', period_days: 7, accent: '', status: 'draft', is_featured: 0, is_private: 0 };
  const load = React.useCallback(() => API.get('/api/columns?status=all').then(d => setCols(safe(d))).catch(() => { }), []);
  React.useEffect(() => { load(); }, [load]);
  const up = async (e, cb) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append('file', f); const d = await API.upload('/api/upload', fd).catch(() => ({})); if (d.url) cb(d.url); e.target.value = ''; };
  const saveCol = async () => {
    if (!form.title.trim()) { toast('Title required', 'err'); return; }
    const r = form.id ? await API.put('/api/columns/' + form.id, form) : await API.post('/api/columns', form);
    if (r.error) { toast(r.error, 'err'); return; }
    toast('Column saved.'); setForm(null); load();
  };
  const delCol = async c => { if (!confirm('Delete column "' + c.title + '" and all its entries?')) return; await API.del('/api/columns/' + c.id); load(); };
  if (sel) return <AdminColumnEntries column={sel} onBack={() => { setSel(null); load(); }} toast={toast} onUpload={up} />;
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '1rem' }}>
        <div className="sec-lbl" style={{ flex: 1 }}><span>Columns</span></div>
        <button className="btn-p" onClick={() => setForm({ ...blank })}>+ New column</button>
      </div>
      {form && (
        <div style={{ border: 'var(--rule)', padding: '1.1rem', marginBottom: '1.2rem', background: 'var(--paper)' }}>
          <div className="form-row"><FormField label="Title"><input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} /></FormField>
            <FormField label="Subtitle"><input value={form.subtitle} onChange={e => setForm(f => ({ ...f, subtitle: e.target.value }))} /></FormField></div>
          <FormField label="Description"><textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={{ minHeight: 56 }} /></FormField>
          <div className="form-row3">
            <FormField label="Cadence"><select value={form.cadence} onChange={e => setForm(f => ({ ...f, cadence: e.target.value }))}>{CADENCE_OPTS.map(c => <option key={c} value={c}>{c}</option>)}</select></FormField>
            <FormField label="Period (days)"><input type="number" value={form.period_days} onChange={e => setForm(f => ({ ...f, period_days: +e.target.value }))} /></FormField>
            <FormField label="Accent"><input value={form.accent || ''} onChange={e => setForm(f => ({ ...f, accent: e.target.value }))} placeholder="#aa0000" /></FormField>
          </div>
          <div className="form-row">
            <FormField label="Cover image"><div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>{form.cover_image && <img src={form.cover_image} alt="" style={{ width: 60, height: 40, objectFit: 'cover', border: 'var(--rt)' }} />}<input value={form.cover_image || ''} onChange={e => setForm(f => ({ ...f, cover_image: e.target.value }))} placeholder="URL" /><input type="file" accept="image/*" onChange={e => up(e, u => setForm(f => ({ ...f, cover_image: u })))} style={{ border: 'none', padding: 0, fontSize: '.7rem' }} /></div></FormField>
            <FormField label="Status"><select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}><option value="draft">draft</option><option value="published">published</option></select></FormField>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '.45rem', fontFamily: 'var(--fm)', fontSize: '.6rem', textTransform: 'uppercase', margin: '.4rem 0' }}><input type="checkbox" checked={!!form.is_featured} onChange={e => setForm(f => ({ ...f, is_featured: e.target.checked ? 1 : 0 }))} style={{ width: 'auto' }} /> Feature on homepage</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '.45rem', fontFamily: 'var(--fm)', fontSize: '.6rem', textTransform: 'uppercase', margin: '.4rem 0' }}><input type="checkbox" checked={!!form.is_private} onChange={e => setForm(f => ({ ...f, is_private: e.target.checked ? 1 : 0 }))} style={{ width: 'auto' }} /> Private (admin/editor only — never public, never in the static mirrors)</label>
          <div style={{ display: 'flex', gap: '.5rem' }}><button className="btn-p" onClick={saveCol}>Save column</button><button className="btn-s" onClick={() => setForm(null)}>Cancel</button></div>
        </div>
      )}
      {cols.length === 0 && !form && <div style={{ fontFamily: 'var(--fm)', fontSize: '.62rem', color: 'var(--g400)', fontStyle: 'italic' }}>No columns yet.</div>}
      {cols.map(c => (
        <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '.7rem 1rem', border: 'var(--rt)', marginBottom: '.4rem' }}>
          <div style={{ flex: 1 }}><strong style={{ fontFamily: 'var(--fh)' }}>{c.title}</strong> <span style={{ fontFamily: 'var(--fm)', fontSize: '.58rem', color: 'var(--g500)', textTransform: 'uppercase' }}>{c.cadence} · {c.status} · {c.entry_count} entries{c.is_featured ? ' · featured' : ''}{c.is_private ? ' · private' : ''}</span></div>
          <button className="btn-s" onClick={() => setSel(c)}>Entries</button>
          <button className="btn-s" onClick={() => setForm({ ...c })}>Edit</button>
          <button className="btn-s" onClick={() => delCol(c)}>Delete</button>
        </div>
      ))}
    </div>
  );
}

function AdminColumnEntries({ column, onBack, toast, onUpload }) {
  const [data, setData] = React.useState(null);
  const [form, setForm] = React.useState(null);
  const blank = { entry_date: todayStr(), title: '', subtitle: '', cover_image: '', body: '', layout: 'prose', status: 'draft', panels: [] };
  const load = React.useCallback(() => API.get('/api/columns/' + column.slug + '?status=all').then(setData).catch(() => { }), [column.slug]);
  React.useEffect(() => { load(); }, [load]);
  const saveEntry = async () => {
    if (!form.title.trim()) { toast('Title required', 'err'); return; }
    const r = form.id ? await API.put('/api/column-entries/' + form.id, form) : await API.post('/api/columns/' + column.id + '/entries', form);
    if (r.error) { toast(r.error, 'err'); return; }
    toast('Entry saved.'); setForm(null); load();
  };
  const delEntry = async e => { if (!confirm('Delete entry "' + e.title + '"?')) return; await API.del('/api/column-entries/' + e.id); load(); };
  const editEntry = async e => { const full = await API.get('/api/column-entries/' + e.id).catch(() => e); setForm({ ...full, panels: safe(full.panels) }); };
  const setPanel = (i, patch) => setForm(f => ({ ...f, panels: f.panels.map((p, j) => j === i ? { ...p, ...patch } : p) }));
  const movePanel = (i, d) => setForm(f => { const j = i + d; if (j < 0 || j >= f.panels.length) return f; const n = [...f.panels];[n[i], n[j]] = [n[j], n[i]]; return { ...f, panels: n }; });
  if (!data) return <div className="loading">Loading entries</div>;
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '1rem', gap: '1rem' }}>
        <button className="art-back" onClick={onBack}>‹ Columns</button>
        <div className="sec-lbl" style={{ flex: 1 }}><span>{column.title} — entries</span></div>
        <BookletPicker id={column.id} colTitle={column.title} label="Compile booklet ↓" />
        <button className="btn-p" onClick={() => setForm({ ...blank })}>+ New entry</button>
      </div>
      {form && (
        <div style={{ border: 'var(--rule)', padding: '1.1rem', marginBottom: '1.2rem', background: 'var(--paper)' }}>
          <div className="form-row3">
            <FormField label="Date"><input type="date" value={form.entry_date} onChange={e => setForm(f => ({ ...f, entry_date: e.target.value }))} /></FormField>
            <FormField label="Layout"><select value={form.layout} onChange={e => setForm(f => ({ ...f, layout: e.target.value }))}>{ENTRY_LAYOUTS.map(l => <option key={l} value={l}>{l}</option>)}</select></FormField>
            <FormField label="Status"><select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}><option value="draft">draft</option><option value="published">published</option></select></FormField>
          </div>
          <div className="form-row"><FormField label="Title"><input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} /></FormField>
            <FormField label="Subtitle"><input value={form.subtitle || ''} onChange={e => setForm(f => ({ ...f, subtitle: e.target.value }))} /></FormField></div>
          <FormField label="Cover"><div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>{form.cover_image && <img src={form.cover_image} alt="" style={{ width: 60, height: 40, objectFit: 'cover', border: 'var(--rt)' }} />}<input value={form.cover_image || ''} onChange={e => setForm(f => ({ ...f, cover_image: e.target.value }))} placeholder="URL" /><input type="file" accept="image/*" onChange={e => onUpload(e, u => setForm(f => ({ ...f, cover_image: u })))} style={{ border: 'none', padding: 0, fontSize: '.7rem' }} /></div></FormField>
          <div className="form-g"><label className="form-lbl">Body (typeset)</label><SemanticComposer value={form.body || ''} onChange={v => setForm(f => ({ ...f, body: v }))} /></div>
          <div className="form-g"><label className="form-lbl">Panels</label>
            {(form.panels || []).map((p, i) => (
              <div key={i} style={{ display: 'flex', gap: '.4rem', alignItems: 'center', marginBottom: '.3rem' }}>
                {p.image && <img src={p.image} alt="" style={{ width: 54, height: 40, objectFit: 'cover', border: 'var(--rt)' }} />}
                <input value={p.image || ''} onChange={e => setPanel(i, { image: e.target.value })} placeholder="image URL" style={{ flex: 1 }} />
                <input value={p.caption || ''} onChange={e => setPanel(i, { caption: e.target.value })} placeholder="caption" style={{ flex: 1 }} />
                <button type="button" className="btn-s" onClick={() => movePanel(i, -1)}>↑</button>
                <button type="button" className="btn-s" onClick={() => movePanel(i, 1)}>↓</button>
                <button type="button" className="btn-s" onClick={() => setForm(f => ({ ...f, panels: f.panels.filter((_, j) => j !== i) }))}>✕</button>
              </div>
            ))}
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <button type="button" className="btn-s" onClick={() => setForm(f => ({ ...f, panels: [...(f.panels || []), { image: '', caption: '', text: '', span: 'half' }] }))}>+ panel</button>
              <input type="file" accept="image/*" onChange={e => onUpload(e, u => setForm(f => ({ ...f, panels: [...(f.panels || []), { image: u, caption: '', text: '', span: 'half' }] })))} style={{ border: 'none', padding: 0, fontSize: '.7rem' }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '.5rem' }}><button className="btn-p" onClick={saveEntry}>Save entry</button><button className="btn-s" onClick={() => setForm(null)}>Cancel</button></div>
        </div>
      )}
      {safe(data.entries).map(e => (
        <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '.6rem 1rem', border: 'var(--rt)', marginBottom: '.4rem' }}>
          <span style={{ fontFamily: 'var(--fm)', fontSize: '.58rem', color: 'var(--g500)', minWidth: 92 }}>{fmtEntryDate(e.entry_date)}</span>
          <div style={{ flex: 1, fontFamily: 'var(--fh)' }}>{e.title} <span style={{ fontFamily: 'var(--fm)', fontSize: '.55rem', color: 'var(--g500)', textTransform: 'uppercase' }}>· {e.layout} · {e.status}</span></div>
          <button className="btn-s" onClick={() => editEntry(e)}>Edit</button>
          <button className="btn-s" onClick={() => delEntry(e)}>Delete</button>
        </div>
      ))}
      {!safe(data.entries).length && !form && <div style={{ fontFamily: 'var(--fm)', fontSize: '.62rem', color: 'var(--g400)', fontStyle: 'italic' }}>No entries yet.</div>}
    </div>
  );
}
