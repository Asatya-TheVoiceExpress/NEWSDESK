#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import re
import sys

from flask import Flask, jsonify, request, render_template_string, send_from_directory, Response

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import dtp_engine as eng

app = Flask(__name__, static_folder=None)


@app.route('/api/projects', methods=['GET'])
def list_projects():
    db = eng.get_db()
    try:
        rows = db.execute('SELECT id, name, kind, source_ref, created_at, updated_at '
                          'FROM dtp_projects ORDER BY updated_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/projects', methods=['POST'])
def create_project():
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip() or 'Untitled project'
    kind = data.get('kind') if data.get('kind') in ('custom',) else 'custom'
    preset = data.get('preset', 'a4')
    pid = eng._create(name, kind, data.get('source_ref'), eng.blank_layout(preset))
    return jsonify({'id': pid})


@app.route('/api/projects/import-sla', methods=['POST'])
def import_sla():
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file uploaded'}), 400
    try:
        layout = eng.sla_to_layout(f.read())
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    name = re.sub(r'\.sla$', '', f.filename, flags=re.I).strip() or 'Imported from Scribus'
    pid = eng._create(name, 'custom', None, layout)
    return jsonify({'id': pid})


@app.route('/api/projects/<int:pid>', methods=['GET'])
def get_project_route(pid):
    proj = eng.get_project(pid)
    if not proj:
        return jsonify({'error': 'Project not found'}), 404
    return jsonify(proj)


@app.route('/api/projects/<int:pid>', methods=['PUT'])
def save_project(pid):
    data = request.get_json(force=True) or {}
    db = eng.get_db()
    try:
        row = db.execute('SELECT 1 FROM dtp_projects WHERE id=?', [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Project not found'}), 404
        fields, params = [], []
        if 'name' in data:
            fields.append('name=?'); params.append(data['name'])
        if 'layout' in data:
            import json
            fields.append('layout=?')
            params.append(json.dumps(eng._normalize_layout_for_storage(data['layout'])))
        fields.append('updated_at=?'); params.append(eng.now())
        params.append(pid)
        db.execute(f'UPDATE dtp_projects SET {", ".join(fields)} WHERE id=?', params)
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/projects/<int:pid>', methods=['DELETE'])
def delete_project(pid):
    db = eng.get_db()
    try:
        db.execute('DELETE FROM dtp_projects WHERE id=?', [pid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/months', methods=['GET'])
def list_months():
    db = eng.get_db()
    try:
        rows = db.execute('''SELECT strftime('%Y-%m', published_at) AS ym, COUNT(*) AS n
                             FROM articles WHERE status='published' AND published_at IS NOT NULL
                             GROUP BY ym ORDER BY ym DESC''').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/articles', methods=['GET'])
def search_articles():
    q = (request.args.get('q') or '').strip()
    db = eng.get_db()
    try:
        sql = 'SELECT id, title, status, updated_at, featured_image FROM articles'
        params = []
        if q:
            sql += ' WHERE title LIKE ?'; params.append(f'%{q}%')
        sql += ' ORDER BY updated_at DESC LIMIT 100'
        rows = [dict(r) for r in db.execute(sql, params).fetchall()]
        for r in rows:
            fi = r.get('featured_image')
            if fi and not fi.startswith('/') and not fi.startswith('http'):
                r['featured_image'] = f'/static/uploads/{fi}'
        return jsonify(rows)
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/components', methods=['GET'])
def article_components(aid):
    result = eng.get_article_components(aid)
    if not result:
        return jsonify({'error': 'Article not found'}), 404
    return jsonify(result)


@app.route('/api/articles/<int:aid>/components/<int:index>', methods=['GET'])
def article_component_block(aid, index):
    block = eng.get_article_semantic_block(aid, index)
    if block is None:
        return jsonify({'error': 'Block not found'}), 404
    return jsonify(block)


@app.route('/api/authors', methods=['GET'])
def list_authors():
    db = eng.get_db()
    try:
        rows = [dict(r) for r in db.execute(
            'SELECT id, name, role FROM authors ORDER BY name').fetchall()]
        return jsonify(rows)
    finally:
        db.close()


@app.route('/api/uploads', methods=['GET'])
def list_uploads():
    q = (request.args.get('q') or '').strip().lower()
    root = os.path.join(eng.STATIC_ROOT, 'uploads')
    exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    out = []
    try:
        for fn in sorted(os.listdir(root), key=lambda n: os.path.getmtime(os.path.join(root, n)), reverse=True):
            if not fn.lower().endswith(exts):
                continue
            if q and q not in fn.lower():
                continue
            out.append({'name': fn, 'url': f'/static/uploads/{fn}'})
            if len(out) >= 200:
                break
    except FileNotFoundError:
        pass
    return jsonify(out)


@app.route('/api/projects/generate_magazine', methods=['POST'])
def generate_magazine():
    data = request.get_json(force=True) or {}
    article_ids = data.get('article_ids') or data.get('article_id')
    if not article_ids:
        return jsonify({'error': 'article_ids (or article_id) required'}), 400
    if not isinstance(article_ids, list):
        article_ids = [article_ids]
    key = ','.join(str(x) for x in article_ids)
    existed = eng._find_existing('magazine', key)
    pid = eng.create_magazine_project(article_ids, title=data.get('title'),
                                       creator=data.get('creator', ''),
                                       description=data.get('description', ''),
                                       regenerate=bool(data.get('regenerate')))
    if pid is None:
        return jsonify({'error': 'Article(s) not found'}), 404
    return jsonify({'id': pid, 'reopened': bool(existed) and not data.get('regenerate')})


@app.route('/api/projects/generate_broadsheet', methods=['POST'])
def generate_broadsheet():
    data = request.get_json(force=True) or {}
    ym = data.get('ym', '')
    existed = eng._find_existing('broadsheet', ym)
    pid = eng.create_broadsheet_project(ym, regenerate=bool(data.get('regenerate')),
                                        enhancement=data.get('enhancement'))
    if pid is None:
        return jsonify({'error': 'Invalid month or no published articles'}), 404
    return jsonify({'id': pid, 'reopened': bool(existed) and not data.get('regenerate')})


@app.route('/api/projects/generate_special', methods=['POST'])
def generate_special():
    data = request.get_json(force=True) or {}
    key = (data.get('key') or '').strip()
    if not key:
        return jsonify({'error': 'key required'}), 400
    existed = eng._find_existing(eng.SPECIAL_BROADSHEET_KIND, key)
    try:
        pid = eng.create_special_broadsheet_project(
            key, data.get('label'),
            article_ids=data.get('article_ids'), entry_ids=data.get('entry_ids'),
            date_from=data.get('date_from'), date_to=data.get('date_to'),
            blank_pages=int(data.get('blank_pages') or 0),
            seed_month=data.get('seed_month'),
            regenerate=bool(data.get('regenerate')), enhancement=data.get('enhancement'))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    if pid is None:
        return jsonify({'error': 'Nothing to typeset -- pick articles/entries, a date '
                                 'range with content, or set blank pages'}), 404
    return jsonify({'id': pid, 'reopened': bool(existed) and not data.get('regenerate')})


@app.route('/api/projects/generate_gazette', methods=['POST'])
def generate_gazette():
    data = request.get_json(force=True) or {}
    article_id = data.get('article_id')
    if not article_id:
        return jsonify({'error': 'article_id required'}), 400
    existed = eng._find_existing('gazette', article_id)
    pid = eng.create_gazette_project(article_id, regenerate=bool(data.get('regenerate')),
                                     enhancement=data.get('enhancement'))
    if pid is None:
        return jsonify({'error': 'Article not found'}), 404
    return jsonify({'id': pid, 'reopened': bool(existed) and not data.get('regenerate')})


@app.route('/api/projects/<int:pid>/preview', methods=['GET'])
def preview_project(pid):
    proj = eng.get_project(pid)
    if not proj:
        return '<div>Project not found</div>', 404
    layout = proj['layout']
    master_param = request.args.get('master')
    if master_param is not None:
        editable = request.args.get('editable', '1') != '0'
        html = eng.master_to_html(layout, master_param, editable=editable)
        return f'<!doctype html><html><head><meta charset="utf-8"></head><body>{html}</body></html>'
    layout = eng.resolve_layout(layout)
    page_param = request.args.get('page')
    if page_param is not None:
        try:
            idx = int(page_param)
            pages = layout.get('pages') or []
            if 0 <= idx < len(pages):
                layout = dict(layout)
                layout['pages'] = [pages[idx]]
        except ValueError:
            pass
    editable = request.args.get('editable', '1') != '0'
    html = eng.layout_to_html(layout, editable=editable)
    return f'<!doctype html><html><head><meta charset="utf-8"></head><body>{html}</body></html>'


@app.route('/api/projects/<int:pid>/preview.pdf', methods=['GET'])
def preview_pdf(pid):
    proj = eng.get_project(pid)
    if not proj:
        return jsonify({'error': 'Project not found'}), 404
    pdf, err = eng.render_pdf(proj['layout'])
    if err:
        return jsonify({'error': err}), 500
    return Response(pdf, mimetype='application/pdf')


@app.route('/api/projects/<int:pid>/export.sla', methods=['GET'])
def export_sla(pid):
    proj = eng.get_project(pid)
    if not proj:
        return jsonify({'error': 'Project not found'}), 404
    sla = eng.layout_to_sla(proj['layout'], doc_name=proj.get('name') or 'Untitled')
    fname = re.sub(r'[^A-Za-z0-9_-]+', '_', proj.get('name') or 'untitled').strip('_') or 'untitled'
    return Response(sla, mimetype='application/x-scribus',
                     headers={'Content-Disposition': f'attachment; filename="{fname}.sla"'})


@app.route('/api/projects/<int:pid>/publish', methods=['POST'])
def publish_project(pid):
    data = request.get_json(silent=True) or {}
    result = eng.publish_project(pid, title=data.get('title'), output=data.get('output', 'pdf'),
                                 tags=data.get('tags'))
    if 'error' in result:
        return jsonify(result), 500 if 'not found' not in result['error'].lower() else 404
    result.pop('content', None)
    result.pop('mimetype', None)
    return jsonify(result)


@app.route('/api/publications', methods=['GET'])
def list_publications():
    q = (request.args.get('q') or '').strip().lower()
    items = eng.list_publications()
    if q:
        items = [p for p in items if q in (p['title'] or '').lower()
                 or q in (p['filename'] or '').lower()]
    return jsonify(items)


@app.route('/api/publications/import', methods=['POST'])
def import_publication_pdf():
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file uploaded'}), 400
    data = f.read()
    if len(data) > 60 * 1024 * 1024:
        return jsonify({'error': 'PDF too large (max 60 MB)'}), 400
    tags = [t.strip() for t in (request.form.get('tags') or '').split(',') if t.strip()]
    result = eng.import_pdf(data, f.filename,
                            title=request.form.get('title'),
                            tags=tags,
                            description=request.form.get('description') or '',
                            featured=(request.form.get('featured') or '').lower()
                                     in ('1', 'true', 'on', 'yes'))
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result), 201


@app.route('/api/publications/<int:pub_id>', methods=['PUT'])
def update_publication_flags(pub_id):
    data = request.get_json(silent=True) or {}
    result = eng.set_publication_flags(pub_id,
                                       featured=data.get('featured'),
                                       tags=data.get('tags'),
                                       title=data.get('title'))
    if 'error' in result:
        return jsonify(result), 404 if 'not found' in result['error'].lower() else 400
    return jsonify(result)


@app.route('/api/publications/<int:pub_id>/replace', methods=['POST'])
def replace_publication_pdf(pub_id):
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file uploaded'}), 400
    data = f.read()
    if len(data) > 60 * 1024 * 1024:
        return jsonify({'error': 'File too large (max 60 MB)'}), 400
    result = eng.replace_publication_file(pub_id, data, f.filename)
    if 'error' in result:
        return jsonify(result), 404 if 'not found' in result['error'].lower() else 400
    return jsonify(result)


@app.route('/api/publications/<int:pub_id>/open', methods=['POST'])
def open_publication(pub_id):
    data = request.get_json(silent=True) or {}
    result = eng.project_for_publication(pub_id, regenerate=bool(data.get('regenerate')))
    if 'error' in result:
        return jsonify(result), 404 if 'not found' in result['error'].lower() else 400
    return jsonify(result)


@app.route('/static/<path:p>')
def serve_static(p):
    return send_from_directory(eng.STATIC_ROOT, p)


@app.route('/fonts/<path:p>')
def serve_fonts(p):
    return send_from_directory(os.path.join(BASE, 'fonts'), p)


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


INDEX_HTML = r'''<!doctype html><html><head><meta charset="utf-8">
<title>DTP</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--line:#555;--dim:#999;--bg:#111;--fg:#eee;--panel:#1c1c1c;--accent:#7aa2ff}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{font:12px/1.4 Verdana,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--fg);display:flex;flex-direction:column;overflow:hidden}
h1{font-family:Georgia,serif;font-size:1rem;margin:0}
header{display:flex;align-items:center;gap:.2rem .4rem;padding:.2rem .6rem;border-bottom:1px solid var(--line);background:var(--panel);flex-wrap:wrap}
.ribbon-group{display:flex;flex-direction:row;align-items:center;gap:.35rem;padding:0 .5rem;border-right:1px solid #333}
.ribbon-group:last-of-type{border-right:none}
.ribbon-label{font-size:.6rem;color:var(--dim);text-transform:uppercase;letter-spacing:.04em}
.ribbon-row{display:flex;align-items:center;gap:.25rem;flex-wrap:wrap}
select,input{font:inherit}
button{border:1px solid var(--line);background:#1a1a1a;color:var(--fg);padding:.15rem .5rem;cursor:pointer;font:inherit;border-radius:0}
button:hover{background:#2a2a2a}
button.primary{background:#eee;color:#111;border-color:#eee}
button.primary:hover{background:#fff}
main{display:grid;grid-template-columns:220px 1fr 260px;flex:1;min-height:0}
.rail{background:#151515;overflow:auto;border-right:1px solid var(--line);padding:.5rem}
.palette{display:flex;align-items:center;gap:.3rem;padding:.2rem .6rem;border-bottom:1px solid var(--line);background:#151515;flex-wrap:wrap}
.stage{overflow:auto;background:#2a2a2a;display:flex;justify-content:center;align-items:flex-start;padding:1.5rem 1.5rem 1.5rem 42px;position:relative}
.stage-inner{position:relative}
.inspector{background:#151515;overflow:auto;border-left:1px solid var(--line);padding:.5rem;display:flex;flex-direction:column}
.mi{border:1px solid var(--line);padding:.3rem;margin-bottom:.4rem;cursor:pointer;background:#1a1a1a}
.mi:hover{background:var(--panel)}
.mi.is-active{outline:2px solid var(--accent)}
.mi-num{font-size:.7rem;color:var(--dim);margin-bottom:.25rem}
.mi-thumb{overflow:hidden;border:1px solid #444;background:#eee}
.mi-thumb iframe{border:none;pointer-events:none}
.hint{color:var(--dim);font-size:.78rem}
.field{margin-bottom:.6rem}
.field label{display:block;font-size:.72rem;color:var(--dim);margin-bottom:.15rem;text-transform:uppercase}
input,textarea,select{width:100%;padding:.25rem .35rem;border:1px solid var(--line);border-radius:0;background:#1a1a1a;color:var(--fg)}
input[type=color]{padding:.1rem;height:1.8rem}
iframe{border:none;background:#fff}
.ruler-h{position:absolute;left:42px;top:0;height:20px;background:#222;border-bottom:1px solid var(--line);overflow:hidden;cursor:ns-resize}
.ruler-v{position:absolute;left:22px;top:1.5rem;width:20px;background:#222;border-right:1px solid var(--line);overflow:hidden;cursor:ew-resize}
.tick{position:absolute;font-size:8px;color:#999;border-left:1px solid #666;padding-left:2px;height:100%;top:0}
.ruler-v .tick{border-left:none;border-top:1px solid #666;padding-left:1px;left:0;width:100%;height:auto}
.panel-title{font-size:.72rem;color:var(--dim);text-transform:uppercase;margin-bottom:.3rem;font-weight:bold}
.layers-panel{border-bottom:1px solid var(--line);padding-bottom:.5rem;margin-bottom:.6rem;max-height:34vh;overflow:auto}
.layer-row{display:flex;justify-content:space-between;align-items:center;padding:.25rem .3rem;cursor:pointer;border:1px solid transparent}
.layer-row:hover{background:var(--panel)}
.layer-row.is-sel{border-color:var(--accent);background:#1e2a44}
.layer-label{font-size:.75rem}
.layer-btns button{border:none;background:none;cursor:pointer;padding:0 .15rem;font-size:.8rem}
#inspectorBody{flex:1;overflow:auto}
.modal-back{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:1000}
.modal{background:#161616;border:1px solid var(--line);width:min(560px,92vw);max-height:80vh;display:flex;flex-direction:column}
.modal-head{display:flex;justify-content:space-between;align-items:center;padding:.5rem .7rem;border-bottom:1px solid var(--line);background:var(--panel)}
.modal-head button{border:none;background:none;font-size:1.1rem;cursor:pointer;padding:0 .3rem}
.modal-body{padding:.6rem .7rem;overflow:auto}
.pk-item{display:flex;gap:.5rem;align-items:center;padding:.35rem;cursor:pointer;border-bottom:1px solid #333}
.pk-item:hover{background:var(--panel)}
.pk-item img{width:36px;height:36px;object-fit:cover;background:#333}
.pk-title{font-weight:bold}
.pk-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:.4rem;max-height:55vh;overflow:auto}
.pk-img{cursor:pointer;border:1px solid var(--line);aspect-ratio:1;overflow:hidden}
.pk-img img{width:100%;height:100%;object-fit:cover;display:block}
.pk-img:hover{outline:2px solid var(--accent)}
.comp-panel{margin-top:.6rem;border-top:1px solid var(--line);padding-top:.5rem}
.comp-chip{border:1px solid var(--line);padding:.35rem;margin-bottom:.3rem;cursor:grab;background:#1a1a1a;font-size:.72rem}
.comp-chip:hover{background:var(--panel)}
.comp-chip b{display:block;text-transform:capitalize}
.comp-chip .hint{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pk-item.is-disabled{opacity:.45;cursor:default}
.doclayer-row{display:flex;align-items:center;gap:.3rem;padding:.25rem;border:1px solid var(--line);margin-bottom:.25rem;background:#1a1a1a}
.doclayer-row.is-active{background:var(--panel);font-weight:bold}
.doclayer-row input[type=text]{border:none;background:transparent;padding:0;flex:1;min-width:0}
.doclayer-row button{border:none;background:none;cursor:pointer;padding:0 .15rem;font-size:.85rem}
</style>
<script src="https://unpkg.com/konva@9/konva.min.js"></script>
</head>
<body>
<header>
  <div class="ribbon-group" style="border-right:none">
    <h1>DTP</h1>
    <select id="projSel"></select>
  </div>
  <div class="ribbon-group">
    <label class="ribbon-label">File</label>
    <div class="ribbon-row">
      <button id="newBtn">New</button>
      <button id="libraryBtn" title="Open any publication on the Newsstand for editing">Library…</button>
      <button id="saveBtn">Save</button>
      <button class="primary" id="exportBtn">Preview PDF</button>
      <button class="primary" id="publishBtn">Publish</button>
      <button id="exportSlaBtn" title="One-way export for manual polish in real Scribus">Export to Scribus…</button>
      <button id="importSlaBtn" title="Upload a real Scribus .sla file as a new project">Import from Scribus…</button>
      <input type="file" id="importSlaFile" accept=".sla" style="display:none">
      <button id="importPdfBtn" title="Shelve a finished PDF on the Newsstand with tags — no layout, edited by replacing the file">Import PDF…</button>
      <input type="file" id="importPdfFile" accept=".pdf" style="display:none">
      <input type="file" id="replacePubFile" style="display:none">
    </div>
  </div>
  <div class="ribbon-group">
    <label class="ribbon-label">Generate</label>
    <div class="ribbon-row">
      <button id="genMagBtn">Magazine…</button>
      <button id="genBsBtn">Broadsheet…</button>
      <button id="genSpBtn">Special…</button>
      <button id="genGzBtn">Gazette…</button>
    </div>
  </div>
  <div class="ribbon-group">
    <label class="ribbon-label">Edit</label>
    <div class="ribbon-row">
      <button id="undoBtn" title="Ctrl+Z">Undo</button>
      <button id="redoBtn" title="Ctrl+Y">Redo</button>
    </div>
  </div>
  <div class="ribbon-group">
    <label class="ribbon-label">View</label>
    <div class="ribbon-row">
      <label style="display:flex;align-items:center;gap:.3rem">Grid(mm)<input id="gridMm" type="number" value="0" style="width:3.5rem"></label>
      <button id="zoomOutBtn" type="button" style="padding:.05rem .45rem">−</button>
      <span id="zoomPct" class="hint" style="width:3.2rem;text-align:center">72%</span>
      <button id="zoomInBtn" type="button" style="padding:.05rem .45rem">+</button>
      <button id="spreadBtn" type="button" title="Show facing pages side by side">Spread: Off</button>
    </div>
  </div>
  <span style="flex:1"></span>
  <span class="hint" id="status" style="align-self:center"></span>
</header>
<div class="palette" id="palette">
  <span class="ribbon-label" style="margin-right:.2rem">Insert:</span>
  <button data-t="text">Text</button>
  <button data-t="image">Image</button>
  <button data-t="headline">Headline</button>
  <button data-t="pullquote">Pull quote</button>
  <button data-t="logo">Logo</button>
  <button data-t="qr">QR code</button>
  <button data-t="generative_art">Generative art</button>
  <button data-t="copyright">Copyright</button>
  <button data-t="author_bio">Author bio</button>
  <button data-t="vector_shape">Shape</button>
  <button id="drawShapeBtn" type="button" title="Click to place polygon/polyline points on the canvas">Draw shape…</button>
</div>
<main>
  <div class="rail">
    <div id="masterBanner" style="display:none;background:#eee;color:#111;padding:.4rem;margin-bottom:.5rem;font-size:.72rem"></div>
    <div id="pages"></div>
    <div class="comp-panel" id="mastersPanel">
      <div class="panel-title">Masters</div>
      <div id="masterAssign" class="field"></div>
      <div id="mastersList"></div>
      <button id="addMasterBtn" style="width:100%;margin-top:.3rem">+ Master</button>
    </div>
    <div class="comp-panel" id="docLayersPanel">
      <div class="panel-title">Layers</div>
      <div id="unifiedLayersList"></div>
      <button id="addLayerBtn" style="width:100%;margin-top:.3rem">+ Layer</button>
    </div>
    <div class="comp-panel">
      <div class="panel-title">Article Components</div>
      <button id="browseArticleBtn" style="width:100%;margin-bottom:.4rem">Browse article…</button>
      <div id="compList"></div>
    </div>
    <div class="comp-panel">
      <div class="panel-title">Images</div>
      <input id="imgPanelQ" placeholder="Search uploads..." style="width:100%;margin-bottom:.4rem">
      <div id="imgPanelGrid" class="pk-grid"></div>
    </div>
  </div>
  <div class="stage" id="stage">
    <div class="ruler-h" id="rulerH"></div>
    <div class="ruler-v" id="rulerV"></div>
    <div class="stage-inner"><iframe id="frame" width="900" height="1200"></iframe><div id="konvaOverlay" style="position:absolute;left:0;top:0"></div></div>
  </div>
  <div class="inspector">
    <div id="inspectorBody"><div class="hint">Select a block.</div></div>
  </div>
</main>
<script>
const $projSel=document.getElementById('projSel'), $pages=document.getElementById('pages'),
      $frame=document.getElementById('frame'), $inspectorBody=document.getElementById('inspectorBody'),
      $status=document.getElementById('status');
const j=(u,o)=>fetch(u,Object.assign({headers:{'Content-Type':'application/json'}},o)).then(r=>r.json().then(d=>{if(!r.ok)throw new Error(d.error||r.statusText);return d;}));
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

let projects=[], project=null, curPage=0, selectedIds=new Set();
let stageScale=0.72;
let spreadView=false;
function spreadPageIndices(i, total){
  if(i<=0) return [0];
  const left = (i%2===1) ? i : i-1;
  const right = left+1;
  return right<total ? [left,right] : [left];
}

function openModal(title, bodyHtml, onMount){
  closeModal();
  const back=document.createElement('div'); back.className='modal-back'; back.id='modalBack';
  back.innerHTML=`<div class="modal"><div class="modal-head"><b>${esc(title)}</b><button id="modalX">×</button></div><div class="modal-body">${bodyHtml}</div></div>`;
  document.body.appendChild(back);
  back.querySelector('#modalX').onclick=closeModal;
  back.onclick=e=>{ if(e.target===back) closeModal(); };
  onMount && onMount(back.querySelector('.modal-body'));
}
function closeModal(){ const b=document.getElementById('modalBack'); if(b) b.remove(); }

function askForm(title, fields, okLabel){
  return new Promise(resolve=>{
    const back=document.createElement('div'); back.className='modal-back'; back.style.zIndex=1100;
    back.innerHTML=`<form class="modal"><div class="modal-head"><b>${esc(title)}</b><button type="button" data-x>×</button></div>
      <div class="modal-body">${fields.map(f=> f.type==='checkbox'
        ? `<label style="display:flex;gap:.4rem;align-items:center;margin:.4rem 0"><input type="checkbox" name="${f.name}" ${f.value?'checked':''}> ${esc(f.label)}</label>`
        : `<label class="hint" style="display:block;margin:.4rem 0 .15rem">${esc(f.label)}</label>
           <input name="${f.name}" value="${esc(f.value||'')}" placeholder="${esc(f.placeholder||'')}" style="width:100%">`).join('')}
        <div style="display:flex;justify-content:flex-end;gap:.4rem;margin-top:.7rem">
          <button type="button" data-x>Cancel</button><button type="submit">${esc(okLabel||'OK')}</button></div></div></form>`;
    document.body.appendChild(back);
    const form=back.querySelector('form');
    const done=v=>{ back.remove(); resolve(v); };
    back.querySelectorAll('[data-x]').forEach(b=>b.onclick=()=>done(null));
    back.onclick=e=>{ if(e.target===back) done(null); };
    back.onkeydown=e=>{ if(e.key==='Escape') done(null); };
    form.onsubmit=e=>{ e.preventDefault();
      const out={}; fields.forEach(f=>{ const el=form.elements[f.name]; out[f.name]=f.type==='checkbox'?el.checked:el.value; }); done(out); };
    const first=form.querySelector('input:not([type=checkbox])'); if(first){ first.focus(); first.select(); }
  });
}

function pickArticle(cb){
  openModal('Pick an article', `<input id="pkQ" placeholder="Search articles..." style="width:100%;margin-bottom:.5rem">
    <div id="pkList"></div>`, root=>{
    const list=root.querySelector('#pkList'), q=root.querySelector('#pkQ');
    async function refresh(){
      const items = await j('/api/articles?q='+encodeURIComponent(q.value||''));
      list.innerHTML = items.map(a=>`<div class="pk-item" data-id="${a.id}">
        <img src="${a.featured_image?esc(a.featured_image):''}" onerror="this.style.visibility='hidden'">
        <div><div class="pk-title">${esc(a.title)}</div><div class="hint">${esc(a.status)} · updated ${esc((a.updated_at||'').slice(0,10))}</div></div></div>`).join('')
        || '<div class="hint">No matches.</div>';
      list.querySelectorAll('.pk-item').forEach(el=>{ el.onclick=()=>{ closeModal(); cb(Number(el.dataset.id)); }; });
    }
    q.oninput=refresh; q.focus(); refresh();
  });
}
function pickArticlesMulti(cb){
  openModal('Pick articles for this issue', `<input id="pkQ" placeholder="Search articles..." style="width:100%;margin-bottom:.5rem">
    <div id="pkList"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.5rem">
      <span class="hint" id="pkCount">0 selected</span>
      <button id="pkGo" disabled>Generate magazine</button>
    </div>`, root=>{
    const list=root.querySelector('#pkList'), q=root.querySelector('#pkQ');
    const goBtn=root.querySelector('#pkGo'), countEl=root.querySelector('#pkCount');
    const selected = new Set();
    function updateGo(){ countEl.textContent = selected.size+' selected'; goBtn.disabled = selected.size===0; }
    async function refresh(){
      const items = await j('/api/articles?q='+encodeURIComponent(q.value||''));
      list.innerHTML = items.map(a=>`<div class="pk-item" data-id="${a.id}">
        <input type="checkbox" class="pk-check" ${selected.has(a.id)?'checked':''}>
        <img src="${a.featured_image?esc(a.featured_image):''}" onerror="this.style.visibility='hidden'">
        <div><div class="pk-title">${esc(a.title)}</div><div class="hint">${esc(a.status)} · updated ${esc((a.updated_at||'').slice(0,10))}</div></div></div>`).join('')
        || '<div class="hint">No matches.</div>';
      list.querySelectorAll('.pk-item').forEach(el=>{
        const id=Number(el.dataset.id);
        el.onclick=()=>{
          if(selected.has(id)) selected.delete(id); else selected.add(id);
          el.querySelector('.pk-check').checked = selected.has(id);
          updateGo();
        };
      });
    }
    q.oninput=refresh; q.focus(); refresh();
    goBtn.onclick=()=>{ if(!selected.size) return; closeModal(); cb([...selected]); };
  });
}
async function pickMonth(cb){
  const months = await j('/api/months');
  openModal('Pick a month', `<div id="pkList"></div>`, root=>{
    const list=root.querySelector('#pkList');
    list.innerHTML = months.map(m=>`<div class="pk-item" data-ym="${m.ym}"><div><div class="pk-title">${esc(m.ym)}</div><div class="hint">${m.n} article(s)</div></div></div>`).join('')
      || '<div class="hint">No published months.</div>';
    list.querySelectorAll('.pk-item').forEach(el=>{ el.onclick=()=>{ closeModal(); cb(el.dataset.ym); }; });
  });
}
function pickPublication(cb){
  openModal('The Newsstand shelf', `<input id="pkQ" placeholder="Search the Newsstand..." style="width:100%;margin-bottom:.5rem">
    <div class="hint" style="margin-bottom:.5rem">★ marks a publication as featured — promoted on the shelf, and never pruned. Reader-built ebooks are deleted 30 days after they are made unless they are featured.</div>
    <div id="pkList"></div>`, root=>{
    const list=root.querySelector('#pkList'), q=root.querySelector('#pkQ');
    async function refresh(){
      const items = await j('/api/publications?q='+encodeURIComponent(q.value||''));
      list.innerHTML = items.map(p=>{
        const note = p.frozen ? 'imported PDF — replace the file to edit'
                   : p.dtp_project_id ? 'edited in dtp'
                   : (p.editable ? 'not yet edited here — opens from source' : 'no editable source');
        const tags = (p.tags||[]).join(', ');
        return `<div class="pk-item" data-id="${p.id}" data-ok="${p.editable?1:0}" style="align-items:center">
          <div style="flex:1;min-width:0">
            <div class="pk-title" data-act="open" style="${p.editable?'cursor:pointer':'opacity:.7'}">${p.featured?'★ ':''}${esc(p.title||p.filename)}</div>
            <div class="hint">${esc(p.pub_type||'')} · ${esc(p.filename||'')} · ${note}${tags?' · '+esc(tags):''}</div>
          </div>
          <button data-act="star" title="Featured — keep permanently">${p.featured?'★':'☆'}</button>
          <button data-act="tags" title="Edit tags">Tags</button>
          <button data-act="replace" title="Swap the file, keeping this shelf entry">Replace</button>
        </div>`;
      }).join('') || '<div class="hint">Nothing on the Newsstand yet.</div>';

      list.querySelectorAll('.pk-item').forEach(el=>{
        const id = Number(el.dataset.id);
        const item = items.find(p=>p.id===id);
        el.onclick = async (ev)=>{
          const act = (ev.target.dataset||{}).act;
          if(act==='star'){
            ev.stopPropagation();
            await j(`/api/publications/${id}`,{method:'PUT',
              body:JSON.stringify({featured:!item.featured})});
            refresh(); return;
          }
          if(act==='tags'){
            ev.stopPropagation();
            const a = await askForm('Tags for “'+(item.title||'publication')+'”',
              [{name:'tags',label:'Comma separated',value:(item.tags||[]).join(', ')}], 'Save tags');
            if(!a) return;
            await j(`/api/publications/${id}`,{method:'PUT',
              body:JSON.stringify({tags:a.tags.split(',').map(s=>s.trim()).filter(Boolean)})});
            refresh(); return;
          }
          if(act==='replace'){
            ev.stopPropagation();
            const inp = document.getElementById('replacePubFile');
            inp.accept = '.' + String(item.filename||'').split('.').pop();
            inp.onchange = async ()=>{
              const f = inp.files[0]; inp.value='';
              if(!f) return;
              try{
                const fd = new FormData(); fd.append('file', f);
                await fetch(`/api/publications/${id}/replace`,{method:'POST',body:fd})
                  .then(r=>r.json().then(d=>{if(!r.ok) throw new Error(d.error||r.statusText); return d;}));
                $status.textContent = 'Replaced the file behind publication #'+id+'.';
                refresh();
              }catch(err){ $status.textContent='Replace failed: '+err.message; }
            };
            inp.click(); return;
          }
          if(el.dataset.ok!=='1') return;
          closeModal(); cb(id);
        };
      });
    }
    q.oninput=refresh; refresh();
  });
}
function pickImage(cb){
  openModal('Pick an image', `<input id="pkQ" placeholder="Search uploads..." style="width:100%;margin-bottom:.5rem">
    <div id="pkGrid" class="pk-grid"></div>`, root=>{
    const grid=root.querySelector('#pkGrid'), q=root.querySelector('#pkQ');
    async function refresh(){
      const items = await j('/api/uploads?q='+encodeURIComponent(q.value||''));
      grid.innerHTML = items.map(im=>`<div class="pk-img" data-url="${esc(im.url)}"><img src="${esc(im.url)}" loading="lazy"></div>`).join('')
        || '<div class="hint">No images in static/uploads.</div>';
      grid.querySelectorAll('.pk-img').forEach(el=>{ el.onclick=()=>{ closeModal(); cb(el.dataset.url); }; });
    }
    q.oninput=refresh; refresh();
  });
}

async function boot(){
  projects = await j('/api/projects');
  refreshSel();
  if(projects.length) await openProject(projects[0].id);
  $projSel.onchange = ()=>openProject(Number($projSel.value));
  document.getElementById('newBtn').onclick = async ()=>{
    const a = await askForm('New project',[{name:'name',label:'Project name',value:'Untitled'}],'Create');
    const name = a && a.name.trim(); if(!name) return;
    const r = await j('/api/projects',{method:'POST',body:JSON.stringify({name,kind:'custom',preset:'a4'})});
    projects = await j('/api/projects'); refreshSel(); await openProject(r.id);
  };
  document.getElementById('libraryBtn').onclick = ()=> pickPublication(async pubId=>{
    $status.textContent='Opening...';
    try{
      const r = await j(`/api/publications/${pubId}/open`,{method:'POST',body:JSON.stringify({})});
      projects = await j('/api/projects'); refreshSel(); await openProject(r.project_id);
      $status.textContent = r.via==='rebuilt' ? 'Rebuilt from source' : '';
    }catch(e){ $status.textContent='Failed: '+e.message; }
  });
  document.getElementById('genMagBtn').onclick = ()=> pickArticlesMulti(async ids=>{
    $status.textContent='Generating...';
    try{ const r = await j('/api/projects/generate_magazine',{method:'POST',body:JSON.stringify({article_ids:ids})});
      projects = await j('/api/projects'); refreshSel(); await openProject(r.id); $status.textContent=''; }
    catch(e){ $status.textContent='Failed: '+e.message; }
  });
  document.getElementById('genBsBtn').onclick = ()=> pickMonth(async ym=>{
    $status.textContent='Generating...';
    try{ const r = await j('/api/projects/generate_broadsheet',{method:'POST',body:JSON.stringify({ym})});
      projects = await j('/api/projects'); refreshSel(); await openProject(r.id); $status.textContent=''; }
    catch(e){ $status.textContent='Failed: '+e.message; }
  });
  function openSpecialDialog(st){
    st = st || {};
    const today = new Date().toISOString().slice(0,10);
    let picked = st.picked || [];
    openModal('New special broadsheet', `
      <label class="hint">Edition label (prints on the masthead)</label>
      <input id="spLabel" placeholder="Special Issue — Floods" value="${esc(st.label||'')}" style="width:100%;margin-bottom:.5rem">
      <label class="hint">Key (slug — identifies this issue, reused to regenerate it)</label>
      <input id="spKey" placeholder="floods-2026" value="${esc(st.key||'')}" style="width:100%;margin-bottom:.6rem">
      <div style="margin-bottom:.5rem;display:flex;gap:1.2rem">
        <!-- radios opt out of the global input{width:100%} rule explicitly here -->
        <label style="display:inline-flex;align-items:center;gap:.35rem;width:auto">
          <input type="radio" name="spMode" value="content" style="width:auto;margin:0" ${st.mode==='blank'?'':'checked'}> Build from content</label>
        <label style="display:inline-flex;align-items:center;gap:.35rem;width:auto">
          <input type="radio" name="spMode" value="blank" style="width:auto;margin:0" ${st.mode==='blank'?'checked':''}> Free issue (empty frames)</label>
      </div>
      <div id="spContent" style="border:1px solid #444;padding:.5rem;margin-bottom:.5rem">
        <label class="hint">Published between (inclusive)</label>
        <div style="display:flex;gap:.4rem;margin-bottom:.5rem">
          <input id="spFrom" type="date" value="${esc(st.from||today)}" style="flex:1 1 0;min-width:0">
          <input id="spTo" type="date" value="${esc(st.to||today)}" style="flex:1 1 0;min-width:0">
        </div>
        <div class="hint" id="spPickInfo"></div>
        <div style="display:flex;gap:.4rem;align-items:center;margin-top:.35rem">
          <button id="spPick" style="flex:0 0 auto">Pick articles…</button>
          <button id="spClear" style="flex:0 0 auto">Clear</button>
        </div>
      </div>
      <div id="spBlank" style="border:1px solid #444;padding:.5rem;margin-bottom:.5rem;display:none">
        <label class="hint">Pages of empty, threaded column frames</label>
        <input id="spPages" type="number" min="1" max="24" value="${st.pages||4}" style="width:6rem">
        <div class="hint" style="margin-top:.35rem">Frames are chained in reading order, so text
          poured into the first flows through the whole issue.</div>
      </div>
      <button id="spGo" style="width:100%">Create</button>`, root=>{
      const $=s=>root.querySelector(s);
      const snapshot=()=>({label:$('#spLabel').value, key:$('#spKey').value,
                           mode:root.querySelector('input[name=spMode]:checked').value,
                           from:$('#spFrom').value, to:$('#spTo').value,
                           pages:$('#spPages').value, picked});
      const showPick=()=>{ $('#spPickInfo').textContent = picked.length
        ? `${picked.length} article(s) picked — the date window is ignored.`
        : 'Whole window. Or pick exact articles:'; };
      const sync=()=>{
        const blank = root.querySelector('input[name=spMode]:checked').value==='blank';
        $('#spBlank').style.display = blank?'block':'none';
        $('#spContent').style.display = blank?'none':'block';
      };
      root.querySelectorAll('input[name=spMode]').forEach(r=>r.onchange=sync);
      $('#spPick').onclick = ()=>{
        const st2 = snapshot();
        pickArticlesMulti(ids=>{ st2.picked = ids; openSpecialDialog(st2); });
      };
      $('#spClear').onclick = ()=>{ picked=[]; showPick(); };
      $('#spGo').onclick = async ()=>{
        const label = $('#spLabel').value.trim();
        const key = ($('#spKey').value.trim() || label).toLowerCase()
                      .replace(/[^a-z0-9._-]+/g,'-').replace(/^-|-$/g,'');
        if(!key){ $('#spGo').textContent='Needs a label or key'; return; }
        const blank = root.querySelector('input[name=spMode]:checked').value==='blank';
        const body = {key, label: label||key, regenerate:true};
        if(blank){ body.blank_pages = parseInt($('#spPages').value,10)||4; }
        else if(picked.length){ body.article_ids = picked; }
        else { body.date_from = $('#spFrom').value; body.date_to = $('#spTo').value; }
        closeModal(); $status.textContent='Generating special…';
        try{ const r = await j('/api/projects/generate_special',{method:'POST',body:JSON.stringify(body)});
          projects = await j('/api/projects'); refreshSel(); await openProject(r.id); $status.textContent=''; }
        catch(e){ $status.textContent='Failed: '+e.message; }
      };
      sync(); showPick();
    });
  }
  document.getElementById('genSpBtn').onclick = ()=> openSpecialDialog();
  document.getElementById('genGzBtn').onclick = ()=> pickArticle(async id=>{
    $status.textContent='Generating...';
    try{ const r = await j('/api/projects/generate_gazette',{method:'POST',body:JSON.stringify({article_id:id})});
      projects = await j('/api/projects'); refreshSel(); await openProject(r.id); $status.textContent=''; }
    catch(e){ $status.textContent='Failed: '+e.message; }
  });
  document.getElementById('undoBtn').onclick = doUndo;
  document.getElementById('redoBtn').onclick = doRedo;
  document.getElementById('zoomInBtn').onclick = ()=> setZoom(stageScale + 0.1);
  document.getElementById('zoomOutBtn').onclick = ()=> setZoom(stageScale - 0.1);
  document.getElementById('spreadBtn').onclick = ()=>{
    spreadView = !spreadView;
    document.getElementById('spreadBtn').textContent = spreadView ? 'Spread: On' : 'Spread: Off';
    loadFrame();
  };
  document.getElementById('saveBtn').onclick = saveProject;
  document.getElementById('exportBtn').onclick = ()=>{
    if(!project) return;
    window.open(`/api/projects/${project.id}/preview.pdf`,'_blank');
  };
  document.getElementById('publishBtn').onclick = async ()=>{
    if(!project) return;
    const a = await askForm('Publish to the Newsstand',[
      {name:'title',label:'Title',value:project.name},
      {name:'tags',label:'Tags (comma separated, optional)',value:''}],'Publish');
    const title = a && a.title.trim(); if(!title) return;
    const tags = a.tags.split(',').map(s=>s.trim()).filter(Boolean);
    $status.textContent='Publishing...';
    try{
      const r = await j(`/api/projects/${project.id}/publish`,{method:'POST',
        body:JSON.stringify(tags&&tags.length?{title,tags}:{title})});
      $status.textContent='Published to Newsstand (publication #'+r.publication_id+'). Run ve-push.py/librarize.py to ship it live.';
    } catch(e){ $status.textContent='Failed: '+e.message; }
  };
  document.getElementById('exportSlaBtn').onclick = ()=>{
    if(!project) return;
    const a=document.createElement('a'); a.href=`/api/projects/${project.id}/export.sla`; a.download='';
    document.body.appendChild(a); a.click(); a.remove();
  };
  document.getElementById('importSlaBtn').onclick = ()=> document.getElementById('importSlaFile').click();
  document.getElementById('importSlaFile').onchange = async (e)=>{
    const file = e.target.files[0]; e.target.value='';
    if(!file) return;
    $status.textContent = 'Importing...';
    try{
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch('/api/projects/import-sla', {method:'POST', body:fd}).then(r=>r.json().then(d=>{if(!r.ok) throw new Error(d.error||r.statusText); return d;}));
      projects = await j('/api/projects'); refreshSel(); await openProject(r.id);
      $status.textContent = 'Imported from Scribus.';
    } catch(err){ $status.textContent = 'Import failed: '+err.message; }
  };
  document.getElementById('importPdfBtn').onclick = ()=> document.getElementById('importPdfFile').click();
  document.getElementById('importPdfFile').onchange = async (e)=>{
    const file = e.target.files[0]; e.target.value='';
    if(!file) return;
    const a = await askForm('Import PDF to the Newsstand',[
      {name:'title',label:'Title on the Newsstand',value:file.name.replace(/\.pdf$/i,'')},
      {name:'tags',label:'Tags (comma separated, optional)',value:''},
      {name:'featured',type:'checkbox',label:'Featured (promoted on the shelf, never pruned)'}],'Import');
    if(!a) return;
    const {title, tags, featured} = a;
    $status.textContent = 'Importing PDF...';
    try{
      const fd = new FormData();
      fd.append('file', file); fd.append('title', title); fd.append('tags', tags);
      if(featured) fd.append('featured','1');
      const r = await fetch('/api/publications/import', {method:'POST', body:fd})
        .then(r=>r.json().then(d=>{if(!r.ok) throw new Error(d.error||r.statusText); return d;}));
      $status.textContent = `Shelved as publication #${r.publication_id}. Run librarize.py to ship it live.`;
    } catch(err){ $status.textContent = 'Import failed: '+err.message; }
  };
  document.querySelectorAll('#palette button[data-t]').forEach(b=>{ b.onclick=()=>addBlock(b.dataset.t); });
  document.getElementById('drawShapeBtn').onclick = ()=> startShapeDrawing(null);
  document.getElementById('browseArticleBtn').onclick = ()=> pickArticle(async id=>{
    compArticleId = id;
    const data = await j(`/api/articles/${id}/components`);
    drawComponents(data);
  });
  document.getElementById('imgPanelQ').oninput = e=> drawImagesPanel(e.target.value);
  drawImagesPanel('');
  document.getElementById('addLayerBtn').onclick = ()=>{
    const layers = docLayers();
    let n=1; while(layers.some(l=>l.name==='Layer '+n)) n++;
    layers.push({name:'Layer '+n, visible:true, locked:false});
    drawDocLayers(); loadFrame();
  };
  document.getElementById('addMasterBtn').onclick = ()=>{
    if(!project.layout.masters) project.layout.masters={};
    let n=1; while(project.layout.masters['Master '+n]) n++;
    const name='Master '+n;
    project.layout.masters[name]={blocks:[]};
    drawMasters();
    enterMasterEdit(name);
  };
}

let compArticleId = null;
function docLayers(){
  if(!project) return [{name:'Default',visible:true,locked:false}];
  if(!project.layout.doc_layers) project.layout.doc_layers=[{name:'Default',visible:true,locked:false}];
  return project.layout.doc_layers;
}
function isEffectivelyLocked(b){
  if(b.locked) return true;
  const l = docLayers().find(x=>x.name===(b.layer||'Default'));
  return !!(l && l.locked);
}
function drawUnifiedLayers(){
  const list = document.getElementById('unifiedLayersList'); if(!list) return;
  list.innerHTML = '';
  if(!project) return;
  const blocks = (curPageObj()||{}).blocks||[];
  docLayers().forEach(l=>{
    const head=document.createElement('div'); head.className='doclayer-row';
    const visChk=document.createElement('input'); visChk.type='checkbox'; visChk.checked=l.visible!==false; visChk.title='Visible';
    visChk.onchange=()=>{ l.visible=visChk.checked; loadFrame(); };
    const nameInp=document.createElement('input'); nameInp.type='text'; nameInp.value=l.name;
    nameInp.onblur=()=>{
      const newName=(nameInp.value||'').trim()||l.name;
      if(newName!==l.name){
        (project.layout.pages||[]).forEach(pg=>(pg.blocks||[]).forEach(b=>{ if((b.layer||'Default')===l.name) b.layer=newName; }));
        l.name=newName; drawInspector();
      }
      loadFrame();
    };
    const lockBtn=document.createElement('button'); lockBtn.textContent = l.locked?'🔒':'🔓'; lockBtn.title='Lock layer';
    lockBtn.onclick=()=>{ l.locked=!l.locked; drawUnifiedLayers(); loadFrame(); };
    const delBtn=document.createElement('button'); delBtn.textContent='✕'; delBtn.title='Delete layer';
    delBtn.style.display = docLayers().length>1 ? '' : 'none';
    delBtn.onclick=()=>{
      if(docLayers().length<=1) return;
      const layers=docLayers(); const idx=layers.indexOf(l); layers.splice(idx,1);
      const fallback = layers[0].name;
      (project.layout.pages||[]).forEach(pg=>(pg.blocks||[]).forEach(b=>{ if((b.layer||'Default')===l.name) b.layer=fallback; }));
      drawUnifiedLayers(); drawInspector(); loadFrame();
    };
    head.appendChild(visChk); head.appendChild(nameInp); head.appendChild(lockBtn); head.appendChild(delBtn);
    list.appendChild(head);

    const layerBlocks = [...blocks].filter(b=>(b.layer||'Default')===l.name).reverse();
    layerBlocks.forEach(b=>{
      const row=document.createElement('div'); row.className='layer-row'+(selectedIds.has(b.id)?' is-sel':'');
      row.style.marginLeft='1rem';
      const lockChar = b.locked ? '🔒' : '🔓';
      row.innerHTML = `<span class="layer-label">${b.group_id?'⛓ ':''}${esc(b.type)}</span>
        <span class="layer-btns">
          <button data-a="lock" title="${b.locked?'Unlock':'Lock'}">${lockChar}</button>
          <button data-a="front" title="Bring to front">⤒</button>
          <button data-a="forward" title="Bring forward">↑</button>
          <button data-a="backward" title="Send backward">↓</button>
          <button data-a="back" title="Send to back">⤓</button>
        </span>`;
      row.addEventListener('click', e=>{
        if(e.target.closest('button')) return;
        selectedIds = selectGroup(b.id); drawUnifiedLayers(); drawInspector(); loadFrame();
      });
      row.querySelector('button[data-a="lock"]').onclick=(e)=>{ e.stopPropagation(); b.locked=!b.locked; drawUnifiedLayers(); drawInspector(); };
      row.querySelectorAll('button[data-a]:not([data-a="lock"])').forEach(btn=>{
        btn.onclick=(e)=>{ e.stopPropagation(); reorderBlock(b.id, btn.dataset.a); };
      });
      list.appendChild(row);
    });
    if(!layerBlocks.length){
      const empty=document.createElement('div'); empty.className='hint'; empty.style.cssText='margin-left:1rem;margin-bottom:.3rem';
      empty.textContent='No blocks on this page in this layer.';
      list.appendChild(empty);
    }
  });
}
function drawDocLayers(){ drawUnifiedLayers(); }

function drawComponents(data){
  const list = document.getElementById('compList');
  list.innerHTML = `<div class="hint" style="margin-bottom:.3rem;font-weight:bold">${esc(data.title)}</div>`;
  data.meta.forEach(m=>{
    const chip = document.createElement('div'); chip.className='comp-chip'; chip.draggable=true;
    chip.innerHTML = `<b>${esc(m.label)}</b><div class="hint">${esc(String(m.value)).slice(0,50)}</div>`;
    chip.ondragstart = e=>{ e.dataTransfer.setData('text/plain', JSON.stringify(
      {kind:'meta', field:m.field, ftype:m.type, value:m.value})); };
    list.appendChild(chip);
  });
  data.blocks.forEach(b=>{
    const chip = document.createElement('div'); chip.className='comp-chip'; chip.draggable=true;
    chip.innerHTML = `<b>${esc(b.type)}${b.role?' · '+esc(b.role):''}</b><div class="hint">${esc(b.preview)}</div>`;
    chip.ondragstart = e=>{ e.dataTransfer.setData('text/plain', JSON.stringify(
      {kind:'block', articleId: compArticleId, index: b.index})); };
    list.appendChild(chip);
  });
  if(!data.meta.length && !data.blocks.length) list.innerHTML += '<div class="hint">No components found.</div>';
}
async function drawImagesPanel(q){
  const grid = document.getElementById('imgPanelGrid'); if(!grid) return;
  const items = await j('/api/uploads?q='+encodeURIComponent(q||''));
  grid.innerHTML = '';
  items.forEach(im=>{
    const chip = document.createElement('div'); chip.className='pk-img'; chip.draggable=true; chip.title=im.name;
    chip.innerHTML = `<img src="${esc(im.url)}" loading="lazy">`;
    chip.ondragstart = e=>{ e.dataTransfer.setData('text/plain', JSON.stringify({kind:'image', url: im.url})); };
    grid.appendChild(chip);
  });
  if(!items.length) grid.innerHTML = '<div class="hint">No images in static/uploads.</div>';
}
function rid(){ return Math.random().toString(16).slice(2,10); }
function semHeightGuess(sem){
  const t = sem.type;
  if(t==='paragraph'){ const words=(sem.html||'').replace(/<[^>]+>/g,'').split(/\s+/).filter(Boolean).length; return Math.max(14, Math.min(160, words*0.85)); }
  if(t==='quote') return 42;
  if(t==='photo_unit'||t==='photo_narrative') return 95;
  if(t==='heading') return 14;
  return 40;
}
async function handleComponentDrop(payload, xmm, ymm){
  if(!project) return;
  let block;
  if(payload.kind==='meta'){
    if(payload.ftype==='image'){
      block = {id:rid(), type:'image', x:xmm, y:ymm, w:60, h:60, src:payload.value, caption:''};
    } else {
      block = {id:rid(), type:'meta_field', x:xmm, y:ymm, w:80, h:16, field:payload.field, text:String(payload.value)};
    }
  } else if(payload.kind==='block'){
    const sem = await j(`/api/articles/${payload.articleId}/components/${payload.index}`);
    block = {id:rid(), type:'sem_para', x:xmm, y:ymm, w:120, h:semHeightGuess(sem),
      article_id:payload.articleId, idx:1, accent:'', art_type:'', pq_style:1,
      is_first:false, sem, citations:[]};
  } else if(payload.kind==='image'){
    block = {id:rid(), type:'image', x:xmm, y:ymm, w:60, h:60, src:payload.url, caption:''};
  } else return;
  curPageObj().blocks.push(block);
  selectedIds = new Set([block.id]);
  drawPages(); drawLayers(); drawInspector(); loadFrame();
}
function refreshSel(){
  $projSel.innerHTML = projects.map(p=>`<option value="${p.id}">[${p.kind}] ${esc(p.name)}</option>`).join('');
  if(project) $projSel.value = project.id;
}
async function openProject(id){
  project = await j('/api/projects/'+id);
  curPage = 0; selectedIds = new Set(); refreshSel();
  resetUndoHistory();
  drawPages(); drawLayers(); drawDocLayers(); drawMasters(); drawInspector(); loadFrame();
}

function selectPage(i){
  curPage=i; selectedIds=new Set();
  $pages.querySelectorAll('.mi[data-page-idx]').forEach(el=>{
    el.classList.toggle('is-active', Number(el.dataset.pageIdx)===i);
  });
  drawLayers(); drawMasters(); drawInspector(); loadFrame();
}
function drawPages(){
  $pages.innerHTML='';
  const dims = project.layout.page;
  (project.layout.pages||[]).forEach((pg,i)=>{
    const wrap=document.createElement('div'); wrap.className='mi'+(i===curPage?' is-active':'');
    wrap.dataset.pageIdx = i;
    wrap.innerHTML = `<div class="mi-num">Page ${i+1}</div><div class="mi-thumb"></div>`;
    wrap.onclick=()=> selectPage(i);
    $pages.appendChild(wrap);
    const thumbBox = wrap.querySelector('.mi-thumb');
    const fullW = dims.w*3.78, fullH = dims.h*3.78;
    const scale = 170/fullW;
    thumbBox.style.width = Math.round(fullW*scale)+'px';
    thumbBox.style.height = Math.round(fullH*scale)+'px';
    const tf = document.createElement('iframe');
    tf.scrolling='no'; tf.width=fullW; tf.height=fullH;
    tf.style.transform = `scale(${scale})`; tf.style.transformOrigin='top left';
    thumbBox.appendChild(tf);
    fetch(`/api/projects/${project.id}/preview?page=${i}&editable=0`).then(r=>r.text()).then(html=>{ tf.srcdoc = html; });
  });
  const addBtn=document.createElement('button'); addBtn.textContent='+ Page'; addBtn.style.width='100%'; addBtn.style.marginTop='.4rem';
  addBtn.onclick=()=>{ project.layout.pages.push({blocks:[]}); curPage=project.layout.pages.length-1; drawPages(); drawLayers(); loadFrame(); };
  $pages.appendChild(addBtn);
}

function setZoom(v){
  stageScale = Math.max(0.2, Math.min(2.0, Math.round(v*100)/100));
  document.getElementById('zoomPct').textContent = Math.round(stageScale*100)+'%';
  if(!project) return;
  const dims = project.layout.page;
  const nUp = (spreadView && !editingMaster) ? spreadPageIndices(curPage, (project.layout.pages||[]).length).length : 1;
  $frame.width = dims.w*3.78*nUp; $frame.height = dims.h*3.78;
  $frame.style.transform = `scale(${stageScale})`; $frame.style.transformOrigin='top left';
  drawRulers();
  syncKonvaOverlay();
}
function drawRulers(){
  const dims = project.layout.page;
  const pxPerMm = 3.78*stageScale;
  const rh=document.getElementById('rulerH'), rv=document.getElementById('rulerV');
  rh.style.width=(dims.w*pxPerMm)+'px'; rh.style.height='20px';
  rv.style.height=(dims.h*pxPerMm)+'px'; rv.style.width='20px';
  let hticks='', vticks='';
  for(let m=0;m<=dims.w;m+=10) hticks += `<div class="tick" style="left:${m*pxPerMm}px">${m%50===0?m:''}</div>`;
  for(let m=0;m<=dims.h;m+=10) vticks += `<div class="tick" style="top:${m*pxPerMm}px">${m%50===0?m:''}</div>`;
  rh.innerHTML=hticks; rv.innerHTML=vticks;
}

let undoStack=[], redoStack=[], _lastSnapshot=null;
function snapshotStr(){ return JSON.stringify(project.layout); }
function resetUndoHistory(){ undoStack=[]; redoStack=[]; _lastSnapshot = project ? snapshotStr() : null; }
function _captureUndoPoint(){
  if(!project) return;
  const cur = snapshotStr();
  if(_lastSnapshot !== null && _lastSnapshot !== cur){
    undoStack.push(_lastSnapshot);
    if(undoStack.length > 100) undoStack.shift();
    redoStack = [];
  }
  _lastSnapshot = cur;
}
function clampSelection(){
  const ids = new Set(((curPageObj()||{}).blocks||[]).map(b=>b.id));
  selectedIds = new Set([...selectedIds].filter(id=>ids.has(id)));
}
function doUndo(){
  if(!undoStack.length || !project) return;
  redoStack.push(snapshotStr());
  const prev = undoStack.pop();
  project.layout = JSON.parse(prev);
  _lastSnapshot = prev;
  clampSelection();
  drawPages(); drawLayers(); drawDocLayers(); drawMasters(); drawInspector(); loadFrame();
}
function doRedo(){
  if(!redoStack.length || !project) return;
  undoStack.push(snapshotStr());
  const next = redoStack.pop();
  project.layout = JSON.parse(next);
  _lastSnapshot = next;
  clampSelection();
  drawPages(); drawLayers(); drawDocLayers(); drawMasters(); drawInspector(); loadFrame();
}
function _isTextEditContext(el){
  return el && (el.tagName==='INPUT' || el.tagName==='TEXTAREA' || el.isContentEditable);
}
document.addEventListener('keydown', e=>{
  const mod = e.ctrlKey || e.metaKey;
  if(!mod || _isTextEditContext(document.activeElement)) return;
  const k = e.key.toLowerCase();
  if(k==='z' && !e.shiftKey){ e.preventDefault(); doUndo(); }
  else if(k==='y' || (k==='z' && e.shiftKey)){ e.preventDefault(); doRedo(); }
  else if(k==='c'){ e.preventDefault(); copySelection(); }
  else if(k==='v'){ e.preventDefault(); pasteClipboard(); }
});
document.addEventListener('keydown', e=>{
  if(_isTextEditContext(document.activeElement)) return;
  const k = e.key.toLowerCase();
  if(!['arrowup','arrowdown','arrowleft','arrowright'].includes(k) || !selectedIds.size || !project) return;
  e.preventDefault();
  const step = e.shiftKey ? 5 : 1;
  const dx = k==='arrowleft'?-step : k==='arrowright'?step : 0;
  const dy = k==='arrowup'?-step : k==='arrowdown'?step : 0;
  const blocks = curPageObj().blocks.filter(b=>selectedIds.has(b.id) && !isEffectivelyLocked(b));
  blocks.forEach(b=>{ b.x=Math.max(0,b.x+dx); b.y=Math.max(0,b.y+dy); });
  loadFrame();
});

let _loadFrameTimer = null;
function loadFrame(){
  clearTimeout(_loadFrameTimer);
  _loadFrameTimer = setTimeout(_loadFrameNow, 220);
}
async function _loadFrameNow(){
  _captureUndoPoint();
  syncAllMasterOverrides();
  const dims = project.layout.page;
  const spreadIdx = (spreadView && !editingMaster) ? spreadPageIndices(curPage, (project.layout.pages||[]).length) : [curPage];
  const nUp = spreadIdx.length;
  $frame.width = dims.w*3.78*nUp; $frame.height = dims.h*3.78;
  $frame.style.transform = `scale(${stageScale})`; $frame.style.transformOrigin='top left';
  $frame.srcdoc = '';
  drawRulers();
  try{ await j(`/api/projects/${project.id}`,{method:'PUT',body:JSON.stringify({layout:project.layout})}); }catch(e){}
  const previewUrl = editingMaster
    ? `/api/projects/${project.id}/preview?master=${encodeURIComponent(editingMaster)}`
    : `/api/projects/${project.id}/preview`;
  fetch(previewUrl).then(r=>r.text()).then(html=>{
    $frame.onload = ()=>{
      const doc = $frame.contentDocument;
      const pages = doc.querySelectorAll('.page[data-page]');
      pages.forEach((p,i)=>{
        const visible = editingMaster || spreadIdx.includes(i);
        p.style.display = visible ? 'inline-block' : 'none';
        p.style.verticalAlign = 'top';
        p.style.margin = visible ? '0' : '';
      });
      drawMarginFrame(doc);
      syncKonvaOverlay(doc);
    };
    $frame.srcdoc = html;
  });
}
function snap(v){ const g=Number(document.getElementById('gridMm').value)||0; return g>0 ? Math.round(v/g)*g : v; }
let editingMaster = null;
function curPageObj(){
  if(editingMaster){
    if(!project.layout.masters) project.layout.masters={};
    if(!project.layout.masters[editingMaster]) project.layout.masters[editingMaster]={blocks:[]};
    return project.layout.masters[editingMaster];
  }
  return (project.layout.pages||[])[curPage];
}
function frameChains(){ if(!project.layout.frame_chains) project.layout.frame_chains=[]; return project.layout.frame_chains; }
function chainContaining(id){ return frameChains().find(c=>(c.frame_ids||[]).includes(id)) || null; }
function removeFromChain(id){
  const ch = chainContaining(id); if(!ch) return;
  ch.frame_ids = (ch.frame_ids||[]).filter(x=>x!==id);
  if(ch.frame_ids.length<2) project.layout.frame_chains = frameChains().filter(c=>c!==ch);
}
function moveInChain(id, dir){
  const ch = chainContaining(id); if(!ch) return;
  const idx = ch.frame_ids.indexOf(id), j = idx+dir;
  if(idx<0 || j<0 || j>=ch.frame_ids.length) return;
  [ch.frame_ids[idx], ch.frame_ids[j]] = [ch.frame_ids[j], ch.frame_ids[idx]];
}
function masterNames(){ return Object.keys(project.layout.masters||{}); }
function masterBlockFor(b){
  if(!b || !b.master_ref || editingMaster) return null;
  const pg = (project.layout.pages||[])[curPage];
  const mname = pg && pg.master;
  if(!mname || !project.layout.masters || !project.layout.masters[mname]) return null;
  return (project.layout.masters[mname].blocks||[]).find(mb=>mb.id===b.master_ref) || null;
}
function syncMasterOverrides(b){
  const mb = masterBlockFor(b);
  if(!mb) return;
  const overrides = {};
  Object.keys(b).forEach(k=>{
    if(k==='id' || k==='master_ref' || k==='overrides') return;
    if(JSON.stringify(b[k]) !== JSON.stringify(mb[k])) overrides[k]=b[k];
  });
  b.overrides = overrides;
}
function syncAllMasterOverrides(){
  if(editingMaster) return;
  const pg = (project.layout.pages||[])[curPage];
  (pg && pg.blocks || []).forEach(b=>{ if(b.master_ref) syncMasterOverrides(b); });
}
function enterMasterEdit(name){
  editingMaster = name;
  selectedIds = new Set();
  drawPages(); drawLayers(); drawDocLayers(); drawMasters(); drawInspector(); loadFrame();
}
function exitMasterEdit(){
  editingMaster = null;
  selectedIds = new Set();
  drawPages(); drawLayers(); drawDocLayers(); drawMasters(); drawInspector(); loadFrame();
}
function drawMasters(){
  const banner = document.getElementById('masterBanner');
  const pagesRail = document.getElementById('pages');
  if(editingMaster){
    banner.style.display=''; banner.innerHTML = `Editing master "${esc(editingMaster)}" &nbsp;`;
    const backBtn=document.createElement('button'); backBtn.textContent='← Back to pages';
    backBtn.style.cssText='margin-left:.3rem'; backBtn.onclick=exitMasterEdit;
    banner.appendChild(backBtn);
    pagesRail.style.display='none';
  } else {
    banner.style.display='none';
    pagesRail.style.display='';
  }

  const assign = document.getElementById('masterAssign');
  if(editingMaster || !project.layout.pages[curPage]){
    assign.innerHTML='';
  } else {
    const pg = project.layout.pages[curPage];
    assign.innerHTML = '<label>This page\'s master</label>';
    const sel=document.createElement('select');
    const noneOpt=document.createElement('option'); noneOpt.value=''; noneOpt.textContent='(none)'; sel.appendChild(noneOpt);
    masterNames().forEach(n=>{ const o=document.createElement('option'); o.value=n; o.textContent=n; if(pg.master===n) o.selected=true; sel.appendChild(o); });
    sel.onchange=()=>{ pg.master = sel.value||undefined; loadFrame(); drawMasters(); };
    assign.appendChild(sel);

    if(pg.master && project.layout.masters && project.layout.masters[pg.master]){
      const mBlocks = project.layout.masters[pg.master].blocks || [];
      const alreadyRefd = new Set((pg.blocks||[]).map(b=>b.master_ref).filter(Boolean));
      const avail = mBlocks.filter(mb=>!alreadyRefd.has(mb.id));
      if(avail.length){
        const row=document.createElement('div'); row.style.cssText='margin-top:.4rem';
        row.innerHTML='<label>Override a master block on this page</label>';
        const msel=document.createElement('select');
        avail.forEach(mb=>{ const o=document.createElement('option'); o.value=mb.id;
          o.textContent=`${mb.type} (${(mb.text||mb.caption||mb.id||'').toString().slice(0,24)})`; msel.appendChild(o); });
        const addBtn=document.createElement('button'); addBtn.type='button'; addBtn.textContent='Add override'; addBtn.style.marginLeft='.3rem';
        addBtn.onclick=()=>{
          const mb = mBlocks.find(x=>x.id===msel.value); if(!mb) return;
          const copy = JSON.parse(JSON.stringify(mb));
          copy.id = Math.random().toString(16).slice(2,10);
          copy.master_ref = mb.id; copy.overrides = {};
          pg.blocks = pg.blocks || []; pg.blocks.push(copy);
          selectedIds = new Set([copy.id]);
          drawPages(); drawLayers(); drawInspector(); drawMasters(); loadFrame();
        };
        row.appendChild(msel); row.appendChild(addBtn); assign.appendChild(row);
      }
    }
  }

  const list = document.getElementById('mastersList'); list.innerHTML='';
  masterNames().forEach(n=>{
    const row=document.createElement('div'); row.className='doclayer-row'+(editingMaster===n?' is-active':'');
    const nameSpan=document.createElement('span'); nameSpan.textContent=n; nameSpan.style.flex='1'; nameSpan.style.cursor='pointer';
    nameSpan.onclick=()=>enterMasterEdit(n);
    const delBtn=document.createElement('button'); delBtn.textContent='✕'; delBtn.title='Delete master';
    delBtn.onclick=()=>{
      if(editingMaster===n) exitMasterEdit();
      delete project.layout.masters[n];
      (project.layout.pages||[]).forEach(pg=>{ if(pg.master===n) delete pg.master; });
      drawMasters(); loadFrame();
    };
    row.appendChild(nameSpan); row.appendChild(delBtn);
    list.appendChild(row);
  });
}
function blockById(id){ return (curPageObj().blocks||[]).find(b=>b.id===id); }

function drawMarginFrame(doc){
  const page = doc.querySelector(`.page[data-page="${curPage}"]`); if(!page) return;
  const old = doc.getElementById('dtpMarginFrame'); if(old) old.remove();
  const m = (project.layout.page && project.layout.page.margin) || [15,15,15,15];
  const [t,r,b,l] = m;
  const el = doc.createElement('div'); el.id='dtpMarginFrame';
  el.style.cssText = `position:absolute;left:${l}mm;top:${t}mm;right:${r}mm;bottom:${b}mm;`+
    `border:1px dashed rgba(0,160,0,.5);pointer-events:none;z-index:99997`;
  page.appendChild(el);
}

function pageGuides(){
  const pg = curPageObj();
  if(!pg.guides) pg.guides = {h:[], v:[]};
  return pg.guides;
}
document.getElementById('rulerH').addEventListener('mousedown', e=>{
  if(!project) return;
  pageGuides().h.push(20);
  loadFrame();
});
document.getElementById('rulerV').addEventListener('mousedown', e=>{
  if(!project) return;
  pageGuides().v.push(20);
  loadFrame();
});

function siblingEdges(excludeId){
  const blocks=(curPageObj().blocks||[]).filter(b=>b.id!==excludeId);
  const xs=[], ys=[];
  blocks.forEach(b=>{ xs.push(b.x, b.x+b.w); ys.push(b.y, b.y+b.h); });
  const g = pageGuides();
  ys.push(...(g.h||[])); xs.push(...(g.v||[]));
  const dims = project.layout.page, m = (dims && dims.margin) || [15,15,15,15];
  const [t,r,b,l] = m;
  xs.push(l, dims.w-r); ys.push(t, dims.h-b);
  return {xs, ys};
}
function snapEdge(val, candidates, tol){
  for(const c of candidates){ if(Math.abs(val-c)<=tol) return c; }
  return null;
}
let clipboardBlocks = [];
function copySelection(){
  if(!project || !selectedIds.size) return;
  clipboardBlocks = curPageObj().blocks
    .filter(b=>selectedIds.has(b.id)).map(b=>JSON.parse(JSON.stringify(b)));
}
function pasteClipboard(){
  if(!project || !clipboardBlocks.length) return;
  const pasted = clipboardBlocks.map(b=>{
    const copy = JSON.parse(JSON.stringify(b));
    copy.id = rid(); copy.x = (copy.x||0)+6; copy.y = (copy.y||0)+6;
    delete copy.group_id; copy.locked = false;
    return copy;
  });
  curPageObj().blocks.push(...pasted);
  selectedIds = new Set(pasted.map(b=>b.id));
  drawPages(); drawLayers(); drawInspector(); loadFrame();
}

let konvaStage=null, konvaLayer=null, konvaTransformer=null, konvaNodes=new Map();
let _curDoc=null, _curMetrics=null;
function mm2pxX(mm,m){ return m.originRelX + mm*m.ppmX; }
function mm2pxY(mm,m){ return m.originRelY + mm*m.ppmY; }
function px2mmX(px,m){ return (px - m.originRelX)/m.ppmX; }
function px2mmY(px,m){ return (px - m.originRelY)/m.ppmY; }
function destroyKonvaOverlay(){
  if(konvaStage){ konvaStage.destroy(); }
  konvaStage=null; konvaLayer=null; konvaTransformer=null; konvaNodes=new Map();
  const overlay = document.getElementById('konvaOverlay');
  if(overlay) overlay.innerHTML='';
}

let _shapeDraw = null;
const SHAPE_DRAG_THRESHOLD_PX = 4;
function startShapeDrawing(existingBlock){
  if(!konvaStage){ return; }
  cancelShapeDrawing();
  _shapeDraw = {points: [], targetBlock: existingBlock || null, markers: [], line: null,
                pointerDown: false, dragIdx: null, dragStart: null};
  const st = document.getElementById('status');
  if(st) st.textContent = 'Click to place a straight point; click-and-drag to pull a curve handle. Double-click or Enter to finish, Esc to cancel.';
  konvaStage.container().style.cursor = 'crosshair';
}
function cancelShapeDrawing(){
  if(!_shapeDraw) return;
  _shapeDraw.markers.forEach(m=>m.destroy());
  if(_shapeDraw.line) _shapeDraw.line.destroy();
  if(konvaLayer) konvaLayer.batchDraw();
  if(konvaStage) konvaStage.container().style.cursor = 'default';
  _shapeDraw = null;
  const st = document.getElementById('status');
  if(st) st.textContent = '';
}
function addShapeDrawPoint(){
  if(!_shapeDraw || !_curMetrics) return;
  const pos = konvaStage.getPointerPosition(); if(!pos) return;
  const m = _curMetrics;
  const xmm = Math.max(0, px2mmX(pos.x, m)), ymm = Math.max(0, px2mmY(pos.y, m));
  _shapeDraw.points.push({x: xmm, y: ymm});
  const dot = new Konva.Circle({x: pos.x, y: pos.y, radius: 4, fill: '#ff2020', stroke: '#fff', strokeWidth: 1});
  konvaLayer.add(dot);
  _shapeDraw.markers.push(dot);
  _shapeDraw.pointerDown = true;
  _shapeDraw.dragIdx = _shapeDraw.points.length - 1;
  _shapeDraw.dragStart = {x: pos.x, y: pos.y};
  redrawShapeDrawPreview();
}
function redrawShapeDrawPreview(){
  if(!_shapeDraw || !_curMetrics) return;
  const m = _curMetrics;
  if(_shapeDraw.line) _shapeDraw.line.destroy();
  if(_shapeDraw.points.length >= 2){
    const segs = [];
    for(let i=0;i<_shapeDraw.points.length-1;i++){
      const A=_shapeDraw.points[i], B=_shapeDraw.points[i+1];
      const c1 = A.hx!=null ? {x:A.hx,y:A.hy} : A;
      const c2 = B.hx!=null ? {x:2*B.x-B.hx, y:2*B.y-B.hy} : B;
      segs.push([mm2pxX(A.x,m),mm2pxY(A.y,m), mm2pxX(c1.x,m),mm2pxY(c1.y,m),
                 mm2pxX(c2.x,m),mm2pxY(c2.y,m), mm2pxX(B.x,m),mm2pxY(B.y,m)]);
    }
    _shapeDraw.line = new Konva.Shape({
      stroke:'#ff2020', strokeWidth:1.5, dash:[4,3],
      sceneFunc:(ctx,shape)=>{
        ctx.beginPath();
        segs.forEach((s,i)=>{ if(i===0) ctx.moveTo(s[0],s[1]); ctx.bezierCurveTo(s[2],s[3],s[4],s[5],s[6],s[7]); });
        ctx.strokeShape(shape);
      }
    });
    konvaLayer.add(_shapeDraw.line);
    _shapeDraw.line.moveToBottom();
  }
  konvaLayer.batchDraw();
}
function updateShapeDragHandle(){
  if(!_shapeDraw || !_shapeDraw.pointerDown || _shapeDraw.dragIdx==null || !_curMetrics) return;
  const pos = konvaStage.getPointerPosition(); if(!pos) return;
  const start = _shapeDraw.dragStart;
  if(Math.hypot(pos.x-start.x, pos.y-start.y) < SHAPE_DRAG_THRESHOLD_PX) return;
  const m = _curMetrics;
  const pt = _shapeDraw.points[_shapeDraw.dragIdx];
  pt.hx = px2mmX(pos.x, m); pt.hy = px2mmY(pos.y, m);
  redrawShapeDrawPreview();
}
function finishShapeDragHandle(){
  if(_shapeDraw){ _shapeDraw.pointerDown = false; _shapeDraw.dragIdx = null; _shapeDraw.dragStart = null; }
}
function _shapeSegmentCmd(A, B){
  const c1 = A.hx!=null ? [A.hx, A.hy] : [A.x, A.y];
  const c2 = B.hx!=null ? [2*B.x-B.hx, 2*B.y-B.hy] : [B.x, B.y];
  if(c1[0]===A.x && c1[1]===A.y && c2[0]===B.x && c2[1]===B.y) return `L${B.x} ${B.y}`;
  return `C${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${B.x} ${B.y}`;
}
function finishShapeDrawing(){
  if(!_shapeDraw || _shapeDraw.points.length < 2){ cancelShapeDrawing(); return; }
  const pts = _shapeDraw.points;
  const xs = pts.map(p=>p.x), ys = pts.map(p=>p.y);
  const x0 = Math.min(...xs), y0 = Math.min(...ys);
  const w = Math.max(5, Math.max(...xs) - x0), h = Math.max(5, Math.max(...ys) - y0);
  const rnd = n=>Math.round(n*100)/100;
  const local = pts.map(p=>({x: rnd(p.x-x0), y: rnd(p.y-y0),
                              hx: p.hx!=null?rnd(p.hx-x0):undefined, hy: p.hy!=null?rnd(p.hy-y0):undefined}));
  let b = _shapeDraw.targetBlock;
  if(!b){
    b = {id: Math.random().toString(16).slice(2,10), type:'vector_shape', shape:'polygon', fill:'none', stroke:'#111111', stroke_width:1};
    curPageObj().blocks.push(b);
  }
  b.x = rnd(x0); b.y = rnd(y0); b.w = rnd(w); b.h = rnd(h);
  b.points = local.map(p=>[p.x, p.y]);
  if(!b.shape || b.shape==='rect' || b.shape==='ellipse') b.shape = 'polygon';
  const hasCurve = local.some(p=>p.hx!=null);
  if(hasCurve){
    let d = `M${local[0].x} ${local[0].y}`;
    for(let i=0;i<local.length-1;i++) d += ' ' + _shapeSegmentCmd(local[i], local[i+1]);
    if(b.shape==='polygon') d += ' ' + _shapeSegmentCmd(local[local.length-1], local[0]) + ' Z';
    b.svg_path = d;
  } else {
    delete b.svg_path;
  }
  selectedIds = new Set([b.id]);
  cancelShapeDrawing();
  drawPages(); drawLayers(); drawInspector(); loadFrame();
}
document.addEventListener('keydown', e=>{
  if(!_shapeDraw) return;
  if(e.key==='Escape'){ cancelShapeDrawing(); }
  else if(e.key==='Enter'){ finishShapeDrawing(); }
});
function syncKonvaOverlay(doc){
  if(doc) _curDoc = doc;
  doc = _curDoc;
  const overlay = document.getElementById('konvaOverlay');
  if(!project || !doc || !overlay){ destroyKonvaOverlay(); return; }
  const domPage = editingMaster ? 0 : curPage;
  const stageInner = document.querySelector('.stage-inner');
  const frameRect = $frame.getBoundingClientRect();
  const innerRect = stageInner.getBoundingClientRect();
  const pageEl = doc.querySelector(`.page[data-page="${domPage}"]`);
  overlay.style.left = (frameRect.left-innerRect.left)+'px';
  overlay.style.top = (frameRect.top-innerRect.top)+'px';
  overlay.style.width = frameRect.width+'px';
  overlay.style.height = frameRect.height+'px';
  if(!pageEl || frameRect.width<=0 || frameRect.height<=0){ destroyKonvaOverlay(); return; }

  const dims = project.layout.page;
  const outerScaleX = $frame.clientWidth ? frameRect.width/$frame.clientWidth : 1;
  const outerScaleY = $frame.clientHeight ? frameRect.height/$frame.clientHeight : 1;
  const pageRectInner = pageEl.getBoundingClientRect();
  const m = _curMetrics = {
    originRelX: pageRectInner.left*outerScaleX, originRelY: pageRectInner.top*outerScaleY,
    ppmX: (pageRectInner.width*outerScaleX)/dims.w, ppmY: (pageRectInner.height*outerScaleY)/dims.h,
    outerScaleX, outerScaleY, frameRect,
  };

  if(!konvaStage || konvaStage.width()!==frameRect.width || konvaStage.height()!==frameRect.height){
    destroyKonvaOverlay();
    konvaStage = new Konva.Stage({container:'konvaOverlay', width:Math.max(1,frameRect.width), height:Math.max(1,frameRect.height)});
    konvaLayer = new Konva.Layer();
    konvaStage.add(konvaLayer);
    konvaTransformer = new Konva.Transformer({rotateEnabled:true, borderStroke:'#0060ff', anchorStroke:'#0060ff', anchorFill:'#fff', anchorSize:8});
    konvaLayer.add(konvaTransformer);
    konvaStage.on('mousedown touchstart', e=>{
      if(_shapeDraw){ addShapeDrawPoint(); return; }
      if(e.target===konvaStage){ selectedIds=new Set(); drawLayers(); drawInspector(); syncKonvaSelection(); }
    });
    konvaStage.on('mousemove touchmove', ()=>{ if(_shapeDraw) updateShapeDragHandle(); });
    konvaStage.on('mouseup touchend', ()=>{ if(_shapeDraw) finishShapeDragHandle(); });
    konvaStage.on('dblclick dbltap', ()=>{ if(_shapeDraw) finishShapeDrawing(); });
  }

  const blocks = curPageObj().blocks||[];
  const liveIds = new Set();
  blocks.forEach(b=>{
    const el = doc.querySelector(`.dtp-block[data-block-id="${b.id}"][data-page="${domPage}"]`);
    if(!el) return;
    liveIds.add(b.id);
    const w = Math.max(2, el.offsetWidth*outerScaleX), h = Math.max(2, el.offsetHeight*outerScaleY);
    const left = m.originRelX + el.offsetLeft*outerScaleX, top = m.originRelY + el.offsetTop*outerScaleY;
    const locked = isEffectivelyLocked(b);
    let rect = konvaNodes.get(b.id);
    if(!rect){
      rect = new Konva.Rect({fill:'rgba(0,96,255,0.04)', stroke:'rgba(0,96,255,.35)', strokeWidth:1});
      rect.blockId = b.id;
      konvaLayer.add(rect);
      wireKonvaBlockEvents(rect);
      konvaNodes.set(b.id, rect);
    }
    rect.width(w); rect.height(h);
    rect.offsetX(w/2); rect.offsetY(h/2);
    rect.x(left+w/2); rect.y(top+h/2);
    rect.rotation(b.rotation||0);
    rect.draggable(!locked);
    rect.opacity(locked?0.5:1);
  });
  [...konvaNodes.keys()].forEach(id=>{
    if(!liveIds.has(id)){ konvaNodes.get(id).destroy(); konvaNodes.delete(id); }
  });
  konvaTransformer.moveToTop();
  konvaLayer.batchDraw();
  syncKonvaSelection();
  drawGuidesOuter(m);
  wireComponentDropOnce();
}
function syncKonvaSelection(){
  if(!konvaLayer || !konvaTransformer) return;
  const nodes = [];
  konvaNodes.forEach((rect,id)=>{
    const selected = selectedIds.has(id);
    rect.stroke(selected ? '#0060ff' : 'rgba(0,96,255,.35)');
    rect.strokeWidth(selected ? 2 : 1);
    rect.fill(selected ? 'rgba(0,96,255,0.10)' : 'rgba(0,96,255,0.04)');
    if(selected){
      const b = blockById(id);
      if(b && !isEffectivelyLocked(b)) nodes.push(rect);
    }
  });
  konvaTransformer.nodes(nodes);
  konvaLayer.batchDraw();
}
function wireKonvaBlockEvents(rect){
  let dragStart = null;
  rect.on('click tap', e=>{
    e.cancelBubble = true;
    const id = rect.blockId;
    if(e.evt && e.evt.shiftKey){ selectedIds.has(id) ? selectedIds.delete(id) : selectedIds.add(id); }
    else if(!selectedIds.has(id)){ selectedIds = selectGroup(id); }
    drawLayers(); drawInspector(); syncKonvaSelection();
  });
  rect.on('dragstart', ()=>{
    const id = rect.blockId;
    if(!selectedIds.has(id)){ selectedIds = selectGroup(id); drawLayers(); drawInspector(); syncKonvaSelection(); }
    dragStart = new Map();
    selectedIds.forEach(sid=>{
      const b=blockById(sid); if(!b || isEffectivelyLocked(b)) return;
      const n=konvaNodes.get(sid); if(n) dragStart.set(sid, {x:n.x(), y:n.y()});
    });
  });
  rect.on('dragmove', ()=>{
    if(!dragStart || !_curMetrics) return;
    const m = _curMetrics, id = rect.blockId;
    const start = dragStart.get(id); if(!start) return;
    let dx = rect.x()-start.x, dy = rect.y()-start.y;
    if(selectedIds.size===1){
      const w=rect.width(), h=rect.height();
      let nxMm = snap(px2mmX(rect.x()-w/2, m)), nyMm = snap(px2mmY(rect.y()-h/2, m));
      const {xs,ys} = siblingEdges(id);
      const sxE = snapEdge(nxMm, xs, 2), syE = snapEdge(nyMm, ys, 2);
      if(sxE!=null) nxMm = sxE;
      if(syE!=null) nyMm = syE;
      const snappedX = mm2pxX(nxMm,m)+w/2, snappedY = mm2pxY(nyMm,m)+h/2;
      dx = snappedX-start.x; dy = snappedY-start.y;
      rect.x(snappedX); rect.y(snappedY);
      showGuideOuter(sxE!=null?mm2pxX(sxE,m):null, syE!=null?mm2pxY(syE,m):null);
    }
    selectedIds.forEach(sid=>{
      if(sid===id) return;
      const n=konvaNodes.get(sid), st=dragStart.get(sid);
      if(!n || !st) return;
      n.x(st.x+dx); n.y(st.y+dy);
    });
    konvaLayer.batchDraw();
  });
  rect.on('dragend', ()=>{
    if(!dragStart || !_curMetrics){ dragStart=null; return; }
    const m = _curMetrics;
    dragStart.forEach((_,sid)=>{
      const n=konvaNodes.get(sid), b=blockById(sid);
      if(!n || !b) return;
      const w=n.width(), h=n.height();
      b.x = Math.max(0, snap(px2mmX(n.x()-w/2, m)));
      b.y = Math.max(0, snap(px2mmY(n.y()-h/2, m)));
    });
    dragStart = null;
    showGuideOuter(null,null);
    drawInspector();
    loadFrame();
  });
  rect.on('transformend', ()=>{
    if(!_curMetrics || !konvaTransformer) return;
    const m = _curMetrics;
    konvaTransformer.nodes().forEach(n=>{
      const b = blockById(n.blockId); if(!b) return;
      const sx=n.scaleX(), sy=n.scaleY();
      n.scaleX(1); n.scaleY(1);
      const w = Math.max(10, n.width()*sx), h = Math.max(10, n.height()*sy);
      n.width(w); n.height(h); n.offsetX(w/2); n.offsetY(h/2);
      b.w = Math.max(10, snap(w/m.ppmX));
      b.h = Math.max(10, snap(h/m.ppmY));
      b.x = Math.max(0, snap(px2mmX(n.x()-w/2, m)));
      b.y = Math.max(0, snap(px2mmY(n.y()-h/2, m)));
      b.rotation = Math.round(n.rotation()) || undefined;
    });
    drawInspector();
    loadFrame();
  });
}
function drawGuidesOuter(m){
  const overlay = document.getElementById('konvaOverlay');
  overlay.querySelectorAll('.dtp-guide-outer').forEach(el=>el.remove());
  const g = pageGuides();
  (g.h||[]).forEach((ymm,i)=>{
    const el=document.createElement('div'); el.className='dtp-guide-outer';
    el.style.cssText=`position:absolute;left:0;right:0;top:${mm2pxY(ymm,m)}px;height:0;border-top:1px dashed #0090ff;cursor:ns-resize;pointer-events:auto`;
    overlay.appendChild(el);
    wireGuideDragOuter(el,'h',i,m);
  });
  (g.v||[]).forEach((xmm,i)=>{
    const el=document.createElement('div'); el.className='dtp-guide-outer';
    el.style.cssText=`position:absolute;top:0;bottom:0;left:${mm2pxX(xmm,m)}px;width:0;border-left:1px dashed #0090ff;cursor:ew-resize;pointer-events:auto`;
    overlay.appendChild(el);
    wireGuideDragOuter(el,'v',i,m);
  });
}
function wireGuideDragOuter(el,axis,idx,m){
  el.onmousedown = e=>{
    e.preventDefault(); e.stopPropagation();
    const frameRect = m.frameRect;
    let del = false;
    function mv(ev){
      const g = pageGuides();
      const outside = axis==='h'
        ? (ev.clientY < frameRect.top-15 || ev.clientY > frameRect.bottom+15)
        : (ev.clientX < frameRect.left-15 || ev.clientX > frameRect.right+15);
      del = outside;
      el.style.opacity = outside ? '0.25' : '1';
      if(outside) return;
      if(axis==='h'){ const ymm=Math.max(0, px2mmY(ev.clientY-frameRect.top, m)); g.h[idx]=ymm; el.style.top=mm2pxY(ymm,m)+'px'; }
      else { const xmm=Math.max(0, px2mmX(ev.clientX-frameRect.left, m)); g.v[idx]=xmm; el.style.left=mm2pxX(xmm,m)+'px'; }
    }
    function up(){
      document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up);
      if(del){ pageGuides()[axis].splice(idx,1); syncKonvaOverlay(); }
      loadFrame();
    }
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
  };
}
function showGuideOuter(xpx, ypx){
  const overlay = document.getElementById('konvaOverlay');
  if(!overlay) return;
  let gx=document.getElementById('dtpGuideXOuter'), gy=document.getElementById('dtpGuideYOuter');
  if(!gx){ gx=document.createElement('div'); gx.id='dtpGuideXOuter'; gx.style.cssText='position:absolute;top:0;bottom:0;width:0;border-left:1px dashed red;pointer-events:none;display:none'; overlay.appendChild(gx); }
  if(!gy){ gy=document.createElement('div'); gy.id='dtpGuideYOuter'; gy.style.cssText='position:absolute;left:0;right:0;height:0;border-top:1px dashed red;pointer-events:none;display:none'; overlay.appendChild(gy); }
  if(xpx!=null){ gx.style.left=xpx+'px'; gx.style.display='block'; } else gx.style.display='none';
  if(ypx!=null){ gy.style.top=ypx+'px'; gy.style.display='block'; } else gy.style.display='none';
}
function wireComponentDropOnce(){
  const overlay = document.getElementById('konvaOverlay');
  if(!overlay || overlay._dropWired) return;
  overlay._dropWired = true;
  overlay.addEventListener('dragover', e=>{ e.preventDefault(); });
  overlay.addEventListener('drop', e=>{
    e.preventDefault();
    const raw = e.dataTransfer.getData('text/plain'); if(!raw) return;
    let payload; try{ payload = JSON.parse(raw); } catch(_){ return; }
    const m = _curMetrics; if(!m) return;
    const xmm = Math.max(0, px2mmX(e.clientX-m.frameRect.left, m));
    const ymm = Math.max(0, px2mmY(e.clientY-m.frameRect.top, m));
    handleComponentDrop(payload, xmm, ymm);
  });
}

const BLOCK_DEFAULTS = {
  text: {w:80,h:40,text:'New text block'},
  image: {w:60,h:60,src:'',caption:'',credit:''},
  headline: {w:120,h:20,text:'Headline',color:'#111111'},
  pullquote: {w:70,h:40,text:'Pull quote text',cite:'',style:1,accent:'#c8a84a'},
  logo: {w:30,h:30,invert:false},
  qr: {w:35,h:40,url:'',label:''},
  generative_art: {w:80,h:100,art_style:'flow',seed:42,label:''},
  copyright: {w:100,h:10,align:'center',text_override:''},
  author_bio: {w:90,h:40,author_id:null},
  vector_shape: {w:60,h:40,shape:'rect',fill:'none',stroke:'#111111',stroke_width:1,points:[]},
};
function addBlock(type){
  if(!project || !curPageObj()) return;
  const d = BLOCK_DEFAULTS[type]; if(!d) return;
  const block = Object.assign({id: Math.random().toString(16).slice(2,10), type, x:10, y:10}, d);
  curPageObj().blocks.push(block);
  selectedIds = new Set([block.id]);
  drawPages(); drawLayers(); drawInspector(); loadFrame();
}

function drawLayers(){ drawUnifiedLayers(); }
function selectGroup(id){
  const b = blockById(id);
  if(!b || !b.group_id) return new Set([id]);
  const blocks = curPageObj().blocks;
  return new Set(blocks.filter(x=>x.group_id===b.group_id).map(x=>x.id));
}
function reorderBlock(id, action){
  const blocks = curPageObj().blocks;
  const idx = blocks.findIndex(b=>b.id===id); if(idx<0) return;
  if(action==='front'){ const [b]=blocks.splice(idx,1); blocks.push(b); }
  else if(action==='back'){ const [b]=blocks.splice(idx,1); blocks.unshift(b); }
  else if(action==='forward' && idx<blocks.length-1){ [blocks[idx],blocks[idx+1]]=[blocks[idx+1],blocks[idx]]; }
  else if(action==='backward' && idx>0){ [blocks[idx],blocks[idx-1]]=[blocks[idx-1],blocks[idx]]; }
  drawLayers(); loadFrame();
}

const TYPE_FIELDS = {
  text: ['text'],
  headline: ['text','color'],
  pullquote: ['text','cite','style','accent'],
  image: ['src','caption','credit'],
  logo: ['invert'],
  qr: ['url','label'],
  generative_art: ['art_style','seed','label'],
  copyright: ['text_override','align'],
  author_bio: ['author_id'],
  vector_shape: ['shape','fill','stroke','stroke_width'],
};
let _authorsCache = null;
async function loadAuthors(){ if(!_authorsCache) _authorsCache = await j('/api/authors'); return _authorsCache; }
const SEM_ROLES = ['lede','analysis','context','scene','testimony','resolution','note','dateline'];
function plainText(html){ return (html||'').replace(/<[^>]+>/g,''); }
function paraHtml(text, role){ return `<p${role?` data-text-role="${esc(role)}"`:''}>${esc(text)}</p>`; }
function runsPlainText(runs){ return (runs||[]).map(r=>r.text||'').join(''); }
function runsToHtmlJS(runs){
  return (runs||[]).map(r=>{
    let txt = esc(r.text||'');
    if(r.href) txt = `<a href="${esc(r.href)}" style="color:inherit;text-decoration:underline">${txt}</a>`;
    if(r.underline) txt = `<u>${txt}</u>`;
    if(r.italic) txt = `<i>${txt}</i>`;
    if(r.bold) txt = `<b>${txt}</b>`;
    if(r.color) txt = `<span style="color:${esc(r.color)}">${txt}</span>`;
    return txt || '​';
  }).join('') || '​';
}
function sameRunFormatting(a,b){
  return !!a.bold===!!b.bold && !!a.italic===!!b.italic && !!a.underline===!!b.underline &&
         (a.color||'')===(b.color||'') && (a.href||'')===(b.href||'');
}
function mergeAdjacentRuns(runs){
  const out=[];
  (runs||[]).forEach(r=>{
    if(!(r.text||'').length) return;
    const prev = out[out.length-1];
    if(prev && sameRunFormatting(prev, r)) prev.text += r.text;
    else out.push(Object.assign({}, r));
  });
  return out.length ? out : [{text:''}];
}
function splitRunsAtRange(runs, start, end, patchFn){
  if(start>=end) return runs;
  const out=[]; let pos=0;
  (runs||[]).forEach(r=>{
    const text=r.text||''; const n=text.length;
    const rStart=pos, rEnd=pos+n; pos=rEnd;
    const lo=Math.max(rStart,start), hi=Math.min(rEnd,end);
    if(lo>=hi){ out.push(r); return; }
    if(lo>rStart) out.push(Object.assign({}, r, {text: text.slice(0, lo-rStart)}));
    out.push(patchFn(Object.assign({}, r, {text: text.slice(lo-rStart, hi-rStart)})));
    if(hi<rEnd) out.push(Object.assign({}, r, {text: text.slice(hi-rStart)}));
  });
  return out;
}
function rangeAllHave(runs, start, end, key){
  let pos=0, sawAny=false;
  for(const r of (runs||[])){
    const n=(r.text||'').length; const rStart=pos, rEnd=pos+n; pos=rEnd;
    const lo=Math.max(rStart,start), hi=Math.min(rEnd,end);
    if(lo>=hi) continue;
    sawAny = true;
    if(!r[key]) return false;
  }
  return sawAny;
}
function getSelectionOffsets(container){
  const sel = window.getSelection();
  if(!sel || sel.rangeCount===0) return null;
  const range = sel.getRangeAt(0);
  if(!container.contains(range.commonAncestorContainer)) return null;
  const pre = document.createRange();
  pre.selectNodeContents(container);
  pre.setEnd(range.startContainer, range.startOffset);
  const start = pre.toString().length;
  return {start, end: start + range.toString().length};
}

function drawRunsToolbar(b, getText, onRunsChanged){
  const wrap=document.createElement('div'); wrap.className='field';
  wrap.innerHTML='<label>Rich text</label>' +
    '<div class="hint" style="margin-bottom:.3rem">Select text below, then click a button to format just that ' +
    'selection. No selection = applies to the whole block. Editing the plain-text field above resets formatting.</div>';

  const text = getText();
  if(!b.runs || runsPlainText(b.runs) !== text) b.runs = [{text}];

  const editable = document.createElement('div');
  editable.contentEditable = 'true';
  editable.className = 'rich-text-edit';
  editable.style.cssText = 'border:1px solid var(--line,#ccc);border-radius:3px;padding:.4rem;min-height:2.4em;' +
    'margin-bottom:.4rem;font-family:Georgia,serif;line-height:1.4;white-space:pre-wrap';
  editable.innerHTML = runsToHtmlJS(b.runs);
  editable.onblur=()=>{ editable.innerHTML = runsToHtmlJS(b.runs); };
  wrap.appendChild(editable);

  function applyToSelection(patch){
    const offs = getSelectionOffsets(editable);
    const total = runsPlainText(b.runs).length;
    const start = offs && offs.end>offs.start ? offs.start : 0;
    const end = offs && offs.end>offs.start ? offs.end : total;
    if(total===0) return;
    const patched = splitRunsAtRange(b.runs, start, end, r=>Object.assign(r, patch));
    b.runs = mergeAdjacentRuns(patched);
    editable.innerHTML = runsToHtmlJS(b.runs);
    if(onRunsChanged) onRunsChanged();
    loadFrame();
  }

  const row=document.createElement('div'); row.style.cssText='display:flex;gap:.4rem;align-items:center;flex-wrap:wrap';
  const mk=(label,key)=>{
    const btn=document.createElement('button'); btn.type='button'; btn.textContent=label;
    btn.onmousedown=e=>e.preventDefault();
    btn.onclick=()=>{
      const offs = getSelectionOffsets(editable);
      const total = runsPlainText(b.runs).length;
      const start = offs && offs.end>offs.start ? offs.start : 0;
      const end = offs && offs.end>offs.start ? offs.end : total;
      const turnOn = !rangeAllHave(b.runs, start, end, key);
      applyToSelection({[key]: turnOn || undefined});
    };
    return btn;
  };
  row.appendChild(mk('Bold','bold')); row.appendChild(mk('Italic','italic')); row.appendChild(mk('Underline','underline'));
  const colorInp=document.createElement('input'); colorInp.type='color'; colorInp.title='Selection color';
  colorInp.onmousedown=e=>e.preventDefault();
  colorInp.oninput=()=>applyToSelection({color: colorInp.value});
  const colorClear=document.createElement('button'); colorClear.type='button'; colorClear.textContent='No color';
  colorClear.onmousedown=e=>e.preventDefault();
  colorClear.onclick=()=>applyToSelection({color: undefined});
  row.appendChild(colorInp); row.appendChild(colorClear);
  wrap.appendChild(row);

  const linkRow=document.createElement('div'); linkRow.style.cssText='margin-top:.3rem;display:flex;gap:.3rem';
  const linkInp=document.createElement('input'); linkInp.placeholder='https:// (link for the current selection)';
  linkInp.style.flex='1';
  linkInp.onmousedown=e=>e.stopPropagation();
  const linkBtn=document.createElement('button'); linkBtn.type='button'; linkBtn.textContent='Apply link';
  linkBtn.onmousedown=e=>e.preventDefault();
  linkBtn.onclick=()=>{ if(linkInp.value) applyToSelection({href: linkInp.value}); };
  const linkClearBtn=document.createElement('button'); linkClearBtn.type='button'; linkClearBtn.textContent='Remove link';
  linkClearBtn.onmousedown=e=>e.preventDefault();
  linkClearBtn.onclick=()=>applyToSelection({href: undefined});
  linkRow.appendChild(linkInp); linkRow.appendChild(linkBtn); linkRow.appendChild(linkClearBtn);
  wrap.appendChild(linkRow);
  return wrap;
}
function drawSemParaEditor(b){
  const sem = b.sem || (b.sem = {type:'paragraph', html:'<p></p>'});
  if(sem.type === 'paragraph'){
    const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML='<label>Paragraph text</label>';
    const ta=document.createElement('textarea'); ta.rows=6; ta.value=plainText(sem.html);
    ta.oninput=()=>{ sem.html = paraHtml(ta.value, sem.text_role); if(sem.runs && sem.runs[0]) sem.runs[0].text=ta.value; };
    ta.onblur=()=>loadFrame();
    wrap.appendChild(ta); $inspectorBody.appendChild(wrap);

    const roleWrap=document.createElement('div'); roleWrap.className='field';
    roleWrap.innerHTML='<label>Role (SEMANTIC.md, or type your own for a fully custom tag)</label>';
    const roleInp=document.createElement('input'); roleInp.setAttribute('list','semRolesDL'); roleInp.value=sem.text_role||'';
    roleInp.oninput=()=>{ sem.text_role = roleInp.value || undefined; sem.html = paraHtml(plainText(sem.html), sem.text_role); };
    roleInp.onblur=()=>loadFrame();
    roleWrap.appendChild(roleInp);
    if(!document.getElementById('semRolesDL')){
      const dl=document.createElement('datalist'); dl.id='semRolesDL';
      SEM_ROLES.forEach(r=>{ const o=document.createElement('option'); o.value=r; dl.appendChild(o); });
      roleWrap.appendChild(dl);
    }
    $inspectorBody.appendChild(roleWrap);

    const convBtn=document.createElement('button'); convBtn.textContent='Convert to quote'; convBtn.style.marginBottom='.5rem';
    convBtn.onclick=()=>{ b.sem = {type:'quote', text:plainText(sem.html), cite:''}; drawInspector(); loadFrame(); };
    $inspectorBody.appendChild(convBtn);

    $inspectorBody.appendChild(drawRunsToolbar(sem, ()=>plainText(sem.html),
      ()=>{  }));
  } else if(sem.type === 'quote'){
    ['text','cite'].forEach(k=>{
      const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML=`<label>${k}</label>`;
      const ta=document.createElement('textarea'); ta.rows = k==='text'?4:1; ta.value=sem[k]||'';
      ta.oninput=()=>{ sem[k]=ta.value; };
      ta.onblur=()=>loadFrame();
      wrap.appendChild(ta); $inspectorBody.appendChild(wrap);
    });
    const convBtn=document.createElement('button'); convBtn.textContent='Convert to paragraph'; convBtn.style.marginBottom='.5rem';
    convBtn.onclick=()=>{ b.sem = {type:'paragraph', html:paraHtml(sem.text||'')}; drawInspector(); loadFrame(); };
    $inspectorBody.appendChild(convBtn);
  } else if(sem.type === 'photo_unit' || sem.type === 'photo_narrative'){
    const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML='<label>Caption</label>';
    const ta=document.createElement('textarea'); ta.rows=2; ta.value=sem.caption||'';
    ta.oninput=()=>{ sem.caption=ta.value; sem.caption_html = ta.value ? `<figcaption>${esc(ta.value)}</figcaption>` : ''; };
    ta.onblur=()=>loadFrame();
    wrap.appendChild(ta); $inspectorBody.appendChild(wrap);

    const chooseBtn=document.createElement('button'); chooseBtn.textContent='Change image…'; chooseBtn.style.marginBottom='.5rem';
    chooseBtn.onclick=()=> pickImage(url=>{ sem.img = `<img src="${esc(url)}" alt="">`; drawInspector(); loadFrame(); });
    $inspectorBody.appendChild(chooseBtn);

    const imgSrcMatch = (sem.img||'').match(/src="([^"]+)"/);
    if(imgSrcMatch){
      const cropWrap=document.createElement('div'); cropWrap.className='field';
      cropWrap.innerHTML='<label>Focal point (click the image to recompose the crop for print)</label>';
      const box=document.createElement('div'); box.style.cssText='position:relative;width:100%;cursor:crosshair;border:1px solid var(--line)';
      const img=document.createElement('img'); img.src=imgSrcMatch[1]; img.style.cssText='width:100%;display:block';
      const dot=document.createElement('div');
      dot.style.cssText=`position:absolute;width:10px;height:10px;border-radius:50%;background:red;border:1px solid #fff;`+
        `transform:translate(-50%,-50%);left:${b.crop_x??50}%;top:${b.crop_y??50}%;pointer-events:none`;
      box.appendChild(img); box.appendChild(dot);
      box.onclick=(e)=>{
        const r=box.getBoundingClientRect();
        const px=Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100));
        const py=Math.max(0,Math.min(100,(e.clientY-r.top)/r.height*100));
        b.crop_x=Math.round(px); b.crop_y=Math.round(py);
        dot.style.left=px+'%'; dot.style.top=py+'%';
        loadFrame();
      };
      cropWrap.appendChild(box); $inspectorBody.appendChild(cropWrap);
    }
  } else {
    const wrap=document.createElement('div'); wrap.className='field';
    wrap.innerHTML = `<label>sem.type: ${esc(sem.type||'')}</label><div class="hint">No dedicated editor for this ` +
      `content type yet -- position/resize/style overrides still apply.</div>`;
    $inspectorBody.appendChild(wrap);
  }
}

function drawInspector(){
  $inspectorBody.innerHTML='';
  if(!project){ $inspectorBody.innerHTML='<div class="hint">Select a block.</div>'; return; }
  const ids=[...selectedIds];
  if(ids.length===0){ $inspectorBody.innerHTML='<div class="hint">Select a block.</div>'; return; }
  if(ids.length>1){
    const blocks = ids.map(blockById).filter(Boolean);
    const h=document.createElement('div'); h.innerHTML=`<b>${blocks.length} blocks selected</b>`; h.style.marginBottom='.5rem';
    $inspectorBody.appendChild(h);

    const alignHead=document.createElement('div'); alignHead.className='panel-title'; alignHead.textContent='Align';
    $inspectorBody.appendChild(alignHead);
    const alignRow=document.createElement('div'); alignRow.style.cssText='display:flex;flex-wrap:wrap;gap:.25rem;margin-bottom:.5rem';
    const ALIGN_OPS = [
      ['Left',()=>{ const x0=Math.min(...blocks.map(b=>b.x)); blocks.forEach(b=>b.x=x0); }],
      ['Center H',()=>{ const x0=Math.min(...blocks.map(b=>b.x)), x1=Math.max(...blocks.map(b=>b.x+b.w)); const c=(x0+x1)/2; blocks.forEach(b=>b.x=c-b.w/2); }],
      ['Right',()=>{ const x1=Math.max(...blocks.map(b=>b.x+b.w)); blocks.forEach(b=>b.x=x1-b.w); }],
      ['Top',()=>{ const y0=Math.min(...blocks.map(b=>b.y)); blocks.forEach(b=>b.y=y0); }],
      ['Center V',()=>{ const y0=Math.min(...blocks.map(b=>b.y)), y1=Math.max(...blocks.map(b=>b.y+b.h)); const c=(y0+y1)/2; blocks.forEach(b=>b.y=c-b.h/2); }],
      ['Bottom',()=>{ const y1=Math.max(...blocks.map(b=>b.y+b.h)); blocks.forEach(b=>b.y=y1-b.h); }],
    ];
    ALIGN_OPS.forEach(([label,fn])=>{
      const btn=document.createElement('button'); btn.textContent=label; btn.style.flex='1 0 auto';
      btn.onclick=()=>{ fn(); drawInspector(); loadFrame(); };
      alignRow.appendChild(btn);
    });
    $inspectorBody.appendChild(alignRow);

    if(blocks.length>=3){
      const distHead=document.createElement('div'); distHead.className='panel-title'; distHead.textContent='Distribute';
      $inspectorBody.appendChild(distHead);
      const distRow=document.createElement('div'); distRow.style.cssText='display:flex;gap:.25rem;margin-bottom:.5rem';
      const distH=document.createElement('button'); distH.textContent='Horizontally'; distH.style.flex='1';
      distH.onclick=()=>{
        const sorted=[...blocks].sort((a,c)=>a.x-c.x);
        const lo=sorted[0].x, hi=sorted[sorted.length-1].x+sorted[sorted.length-1].w;
        const totalW=sorted.reduce((s,b)=>s+b.w,0);
        const gap=(hi-lo-totalW)/(sorted.length-1);
        let cx=lo; sorted.forEach(b=>{ b.x=cx; cx+=b.w+gap; });
        drawInspector(); loadFrame();
      };
      const distV=document.createElement('button'); distV.textContent='Vertically'; distV.style.flex='1';
      distV.onclick=()=>{
        const sorted=[...blocks].sort((a,c)=>a.y-c.y);
        const lo=sorted[0].y, hi=sorted[sorted.length-1].y+sorted[sorted.length-1].h;
        const totalH=sorted.reduce((s,b)=>s+b.h,0);
        const gap=(hi-lo-totalH)/(sorted.length-1);
        let cy=lo; sorted.forEach(b=>{ b.y=cy; cy+=b.h+gap; });
        drawInspector(); loadFrame();
      };
      distRow.appendChild(distH); distRow.appendChild(distV);
      $inspectorBody.appendChild(distRow);
    }

    ['x','y','w','h'].forEach(k=>{
      const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML=`<label>${k} (mm)</label>`;
      const inp=document.createElement('input'); inp.type='number'; inp.placeholder='(mixed)';
      inp.onchange=()=>{ const v=Number(inp.value); if(!isNaN(v)){ blocks.forEach(b=>{ b[k]=v; }); loadFrame(); } };
      wrap.appendChild(inp); $inspectorBody.appendChild(wrap);
    });
    const groupRow=document.createElement('div'); groupRow.style.cssText='display:flex;gap:.25rem;margin-bottom:.5rem';
    const sameGroup = blocks.every(bl=>bl.group_id && bl.group_id===blocks[0].group_id);
    const groupBtn=document.createElement('button'); groupBtn.textContent='Group'; groupBtn.style.flex='1';
    groupBtn.onclick=()=>{ const gid=rid(); blocks.forEach(bl=>bl.group_id=gid); drawInspector(); loadFrame(); };
    const ungroupBtn=document.createElement('button'); ungroupBtn.textContent='Ungroup'; ungroupBtn.style.flex='1';
    ungroupBtn.disabled=!sameGroup;
    ungroupBtn.onclick=()=>{ blocks.forEach(bl=>delete bl.group_id); drawInspector(); loadFrame(); };
    groupRow.appendChild(groupBtn); groupRow.appendChild(ungroupBtn);
    $inspectorBody.appendChild(groupRow);

    const chainable = ids.map(blockById).filter(x=>x && x.type==='sem_para' && x.sem && x.sem.type==='paragraph');
    if(chainable.length>=2 && chainable.length===ids.length){
      const chainHead=document.createElement('div'); chainHead.className='panel-title'; chainHead.textContent='Frame Chain';
      $inspectorBody.appendChild(chainHead);
      const chainBtn=document.createElement('button'); chainBtn.textContent=`Chain these ${chainable.length} frames (in selection order)`;
      chainBtn.style.marginBottom='.5rem';
      chainBtn.onclick=()=>{
        const chains = frameChains();
        chains.forEach(c=>{ c.frame_ids = (c.frame_ids||[]).filter(fid=>!ids.includes(fid)); });
        project.layout.frame_chains = chains.filter(c=>(c.frame_ids||[]).length>=2);
        project.layout.frame_chains.push({id: rid(), frame_ids: ids});
        drawInspector(); loadFrame();
      };
      $inspectorBody.appendChild(chainBtn);
    }

    const delBtn=document.createElement('button'); delBtn.textContent='Delete selected'; delBtn.style.marginTop='.5rem';
    delBtn.onclick=()=>{ curPageObj().blocks = curPageObj().blocks.filter(b=>!selectedIds.has(b.id) || isEffectivelyLocked(b));
      selectedIds=new Set(); drawPages(); drawLayers(); drawInspector(); loadFrame(); };
    $inspectorBody.appendChild(delBtn);
    return;
  }
  const b = blockById(ids[0]);
  if(!b){ $inspectorBody.innerHTML='<div class="hint">Select a block.</div>'; return; }
  const h=document.createElement('div'); h.innerHTML=`<b>${esc(b.type)}</b>`; h.style.marginBottom='.5rem'; $inspectorBody.appendChild(h);

  const posRow=document.createElement('div'); posRow.style.cssText='display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.6rem';
  [['x','X (mm)'],['y','Y (mm)'],['w','W (mm)'],['h','H (mm)'],['rotation','Rotate (°)']].forEach(([k,label])=>{
    const wrap=document.createElement('div'); wrap.className='field'; wrap.style.cssText='flex:1 0 40%;margin-bottom:0';
    wrap.innerHTML=`<label>${label}</label>`;
    const inp=document.createElement('input'); inp.type='number';
    inp.value = k==='rotation' ? (b.rotation||0) : (b[k]??0);
    inp.onchange=()=>{
      const v=Number(inp.value); if(isNaN(v)) return;
      if(k==='rotation') b.rotation = v||undefined;
      else if(k==='w' || k==='h') b[k]=Math.max(10,v);
      else b[k]=Math.max(0,v);
      loadFrame();
    };
    wrap.appendChild(inp); posRow.appendChild(wrap);
  });
  $inspectorBody.appendChild(posRow);

  const fields = TYPE_FIELDS[b.type];
  const handled = new Set(['id','type','html','extra_css','blocks','citations','group_id','locked','layer','x','y','w','h','rotation']);
  if(fields){
    fields.forEach(k=>handled.add(k));
    if(b.type==='image'){
      const chooseBtn=document.createElement('button'); chooseBtn.textContent = b.src ? 'Change image…' : 'Choose image…';
      chooseBtn.style.marginBottom='.5rem';
      chooseBtn.onclick=()=> pickImage(url=>{ b.src=url; drawInspector(); loadFrame(); });
      $inspectorBody.appendChild(chooseBtn);
      if(b.src){ const prev=document.createElement('img'); prev.src=b.src; prev.style.cssText='width:100%;max-height:120px;object-fit:cover;margin-bottom:.5rem;display:block'; $inspectorBody.appendChild(prev); }
    }
    fields.forEach(k=>{
      if(k==='src') return;
      const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML=`<label>${esc(k)}</label>`;
      if(k==='color' || k==='accent'){
        const inp=document.createElement('input'); inp.type='color';
        inp.value = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(b[k]||'') ? b[k] : '#000000';
        inp.oninput=()=>{ b[k]=inp.value; loadFrame(); };
        wrap.appendChild(inp);
      } else if(k==='style'){
        const sel=document.createElement('select');
        for(let s=1;s<=7;s++){ const o=document.createElement('option'); o.value=s; o.textContent='Style '+s; if(Number(b[k])===s) o.selected=true; sel.appendChild(o); }
        sel.onchange=()=>{ b[k]=Number(sel.value); loadFrame(); };
        wrap.appendChild(sel);
      } else if(k==='text' || k==='cite' || k==='caption' || k==='credit' || k==='text_override'){
        const ta=document.createElement('textarea'); ta.rows = k==='text'?4:1; ta.value=b[k]||'';
        ta.oninput=()=>{ b[k]=ta.value; if(k==='text' && b.runs && b.runs[0]) b.runs[0].text=ta.value; };
        ta.onblur=()=>loadFrame();
        wrap.appendChild(ta);
      } else if(k==='invert'){
        const inp=document.createElement('input'); inp.type='checkbox'; inp.checked=!!b[k];
        inp.onchange=()=>{ b[k]=inp.checked; loadFrame(); };
        wrap.appendChild(inp);
      } else if(k==='align' && b.type==='copyright'){
        const sel=document.createElement('select');
        ['left','center','right'].forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; if((b[k]||'center')===v) o.selected=true; sel.appendChild(o); });
        sel.onchange=()=>{ b[k]=sel.value; loadFrame(); };
        wrap.appendChild(sel);
      } else if(k==='art_style'){
        const sel=document.createElement('select');
        [['flow','Flow field'],['voronoi','Voronoi shatter'],['spiral','Spiral emblem']].forEach(([v,l])=>{
          const o=document.createElement('option'); o.value=v; o.textContent=l; if((b[k]||'flow')===v) o.selected=true; sel.appendChild(o);
        });
        sel.onchange=()=>{ b[k]=sel.value; loadFrame(); };
        wrap.appendChild(sel);
      } else if(k==='seed'){
        const inp=document.createElement('input'); inp.type='number'; inp.value=b[k]??42;
        inp.oninput=()=>{ b[k]=Number(inp.value)||0; };
        inp.onblur=()=>loadFrame();
        wrap.appendChild(inp);
      } else if(k==='shape'){
        const sel=document.createElement('select');
        [['rect','Rectangle'],['ellipse','Ellipse'],['polygon','Polygon (closed)'],['polyline','Polyline (open)']].forEach(([v,l])=>{
          const o=document.createElement('option'); o.value=v; o.textContent=l; if((b[k]||'rect')===v) o.selected=true; sel.appendChild(o);
        });
        sel.onchange=()=>{ b[k]=sel.value; drawInspector(); loadFrame(); };
        wrap.appendChild(sel);
      } else if(k==='fill' || k==='stroke'){
        const row=document.createElement('div'); row.style.cssText='display:flex;gap:.3rem;align-items:center';
        const isNone = !b[k] || b[k]==='none';
        const inp=document.createElement('input'); inp.type='color';
        inp.value = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(b[k]||'') ? b[k] : (k==='fill'?'#ffffff':'#111111');
        inp.oninput=()=>{ b[k]=inp.value; loadFrame(); };
        const noneBtn=document.createElement('button'); noneBtn.type='button'; noneBtn.textContent = k==='fill' ? 'None' : 'Default';
        noneBtn.onclick=()=>{ b[k] = k==='fill' ? 'none' : undefined; loadFrame(); };
        row.appendChild(inp); row.appendChild(noneBtn); wrap.appendChild(row);
        if(isNone){ const h=document.createElement('div'); h.className='hint'; h.textContent = k==='fill'?'(no fill)':'(default stroke)'; wrap.appendChild(h); }
      } else if(k==='stroke_width'){
        const inp=document.createElement('input'); inp.type='number'; inp.min=0; inp.step=0.5; inp.value=b[k]??1;
        inp.oninput=()=>{ b[k]=Number(inp.value)||0; };
        inp.onblur=()=>loadFrame();
        wrap.appendChild(inp);
      } else if(k==='author_id'){
        const sel=document.createElement('select');
        const opt0=document.createElement('option'); opt0.value=''; opt0.textContent='(choose author)'; sel.appendChild(opt0);
        loadAuthors().then(authors=>{
          authors.forEach(a=>{
            const o=document.createElement('option'); o.value=a.id; o.textContent=a.name+(a.role?` (${a.role})`:'');
            if(Number(b[k])===a.id) o.selected=true;
            sel.appendChild(o);
          });
        });
        sel.onchange=()=>{ b[k]=sel.value?Number(sel.value):null; loadFrame(); };
        wrap.appendChild(sel);
      } else {
        const inp=document.createElement('input'); inp.value=b[k]??'';
        inp.oninput=()=>{ b[k]=inp.value; loadFrame(); };
        wrap.appendChild(inp);
      }
      $inspectorBody.appendChild(wrap);
    });
    if(fields.includes('text')){
      handled.add('runs');
      $inspectorBody.appendChild(drawRunsToolbar(b, ()=>b.text||''));
    }
  }

  if(b.type==='raw_page'){
    handled.add('html');
    const wrap=document.createElement('div'); wrap.className='field';
    wrap.innerHTML=`<label>html (edit the real ingested page directly)</label>`;
    const ta=document.createElement('textarea'); ta.rows=18; ta.value=b.html||'';
    ta.oninput=()=>{ b.html = ta.value; };
    ta.onblur=()=>loadFrame();
    wrap.appendChild(ta);
    $inspectorBody.appendChild(wrap);
  }

  if(b.type==='bs_column'){
    handled.add('items'); handled.add('link_next');
    const wrap=document.createElement('div'); wrap.className='field';
    wrap.innerHTML='<label>Column content (edit the real flowing html directly)</label>';
    const joined = (b.items||[]).map(it=>it.html||'').join('');
    const ta=document.createElement('textarea'); ta.rows=10; ta.value=joined;
    ta.oninput=()=>{ b.items=[{html:ta.value,cost:1}]; };
    ta.onblur=()=>loadFrame();
    wrap.appendChild(ta);
    $inspectorBody.appendChild(wrap);
  }

  if(b.type==='bs_masthead'){
    handled.add('head'); handled.add('pub_name'); handled.add('edition');
    handled.add('volume'); handled.add('issue_note'); handled.add('fit_box');
    const head = b.head || (b.head = {lead:true, cost:1, kicker:'', title:'', deck:'', byline:'', featured:''});
    [['title','Headline'],['deck','Dek'],['byline','Byline'],['kicker','Kicker (section label)']].forEach(([k,label])=>{
      const wrap=document.createElement('div'); wrap.className='field'; wrap.innerHTML=`<label>${esc(label)}</label>`;
      const el = k==='title'||k==='deck' ? document.createElement('textarea') : document.createElement('input');
      if(el.tagName==='TEXTAREA') el.rows=2;
      el.value = head[k]||'';
      el.oninput=()=>{ head[k]=el.value; };
      el.onblur=()=>loadFrame();
      wrap.appendChild(el); $inspectorBody.appendChild(wrap);
    });
  }

  if(b.type==='sem_para'){
    handled.add('sem'); handled.add('crop_x'); handled.add('crop_y');
    drawSemParaEditor(b);
  }

  if(b.type==='vector_shape'){
    handled.add('points'); handled.add('svg_path');
    const ptsWrap=document.createElement('div'); ptsWrap.className='field';
    const curveNote = b.svg_path ? ' -- includes real curve segments (bezier)' : '';
    ptsWrap.innerHTML = `<label>Points (local mm, 0..w / 0..h) -- ${(b.points||[]).length} placed${curveNote}</label>` +
      `<div class="hint">Click to place a straight point; click-and-drag a point to pull a curve handle out of it.</div>`;
    const drawBtn=document.createElement('button'); drawBtn.type='button';
    drawBtn.textContent = (b.shape==='rect'||b.shape==='ellipse') ? 'Switch to Polygon and draw points…' : 'Redraw points on canvas…';
    drawBtn.onclick=()=>{
      if(b.shape==='rect'||b.shape==='ellipse'){ b.shape='polygon'; }
      startShapeDrawing(b);
    };
    ptsWrap.appendChild(drawBtn);
    const clearBtn=document.createElement('button'); clearBtn.type='button'; clearBtn.textContent='Clear points'; clearBtn.style.marginLeft='.3rem';
    clearBtn.onclick=()=>{ b.points=[]; delete b.svg_path; drawInspector(); loadFrame(); };
    ptsWrap.appendChild(clearBtn);
    $inspectorBody.appendChild(ptsWrap);
  }

  if(b.master_ref){
    handled.add('master_ref'); handled.add('overrides');
    const mWrap=document.createElement('div'); mWrap.className='field';
    const overrideKeys = Object.keys(b.overrides||{});
    mWrap.innerHTML = `<label>Inherited from master (${esc(b.master_ref)})</label>` +
      (overrideKeys.length
        ? `<div class="hint">Overridden here: ${overrideKeys.map(esc).join(', ')}</div>`
        : `<div class="hint">No local overrides -- this block still matches its master exactly.</div>`);
    const resetBtn=document.createElement('button'); resetBtn.type='button'; resetBtn.textContent='Reset to master'; resetBtn.style.marginTop='.3rem';
    resetBtn.disabled = overrideKeys.length===0;
    resetBtn.onclick=()=>{ b.overrides = {}; drawInspector(); loadFrame(); };
    mWrap.appendChild(resetBtn);
    $inspectorBody.appendChild(mWrap);
  }

  if(['body','art_title','art_bleed','citations','photo_group','photo_page'].includes(b.type)){
    handled.add('idx');
    const wrap=document.createElement('div'); wrap.className='field';
    wrap.innerHTML=`<label>idx (article position in magazine)</label>`;
    const inp=document.createElement('input'); inp.type='number'; inp.min=1; inp.value=b.idx??1;
    inp.oninput=()=>{ b.idx=Math.max(1,Number(inp.value)||1); loadFrame(); };
    wrap.appendChild(inp); $inspectorBody.appendChild(wrap);
    if('pq_style' in b){
      handled.add('pq_style');
      const wrap2=document.createElement('div'); wrap2.className='field'; wrap2.innerHTML=`<label>pq_style</label>`;
      const sel=document.createElement('select');
      for(let s=1;s<=7;s++){ const o=document.createElement('option'); o.value=s; o.textContent='Style '+s; if(Number(b.pq_style)===s) o.selected=true; sel.appendChild(o); }
      sel.onchange=()=>{ b.pq_style=Number(sel.value); loadFrame(); };
      wrap2.appendChild(sel); $inspectorBody.appendChild(wrap2);
    }
  }

  handled.add('style_font'); handled.add('style_color'); handled.add('style_align');
  const styleHead=document.createElement('div'); styleHead.className='panel-title'; styleHead.style.marginTop='.5rem';
  styleHead.textContent='Print style'; $inspectorBody.appendChild(styleHead);
  const fontWrap=document.createElement('div'); fontWrap.className='field'; fontWrap.innerHTML='<label>Font</label>';
  const fontSel=document.createElement('select');
  [['','(default)'],['playfair','Playfair Display'],['garamond','EB Garamond'],['montserrat','Montserrat'],
   ['cormorant','Cormorant Garamond'],['mono','IBM Plex Mono'],['georgia','Georgia']].forEach(([v,l])=>{
    const o=document.createElement('option'); o.value=v; o.textContent=l; if((b.style_font||'')===v) o.selected=true; fontSel.appendChild(o);
  });
  fontSel.onchange=()=>{ b.style_font=fontSel.value||undefined; loadFrame(); };
  fontWrap.appendChild(fontSel); $inspectorBody.appendChild(fontWrap);

  const colorWrap=document.createElement('div'); colorWrap.className='field'; colorWrap.innerHTML='<label>Text color</label>';
  const colorRow=document.createElement('div'); colorRow.style.cssText='display:flex;gap:.3rem;align-items:center';
  const colorInp=document.createElement('input'); colorInp.type='color'; colorInp.value=/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(b.style_color||'')?b.style_color:'#000000';
  colorInp.oninput=()=>{ b.style_color=colorInp.value; loadFrame(); };
  const colorClear=document.createElement('button'); colorClear.textContent='Clear'; colorClear.type='button';
  colorClear.onclick=()=>{ delete b.style_color; loadFrame(); };
  colorRow.appendChild(colorInp); colorRow.appendChild(colorClear); colorWrap.appendChild(colorRow);
  $inspectorBody.appendChild(colorWrap);

  const alignWrap=document.createElement('div'); alignWrap.className='field'; alignWrap.innerHTML='<label>Alignment</label>';
  const alignSel=document.createElement('select');
  [['','(default)'],['left','Left'],['center','Center'],['right','Right'],['justify','Justify']].forEach(([v,l])=>{
    const o=document.createElement('option'); o.value=v; o.textContent=l; if((b.style_align||'')===v) o.selected=true; alignSel.appendChild(o);
  });
  alignSel.onchange=()=>{ b.style_align=alignSel.value||undefined; loadFrame(); };
  alignWrap.appendChild(alignSel); $inspectorBody.appendChild(alignWrap);

  handled.add('style_letter_spacing'); handled.add('style_line_height');
  handled.add('style_hyphens'); handled.add('columns'); handled.add('style_dropcap');
  const lsWrap=document.createElement('div'); lsWrap.className='field'; lsWrap.innerHTML='<label>Letter spacing (px)</label>';
  const lsInp=document.createElement('input'); lsInp.type='number'; lsInp.step='0.1'; lsInp.value=b.style_letter_spacing??'';
  lsInp.placeholder='(default)';
  lsInp.oninput=()=>{ b.style_letter_spacing = lsInp.value===''?undefined:Number(lsInp.value); loadFrame(); };
  lsWrap.appendChild(lsInp); $inspectorBody.appendChild(lsWrap);

  const lhWrap=document.createElement('div'); lhWrap.className='field'; lhWrap.innerHTML='<label>Line height</label>';
  const lhInp=document.createElement('input'); lhInp.type='number'; lhInp.step='0.05'; lhInp.value=b.style_line_height??'';
  lhInp.placeholder='(default)';
  lhInp.oninput=()=>{ b.style_line_height = lhInp.value===''?undefined:Number(lhInp.value); loadFrame(); };
  lhWrap.appendChild(lhInp); $inspectorBody.appendChild(lhWrap);

  const hyWrap=document.createElement('div'); hyWrap.className='field'; hyWrap.innerHTML='<label>Hyphenation</label>';
  const hySel=document.createElement('select');
  [['','(default)'],['auto','Auto'],['none','Off']].forEach(([v,l])=>{
    const o=document.createElement('option'); o.value=v; o.textContent=l; if((b.style_hyphens||'')===v) o.selected=true; hySel.appendChild(o);
  });
  hySel.onchange=()=>{ b.style_hyphens=hySel.value||undefined; loadFrame(); };
  hyWrap.appendChild(hySel); $inspectorBody.appendChild(hyWrap);

  const colWrap=document.createElement('div'); colWrap.className='field'; colWrap.innerHTML='<label>Columns (within this block)</label>';
  const colSel=document.createElement('select');
  [['','1 (default)'],['2','2'],['3','3']].forEach(([v,l])=>{
    const o=document.createElement('option'); o.value=v; o.textContent=l; if(String(b.columns||'')===v) o.selected=true; colSel.appendChild(o);
  });
  colSel.onchange=()=>{ b.columns = colSel.value?Number(colSel.value):undefined; loadFrame(); };
  colWrap.appendChild(colSel); $inspectorBody.appendChild(colWrap);

  handled.add('fit_text'); handled.add('fit_box');
  const flowHead=document.createElement('div'); flowHead.className='panel-title'; flowHead.style.marginTop='.5rem';
  flowHead.textContent='Text Flow'; $inspectorBody.appendChild(flowHead);
  const fitWrap=document.createElement('div'); fitWrap.className='field';
  fitWrap.innerHTML = '<label>Overflow behavior (resolved on PDF/HTML export)</label>';
  const fitTextLbl=document.createElement('label'); fitTextLbl.style.cssText='display:flex;gap:.3rem;align-items:center;font-weight:normal;text-transform:none';
  const fitTextChk=document.createElement('input'); fitTextChk.type='checkbox'; fitTextChk.checked=!!b.fit_text; fitTextChk.style.width='auto';
  fitTextChk.onchange=()=>{ b.fit_text = fitTextChk.checked||undefined; if(fitTextChk.checked) b.fit_box=undefined; drawInspector(); loadFrame(); };
  fitTextLbl.appendChild(fitTextChk); fitTextLbl.append(' Shrink Text on Overflow');
  fitWrap.appendChild(fitTextLbl);
  const fitBoxLbl=document.createElement('label'); fitBoxLbl.style.cssText='display:flex;gap:.3rem;align-items:center;font-weight:normal;text-transform:none;margin-top:.2rem';
  const fitBoxChk=document.createElement('input'); fitBoxChk.type='checkbox'; fitBoxChk.checked=!!b.fit_box; fitBoxChk.style.width='auto';
  fitBoxChk.onchange=()=>{ b.fit_box = fitBoxChk.checked||undefined; if(fitBoxChk.checked) b.fit_text=undefined; drawInspector(); loadFrame(); };
  fitBoxLbl.appendChild(fitBoxChk); fitBoxLbl.append(' Grow Box to Fit');
  fitWrap.appendChild(fitBoxLbl);
  $inspectorBody.appendChild(fitWrap);

  if(b.type==='sem_para' && b.sem && b.sem.type==='paragraph'){
    const dcWrap=document.createElement('div'); dcWrap.className='field'; dcWrap.innerHTML='<label>Drop cap size (lede paragraphs)</label>';
    const dcSel=document.createElement('select');
    [['','(default)'],['small','Small'],['medium','Medium'],['large','Large']].forEach(([v,l])=>{
      const o=document.createElement('option'); o.value=v; o.textContent=l; if((b.style_dropcap||'')===v) o.selected=true; dcSel.appendChild(o);
    });
    dcSel.onchange=()=>{ b.style_dropcap=dcSel.value||undefined; loadFrame(); };
    dcWrap.appendChild(dcSel); $inspectorBody.appendChild(dcWrap);

    handled.add('link_next');
    const linkWrap=document.createElement('div'); linkWrap.className='field';
    linkWrap.innerHTML='<label>Link to Next Box (overflow text flows here on export)</label>';
    const otherParas = (curPageObj().blocks||[])
      .filter(x=>x.id!==b.id && x.type==='sem_para' && x.sem && x.sem.type==='paragraph');
    const linkSel=document.createElement('select');
    const noneOpt=document.createElement('option'); noneOpt.value=''; noneOpt.textContent='(none)'; linkSel.appendChild(noneOpt);
    otherParas.forEach(x=>{ const o=document.createElement('option'); o.value=x.id;
      o.textContent=(plainText(x.sem.html)||'(empty)').slice(0,30); if(b.link_next===x.id) o.selected=true; linkSel.appendChild(o); });
    linkSel.onchange=()=>{ b.link_next = linkSel.value||undefined; loadFrame(); };
    linkWrap.appendChild(linkSel); $inspectorBody.appendChild(linkWrap);

    const chain = chainContaining(b.id);
    const chainWrap=document.createElement('div'); chainWrap.className='field';
    if(chain){
      const idx = chain.frame_ids.indexOf(b.id);
      chainWrap.innerHTML = `<label>Frame chain: position ${idx+1} of ${chain.frame_ids.length}</label>`;
      const row=document.createElement('div'); row.style.cssText='display:flex;gap:.3rem';
      const upBtn=document.createElement('button'); upBtn.type='button'; upBtn.textContent='↑ Earlier'; upBtn.disabled=idx===0;
      upBtn.onclick=()=>{ moveInChain(b.id,-1); drawInspector(); loadFrame(); };
      const dnBtn=document.createElement('button'); dnBtn.type='button'; dnBtn.textContent='↓ Later'; dnBtn.disabled=idx===chain.frame_ids.length-1;
      dnBtn.onclick=()=>{ moveInChain(b.id,1); drawInspector(); loadFrame(); };
      const breakBtn=document.createElement('button'); breakBtn.type='button'; breakBtn.textContent='Remove from chain';
      breakBtn.onclick=()=>{ removeFromChain(b.id); drawInspector(); loadFrame(); };
      row.appendChild(upBtn); row.appendChild(dnBtn); row.appendChild(breakBtn);
      chainWrap.appendChild(row);
      $inspectorBody.appendChild(chainWrap);
    }
  }

  const dupBtn=document.createElement('button'); dupBtn.textContent='Duplicate block'; dupBtn.style.marginBottom='.5rem';
  dupBtn.onclick=()=>{
    const copy = JSON.parse(JSON.stringify(b));
    copy.id = Math.random().toString(16).slice(2,10);
    copy.x = b.x + 6; copy.y = b.y + 6;
    curPageObj().blocks.push(copy);
    selectedIds = new Set([copy.id]); drawPages(); drawLayers(); loadFrame();
  };
  $inspectorBody.appendChild(dupBtn);

  Object.keys(b).forEach(k=>{
    if(handled.has(k)) return;
    const wrap=document.createElement('div'); wrap.className='field';
    wrap.innerHTML=`<label>${esc(k)}</label>`;
    const val = b[k];
    if(typeof val==='object'){
      wrap.innerHTML += `<div class="hint">${esc(JSON.stringify(val)).slice(0,80)}</div>`;
    } else {
      const inp=document.createElement('input'); inp.value=val??'';
      inp.oninput=()=>{ b[k] = (typeof val==='number') ? Number(inp.value) : inp.value; loadFrame(); };
      wrap.appendChild(inp);
    }
    $inspectorBody.appendChild(wrap);
  });

  const lockBtn=document.createElement('button'); lockBtn.textContent = b.locked ? 'Unlock block' : 'Lock block';
  lockBtn.style.marginTop='.5rem'; lockBtn.style.marginRight='.3rem';
  lockBtn.onclick=()=>{ b.locked=!b.locked; drawLayers(); drawInspector(); };
  $inspectorBody.appendChild(lockBtn);

  const layerWrap=document.createElement('div'); layerWrap.className='field'; layerWrap.innerHTML='<label>Layer</label>';
  const layerSel=document.createElement('select');
  docLayers().forEach(l=>{ const o=document.createElement('option'); o.value=l.name; o.textContent=l.name;
    if((b.layer||'Default')===l.name) o.selected=true; layerSel.appendChild(o); });
  layerSel.onchange=()=>{ b.layer=layerSel.value; loadFrame(); };
  layerWrap.appendChild(layerSel); $inspectorBody.appendChild(layerWrap);

  const delBtn=document.createElement('button'); delBtn.textContent='Delete block'; delBtn.style.marginTop='.5rem';
  delBtn.disabled = isEffectivelyLocked(b);
  delBtn.onclick=()=>{ if(isEffectivelyLocked(b)) return; curPageObj().blocks = curPageObj().blocks.filter(x=>x.id!==b.id);
    selectedIds=new Set(); drawPages(); drawLayers(); drawInspector(); loadFrame(); };
  $inspectorBody.appendChild(delBtn);
}

async function saveProject(){
  syncAllMasterOverrides();
  $status.textContent='Saving...';
  try{ await j(`/api/projects/${project.id}`,{method:'PUT',body:JSON.stringify({layout:project.layout})}); $status.textContent='Saved'; }
  catch(e){ $status.textContent='Failed: '+e.message; }
  setTimeout(()=>$status.textContent='',1400);
}
boot();
</script>
</body></html>'''


def _cli_ok(payload):
    payload = dict(payload)
    payload['success'] = True
    print(json.dumps(payload))
    return 0


def _cli_error(msg):
    print(json.dumps({'success': False, 'error': str(msg)}))
    return 1


def _load_data_file(path):
    if not path:
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _cli_generate(args):
    data = _load_data_file(args.data_file)
    try:
        if args.kind == 'magazine':
            articles = data.get('articles')
            article_ids = [a['id'] for a in articles] if articles else args.article_id
            if not article_ids:
                return _cli_error('magazine generation needs --article-id or --data-file with articles')
            key = ','.join(str(x) for x in (article_ids if isinstance(article_ids, list) else [article_ids]))
            existed = eng._find_existing('magazine', key)
            pid = eng.create_magazine_project(
                article_ids, articles=articles, title=args.title,
                creator=args.creator or '', description=args.description or '',
                regenerate=args.regenerate)
        elif args.kind == 'broadsheet':
            existed = eng._find_existing('broadsheet', args.ym)
            pid = eng.create_broadsheet_project(args.ym, articles=data.get('articles'),
                                                regenerate=args.regenerate,
                                                enhancement=data.get('enhancement'))
        elif args.kind == 'special':
            if not args.blank_pages and not (args.article_id or args.entry_id
                                             or (args.date_from and args.date_to)):
                return _cli_error('a special broadsheet needs content (--article-id / --entry-id / '
                                  '--from with --to) or --blank-pages N for a free issue')
            existed = eng._find_existing(eng.SPECIAL_BROADSHEET_KIND, args.key)
            pid = eng.create_special_broadsheet_project(
                args.key, args.label, article_ids=args.article_id, entry_ids=args.entry_id,
                date_from=args.date_from, date_to=args.date_to,
                blank_pages=args.blank_pages, seed_month=args.seed_month,
                regenerate=args.regenerate, enhancement=data.get('enhancement'))
        elif args.kind == 'gazette':
            existed = eng._find_existing('gazette', args.article_id)
            pid = eng.create_gazette_project(args.article_id, art=data.get('art'),
                                             regenerate=args.regenerate,
                                             enhancement=data.get('enhancement'))
        elif args.kind == 'booklet':
            if 'articles' not in data or 'col_row' not in data:
                return _cli_error("booklet generation needs --data-file with 'articles' + "
                                  "'col_row' -- dtp_engine doesn't derive column-entry-to-"
                                  "article mapping itself, only app.py's route does")
            label = args.label or ''
            source_ref = f'{args.column_id}:{args.period}:{label}'
            existed = eng._find_existing('booklet', source_ref)
            pid = eng.create_booklet_project(args.column_id, data['articles'], data['col_row'],
                                             period=args.period, label=label,
                                             regenerate=args.regenerate,
                                             enhancement=data.get('enhancement'))
        else:
            return _cli_error(f'unknown generate kind: {args.kind}')
    except Exception as e:
        return _cli_error(e)
    if pid is None:
        return _cli_error('generation failed -- article/month/column not found, or no content')
    return _cli_ok({'project_id': pid, 'reopened': bool(existed) and not args.regenerate})


def _cli_render(args):
    proj = eng.get_project(args.project_id)
    if not proj:
        return _cli_error('Project not found')
    try:
        if args.format == 'pdf':
            content, err = eng.render_pdf(proj['layout'])
            if err:
                return _cli_error(err)
        else:
            content = eng.render_html(proj['layout'], title=proj['name'], kind=proj['kind']).encode('utf-8')
        with open(args.out, 'wb') as f:
            f.write(content)
    except Exception as e:
        return _cli_error(e)
    return _cli_ok({'out': args.out, 'bytes': len(content)})


def _cli_publish(args):
    try:
        result = eng.publish_project(args.project_id, title=args.title, output=args.format,
                                     sig=getattr(args, 'sig', None),
                                     tags=_split_tags(getattr(args, 'tags', None)))
    except Exception as e:
        return _cli_error(e)
    if 'error' in result:
        return _cli_error(result['error'])
    result.pop('content', None)
    result.pop('mimetype', None)
    return _cli_ok(result)


def _split_tags(raw):
    if raw is None:
        return None
    return [t.strip() for t in str(raw).split(',') if t.strip()]


def _cli_import_pdf(args):
    try:
        with open(args.file, 'rb') as f:
            content = f.read()
    except OSError as e:
        return _cli_error(e)
    result = eng.import_pdf(content, os.path.basename(args.file), title=args.title,
                            tags=_split_tags(args.tags) or [],
                            description=args.description or '', featured=args.featured)
    if 'error' in result:
        return _cli_error(result['error'])
    return _cli_ok(result)


def _cli_replace_pdf(args):
    try:
        with open(args.file, 'rb') as f:
            content = f.read()
    except OSError as e:
        return _cli_error(e)
    result = eng.replace_publication_file(args.publication_id, content,
                                          os.path.basename(args.file))
    if 'error' in result:
        return _cli_error(result['error'])
    return _cli_ok(result)


def _cli_feature(args):
    result = eng.set_publication_flags(
        args.publication_id,
        featured=(None if args.featured == args.unfeatured else args.featured),
        tags=_split_tags(args.tags))
    if 'error' in result:
        return _cli_error(result['error'])
    return _cli_ok(result)


def _build_cli_parser():
    parser = argparse.ArgumentParser(prog='dtp.py', description='Voice Express DTP -- CLI')
    sub = parser.add_subparsers(dest='command')

    gen = sub.add_parser('generate', help='Create/refresh a dtp_projects layout')
    gen_sub = gen.add_subparsers(dest='kind', required=True)

    mag = gen_sub.add_parser('magazine')
    mag.add_argument('--article-id', type=int, action='append',
                      help='repeatable for a multi-article collection issue; optional if --data-file supplies articles')
    mag.add_argument('--title')
    mag.add_argument('--creator', default='')
    mag.add_argument('--description', default='')
    mag.add_argument('--regenerate', action='store_true')
    mag.add_argument('--data-file')

    bs = gen_sub.add_parser('broadsheet')
    bs.add_argument('--ym', required=True)
    bs.add_argument('--regenerate', action='store_true')
    bs.add_argument('--data-file')

    sp = gen_sub.add_parser('special', help='A special broadsheet: an issue that is not a calendar '
                                            'month. Either hand-picked/date-ranged content, or '
                                            '--blank-pages N for a free issue to lay out by hand.')
    sp.add_argument('--key', required=True, help='slug identifying this special (its project source_ref)')
    sp.add_argument('--label', help='masthead edition line, e.g. "Special Issue - Floods"')
    sp.add_argument('--article-id', type=int, action='append',
                    help='repeatable; running order is the order given')
    sp.add_argument('--entry-id', type=int, action='append',
                    help='repeatable; hand-picked published column entries')
    sp.add_argument('--from', dest='date_from', help='YYYY-MM-DD, inclusive (use with --to)')
    sp.add_argument('--to', dest='date_to', help='YYYY-MM-DD, inclusive (use with --from)')
    sp.add_argument('--blank-pages', type=int, default=0,
                    help='N>0 builds a FREE issue: N pages of empty threaded column frames, no content')
    sp.add_argument('--seed-month', help="YYYY-MM anchoring the word pool/back cover; defaults to --from's month")
    sp.add_argument('--regenerate', action='store_true')
    sp.add_argument('--data-file')

    gz = gen_sub.add_parser('gazette')
    gz.add_argument('--article-id', type=int, required=True)
    gz.add_argument('--regenerate', action='store_true')
    gz.add_argument('--data-file')

    bk = gen_sub.add_parser('booklet')
    bk.add_argument('--column-id', type=int, required=True)
    bk.add_argument('--period', default='all', choices=['week', 'month', 'year', 'all'])
    bk.add_argument('--label', default='')
    bk.add_argument('--regenerate', action='store_true')
    bk.add_argument('--data-file')

    rend = sub.add_parser('render', help='Render a project to a PDF/HTML file')
    rend.add_argument('--project-id', type=int, required=True)
    rend.add_argument('--format', choices=['pdf', 'html'], default='pdf')
    rend.add_argument('--out', required=True)

    pub = sub.add_parser('publish', help='Render + save to the Newsstand publications library')
    pub.add_argument('--project-id', type=int, required=True)
    pub.add_argument('--title')
    pub.add_argument('--format', choices=['pdf', 'html'], default='pdf')
    pub.add_argument('--sig', help="source fingerprint recorded on the row, so a later "
                                   "request can tell whether this artifact is still current")
    pub.add_argument('--tags', help='comma-separated tags for the Newsstand shelf. Omit to '
                                    'keep whatever tags the row already carries.')

    imp = sub.add_parser('import-pdf',
                         help='Shelve an already-finished PDF as a frozen publication')
    imp.add_argument('--file', required=True, help='the PDF to shelve')
    imp.add_argument('--title', help='defaults to the filename')
    imp.add_argument('--tags', help='comma-separated tags for the Newsstand shelf')
    imp.add_argument('--description', help='blurb shown beside it on the shelf')
    imp.add_argument('--featured', action='store_true', help='mark it featured (never pruned)')

    rep = sub.add_parser('replace-file',
                         help="Swap a publication's file, keeping its shelf entry. The only "
                              'way to edit a frozen PDF.')
    rep.add_argument('--publication-id', type=int, required=True)
    rep.add_argument('--file', required=True, help='the replacement, same extension')

    feat = sub.add_parser('feature', help='Star/unstar a publication, or retag it')
    feat.add_argument('--publication-id', type=int, required=True)
    feat.add_argument('--featured', action='store_true', help='mark featured')
    feat.add_argument('--unfeatured', action='store_true', help='clear featured')
    feat.add_argument('--tags', help='comma-separated tags (replaces the existing set)')

    st = sub.add_parser('status', help='Is the published artifact for a source still current?')
    st.add_argument('--kind', required=True)
    st.add_argument('--source-ref', required=True)
    st.add_argument('--ext', required=True)
    st.add_argument('--sig')

    op = sub.add_parser('open-publication',
                        help='Get (creating if needed) the dtp project that edits a publication')
    op.add_argument('--publication-id', type=int, required=True)
    op.add_argument('--regenerate', action='store_true')

    sub.add_parser('unify', help='One-off: register every artifact into the publications '
                                 'table and collapse duplicate copies onto canonical paths')

    dd = sub.add_parser('dedupe-projects',
                        help='Collapse historical duplicate dtp_projects rows for one source')
    dd.add_argument('--apply', action='store_true', help='actually delete (default: dry run)')

    return parser


def _cli_status(args):
    try:
        return _cli_ok(eng.artifact_status(args.kind, args.source_ref, args.ext, sig=args.sig))
    except Exception as e:
        return _cli_error(e)


def _cli_open_publication(args):
    try:
        result = eng.project_for_publication(args.publication_id, regenerate=args.regenerate)
    except Exception as e:
        return _cli_error(e)
    if 'error' in result:
        return _cli_error(result['error'])
    return _cli_ok(result)


def _cli_unify(args):
    import ve_library
    db = eng.get_db()
    try:
        added = ve_library.register_all(db, verbose=True)
        merged, moved = ve_library.reconcile(db)
        total = db.execute('SELECT COUNT(*) FROM publications').fetchone()[0]
    except Exception as e:
        return _cli_error(e)
    finally:
        db.close()
    return _cli_ok({'registered': added, 'merged': merged, 'moved': moved, 'publications': total})


def _cli_dedupe_projects(args):
    db = eng.get_db()
    try:
        rows = db.execute('SELECT id, kind, source_ref, updated_at FROM dtp_projects '
                          'WHERE source_ref IS NOT NULL '
                          'ORDER BY kind, source_ref, updated_at DESC, id DESC').fetchall()
        keep, drop = {}, []
        for r in rows:
            k = (r['kind'], r['source_ref'])
            if k in keep:
                drop.append(r['id'])
            else:
                keep[k] = r['id']
        linked = set()
        for p in db.execute("SELECT metadata FROM publications "
                            "WHERE metadata LIKE '%dtp_project_id%'").fetchall():
            try:
                v = (json.loads(p['metadata'] or '{}') or {}).get('dtp_project_id')
                if v:
                    linked.add(int(v))
            except Exception:
                pass
        drop = [d for d in drop if d not in linked]
        if args.apply and drop:
            db.executemany('DELETE FROM dtp_projects WHERE id=?', [(d,) for d in drop])
            db.commit()
    except Exception as e:
        return _cli_error(e)
    finally:
        db.close()
    return _cli_ok({'kept': len(keep), 'droppable': len(drop),
                    'dropped': len(drop) if args.apply else 0,
                    'applied': bool(args.apply), 'ids': drop[:50]})


def _cli_main(argv):
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    if args.command == 'generate':
        return _cli_generate(args)
    if args.command == 'render':
        return _cli_render(args)
    if args.command == 'publish':
        return _cli_publish(args)
    if args.command == 'import-pdf':
        return _cli_import_pdf(args)
    if args.command == 'replace-file':
        return _cli_replace_pdf(args)
    if args.command == 'feature':
        return _cli_feature(args)
    if args.command == 'status':
        return _cli_status(args)
    if args.command == 'open-publication':
        return _cli_open_publication(args)
    if args.command == 'unify':
        return _cli_unify(args)
    if args.command == 'dedupe-projects':
        return _cli_dedupe_projects(args)
    parser.print_help()
    return 1


if __name__ == '__main__':
    eng.ensure_schema()
    if len(sys.argv) > 1:
        sys.exit(_cli_main(sys.argv[1:]))
    port = int(os.environ.get('DTP_PORT', 8797))
    print(f'DTP -> http://localhost:{port}')
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)
