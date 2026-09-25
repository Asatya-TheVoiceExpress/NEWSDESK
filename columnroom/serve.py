#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template_string, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, ROOT)
import ve.db as _ve_db
import ve.paths as _ve_paths
import ve.tags as _ve_tags
import ve.repo as _ve_repo


def _load_config():
    with open(os.path.join(BASE, 'config.json'), encoding='utf-8') as fh:
        cfg = json.load(fh)
    for key in ('db_path', 'media_path'):
        p = cfg.get(key)
        if p and not os.path.isabs(p):
            cfg[key] = os.path.normpath(os.path.join(BASE, p))
    return cfg


CFG = _load_config()
DB_PATH = _ve_paths.db_path(BASE)
MEDIA_PATH = _ve_paths.uploads_path(BASE)
os.makedirs(MEDIA_PATH, exist_ok=True)
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif'}

app = Flask(__name__)


def get_db():
    return _ve_db.connect(DB_PATH)


def ensure_schema():
    db = get_db()
    _ve_db.migrate(db)
    db.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def _meta_row(db, cid):
    row = db.execute('SELECT * FROM column_room_meta WHERE column_id=?', [cid]).fetchone()
    if row:
        return dict(row)
    return {'column_id': cid, 'template': '{}', 'ended_at': None}


def _entry_dict(db, row):
    return _ve_repo.entry_dict(db, row)


@app.route('/api/tags', methods=['GET'])
def list_tags():
    db = get_db()
    try:
        return jsonify([dict(r) for r in db.execute('SELECT id,name FROM tags ORDER BY name').fetchall()])
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/entries/tags', methods=['POST'])
def tag_all_entries(cid):
    data = request.json or {}
    tag_ids = list(dict.fromkeys(int(t) for t in (data.get('tag_ids') or [])))
    db = get_db()
    try:
        if not db.execute('SELECT 1 FROM columns WHERE id=?', [cid]).fetchone():
            return jsonify({'error': 'Column not found'}), 404
        eids = [r[0] for r in db.execute('SELECT id FROM column_entries WHERE column_id=?', [cid]).fetchall()]
        _ve_tags.add_entry_tags(db, eids, tag_ids)
        db.commit()
        return jsonify({'success': True, 'entries': len(eids), 'tags': len(tag_ids)})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


def _unique_slug(db, base):
    import re
    slug = re.sub(r'[^\w\s-]', '', base.lower()).strip()
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')[:80] or 'column'
    s, i = slug, 1
    while db.execute('SELECT 1 FROM columns WHERE slug=?', [s]).fetchone():
        s = f'{slug}-{i}'; i += 1
    return s


@app.route('/api/columns', methods=['GET'])
def list_columns():
    db = get_db()
    try:
        rows = db.execute('''SELECT c.*,
            (SELECT COUNT(*) FROM column_entries e WHERE e.column_id=c.id) AS entry_count,
            (SELECT MAX(entry_date) FROM column_entries e WHERE e.column_id=c.id) AS last_entry_date
            FROM columns c ORDER BY c.sort_order, c.title''').fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['ended_at'] = _meta_row(db, d['id']).get('ended_at')
            out.append(d)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/columns', methods=['POST'])
def create_column():
    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title required'}), 400
    db = get_db()
    try:
        slug = _unique_slug(db, title)
        ts = now()
        db.execute('''INSERT INTO columns (title,slug,subtitle,description,cover_image,cadence,
            period_days,accent,status,is_featured,is_private,sort_order,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', [
            title, slug, data.get('subtitle', ''), data.get('description', ''), '',
            data.get('cadence', 'weekly'), int(data.get('period_days') or 7), '',
            data.get('status', 'draft'), 0, 1 if data.get('is_private') else 0, 0, ts, ts])
        cid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': cid, 'slug': slug}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>', methods=['PUT'])
def update_column(cid):
    data = request.json or {}
    db = get_db()
    try:
        ex = db.execute('SELECT * FROM columns WHERE id=?', [cid]).fetchone()
        if not ex: return jsonify({'error': 'Not found'}), 404
        db.execute('''UPDATE columns SET title=?,cadence=?,period_days=?,status=?,is_private=?,updated_at=? WHERE id=?''', [
            (data.get('title') or ex['title']).strip(), data.get('cadence', ex['cadence']),
            int(data.get('period_days', ex['period_days']) or 7), data.get('status', ex['status']),
            1 if data.get('is_private', ex['is_private']) else 0,
            now(), cid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/end', methods=['POST'])
def end_column(cid):
    db = get_db()
    try:
        if not db.execute('SELECT 1 FROM columns WHERE id=?', [cid]).fetchone():
            return jsonify({'error': 'Not found'}), 404
        db.execute('INSERT INTO column_room_meta (column_id,template,ended_at) VALUES (?,COALESCE((SELECT template FROM column_room_meta WHERE column_id=?),"{}"),?) '
                   'ON CONFLICT(column_id) DO UPDATE SET ended_at=excluded.ended_at', [cid, cid, now()])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/reopen', methods=['POST'])
def reopen_column(cid):
    db = get_db()
    try:
        db.execute('UPDATE column_room_meta SET ended_at=NULL WHERE column_id=?', [cid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/template', methods=['GET'])
def get_template(cid):
    db = get_db()
    try:
        m = _meta_row(db, cid)
        try:
            tpl = json.loads(m.get('template') or '{}')
        except (TypeError, ValueError):
            tpl = {}
        tpl.setdefault('layout', 'prose')
        tpl.setdefault('panels', [])
        return jsonify(tpl)
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/template', methods=['PUT'])
def save_template(cid):
    data = request.json or {}
    tpl = {'layout': data.get('layout', 'prose'),
           'panels': [{'caption': p.get('caption', ''), 'span': p.get('span', 'half')} for p in (data.get('panels') or [])]}
    db = get_db()
    try:
        if not db.execute('SELECT 1 FROM columns WHERE id=?', [cid]).fetchone():
            return jsonify({'error': 'Column not found'}), 404
        db.execute('INSERT INTO column_room_meta (column_id,template) VALUES (?,?) '
                   'ON CONFLICT(column_id) DO UPDATE SET template=excluded.template', [cid, json.dumps(tpl)])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/entries', methods=['GET'])
def list_entries(cid):
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM column_entries WHERE column_id=? ORDER BY entry_date DESC, sort_order', [cid]).fetchall()
        return jsonify([_entry_dict(db, r) for r in rows])
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/entries', methods=['POST'])
def create_entry(cid):
    db = get_db()
    try:
        if not db.execute('SELECT 1 FROM columns WHERE id=?', [cid]).fetchone():
            return jsonify({'error': 'Column not found'}), 404
        data = dict(request.json or {})
        layout = data.get('layout')
        panels = data.get('panels')
        if data.get('use_template'):
            m = _meta_row(db, cid)
            try:
                tpl = json.loads(m.get('template') or '{}')
            except (TypeError, ValueError):
                tpl = {}
            layout = layout or tpl.get('layout', 'prose')
            panels = panels if panels is not None else [dict(p) for p in tpl.get('panels', [])]
        data['layout'] = layout or 'prose'
        data['panels'] = panels
        eid = _ve_repo.create_entry(db, cid, data, now())
        return jsonify({'id': eid}), 201
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/entries/<int:eid>', methods=['GET'])
def get_entry(eid):
    db = get_db()
    try:
        return jsonify(_ve_repo.get_entry(db, eid, joined=False))
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    finally:
        db.close()


@app.route('/api/entries/<int:eid>', methods=['PUT'])
def update_entry(eid):
    db = get_db()
    try:
        _ve_repo.update_entry(db, eid, request.json or {}, now())
        return jsonify({'success': True})
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/entries/<int:eid>', methods=['DELETE'])
def delete_entry(eid):
    db = get_db()
    try:
        _ve_repo.delete_entry(db, eid)
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/media/upload', methods=['POST'])
def media_upload():
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'file required'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else 'jpg'
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Unsupported image type'}), 400
    fn = f'{uuid.uuid4().hex}.{ext}'
    f.save(os.path.join(MEDIA_PATH, fn))
    return jsonify({'url': f'/static/uploads/{fn}'})


@app.route('/static/uploads/<path:p>')
def serve_upload(p):
    return send_from_directory(MEDIA_PATH, p)


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


INDEX_HTML = r'''<!doctype html><html><head><meta charset="utf-8">
<title>Columnroom</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--line:#000;--dim:#555;--bg:#fff;--fg:#000;--vlink:#0000ee;--panel:#f2f2f2}
*{box-sizing:border-box}
body{margin:0;font:13px/1.45 Verdana,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--fg)}
h1,h2,h3,h4{font-family:Georgia,'Times New Roman',serif;font-weight:bold;margin:0}
a{color:var(--vlink)}
header{display:flex;align-items:center;gap:1rem;padding:.5rem 1rem;border-bottom:2px solid var(--line);background:var(--panel)}
header h1{font-size:1.05rem}
select#colSel{max-width:300px;font:inherit}
main{display:grid;grid-template-columns:250px 1px 1fr;height:calc(100vh - 46px)}
.divider{background:var(--line)}
.list{overflow:auto;padding:.6rem}
.edit{overflow:auto;padding:.9rem 1.2rem}
table{border-collapse:collapse;width:100%}
table.grid td,table.grid th{border:1px solid var(--line);padding:.25rem .4rem;text-align:left;font-size:.78rem}
table.grid th{background:var(--panel)}
.mi{border:1px solid var(--line);padding:.4rem .5rem;margin-bottom:.3rem;cursor:pointer;background:#fff}
.mi:hover{background:var(--panel)}
.bulk{border:1px solid var(--line);padding:.5rem;margin-bottom:.6rem;background:var(--panel)}
.mi.is-active{background:var(--panel);font-weight:bold}
.hint{color:var(--dim);font-size:.76rem}
.field{margin-bottom:.6rem}
.field label{display:block;font-size:.72rem;color:var(--dim);margin-bottom:.15rem;text-transform:uppercase;letter-spacing:.02em}
input,select,textarea{width:100%;padding:.35rem .4rem;border:1px solid var(--line);font:inherit;background:#fff;color:#000;border-radius:0}
textarea{min-height:90px;resize:vertical}
.wysiwyg{min-height:160px;border:1px solid var(--line);padding:.5rem}
.row{display:flex;gap:.6rem}
.row>*{flex:1}
button,.btn{border:1px solid var(--line);background:#fff;padding:.3rem .7rem;cursor:pointer;font:inherit;border-radius:0}
button:hover{background:var(--panel)}
button.primary{background:#000;color:#fff}
button.primary:hover{background:#222}
.tb{display:flex;gap:.4rem;margin-top:.6rem;flex-wrap:wrap}
.panel{border:1px dashed var(--line);padding:.5rem;margin-bottom:.5rem}
img.thumb{max-width:110px;display:block;margin-bottom:.3rem}
fieldset{border:1px solid var(--line);margin:0 0 .8rem}
legend{font-size:.72rem;color:var(--dim);text-transform:uppercase;padding:0 .3rem}
details{border:1px solid var(--line);margin-bottom:.7rem}
details>summary{cursor:pointer;padding:.4rem .5rem;background:var(--panel);font-weight:bold;list-style:none}
details>summary::-webkit-details-marker{display:none}
details>summary:before{content:"+ ";}
details[open]>summary:before{content:"- ";}
details>.body{padding:.6rem}
.status-ok{color:#0a5;font-weight:bold}
.status-bad{color:#c00;font-weight:bold}
.status-ended{color:var(--dim);font-weight:bold}
.timeline{display:flex;flex-wrap:wrap;gap:2px;margin:.4rem 0}
.tl-cell{width:22px;height:22px;border:1px solid var(--line);font-size:.6rem;display:flex;align-items:center;justify-content:center}
.tl-cell.done{background:#cfead9}
.tl-cell.missing{background:#f6cfcf}
.tl-cell.future{background:#fff;color:#bbb}
@media(prefers-color-scheme:dark){
 :root{--line:#ccc;--dim:#aaa;--bg:#111;--fg:#eee;--panel:#1e1e1e}
 select,input,textarea,button,.mi,.wysiwyg,details>summary{background:#161616;color:#eee;border-color:#ccc}
 .mi:hover{background:#2a2a2a;color:#eee}
 .mi.is-active{background:#242424}
 .mi.is-active:hover{background:#303030}
 button.primary{background:#eee;color:#111}
 button.primary:hover{background:#ccc}
 table.grid th{background:#1e1e1e}
 .tl-cell.done{background:#173a24}
 .tl-cell.missing{background:#3a1717}
}
.nrlink{margin-left:auto;border:1px solid var(--line);padding:.3rem .7rem;text-decoration:none;color:inherit;font-size:.78rem;background:#fff}
.nrlink:hover{background:#000;color:#fff}
@media(prefers-color-scheme:dark){.nrlink{background:#161616;color:#eee}.nrlink:hover{background:#eee;color:#111}}
</style></head>
<body>
<header>
  <h1>COLUMNROOM</h1>
  <a href="http://localhost:8790" target="_blank" class="nrlink" title="Collect reader data, publish to both sites, analytics">▤ Newsroom</a>
  <select id="colSel"></select>
  <button id="newColBtn">+ New column</button>
  <span style="flex:1"></span>
  <span class="hint" id="statusLine"></span>
</header>
<main>
  <div class="list" id="list"></div>
  <div class="divider"></div>
  <div class="edit" id="edit"></div>
</main>
<script>
const $list = document.getElementById('list');
const $edit = document.getElementById('edit');
const $colSel = document.getElementById('colSel');
const $statusLine = document.getElementById('statusLine');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const j = (url, opts) => fetch(url, Object.assign({headers: opts&&opts.body instanceof FormData ? {} : {'Content-Type':'application/json'}}, opts))
  .then(r => r.json().then(d => { if (!r.ok) throw new Error(d.error||r.statusText); return d; }));
const mkbtn = (label, cls, fn) => { const b=document.createElement('button'); if(cls) b.className=cls; b.textContent=label; b.onclick=fn; return b; };
function field(label, get, set, opts={}){
  const w=document.createElement('div'); w.className='field';
  const lab=document.createElement('label'); lab.textContent=label; w.appendChild(lab);
  let i;
  if(opts.select){
    i=document.createElement('select');
    i.innerHTML = opts.select.map(o=>`<option ${get()===o?'selected':''}>${esc(o)}</option>`).join('');
    i.onchange=()=>set(i.value);
  } else if(opts.area){
    i=document.createElement('textarea'); i.value=get()||''; i.oninput=()=>set(i.value);
  } else {
    i=document.createElement('input'); if(opts.type) i.type=opts.type;
    i.value=get()??''; i.oninput=()=>set(i.value);
  }
  w.appendChild(i); return w;
}
function imagePicker(getUrl, setUrl, redraw){
  const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML='<label>Image</label>';
  if(getUrl()) { const im=document.createElement('img'); im.src=getUrl(); im.className='thumb'; wrap.appendChild(im); }
  const path=document.createElement('input'); path.placeholder='/static/uploads/... path'; path.value=getUrl()||'';
  path.oninput=()=>setUrl(path.value);
  const fileInp=document.createElement('input'); fileInp.type='file'; fileInp.accept='image/*'; fileInp.style.marginTop='.3rem';
  fileInp.onchange=async ()=>{
    if(!fileInp.files[0]) return;
    const fd=new FormData(); fd.append('file', fileInp.files[0]);
    const r=await j('/api/media/upload',{method:'POST',body:fd});
    setUrl(r.url); redraw && redraw();
  };
  wrap.append(path, fileInp);
  return wrap;
}

function isoWeekKey(d){
  const dt = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = (dt.getUTCDay() + 6) % 7;
  dt.setUTCDate(dt.getUTCDate() - day + 3);
  const firstThursday = new Date(Date.UTC(dt.getUTCFullYear(),0,4));
  const week = 1 + Math.round(((dt - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay()+6)%7)) / 7);
  return `${dt.getUTCFullYear()}-W${String(week).padStart(2,'0')}`;
}
function customAnchor(col, entries){
  const today = new Date().toISOString().slice(0,10);
  if(entries && entries.length) return entries.reduce((a,e)=>e.entry_date<a?e.entry_date:a, entries[0].entry_date);
  return (col.created_at||today).slice(0,10);
}
function periodKey(col, dateStr, anchor){
  const d = new Date(dateStr + 'T00:00:00Z');
  if(col.cadence === 'daily') return dateStr;
  if(col.cadence === 'monthly') return dateStr.slice(0,7);
  if(col.cadence === 'custom'){
    const start = new Date((anchor||col.created_at||dateStr).slice(0,10) + 'T00:00:00Z');
    const days = Math.floor((d - start) / 86400000);
    const idx = Math.floor(days / (col.period_days || 7));
    return 'P' + idx;
  }
  return isoWeekKey(d);
}
function periodLabel(col, key){
  if(col.cadence === 'custom') return key.replace('P','window ');
  return key;
}
function buildTimeline(col, entries){
  const today = new Date().toISOString().slice(0,10);
  const start = customAnchor(col, entries);
  const doneKeys = new Set(entries.filter(e=>e.status==='published'||e.status==='draft').map(e=>periodKey(col, e.entry_date, start)));
  const cells = [];
  if(col.cadence === 'custom'){
    const startDate = new Date(start+'T00:00:00Z');
    const todayDate = new Date(today+'T00:00:00Z');
    const total = Math.max(0, Math.floor((todayDate-startDate)/86400000/(col.period_days||7)));
    for(let i=0;i<=total;i++){ const key='P'+i; cells.push({key, label:'#'+(i+1), done: doneKeys.has(key)}); }
    return cells;
  }
  let cur = new Date(start+'T00:00:00Z');
  const end = new Date(today+'T00:00:00Z');
  const step = col.cadence === 'daily' ? 1 : (col.cadence === 'monthly' ? 30 : 7);
  const seen = new Set();
  while(cur <= end && cells.length < 400){
    const ds = cur.toISOString().slice(0,10);
    const key = periodKey(col, ds);
    if(!seen.has(key)){
      seen.add(key);
      cells.push({key, label: col.cadence==='monthly'?key.slice(5):key.split('-').pop().replace('W',''), done: doneKeys.has(key)});
    }
    if(col.cadence === 'monthly'){ cur.setUTCMonth(cur.getUTCMonth()+1); } else { cur.setUTCDate(cur.getUTCDate()+step); }
  }
  return cells;
}

let columns = [], curColumn = null, entries = [], curEntry = null, activeView = 'entries';

let allTags = [];
async function boot(){
  allTags = await j('/api/tags');
  columns = await j('/api/columns');
  refreshSelect();
  curColumn = columns.length ? columns[0] : null;
  $colSel.onchange = async () => { curColumn = columns.find(c=>c.id===Number($colSel.value)); curEntry=null; await loadEntries(); render(); };
  document.getElementById('newColBtn').onclick = createColumnFlow;
  if(curColumn) await loadEntries();
  render();
}
function refreshSelect(){
  $colSel.innerHTML = columns.map(c=>`<option value="${c.id}">${c.is_private?'[private] ':''}${esc(c.title)}${c.ended_at?' (ended)':''} (${c.entry_count})</option>`).join('');
  if(curColumn) $colSel.value = curColumn.id;
}
async function createColumnFlow(){
  const title = prompt('New column title'); if(!title) return;
  const r = await j('/api/columns', {method:'POST', body: JSON.stringify({title})});
  columns = await j('/api/columns');
  curColumn = columns.find(c=>c.id===r.id); curEntry=null;
  refreshSelect(); await loadEntries(); render();
}
async function loadEntries(){
  entries = curColumn ? await j(`/api/columns/${curColumn.id}/entries`) : [];
}
function render(){
  drawList(); drawEdit();
  if(curColumn){
    const anchor = customAnchor(curColumn, entries);
    const done = entries.some(e=>periodKey(curColumn, e.entry_date, anchor) === periodKey(curColumn, new Date().toISOString().slice(0,10), anchor));
    $statusLine.innerHTML = curColumn.ended_at ? `<span class="status-ended">RUN ENDED ${esc((curColumn.ended_at||'').slice(0,10))}</span>`
      : (done ? '<span class="status-ok">current period: done</span>' : '<span class="status-bad">current period: missing</span>');
  } else { $statusLine.textContent=''; }
}
function drawList(){
  $list.innerHTML='';
  if(!curColumn){ $list.innerHTML='<div class="hint">No columns yet -- create one above.</div>'; return; }

  const tabs = document.createElement('div'); tabs.className='tb'; tabs.style.marginBottom='.6rem';
  ['entries','timeline','template','settings'].forEach(v=>{
    tabs.appendChild(mkbtn(v, activeView===v?'primary':'', ()=>{ activeView=v; render(); }));
  });
  $list.appendChild(tabs);

  if(activeView !== 'entries'){ $list.appendChild(Object.assign(document.createElement('div'),{className:'hint',textContent:'Entry list hidden on this tab.'})); return; }

  const add = mkbtn('+ New entry','primary', async ()=>{
    const useTpl = confirm('Start from this column\'s saved template?');
    const r = await j(`/api/columns/${curColumn.id}/entries`, {method:'POST', body: JSON.stringify({title:'Untitled', entry_date:new Date().toISOString().slice(0,10), use_template: useTpl})});
    await loadEntries();
    curEntry = entries.find(e=>e.id===r.id);
    drawList(); drawEdit();
  });
  add.style.width='100%'; add.style.marginBottom='.6rem';
  $list.appendChild(add);
  const bulkBtn = mkbtn('Tag all entries','', ()=>{ bulkOpen=!bulkOpen; drawList(); });
  bulkBtn.style.cssText='width:100%;margin-bottom:.6rem';
  $list.appendChild(bulkBtn);
  if(bulkOpen) $list.appendChild(bulkPanel());
  entries.forEach(en=>{
    const row=document.createElement('div'); row.className='mi'+(curEntry&&curEntry.id===en.id?' is-active':'');
    row.innerHTML = `<b>${esc(en.entry_date)} -- ${esc(en.title)}</b><br><span class="hint">${esc(en.status)} - ${esc(en.layout)}</span>`;
    row.onclick=async ()=>{ curEntry = await j('/api/entries/'+en.id); drawList(); drawEdit(); };
    $list.appendChild(row);
  });
  if(!entries.length) $list.appendChild(Object.assign(document.createElement('div'),{className:'hint',textContent:'No entries yet.'}));
}
let bulkOpen = false;
function bulkPanel(){
  const box=document.createElement('div'); box.className='bulk';
  const picked=[];
  const chips=document.createElement('div'); chips.style.cssText='display:flex;flex-wrap:wrap;gap:.3rem;margin-bottom:.3rem';
  const sel=document.createElement('select');
  const msg=document.createElement('div'); msg.className='hint'; msg.style.marginTop='.4rem';
  const draw=()=>{
    chips.innerHTML='';
    picked.forEach(id=>{
      const t=allTags.find(x=>x.id===id); if(!t) return;
      chips.appendChild(mkbtn(t.name+' ×','', ()=>{ picked.splice(picked.indexOf(id),1); draw(); }));
    });
    sel.innerHTML='<option value="">add tag…</option>'+allTags.filter(t=>!picked.includes(t.id)).map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join('');
  };
  sel.onchange=()=>{ if(sel.value){ picked.push(+sel.value); draw(); } };
  draw();
  const lab=document.createElement('div'); lab.className='hint'; lab.style.marginBottom='.3rem';
  lab.textContent=`Add these tags to all ${entries.length} entries in this column.`;
  const tb=document.createElement('div'); tb.className='tb';
  const apply=mkbtn('Apply','primary', async ()=>{
    if(!picked.length){ msg.textContent='Pick at least one tag.'; return; }
    apply.disabled=true;
    try{
      const r=await j(`/api/columns/${curColumn.id}/entries/tags`, {method:'POST', body: JSON.stringify({tag_ids:picked})});
      msg.textContent=`Tagged ${r.entries} entries`;
      await loadEntries();
      if(curEntry) curEntry = await j('/api/entries/'+curEntry.id);
      drawEdit();
    }catch(err){ msg.textContent='Failed: '+err.message; }
    apply.disabled=false;
  });
  tb.append(apply, mkbtn('Close','', ()=>{ bulkOpen=false; drawList(); }));
  box.append(lab, chips, sel, tb, msg);
  return box;
}
function drawEdit(){
  $edit.innerHTML='';
  if(!curColumn){ $edit.innerHTML='<div class="hint">Create a column to get started.</div>'; return; }
  if(activeView === 'timeline') return drawTimeline();
  if(activeView === 'template') return drawTemplate();
  if(activeView === 'settings') return drawSettings();
  return drawEntryEdit();
}

function drawTimeline(){
  const cells = buildTimeline(curColumn, entries);
  const h=document.createElement('h3'); h.textContent = `Timeline -- ${curColumn.title}`;
  const hint=document.createElement('div'); hint.className='hint'; hint.style.margin='.3rem 0 .6rem';
  hint.textContent = `Cadence: ${curColumn.cadence}${curColumn.cadence==='custom'?` (every ${curColumn.period_days} days)`:''}. Green = entry exists for that period, red = missing.`;
  const tl = document.createElement('div'); tl.className='timeline';
  cells.forEach(c=>{
    const cell=document.createElement('div'); cell.className='tl-cell '+(c.done?'done':'missing'); cell.title=periodLabel(curColumn,c.key);
    cell.textContent = c.label;
    tl.appendChild(cell);
  });
  $edit.append(h, hint, tl);
}

function drawTemplate(){
  const h=document.createElement('h3'); h.textContent = `Template -- ${curColumn.title}`;
  const hint=document.createElement('div'); hint.className='hint'; hint.style.margin='.3rem 0 .6rem';
  hint.textContent = 'Build once: the default layout + panel skeleton (captions/spans) new entries can start from. Choose "start from template" when creating an entry.';
  $edit.append(h, hint);
  const state = {layout:'prose', panels:[]};
  j(`/api/columns/${curColumn.id}/template`).then(tpl=>{
    state.layout = tpl.layout; state.panels = tpl.panels || [];
    drawBody();
  });
  const body = document.createElement('div'); $edit.appendChild(body);
  function drawBody(){
    body.innerHTML='';
    body.appendChild(field('Default layout', ()=>state.layout, v=>state.layout=v, {select:['prose','comic','slideshow','grid']}));
    const panelsWrap=document.createElement('div'); panelsWrap.className='field'; panelsWrap.innerHTML='<label>Panel skeleton</label>';
    const rows=document.createElement('div');
    const drawPanels=()=>{
      rows.innerHTML='';
      state.panels.forEach((p,i)=>{
        const pr=document.createElement('div'); pr.className='panel';
        const cap=document.createElement('input'); cap.placeholder='Caption hint'; cap.value=p.caption||''; cap.oninput=()=>p.caption=cap.value; cap.style.marginBottom='.3rem';
        const span=document.createElement('select'); span.innerHTML=['full','wide','half','third'].map(s=>`<option ${p.span===s?'selected':''}>${s}</option>`).join('');
        span.onchange=()=>p.span=span.value;
        const rm=mkbtn('Remove','', ()=>{ state.panels.splice(i,1); drawPanels(); });
        pr.append(cap, span, rm);
        rows.appendChild(pr);
      });
    };
    drawPanels();
    const addPanel=mkbtn('+ Panel slot','', ()=>{ state.panels.push({caption:'',span:'half'}); drawPanels(); });
    panelsWrap.append(rows, addPanel); body.appendChild(panelsWrap);
    const tb=document.createElement('div'); tb.className='tb';
    const saveBtn=mkbtn('Save template','primary', async ()=>{
      saveBtn.textContent='Saving...';
      try{ await j(`/api/columns/${curColumn.id}/template`, {method:'PUT', body: JSON.stringify(state)}); saveBtn.textContent='Saved'; }
      catch(e){ saveBtn.textContent='Failed: '+e.message; }
      setTimeout(()=>saveBtn.textContent='Save template',1400);
    });
    tb.appendChild(saveBtn); body.appendChild(tb);
  }
}

function drawSettings(){
  const h=document.createElement('h3'); h.textContent = `Settings -- ${curColumn.title}`; h.style.marginBottom='.6rem';
  $edit.appendChild(h);
  const state = {...curColumn};
  $edit.appendChild(field('Title', ()=>state.title, v=>state.title=v));
  const row=document.createElement('div'); row.className='row';
  row.append(
    field('Cadence', ()=>state.cadence, v=>state.cadence=v, {select:['daily','weekly','monthly','custom']}),
    field('Period days (custom)', ()=>state.period_days, v=>state.period_days=v, {type:'number'}),
    field('Status', ()=>state.status, v=>state.status=v, {select:['draft','published']}),
  );
  $edit.appendChild(row);
  const privRow=document.createElement('label'); privRow.className='hint'; privRow.style.display='block'; privRow.style.margin='.4rem 0 .8rem';
  const privCb=document.createElement('input'); privCb.type='checkbox'; privCb.style.width='auto'; privCb.style.marginRight='.4rem'; privCb.checked=!!state.is_private;
  privCb.onchange=()=>state.is_private=privCb.checked?1:0;
  privRow.append(privCb, 'Private (admin/editor only -- never public, never in the static mirrors)');
  $edit.appendChild(privRow);
  const tb=document.createElement('div'); tb.className='tb';
  const saveBtn=mkbtn('Save','primary', async ()=>{
    saveBtn.textContent='Saving...';
    try{ await j(`/api/columns/${curColumn.id}`, {method:'PUT', body: JSON.stringify(state)}); columns = await j('/api/columns'); curColumn = columns.find(c=>c.id===curColumn.id); refreshSelect(); saveBtn.textContent='Saved'; render(); }
    catch(e){ saveBtn.textContent='Failed: '+e.message; }
    setTimeout(()=>saveBtn.textContent='Save',1400);
  });
  tb.appendChild(saveBtn);
  if(curColumn.ended_at){
    tb.appendChild(mkbtn('Reopen run','', async ()=>{ await j(`/api/columns/${curColumn.id}/reopen`,{method:'POST'}); columns=await j('/api/columns'); curColumn=columns.find(c=>c.id===curColumn.id); refreshSelect(); render(); }));
  } else {
    tb.appendChild(mkbtn('End this column\'s run','', async ()=>{
      if(!confirm(`Mark "${curColumn.title}" as ended? It stays on the site, Columnroom will just flag it as no longer active.`)) return;
      await j(`/api/columns/${curColumn.id}/end`,{method:'POST'}); columns=await j('/api/columns'); curColumn=columns.find(c=>c.id===curColumn.id); refreshSelect(); render();
    }));
  }
  $edit.appendChild(tb);
}

function drawEntryEdit(){
  if(!curEntry){ $edit.innerHTML='<div class="hint">Select or create an entry.</div>'; return; }
  $edit.innerHTML='';
  const e = curEntry;
  const r1=document.createElement('div'); r1.className='row';
  r1.append(
    field('Date', ()=>e.entry_date, v=>e.entry_date=v, {type:'date'}),
    field('Layout', ()=>e.layout, v=>e.layout=v, {select:['prose','comic','slideshow','grid']}),
    field('Status', ()=>e.status, v=>e.status=v, {select:['draft','published']}),
  );
  $edit.append(
    field('Title', ()=>e.title, v=>e.title=v),
    field('Subtitle', ()=>e.subtitle, v=>e.subtitle=v),
  );
  $edit.appendChild(r1);
  $edit.appendChild(imagePicker(()=>e.cover_image, v=>e.cover_image=v, drawEntryEdit));

  const bodyWrap=document.createElement('div'); bodyWrap.className='field'; bodyWrap.innerHTML='<label>Body</label>';
  const wtb=document.createElement('div'); wtb.className='tb'; wtb.style.marginTop='0'; wtb.style.marginBottom='.3rem';
  [['Bold','bold'],['Italic','italic'],['Link','createLink'],['Quote','formatBlock:BLOCKQUOTE']].forEach(([label,cmd])=>{
    wtb.appendChild(mkbtn(label,'', ()=>{
      if(cmd==='createLink'){ const url=prompt('URL'); if(url) document.execCommand('createLink', false, url); }
      else if(cmd.startsWith('formatBlock')) document.execCommand('formatBlock', false, cmd.split(':')[1]);
      else document.execCommand(cmd);
    }));
  });
  const canvas=document.createElement('div'); canvas.className='wysiwyg'; canvas.contentEditable='true';
  canvas.innerHTML = e.body||'';
  canvas.oninput=()=>{ e.body = canvas.innerHTML; };
  bodyWrap.append(wtb, canvas); $edit.appendChild(bodyWrap);

  const tagWrap=document.createElement('div'); tagWrap.className='field'; tagWrap.innerHTML='<label>Tags</label>';
  e.tag_ids = e.tag_ids || [];
  const tagChips=document.createElement('div'); tagChips.style.cssText='display:flex;flex-wrap:wrap;gap:.3rem;margin-bottom:.3rem';
  const tagSel=document.createElement('select');
  const drawTags=()=>{
    tagChips.innerHTML='';
    e.tag_ids.forEach(id=>{
      const t=allTags.find(x=>x.id===id); if(!t) return;
      tagChips.appendChild(mkbtn(t.name+' ×','', ()=>{ e.tag_ids=e.tag_ids.filter(x=>x!==id); drawTags(); }));
    });
    tagSel.innerHTML='<option value="">add tag…</option>'+allTags.filter(t=>!e.tag_ids.includes(t.id)).map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join('');
  };
  tagSel.onchange=()=>{ if(tagSel.value){ e.tag_ids.push(+tagSel.value); drawTags(); } };
  drawTags();
  tagWrap.append(tagChips, tagSel); $edit.appendChild(tagWrap);

  const panelsWrap=document.createElement('div'); panelsWrap.className='field'; panelsWrap.innerHTML='<label>Panels (comic / grid / slideshow)</label>';
  e.panels = e.panels || [];
  const panelRows=document.createElement('div');
  const drawPanels=()=>{
    panelRows.innerHTML='';
    e.panels.forEach((p,i)=>{
      const pr=document.createElement('div'); pr.className='panel';
      pr.appendChild(imagePicker(()=>p.image, v=>p.image=v, drawPanels));
      const cap=document.createElement('input'); cap.placeholder='Caption'; cap.value=p.caption||''; cap.oninput=()=>p.caption=cap.value; cap.style.marginBottom='.3rem';
      const txt=document.createElement('textarea'); txt.placeholder='Text'; txt.value=p.text||''; txt.oninput=()=>p.text=txt.value; txt.style.marginBottom='.3rem';
      const span=document.createElement('select'); span.innerHTML=['full','wide','half','third'].map(s=>`<option ${p.span===s?'selected':''}>${s}</option>`).join('');
      span.onchange=()=>p.span=span.value;
      const rm=mkbtn('Remove panel','', ()=>{ e.panels.splice(i,1); drawPanels(); });
      pr.append(cap, txt, span, rm);
      panelRows.appendChild(pr);
    });
  };
  drawPanels();
  const addPanel=mkbtn('+ Panel','', ()=>{ e.panels.push({image:'',caption:'',text:'',span:'half'}); drawPanels(); });
  panelsWrap.append(panelRows, addPanel); $edit.appendChild(panelsWrap);

  const tb=document.createElement('div'); tb.className='tb';
  const saveBtn = mkbtn('Save entry','primary', async ()=>{
    saveBtn.textContent='Saving...';
    try{ await j('/api/entries/'+e.id, {method:'PUT', body: JSON.stringify(e)}); await loadEntries(); drawList(); render(); saveBtn.textContent='Saved'; }
    catch(err){ saveBtn.textContent='Failed: '+err.message; }
    setTimeout(()=>saveBtn.textContent='Save entry',1400);
  });
  const delBtn = mkbtn('Delete entry','', async ()=>{
    if(!confirm(`Delete entry "${e.title}"?`)) return;
    await j('/api/entries/'+e.id, {method:'DELETE'});
    curEntry=null; await loadEntries(); render();
  });
  tb.append(saveBtn, delBtn);
  $edit.appendChild(tb);
}

boot();
</script>
</body></html>'''


if __name__ == '__main__':
    ensure_schema()
    port = CFG.get('port', 8789)
    print(f'Columnroom -> http://localhost:{port}')
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)
