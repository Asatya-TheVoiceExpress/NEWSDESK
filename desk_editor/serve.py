#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import html as html_mod
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

from flask import (Flask, jsonify, request, send_file, send_from_directory,
                   abort)

import ve_semantic
from helpers import slugify, unique_slug, reading_time, compose_byline

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
CONFIG_JSON = os.path.join(ROOT, 'broadsheet_config.json')

sys.path.insert(0, ROOT)
try:
    from pub_icons import generate_icon as _gen_icon
except ImportError:
    _gen_icon = None
try:
    import ve_library as _ve_library
except ImportError:
    _ve_library = None
import ve.db as _ve_db
import ve.paths as _ve_paths
import ve.tags as _ve_tags
import ve.repo as _ve_repo


def _load_config():
    with open(os.path.join(BASE, 'config.json'), encoding='utf-8') as fh:
        cfg = json.load(fh)
    for key in ('db_path', 'media_path', 'app_css', 'fonts_dir',
                'previews_dir', 'thumbs_dir'):
        p = cfg.get(key)
        if p and not os.path.isabs(p):
            cfg[key] = os.path.normpath(os.path.join(BASE, p))
    return cfg


CFG = _load_config()
DB_PATH = _ve_paths.db_path(BASE)
MEDIA_PATH = _ve_paths.uploads_path(BASE)
PREVIEWS_DIR = CFG['previews_dir']
THUMBS_DIR = CFG['thumbs_dir']
PUBLICATIONS_PATH = _ve_paths.publications_path(BASE)
os.makedirs(MEDIA_PATH, exist_ok=True)
os.makedirs(PREVIEWS_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)
os.makedirs(PUBLICATIONS_PATH, exist_ok=True)

ARTIFACT_MEDIA_PATH = _ve_paths.media_path(BASE)
ARTIFACT_DIRS = [PUBLICATIONS_PATH, ARTIFACT_MEDIA_PATH]


def publication_path(filename):
    if not filename:
        return None
    for d in ARTIFACT_DIRS:
        fp = os.path.join(d, filename)
        if os.path.exists(fp):
            return fp
    return None

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif'}
IMAGE_EXT = ALLOWED_EXT | {'bmp', 'tif', 'tiff'}

app = Flask(__name__, static_folder=None)


def get_db():
    return _ve_db.connect(DB_PATH)


def ensure_schema():
    db = get_db()
    _ve_db.migrate(db)
    db.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _alt_lookup(db):
    rows = db.execute('SELECT filename, original_name FROM images').fetchall()
    by_file = {r['filename']: (r['original_name'] or '') for r in rows}
    def lookup(src):
        return by_file.get((src or '').rsplit('/', 1)[-1], '')
    return lookup


def normalize_body(db, html):
    return ve_semantic.normalize(html or '', alt_lookup=_alt_lookup(db))


def set_article_authors(db, aid, authors, fallback_author_id=None):
    db.execute('DELETE FROM article_authors WHERE article_id=?', [aid])
    clean = []
    for i, a in enumerate(authors or []):
        try:
            auid = int(a.get('author_id'))
        except (TypeError, ValueError):
            continue
        clean.append((auid, (a.get('role') or 'author'), int(a.get('sort_order', i) or i)))
    if not clean and fallback_author_id:
        try:
            clean = [(int(fallback_author_id), 'author', 0)]
        except (TypeError, ValueError):
            clean = []
    for auid, role, order in clean:
        db.execute('INSERT OR IGNORE INTO article_authors (article_id,author_id,role,sort_order) '
                   'VALUES (?,?,?,?)', [aid, auid, role, order])
    primary = next((auid for auid, role, _ in clean if role in ('author', 'co-author')),
                   clean[0][0] if clean else None)
    db.execute('UPDATE articles SET author_id=? WHERE id=?', [primary, aid])


def authors_of(db, aid):
    rows = db.execute('''SELECT aa.author_id AS author_id, au.name, aa.role, aa.sort_order
        FROM article_authors aa JOIN authors au ON au.id=aa.author_id
        WHERE aa.article_id=? ORDER BY aa.sort_order, aa.author_id''', [aid]).fetchall()
    return [dict(r) for r in rows]


def record_history(db, aid, action, language=None):
    try:
        db.execute('INSERT INTO article_history (article_id,user_id,display_name,action,language) '
                   'VALUES (?,?,?,?,?)', [aid, None, 'desk editor', action, language])
    except Exception as e:
        print(f'[history] {e}')


VERSION_EVERY_SECONDS = 600


def record_version(db, aid, message='edited', force=True):
    """Snapshot the article. Autosaves (force=False) snapshot at most every 10 minutes."""
    try:
        if not force:
            last = db.execute("SELECT (julianday('now') - julianday(created_at)) * 86400 AS age "
                              'FROM article_versions WHERE article_id=? ORDER BY id DESC LIMIT 1',
                              [aid]).fetchone()
            if last and last['age'] is not None and last['age'] < VERSION_EVERY_SECONDS:
                return
        row = db.execute('SELECT title,subtitle,excerpt,seo_description,seo_keywords,content,'
                         'byline,status,featured_image,category_id,section_id,published_at '
                         'FROM articles WHERE id=?', [aid]).fetchone()
        if not row:
            return
        snap = dict(row)
        snap['_authors'] = [{'author_id': a['author_id'], 'role': a['role'], 'sort_order': a['sort_order']}
                            for a in authors_of(db, aid)]
        snap['_tag_ids'] = [r['tag_id'] for r in db.execute(
            'SELECT tag_id FROM article_tags WHERE article_id=?', [aid]).fetchall()]
        snap['_citations'] = [dict(r) for r in db.execute(
            'SELECT reference_text,url,author,published_date FROM citations '
            'WHERE article_id=? ORDER BY citation_number', [aid]).fetchall()]
        db.execute('INSERT INTO article_versions (article_id,user_id,display_name,message,snapshot) '
                   'VALUES (?,?,?,?,?)',
                   [aid, None, 'desk editor', message, json.dumps(snap, ensure_ascii=False)])
    except Exception as e:
        print(f'[version] {e}')


def _write_article(db, data, aid=None):
    ex = db.execute('SELECT * FROM articles WHERE id=?', [aid]).fetchone() if aid else None
    title = (data.get('title') or (ex['title'] if ex else '') or '').strip() or 'Untitled draft'
    content = normalize_body(db, data.get('content', ex['content'] if ex else ''))
    status = data.get('status', ex['status'] if ex else 'draft')
    now = now_iso()
    pub_at = data.get('published_at') or (ex['published_at'] if ex else None)
    if status == 'published' and not pub_at:
        pub_at = now
    fields = dict(
        title=title,
        subtitle=data.get('subtitle', ex['subtitle'] if ex else '') or '',
        content=content,
        excerpt=data.get('excerpt', ex['excerpt'] if ex else '') or '',
        seo_description=data.get('seo_description', ex['seo_description'] if ex else '') or '',
        seo_keywords=data.get('seo_keywords', ex['seo_keywords'] if ex else '') or '',
        byline=data.get('byline', ex['byline'] if ex else '') or '',
        category_id=data.get('category_id', ex['category_id'] if ex else None) or None,
        section_id=data.get('section_id', ex['section_id'] if ex else None) or None,
        status=status,
        language=data.get('language', ex['language'] if ex else 'en') or 'en',
        featured_image=data.get('featured_image', ex['featured_image'] if ex else '') or '',
        latitude=data.get('latitude', ex['latitude'] if ex else None) or None,
        longitude=data.get('longitude', ex['longitude'] if ex else None) or None,
        location_name=data.get('location_name', ex['location_name'] if ex else '') or '',
        published_at=pub_at,
        reading_time=reading_time(content),
        is_featured=1 if data.get('is_featured', ex['is_featured'] if ex else 0) else 0,
        series_id=data.get('series_id', ex['series_id'] if ex else None) or None,
        series_order=data.get('series_order', ex['series_order'] if ex else 0) or 0,
        updated_at=now,
    )
    prov = (data.get('slug') or '').strip()
    if ex:
        fields['slug'] = unique_slug(db, slugify(prov), exclude_id=aid) if prov else ex['slug']
        cols = ', '.join(f'{k}=?' for k in fields)
        db.execute(f'UPDATE articles SET {cols} WHERE id=?', list(fields.values()) + [aid])
        slug = fields['slug']
    else:
        slug = unique_slug(db, slugify(prov or title))
        fields['slug'] = slug
        fields['created_at'] = now
        cols = ', '.join(fields)
        ph = ', '.join('?' * len(fields))
        db.execute(f'INSERT INTO articles ({cols}) VALUES ({ph})', list(fields.values()))
        aid = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    if 'authors' in data or not ex:
        set_article_authors(db, aid, data.get('authors'), data.get('author_id'))
    if 'tag_ids' in data:
        db.execute('DELETE FROM article_tags WHERE article_id=?', [aid])
        for tid in (data.get('tag_ids') or []):
            try:
                db.execute('INSERT OR IGNORE INTO article_tags VALUES (?,?)', [aid, tid])
            except Exception:
                pass
    if 'citations' in data:
        db.execute('DELETE FROM citations WHERE article_id=?', [aid])
        for i, c in enumerate(data.get('citations') or [], 1):
            db.execute('INSERT INTO citations (article_id,reference_text,url,author,published_date,citation_number) '
                       'VALUES (?,?,?,?,?,?)',
                       [aid, c.get('reference_text', ''), c.get('url', ''), c.get('author', ''),
                        c.get('published_date', ''), i])
    record_version(db, aid, (data.get('version_message') or 'saved from desk editor')[:200],
                   force=bool(data.get('version')) or not ex)
    record_history(db, aid, 'created' if not ex else 'edited')
    return aid, slug


def render_preview(db, aid):
    art = db.execute('SELECT * FROM articles WHERE id=?', [aid]).fetchone()
    if not art:
        return None
    authors = authors_of(db, aid)
    byline = art['byline'] or compose_byline(authors)
    esc = lambda v: html_mod.escape(v or '')
    title, sub, byline = esc(art['title']), esc(art['subtitle']), esc(byline)
    html = f"""<!doctype html><html lang="{esc(art['language']) or 'en'}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="/vendor/app.css">
<style>body{{margin:0;background:var(--paper,#f7f6f2)}}
.de-preview{{max-width:46rem;margin:0 auto;padding:3rem 1.5rem}}
.de-preview h1{{font-family:var(--fh);font-size:2.6rem;line-height:1.06;margin:0 0 .3em}}
.de-preview .de-sub{{font-family:var(--fh);font-size:1.3rem;color:var(--g700);margin:0 0 .6em}}
.de-preview .de-byline{{font-family:var(--fm);text-transform:uppercase;letter-spacing:.08em;
  font-size:.72rem;color:var(--g600);border-top:1px solid currentColor;padding-top:.6em;margin-bottom:2em}}</style>
</head><body><article class="de-preview art-content">
<h1>{title}</h1>{f'<p class="de-sub">{sub}</p>' if sub else ''}
{f'<p class="de-byline">{byline}</p>' if byline else ''}
{art['content'] or ''}
</article></body></html>"""
    out = os.path.join(PREVIEWS_DIR, f'{aid}.html')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    db.execute('INSERT INTO editor_projects (article_id,preview_path,updated_at) VALUES (?,?,?) '
               'ON CONFLICT(article_id) DO UPDATE SET preview_path=excluded.preview_path,'
               'updated_at=excluded.updated_at', [aid, out, now_iso()])
    db.commit()
    return out


@app.route('/')
def index():
    return send_from_directory(os.path.join(BASE, 'web'), 'index.html')


@app.route('/src/<path:p>')
def src(p):
    return send_from_directory(os.path.join(BASE, 'web', 'src'), p)


@app.route('/styles/<path:p>')
def styles(p):
    return send_from_directory(os.path.join(BASE, 'web', 'styles'), p)


@app.route('/vendor/app.css')
def vendor_css():
    return send_file(CFG['app_css'], mimetype='text/css')


@app.route('/fonts/<path:p>')
def fonts(p):
    return send_from_directory(CFG['fonts_dir'], p)


@app.route('/vendor/logo')
def vendor_logo():
    return send_file(CFG.get('logo') or os.path.join(CFG['fonts_dir'], '..', 'logo-ve.png'))


@app.route('/static/uploads/<path:p>')
def uploads(p):
    return send_from_directory(MEDIA_PATH, p)


@app.route('/static/publications/<path:p>')
def publications_static(p):
    fp = publication_path(p)
    if not fp:
        return jsonify({'error': 'Not found'}), 404
    return send_from_directory(os.path.dirname(fp), os.path.basename(fp))


@app.route('/static/media/<path:p>')
def artifact_media_static(p):
    return send_from_directory(ARTIFACT_MEDIA_PATH, p)


@app.route('/previews/<path:p>')
def previews(p):
    return send_from_directory(PREVIEWS_DIR, p)


@app.route('/api/lookups')
def lookups():
    db = get_db()
    try:
        def rows(sql):
            return [dict(r) for r in db.execute(sql).fetchall()]
        return jsonify({
            'authors': rows('SELECT id,name,role FROM authors ORDER BY name'),
            'categories': rows('SELECT id,name,slug FROM categories ORDER BY name'),
            'sections': rows('SELECT id,name,slug FROM sections ORDER BY sort_order,name'),
            'tags': rows('SELECT id,name,slug FROM tags ORDER BY name'),
            'series': rows('SELECT id,title,slug FROM article_series ORDER BY title'),
            'roles': ['author', 'co-author', 'photographer', 'illustrator',
                      'translator', 'editor', 'post-editor', 'typesetter',
                      'as-told-to', 'reporting'],
            'prose_roles': sorted(ve_semantic.PROSE_ROLES),
            'default_author_id': CFG.get('default_author_id'),
        })
    finally:
        db.close()


@app.route('/api/drafts')
def drafts():
    db = get_db()
    try:
        rows = db.execute('''SELECT a.id,a.title,a.subtitle,a.status,a.featured_image,a.updated_at,
            ep.preview_path FROM articles a LEFT JOIN editor_projects ep ON ep.article_id=a.id
            ORDER BY a.updated_at DESC LIMIT 200''').fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['has_preview'] = bool(r['preview_path'] and os.path.exists(r['preview_path']))
            out.append(d)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/articles/<int:aid>')
def get_article(aid):
    db = get_db()
    try:
        a = db.execute('SELECT * FROM articles WHERE id=?', [aid]).fetchone()
        if not a:
            return jsonify({'error': 'Not found'}), 404
        d = dict(a)
        d['authors'] = authors_of(db, aid)
        d['tag_ids'] = [r['tag_id'] for r in db.execute(
            'SELECT tag_id FROM article_tags WHERE article_id=?', [aid]).fetchall()]
        d['citations'] = [dict(r) for r in db.execute(
            'SELECT reference_text,url,author,published_date,citation_number '
            'FROM citations WHERE article_id=? ORDER BY citation_number', [aid]).fetchall()]
        proj = db.execute('SELECT folder_mounts,layout FROM editor_projects WHERE article_id=?',
                          [aid]).fetchone()
        d['folder_mounts'] = json.loads(proj['folder_mounts']) if proj else []
        d['layout'] = json.loads(proj['layout']) if proj else {}
        return jsonify(d)
    finally:
        db.close()


@app.route('/api/articles', methods=['POST'])
def create_article():
    db = get_db()
    try:
        aid, slug = _write_article(db, request.json or {})
        db.commit()
        return jsonify({'id': aid, 'slug': slug}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/articles/<int:aid>', methods=['PUT'])
def update_article(aid):
    db = get_db()
    try:
        if not db.execute('SELECT 1 FROM articles WHERE id=?', [aid]).fetchone():
            return jsonify({'error': 'Not found'}), 404
        _write_article(db, request.json or {}, aid)
        db.commit()
        return jsonify({'success': True, 'id': aid})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/preview', methods=['POST'])
def article_preview(aid):
    db = get_db()
    try:
        out = render_preview(db, aid)
        if not out:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'url': f'/previews/{aid}.html'})
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/versions')
def versions(aid):
    db = get_db()
    try:
        rows = db.execute('SELECT id,display_name,message,created_at,length(snapshot) AS size '
                          'FROM article_versions WHERE article_id=? ORDER BY id DESC', [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/versions/<int:vid>/restore', methods=['POST'])
def restore_version(aid, vid):
    db = get_db()
    try:
        r = db.execute('SELECT snapshot FROM article_versions WHERE id=? AND article_id=?',
                       [vid, aid]).fetchone()
        if not r:
            return jsonify({'error': 'Not found'}), 404
        snap = json.loads(r['snapshot'])
        record_version(db, aid, f'before restoring v{vid}')
        cols = [k for k in snap if k != 'id' and not k.startswith('_')]
        db.execute(f"UPDATE articles SET {', '.join(f'{c}=?' for c in cols)}, updated_at=? WHERE id=?",
                   [snap[c] for c in cols] + [now_iso(), aid])
        if '_authors' in snap:
            set_article_authors(db, aid, snap['_authors'])
        if '_tag_ids' in snap:
            db.execute('DELETE FROM article_tags WHERE article_id=?', [aid])
            for tid in snap['_tag_ids']:
                db.execute('INSERT OR IGNORE INTO article_tags VALUES (?,?)', [aid, tid])
        if '_citations' in snap:
            db.execute('DELETE FROM citations WHERE article_id=?', [aid])
            for i, c in enumerate(snap['_citations'], 1):
                db.execute('INSERT INTO citations (article_id,reference_text,url,author,published_date,citation_number) '
                           'VALUES (?,?,?,?,?,?)', [aid, c.get('reference_text', ''), c.get('url', ''),
                                                    c.get('author', ''), c.get('published_date', ''), i])
        record_version(db, aid, f'restored v{vid}')
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


SUPPORTED_TRANS_LANGS = {'hi', 'fr', 'es', 'ar', 'zh', 'de'}
LANG_MM_CODE = {'en': 'en', 'hi': 'hi', 'fr': 'fr', 'es': 'es', 'ar': 'ar', 'zh': 'zh-CN', 'de': 'de'}


@app.route('/api/articles/<int:aid>/translations')
def translations_list(aid):
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM translations WHERE article_id=? ORDER BY language', [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/translations', methods=['POST'])
def translation_save(aid):
    db = get_db()
    try:
        data = request.json or {}
        lang = (data.get('language') or '').strip()
        if not lang:
            return jsonify({'error': 'language required'}), 400
        art = db.execute('SELECT id FROM articles WHERE id=?', [aid]).fetchone()
        if not art:
            return jsonify({'error': 'Article not found'}), 404
        ex = db.execute('SELECT id FROM translations WHERE article_id=? AND language=?', [aid, lang]).fetchone()
        if ex:
            db.execute('UPDATE translations SET title=?,content=?,excerpt=?,translator_name=? '
                       'WHERE article_id=? AND language=?',
                       [data.get('title', ''), data.get('content', ''), data.get('excerpt', ''),
                        'desk editor', aid, lang])
        else:
            db.execute('INSERT INTO translations (article_id,language,title,content,excerpt,translator_name) '
                       'VALUES (?,?,?,?,?,?)',
                       [aid, lang, data.get('title', ''), data.get('content', ''), data.get('excerpt', ''),
                        'desk editor'])
        record_history(db, aid, 'translated', lang)
        db.commit()
        row = db.execute('SELECT * FROM translations WHERE article_id=? AND language=?', [aid, lang]).fetchone()
        return jsonify(dict(row))
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/translation/<lang>', methods=['DELETE'])
def translation_delete(aid, lang):
    db = get_db()
    try:
        db.execute('DELETE FROM translations WHERE article_id=? AND language=?', [aid, lang])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


def _mm_translate_chunk(text, source, target):
    if not text or not text.strip():
        return text
    q = urllib.parse.quote(text)
    url = f'https://api.mymemory.translated.net/get?q={q}&langpair={source}|{target}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (VoiceExpress desk-editor translate)'})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode('utf-8'))
    t = (d.get('responseData') or {}).get('translatedText')
    if not t:
        raise RuntimeError(d.get('responseDetails') or 'translate failed')
    return t


def _mm_translate_text(text, source, target):
    if not text or not text.strip():
        return text
    limit = 450
    if len(urllib.parse.quote(text)) < limit:
        return _mm_translate_chunk(text, source, target)
    parts = re.findall(r'[^.!?\n]+[.!?\n]*\s*', text) or [text]
    chunks, cur = [], ''
    for p in parts:
        if len(urllib.parse.quote(cur + p)) > limit:
            if cur:
                chunks.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        chunks.append(cur)
    return ''.join(_mm_translate_chunk(c, source, target) for c in chunks)


def _mm_translate_html(html, source, target):
    if not html:
        return html
    from bs4 import BeautifulSoup, NavigableString
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup.find_all(string=True):
        if isinstance(node, NavigableString) and node.strip():
            node.replace_with(_mm_translate_text(str(node), source, target))
    return str(soup)


@app.route('/api/articles/<int:aid>/translate', methods=['POST'])
def translation_auto(aid):
    db = get_db()
    try:
        data = request.json or {}
        target_lang = data.get('target_language', '')
        if target_lang not in SUPPORTED_TRANS_LANGS:
            return jsonify({'error': 'Language not supported'}), 400
        art = db.execute('SELECT * FROM articles WHERE id=?', [aid]).fetchone()
        if not art:
            return jsonify({'error': 'Article not found'}), 404
        native = art['language'] or 'en'
        if target_lang == native:
            return jsonify({'error': 'Invalid target language'}), 400
        src_mm, tgt_mm = LANG_MM_CODE.get(native, native), LANG_MM_CODE.get(target_lang, target_lang)
        try:
            title = _mm_translate_text(art['title'] or '', src_mm, tgt_mm)
            excerpt = _mm_translate_text(art['excerpt'] or '', src_mm, tgt_mm)
            content = _mm_translate_html(art['content'] or '', src_mm, tgt_mm)
        except Exception:
            return jsonify({'error': 'Translation service unavailable. Please try again.'}), 502
        return jsonify({'language': target_lang, 'title': title, 'excerpt': excerpt, 'content': content})
    finally:
        db.close()


def _store_image_bytes(db, raw, original_name, ext, aid=None):
    ext = (ext or 'jpg').lower().lstrip('.')
    if ext not in ALLOWED_EXT:
        ext = 'jpg'
    fn = f'{uuid.uuid4().hex}.{ext}'
    with open(os.path.join(MEDIA_PATH, fn), 'wb') as fh:
        fh.write(raw)
    db.execute('INSERT INTO images (filename,original_name,article_id) VALUES (?,?,?)',
               [fn, (original_name or fn)[:200], aid])
    return fn


@app.route('/api/media/inject', methods=['POST'])
def media_inject():
    db = get_db()
    try:
        aid = request.values.get('article_id') or None
        if 'file' in request.files:
            f = request.files['file']
            ext = f.filename.rsplit('.', 1)[-1] if '.' in (f.filename or '') else 'jpg'
            fn = _store_image_bytes(db, f.read(), f.filename, ext, aid)
        else:
            src = (request.json or {}).get('path') if request.is_json else request.values.get('path')
            if not src or not os.path.isfile(src):
                return jsonify({'error': 'file or path required'}), 400
            with open(src, 'rb') as fh:
                raw = fh.read()
            fn = _store_image_bytes(db, raw, os.path.basename(src),
                                    src.rsplit('.', 1)[-1], aid)
        db.commit()
        return jsonify({'url': f'/static/uploads/{fn}', 'filename': fn})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/media')
def media_list():
    db = get_db()
    try:
        aid = request.args.get('article')
        if aid:
            rows = db.execute('SELECT filename,original_name FROM images WHERE article_id=? '
                              'ORDER BY id DESC', [aid]).fetchall()
        else:
            rows = db.execute('SELECT filename,original_name FROM images ORDER BY id DESC '
                              'LIMIT 500').fetchall()
        return jsonify([{'url': f"/static/uploads/{r['filename']}", **dict(r)} for r in rows])
    finally:
        db.close()


INGEST_EXT = {'docx', 'doc', 'rtf', 'odt', 'html', 'htm', 'md', 'markdown', 'txt'}


def _convert_document_to_html(db, raw, filename, aid=None):
    try:
        import pypandoc
    except ImportError:
        raise RuntimeError('pypandoc is not installed on the server (pip install pypandoc)')
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'docx'
    if ext not in INGEST_EXT:
        raise ValueError(f'unsupported file type: .{ext}')
    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, f'in.{ext}')
        with open(src_path, 'wb') as fh:
            fh.write(raw)
        media_dir = os.path.join(td, 'media')
        try:
            html = pypandoc.convert_file(src_path, 'html', extra_args=['--wrap=none', f'--extract-media={media_dir}'])
        except OSError:
            raise RuntimeError('pandoc is not installed on this server -- see https://pandoc.org/installing.html')

        def repl(m):
            rel = m.group(1)
            local = os.path.normpath(os.path.join(td, rel))
            if not local.startswith(os.path.normpath(td)) or not os.path.isfile(local):
                return m.group(0)
            with open(local, 'rb') as fh:
                img_raw = fh.read()
            fn = _store_image_bytes(db, img_raw, os.path.basename(rel), rel.rsplit('.', 1)[-1], aid)
            return f'src="/static/uploads/{fn}"'
        html = re.sub(r'src="(media/[^"]+)"', repl, html)
    return html


@app.route('/api/ingest', methods=['POST'])
def ingest_document():
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    aid = request.values.get('article_id') or None
    db = get_db()
    try:
        html = _convert_document_to_html(db, f.read(), f.filename or 'document.docx', aid)
        db.commit()
        m = re.search(r'<h[12][^>]*>(.*?)</h[12]>', html, re.I | re.S)
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''
        return jsonify({'html': html, 'title': title})
    except (RuntimeError, ValueError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/palette/scan')
def palette_scan():
    path = request.args.get('path', '')
    if not path or not os.path.isdir(path):
        return jsonify({'error': 'directory not found'}), 404
    items = []
    try:
        for name in sorted(os.listdir(path)):
            ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
            if ext in IMAGE_EXT:
                items.append({'name': name, 'path': os.path.join(path, name),
                              'thumb': f'/api/palette/thumb?path={os.path.join(path, name)}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'path': path, 'count': len(items), 'items': items})


@app.route('/api/palette/thumb')
def palette_thumb():
    import hashlib
    path = request.args.get('path', '')
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        st = os.stat(path)
        key = hashlib.md5(f'{path}:{st.st_mtime_ns}:{st.st_size}'.encode()).hexdigest()
        cached = os.path.join(THUMBS_DIR, key + '.jpg')
        if not os.path.exists(cached):
            from PIL import Image
            im = Image.open(path)
            im = im.convert('RGB')
            im.thumbnail((360, 360))
            im.save(cached, 'JPEG', quality=82)
        return send_file(cached, mimetype='image/jpeg')
    except Exception:
        abort(415)


@app.route('/api/articles/<int:aid>/palette', methods=['GET'])
def palette_get(aid):
    db = get_db()
    try:
        proj = db.execute('SELECT folder_mounts FROM editor_projects WHERE article_id=?',
                          [aid]).fetchone()
        mounts = json.loads(proj['folder_mounts']) if proj else []
        loose = [dict(r) for r in db.execute(
            "SELECT id,path,url,title,thumb FROM editor_resources "
            "WHERE article_id=? AND kind='media' ORDER BY sort_order,id", [aid]).fetchall()]
        return jsonify({'mounts': mounts, 'items': loose})
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/palette', methods=['POST'])
def palette_post(aid):
    db = get_db()
    try:
        data = request.json or {}
        if 'mounts' in data:
            db.execute('INSERT INTO editor_projects (article_id,folder_mounts,updated_at) '
                       'VALUES (?,?,?) ON CONFLICT(article_id) DO UPDATE SET '
                       'folder_mounts=excluded.folder_mounts,updated_at=excluded.updated_at',
                       [aid, json.dumps(data['mounts']), now_iso()])
        if 'item' in data:
            it = data['item']
            db.execute("INSERT INTO editor_resources (article_id,kind,title,url,path,thumb,sort_order) "
                       "VALUES (?,'media',?,?,?,?,?)",
                       [aid, it.get('title'), it.get('url'), it.get('path'),
                        it.get('thumb'), it.get('sort_order', 0)])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/sources', methods=['GET'])
def sources_get(aid):
    db = get_db()
    try:
        rows = db.execute("SELECT id,kind,title,url,body,sort_order FROM editor_resources "
                          "WHERE article_id=? AND kind IN ('text','url') ORDER BY sort_order,id",
                          [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/articles/<int:aid>/sources', methods=['POST'])
def sources_post(aid):
    db = get_db()
    try:
        d = request.json or {}
        db.execute("INSERT INTO editor_resources (article_id,kind,title,url,body,sort_order) "
                   "VALUES (?,?,?,?,?,?)",
                   [aid, d.get('kind', 'text'), d.get('title', 'Source'), d.get('url', ''),
                    d.get('body', ''), d.get('sort_order', 0)])
        sid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': sid}), 201
    finally:
        db.close()


@app.route('/api/sources/<int:sid>', methods=['PUT', 'DELETE'])
def source_edit(sid):
    db = get_db()
    try:
        if request.method == 'DELETE':
            db.execute('DELETE FROM editor_resources WHERE id=?', [sid])
        else:
            d = request.json or {}
            db.execute('UPDATE editor_resources SET title=?,url=?,body=? WHERE id=?',
                       [d.get('title'), d.get('url'), d.get('body'), sid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/tags', methods=['GET'])
def tags_list():
    db = get_db()
    try:
        return jsonify(_ve_repo.list_tags(db))
    finally:
        db.close()


@app.route('/api/tags', methods=['POST'])
def create_tag():
    name = ((request.json or {}).get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    db = get_db()
    try:
        tag, created = _ve_repo.create_tag(db, name, match='name')
        return jsonify(tag), (201 if created else 200)
    finally:
        db.close()


@app.route('/api/tags/<int:tid>', methods=['PUT'])
def tag_rename(tid):
    db = get_db()
    try:
        return jsonify(_ve_repo.rename_tag(db, tid, (request.json or {}).get('name')))
    except _ve_repo.Invalid as e:
        return jsonify({'error': str(e)}), 400
    finally:
        db.close()


@app.route('/api/tags/<int:tid>', methods=['DELETE'])
def tag_delete(tid):
    db = get_db()
    try:
        _ve_repo.delete_tag(db, tid)
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/tags/<int:tid>/merge', methods=['POST'])
def tag_merge(tid):
    db = get_db()
    try:
        return jsonify(_ve_repo.merge_tag(db, tid, (request.json or {}).get('into')))
    except _ve_repo.Invalid as e:
        return jsonify({'error': str(e)}), 400
    finally:
        db.close()


@app.route('/api/categories', methods=['GET'])
def categories_list():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
        out = []
        for r in rows:
            c = dict(r)
            c['article_count'] = db.execute(
                "SELECT COUNT(*) FROM articles WHERE category_id=? AND status='published'", [c['id']]).fetchone()[0]
            out.append(c)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/categories', methods=['POST'])
def category_create():
    name = ((request.json or {}).get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    db = get_db()
    try:
        slug = slugify(name)
        ex = db.execute('SELECT id FROM categories WHERE slug=?', [slug]).fetchone()
        if ex:
            return jsonify({'id': ex['id'], 'slug': slug})
        db.execute('INSERT INTO categories (name,slug,description) VALUES (?,?,?)',
                   [name, slug, (request.json or {}).get('description', '')])
        cid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': cid, 'slug': slug}), 201
    finally:
        db.close()


@app.route('/api/categories/<int:cid>', methods=['PUT'])
def category_rename(cid):
    d = request.json or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    db = get_db()
    try:
        slug = slugify(name); n = 2
        while db.execute('SELECT 1 FROM categories WHERE slug=? AND id!=?', [slug, cid]).fetchone():
            slug = f'{slugify(name)}-{n}'; n += 1
        db.execute('UPDATE categories SET name=?,slug=?,description=? WHERE id=?',
                   [name, slug, d.get('description', ''), cid])
        db.commit()
        return jsonify({'id': cid, 'name': name, 'slug': slug})
    finally:
        db.close()


@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def category_delete(cid):
    db = get_db()
    try:
        db.execute('DELETE FROM categories WHERE id=?', [cid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/categories/<int:cid>/merge', methods=['POST'])
def category_merge(cid):
    into = (request.json or {}).get('into')
    db = get_db()
    try:
        if not into or int(into) == cid:
            return jsonify({'error': 'Pick a different target category'}), 400
        db.execute('UPDATE articles SET category_id=? WHERE category_id=?', [into, cid])
        db.execute('DELETE FROM categories WHERE id=?', [cid])
        db.commit()
        return jsonify({'success': True, 'into': into})
    finally:
        db.close()


@app.route('/api/sections', methods=['GET'])
def sections_list():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT s.*, COUNT(a.id) as article_count FROM sections s "
            "LEFT JOIN articles a ON a.section_id=s.id AND a.status='published' "
            "GROUP BY s.id ORDER BY s.sort_order, s.name").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/sections/<int:sid>', methods=['PUT'])
def section_update(sid):
    d = request.json or {}
    db = get_db()
    try:
        db.execute('UPDATE sections SET name=?,description=?,sort_order=? WHERE id=?',
                   [d.get('name'), d.get('description', ''), d.get('sort_order', 0), sid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/series', methods=['GET'])
def series_list():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM article_series ORDER BY title').fetchall()
        out = []
        for r in rows:
            s = dict(r)
            s['article_count'] = db.execute(
                'SELECT COUNT(*) FROM articles WHERE series_id=?', [s['id']]).fetchone()[0]
            out.append(s)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/series', methods=['POST'])
def series_create():
    d = request.json or {}
    title = (d.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title required'}), 400
    db = get_db()
    try:
        slug = slugify(title)
        if db.execute('SELECT 1 FROM article_series WHERE slug=?', [slug]).fetchone():
            return jsonify({'error': 'A series with this title already exists'}), 409
        db.execute('INSERT INTO article_series (title,slug,description,cover_image,created_at) VALUES (?,?,?,?,?)',
                   [title, slug, d.get('description', ''), d.get('cover_image', ''), now_iso()])
        sid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': sid, 'slug': slug, 'title': title}), 201
    finally:
        db.close()


@app.route('/api/series/<int:sid>', methods=['PUT'])
def series_update(sid):
    d = request.json or {}
    title = (d.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title required'}), 400
    db = get_db()
    try:
        db.execute('UPDATE article_series SET title=?,description=?,cover_image=? WHERE id=?',
                   [title, d.get('description', ''), d.get('cover_image', ''), sid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/series/<int:sid>', methods=['DELETE'])
def series_delete(sid):
    db = get_db()
    try:
        db.execute('UPDATE articles SET series_id=NULL,series_order=0 WHERE series_id=?', [sid])
        db.execute('DELETE FROM article_series WHERE id=?', [sid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/authors', methods=['GET'])
def authors_full():
    db = get_db()
    try:
        rows = db.execute('SELECT id,name,email,bio,role,author_type,avatar_url,'
                          'social_twitter,social_instagram FROM authors ORDER BY name').fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['links'] = [dict(l) for l in db.execute(
                'SELECT id,title,url,link_type,sort_order FROM author_links '
                'WHERE author_id=? ORDER BY sort_order,id', [r['id']]).fetchall()]
            out.append(d)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/authors', methods=['POST'])
def author_create():
    d = request.json or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    db = get_db()
    try:
        db.execute('INSERT INTO authors (name,bio,role,author_type) VALUES (?,?,?,?)',
                   [name, d.get('bio', ''), d.get('role', 'journalist'), d.get('author_type', 'reporter')])
        aid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': aid, 'name': name}), 201
    finally:
        db.close()


@app.route('/api/authors/<int:aid>', methods=['PUT'])
def author_update(aid):
    d = request.json or {}
    db = get_db()
    try:
        ex = db.execute('SELECT * FROM authors WHERE id=?', [aid]).fetchone()
        if not ex:
            return jsonify({'error': 'Not found'}), 404
        db.execute('''UPDATE authors SET name=?,bio=?,role=?,author_type=?,avatar_url=?,
            social_twitter=?,social_instagram=? WHERE id=?''',
                   [(d.get('name') or ex['name']).strip(), d.get('bio', ex['bio'] or ''),
                    d.get('role', ex['role'] or 'journalist'),
                    d.get('author_type', ex['author_type'] or 'reporter'),
                    d.get('avatar_url', ex['avatar_url'] or ''),
                    d.get('social_twitter', ex['social_twitter'] or ''),
                    d.get('social_instagram', ex['social_instagram'] or ''), aid])
        if 'links' in d:
            db.execute('DELETE FROM author_links WHERE author_id=?', [aid])
            for i, l in enumerate(d['links'] or []):
                if not (l.get('url') or '').strip():
                    continue
                db.execute('INSERT INTO author_links (author_id,title,url,link_type,sort_order) '
                           'VALUES (?,?,?,?,?)',
                           [aid, l.get('title', ''), l.get('url', ''), l.get('link_type', 'other'),
                            l.get('sort_order', i)])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


def _column_unique_slug(db, base, exclude_id=None):
    base = slugify(base) or 'column'
    slug, n = base, 2
    while True:
        row = db.execute('SELECT id FROM columns WHERE slug=?', [slug]).fetchone()
        if not row or (exclude_id and row['id'] == exclude_id):
            return slug
        slug = f'{base}-{n}'; n += 1


def column_authors_list(db, cid):
    rows = db.execute('''SELECT ca.author_id AS id, au.name, ca.role, ca.sort_order
        FROM column_authors ca JOIN authors au ON au.id=ca.author_id
        WHERE ca.column_id=? ORDER BY ca.sort_order, ca.author_id''', [cid]).fetchall()
    return [dict(r) for r in rows]


def set_column_authors(db, cid, authors):
    db.execute('DELETE FROM column_authors WHERE column_id=?', [cid])
    for i, a in enumerate(authors or []):
        try: auid = int(a.get('author_id'))
        except (TypeError, ValueError): continue
        db.execute('INSERT OR IGNORE INTO column_authors (column_id,author_id,role,sort_order) VALUES (?,?,?,?)',
                   [cid, auid, a.get('role') or 'author', int(a.get('sort_order', i) or i)])


def _column_dict(db, row):
    d = dict(row)
    d['authors'] = column_authors_list(db, d['id'])
    d['byline_auto'] = compose_byline(d['authors'])
    d['entry_count'] = db.execute('SELECT COUNT(*) FROM column_entries WHERE column_id=?', [d['id']]).fetchone()[0]
    return d


def _entry_dict(db, row, with_panels=True):
    return _ve_repo.entry_dict(db, row, with_panels)


@app.route('/api/columns', methods=['GET'])
def columns_list():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM columns ORDER BY is_featured DESC, sort_order, title').fetchall()
        return jsonify([_column_dict(db, r) for r in rows])
    finally:
        db.close()


@app.route('/api/columns/<slug_or_id>', methods=['GET'])
def column_get(slug_or_id):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM columns WHERE slug=? OR id=?', [slug_or_id, slug_or_id]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        d = _column_dict(db, row)
        d['entries'] = _ve_repo.list_entries(db, d['id'], with_panels=False)
        return jsonify(d)
    finally:
        db.close()


@app.route('/api/columns', methods=['POST'])
def column_create():
    db = get_db()
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({'error': 'Title required'}), 400
        slug = _column_unique_slug(db, data.get('slug') or title)
        now = now_iso()
        db.execute('''INSERT INTO columns (title,slug,subtitle,description,cover_image,cadence,
            period_days,accent,status,is_featured,sort_order,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', [
            title, slug, data.get('subtitle', ''), data.get('description', ''),
            data.get('cover_image', ''), data.get('cadence', 'weekly'),
            int(data.get('period_days') or 7), data.get('accent', ''),
            data.get('status', 'draft'), 1 if data.get('is_featured') else 0,
            int(data.get('sort_order') or 0), now, now])
        cid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        set_column_authors(db, cid, data.get('authors'))
        db.commit()
        return jsonify({'id': cid, 'slug': slug}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>', methods=['PUT'])
def column_update(cid):
    db = get_db()
    try:
        data = request.json or {}
        ex = db.execute('SELECT * FROM columns WHERE id=?', [cid]).fetchone()
        if not ex:
            return jsonify({'error': 'Not found'}), 404
        slug = _column_unique_slug(db, data.get('slug') or data.get('title') or ex['title'], cid) \
            if (data.get('slug') or data.get('title')) else ex['slug']
        db.execute('''UPDATE columns SET title=?,slug=?,subtitle=?,description=?,cover_image=?,
            cadence=?,period_days=?,accent=?,status=?,is_featured=?,sort_order=?,updated_at=? WHERE id=?''', [
            (data.get('title') or ex['title']).strip(), slug,
            data.get('subtitle', ex['subtitle'] or ''), data.get('description', ex['description'] or ''),
            data.get('cover_image', ex['cover_image'] or ''), data.get('cadence', ex['cadence']),
            int(data.get('period_days', ex['period_days']) or 7), data.get('accent', ex['accent'] or ''),
            data.get('status', ex['status']), 1 if data.get('is_featured', ex['is_featured']) else 0,
            int(data.get('sort_order', ex['sort_order']) or 0), now_iso(), cid])
        if 'authors' in data:
            set_column_authors(db, cid, data.get('authors'))
        db.commit()
        return jsonify({'success': True, 'slug': slug})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/columns/<int:cid>', methods=['DELETE'])
def column_delete(cid):
    db = get_db()
    try:
        db.execute('DELETE FROM columns WHERE id=?', [cid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/columns/<int:cid>/entries', methods=['POST'])
def column_entry_create(cid):
    db = get_db()
    try:
        eid = _ve_repo.create_entry(db, cid, request.json or {}, now_iso(), lambda b: normalize_body(db, b))
        return jsonify({'id': eid}), 201
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/column-entries/<int:eid>', methods=['GET'])
def column_entry_get(eid):
    db = get_db()
    try:
        return jsonify(_ve_repo.get_entry(db, eid))
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    finally:
        db.close()


@app.route('/api/column-entries/<int:eid>', methods=['PUT'])
def column_entry_update(eid):
    db = get_db()
    try:
        _ve_repo.update_entry(db, eid, request.json or {}, now_iso(), lambda b: normalize_body(db, b))
        return jsonify({'success': True})
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/column-entries/<int:eid>', methods=['DELETE'])
def column_entry_delete(eid):
    db = get_db()
    try:
        _ve_repo.delete_entry(db, eid)
        return jsonify({'success': True})
    finally:
        db.close()


def _pub_cover_from_upload(cf):
    ext = (cf.filename.rsplit('.', 1)[-1] if '.' in (cf.filename or '') else 'jpg').lower()
    if ext not in ALLOWED_EXT:
        ext = 'jpg'
    fn = f'pubcover_{uuid.uuid4().hex[:8]}.{ext}'
    cf.save(os.path.join(MEDIA_PATH, fn))
    return f'/static/uploads/{fn}'


@app.route('/api/publications', methods=['GET'])
def publications_list():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM publications ORDER BY created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/publications/<int:pid>', methods=['GET'])
def publication_get(pid):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM publications WHERE id=?', [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))
    finally:
        db.close()


@app.route('/api/publications/<int:pid>', methods=['PUT'])
def publication_update(pid):
    data = request.json or {}
    db = get_db()
    try:
        row = db.execute('SELECT id FROM publications WHERE id=?', [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        fields, params = [], []
        for key in ('title', 'description', 'price_min', 'price_max', 'price_suggested',
                    'currency', 'cover_image', 'is_visible', 'is_featured'):
            if key in data:
                fields.append(f'{key}=?')
                params.append(data[key])
        if 'tags' in data:
            cur = db.execute('SELECT metadata FROM publications WHERE id=?', [pid]).fetchone()
            try:
                meta = json.loads(cur['metadata'] or '{}') or {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            raw = data['tags']
            if isinstance(raw, str):
                raw = raw.split(',')
            meta['tags'] = [str(t).strip() for t in (raw or []) if str(t).strip()][:20]
            fields.append('metadata=?')
            params.append(json.dumps(meta, ensure_ascii=False))
        if fields:
            params.append(pid)
            db.execute(f"UPDATE publications SET {','.join(fields)} WHERE id=?", params)
            db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/publications/<int:pid>', methods=['DELETE'])
def publication_delete(pid):
    db = get_db()
    try:
        row = db.execute('SELECT filename FROM publications WHERE id=?', [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        if row['filename']:
            fp = publication_path(row['filename'])
            if fp:
                os.remove(fp)
            stem = os.path.splitext(row['filename'])[0]
            side = publication_path(f'{stem}.dtp.json')
            if side:
                os.remove(side)
        db.execute('DELETE FROM publications WHERE id=?', [pid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/publications/upload', methods=['POST'])
def publication_upload():
    f = request.files.get('file')
    if not f or not (f.filename or '').lower().endswith('.pdf'):
        return jsonify({'error': 'A PDF file is required'}), 400
    data = f.read()
    if len(data) > 60 * 1024 * 1024:
        return jsonify({'error': 'PDF too large (max 60 MB)'}), 400
    title = (request.form.get('title') or os.path.splitext(f.filename)[0] or 'Untitled').strip()[:200]
    desc = (request.form.get('description') or '').strip()[:1000]
    ts = datetime.now(timezone.utc).strftime('%Y%m%d')
    safe = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:50] or 'upload'
    filename = f'{safe}_{ts}_{uuid.uuid4().hex[:6]}.pdf'
    try:
        with open(os.path.join(PUBLICATIONS_PATH, filename), 'wb') as fh:
            fh.write(data)
    except Exception as e:
        return jsonify({'error': f'Could not store file: {e}'}), 500
    cover = None
    cf = request.files.get('cover')
    if cf and cf.filename and cf.filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXT:
        cover = _pub_cover_from_upload(cf)
    elif (request.form.get('cover_url') or '').strip():
        cover = request.form['cover_url'].strip()
    db = get_db()
    try:
        meta = json.dumps({'uploaded': True, 'description': desc}, ensure_ascii=False)
        db.execute('''INSERT INTO publications
            (title, pub_type, filename, file_size, cover_image, description, article_count,
             issue_number, price_min, price_max, price_suggested, currency, metadata)
            VALUES (?,?,?,?,?,?,?,?,0,500,0,'INR',?)''',
            [title, 'pdf', filename, len(data), cover, desc, 0, None, meta])
        db.commit()
        pid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        return jsonify({'success': True, 'id': pid}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/publications/<int:pid>/replace', methods=['POST'])
def publication_replace(pid):
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'A replacement file is required'}), 400
    db = get_db()
    try:
        row = db.execute('SELECT filename FROM publications WHERE id=?', [pid]).fetchone()
        if not row or not row['filename']:
            return jsonify({'error': 'Not found'}), 404
        old_ext = row['filename'].rsplit('.', 1)[-1].lower()
        new_ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if new_ext != old_ext:
            return jsonify({'error': f'This publication is a .{old_ext} — '
                                     'the replacement must be too'}), 400
        data = f.read()
        if len(data) > 60 * 1024 * 1024:
            return jsonify({'error': 'File too large (max 60 MB)'}), 400
        fp = publication_path(row['filename']) or os.path.join(PUBLICATIONS_PATH, row['filename'])
        with open(fp, 'wb') as fh:
            fh.write(data)
        db.execute('UPDATE publications SET file_size=? WHERE id=?', [len(data), pid])
        db.commit()
        return jsonify({'success': True, 'file_size': len(data), 'filename': row['filename']})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/publications/<int:pid>/icon', methods=['POST'])
def publication_icon(pid):
    if not _gen_icon:
        return jsonify({'error': 'Pillow not installed on this server -- pip install Pillow'}), 503
    db = get_db()
    try:
        row = db.execute('SELECT * FROM publications WHERE id=?', [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        title = row['title'] or 'Untitled'
        tags = [w for w in re.sub(r'<[^>]+>', '', title).upper().split() if len(w) > 4 and w.isalpha()]
        cover = _gen_icon(row['pub_type'] or 'pdf', list(dict.fromkeys(tags))[:20], title,
                          seed=int(hashlib.md5(title.encode()).hexdigest()[:8], 16))
        if not cover:
            return jsonify({'error': 'Icon generation failed'}), 500
        db.execute('UPDATE publications SET cover_image=? WHERE id=?', [cover, pid])
        db.commit()
        return jsonify({'success': True, 'cover_image': cover})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/library')
def library():
    db = get_db()
    try:
        rows = db.execute('''SELECT a.id,a.title,a.slug,a.status,a.category_id,a.section_id,
            a.latitude,a.longitude,a.location_name,a.updated_at,
            c.name AS category_name, s.name AS section_name
            FROM articles a LEFT JOIN categories c ON c.id=a.category_id
            LEFT JOIN sections s ON s.id=a.section_id ORDER BY a.updated_at DESC''').fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['tag_ids'] = [x['tag_id'] for x in db.execute(
                'SELECT tag_id FROM article_tags WHERE article_id=?', [r['id']]).fetchall()]
            out.append(d)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/articles/<int:aid>', methods=['DELETE'])
def delete_article(aid):
    db = get_db()
    try:
        db.execute('UPDATE images SET article_id=NULL WHERE article_id=?', [aid])
        db.execute('DELETE FROM articles WHERE id=?', [aid])
        db.commit()
        p = os.path.join(PREVIEWS_DIR, f'{aid}.html')
        if os.path.exists(p):
            os.remove(p)
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/articles/batch', methods=['POST'])
def batch_update():
    d = request.json or {}
    ids = [int(i) for i in (d.get('ids') or [])]
    if not ids:
        return jsonify({'error': 'no ids'}), 400
    SETTABLE = ['category_id', 'section_id', 'status', 'latitude', 'longitude', 'location_name']
    sets = {k: d[k] for k in SETTABLE if k in d}
    add_tags = [int(t) for t in (d.get('add_tag_ids') or [])]
    db = get_db()
    try:
        ph = ','.join('?' * len(ids))
        if sets:
            cols = ', '.join(f'{k}=?' for k in sets) + ', updated_at=?'
            db.execute(f'UPDATE articles SET {cols} WHERE id IN ({ph})',
                       list(sets.values()) + [now_iso()] + ids)
            if sets.get('status') == 'published':
                db.execute(f"UPDATE articles SET published_at=? WHERE id IN ({ph}) "
                           "AND (published_at IS NULL OR published_at='')",
                           [datetime.now().replace(microsecond=0).isoformat()] + ids)
        for tid in add_tags:
            for aid in ids:
                db.execute('INSERT OR IGNORE INTO article_tags VALUES (?,?)', [aid, tid])
        db.commit()
        return jsonify({'success': True, 'count': len(ids)})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


PAGE_DEFAULTS = {
    'about': 'About',
    'submissions': 'Submissions',
}


@app.route('/api/pages', methods=['GET'])
def pages_list():
    db = get_db()
    try:
        rows = {r['slug']: dict(r) for r in db.execute(
            'SELECT slug,title,content,updated_at FROM site_pages').fetchall()}
        out = []
        for slug, title in PAGE_DEFAULTS.items():
            out.append(rows.get(slug) or {'slug': slug, 'title': title, 'content': '', 'updated_at': None})
        for slug, row in rows.items():
            if slug not in PAGE_DEFAULTS:
                out.append(row)
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/pages/<slug>', methods=['GET'])
def page_get(slug):
    db = get_db()
    try:
        row = db.execute('SELECT slug,title,content,updated_at FROM site_pages WHERE slug=?', [slug]).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({'slug': slug, 'title': PAGE_DEFAULTS.get(slug, slug.title()), 'content': '', 'updated_at': None})
    finally:
        db.close()


@app.route('/api/pages/<slug>', methods=['PUT'])
def page_save(slug):
    d = request.json or {}
    title = (d.get('title') or PAGE_DEFAULTS.get(slug, slug.title())).strip()
    content = d.get('content') or ''
    db = get_db()
    try:
        db.execute('''INSERT INTO site_pages (slug,title,content,updated_at) VALUES (?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET title=excluded.title,content=excluded.content,
            updated_at=excluded.updated_at''', [slug, title, content, now_iso()])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/config', methods=['GET'])
def config_get():
    if not os.path.exists(CONFIG_JSON):
        return jsonify({})
    with open(CONFIG_JSON, encoding='utf-8') as fh:
        return jsonify(json.load(fh))


@app.route('/api/config', methods=['PUT'])
def config_save():
    cfg = request.json or {}
    with open(CONFIG_JSON, 'w', encoding='utf-8') as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    return jsonify({'success': True})


_PDF_ENHANCEMENT_DEFAULTS = {'toc': False, 'page_numbers': True, 'cover_note': '', 'accent': '', 'extra_css': ''}
_PDF_TARGET_TYPES = ('broadsheet', 'magazine', 'column_booklet')

@app.route('/api/pdf-enhancements/<target_type>/<path:target_key>', methods=['GET'])
def pdf_enhancement_get(target_type, target_key):
    if target_type not in _PDF_TARGET_TYPES:
        return jsonify({'error': 'Unknown target_type'}), 400
    db = get_db()
    try:
        row = db.execute('SELECT toc,page_numbers,cover_note,accent,extra_css FROM pdf_enhancements '
                         'WHERE target_type=? AND target_key=?', [target_type, target_key]).fetchone()
        if not row:
            return jsonify(dict(_PDF_ENHANCEMENT_DEFAULTS))
        return jsonify({'toc': bool(row['toc']), 'page_numbers': bool(row['page_numbers']),
                        'cover_note': row['cover_note'] or '', 'accent': row['accent'] or '',
                        'extra_css': row['extra_css'] or ''})
    finally:
        db.close()


@app.route('/api/pdf-enhancements/<target_type>/<path:target_key>', methods=['PUT'])
def pdf_enhancement_put(target_type, target_key):
    if target_type not in _PDF_TARGET_TYPES:
        return jsonify({'error': 'Unknown target_type'}), 400
    d = request.json or {}
    db = get_db()
    try:
        db.execute('''INSERT INTO pdf_enhancements (target_type,target_key,toc,page_numbers,cover_note,accent,extra_css,updated_at)
            VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(target_type,target_key) DO UPDATE SET
              toc=excluded.toc, page_numbers=excluded.page_numbers, cover_note=excluded.cover_note,
              accent=excluded.accent, extra_css=excluded.extra_css, updated_at=CURRENT_TIMESTAMP''',
            [target_type, target_key, 1 if d.get('toc') else 0, 1 if d.get('page_numbers', True) else 0,
             (d.get('cover_note') or '')[:500], (d.get('accent') or '')[:20], (d.get('extra_css') or '')[:20000]])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/broadsheet-months', methods=['GET'])
def broadsheet_months():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT DISTINCT ym FROM ("
            "  SELECT substr(published_at,1,7) ym FROM articles"
            "   WHERE status='published' AND published_at IS NOT NULL"
            "  UNION"
            "  SELECT substr(entry_date,1,7) ym FROM column_entries"
            "   WHERE status='published' AND entry_date IS NOT NULL"
            ") WHERE ym IS NOT NULL ORDER BY ym DESC").fetchall()
        return jsonify([r['ym'] for r in rows if r['ym']])
    finally:
        db.close()


@app.route('/api/rebuild', methods=['POST'])
def rebuild():
    which = (request.json or {}).get('targets') or ['ve-push', 'librarize']
    scripts = {'ve-push': 've-push.py', 'librarize': 'librarize.py'}
    log, ok = [], True
    for key in which:
        script = scripts.get(key)
        if not script or not os.path.exists(os.path.join(ROOT, script)):
            continue
        log.append(f'$ python {script}')
        try:
            r = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True,
                               text=True, timeout=600)
            log.append(r.stdout.strip())
            if r.stderr.strip():
                log.append(r.stderr.strip())
            if r.returncode != 0:
                ok = False
                log.append(f'[exit code {r.returncode}]')
        except Exception as e:
            ok = False
            log.append(f'[failed: {e}]')
    return jsonify({'success': ok, 'log': '\n'.join(log).strip()})


if __name__ == '__main__':
    ensure_schema()
    port = CFG.get('port', 8765)
    print(f'Voice Express Desk Editor -> http://localhost:{port}')
    print(f'  db    : {DB_PATH}')
    print(f'  media : {MEDIA_PATH}')
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)
