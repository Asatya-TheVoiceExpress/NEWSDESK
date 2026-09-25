from flask import Flask, request, jsonify, send_from_directory, send_file, session
from flask_cors import CORS
import sqlite3
import os
import json
import re
import io
import zipfile
import html as _html
from datetime import datetime, timedelta
import uuid
import calendar
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import random
import hashlib
import mimetypes
import urllib.request as _urllib_req
import urllib.parse
from concurrent.futures import ThreadPoolExecutor as _TPE
import threading as _threading

try:
    from make_magazine import build_magazine_html
    _PRINTABLES_OK = True
except Exception as _e:
    _PRINTABLES_OK = False
    print(f'[warn] printables unavailable: {_e}')

try:
    from make_newsletter_broadsheet import build_newsletter_broadsheet
    _NL_BROADSHEET_OK = True
except Exception as _nbe:
    _NL_BROADSHEET_OK = False
    print(f'[warn] newsletter broadsheet unavailable: {_nbe}')

try:
    from make_newsletter_broadsheet import build_broadsheet_scroll
    _NL_BROADSHEET_SCROLL_OK = True
except Exception as _nbse:
    _NL_BROADSHEET_SCROLL_OK = False
    print(f'[warn] broadsheet scroll unavailable: {_nbse}')

try:
    from make_column_booklet import build_column_booklet
    _COL_BOOKLET_OK = True
except Exception as _cbe:
    _COL_BOOKLET_OK = False
    print(f'[warn] column booklet unavailable: {_cbe}')

try:
    from make_article_print import build_article_print
    _ART_PRINT_OK = True
except Exception as _ape:
    _ART_PRINT_OK = False
    print(f'[warn] article printable unavailable: {_ape}')

try:
    from pdf_design_editor import (
        init_design_tables, get_custom_css, save_custom_css, get_screenshots,
        save_screenshots, render_html_with_custom_css, capture_pdf_screenshots,
        EDITOR_TEMPLATE
    )
    _DESIGN_EDITOR_OK = True
    init_design_tables()
except Exception as _de:
    _DESIGN_EDITOR_OK = False
    print(f'[warn] design editor unavailable: {_de}')

DTP_PY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dtp.py')
_DTP_ENGINE_OK = os.path.exists(DTP_PY_PATH)
if not _DTP_ENGINE_OK:
    print('[warn] dtp.py not found -- publication generation falls back to direct calls')


def _dtp_run(*args, data=None, timeout=120):
    import subprocess, tempfile
    tmp_path = None
    cmd = [_sys.executable, DTP_PY_PATH] + [str(a) for a in args]
    try:
        if data is not None:
            fd, tmp_path = tempfile.mkstemp(suffix='.json', prefix='dtp_data_')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            cmd += ['--data-file', tmp_path]
        env = dict(os.environ)
        env['DTP_DB_PATH'] = os.path.abspath(DATABASE)
        env['PUBLICATIONS_PATH'] = os.path.abspath(PUBLICATIONS_FOLDER)
        env['DTP_STATIC_ROOT'] = os.path.abspath(STATIC_ROOT)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=os.path.dirname(DTP_PY_PATH), env=env)
        out = (r.stdout or '').strip()
        if not out:
            return {'error': f'dtp.py produced no output (exit {r.returncode}): {(r.stderr or "").strip()[-1000:]}'}
        try:
            return json.loads(out.splitlines()[-1])
        except Exception:
            return {'error': f'dtp.py produced invalid JSON: {out[:500]!r}'}
    except Exception as e:
        return {'error': f'dtp.py CLI failed: {e}'}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

try:
    from pub_icons import generate_icon as _gen_icon, spiral_text_icon as _spiral_icon
except Exception:
    _gen_icon = None
    _spiral_icon = None

try:
    import ve_library as _ve_library
except Exception as _vle:
    _ve_library = None
    print(f'[warn] ve_library unavailable, artifact freshness checks disabled: {_vle}')

import ve.db as _ve_db
import ve.paths as _ve_paths
import ve.tags as _ve_tags
import ve.repo as _ve_repo

try:
    import ve_semantic as _semantic
except Exception:
    _semantic = None

def _normalize_html(text):
    return _semantic.normalize(text) if (_semantic and text) else text

_CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'broadsheet_config.json')
_cfg_lock  = __import__('threading').Lock()

def _bump_issue_number():
    with _cfg_lock:
        try:
            with open(_CFG_PATH, encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        mag = cfg.setdefault('magazine', {})
        new_issue = mag.get('issue_number', 0) + 1
        mag['issue_number'] = new_issue
        with open(_CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return new_issue

def _bump_volume():
    with _cfg_lock:
        try:
            with open(_CFG_PATH, encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        pub = cfg.setdefault('publication', {})
        new_vol = int(pub.get('volume', 0)) + 1
        pub['volume'] = new_vol
        with open(_CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return new_vol

app = Flask(__name__)
CORS(app, supports_credentials=True)

_KEY_FILE = os.environ.get('KEY_FILE', '.ve_secret')
if os.environ.get('SECRET_KEY'):
    app.secret_key = os.environ['SECRET_KEY']
elif os.path.exists(_KEY_FILE):
    with open(_KEY_FILE) as _f:
        app.secret_key = _f.read().strip()
else:
    app.secret_key = os.urandom(24).hex()
    with open(_KEY_FILE, 'w') as _f:
        _f.write(app.secret_key)

DATABASE      = _ve_paths.db_path()
UPLOAD_FOLDER = _ve_paths.uploads_path()

import sys as _sys, glob as _glob, shutil as _shutil
VE_TEST = ('--test' in _sys.argv) or os.environ.get('VE_TEST', '').lower() in ('1', 'true', 'yes')
if VE_TEST and not os.environ.get('DB_PATH'):
    DATABASE = 'voice_express.test.db'
    if not os.path.exists(DATABASE):
        _seed = sorted(_glob.glob('ve-seed-*.zip')) + sorted(_glob.glob(os.path.join('..', 've-seed-*.zip')))
        if _seed:
            try:
                import ve_import
                ve_import.restore(_seed[-1], db_path=DATABASE, uploads_dir=UPLOAD_FOLDER)
                print('[test] seeded %s from %s' % (DATABASE, _seed[-1]))
            except Exception as _e:
                print('[test] seed restore failed (%s); starting empty' % _e)
        elif os.path.exists('voice_express.db'):
            _shutil.copyfile('voice_express.db', DATABASE)
            print('[test] cloned voice_express.db -> %s' % DATABASE)

if not VE_TEST and not os.path.exists(DATABASE):
    _pseed = sorted(_glob.glob('ve-seed-*.zip')) + sorted(_glob.glob('ve-export-*.zip')) \
           + sorted(_glob.glob(os.path.join('..', 've-seed-*.zip')))
    if _pseed:
        try:
            import ve_import
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            ve_import.restore(_pseed[-1], db_path=DATABASE, uploads_dir=UPLOAD_FOLDER)
            print('[seed] restored %s from %s' % (DATABASE, _pseed[-1]))
        except Exception as _e:
            print('[seed] restore failed (%s); starting empty' % _e)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
PUBLICATIONS_FOLDER = _ve_paths.publications_path()
os.makedirs(PUBLICATIONS_FOLDER, exist_ok=True)
MEDIA_FOLDER = _ve_paths.media_path()
os.makedirs(MEDIA_FOLDER, exist_ok=True)
_CACHE_DIR = os.path.join(PUBLICATIONS_FOLDER, '_cache')


def _publication_path(filename):
    if not filename:
        return None
    for folder in (PUBLICATIONS_FOLDER, MEDIA_FOLDER):
        p = os.path.join(folder, filename)
        if os.path.exists(p):
            return p
    return None

os.makedirs(_CACHE_DIR, exist_ok=True)


class ArtifactError(RuntimeError):
    pass


def _dtp_artifact(db, kind, source_ref, fmt, *, gen_args=(), data=None,
                  title=None, sig=None, pub_type=None):
    if not _DTP_ENGINE_OK:
        raise ArtifactError('dtp.py is not available -- publication generation is offline')
    ext = 'pdf' if fmt == 'pdf' else 'html'
    status = {'state': 'stale'}
    if _ve_library and source_ref is not None:
        try:
            status = _ve_library.artifact_status(db, kind, source_ref, ext, sig=sig,
                                                 static_root=STATIC_ROOT)
        except Exception as _se:
            print(f'[artifact] status check failed ({kind}/{source_ref}): {_se}')

    if status.get('state') == 'fresh' and status.get('path'):
        with open(status['path'], 'rb') as f:
            return f.read(), status['filename']

    pid = status.get('project_id')
    if status.get('state') != 'restale' or not pid:
        gen = _dtp_run('generate', kind, *gen_args, '--regenerate', data=data, timeout=900)
        if 'error' in gen:
            raise ArtifactError(gen['error'])
        pid = gen['project_id']

    pub_args = ['publish', '--project-id', pid, '--format', fmt]
    if title:
        pub_args += ['--title', title]
    if sig is not None:
        pub_args += ['--sig', sig]
    pub = _dtp_run(*pub_args, timeout=900)
    if 'error' in pub:
        raise ArtifactError(pub['error'])
    path = _publication_path(pub['filename'])
    if not path:
        raise ArtifactError(f'dtp published {pub["filename"]} but it is not on disk')
    with open(path, 'rb') as f:
        return f.read(), pub['filename']


def _month_sig(db, ym):
    import hashlib as _hl
    rows = db.execute("SELECT id,updated_at,status FROM articles WHERE substr(published_at,1,7)=?", [ym]).fetchall()
    crow = db.execute("SELECT id,updated_at FROM column_entries WHERE substr(entry_date,1,7)=?", [ym]).fetchall()
    raw = '|'.join(f'{r["id"]}:{r["updated_at"]}:{r["status"]}' for r in rows) + '#' + \
          '|'.join(f'{r["id"]}:{r["updated_at"]}' for r in crow)
    return _hl.md5(raw.encode()).hexdigest()

_PDF_ENHANCEMENT_DEFAULTS = {'toc': False, 'page_numbers': True, 'cover_note': '', 'accent': '', 'extra_css': ''}

def get_pdf_enhancement(db, target_type, target_key):
    row = db.execute('SELECT toc,page_numbers,cover_note,accent,extra_css FROM pdf_enhancements '
                     'WHERE target_type=? AND target_key=?', [target_type, str(target_key)]).fetchone()
    if not row:
        return dict(_PDF_ENHANCEMENT_DEFAULTS)
    return {'toc': bool(row['toc']), 'page_numbers': bool(row['page_numbers']),
            'cover_note': row['cover_note'] or '', 'accent': row['accent'] or '',
            'extra_css': row['extra_css'] or ''}

STATIC_ROOT = os.path.dirname(os.path.abspath(UPLOAD_FOLDER))

_LOCALIZE_UA = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://docs.google.com/',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
}
_KNOWN_IMG_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}

def _localize_url(url):
    if not url or not url.startswith(('http://', 'https://')):
        return url
    key = hashlib.md5(url.encode()).hexdigest()
    raw_ext = os.path.splitext(url.split('?')[0])[1].lower()
    ext = raw_ext if raw_ext in _KNOWN_IMG_EXTS else ''
    for e in ([ext] if ext else list(_KNOWN_IMG_EXTS)):
        p = os.path.join(UPLOAD_FOLDER, f'_cache_{key}{e}')
        if os.path.exists(p):
            return f'/static/uploads/_cache_{key}{e}'
    try:
        req = _urllib_req.Request(url, headers=_LOCALIZE_UA)
        with _urllib_req.urlopen(req, timeout=10) as r:
            ct   = r.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
            data = r.read(5 * 1024 * 1024)
        if not ext:
            guessed = mimetypes.guess_extension(ct) or '.jpg'
            ext = '.jpg' if guessed == '.jpe' else guessed
        fname = f'_cache_{key}{ext}'
        with open(os.path.join(UPLOAD_FOLDER, fname), 'wb') as fh:
            fh.write(data)
        return f'/static/uploads/{fname}'
    except Exception as _le:
        print(f'[localize] {url[:70]}: {_le}')
        return url

def _localize_content(featured_image, content):
    urls = set()
    if featured_image and featured_image.startswith('http'):
        urls.add(featured_image)
    for src in re.findall(r'src=["\']([^"\']+)["\']', content or ''):
        if src.startswith('http'):
            urls.add(src)
    if not urls:
        return featured_image, content
    with _TPE(max_workers=8) as ex:
        mapping = dict(zip(urls, ex.map(_localize_url, urls)))
    new_fi = mapping.get(featured_image, featured_image)
    def _sub(m):
        return m.group(1) + mapping.get(m.group(2), m.group(2)) + m.group(3)
    new_content = re.sub(r'(src=["\'])([^"\']+)(["\'])', _sub, content or '') if content else content
    return new_fi, new_content

def _localize_articles(db, articles):
    for art in articles:
        fi  = art.get('featured_image') or ''
        con = art.get('content') or ''
        new_fi, new_con = _localize_content(fi, con)
        if new_fi != fi or new_con != con:
            art['featured_image'] = new_fi
            art['content']        = new_con
            try:
                db.execute('UPDATE articles SET featured_image=?, content=? WHERE id=?',
                           [new_fi, new_con, art['id']])
                db.commit()
            except Exception as _dbe:
                print(f'[localize] db update failed for article {art.get("id")}: {_dbe}')

def _localize_ids_bg(article_ids):
    if not article_ids:
        return
    def _run():
        try:
            _db = _ve_db.connect(DATABASE)
            ph   = ','.join('?' * len(article_ids))
            arts = [dict(r) for r in _db.execute(
                f'SELECT id, featured_image, content FROM articles WHERE id IN ({ph})',
                article_ids
            ).fetchall()]
            _localize_articles(_db, arts)
            _db.close()
            print(f'[import] localized media for {len(article_ids)} articles')
        except Exception as _e:
            print(f'[import] background localization error: {_e}')
    _threading.Thread(target=_run, daemon=True).start()

def get_db():
    return _ve_db.connect(DATABASE)

def init_db():
    db = get_db()
    with open('schema.sql', 'r') as f:
        db.executescript(f.read())
    db.commit()
    db.close()

def migrate_db():
    db = get_db()
    _ve_db.migrate(db)
    db.close()

def _save_to_library(db, title, pub_type, content_bytes, articles, safe_name, ext,
                      creator='', description='', extra_meta=None):
    try:
        ts = datetime.utcnow().strftime('%Y%m%d')
        filename = f'{safe_name}_{ts}_{uuid.uuid4().hex[:6]}.{ext}'
        filepath = os.path.join(PUBLICATIONS_FOLDER, filename)
        with open(filepath, 'wb') as _fh:
            _fh.write(content_bytes)
        cover = None
        if _gen_icon:
            try:
                _tags = []
                for _a in (articles or []):
                    _raw = _a.get('tags') or _a.get('tag_names') or ''
                    if isinstance(_raw, list):
                        _tags.extend(_raw)
                    elif _raw:
                        _tags.extend(re.split(r'[,;]+', _raw))
                if not _tags:
                    for _a in (articles or []):
                        for _w in re.sub(r'<[^>]+>', '', _a.get('title', '')).upper().split():
                            if len(_w) > 4 and _w.isalpha():
                                _tags.append(_w)
                _icon_seed = 42
                if pub_type == 'broadsheet':
                    try:
                        _ip  = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                                or request.remote_addr or '0.0.0.0')
                        _day = datetime.utcnow().strftime('%Y%m%d')
                        _icon_seed = int(hashlib.md5(f'{_ip}|{_day}'.encode()).hexdigest()[:8], 16)
                    except Exception:
                        pass
                cover = _gen_icon(pub_type, list(dict.fromkeys(_tags))[:20], title,
                                  seed=_icon_seed)
            except Exception as _ie:
                print(f'[library] icon generation failed: {_ie}')
        if not cover and articles:
            fi = (articles[0].get('featured_image') or '').strip()
            if fi:
                cover = fi if fi.startswith('/') else f'/static/uploads/{fi}'
        issue_num = None
        if pub_type in ('magazine_pdf', 'magazine_html'):
            try:
                with open(_CFG_PATH, encoding='utf-8') as _cf:
                    _cfg = json.load(_cf)
                issue_num = _cfg.get('magazine', {}).get('issue_number')
            except Exception:
                pass
        meta_d = {
            'articles': [
                {'id': a.get('id'), 'title': a.get('title'), 'author': a.get('author_name', '')}
                for a in (articles or [])[:20]
            ],
            'article_ids': [a.get('id') for a in (articles or [])],
            'creator': creator, 'description': description,
        }
        meta_d.update(extra_meta or {})
        meta = json.dumps(meta_d, ensure_ascii=False)
        db.execute(
            '''INSERT INTO publications
               (title, pub_type, filename, file_size, cover_image, article_count,
                issue_number, price_min, price_max, price_suggested, currency, metadata)
               VALUES (?,?,?,?,?,?,?,0,500,0,'INR',?)''',
            [title, pub_type, filename, len(content_bytes), cover,
             len(articles or []), issue_num, meta]
        )
        db.commit()
        print(f'[library] Saved {pub_type}: {filename}')
    except Exception as _le:
        print(f'[library] Could not save publication: {_le}')

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def slugify(text):
    text = str(text).lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:80] or 'untitled'

def reading_time(content):
    words = len(re.sub(r'<[^>]+>', '', str(content or '')).split())
    return max(1, round(words / 200))

def unique_slug(db, base, exclude_id=None):
    slug = base
    i = 1
    while True:
        q = 'SELECT id FROM articles WHERE slug=? AND id!=?' if exclude_id else 'SELECT id FROM articles WHERE slug=?'
        p = [slug, exclude_id] if exclude_id else [slug]
        if not db.execute(q, p).fetchone():
            return slug
        slug = f'{base}-{i}'; i += 1

_ROLE_BYLINE = {'photographer': 'Photos by', 'illustrator': 'Art by',
                'translator': 'Translation by', 'editor': 'Edited by',
                'as-told-to': 'As told to', 'reporting': 'Additional reporting by',
                'typesetter': 'Typeset by', 'post-editor': 'Post-edited by'}

_AUTO_CREDIT_ROLE = {'editor': 'editor', 'translator': 'translator', 'typesetter': 'typesetter'}


def _auto_credit(db, article_id, uid, session_role):
    row = db.execute('SELECT author_id FROM users WHERE id=?', [uid]).fetchone()
    author_id = row['author_id'] if row else None
    if not author_id:
        return
    primary = db.execute('SELECT author_id FROM articles WHERE id=?', [article_id]).fetchone()
    if primary and primary['author_id'] == author_id:
        return
    credit_role = _AUTO_CREDIT_ROLE.get(session_role) or ('co-author' if session_role == 'author' else None)
    if not credit_role:
        return
    exists = db.execute('SELECT 1 FROM article_authors WHERE article_id=? AND author_id=? AND role=?',
                        [article_id, author_id, credit_role]).fetchone()
    if exists:
        return
    max_order = db.execute('SELECT COALESCE(MAX(sort_order),0) FROM article_authors WHERE article_id=?',
                           [article_id]).fetchone()[0]
    db.execute('INSERT INTO article_authors (article_id,author_id,role,sort_order) VALUES (?,?,?,?)',
              [article_id, author_id, credit_role, max_order + 1])

def article_authors_list(db, aid):
    if _ve_library:
        return _ve_library.article_authors_list(db, aid)
    rows = db.execute('''SELECT aa.author_id AS id, au.name, aa.role, aa.sort_order
        FROM article_authors aa JOIN authors au ON au.id=aa.author_id
        WHERE aa.article_id=? ORDER BY aa.sort_order, aa.author_id''', [aid]).fetchall()
    return [dict(r) for r in rows]

def compose_byline(authors):
    if _ve_library:
        return _ve_library.compose_byline(authors)
    if not authors:
        return ''
    def _join(names):
        names = [n for n in names if n]
        if not names: return ''
        if len(names) == 1: return names[0]
        return ', '.join(names[:-1]) + ' & ' + names[-1]
    groups = {}
    order = []
    for a in authors:
        r = a.get('role') or 'author'
        if r not in groups: groups[r] = []; order.append(r)
        groups[r].append(a.get('name'))
    parts = []
    writers = (groups.pop('author', []) if 'author' in groups else []) + \
              (groups.pop('co-author', []) if 'co-author' in groups else [])
    if writers: parts.append(_join(writers))
    for r in order:
        if r in ('author', 'co-author') or r not in groups: continue
        parts.append(f"{_ROLE_BYLINE.get(r, r.title() + ' by')} {_join(groups[r])}")
    return ' - '.join(p for p in parts if p)

def set_article_authors(db, aid, authors, fallback_author_id=None):
    db.execute('DELETE FROM article_authors WHERE article_id=?', [aid])
    clean = []
    for i, a in enumerate(authors or []):
        try: auid = int(a.get('author_id'))
        except (TypeError, ValueError): continue
        clean.append((auid, (a.get('role') or 'author'), int(a.get('sort_order', i) or i)))
    if not clean and fallback_author_id:
        try: clean = [(int(fallback_author_id), 'author', 0)]
        except (TypeError, ValueError): clean = []
    for auid, role, order in clean:
        db.execute('INSERT OR IGNORE INTO article_authors (article_id,author_id,role,sort_order) VALUES (?,?,?,?)',
                   [aid, auid, role, order])
    primary = next((auid for auid, role, _ in clean if role in ('author', 'co-author')),
                   clean[0][0] if clean else None)
    db.execute('UPDATE articles SET author_id=? WHERE id=?', [primary, aid])

def _article_print_dict(db, row):
    d = dict(row)
    d['authors'] = article_authors_list(db, d['id'])
    d['byline_auto'] = compose_byline(d['authors'])
    return d

def article_to_dict(a, db):
    d = dict(a)
    tags = db.execute('SELECT t.* FROM tags t JOIN article_tags at2 ON t.id=at2.tag_id WHERE at2.article_id=?', [d['id']]).fetchall()
    d['tags'] = [dict(t) for t in tags]
    d['authors'] = article_authors_list(db, d['id'])
    d['byline_auto'] = compose_byline(d['authors'])
    sid = d.get('series_id')
    if sid:
        s = db.execute('SELECT id, title, slug FROM article_series WHERE id=?', [sid]).fetchone()
        if s:
            d['series_title'] = s['title']
            d['series_slug']  = s['slug']
    if d.get('section_id') and 'section_name' not in d:
        sec = db.execute('SELECT name, slug FROM sections WHERE id=?', [d['section_id']]).fetchone()
        if sec:
            d['section_name'] = sec['name']
            d['section_slug'] = sec['slug']
    return d

def record_history(db, article_id, action, language=None):
    uid = session.get('user_id')
    if not uid: return
    try:
        row = db.execute('SELECT u.username, a.name FROM users u LEFT JOIN authors a ON u.author_id=a.id WHERE u.id=?', [uid]).fetchone()
        display = (row['name'] or row['username']) if row else None
        db.execute('INSERT INTO article_history (article_id,user_id,display_name,action,language) VALUES (?,?,?,?,?)',
            [article_id, uid, display, action, language])
    except Exception:
        pass

def record_version(db, article_id, message='edited'):
    try:
        row = db.execute('SELECT title,subtitle,excerpt,seo_description,seo_keywords,content,byline,status,featured_image,'
                         'category_id,section_id,published_at FROM articles WHERE id=?',
                         [article_id]).fetchone()
        if not row: return
        snap = json.dumps(dict(row), ensure_ascii=False)
        uid = session.get('user_id')
        disp = None
        if uid:
            u = db.execute('SELECT u.username, a.name FROM users u LEFT JOIN authors a '
                           'ON u.author_id=a.id WHERE u.id=?', [uid]).fetchone()
            disp = (u['name'] or u['username']) if u else None
        db.execute('INSERT INTO article_versions (article_id,user_id,display_name,message,snapshot) '
                   'VALUES (?,?,?,?,?)', [article_id, uid, disp, message, snap])
    except Exception as _ve:
        print(f'[version] {_ve}')

@app.route('/')
def index():
    base = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base, 'templates', 'index.html')
    with open(html_path, encoding='utf-8') as fh:
        html = fh.read()
    try:
        import glob as _g
        assets = _g.glob(os.path.join(base, 'static', 'js', '*.jsx')) + [os.path.join(base, 'static', 'css', 'app.css')]
        ver = int(max(os.path.getmtime(a) for a in assets if os.path.exists(a)))
        html = html.replace('.jsx"', f'.jsx?v={ver}"').replace('app.css"', f'app.css?v={ver}"')
    except Exception:
        pass
    product = os.environ.get('VE_PRODUCT', 'full')
    html = html.replace('<head>', f'<head><script>window.VE_PRODUCT="{product}";</script>', 1)
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

_LINK_PREVIEW_CACHE = {}

@app.route('/api/link-preview')
def link_preview():
    import urllib.parse as _up
    url = (request.args.get('url') or '').strip()
    if not url.startswith(('http://', 'https://')):
        return jsonify({'error': 'bad url'}), 400
    if url in _LINK_PREVIEW_CACHE:
        return jsonify(_LINK_PREVIEW_CACHE[url])
    meta = {'url': url, 'site': _up.urlparse(url).netloc, 'title': '', 'description': '', 'image': ''}
    try:
        req = _urllib_req.Request(url, headers={'User-Agent': 'Mozilla/5.0 (VoiceExpress link-preview)'})
        with _urllib_req.urlopen(req, timeout=6) as r:
            if 'html' in r.headers.get('Content-Type', ''):
                data = r.read(300000).decode('utf-8', 'ignore')
                def grab(prop):
                    m = (re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]*content=["\']([^"\']*)["\']', data, re.I)
                         or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + re.escape(prop) + r'["\']', data, re.I))
                    return _html.unescape(m.group(1)).strip() if m else ''
                tm = re.search(r'<title[^>]*>(.*?)</title>', data, re.S | re.I)
                meta['title'] = (grab('og:title') or (_html.unescape(tm.group(1)).strip() if tm else ''))[:160]
                meta['description'] = (grab('og:description') or grab('description'))[:280]
                meta['image'] = grab('og:image')[:500]
    except Exception as e:
        meta['error'] = str(e)[:80]
    if len(_LINK_PREVIEW_CACHE) > 800:
        _LINK_PREVIEW_CACHE.clear()
    _LINK_PREVIEW_CACHE[url] = meta
    return jsonify(meta)

@app.route('/api/articles', methods=['GET'])
def get_articles():
    db = get_db()
    try:
        status    = request.args.get('status', 'published')
        category  = request.args.get('category', '')
        section   = request.args.get('section', '')
        tag       = request.args.get('tag', '')
        language  = request.args.get('language', '')
        author_id = request.args.get('author_id', '')
        search    = request.args.get('search', '').strip()
        title_search = request.args.get('title_search', '').strip()
        limit     = min(int(request.args.get('limit', 50)), 200)
        offset    = int(request.args.get('offset', 0))
        geotagged = request.args.get('geotagged', '')
        featured  = request.args.get('featured', '')

        q = '''SELECT a.*, au.name as author_name, au.avatar_url, au.role as author_role,
               c.name as category_name, c.slug as category_slug,
               s.name as section_name, s.slug as section_slug
               FROM articles a
               LEFT JOIN authors au ON a.author_id = au.id
               LEFT JOIN categories c ON a.category_id = c.id
               LEFT JOIN sections s ON a.section_id = s.id
               WHERE 1=1'''
        p = []
        if status and status != 'all': q += ' AND a.status=?'; p.append(status)
        if category: q += ' AND (c.slug=? OR c.name=?)'; p += [category, category]
        if section:  q += ' AND (s.slug=? OR s.name=?)'; p += [section, section]
        if author_id: q += ' AND a.id IN (SELECT article_id FROM article_authors WHERE author_id=?)'; p.append(author_id)
        if language: q += ' AND a.language=?'; p.append(language)
        if geotagged == 'true': q += ' AND a.latitude IS NOT NULL AND a.latitude!=0'
        if featured == 'true': q += ' AND a.is_featured=1'
        if search:
            q += ' AND (a.title LIKE ? OR a.content LIKE ? OR a.excerpt LIKE ? OR au.name LIKE ?)'
            p += [f'%{search}%']*4
        if title_search:
            q += ' AND a.title LIKE ?'
            p.append(f'%{title_search}%')
        if tag:
            q += ' AND a.id IN (SELECT at2.article_id FROM article_tags at2 JOIN tags t ON t.id=at2.tag_id WHERE t.slug=? OR t.name=?)'
            p += [tag, tag]
        q += ' ORDER BY a.is_featured DESC, a.published_at DESC LIMIT ? OFFSET ?'; p += [limit, offset]
        return jsonify([article_to_dict(r, db) for r in db.execute(q, p).fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>', methods=['GET'])
def get_article(aid):
    db = get_db()
    try:
        row = db.execute('''SELECT a.*, au.name as author_name, au.bio as author_bio,
            au.avatar_url, au.role as author_role, au.social_twitter, au.social_instagram,
            c.name as category_name, c.slug as category_slug
            FROM articles a LEFT JOIN authors au ON a.author_id=au.id
            LEFT JOIN categories c ON a.category_id=c.id WHERE a.id=?''', [aid]).fetchone()
        if not row: return jsonify({'error': 'Not found'}), 404
        art = article_to_dict(row, db)
        _uid = session.get('user_id')
        art['annotations'] = [dict(a) for a in db.execute(
            'SELECT * FROM annotations WHERE article_id=? AND user_id=? ORDER BY created_at', [aid, _uid]).fetchall()] if _uid else []
        art['citations']   = [dict(c) for c in db.execute('SELECT * FROM citations WHERE article_id=? ORDER BY citation_number', [aid]).fetchall()]
        art['corrections'] = [dict(c) for c in db.execute('SELECT * FROM corrections WHERE article_id=? ORDER BY published_at DESC', [aid]).fetchall()]
        art['available_languages'] = [t['language'] for t in db.execute('SELECT language FROM translations WHERE article_id=?', [aid]).fetchall()]
        related = {}
        if art.get('category_id'):
            for r in db.execute('''SELECT a.id,a.title,a.slug,a.excerpt,a.featured_image,a.published_at,a.reading_time,au.name as author_name
                FROM articles a LEFT JOIN authors au ON a.author_id=au.id
                WHERE a.category_id=? AND a.id!=? AND a.status='published'
                ORDER BY a.published_at DESC LIMIT 4''', [art['category_id'], aid]).fetchall():
                related[r['id']] = dict(r)
        tag_ids = [t['id'] for t in art.get('tags', [])]
        if tag_ids:
            ph = ','.join('?' * len(tag_ids))
            for r in db.execute(f'''SELECT a.id,a.title,a.slug,a.excerpt,a.featured_image,a.published_at,a.reading_time,au.name as author_name
                FROM articles a JOIN article_tags at2 ON a.id=at2.article_id
                LEFT JOIN authors au ON a.author_id=au.id
                WHERE at2.tag_id IN ({ph}) AND a.id!=? AND a.status='published'
                GROUP BY a.id ORDER BY COUNT(*) DESC, a.published_at DESC LIMIT 4''', tag_ids + [aid]).fetchall():
                if r['id'] not in related: related[r['id']] = dict(r)
        art['related'] = list(related.values())[:6]
        try:
            art['history'] = [dict(r) for r in db.execute('''
                SELECT ah.id,ah.action,ah.language,ah.edited_at,ah.display_name
                FROM article_history ah WHERE ah.article_id=? ORDER BY ah.edited_at ASC LIMIT 20''', [aid]).fetchall()]
            for t in art.get('available_languages', []):
                tr = db.execute('SELECT translator_name FROM translations WHERE article_id=? AND language=?', [aid, t]).fetchone()
                if tr and tr['translator_name']:
                    art.setdefault('translators', {})[t] = tr['translator_name']
        except Exception:
            art['history'] = []
        if art.get('series_id'):
            art['series_articles'] = [dict(r) for r in db.execute('''SELECT a.id,a.title,a.slug,a.series_order,a.published_at,au.name as author_name
                FROM articles a LEFT JOIN authors au ON a.author_id=au.id
                WHERE a.series_id=? AND a.status='published' ORDER BY a.series_order,a.published_at''', [art['series_id']]).fetchall()]
        else:
            art['series_articles'] = []
        return jsonify(art)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles', methods=['POST'])
def create_article():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title: return jsonify({'error': 'Title required'}), 400
        slug           = unique_slug(db, slugify(title))
        content        = data.get('content', '')
        featured_image = data.get('featured_image', '')
        featured_image, content = _localize_content(featured_image, content)
        content = _normalize_html(content)
        now     = datetime.utcnow().isoformat()
        status  = data.get('status', 'draft')
        pub_at  = data.get('published_at') or (now if status == 'published' else None)
        db.execute('''INSERT INTO articles (title,slug,subtitle,content,excerpt,seo_description,seo_keywords,author_id,byline,category_id,section_id,status,
            language,featured_image,latitude,longitude,location_name,published_at,reading_time,
            is_featured,series_id,series_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', [
            title, slug, data.get('subtitle',''), content, data.get('excerpt',''),
            data.get('seo_description',''), data.get('seo_keywords',''), data.get('author_id') or None,
            data.get('byline',''), data.get('category_id') or None,
            data.get('section_id') or None, status,
            data.get('language','en'), featured_image,
            data.get('latitude') or None, data.get('longitude') or None,
            data.get('location_name',''), pub_at, reading_time(content),
            1 if data.get('is_featured') else 0,
            data.get('series_id') or None, data.get('series_order') or 0, now, now])
        aid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        set_article_authors(db, aid, data.get('authors'), data.get('author_id'))
        record_history(db, aid, 'created')
        record_version(db, aid, (data.get('version_message') or 'created').strip()[:200])
        for tid in (data.get('tag_ids') or []):
            try: db.execute('INSERT OR IGNORE INTO article_tags VALUES (?,?)', [aid, tid])
            except: pass
        for i, c in enumerate(data.get('citations') or [], 1):
            db.execute('INSERT INTO citations (article_id,reference_text,url,author,published_date,citation_number) VALUES (?,?,?,?,?,?)',
                [aid, c.get('reference_text',''), c.get('url',''), c.get('author',''), c.get('published_date',''), i])
        db.commit()
        return jsonify({'id': aid, 'slug': slug}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>', methods=['PUT'])
def update_article(aid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        ex = db.execute('SELECT * FROM articles WHERE id=?', [aid]).fetchone()
        if not ex: return jsonify({'error': 'Not found'}), 404
        content        = data.get('content', ex['content'])
        featured_image = data.get('featured_image', ex['featured_image'] or '')
        featured_image, content = _localize_content(featured_image, content)
        content = _normalize_html(content)
        status  = data.get('status', ex['status'])
        now     = datetime.utcnow().isoformat()
        pub_at  = data.get('published_at') or ex['published_at']
        if status == 'published' and not pub_at: pub_at = now
        db.execute('''UPDATE articles SET title=?,subtitle=?,content=?,excerpt=?,seo_description=?,seo_keywords=?,author_id=?,byline=?,
            category_id=?,section_id=?,status=?,language=?,
            featured_image=?,latitude=?,longitude=?,location_name=?,published_at=?,
            reading_time=?,is_featured=?,series_id=?,series_order=?,updated_at=? WHERE id=?''', [
            (data.get('title') or ex['title']).strip(),
            data.get('subtitle', ex['subtitle'] if 'subtitle' in ex.keys() else '') or '', content,
            data.get('excerpt', ex['excerpt'] or ''),
            data.get('seo_description', ex['seo_description'] if 'seo_description' in ex.keys() else '') or '',
            data.get('seo_keywords', ex['seo_keywords'] if 'seo_keywords' in ex.keys() else '') or '',
            data.get('author_id', ex['author_id']) or None,
            data.get('byline', ex['byline'] or ''),
            data.get('category_id', ex['category_id']) or None,
            data.get('section_id', ex['section_id'] if 'section_id' in ex.keys() else None) or None,
            status, data.get('language', ex['language']),
            featured_image,
            data.get('latitude', ex['latitude']) or None,
            data.get('longitude', ex['longitude']) or None,
            data.get('location_name', ex['location_name'] or ''),
            pub_at, reading_time(content),
            1 if data.get('is_featured', ex['is_featured']) else 0,
            data.get('series_id', ex['series_id'] if 'series_id' in ex.keys() else None) or None,
            data.get('series_order', ex['series_order'] if 'series_order' in ex.keys() else 0) or 0,
            now, aid])
        if 'authors' in data:
            set_article_authors(db, aid, data.get('authors'), data.get('author_id'))
        record_history(db, aid, 'edited')
        if session.get('user_id'):
            _auto_credit(db, aid, session['user_id'], session.get('role'))
        record_version(db, aid, (data.get('version_message') or 'edited').strip()[:200])
        if 'tag_ids' in data:
            db.execute('DELETE FROM article_tags WHERE article_id=?', [aid])
            for tid in (data['tag_ids'] or []):
                try: db.execute('INSERT OR IGNORE INTO article_tags VALUES (?,?)', [aid, tid])
                except: pass
        if 'citations' in data:
            db.execute('DELETE FROM citations WHERE article_id=?', [aid])
            for i, c in enumerate(data['citations'] or [], 1):
                db.execute('INSERT INTO citations (article_id,reference_text,url,author,published_date,citation_number) VALUES (?,?,?,?,?,?)',
                    [aid, c.get('reference_text',''), c.get('url',''), c.get('author',''), c.get('published_date',''), i])
        db.commit()
        return jsonify({'success': True, 'id': aid})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>', methods=['DELETE'])
def delete_article(aid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        for tbl in ['article_tags','annotations','citations','translations']:
            db.execute(f'DELETE FROM {tbl} WHERE article_id=?', [aid])
        db.execute('DELETE FROM articles WHERE id=?', [aid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/versions', methods=['GET'])
def list_article_versions(aid):
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error': 'Forbidden'}), 403
    db = get_db()
    try:
        rows = db.execute('SELECT id, display_name, message, created_at, length(snapshot) AS size '
                          'FROM article_versions WHERE article_id=? ORDER BY id DESC', [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/versions/<int:vid>', methods=['GET'])
def get_article_version(aid, vid):
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error': 'Forbidden'}), 403
    db = get_db()
    try:
        r = db.execute('SELECT * FROM article_versions WHERE id=? AND article_id=?', [vid, aid]).fetchone()
        if not r:
            return jsonify({'error': 'Not found'}), 404
        d = dict(r)
        try: d['snapshot'] = json.loads(d['snapshot'])
        except Exception: d['snapshot'] = {}
        return jsonify(d)
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/versions/<int:vid>/restore', methods=['POST'])
def restore_article_version(aid, vid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error': 'Forbidden'}), 403
    db = get_db()
    try:
        r = db.execute('SELECT snapshot FROM article_versions WHERE id=? AND article_id=?', [vid, aid]).fetchone()
        if not r:
            return jsonify({'error': 'Not found'}), 404
        s = json.loads(r['snapshot'])
        db.execute('''UPDATE articles SET title=?,excerpt=?,content=?,byline=?,status=?,
            featured_image=?,category_id=?,section_id=?,reading_time=?,updated_at=? WHERE id=?''', [
            s.get('title'), s.get('excerpt'), s.get('content'), s.get('byline'), s.get('status'),
            s.get('featured_image'), s.get('category_id'), s.get('section_id'),
            reading_time(s.get('content')), datetime.utcnow().isoformat(), aid])
        record_history(db, aid, 'edited')
        record_version(db, aid, f'restored from version #{vid}')
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/print', methods=['GET'])
def article_print(aid):
    if not _ART_PRINT_OK:
        return jsonify({'error': 'Article printable unavailable'}), 503
    db = get_db()
    try:
        row = db.execute(
            "SELECT a.*,au.name as author_name,c.name as category_name,s.name as section_name "
            "FROM articles a LEFT JOIN authors au ON a.author_id=au.id "
            "LEFT JOIN categories c ON a.category_id=c.id "
            "LEFT JOIN sections s ON a.section_id=s.id "
            "WHERE a.id=? AND a.status='published'", [aid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        safe = re.sub(r'[^\w\s-]', '', (row['title'] or 'article')).strip().replace(' ', '_')[:60] or 'article'
        enh = get_pdf_enhancement(db, 'gazette', str(aid))
        sig = f'{row["updated_at"]}|{json.dumps(enh, sort_keys=True)}'
        art = _article_print_dict(db, row)
        try:
            art['byline_auto'] = compose_byline(article_authors_list(db, aid)) or art.get('author_name')
        except Exception:
            pass
        _localize_articles(db, [art])
        try:
            data, _fn = _dtp_artifact(db, 'gazette', str(aid), 'html',
                                      gen_args=('--article-id', aid),
                                      data={'art': art, 'enhancement': enh},
                                      title=row['title'], sig=sig)
        except ArtifactError as ae:
            return jsonify({'error': f'Gazette generation failed: {ae}'}), 503
        return send_file(io.BytesIO(data),
                         mimetype='text/html; charset=utf-8', as_attachment=True,
                         download_name=f'{safe}_gazette.html')
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/authors', methods=['GET'])
def get_authors():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM authors ORDER BY name').fetchall()
        result = []
        for r in rows:
            a = dict(r)
            a['article_count'] = db.execute("SELECT COUNT(*) FROM articles WHERE author_id=? AND status='published'", [a['id']]).fetchone()[0]
            result.append(a)
        return jsonify(result)
    finally:
        db.close()

@app.route('/api/authors', methods=['POST'])
def create_author():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        name = (data.get('name') or '').strip()
        if not name: return jsonify({'error': 'Name required'}), 400
        db.execute('INSERT INTO authors (name,email,bio,role,author_type,avatar_url,social_twitter,social_instagram) VALUES (?,?,?,?,?,?,?,?)',
            [name, data.get('email',''), data.get('bio',''), data.get('role',''),
             data.get('author_type','reporter'), data.get('avatar_url',''),
             data.get('social_twitter',''), data.get('social_instagram','')])
        aid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': aid}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/authors/<int:aid>', methods=['PUT'])
def update_author(aid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        db.execute('UPDATE authors SET name=?,email=?,bio=?,role=?,author_type=?,avatar_url=?,social_twitter=?,social_instagram=? WHERE id=?',
            [data.get('name',''), data.get('email',''), data.get('bio',''), data.get('role',''),
             data.get('author_type','reporter'), data.get('avatar_url',''),
             data.get('social_twitter',''), data.get('social_instagram',''), aid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/authors/<int:aid>', methods=['DELETE'])
def delete_author(aid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        db.execute('DELETE FROM authors WHERE id=?', [aid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/categories', methods=['GET'])
def get_categories():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
        result = []
        for r in rows:
            c = dict(r)
            c['article_count'] = db.execute("SELECT COUNT(*) FROM articles WHERE category_id=? AND status='published'", [c['id']]).fetchone()[0]
            result.append(c)
        return jsonify(result)
    finally:
        db.close()

@app.route('/api/categories', methods=['POST'])
def create_category():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        name = (data.get('name') or '').strip()
        if not name: return jsonify({'error': 'Name required'}), 400
        slug = slugify(name)
        ex = db.execute('SELECT id FROM categories WHERE slug=?', [slug]).fetchone()
        if ex: return jsonify({'id': ex['id'], 'slug': slug})
        db.execute('INSERT INTO categories (name,slug,description) VALUES (?,?,?)', [name, slug, data.get('description','')])
        cid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': cid, 'slug': slug}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def delete_category(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        db.execute('DELETE FROM categories WHERE id=?', [cid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/categories/<int:cid>', methods=['PUT'])
def rename_category(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        name = (data.get('name') or '').strip()
        if not name: return jsonify({'error': 'Name required'}), 400
        slug = slugify(name); n = 2
        while db.execute('SELECT 1 FROM categories WHERE slug=? AND id!=?', [slug, cid]).fetchone():
            slug = f'{slugify(name)}-{n}'; n += 1
        db.execute('UPDATE categories SET name=?,slug=?,description=? WHERE id=?',
                   [name, slug, data.get('description', ''), cid])
        db.commit(); return jsonify({'id': cid, 'name': name, 'slug': slug})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/categories/<int:cid>/merge', methods=['POST'])
def merge_category(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        into = (request.json or {}).get('into')
        if not into or int(into) == cid: return jsonify({'error': 'Pick a different target category'}), 400
        db.execute('UPDATE articles SET category_id=? WHERE category_id=?', [into, cid])
        db.execute('DELETE FROM categories WHERE id=?', [cid])
        db.commit(); return jsonify({'success': True, 'into': into})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/sections', methods=['GET'])
def get_sections():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT s.*, COUNT(a.id) as article_count "
            "FROM sections s LEFT JOIN articles a ON a.section_id=s.id AND a.status='published' "
            "GROUP BY s.id ORDER BY s.sort_order, s.name"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/sections/<int:sid>', methods=['PUT'])
def update_section(sid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        db.execute('UPDATE sections SET name=?,description=?,sort_order=? WHERE id=?',
                   [data.get('name'), data.get('description',''), data.get('sort_order',0), sid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/tags', methods=['GET'])
def get_tags():
    db = get_db()
    try:
        return jsonify(_ve_repo.list_tags(db))
    finally:
        db.close()

@app.route('/api/tags', methods=['POST'])
def create_tag():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        tag, created = _ve_repo.create_tag(db, (request.json or {}).get('name'), match='slug')
        return jsonify(tag), (201 if created else 200)
    except _ve_repo.Invalid as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/tags/<int:tid>', methods=['DELETE'])
def delete_tag(tid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        _ve_repo.delete_tag(db, tid)
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/tags/<int:tid>', methods=['PUT'])
def rename_tag(tid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        return jsonify(_ve_repo.rename_tag(db, tid, (request.json or {}).get('name')))
    except _ve_repo.Invalid as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/tags/<int:tid>/merge', methods=['POST'])
def merge_tag(tid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        return jsonify(_ve_repo.merge_tag(db, tid, (request.json or {}).get('into')))
    except _ve_repo.Invalid as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/upload', methods=['POST'])
def upload_image():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['file']
    if not f or not f.filename or not allowed_file(f.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    ext = f.filename.rsplit('.', 1)[1].lower()
    filename = f'{uuid.uuid4().hex}.{ext}'
    try:
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    db = get_db()
    try:
        db.execute('INSERT INTO images (filename,original_name,article_id) VALUES (?,?,?)',
            [filename, secure_filename(f.filename), request.form.get('article_id')])
        db.commit()
    finally:
        db.close()
    return jsonify({'url': f'/static/uploads/{filename}', 'filename': filename})

@app.route('/api/annotations', methods=['POST'])
def create_annotation():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Sign in to save annotations'}), 401
    db = get_db()
    try:
        data = request.json or {}
        if not data.get('article_id'): return jsonify({'error': 'article_id required'}), 400
        db.execute('INSERT INTO annotations (article_id,start_offset,end_offset,selected_text,note,color,user_id) VALUES (?,?,?,?,?,?,?)',
            [data['article_id'], data.get('start_offset'), data.get('end_offset'),
             (data.get('selected_text',''))[:500], data.get('note',''), data.get('color','#ffeb3b'), uid])
        aid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify(dict(db.execute('SELECT * FROM annotations WHERE id=?', [aid]).fetchone())), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/annotations/<int:ann_id>', methods=['DELETE'])
def delete_annotation(ann_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Sign in required'}), 401
    db = get_db()
    try:
        row = db.execute('SELECT user_id FROM annotations WHERE id=?', [ann_id]).fetchone()
        if not row: return jsonify({'error': 'Not found'}), 404
        if row['user_id'] != uid: return jsonify({'error': 'Unauthorized'}), 403
        db.execute('DELETE FROM annotations WHERE id=?', [ann_id])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/corrections', methods=['GET'])
def get_corrections(aid):
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM corrections WHERE article_id=? ORDER BY published_at DESC', [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/corrections', methods=['POST'])
def create_correction(aid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if not session.get('user_id'):
        return jsonify({'error': 'Login required'}), 401
    db = get_db()
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        body  = (data.get('body') or '').strip()
        if not title or not body:
            return jsonify({'error': 'title and body required'}), 400
        severity = data.get('severity', 'minor')
        if severity not in ('minor', 'major', 'retraction'):
            severity = 'minor'
        db.execute('INSERT INTO corrections (article_id,title,body,severity,published_by) VALUES (?,?,?,?,?)',
            [aid, title, body, severity, session.get('user_id')])
        cid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('UPDATE articles SET updated_at=? WHERE id=?', [datetime.utcnow().isoformat(), aid])
        record_history(db, aid, f'correction:{severity}')
        db.commit()
        return jsonify(dict(db.execute('SELECT * FROM corrections WHERE id=?', [cid]).fetchone())), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/corrections/<int:cid>', methods=['DELETE'])
def delete_correction(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if not session.get('user_id'):
        return jsonify({'error': 'Login required'}), 401
    db = get_db()
    try:
        db.execute('DELETE FROM corrections WHERE id=?', [cid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

SUPPORTED_LANGS = {'hi','fr','es','ar','zh','de'}
LANG_LABELS = {'hi':'हिंदी','fr':'Français','es':'Español','ar':'العربية','zh':'中文','de':'Deutsch'}
LANG_MM_CODE = {'en':'en','hi':'hi','fr':'fr','es':'es','ar':'ar','zh':'zh-CN','de':'de'}

def _mm_translate_chunk(text, source, target):
    if not text or not text.strip(): return text
    import json as _json
    q = urllib.parse.quote(text)
    url = f'https://api.mymemory.translated.net/get?q={q}&langpair={source}|{target}'
    req = _urllib_req.Request(url, headers={'User-Agent': 'Mozilla/5.0 (VoiceExpress translate)'})
    with _urllib_req.urlopen(req, timeout=10) as r:
        d = _json.loads(r.read().decode('utf-8'))
    t = (d.get('responseData') or {}).get('translatedText')
    if not t: raise RuntimeError(d.get('responseDetails') or 'translate failed')
    return t

def _mm_translate_text(text, source, target):
    if not text or not text.strip(): return text
    LIMIT = 450
    if len(urllib.parse.quote(text)) < LIMIT:
        return _mm_translate_chunk(text, source, target)
    parts = re.findall(r'[^.!?\n]+[.!?\n]*\s*', text) or [text]
    chunks, cur = [], ''
    for p in parts:
        if len(urllib.parse.quote(cur + p)) > LIMIT:
            if cur: chunks.append(cur)
            cur = p
        else:
            cur += p
    if cur: chunks.append(cur)
    return ''.join(_mm_translate_chunk(c, source, target) for c in chunks)

def _mm_translate_html(html, source, target):
    if not html: return html
    from bs4 import BeautifulSoup, NavigableString
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup.find_all(string=True):
        if isinstance(node, NavigableString) and node.strip():
            node.replace_with(_mm_translate_text(str(node), source, target))
    return str(soup)

@app.route('/api/translate', methods=['POST'])
def translate_article():
    db = get_db()
    try:
        data = request.json or {}
        article_id  = data.get('article_id')
        target_lang = data.get('target_language','')
        if not article_id: return jsonify({'error': 'article_id required'}), 400
        if target_lang not in SUPPORTED_LANGS: return jsonify({'error': 'Language not supported'}), 400
        ex = db.execute('SELECT * FROM translations WHERE article_id=? AND language=?', [article_id, target_lang]).fetchone()
        if ex: return jsonify(dict(ex))
        art = db.execute('SELECT * FROM articles WHERE id=?', [article_id]).fetchone()
        if not art: return jsonify({'error': 'Article not found'}), 404
        native = art['language'] or 'en'
        src_mm, tgt_mm = LANG_MM_CODE.get(native, native), LANG_MM_CODE.get(target_lang, target_lang)
        try:
            title   = _mm_translate_text(art['title'] or '', src_mm, tgt_mm)
            excerpt = _mm_translate_text(art['excerpt'] or '', src_mm, tgt_mm)
            content = _mm_translate_html(art['content'] or '', src_mm, tgt_mm)
        except Exception:
            return jsonify({'error': 'Translation service unavailable. Please try again.'}), 502
        db.execute('INSERT INTO translations (article_id,language,title,content,excerpt) VALUES (?,?,?,?,?)',
            [article_id, target_lang, title, content, excerpt])
        db.commit()
        return jsonify(dict(db.execute('SELECT * FROM translations WHERE article_id=? AND language=?', [article_id, target_lang]).fetchone()))
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/translation/<lang>', methods=['GET'])
def get_translation(aid, lang):
    db = get_db()
    try:
        t = db.execute('SELECT * FROM translations WHERE article_id=? AND language=?', [aid, lang]).fetchone()
        if not t: return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(t))
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/translations', methods=['GET'])
def get_all_translations(aid):
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM translations WHERE article_id=? ORDER BY language', [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/translations', methods=['POST'])
def save_translation(aid):
    db = get_db()
    try:
        data = request.json or {}
        lang = (data.get('language') or '').strip()
        if not lang: return jsonify({'error': 'language required'}), 400
        art = db.execute('SELECT id FROM articles WHERE id=?', [aid]).fetchone()
        if not art: return jsonify({'error': 'Article not found'}), 404
        uid = session.get('user_id')
        tname = None
        if uid:
            urow = db.execute('SELECT u.username, a.name FROM users u LEFT JOIN authors a ON u.author_id=a.id WHERE u.id=?', [uid]).fetchone()
            tname = (urow['name'] or urow['username']) if urow else None
        t_content = _normalize_html(data.get('content',''))
        ex = db.execute('SELECT id FROM translations WHERE article_id=? AND language=?', [aid, lang]).fetchone()
        if ex:
            db.execute('UPDATE translations SET title=?,content=?,excerpt=?,translator_id=?,translator_name=? WHERE article_id=? AND language=?',
                [data.get('title',''), t_content, data.get('excerpt',''), uid, tname, aid, lang])
        else:
            db.execute('INSERT INTO translations (article_id,language,title,content,excerpt,translator_id,translator_name) VALUES (?,?,?,?,?,?,?)',
                [aid, lang, data.get('title',''), t_content, data.get('excerpt',''), uid, tname])
        record_history(db, aid, 'translated', lang)
        db.commit()
        row = db.execute('SELECT * FROM translations WHERE article_id=? AND language=?', [aid, lang]).fetchone()
        return jsonify(dict(row)), 200
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/articles/<int:aid>/translation/<lang>', methods=['DELETE'])
def delete_translation(aid, lang):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        db.execute('DELETE FROM translations WHERE article_id=? AND language=?', [aid, lang])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/series', methods=['GET'])
def get_series():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM article_series ORDER BY title').fetchall()
        result = []
        for r in rows:
            s = dict(r)
            try:
                s['article_count'] = db.execute('SELECT COUNT(*) FROM articles WHERE series_id=?', [s['id']]).fetchone()[0]
            except Exception:
                s['article_count'] = 0
            result.append(s)
        return jsonify(result)
    finally:
        db.close()

@app.route('/api/series', methods=['POST'])
def create_series():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title: return jsonify({'error': 'Title required'}), 400
        sl = slugify(title)
        ex = db.execute('SELECT id FROM article_series WHERE slug=?', [sl]).fetchone()
        if ex: return jsonify({'error': 'A series with this title already exists'}), 409
        now = datetime.utcnow().isoformat()
        db.execute('INSERT INTO article_series (title,slug,description,cover_image,created_at) VALUES (?,?,?,?,?)',
            [title, sl, data.get('description',''), data.get('cover_image',''), now])
        sid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': sid, 'slug': sl, 'title': title}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/series/<int:sid>', methods=['GET'])
def get_series_one(sid):
    db = get_db()
    try:
        s = db.execute('SELECT * FROM article_series WHERE id=?', [sid]).fetchone()
        if not s: return jsonify({'error': 'Not found'}), 404
        d = dict(s)
        arts = db.execute('''SELECT a.id,a.title,a.slug,a.excerpt,a.featured_image,a.published_at,
            a.reading_time,a.series_order,au.name as author_name
            FROM articles a LEFT JOIN authors au ON a.author_id=au.id
            WHERE a.series_id=? ORDER BY a.series_order,a.published_at''', [sid]).fetchall()
        d['articles'] = [dict(a) for a in arts]
        return jsonify(d)
    finally:
        db.close()

@app.route('/api/series/<int:sid>', methods=['PUT'])
def update_series(sid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title: return jsonify({'error': 'Title required'}), 400
        db.execute('UPDATE article_series SET title=?,description=?,cover_image=? WHERE id=?',
            [title, data.get('description',''), data.get('cover_image',''), sid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/series/<int:sid>', methods=['DELETE'])
def delete_series(sid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        db.execute('UPDATE articles SET series_id=NULL,series_order=0 WHERE series_id=?', [sid])
        db.execute('DELETE FROM article_series WHERE id=?', [sid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

def _newsletter_covers(db):
    covers = {}
    try:
        rows = db.execute(
            "SELECT pub_type, filename, cover_image FROM publications "
            "WHERE cover_image IS NOT NULL AND cover_image <> '' "
            "AND pub_type IN ('broadsheet','magazine')").fetchall()
    except Exception:
        return covers
    for r in rows:
        m = re.search(r'(?:broadsheet|magazine)[_-](\d{4})[_-](\d{1,2})',
                      r['filename'] or '')
        if not m:
            continue
        key = (int(m.group(1)), int(m.group(2)))
        if key not in covers or r['pub_type'] == 'broadsheet':
            covers[key] = r['cover_image']
    return covers


@app.route('/api/newsletters', methods=['GET'])
def get_newsletters():
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM newsletters ORDER BY year DESC, month DESC').fetchall()
        covers = _newsletter_covers(db)
        result = []
        for r in rows:
            n = dict(r)
            if isinstance(n.get('content'), str):
                try: n['content'] = json.loads(n['content'])
                except: n['content'] = {}
            n['cover_image'] = covers.get((n.get('year'), n.get('month')))
            result.append(n)
        return jsonify(result)
    finally:
        db.close()

def _newsletter_stamp(db, ym):
    a = db.execute("SELECT MAX(updated_at) FROM articles WHERE status='published'"
                   ' AND substr(published_at,1,7)=?', [ym]).fetchone()[0] or ''
    c = db.execute("SELECT MAX(updated_at) FROM column_entries WHERE status='published'"
                   ' AND substr(entry_date,1,7)=?', [ym]).fetchone()[0] or ''
    return a + '|' + c


def _generate_newsletter(db, year, month, persist=True):
    ym = f'{year}-{month:02d}'
    row = db.execute('SELECT * FROM newsletters WHERE month=? AND year=?', [month, year]).fetchone()
    if row:
        n = dict(row)
        if isinstance(n.get('content'), str):
            try: n['content'] = json.loads(n['content'])
            except: n['content'] = {}
        cached = n.get('content') or {}
        live_a = db.execute("SELECT COUNT(*) FROM articles WHERE status='published'"
                            ' AND substr(published_at,1,7)=?', [ym]).fetchone()[0]
        live_c = db.execute("SELECT COUNT(*) FROM column_entries WHERE status='published'"
                            ' AND substr(entry_date,1,7)=?', [ym]).fetchone()[0]
        if (len(cached.get('articles') or []) == live_a
                and len(cached.get('columns') or []) == live_c
                and cached.get('stamp') == _newsletter_stamp(db, ym)):
            return n
        db.execute('DELETE FROM newsletters WHERE id=?', [n['id']])
        db.commit()
    articles = db.execute('''SELECT a.id,a.title,a.slug,a.excerpt,a.content,a.featured_image,
        a.published_at,a.reading_time,a.is_featured,au.name as author_name,c.name as category_name
        FROM articles a LEFT JOIN authors au ON a.author_id=au.id
        LEFT JOIN categories c ON a.category_id=c.id
        WHERE a.status='published' AND substr(a.published_at,1,7)=?
        ORDER BY a.is_featured DESC, a.published_at DESC''', [ym]).fetchall()
    col_entries = db.execute('''SELECT e.id,e.title,e.subtitle,e.cover_image,e.entry_date,
        col.title AS column_title, col.slug AS column_slug
        FROM column_entries e JOIN columns col ON col.id=e.column_id
        WHERE e.status='published' AND substr(e.entry_date,1,7)=?
        ORDER BY e.entry_date DESC''', [ym]).fetchall()
    month_name = calendar.month_name[month]
    content = {'articles': [dict(a) for a in articles],
        'columns': [dict(x) for x in col_entries],
        'month': month_name, 'year': year,
        'stamp': _newsletter_stamp(db, ym),
        'editorial': (f'Welcome to the {month_name} {year} edition of Voice Express. '
                      f'Our correspondents bring you the stories that matter, from frontlines '
                      f'of policy to quiet revolutions in culture and science.')}
    title = f'The Voice Express · {month_name} {year}'
    pub_at = datetime.utcnow().isoformat()
    if not persist or (not content['articles'] and not content['columns']):
        return {'id': None, 'title': title, 'month': month, 'year': year,
                'content': content, 'status': 'published', 'published_at': pub_at}
    db.execute('INSERT INTO newsletters (title,month,year,content,status,published_at) VALUES (?,?,?,?,?,?)',
        [title, month, year, json.dumps(content), 'published', pub_at])
    nid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    if _gen_icon:
        try:
            _imgs  = [a.get('featured_image', '') for a in content['articles'] if a.get('featured_image')]
            _ntags = []
            for _a in content['articles']:
                _raw = _a.get('tags') or _a.get('tag_names') or ''
                if isinstance(_raw, list):  _ntags.extend(_raw)
                elif _raw:                  _ntags.extend(re.split(r'[,;]+', _raw))
            _cover = _gen_icon('newsletter', _ntags[:20], title, seed=nid, article_images=_imgs)
            if _cover:
                content['cover_image'] = _cover
                db.execute('UPDATE newsletters SET content=? WHERE id=?', [json.dumps(content), nid])
        except Exception as _nie:
            print(f'[newsletter] icon error: {_nie}')
    db.commit()
    return {'id': nid, 'title': title, 'month': month, 'year': year,
            'content': content, 'status': 'published', 'published_at': pub_at}


@app.route('/api/newsletters/current', methods=['GET'])
def get_current_newsletter():
    now = datetime.utcnow()
    db = get_db()
    try:
        return jsonify(_generate_newsletter(db, now.year, now.month))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/newsletters/range', methods=['GET'])
def newsletter_range():
    db = get_db()
    try:
        now = datetime.utcnow()
        cur = f'{now.year}-{now.month:02d}'
        lo  = db.execute("SELECT MIN(substr(published_at,1,7)) FROM articles "
                         "WHERE status='published' AND published_at IS NOT NULL").fetchone()[0]
        loe = db.execute("SELECT MIN(substr(entry_date,1,7)) FROM column_entries "
                         "WHERE status='published'").fetchone()[0]
        cand = [x for x in (lo, loe) if x]
        return jsonify({'min': (min(cand) if cand else cur), 'max': cur})
    finally:
        db.close()

@app.route('/api/newsletters/months', methods=['GET'])
def newsletter_months():
    db = get_db()
    try:
        now = datetime.utcnow()
        cur = f'{now.year}-{now.month:02d}'
        rows = db.execute('''
            SELECT ym, SUM(ac) AS ac, SUM(cc) AS cc FROM (
              SELECT substr(published_at,1,7) AS ym, COUNT(*) AS ac, 0 AS cc FROM articles
                WHERE status='published' AND published_at IS NOT NULL GROUP BY ym
              UNION ALL
              SELECT substr(entry_date,1,7) AS ym, 0 AS ac, COUNT(*) AS cc FROM column_entries
                WHERE status='published' GROUP BY ym
            ) GROUP BY ym ORDER BY ym DESC''').fetchall()
        pub_covers = _newsletter_covers(db)
        out = []
        for r in rows:
            ym = r['ym']
            if not ym or ym > cur:
                continue
            y, m = int(ym[:4]), int(ym[5:7])
            title = f'The Voice Express · {calendar.month_name[m]} {y}'
            cover = pub_covers.get((y, m))
            if not cover and _spiral_icon:
                try:
                    arows = db.execute("SELECT title, content FROM articles WHERE status='published' "
                                       "AND substr(published_at,1,7)=? ORDER BY is_featured DESC, published_at", [ym]).fetchall()
                    phrases = []
                    for ar in arows:
                        if ar['title']: phrases.append(ar['title'])
                        for q in re.findall(r'<blockquote[^>]*>(.*?)</blockquote>', ar['content'] or '', re.S):
                            qt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', q)).strip()
                            if 8 < len(qt) < 150: phrases.append('“' + qt + '”')
                    cover = _spiral_icon(y * 100 + m, phrases[:40])
                except Exception: cover = None
            if not cover:
                cov = db.execute("SELECT featured_image FROM articles WHERE status='published' "
                                 "AND substr(published_at,1,7)=? AND featured_image IS NOT NULL "
                                 "AND featured_image!='' ORDER BY is_featured DESC, published_at DESC "
                                 "LIMIT 1", [ym]).fetchone()
                cover = cov['featured_image'] if cov else None
            out.append({'year': y, 'month': m, 'title': title,
                        'article_count': r['ac'] or 0, 'column_count': r['cc'] or 0,
                        'cover_image': cover})
        return jsonify(out)
    finally:
        db.close()

@app.route('/api/newsletters/<int:year>/<int:month>', methods=['GET'])
def get_newsletter_month(year, month):
    if month < 1 or month > 12:
        return jsonify({'error': 'bad month'}), 400
    db = get_db()
    try:
        return jsonify(_generate_newsletter(db, year, month))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/newsletters/regenerate', methods=['POST'])
def regenerate_newsletter():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    data  = request.json or {}
    now   = datetime.utcnow()
    year  = int(data.get('year')  or now.year)
    month = int(data.get('month') or now.month)
    db = get_db()
    try:
        db.execute('DELETE FROM newsletters WHERE month=? AND year=?', [month, year])
        db.commit()
        return jsonify(_generate_newsletter(db, year, month))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

def _month_has_column_entries(db, ym):
    try:
        row = db.execute(
            "SELECT COUNT(*) n FROM column_entries e JOIN columns c ON c.id=e.column_id "
            "WHERE e.status='published' AND substr(e.entry_date,1,7)=? "
            "AND COALESCE(c.is_private,0)=0", [ym]).fetchone()
        return bool(row and row['n'])
    except Exception:
        return False


def _column_entries_as_articles(db, ym):
    out = []
    try:
        rows = db.execute(
            "SELECT e.*, c.id AS _col_id FROM column_entries e "
            "JOIN columns c ON c.id = e.column_id "
            "WHERE e.status='published' AND substr(e.entry_date,1,7)=? "
            "ORDER BY e.entry_date, e.sort_order", [ym]).fetchall()
        for e in rows:
            col = db.execute('SELECT * FROM columns WHERE id=?', [e['_col_id']]).fetchone()
            if not col or col['is_private']:
                continue
            byline = compose_byline(column_authors_list(db, col['id']))
            art = _entry_to_article(db, col, e, byline)
            art['byline_auto'] = byline
            out.append(art)
    except Exception as ex:
        print(f'[broadsheet] column-entry conversion failed for {ym}: {ex}')
    return out


@app.route('/api/newsletters/<int:year>/<int:month>/broadsheet', methods=['GET'])
def newsletter_broadsheet(year, month):
    if not _NL_BROADSHEET_OK:
        return jsonify({'error': 'Broadsheet generator unavailable'}), 503
    if month < 1 or month > 12:
        return jsonify({'error': 'bad month'}), 400
    db = get_db()
    try:
        ed = _generate_newsletter(db, year, month)
        content = ed.get('content', {}) or {}
        if not content.get('articles') and not content.get('columns'):
            if not _month_has_column_entries(db, f'{year}-{month:02d}'):
                return jsonify({'error': 'No content for this month'}), 404
        for a in content.get('articles', []):
            try:
                a['byline_auto'] = compose_byline(article_authors_list(db, a['id'])) or a.get('author_name')
                srow = db.execute('SELECT s.name FROM articles ar LEFT JOIN sections s '
                                  'ON ar.section_id=s.id WHERE ar.id=?', [a['id']]).fetchone()
                if srow and srow[0]:
                    a['section_name'] = srow[0]
            except Exception:
                pass
        ym = f'{year}-{month:02d}'

        enh = get_pdf_enhancement(db, 'broadsheet', ym)
        sig = f'{_month_sig(db, ym)}|{json.dumps(enh, sort_keys=True)}'
        gen_data = {'articles': content.get('articles')}

        fmt = (request.args.get('format') or '').lower()
        if fmt == 'scroll':
            if not _NL_BROADSHEET_SCROLL_OK:
                return jsonify({'error': 'Broadsheet scroll generator unavailable'}), 503
            scroll_articles = content.get('articles') or []
            if not scroll_articles:
                scroll_articles = _column_entries_as_articles(db, ym)
            html_str = build_broadsheet_scroll(ym, articles=scroll_articles)
            if html_str is None:
                return jsonify({'error': 'No content for this month'}), 404
            return send_file(io.BytesIO(html_str.encode('utf-8')),
                             mimetype='text/html; charset=utf-8', as_attachment=False,
                             download_name=f'voice-express-broadsheet-scroll-{year}-{month:02d}.html')

        want_pdf = fmt == 'pdf'
        try:
            data, _fn = _dtp_artifact(db, 'broadsheet', ym, 'pdf' if want_pdf else 'html',
                                      gen_args=('--ym', ym), data=gen_data,
                                      title=f'The Voice Express - {ym}', sig=sig)
        except ArtifactError as ae:
            return jsonify({'error': f'Broadsheet generation failed: {ae}'}), 503
        if want_pdf:
            return send_file(io.BytesIO(data), mimetype='application/pdf', as_attachment=True,
                             download_name=f'voice-express-broadsheet-{year}-{month:02d}.pdf')
        inline = fmt == 'view'
        return send_file(io.BytesIO(data),
                         mimetype='text/html; charset=utf-8', as_attachment=not inline,
                         download_name=f'voice-express-broadsheet-{year}-{month:02d}.html')
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

def _html_to_pdf(html_str):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                b = p.chromium.launch(headless=True)
            pg = b.new_page()
            pg.set_content(html_str, wait_until='load')
            pdf = pg.pdf(prefer_css_page_size=True, print_background=True,
                         margin={'top': '0mm', 'right': '0mm', 'bottom': '0mm', 'left': '0mm'})
            b.close()
            return pdf
    except Exception as _pe:
        print(f'[broadsheet pdf] {_pe}')
        return None

def _design_source_html(design_type, target_id):
    db = get_db()
    try:
        if design_type == 'article':
            row = db.execute("SELECT a.*,au.name as author_name,c.name as category_name,"
                             "s.name as section_name FROM articles a "
                             "LEFT JOIN authors au ON a.author_id=au.id "
                             "LEFT JOIN categories c ON a.category_id=c.id "
                             "LEFT JOIN sections s ON a.section_id=s.id "
                             "WHERE a.id=?", [target_id]).fetchone()
            if not row:
                return None, (jsonify({'error': 'Article not found'}), 404)
            enh = get_pdf_enhancement(db, 'gazette', str(target_id))
            art = _article_print_dict(db, row)
            _localize_articles(db, [art])
            sig = f'{row["updated_at"]}|{json.dumps(enh, sort_keys=True)}'
            data, _fn = _dtp_artifact(db, 'gazette', str(target_id), 'html',
                                      gen_args=('--article-id', target_id),
                                      data={'art': art, 'enhancement': enh},
                                      title=row['title'], sig=sig)
            return data.decode('utf-8'), None

        if design_type == 'broadsheet':
            nl = db.execute('SELECT * FROM newsletters WHERE id=?', [target_id]).fetchone()
            if not nl:
                return None, (jsonify({'error': 'Newsletter not found'}), 404)
            try:
                content = json.loads(nl['content'] or '{}')
            except (json.JSONDecodeError, TypeError):
                content = {}
            year = content.get('year') or nl['year']
            month = content.get('month') or nl['month']
            ym = f'{int(year)}-{int(month):02d}'
            enh = get_pdf_enhancement(db, 'broadsheet', ym)
            sig = f'{_month_sig(db, ym)}|{json.dumps(enh, sort_keys=True)}'
            data, _fn = _dtp_artifact(db, 'broadsheet', ym, 'html',
                                      gen_args=('--ym', ym),
                                      data={'articles': content.get('articles')},
                                      title=f'The Voice Express - {ym}', sig=sig)
            return data.decode('utf-8'), None

        return None, (jsonify({'error': 'Unknown design type'}), 400)
    finally:
        db.close()


@app.route('/api/design/preview/<design_type>/<int:target_id>')
def design_preview(design_type, target_id):
    if not _DESIGN_EDITOR_OK:
        return jsonify({'error': 'Design editor not available'}), 503

    try:
        html, err = _design_source_html(design_type, target_id)
    except ArtifactError as ae:
        return jsonify({'error': f'Preview generation failed: {ae}'}), 503
    if err:
        return err

    custom_css = get_custom_css(design_type, target_id)
    html = render_html_with_custom_css(html, custom_css)
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/design/custom-css/<design_type>/<int:target_id>', methods=['GET', 'POST'])
def design_custom_css(design_type, target_id):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    if not _DESIGN_EDITOR_OK:
        return jsonify({'error': 'Design editor not available'}), 503

    if request.method == 'GET':
        css = get_custom_css(design_type, target_id)
        return jsonify({'custom_css': css})

    data = request.json or {}
    custom_css = data.get('custom_css', '')
    save_custom_css(design_type, target_id, custom_css)
    return jsonify({'success': True})


@app.route('/api/design/editor/<design_type>/<int:target_id>')
def design_editor(design_type, target_id):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    if not _DESIGN_EDITOR_OK:
        return jsonify({'error': 'Design editor not available'}), 503

    html = EDITOR_TEMPLATE.replace('__TYPE__', design_type).replace('__ID__', str(target_id))
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/design/generate-pdf/<design_type>/<int:target_id>', methods=['POST'])
def design_generate_pdf(design_type, target_id):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    if not _DESIGN_EDITOR_OK:
        return jsonify({'error': 'Design editor not available'}), 503

    data = request.json or {}
    custom_css = data.get('custom_css', '')

    try:
        html, err = _design_source_html(design_type, target_id)
    except ArtifactError as ae:
        return jsonify({'error': f'PDF generation failed: {ae}'}), 503
    if err:
        return err

    html = render_html_with_custom_css(html, custom_css)
    pdf = _html_to_pdf(html)

    if not pdf:
        return jsonify({'error': 'PDF rendering failed'}), 500

    pdf_path = os.path.join(_CACHE_DIR, f'design_{design_type}_{target_id}.pdf')
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(pdf)

    return jsonify({'success': True, 'pdf_path': pdf_path})


@app.route('/api/design/screenshots/<design_type>/<int:target_id>', methods=['GET', 'POST'])
def design_screenshots(design_type, target_id):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    if not _DESIGN_EDITOR_OK:
        return jsonify({'error': 'Design editor not available'}), 503

    if request.method == 'GET':
        screenshots = get_screenshots(design_type, target_id)
        return jsonify({'screenshots': screenshots})

    pdf_path = os.path.join(_CACHE_DIR, f'design_{design_type}_{target_id}.pdf')
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'PDF not found. Generate PDF first.'}), 404

    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        screenshots_b64 = capture_pdf_screenshots(pdf_bytes, max_pages=5)
        if screenshots_b64:
            save_screenshots(design_type, target_id, screenshots_b64)
        return jsonify({'success': True, 'page_count': len(screenshots_b64)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/newsletters/<int:nid>', methods=['PUT'])
def update_newsletter(nid):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json or {}
    db = get_db()
    try:
        row = db.execute('SELECT id,content FROM newsletters WHERE id=?', [nid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        content = {}
        try: content = json.loads(row['content'] or '{}')
        except: pass
        if 'editorial' in data:
            content['editorial'] = data['editorial']
        fields, params = ['content=?'], [json.dumps(content, ensure_ascii=False)]
        if 'title' in data:
            fields.append('title=?')
            params.append(str(data['title'])[:200])
        params.append(nid)
        db.execute(f"UPDATE newsletters SET {','.join(fields)} WHERE id=?", params)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/newsletters/<int:nid>', methods=['DELETE'])
def delete_newsletter(nid):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    try:
        row = db.execute('SELECT id FROM newsletters WHERE id=?', [nid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        db.execute('DELETE FROM newsletters WHERE id=?', [nid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
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
    return _ve_repo.entry_dict(db, row, with_panels, with_names=True)

@app.route('/api/columns', methods=['GET'])
def list_columns():
    db = get_db()
    try:
        status = request.args.get('status', 'published')
        q = 'SELECT * FROM columns'
        where, p = [], []
        if status != 'all':
            where.append('status=?'); p.append(status)
        if session.get('role') not in ('admin', 'editor'):
            where.append('is_private=0')
        if where:
            q += ' WHERE ' + ' AND '.join(where)
        q += ' ORDER BY is_featured DESC, sort_order, title'
        return jsonify([_column_dict(db, r) for r in db.execute(q, p).fetchall()])
    finally:
        db.close()

@app.route('/api/columns/<slug>', methods=['GET'])
def get_column(slug):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM columns WHERE slug=? OR id=?', [slug, slug]).fetchone()
        if not row: return jsonify({'error': 'Not found'}), 404
        if row['is_private'] and session.get('role') not in ('admin', 'editor'):
            return jsonify({'error': 'Not found'}), 404
        d = _column_dict(db, row)
        only_pub = request.args.get('status', 'published') != 'all'
        d['entries'] = _ve_repo.list_entries(db, d['id'], only_published=only_pub, with_names=True)
        return jsonify(d)
    finally:
        db.close()

@app.route('/api/columns', methods=['POST'])
def create_column():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title: return jsonify({'error': 'Title required'}), 400
        slug = _column_unique_slug(db, data.get('slug') or title)
        now = datetime.utcnow().isoformat()
        db.execute('''INSERT INTO columns (title,slug,subtitle,description,cover_image,cadence,
            period_days,accent,status,is_featured,sort_order,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', [
            title, slug, data.get('subtitle',''), data.get('description',''),
            data.get('cover_image',''), data.get('cadence','weekly'),
            int(data.get('period_days') or 7), data.get('accent',''),
            data.get('status','draft'), 1 if data.get('is_featured') else 0,
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
def update_column(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        ex = db.execute('SELECT * FROM columns WHERE id=?', [cid]).fetchone()
        if not ex: return jsonify({'error': 'Not found'}), 404
        slug = _column_unique_slug(db, data.get('slug') or data.get('title') or ex['title'], cid) \
            if (data.get('slug') or data.get('title')) else ex['slug']
        db.execute('''UPDATE columns SET title=?,slug=?,subtitle=?,description=?,cover_image=?,
            cadence=?,period_days=?,accent=?,status=?,is_featured=?,sort_order=?,updated_at=? WHERE id=?''', [
            (data.get('title') or ex['title']).strip(), slug,
            data.get('subtitle', ex['subtitle'] or ''), data.get('description', ex['description'] or ''),
            data.get('cover_image', ex['cover_image'] or ''), data.get('cadence', ex['cadence']),
            int(data.get('period_days', ex['period_days']) or 7), data.get('accent', ex['accent'] or ''),
            data.get('status', ex['status']), 1 if data.get('is_featured', ex['is_featured']) else 0,
            int(data.get('sort_order', ex['sort_order']) or 0), datetime.utcnow().isoformat(), cid])
        if 'authors' in data:
            set_column_authors(db, cid, data.get('authors'))
        db.commit()
        return jsonify({'success': True, 'slug': slug})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/columns/<int:cid>', methods=['DELETE'])
def delete_column(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        db.execute('DELETE FROM columns WHERE id=?', [cid])
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()

@app.route('/api/columns/<int:cid>/calendar', methods=['GET'])
def column_calendar(cid):
    db = get_db()
    try:
        col = db.execute('SELECT is_private FROM columns WHERE id=?', [cid]).fetchone()
        if not col: return jsonify({'error': 'Not found'}), 404
        if col['is_private'] and session.get('role') not in ('admin', 'editor'):
            return jsonify({'error': 'Not found'}), 404
        q = "SELECT * FROM column_entries WHERE column_id=?"
        p = [cid]
        only_pub = request.args.get('status', 'published') != 'all'
        if only_pub: q += " AND status='published'"
        ym = request.args.get('month')
        if ym: q += " AND entry_date LIKE ?"; p.append(ym + '%')
        q += ' ORDER BY entry_date, sort_order'
        out = {}
        for r in db.execute(q, p).fetchall():
            out.setdefault(r['entry_date'], []).append(_entry_dict(db, r, with_panels=False))
        return jsonify(out)
    finally:
        db.close()

@app.route('/api/column-entries/<int:eid>', methods=['GET'])
def get_column_entry(eid):
    db = get_db()
    try:
        try:
            d = _ve_repo.get_entry(db, eid, with_private=True, with_names=True)
        except _ve_repo.Missing as e:
            return jsonify({'error': str(e)}), 404
        if d['is_private'] and session.get('role') not in ('admin', 'editor'):
            return jsonify({'error': 'Not found'}), 404
        return jsonify(d)
    finally:
        db.close()

@app.route('/api/columns/<int:cid>/entries', methods=['POST'])
def create_column_entry(cid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        eid = _ve_repo.create_entry(db, cid, request.json or {}, datetime.utcnow().isoformat(), _normalize_html)
        return jsonify({'id': eid}), 201
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/column-entries/<int:eid>', methods=['PUT'])
def update_column_entry(eid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        _ve_repo.update_entry(db, eid, request.json or {}, datetime.utcnow().isoformat(), _normalize_html)
        return jsonify({'success': True})
    except _ve_repo.Missing as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/column-entries/<int:eid>', methods=['DELETE'])
def delete_column_entry(eid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        _ve_repo.delete_entry(db, eid, purge_children=True)
        return jsonify({'success': True})
    finally:
        db.close()

def _entry_to_article(db, col, entry, byline):
    body = entry['body'] or ''
    panels = db.execute('SELECT * FROM column_panels WHERE entry_id=? ORDER BY sort_order, id', [entry['id']]).fetchall()
    if panels:
        gtype = entry['layout'] if entry['layout'] in ('comic', 'grid', 'sequence') else 'grid'
        figs = []
        for p in panels:
            if not p['image']:
                continue
            cap = ''
            if p['caption']:
                cls = ' class="panel-caption"' if gtype == 'comic' else ''
                cap = f'<figcaption{cls}>{p["caption"]}</figcaption>'
            figs.append(f'<figure><img src="{p["image"]}" alt="">{cap}</figure>')
        if figs:
            body += f'<div class="photo-group" data-type="{gtype}">' + ''.join(figs) + '</div>'
    return {'id': entry['id'], 'title': entry['title'], 'content': body,
            'excerpt': entry['subtitle'] or '', 'featured_image': entry['cover_image'] or '',
            'byline_auto': byline, 'author_name': byline, 'byline': byline,
            'category_name': col['title'], 'published_at': entry['entry_date'],
            'tag_ids': _ve_tags.entry_tag_ids(db, entry['id']),
            'tags': _ve_tags.entry_tag_names(db, entry['id'])}

@app.route('/api/columns/<int:cid>/booklet', methods=['GET', 'POST'])
def column_booklet(cid):
    if not _PRINTABLES_OK:
        return jsonify({'error': 'Printables unavailable'}), 503
    db = get_db()
    try:
        col = db.execute('SELECT * FROM columns WHERE id=?', [cid]).fetchone()
        if not col:
            return jsonify({'error': 'Column not found'}), 404
        if col['is_private'] and session.get('role') not in ('admin', 'editor'):
            return jsonify({'error': 'Column not found'}), 404
        byline = compose_byline(column_authors_list(db, cid))
        period = (request.args.get('period') or 'all').lower()
        if period not in ('week', 'month', 'year', 'all'): period = 'all'
        frm = (request.args.get('from') or '').strip()
        to  = (request.args.get('to') or '').strip()
        q = "SELECT * FROM column_entries WHERE column_id=? AND status='published'"; p = [cid]
        if frm: q += " AND substr(entry_date,1,10)>=?"; p.append(frm)
        if to:  q += " AND substr(entry_date,1,10)<=?"; p.append(to)
        q += " ORDER BY entry_date, sort_order"
        entries = db.execute(q, p).fetchall()
        if not entries:
            return jsonify({'error': 'No published entries to compile'}), 400
        arts = [_entry_to_article(db, col, e, byline) for e in entries]
        for a in arts: a['byline_auto'] = byline
        title = col['title']
        label = (f'{frm} – {to}' if frm and to else (frm or to or '')).strip()
        safe = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:60] or 'booklet'
        if label:
            pub_title = f'{title} — Booklet, {label}'
        elif period != 'all':
            pub_title = f'{title} — Booklet, this {period}'
        else:
            pub_title = f'{title} — Booklet, all time'

        enh = get_pdf_enhancement(db, 'column_booklet', cid)
        sig = hashlib.md5(('|'.join(f'{e["id"]}:{e["updated_at"]}' for e in entries)
                           + '|' + json.dumps(enh, sort_keys=True)).encode()).hexdigest()
        try:
            data, _fn = _dtp_artifact(db, 'booklet', f'{cid}:{period}:{label}', 'html',
                                      gen_args=('--column-id', cid, '--period', period,
                                                '--label', label),
                                      data={'articles': arts, 'col_row': dict(col), 'enhancement': enh},
                                      title=pub_title, sig=sig)
        except ArtifactError as ae:
            return jsonify({'error': f'Booklet generation failed: {ae}'}), 503
        try:
            entry_imgs = [e['cover_image'] for e in entries if e['cover_image']]
            cover = None
            if _gen_icon and entry_imgs:
                cover = _gen_icon('compilation', [], f'{title} {label or period}',
                                  seed=cid * 1000 + (hash(label or period) % 997),
                                  article_images=entry_imgs)
            cover = cover or col['cover_image']
            if cover:
                db.execute('UPDATE publications SET cover_image=? WHERE filename=?',
                           [cover, _fn])
                db.commit()
        except Exception as _ce:
            print(f'[booklet] could not stamp compilation cover: {_ce}')
        return send_file(io.BytesIO(data), mimetype='text/html; charset=utf-8',
                         as_attachment=True, download_name=f'{safe}_booklet.html')
    finally:
        db.close()

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    uid = session.get('user_id')
    if not uid: return jsonify(None)
    db = get_db()
    try:
        row = db.execute('SELECT id,username,role,author_id FROM users WHERE id=?', [uid]).fetchone()
        if not row: session.clear(); return jsonify(None)
        return jsonify(dict(row))
    finally: db.close()

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    db = get_db()
    try:
        row = db.execute('SELECT * FROM users WHERE username=?', [username]).fetchone()
        if not row or not check_password_hash(row['password_hash'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        session['user_id'] = row['id']
        session['role']    = row['role']
        session['username']= row['username']
        db.execute('UPDATE users SET last_login=? WHERE id=?', [datetime.utcnow().isoformat(), row['id']])
        db.commit()
        return jsonify({'id': row['id'], 'username': row['username'], 'role': row['role'], 'author_id': row['author_id']})
    finally: db.close()

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/register-reader', methods=['POST'])
def register_reader():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email    = (data.get('email') or '').strip() or None
    if not username or not password: return jsonify({'error': 'Username and password required'}), 400
    if len(password) < 6: return jsonify({'error': 'Password must be at least 6 characters'}), 400
    db = get_db()
    try:
        db.execute('INSERT INTO users (username,password_hash,role,email) VALUES (?,?,?,?)',
            [username, generate_password_hash(password), 'reader', email])
        uid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        session['user_id'] = uid
        return jsonify({'id': uid, 'username': username, 'role': 'reader', 'author_id': None}), 201
    except Exception as e:
        db.rollback()
        if 'UNIQUE' in str(e): return jsonify({'error': 'Username already taken'}), 409
        return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/reader/track', methods=['POST'])
def track_read():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    aid = (request.json or {}).get('article_id')
    if not aid: return jsonify({'error': 'article_id required'}), 400
    db = get_db()
    try:
        now = datetime.utcnow().isoformat()
        ex = db.execute('SELECT id,read_count FROM reading_history WHERE user_id=? AND article_id=?', [uid, aid]).fetchone()
        if ex: db.execute('UPDATE reading_history SET read_at=?,read_count=? WHERE id=?', [now, ex['read_count']+1, ex['id']])
        else:  db.execute('INSERT INTO reading_history (user_id,article_id,read_at) VALUES (?,?,?)', [uid, aid, now])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/reader/history', methods=['GET'])
def get_history():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    db = get_db()
    try:
        rows = db.execute('''SELECT rh.read_at,rh.read_count,a.id,a.title,a.slug,a.excerpt,
            a.featured_image,a.published_at,a.reading_time,au.name as author_name,c.name as category_name
            FROM reading_history rh JOIN articles a ON rh.article_id=a.id
            LEFT JOIN authors au ON a.author_id=au.id LEFT JOIN categories c ON a.category_id=c.id
            WHERE rh.user_id=? ORDER BY rh.read_at DESC LIMIT 60''', [uid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/reader/puzzle-complete', methods=['POST'])
def record_puzzle_complete():
    uid = session.get('user_id')
    if not uid: return jsonify({'success': True})
    data = request.json or {}
    db = get_db()
    try:
        db.execute('''INSERT INTO user_puzzle_completions (user_id,puzzle_type,puzzle_date,difficulty,elapsed,completed_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(user_id,puzzle_type,puzzle_date,difficulty) DO UPDATE SET
            elapsed=MIN(elapsed,excluded.elapsed),completed_at=excluded.completed_at''',
            [uid, data.get('type',''), data.get('date',''), data.get('difficulty',''),
             data.get('elapsed',0), datetime.utcnow().isoformat()])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/reader/puzzle-stats', methods=['GET'])
def get_puzzle_stats():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM user_puzzle_completions WHERE user_id=? ORDER BY completed_at DESC LIMIT 100', [uid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/reader/profile', methods=['GET'])
def get_reader_profile():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    db = get_db()
    try:
        u = db.execute('SELECT id,username,role,email,created_at FROM users WHERE id=?', [uid]).fetchone()
        if not u: return jsonify({'error': 'Not found'}), 404
        d = dict(u)
        d['article_count'] = db.execute('SELECT COUNT(*) FROM reading_history WHERE user_id=?', [uid]).fetchone()[0]
        d['puzzle_count']  = db.execute('SELECT COUNT(*) FROM user_puzzle_completions WHERE user_id=?', [uid]).fetchone()[0]
        return jsonify(d)
    finally: db.close()

@app.route('/api/reader/profile', methods=['PUT'])
def update_reader_profile():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    data = request.json or {}
    db = get_db()
    try:
        if data.get('password'):
            if len(data['password']) < 6: return jsonify({'error': 'Min 6 characters'}), 400
            db.execute('UPDATE users SET password_hash=? WHERE id=?', [generate_password_hash(data['password']), uid])
        if 'email' in data:
            db.execute('UPDATE users SET email=? WHERE id=?', [data['email'] or None, uid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    db = get_db()
    try:
        author_id = data.get('author_id') or None
        db.execute('INSERT INTO users (username,password_hash,role,author_id) VALUES (?,?,?,?)',
            [username, generate_password_hash(password), data.get('role','author'), author_id])
        uid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': uid, 'username': username}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/auth/users', methods=['GET'])
def auth_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    db = get_db()
    try:
        rows = db.execute('''SELECT u.id,u.username,u.role,u.author_id,u.last_login,a.name as author_name
            FROM users u LEFT JOIN authors a ON u.author_id=a.id ORDER BY u.username''').fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/auth/users/<int:uid>/password', methods=['PUT'])
def auth_change_password(uid):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    data = request.json or {}
    pw = data.get('password','')
    if len(pw) < 6: return jsonify({'error': 'Min 6 characters'}), 400
    db = get_db()
    try:
        db.execute('UPDATE users SET password_hash=? WHERE id=?', [generate_password_hash(pw), uid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/auth/users/<int:uid>', methods=['DELETE'])
def auth_delete_user(uid):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    db = get_db()
    try:
        db.execute('DELETE FROM users WHERE id=?', [uid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/authors/<int:aid>/links', methods=['GET'])
def get_author_links(aid):
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM author_links WHERE author_id=? ORDER BY sort_order,id', [aid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/authors/<int:aid>/links', methods=['POST'])
def add_author_link(aid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        if not data.get('title') or not data.get('url'):
            return jsonify({'error': 'title and url required'}), 400
        max_order = db.execute('SELECT COALESCE(MAX(sort_order),0) FROM author_links WHERE author_id=?', [aid]).fetchone()[0]
        db.execute('INSERT INTO author_links (author_id,title,url,link_type,sort_order) VALUES (?,?,?,?,?)',
            [aid, data['title'], data['url'], data.get('link_type','other'), max_order+1])
        lid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify(dict(db.execute('SELECT * FROM author_links WHERE id=?', [lid]).fetchone())), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/authors/links/<int:lid>', methods=['PUT'])
def update_author_link(lid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        data = request.json or {}
        db.execute('UPDATE author_links SET title=?,url=?,link_type=? WHERE id=?',
            [data.get('title',''), data.get('url',''), data.get('link_type','other'), lid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/authors/links/<int:lid>', methods=['DELETE'])
def delete_author_link(lid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        db.execute('DELETE FROM author_links WHERE id=?', [lid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/puzzles/session', methods=['GET'])
def get_puzzle_session():
    db = get_db()
    try:
        ptype = request.args.get('type', '')
        pdate = request.args.get('date', '')
        difficulty = request.args.get('difficulty', '')
        if not ptype or not pdate:
            return jsonify({'error': 'type and date required'}), 400
        row = db.execute(
            'SELECT * FROM puzzle_sessions WHERE puzzle_type=? AND puzzle_date=? AND difficulty=?',
            [ptype, pdate, difficulty]
        ).fetchone()
        if not row:
            return jsonify(None)
        return jsonify(dict(row))
    finally:
        db.close()

@app.route('/api/puzzles/session', methods=['POST'])
def save_puzzle_session():
    db = get_db()
    try:
        data = request.json or {}
        ptype = data.get('type', '')
        pdate = data.get('date', '')
        difficulty = data.get('difficulty', '')
        if not ptype or not pdate:
            return jsonify({'error': 'type and date required'}), 400
        state = json.dumps(data.get('state')) if data.get('state') is not None else None
        elapsed = int(data.get('elapsed', 0))
        completed = 1 if data.get('completed') else 0
        now = datetime.utcnow().isoformat()
        db.execute('''INSERT INTO puzzle_sessions (puzzle_type,puzzle_date,difficulty,state,elapsed,completed,updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(puzzle_type,puzzle_date,difficulty) DO UPDATE SET
            state=excluded.state, elapsed=excluded.elapsed, completed=excluded.completed, updated_at=excluded.updated_at''',
            [ptype, pdate, difficulty, state, elapsed, completed, now])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/puzzles/archive', methods=['GET'])
def get_puzzle_archive():
    db = get_db()
    try:
        ptype = request.args.get('type', '')
        difficulty = request.args.get('difficulty', '')
        if not ptype:
            return jsonify({'error': 'type required'}), 400
        rows = db.execute(
            'SELECT puzzle_date, difficulty, elapsed, completed FROM puzzle_sessions WHERE puzzle_type=? AND difficulty=? ORDER BY puzzle_date DESC LIMIT 60',
            [ptype, difficulty]
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@app.route('/api/puzzles/wordcache', methods=['GET'])
def get_word_cache():
    db = get_db()
    try:
        pdate = request.args.get('date', '')
        if not pdate:
            return jsonify(None)
        row = db.execute('SELECT word_data FROM puzzle_word_cache WHERE puzzle_date=?', [pdate]).fetchone()
        if not row:
            return jsonify(None)
        try:
            return jsonify(json.loads(row['word_data']))
        except Exception:
            return jsonify(None)
    finally:
        db.close()

@app.route('/api/puzzles/wordcache', methods=['POST'])
def save_word_cache():
    db = get_db()
    try:
        data = request.json or {}
        pdate = data.get('date', '')
        if not pdate:
            return jsonify({'error': 'date required'}), 400
        word_data = json.dumps({'words': data.get('words', []), 'topic': data.get('topic', '')})
        now = datetime.utcnow().isoformat()
        db.execute('''INSERT INTO puzzle_word_cache (puzzle_date, word_data, created_at) VALUES (?,?,?)
            ON CONFLICT(puzzle_date) DO UPDATE SET word_data=excluded.word_data''',
            [pdate, word_data, now])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/stats', methods=['GET'])
def get_stats():
    db = get_db()
    try:
        return jsonify({
            'articles':    db.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0],
            'drafts':      db.execute("SELECT COUNT(*) FROM articles WHERE status='draft'").fetchone()[0],
            'authors':     db.execute("SELECT COUNT(*) FROM authors").fetchone()[0],
            'categories':  db.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
            'tags':        db.execute("SELECT COUNT(*) FROM tags").fetchone()[0],
            'geotagged':   db.execute("SELECT COUNT(*) FROM articles WHERE status='published' AND latitude IS NOT NULL AND latitude!=0").fetchone()[0],
            'annotations': db.execute("SELECT COUNT(*) FROM annotations").fetchone()[0],
        })
    finally:
        db.close()

@app.route('/api/authors/<int:aid>/contributions', methods=['GET'])
def get_author_contributions(aid):
    db = get_db()
    try:
        user = db.execute('SELECT id FROM users WHERE author_id=?', [aid]).fetchone()
        if not user:
            return jsonify({'translated': [], 'edited': [], 'user_id': None})
        uid = user['id']
        translated = db.execute('''SELECT DISTINCT a.id,a.title,a.slug,a.featured_image,a.published_at,
            t.language,t.translator_name,a.reading_time,au.name as original_author
            FROM translations t JOIN articles a ON t.article_id=a.id
            LEFT JOIN authors au ON a.author_id=au.id
            WHERE t.translator_id=? ORDER BY t.rowid DESC''', [uid]).fetchall()
        edited = db.execute('''SELECT DISTINCT a.id,a.title,a.slug,a.featured_image,a.published_at,
            h.edited_at,h.action,a.reading_time,au.name as author_name
            FROM article_history h JOIN articles a ON h.article_id=a.id
            LEFT JOIN authors au ON a.author_id=au.id
            WHERE h.user_id=? AND h.action='edited' ORDER BY h.edited_at DESC LIMIT 30''', [uid]).fetchall()
        return jsonify({
            'translated': [dict(r) for r in translated],
            'edited':     [dict(r) for r in edited],
            'user_id':    uid,
        })
    finally:
        db.close()

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    db = get_db()
    period = request.args.get('period','90')
    try:
        since = '2000-01-01' if period == 'all' else (datetime.utcnow() - timedelta(days=int(period))).isoformat()

        monthly_pubs = db.execute(
            "SELECT substr(published_at,1,7) as month,COUNT(*) as count "
            "FROM articles WHERE status='published' AND published_at>? "
            "GROUP BY month ORDER BY month ASC LIMIT 24", [since]).fetchall()

        top_authors = db.execute(
            "SELECT au.name,COUNT(*) as count FROM articles a "
            "JOIN authors au ON a.author_id=au.id WHERE a.status='published' "
            "GROUP BY au.id ORDER BY count DESC LIMIT 8").fetchall()

        top_tags = db.execute(
            "SELECT t.name,COUNT(*) as count FROM article_tags at2 "
            "JOIN tags t ON t.id=at2.tag_id GROUP BY t.id ORDER BY count DESC LIMIT 12").fetchall()

        try:
            monthly_reads = db.execute(
                "SELECT substr(read_at,1,7) as month,SUM(read_count) as count "
                "FROM reading_history WHERE read_at>? GROUP BY month ORDER BY month ASC LIMIT 24", [since]).fetchall()
        except Exception: monthly_reads = []
        try:
            monthly_comments = db.execute(
                "SELECT substr(created_at,1,7) as month,COUNT(*) as count "
                "FROM comments WHERE created_at>? GROUP BY month ORDER BY month ASC LIMIT 24", [since]).fetchall()
        except Exception: monthly_comments = []

        try:
            article_analytics = db.execute(
                "SELECT a.id,a.title,a.slug,a.published_at,a.reading_time,"
                "au.name as author_name,c.name as category_name,"
                "COALESCE(SUM(rh.read_count),0) as total_reads,"
                "(SELECT COUNT(*) FROM comments cm WHERE cm.article_id=a.id AND cm.status='approved') as comment_count "
                "FROM articles a "
                "LEFT JOIN authors au ON a.author_id=au.id "
                "LEFT JOIN categories c ON a.category_id=c.id "
                "LEFT JOIN reading_history rh ON rh.article_id=a.id "
                "WHERE a.status='published' "
                "GROUP BY a.id ORDER BY total_reads DESC LIMIT 30").fetchall()
        except Exception: article_analytics = []

        try:
            reader_count    = db.execute("SELECT COUNT(*) FROM users WHERE role='reader'").fetchone()[0]
            total_reads     = db.execute("SELECT COALESCE(SUM(read_count),0) FROM reading_history").fetchone()[0]
            puzzle_count    = db.execute("SELECT COUNT(*) FROM user_puzzle_completions").fetchone()[0]
            comment_count   = db.execute("SELECT COUNT(*) FROM comments WHERE status='approved'").fetchone()[0]
            pending_comments= db.execute("SELECT COUNT(*) FROM comments WHERE status='pending'").fetchone()[0]
            letter_count    = db.execute("SELECT COUNT(*) FROM letters").fetchone()[0]
        except Exception:
            reader_count=total_reads=puzzle_count=comment_count=pending_comments=letter_count=0

        return jsonify({
            'monthly_pubs':     [dict(r) for r in monthly_pubs],
            'monthly_reads':    [dict(r) for r in monthly_reads],
            'monthly_comments': [dict(r) for r in monthly_comments],
            'article_analytics':[dict(r) for r in article_analytics],
            'top_authors':      [dict(r) for r in top_authors],
            'top_tags':         [dict(r) for r in top_tags],
            'reader_count':     reader_count,
            'total_reads':      total_reads,
            'puzzle_count':     puzzle_count,
            'comment_count':    comment_count,
            'pending_comments': pending_comments,
            'letter_count':     letter_count,
            'period':           period,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/analytics/locations', methods=['GET'])
def analytics_locations():
    import urllib.request as _ur, json as _json
    db = get_db()
    try:
        ips = set()
        for tbl in ('comments','letters'):
            try:
                for r in db.execute(f'SELECT DISTINCT ip_address FROM {tbl} WHERE ip_address IS NOT NULL AND ip_address != ""').fetchall():
                    ips.add(r['ip_address'])
            except Exception: pass
        public_ips = [ip for ip in ips if ip and not ip.startswith(('127.','10.','192.168.','::1'))]
        if not public_ips:
            return jsonify({'locations':[],'total_ips':0,'geolocated':0})
        cached = {r['ip']:dict(r) for r in db.execute(
            f"SELECT * FROM ip_geo_cache WHERE ip IN ({','.join('?'*len(public_ips))})", public_ips).fetchall()}
        uncached = [ip for ip in public_ips if ip not in cached]
        if uncached:
            batch = [{'query':ip,'fields':'status,country,countryCode,city,lat,lon,query'} for ip in uncached[:100]]
            try:
                req = _ur.Request('http://ip-api.com/batch',
                    data=_json.dumps(batch).encode(),
                    headers={'Content-Type':'application/json'}, method='POST')
                with _ur.urlopen(req, timeout=8) as resp:
                    for r in _json.loads(resp.read()):
                        if r.get('status') == 'success':
                            db.execute('INSERT OR REPLACE INTO ip_geo_cache (ip,country,country_code,city,lat,lon,cached_at) VALUES (?,?,?,?,?,?,?)',
                                [r['query'],r.get('country'),r.get('countryCode'),r.get('city'),r.get('lat'),r.get('lon'),datetime.utcnow().isoformat()])
                            cached[r['query']] = r
                db.commit()
            except Exception: pass
        agg = {}
        for ip in public_ips:
            g = cached.get(ip,{})
            lat,lon = g.get('lat'),g.get('lon')
            if lat and lon:
                key = f"{round(lat,1)},{round(lon,1)}"
                if key not in agg:
                    agg[key] = {'lat':lat,'lon':lon,'country':g.get('country',''),'city':g.get('city',''),'count':0}
                agg[key]['count'] += 1
        return jsonify({'locations':sorted(agg.values(),key=lambda x:-x['count']),'total_ips':len(public_ips),'geolocated':len(agg)})
    except Exception as e:
        return jsonify({'error':str(e)}),500
    finally:
        db.close()


def get_client_ip():
    return (request.headers.get('X-Forwarded-For','').split(',')[0].strip() or
            request.headers.get('X-Real-IP','') or request.remote_addr or '')

@app.route('/api/articles/<int:aid>/comments', methods=['GET'])
def get_comments(aid):
    db = get_db()
    try:
        rows = db.execute(
            'SELECT id,display_name,content,created_at FROM comments'
            " WHERE target_kind='article' AND target_ref=? AND status='approved'"
            ' ORDER BY created_at', [str(aid)]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/publications/<pub_ref>/comments', methods=['GET'])
def get_publication_comments(pub_ref):
    db = get_db()
    try:
        rows = db.execute(
            'SELECT id,display_name,content,created_at,username,selected_text FROM comments'
            " WHERE target_kind='publication' AND target_ref=? AND status='approved'"
            ' ORDER BY created_at', [pub_ref]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/publications/<pub_ref>/comments', methods=['POST'])
def post_publication_comment(pub_ref):
    db = get_db()
    try:
        data = request.json or {}
        name = (data.get('display_name') or '').strip()
        body = (data.get('content') or '').strip()
        if not name or not body: return jsonify({'error':'Name and comment required'}),400
        if len(body) > 2000: return jsonify({'error':'Comment too long'}),400
        db.execute('INSERT INTO comments (target_kind,target_ref,article_id,display_name,'
                   'content,ip_address,user_id,status,username) VALUES (?,?,?,?,?,?,?,?,?)',
            ['publication', pub_ref, None, name[:100], body, get_client_ip(),
             session.get('user_id'), 'pending', (data.get('username') or '').strip() or None])
        db.commit()
        return jsonify({'success':True,'message':'Comment submitted for moderation.'}),201
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

@app.route('/api/articles/<int:aid>/comments', methods=['POST'])
def post_comment(aid):
    db = get_db()
    try:
        data = request.json or {}
        name = (data.get('display_name') or '').strip()
        body = (data.get('content') or '').strip()
        if not name or not body: return jsonify({'error':'Name and comment required'}),400
        if len(body) > 2000: return jsonify({'error':'Comment too long'}),400
        db.execute('INSERT INTO comments (target_kind,target_ref,article_id,display_name,'
                   'content,ip_address,user_id,status) VALUES (?,?,?,?,?,?,?,?)',
            ['article',str(aid),aid,name[:100],body,get_client_ip(),session.get('user_id'),'pending'])
        db.commit()
        return jsonify({'success':True,'message':'Comment submitted for moderation.'}),201
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

@app.route('/api/comments', methods=['GET'])
def admin_get_comments():
    if session.get('role') not in ('admin','editor'):
        return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        status = request.args.get('status','pending')
        rows = db.execute(
            'SELECT c.*, a.title AS article_title FROM comments c'
            " LEFT JOIN articles a ON c.target_kind='article'"
            '   AND c.target_ref=CAST(a.id AS TEXT)'
            ' WHERE c.status=? ORDER BY c.created_at DESC LIMIT 200', [status]).fetchall()
        out = [dict(r) for r in rows]
        pending = {r['target_ref'] for r in out if r.get('target_kind') == 'publication'}
        if pending:
            titles = {}
            for p in db.execute('SELECT filename,title FROM publications').fetchall():
                if not p['filename']:
                    continue
                pid = re.sub(r'[^a-z0-9]+', '-',
                             os.path.splitext(p['filename'])[0].lower()).strip('-')
                if pid in pending:
                    titles[pid] = p['title']
            for r in out:
                if r.get('target_kind') == 'publication':
                    r['article_title'] = titles.get(r['target_ref']) or r['target_ref']
        return jsonify(out)
    finally: db.close()

@app.route('/api/comments/<int:cid>', methods=['PUT'])
def moderate_comment(cid):
    if session.get('role') not in ('admin','editor'):
        return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        db.execute('UPDATE comments SET status=? WHERE id=?',[(request.json or {}).get('status','approved'),cid])
        db.commit(); return jsonify({'success':True})
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

@app.route('/api/comments/<int:cid>', methods=['DELETE'])
def delete_comment(cid):
    if session.get('role') not in ('admin','editor'):
        return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        db.execute('DELETE FROM comments WHERE id=?',[cid])
        db.commit(); return jsonify({'success':True})
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

@app.route('/api/letters', methods=['GET'])
def get_letters():
    uid  = session.get('user_id')
    role = session.get('role','')
    if not uid: return jsonify({'error':'Not logged in'}),401
    db = get_db()
    try:
        if role in ('admin','editor'):
            rows = db.execute(
                'SELECT l.*,u.username,'
                '(SELECT content FROM letter_messages WHERE letter_id=l.id ORDER BY created_at DESC LIMIT 1) as last_msg'
                ' FROM letters l LEFT JOIN users u ON l.user_id=u.id ORDER BY l.last_message_at DESC').fetchall()
        else:
            rows = db.execute(
                'SELECT l.*,'
                '(SELECT content FROM letter_messages WHERE letter_id=l.id ORDER BY created_at DESC LIMIT 1) as last_msg'
                ' FROM letters l WHERE l.user_id=? ORDER BY l.last_message_at DESC', [uid]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/letters', methods=['POST'])
def create_letter():
    uid  = session.get('user_id')
    data = request.json or {}
    subject = (data.get('subject') or '').strip()
    content = (data.get('content') or '').strip()
    guest   = (data.get('guest_name') or '').strip() or None
    if not subject or not content: return jsonify({'error':'Subject and message required'}),400
    ip = get_client_ip()
    db = get_db()
    try:
        now = datetime.utcnow().isoformat()
        db.execute('INSERT INTO letters (user_id,guest_name,subject,status,ip_address,created_at,last_message_at) VALUES (?,?,?,?,?,?,?)',
            [uid, guest, subject, 'open', ip, now, now])
        lid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('INSERT INTO letter_messages (letter_id,sender,content,created_at) VALUES (?,?,?,?)',
            [lid, 'user' if uid else 'guest', content, now])
        db.commit()
        return jsonify({'id':lid,'success':True}),201
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

@app.route('/api/letters/<int:lid>', methods=['GET'])
def get_letter(lid):
    uid  = session.get('user_id')
    role = session.get('role','')
    if not uid: return jsonify({'error':'Not logged in'}),401
    db = get_db()
    try:
        letter = db.execute('SELECT * FROM letters WHERE id=?',[lid]).fetchone()
        if not letter: return jsonify({'error':'Not found'}),404
        if letter['user_id'] != uid and role not in ('admin','editor'):
            return jsonify({'error':'Unauthorized'}),403
        msgs = db.execute('SELECT * FROM letter_messages WHERE letter_id=? ORDER BY created_at',[lid]).fetchall()
        d = dict(letter); d['messages'] = [dict(m) for m in msgs]
        return jsonify(d)
    finally: db.close()

@app.route('/api/letters/<int:lid>/reply', methods=['POST'])
def reply_letter(lid):
    uid  = session.get('user_id')
    role = session.get('role','')
    if not uid: return jsonify({'error':'Not logged in'}),401
    body = (request.json or {}).get('content','').strip()
    if not body: return jsonify({'error':'Message required'}),400
    db = get_db()
    try:
        letter = db.execute('SELECT * FROM letters WHERE id=?',[lid]).fetchone()
        if not letter: return jsonify({'error':'Not found'}),404
        if letter['user_id'] != uid and role not in ('admin','editor'):
            return jsonify({'error':'Unauthorized'}),403
        now    = datetime.utcnow().isoformat()
        sender = 'admin' if role in ('admin','editor') else 'user'
        db.execute('INSERT INTO letter_messages (letter_id,sender,content,created_at) VALUES (?,?,?,?)',
            [lid, sender, body, now])
        db.execute('UPDATE letters SET last_message_at=?,status=? WHERE id=?',
            [now, 'replied' if sender=='admin' else 'open', lid])
        db.commit(); return jsonify({'success':True})
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

@app.route('/api/letters/<int:lid>/close', methods=['POST'])
def close_letter(lid):
    if session.get('role') not in ('admin','editor'):
        return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        db.execute("UPDATE letters SET status='closed' WHERE id=?",[lid])
        db.commit(); return jsonify({'success':True})
    except Exception as e:
        db.rollback(); return jsonify({'error':str(e)}),500
    finally: db.close()

def _require_staff():
    return session.get('role') in ('admin', 'editor', 'author', 'translator', 'typesetter')

@app.route('/api/admin/subscribers', methods=['GET'])
def admin_subscribers():
    if not _require_staff(): return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM newsletter_subscribers ORDER BY subscribed_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/admin/site-messages', methods=['GET'])
def admin_site_messages():
    if not _require_staff(): return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM site_messages ORDER BY created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/admin/activity', methods=['GET'])
def admin_activity():
    if not _require_staff(): return jsonify({'error':'Unauthorized'}),403
    limit = min(int(request.args.get('limit', 500)), 2000)
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM site_activity ORDER BY occurred_at DESC LIMIT ?', [limit]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/admin/newsstand-accounts', methods=['GET'])
def admin_newsstand_accounts():
    if not _require_staff(): return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM newsstand_accounts ORDER BY created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/admin/sheet-annotations', methods=['GET'])
def admin_sheet_annotations():
    if not _require_staff(): return jsonify({'error':'Unauthorized'}),403
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM sheet_annotations ORDER BY created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

_PDF_TARGET_TYPES = ('broadsheet', 'magazine', 'column_booklet', 'gazette')

@app.route('/api/pdf-enhancements/<target_type>/<path:target_key>', methods=['GET'])
def pdf_enhancement_get(target_type, target_key):
    if target_type not in _PDF_TARGET_TYPES: return jsonify({'error': 'Unknown target_type'}), 400
    db = get_db()
    try:
        return jsonify(get_pdf_enhancement(db, target_type, target_key))
    finally: db.close()

@app.route('/api/pdf-enhancements/<target_type>/<path:target_key>', methods=['PUT'])
def pdf_enhancement_put(target_type, target_key):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if target_type not in _PDF_TARGET_TYPES: return jsonify({'error': 'Unknown target_type'}), 400
    d = request.json or {}
    db = get_db()
    try:
        db.execute('''INSERT INTO pdf_enhancements (target_type,target_key,toc,page_numbers,cover_note,accent,extra_css,updated_at)
            VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(target_type,target_key) DO UPDATE SET
              toc=excluded.toc, page_numbers=excluded.page_numbers, cover_note=excluded.cover_note,
              accent=excluded.accent, extra_css=excluded.extra_css, updated_at=CURRENT_TIMESTAMP''',
            [target_type, str(target_key), 1 if d.get('toc') else 0, 1 if d.get('page_numbers', True) else 0,
             (d.get('cover_note') or '')[:500], (d.get('accent') or '')[:20], (d.get('extra_css') or '')[:20000]])
        db.commit()
        return jsonify(get_pdf_enhancement(db, target_type, target_key))
    finally: db.close()

try: init_db()
except Exception as _ie: print(f'init_db: {_ie}')
try: migrate_db()
except Exception as _me: print(f'migrate_db: {_me}')

import mimetypes as _mimetypes

VOICE_EXPRESS_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 210">'
    '<rect width="210" height="210" fill="#0a0a0a"/>'
    '<text x="105" y="130" text-anchor="middle"'
    ' style="font:bold 110px Georgia,serif;fill:#f5f5f2">VE</text>'
    '<text x="105" y="170" text-anchor="middle"'
    ' style="font:14px Georgia,serif;fill:#777;letter-spacing:4px">VOICE EXPRESS</text>'
    '</svg>'
)

EPUB_CSS = """
@charset "UTF-8";

html,body,div,p,h1,h2,h3,h4,h5,ul,ol,li,
blockquote,figure,figcaption{margin:0;padding:0}
*,*::before,*::after{box-sizing:border-box}

html{font-size:100%}
body{
  font-family:Georgia,"Times New Roman",serif;
  font-size:11pt;
  line-height:1.88;
  color:#0d0d0d;
  background:#faf9f7;
  -webkit-hyphens:auto;
  hyphens:auto;
  text-rendering:optimizeLegibility;
}

.cover-wrap{
  page-break-after:always;break-after:page;
  text-align:center;
  padding:4em 3em 5em;
  background:#0a0a0a;color:#f5f5f2;
  min-height:95vh;
}
.cover-logo{
  width:110px;height:110px;display:block;
  margin:0 auto 2em;
  border:1.5px solid rgba(255,255,255,.22);
}
.cover-rule-t{border:none;border-top:5px solid #f5f5f2;margin:0 0 3px}
.cover-rule-s{border:none;border-top:1px solid rgba(255,255,255,.3);margin:0 0 3em}
.cover-lbl{
  font-family:"Courier New",monospace;font-size:.6em;
  text-transform:uppercase;letter-spacing:.22em;color:rgba(255,255,255,.4);
  margin-bottom:.6em;
}
.cover-title{
  font-size:2.6em;font-weight:bold;line-height:1.1;
  color:#f5f5f2;margin:0 0 .3em;letter-spacing:-.02em;
}
.cover-by{
  font-style:italic;color:rgba(255,255,255,.6);
  font-size:.95em;margin:0 0 1em;
}
.cover-desc{
  font-style:italic;color:rgba(255,255,255,.45);font-size:.88em;
  max-width:26em;margin:0 auto 2em;line-height:1.62;
}
.cover-count{
  font-family:"Courier New",monospace;font-size:.62em;
  text-transform:uppercase;letter-spacing:.12em;color:rgba(255,255,255,.35);
}
.cover-date{
  font-family:"Courier New",monospace;font-size:.58em;
  color:rgba(255,255,255,.22);margin-top:.35em;
}
.cover-bottom{border:none;border-top:2px double rgba(255,255,255,.25);margin-top:3em}

.ch-cover{
  page-break-before:always;break-before:page;
  page-break-after:always;break-after:page;
  min-height:85vh;
  display:flex;flex-direction:column;justify-content:center;
  padding:4em 4em 4em 4.5em;
  position:relative;
  background:#faf9f7;
}
.ch-cover-ghost{
  position:absolute;
  bottom:2em;right:1.5em;
  font-size:14em;font-weight:bold;
  color:rgba(0,0,0,.035);line-height:1;
  pointer-events:none;letter-spacing:-.06em;
}
.ch-cover-kicker{
  font-family:"Courier New",monospace;
  font-size:.65em;text-transform:uppercase;
  letter-spacing:.22em;color:#888;margin-bottom:.5em;
}
.ch-cover-rule-top{
  border:none;border-top:3px solid #0d0d0d;
  margin:0 0 1.2em;
}
.ch-cover-title{
  font-size:2.8em;font-weight:bold;line-height:1.07;
  letter-spacing:-.025em;margin:0 0 .5em;
  hyphens:manual;
}
.ch-cover-deck{
  font-size:1.15em;font-style:italic;color:#2a2a2a;
  line-height:1.65;border-left:3px solid #0d0d0d;
  padding-left:1em;margin:0 0 1.2em;max-width:36em;
}
.ch-cover-rule-bot{
  border:none;border-top:1px solid #ccc;margin:0 0 1.2em;
}
.ch-cover-byline{
  font-family:"Courier New",monospace;
  font-size:.68em;text-transform:uppercase;
  letter-spacing:.1em;color:#666;
}
.ch-cover-byline strong{
  font-family:Georgia,serif;font-weight:bold;
  font-variant:small-caps;text-transform:none;
  letter-spacing:.06em;font-size:1.12em;color:#0d0d0d;
}

.founders-wrap{
  padding:4em 4.5em 5em 4.5em;
  page-break-before:always;break-before:page;
  page-break-after:always;break-after:page;
}
.founders-kicker{
  font-family:"Courier New",monospace;font-size:.65em;
  text-transform:uppercase;letter-spacing:.22em;color:#aaa;margin:0 0 .4em;
}
.founders-title{
  font-size:2em;font-weight:bold;font-style:italic;
  margin:0 0 .4em;letter-spacing:-.01em;line-height:1.18;
}
.founders-rule{border:none;border-top:2px solid #0d0d0d;margin:0 0 2em}
.founders-body p{
  margin:0 0 1em;text-align:justify;
  -webkit-hyphens:auto;hyphens:auto;line-height:1.88;
}
.founders-body>p:first-of-type::first-letter{
  float:left;font-size:4.5em;font-weight:bold;
  line-height:.7;margin:.04em .07em 0 0;color:#0d0d0d;
}
.founders-sig{
  margin-top:2.5em;padding-top:1.2em;
  border-top:1px solid #ddd;
}
.founders-sig-name{
  font-weight:bold;font-variant:small-caps;
  font-size:.95em;letter-spacing:.06em;
}
.founders-sig-role{font-size:.82em;color:#777;margin-top:.15em;font-style:italic}

.index-wrap{
  padding:4em 4.5em;
  page-break-after:always;break-after:page;
}
.index-kicker{
  font-family:"Courier New",monospace;font-size:.64em;
  text-transform:uppercase;letter-spacing:.22em;color:#999;margin:0 0 .4em;
}
.index-title{
  font-size:2.6em;font-weight:bold;
  border-bottom:3px solid #0d0d0d;padding-bottom:.3em;
  margin:0 0 1.6em;letter-spacing:-.015em;
}
.index-item{
  display:flex;gap:1em;margin:0 0 1em;
  padding-bottom:.85em;border-bottom:1px dotted #ccc;
  align-items:baseline;
}
.index-n{
  font-family:"Courier New",monospace;font-size:.65em;
  color:rgba(0,0,0,.18);width:1.9em;flex-shrink:0;
  text-align:right;padding-top:.2em;
}
.index-info{flex:1}
.index-art-title{font-weight:bold;font-size:1.06em;line-height:1.3}
.index-art-title a{color:#0d0d0d;text-decoration:none}
.index-art-meta{
  font-family:"Courier New",monospace;font-size:.63em;
  text-transform:uppercase;letter-spacing:.07em;color:#777;margin-top:.2em;
}

.chapter-wrap{
  padding:3.5em 4.5em 4em 4.5em;
  page-break-before:always;break-before:page;
}

.ch-num{
  font-family:"Courier New",monospace;font-size:.64em;
  text-transform:uppercase;letter-spacing:.22em;color:#bbb;margin:0 0 .4em;
}
.ch-category{
  font-family:"Courier New",monospace;font-size:.7em;
  text-transform:uppercase;letter-spacing:.16em;color:#444;
  border-bottom:2px solid #0d0d0d;padding-bottom:.22em;
  margin:0 0 .55em;display:inline-block;
}
.ch-title{
  font-size:2.3em;font-weight:bold;line-height:1.1;
  margin:0 0 .4em;letter-spacing:-.02em;hyphens:manual;
}
.ch-byline{
  font-variant:small-caps;font-size:.9em;letter-spacing:.06em;
  color:#333;margin:0 0 .12em;
}
.ch-meta-detail{
  font-family:"Courier New",monospace;font-size:.65em;
  color:#888;margin:0 0 1.1em;
}
.ch-rule{border:none;border-top:1px solid #333;margin:1em 0 1.5em}
.ch-excerpt{
  font-size:1.15em;font-style:italic;color:#222;
  line-height:1.65;margin:0 0 2em;
  padding:.8em 0;border-top:1px solid #bbb;border-bottom:1px solid #bbb;
}
.ch-featured-img{width:100%;height:auto;display:block;margin:0 0 .35em}
.ch-featured-caption{
  font-family:"Courier New",monospace;font-size:.68em;
  color:#777;font-style:italic;text-align:center;margin:0 0 2em;
}

.article-body{
  font-size:1em;line-height:1.9;
  column-count:1;}

.article-body p{
  margin:0 0 .95em;
  text-align:justify;
  -webkit-hyphens:auto;hyphens:auto;
}

.article-body>p:first-of-type{text-indent:0}
.article-body p+p{text-indent:1.4em;margin-top:-.2em;margin-bottom:0}

.article-body>p:first-of-type::first-letter{
  float:left;font-size:4.6em;font-weight:bold;
  line-height:.7;margin:.03em .07em 0 0;color:#0d0d0d;
}

.article-body h2{
  font-size:1.4em;font-weight:bold;
  margin:2.2em 0 .5em;padding-bottom:.22em;
  border-bottom:1px solid #ddd;letter-spacing:-.01em;
}
.article-body h3{font-size:1.15em;font-weight:bold;margin:1.8em 0 .4em}
.article-body h4{font-size:1em;font-weight:bold;font-style:italic;margin:1.6em 0 .35em}
.article-body strong{font-weight:bold}
.article-body em{font-style:italic}
.article-body a{color:#0d0d0d;text-decoration:underline}
.article-body ul,.article-body ol{margin:.2em 0 1em 2em}
.article-body li{margin-bottom:.4em}

.article-body hr{
  border:none;text-align:center;margin:2.5em 0;
}
.article-body hr::after{
  content:"\2014\00a0\00a7\00a0\2014";
  font-size:.85em;color:#bbb;letter-spacing:.35em;
}

.article-body img{
  max-width:90%;height:auto;
  display:block;margin:2.5em auto 0;
}
.article-body figure{margin:2.5em 0 2em}
.article-body .framed-img-wrap{
  max-width:92%;margin:2.5em auto 0;
  border:4px solid #0d0d0d;padding:4px;
  background:#fff;box-shadow:4px 4px 0 rgba(0,0,0,.1);
  display:block;
}
.article-body .framed-img-wrap img{
  width:100%;height:auto;display:block;max-width:none;margin:0;
  filter:grayscale(6%)contrast(1.06);
}
.article-body figcaption,
.article-body .img-cap,
.article-body .wp-caption-text,
.article-body .caption{
  font-family:"Courier New",monospace;font-size:.68em;
  text-transform:uppercase;letter-spacing:.08em;
  color:#777;text-align:center;
  margin:.5em auto 2em;max-width:92%;
  font-style:italic;
}

.article-body blockquote{
  margin:2em 1.5em;
  padding:1.2em 1.8em;
  border-top:2px solid #0d0d0d;border-bottom:2px solid #0d0d0d;
  text-align:center;
}
.article-body blockquote p{
  font-size:1.5em;font-style:italic;
  line-height:1.38;color:#0d0d0d;margin:0;text-align:center;
  hyphens:none;
}
.article-body blockquote cite{
  display:block;font-family:"Courier New",monospace;
  font-size:.58em;text-transform:uppercase;letter-spacing:.12em;
  color:#888;margin-top:.65em;font-style:normal;
}

.about-wrap{
  padding:4em 4.5em 5em;
  page-break-before:always;break-before:page;
}
.about-rule-top{border:none;border-top:5px double #0d0d0d;margin:0 0 .9em}
.about-kicker{
  font-family:"Courier New",monospace;font-size:.65em;
  text-transform:uppercase;letter-spacing:.2em;color:#888;margin:0 0 .3em;
}
.about-masthead{
  font-size:2.4em;font-weight:bold;margin:0 0 .1em;letter-spacing:-.02em;
}
.about-tagline{
  font-style:italic;color:#555;font-size:1.06em;margin:0 0 2.2em;
}
.about-logo{
  width:70px;height:70px;display:block;margin:0 0 1.5em;
  border:1px solid #ddd;
}
.about-body p{margin-bottom:.92em;text-align:justify;-webkit-hyphens:auto;hyphens:auto}
.about-body h2{font-size:1.3em;font-weight:bold;margin:2em 0 .45em;border-bottom:1px solid #ddd;padding-bottom:.2em}
.about-team-grid{display:flex;flex-wrap:wrap;gap:1.2em;margin-top:1.2em}
.about-team-member{flex:1;min-width:9em}
.about-team-name{font-weight:bold;font-size:.95em}
.about-team-role{font-size:.8em;color:#777;font-style:italic}
.about-team-contact{font-size:.75em;color:#999;margin-top:.2em}
.about-team-contact a{color:inherit}
.about-footer{
  font-family:"Courier New",monospace;font-size:.65em;color:#aaa;
  text-transform:uppercase;letter-spacing:.14em;margin-top:4em;
  padding-top:1em;border-top:1px solid #e0e0e0;text-align:center;
}
mark.ve-hl{padding:0 .04em;border-radius:.1em}
.ve-noteref{text-decoration:none;font-size:.7em;vertical-align:super}
.ve-notes{margin-top:2.5em;padding-top:.8em;border-top:1px solid #ccc;font-size:.92em}
.ve-notes h3{font-size:.7em;text-transform:uppercase;letter-spacing:.14em;color:#777;margin:0 0 .5em}
.ve-notes ol{margin:0;padding-left:1.3em}
.ve-notes li{margin-bottom:.5em;line-height:1.4}
"""

ABOUT_HTML_BODY = """
<div class="about-rule-top"></div>
<p class="about-kicker">About</p>
<div class="about-masthead">The Voice Express</div>
<div class="about-tagline">&#8220;Journalism, innit?&#8221;</div>
<div class="about-body">
<p>Independent news publication based in New Delhi, India. Formerly student-run.</p>
<p><em>The Voice Express</em> was founded in 2022 as an Intro to New Media project
that refused to stay one. We started because none of the seven journalism departments
in the University of Delhi had their own publication. We stayed because the absence
we were trying to fill turned out to be larger than we thought.</p>
<p>We cover the stories that fall through institutional cracks &#8212; labour,
state violence, student life, protest, culture, and whatever else needs to be
said. We do not take advertising. We do not answer to institutions. We are run
by the microscopic cogs, for the microscopic cogs.</p>
<p>After all, the truth takes time.</p>
<h2>Our Team</h2>
<div class="about-team-grid">
<div class="about-team-member">
  <div class="about-team-name">Mouli</div>
  <div class="about-team-role">Chief Editor, Journalist &amp; Creator of the Magazine</div>
</div>
<div class="about-team-member">
  <div class="about-team-name">Mitali (Aayat Mahnoor)</div>
  <div class="about-team-role">Web Developer &amp; Website Maintainer</div>
  <div class="about-team-contact"><a href="mailto:aayatmahnoor@proton.me">aayatmahnoor&#64;proton.me</a></div>
</div>
</div>
<h2>Contact</h2>
<p>Reach out via <a href="mailto:thevoiceexpress@proton.me">thevoiceexpress&#64;proton.me</a>
for queries, story pitches, or collaboration requests.
Read the magazine at <a href="https://emag.thevoiceexpress.in">emag.thevoiceexpress.in</a>,
and every issue, broadsheet and booklet at
<a href="https://newsstand.thevoiceexpress.in">newsstand.thevoiceexpress.in</a>.</p>
</div>
"""

FOUNDERS_NOTE_HTML = """
<div class="founders-wrap">
<p class="founders-kicker">Founder&#8217;s Note &#8212; 2nd September 2023</p>
<h1 class="founders-title">Journalism, innit?</h1>
<hr class="founders-rule"/>
<div class="founders-body">
<p>It is shameful to admit that, despite there being only seven colleges in the
University of Delhi that pride themselves on having a department of
&#8216;Journalism&#8217; &#8212; regardless of how poorly administered or funded &#8212;
not one of them has its own nor is affiliated with any original college news
publication or journal. Which isn&#8217;t to say that they have much else big-name
to offer, really. It&#8217;s not like it&#8217;s a pity party for Journalism
specifically. To be clear. But anyway.</p>
<p>An absence is apparent. Or so it became to us at some point after the start
of TVE as an Intro to New Media project, a means to an end, a most honorable
end of scraping by a grand total of 10% of our grade. Institution &amp; authority,
in their arms the swords of bureaucracy &amp; status quo. There is an impossibility
to capturing a certain elusive creature called progress when faced with these two
goons, particularly if you are but subordinate parts of these very institutions.
Ants to a god, cog in the machine.</p>
<p>News cannot be published this way, &amp; no one else seems to want to publish it
any which way at all. <strong>An independent publishing, run by the microscopic
cogs &amp; for the microscopic cogs, becomes necessary.</strong></p>
<p>In October 2007, a small independent student-run newspaper called DU Beat began
to fill part of this absence. And it has done a brilliant job of doing so, to date,
perhaps now having reached the upper bound of its expansion. But in its expansion,
DU Beat has now itself turned into an institution, defeating the purpose of its
&#8216;independence&#8217; in the first place.</p>
<p>Which isn&#8217;t to mention that in its significance, its publishings also
follow a naturally proportionate order of that which may be deemed significant.
Trends, universities, big-name colleges, lighthearted vanity. Macroscopic cogs,
if you will.</p>
<p>There must (might/should/hopefully will) be more publishings here &amp; there.
But if it is possible for a publishing to exist that covers the microscopic &#8212;
the stories that fall through every institutional crack &#8212; then
<em>The Voice Express</em> is that attempt.</p>
<p>The articles collected in this ebook are part of that ongoing attempt.</p>
</div>
<div class="founders-sig">
<div class="founders-sig-name">Mouli Sharma &#8212; Editor-in-Chief</div>
<div class="founders-sig-role">Scholar of religion, Jamia Millia Islamia &#183;
Freelance journalist, New Delhi &#183;
Published in Frontline India, Article 14, The Leaflet,
Feminism in India, The Polis Project &amp; others</div>
</div>
</div>
"""


def _void_close(html_str):
    for tag in ('br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base',
                'col', 'embed', 'param', 'source', 'track', 'wbr'):
        html_str = re.sub(
            r'<(' + tag + r')(\s[^>]*)?>(?!</' + tag + r'>)',
            lambda m: '<' + m.group(1) + (m.group(2) or '') + '/>',
            html_str, flags=re.IGNORECASE)
    return html_str


EPUB_IMG_MAX_PX = 1600
EPUB_IMG_QUALITY = 82
EPUB_IMG_MIN_BYTES = 300 * 1024


def _shrink_for_epub(data, ext):
    if len(data) < EPUB_IMG_MIN_BYTES:
        return None
    try:
        from PIL import Image
        import io as _pil_io
        im = Image.open(_pil_io.BytesIO(data))
        im.load()
        has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
        if max(im.size) > EPUB_IMG_MAX_PX:
            im.thumbnail((EPUB_IMG_MAX_PX, EPUB_IMG_MAX_PX), Image.LANCZOS)
        out = _pil_io.BytesIO()
        if has_alpha:
            im.convert('RGBA').save(out, format='PNG', optimize=True)
            new_mt, new_ext = 'image/png', '.png'
        else:
            im.convert('RGB').save(out, format='JPEG', quality=EPUB_IMG_QUALITY,
                                   optimize=True, progressive=True)
            new_mt, new_ext = 'image/jpeg', '.jpg'
        shrunk = out.getvalue()
        return (shrunk, new_mt, new_ext) if len(shrunk) < len(data) else None
    except Exception as e:
        print(f'[epub] image downscale skipped ({e})')
        return None


def _fetch_img(src, static_root):
    try:
        if src.startswith('/static/'):
            rel  = src[len('/static/'):].lstrip('/')
            path = os.path.join(static_root, rel)
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    data = f.read()
                mt  = _mimetypes.guess_type(path)[0] or 'image/jpeg'
                ext = os.path.splitext(path)[1].lower() or '.jpg'
                small = _shrink_for_epub(data, ext)
                return small if small else (data, mt, ext)
        elif src.startswith(('http://', 'https://')):
            req = _urllib_req.Request(
                src, headers={'User-Agent': 'VoiceExpress-Ebook/1.0'})
            with _urllib_req.urlopen(req, timeout=6) as resp:
                data = resp.read(3 * 1024 * 1024)
            ct  = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
            mt  = ct or 'image/jpeg'
            raw = _mimetypes.guess_extension(mt) or '.jpg'
            ext = '.jpg' if raw in ('.jpe', '.jpeg') else raw
            small = _shrink_for_epub(data, ext)
            return small if small else (data, mt, ext)
    except Exception:
        pass
    return None, None, None


def _apply_epub_annotations(body, anns):
    import html as _h
    notes = []
    for k, a in enumerate(anns, 1):
        sel = (a.get('selected_text') or '').strip()
        if not sel:
            continue
        note = (a.get('note') or '').strip()
        color = a.get('color') or '#ffeb3b'
        ref = (f'<a class="ve-noteref" epub:type="noteref" href="#venote{k}"><sup>[{k}]</sup></a>'
               if note else '')
        for cand in (_h.escape(sel), sel):
            if cand and cand in body:
                body = body.replace(cand, f'<mark class="ve-hl" style="background:{color}">{cand}</mark>{ref}', 1)
                break
        if note:
            notes.append((k, sel, note))
    if notes:
        items = ''.join(
            f'<li id="venote{k}" epub:type="footnote"><strong>&#8220;{_h.escape(s[:90])}&#8221;</strong> '
            f'&#8212; {_h.escape(n)}</li>' for k, s, n in notes)
        body += f'<aside class="ve-notes" epub:type="footnotes"><h3>Your notes</h3><ol>{items}</ol></aside>'
    return body

def build_epub(articles, title, creator, description, language='en', annotations=None):
    annotations = annotations or {}
    import html as _h
    book_id     = str(uuid.uuid4())
    now_str     = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    date_str    = now_str[:10]
    static_root = STATIC_ROOT

    img_store     = {}
    img_counter   = [0]
    manifest_imgs = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:

        mi = zipfile.ZipInfo('mimetype')
        mi.compress_type = zipfile.ZIP_STORED
        zf.writestr(mi, 'application/epub+zip')

        zf.writestr('META-INF/container.xml',
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<container version="1.0"'
            ' xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>')

        zf.writestr('OEBPS/styles.css', EPUB_CSS)

        logo_png_path = os.path.join(static_root, 'logo.png')
        if os.path.exists(logo_png_path):
            with open(logo_png_path, 'rb') as _lf:
                logo_bytes = _lf.read()
            zf.writestr('OEBPS/images/logo.png', logo_bytes)
            logo_href = 'images/logo.png'
            logo_mt   = 'image/png'
        else:
            zf.writestr('OEBPS/images/logo.svg', VOICE_EXPRESS_LOGO_SVG)
            logo_href = 'images/logo.svg'
            logo_mt   = 'image/svg+xml'

        def embed_images(html_str):
            def repl(m):
                src = m.group(1)
                if not src or src.startswith('data:'):
                    return m.group(0)
                if src in img_store:
                    return m.group(0).replace(src, img_store[src], 1)
                data, mt, ext = _fetch_img(src, static_root)
                if not data:
                    return m.group(0)
                idx     = img_counter[0]; img_counter[0] += 1
                img_id  = 'emb%04d' % idx
                img_rel = 'images/%s%s' % (img_id, ext)
                zf.writestr('OEBPS/' + img_rel, data)
                img_store[src] = img_rel
                manifest_imgs.append((img_id, img_rel, mt))
                return m.group(0).replace(src, img_rel, 1)
            return re.sub(r'src=["\']([^"\']+)["\']', repl,
                          html_str, flags=re.IGNORECASE)

        def xhtml(body_html, pg_title):
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml"'
                ' xmlns:epub="http://www.idpf.org/2007/ops"'
                ' xml:lang="' + _h.escape(language) + '">'
                '<head><meta charset="UTF-8"/>'
                '<title>' + _h.escape(pg_title) + '</title>'
                '<link rel="stylesheet" type="text/css" href="styles.css"/>'
                '</head><body>' + body_html + '</body></html>'
            )

        n = len(articles)
        count_line = '%d article%s' % (n, 's' if n != 1 else '')
        cover_body = (
            '<div class="cover-wrap">'
            '<img class="cover-logo" src="' + logo_href + '" alt="The Voice Express"/>'
            '<hr class="cover-rule-t"/><hr class="cover-rule-s"/>'
            '<p class="cover-lbl">A Voice Express Collection</p>'
            '<p class="cover-title">' + _h.escape(title) + '</p>' +
            ('<p class="cover-by">Curated by ' + _h.escape(creator) + '</p>'
             if creator and creator.strip().lower() not in ('voice express', 'the voice express', '') else '') +
            ('<p class="cover-desc">' + _h.escape(description) + '</p>'
             if description else '') +
            '<p class="cover-meta">' + _h.escape(count_line) + '<br/>'
            'Published ' + date_str + '<br/>'
            'thevoiceexpress.in</p>'
            '<hr class="cover-rule-b"/>'
            '</div>'
        )
        zf.writestr('OEBPS/cover.xhtml', xhtml(cover_body, title))

        zf.writestr('OEBPS/founders.xhtml',
                    xhtml(FOUNDERS_NOTE_HTML, "From the Editor"))

        rows = []
        for i, art in enumerate(articles, 1):
            at   = art.get('title', 'Untitled')
            aau  = art.get('byline_auto') or art.get('author_name') or art.get('byline') or ''
            adt  = (art.get('published_at') or '')[:10]
            acat = art.get('category_name') or ''
            meta = '  ·  '.join(filter(None, [aau, acat, adt]))
            rows.append(
                '<div class="index-item">'
                '<span class="index-n">%d</span>'
                '<div class="index-info">'
                '<div class="index-art-title"><a href="ch%03d.xhtml">%s</a></div>'
                '<div class="index-art-meta">%s</div>'
                '</div></div>' % (i, i, _h.escape(at), _h.escape(meta))
            )
        index_body = (
            '<div class="index-wrap">'
            '<p class="index-kicker">The Voice Express Collection</p>'
            '<h1 class="index-title">Contents</h1>' +
            '\n'.join(rows) + '</div>'
        )
        zf.writestr('OEBPS/index.xhtml', xhtml(index_body, 'Contents'))

        spine_ids   = ['cover', 'founders', 'index']
        nav_entries = [
            ('Cover',          'cover.xhtml'),
            ('From the Editor','founders.xhtml'),
            ('Contents',       'index.xhtml'),
        ]
        manifest_ch = []

        for i, art in enumerate(articles, 1):
            at      = art.get('title') or 'Untitled'
            aau     = art.get('author_name') or art.get('byline') or 'The Voice Express'
            adt     = (art.get('published_at') or art.get('created_at') or '')[:10]
            acat    = art.get('category_name') or ''
            aex     = art.get('excerpt') or ''
            feat    = art.get('featured_image') or ''
            body    = art.get('content') or ''

            body = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>',
                          '', body, flags=re.DOTALL | re.IGNORECASE)
            body = _void_close(body)
            body = embed_images(body)
            anns = annotations.get(art.get('id'))
            if anns:
                body = _apply_epub_annotations(body, anns)

            cov_fname   = 'cov%03d.xhtml' % i
            cov_item_id = 'cov%03d' % i
            cat_badge   = ('<span class="ch-cover-kicker">' + _h.escape(acat) + ' &nbsp;&bull;&nbsp; Chapter ' + str(i) + '</span>'
                           if acat else '<span class="ch-cover-kicker">Chapter ' + str(i) + '</span>')
            cov_body = (
                '<div class="ch-cover">'
                '<div class="ch-cover-ghost">' + ('%02d' % i) + '</div>' +
                cat_badge +
                '<hr class="ch-cover-rule-top"/>'
                '<h1 class="ch-cover-title">' + _h.escape(at) + '</h1>' +
                ('<p class="ch-cover-deck">' + _h.escape(aex) + '</p>' if aex else '') +
                '<hr class="ch-cover-rule-bot"/>'
                '<p class="ch-cover-byline">By <strong>' + _h.escape(aau) + '</strong>' +
                (' &nbsp;&bull;&nbsp; ' + adt if adt else '') + '</p>'
                '</div>'
            )
            zf.writestr('OEBPS/' + cov_fname, xhtml(cov_body, at + ' — Cover'))
            manifest_ch.append((cov_item_id, cov_fname))
            spine_ids.append(cov_item_id)
            nav_entries.append((at, cov_fname))

            fname   = 'ch%03d.xhtml' % i
            item_id = 'ch%03d' % i

            lede_html = ''
            if feat:
                data, mt, ext = _fetch_img(feat, static_root)
                if data:
                    idx  = img_counter[0]; img_counter[0] += 1
                    fid  = 'emb%04d' % idx
                    frel = 'images/%s%s' % (fid, ext)
                    zf.writestr('OEBPS/' + frel, data)
                    img_store[feat] = frel
                    manifest_imgs.append((fid, frel, mt))
                    lede_html = (
                        '<div class="framed-img-wrap">'
                        '<img src="' + frel + '" alt="' + _h.escape(at) + '"/>'
                        '</div>'
                        '<p class="img-cap">Photograph / Illustration</p>'
                    )

            ch_body = (
                '<div class="chapter-wrap">'
                + ('<p class="ch-num">Chapter ' + str(i) + '</p>') +
                ('<p class="ch-category">' + _h.escape(acat) + '</p>' if acat else '') +
                '<h1 class="ch-title">' + _h.escape(at) + '</h1>'
                '<p class="ch-byline">By ' + _h.escape(aau) + '</p>' +
                ('<p class="ch-meta-detail">' + adt + '</p>' if adt else '') +
                '<hr class="ch-rule"/>' +
                ('<p class="ch-excerpt">' + _h.escape(aex) + '</p>' if aex else '') +
                lede_html +
                '<div class="article-body">' + body + '</div>'
                '</div>'
            )
            zf.writestr('OEBPS/' + fname, xhtml(ch_body, at))
            manifest_ch.append((item_id, fname))
            spine_ids.append(item_id)
            nav_entries.append((at + ' (continued)', fname))

        about_full = (
            '<div class="about-wrap">'
            '<img class="about-logo" src="' + logo_href + '" alt="The Voice Express"/>' +
            ABOUT_HTML_BODY +
            '<p class="about-footer">The Voice Express &#183; thevoiceexpress.in'
            ' &#183; ' + date_str + '</p>'
            '</div>'
        )
        zf.writestr('OEBPS/about.xhtml', xhtml(about_full, 'About'))
        spine_ids.append('about')
        nav_entries.append(('About', 'about.xhtml'))

        nav_li = '\n'.join(
            '<li><a href="' + fn + '">' + _h.escape(t) + '</a></li>'
            for t, fn in nav_entries)
        zf.writestr('OEBPS/nav.xhtml', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml"'
            ' xmlns:epub="http://www.idpf.org/2007/ops">'
            '<head><meta charset="UTF-8"/><title>Navigation</title>'
            '<link rel="stylesheet" type="text/css" href="styles.css"/></head>'
            '<body><nav epub:type="toc" id="toc"><h2>Contents</h2>'
            '<ol>' + nav_li + '</ol></nav></body></html>'
        ))

        ncx_pts = '\n'.join(
            '<navPoint id="np%d" playOrder="%d">'
            '<navLabel><text>%s</text></navLabel>'
            '<content src="%s"/></navPoint>' % (j, j, _h.escape(t), fn)
            for j, (t, fn) in enumerate(nav_entries, 1))
        zf.writestr('OEBPS/toc.ncx', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            '<head>'
            '<meta name="dtb:uid" content="urn:uuid:' + book_id + '"/>'
            '<meta name="dtb:depth" content="1"/>'
            '<meta name="dtb:totalPageCount" content="0"/>'
            '<meta name="dtb:maxPageNumber" content="0"/>'
            '</head>'
            '<docTitle><text>' + _h.escape(title) + '</text></docTitle>'
            '<navMap>' + ncx_pts + '</navMap></ncx>'
        ))

        fixed_mf = [
            '<item id="cover"    href="cover.xhtml"    media-type="application/xhtml+xml"/>',
            '<item id="founders" href="founders.xhtml" media-type="application/xhtml+xml"/>',
            '<item id="index"    href="index.xhtml"    media-type="application/xhtml+xml"/>',
            '<item id="about"    href="about.xhtml"    media-type="application/xhtml+xml"/>',
            '<item id="nav"      href="nav.xhtml"      media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx"      href="toc.ncx"        media-type="application/x-dtbncx+xml"/>',
            '<item id="css"      href="styles.css"     media-type="text/css"/>',
            '<item id="logo"     href="' + logo_href + '" media-type="' + logo_mt + '"/>',
        ]
        ch_mf  = ['<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (c, f)
                  for c, f in manifest_ch]
        img_mf = ['<item id="%s" href="%s" media-type="%s"/>' % (ii, ir, im)
                  for ii, ir, im in manifest_imgs]
        mf_str = '\n    '.join(fixed_mf + ch_mf + img_mf)
        sp_str = '\n    '.join('<itemref idref="%s"/>' % r for r in spine_ids)
        zf.writestr('OEBPS/content.opf', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"'
            ' unique-identifier="book-id" xml:lang="' + _h.escape(language) + '">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="book-id">urn:uuid:' + book_id + '</dc:identifier>'
            '<dc:title>' + _h.escape(title) + '</dc:title>'
            '<dc:creator>' + _h.escape(creator or 'The Voice Express') + '</dc:creator>'
            '<dc:description>' + _h.escape(description) + '</dc:description>'
            '<dc:language>' + _h.escape(language) + '</dc:language>'
            '<dc:publisher>The Voice Express</dc:publisher>'
            '<dc:date>' + date_str + '</dc:date>'
            '<meta property="dcterms:modified">' + now_str + '</meta>'
            '</metadata>'
            '<manifest>\n    ' + mf_str + '\n  </manifest>'
            '<spine toc="ncx">\n    ' + sp_str + '\n  </spine>'
            '</package>'
        ))

    return buf.getvalue()







@app.route('/api/pages/<slug>', methods=['GET'])
def get_page(slug):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM site_pages WHERE slug=?', [slug]).fetchone()
        if not row: return jsonify({'error':'Not found'}), 404
        return jsonify(dict(row))
    finally: db.close()

@app.route('/api/pages/<slug>', methods=['PUT'])
def update_page(slug):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error':'Unauthorized'}), 403
    data = request.json or {}
    db = get_db()
    try:
        title   = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        if not title: return jsonify({'error':'Title required'}), 400
        db.execute(
            'INSERT INTO site_pages (slug,title,content,updated_at) VALUES (?,?,?,?)'
            ' ON CONFLICT(slug) DO UPDATE SET title=excluded.title,'
            'content=excluded.content,updated_at=excluded.updated_at',
            [slug, title, content, datetime.utcnow().isoformat()])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally: db.close()

@app.route('/api/pages', methods=['GET'])
def list_pages():
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error':'Unauthorized'}), 403
    db = get_db()
    try:
        rows = db.execute('SELECT slug,title,updated_at FROM site_pages ORDER BY slug').fetchall()
        return jsonify([dict(r) for r in rows])
    finally: db.close()

@app.route('/api/ebook/generate', methods=['POST'])
def generate_ebook():
    data        = request.json or {}
    article_ids = data.get('article_ids', [])
    if not article_ids:
        return jsonify({'error': 'No articles selected'}), 400
    if len(article_ids) > 50:
        return jsonify({'error': 'Max 50 articles per ebook'}), 400

    title       = (data.get('title')       or 'Voice Express Collection').strip()[:200]
    creator     = (data.get('creator')     or 'Voice Express').strip()[:200]
    description = (data.get('description') or '').strip()[:1000]
    language    = (data.get('language')    or 'en').strip()[:10]

    db = get_db()
    try:
        articles = []
        for aid in article_ids:
            row = db.execute(
                "SELECT a.*,au.name as author_name,c.name as category_name,"
                "s.name as section_name,s.slug as section_slug "
                "FROM articles a "
                "LEFT JOIN authors au ON a.author_id=au.id "
                "LEFT JOIN categories c ON a.category_id=c.id "
                "LEFT JOIN sections s ON a.section_id=s.id "
                "WHERE a.id=? AND a.status='published'", [aid]
            ).fetchone()
            if row:
                articles.append(_article_print_dict(db, row))
        if not articles:
            return jsonify({'error': 'No valid published articles found'}), 400
        _localize_articles(db, articles)
        annotations = {}
        uid = session.get('user_id')
        if uid:
            ph = ','.join('?' * len(article_ids))
            for an in db.execute(
                    f"SELECT * FROM annotations WHERE user_id=? AND article_id IN ({ph}) "
                    "ORDER BY article_id, start_offset", [uid] + list(article_ids)).fetchall():
                annotations.setdefault(an['article_id'], []).append(dict(an))
        epub_bytes = build_epub(articles, title, creator, description, language, annotations=annotations)
        safe = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:60] or 'ebook'
        _reader_made = session.get('role') not in ('admin', 'editor', 'author')
        _save_to_library(db, title, 'epub', epub_bytes, articles, safe, 'epub',
                         extra_meta={'reader_generated': True,
                                     'requested_by': session.get('username') or None}
                                    if _reader_made else None)
        return send_file(
            io.BytesIO(epub_bytes),
            mimetype='application/epub+zip',
            as_attachment=True,
            download_name=f'{safe}.epub'
        )
    finally:
        db.close()

@app.route('/api/magazine/generate', methods=['POST'])
def generate_magazine():
    if not _PRINTABLES_OK:
        return jsonify({'error': 'Magazine generator not available'}), 503
    data        = request.json or {}
    article_ids = data.get('article_ids', [])
    if not article_ids:
        return jsonify({'error': 'No articles selected'}), 400
    if len(article_ids) > 50:
        return jsonify({'error': 'Max 50 articles'}), 400
    title       = (data.get('title')       or 'Voice Express Collection').strip()[:200]
    creator     = (data.get('creator')     or '').strip()[:200]
    description = (data.get('description') or '').strip()[:1000]
    db = get_db()
    try:
        articles = []
        for aid in article_ids:
            row = db.execute(
                "SELECT a.*,au.name as author_name,c.name as category_name,"
                "s.name as section_name,s.slug as section_slug "
                "FROM articles a LEFT JOIN authors au ON a.author_id=au.id "
                "LEFT JOIN categories c ON a.category_id=c.id "
                "LEFT JOIN sections s ON a.section_id=s.id "
                "WHERE a.id=? AND a.status='published'", [aid]).fetchone()
            if row: articles.append(_article_print_dict(db, row))
        if not articles:
            return jsonify({'error': 'No valid published articles found'}), 400
        _localize_articles(db, articles)
        _bump_issue_number()
        _bump_volume()
        safe = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:60] or 'magazine'

        src_ref = ','.join(str(a['id']) for a in articles)
        sig = hashlib.md5(('|'.join(f'{a["id"]}:{a.get("updated_at")}' for a in articles)
                           + f'#{title}#{creator}#{description}').encode()).hexdigest()
        try:
            _mag_html_bytes, _fn = _dtp_artifact(
                db, 'magazine', src_ref, 'html',
                gen_args=('--article-id', articles[0]['id'], '--title', title,
                          '--creator', creator, '--description', description),
                data={'articles': articles}, title=title, sig=sig)
        except ArtifactError as ae:
            return jsonify({'error': f'Magazine generation failed: {ae}'}), 503
        return send_file(
            io.BytesIO(_mag_html_bytes),
            mimetype='text/html; charset=utf-8',
            as_attachment=True,
            download_name=f'{safe}_magazine.html'
        )
    finally:
        db.close()

@app.route('/api/magazine/generate-pdf', methods=['POST'])
def generate_magazine_pdf():
    data        = request.json or {}
    article_ids = data.get('article_ids', [])
    if not article_ids:
        return jsonify({'error': 'No articles selected'}), 400
    if len(article_ids) > 50:
        return jsonify({'error': 'Max 50 articles'}), 400
    title       = (data.get('title')   or 'Voice Express').strip()[:200]
    creator     = (data.get('creator') or '').strip()[:200]
    db = get_db()
    try:
        articles = []
        for aid in article_ids:
            row = db.execute(
                "SELECT a.*,au.name as author_name,c.name as category_name,"
                "s.name as section_name,s.slug as section_slug "
                "FROM articles a LEFT JOIN authors au ON a.author_id=au.id "
                "LEFT JOIN categories c ON a.category_id=c.id "
                "LEFT JOIN sections s ON a.section_id=s.id "
                "WHERE a.id=? AND a.status='published'", [aid]).fetchone()
            if row: articles.append(_article_print_dict(db, row))
        if not articles:
            return jsonify({'error': 'No valid published articles found'}), 400
        _localize_articles(db, articles)
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:60] or 'magazine'
        _bump_issue_number()
        _bump_volume()

        src_ref = ','.join(str(a['id']) for a in articles)
        sig = hashlib.md5(('|'.join(f'{a["id"]}:{a.get("updated_at")}' for a in articles)
                           + f'#{title}#{creator}').encode()).hexdigest()
        try:
            pdf_bytes, _fn = _dtp_artifact(
                db, 'magazine', src_ref, 'pdf',
                gen_args=('--article-id', articles[0]['id'], '--title', title,
                          '--creator', creator),
                data={'articles': articles}, title=title, sig=sig)
        except ArtifactError as ae:
            return jsonify({'error': f'Magazine PDF generation failed: {ae}'}), 503
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{safe_title}.pdf'
        )
    finally:
        db.close()


_DELHI_LOCS = [
    (['delhi university','du ','north campus','miranda','srcc','hindu college',
      'hansraj','kirori mal','ramjas','st stephen'], 28.6907, 77.2088, 'Delhi University, North Campus'),
    (['south campus','daulat ram','lsr','lady shri ram','venky','south delhi'],
      28.5695, 77.2144, 'South Delhi'),
    (['jnu','jawaharlal nehru university','vasant kunj'],
      28.5402, 77.1654, 'JNU, New Delhi'),
    (['jamia','okhla','jamia millia','jasola'],
      28.5607, 77.2759, 'Jamia Millia Islamia, New Delhi'),
    (['manesar','imd manesar'],
      28.3572, 76.9375, 'Manesar, Haryana'),
    (['gurugram','gurgaon','cyber city','dlf'],
      28.4595, 77.0266, 'Gurugram, Haryana'),
    (['noida','sector 62','sector 18'],
      28.5355, 77.3910, 'Noida, UP'),
    (['faridabad'],
      28.4089, 77.3178, 'Faridabad, Haryana'),
    (['rohini','pitampura'],
      28.7495, 77.1156, 'Rohini, New Delhi'),
    (['nehru place','south ex','lajpat'],
      28.5491, 77.2491, 'South Extension, New Delhi'),
    (['connaught','cp ','rajiv chowk','central delhi'],
      28.6279, 77.2197, 'Connaught Place, New Delhi'),
    (['india gate','rajpath','kartavya path','lutyens'],
      28.6129, 77.2295, "India Gate, New Delhi"),
    (['paharganj','new delhi railway','new delhi station'],
      28.6432, 77.2195, 'New Delhi Railway Station'),
    (['saket','malviya nagar','hauz khas'],
      28.5290, 77.2170, 'Saket, New Delhi'),
    (['chandni chowk','old delhi','lal qila','red fort','jama masjid'],
      28.6506, 77.2401, 'Old Delhi'),
    (['dwarka','palam','uttam nagar'],
      28.5921, 77.0460, 'Dwarka, New Delhi'),
    (['patiala house','high court','supreme court','tis hazari','district court'],
      28.6295, 77.2460, 'Courts Complex, New Delhi'),
    (['aiims','safdarjung','ansari nagar','green park'],
      28.5672, 77.2100, 'AIIMS, New Delhi'),
    (['iit delhi','iit ','hauz khas'],
      28.5459, 77.1926, 'IIT Delhi'),
    (['karol bagh','rajouri garden','janakpuri'],
      28.6511, 77.1898, 'West Delhi'),
    (['shahdara','yamuna','east delhi','mayur vihar'],
      28.6691, 77.3040, 'East Delhi'),
    (['north east delhi','babarpur','mustafabad','jaffrabad'],
      28.6975, 77.2980, 'North East Delhi'),
    (['ambedkar nagar','sangam vihar','govindpuri','kalkaji'],
      28.5135, 77.2560, 'South Delhi'),
    (['ashram','nizamuddin','lodi','lodhi','humayun'],
      28.5894, 77.2410, 'Nizamuddin, New Delhi'),
]
_DELHI_DEFAULT = (28.6139, 77.2090, 'New Delhi')


def _infer_location(title, content):
    haystack = ((title or '') + ' ' + (content or '')[:600]).lower()
    haystack = re.sub(r'<[^>]+>', ' ', haystack)
    for kws, lat, lon, name in _DELHI_LOCS:
        if any(k in haystack for k in kws):
            return lat, lon, name
    return _DELHI_DEFAULT


@app.route('/api/articles/auto-geotag', methods=['POST'])
def auto_geotag_articles():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    try:
        rows = db.execute(
            "SELECT id, title, content FROM articles "
            "WHERE status='published' AND (latitude IS NULL OR latitude=0)"
        ).fetchall()
        tagged = 0
        rng = random.Random()
        for row in rows:
            lat, lon, name = _infer_location(row['title'], row['content'])
            jitter = 0.0035
            lat += rng.gauss(0, jitter)
            lon += rng.gauss(0, jitter)
            db.execute(
                "UPDATE articles SET latitude=?, longitude=?, location_name=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                [round(lat, 6), round(lon, 6), name, row['id']]
            )
            tagged += 1
        db.commit()
        return jsonify({'tagged': tagged, 'total': len(rows)})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()



@app.route('/api/publications', methods=['GET'])
def list_publications():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM publications WHERE is_visible=1 ORDER BY created_at DESC"
        ).fetchall()
        return jsonify({'publications': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/all', methods=['GET'])
def list_publications_admin():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM publications ORDER BY created_at DESC"
        ).fetchall()
        return jsonify({'publications': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/<int:pid>', methods=['GET'])
def get_publication(pid):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM publications WHERE id=?", [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/<int:pid>', methods=['PUT'])
def update_publication(pid):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json or {}
    db = get_db()
    try:
        row = db.execute("SELECT id FROM publications WHERE id=?", [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        fields, params = [], []
        for key in ('title', 'description', 'price_min', 'price_max', 'price_suggested',
                    'is_visible', 'is_featured'):
            if key in data:
                fields.append(f'{key}=?')
                params.append(data[key])
        if fields:
            params.append(pid)
            db.execute(f"UPDATE publications SET {','.join(fields)} WHERE id=?", params)
            db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/<int:pid>', methods=['DELETE'])
def delete_publication(pid):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    try:
        row = db.execute("SELECT filename FROM publications WHERE id=?", [pid]).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        if row['filename']:
            _fp = _publication_path(row['filename'])
            if _fp:
                os.remove(_fp)
        db.execute("DELETE FROM publications WHERE id=?", [pid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/<int:pid>/download')
def download_publication(pid):
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM publications WHERE id=? AND is_visible=1", [pid]
        ).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        if not row['filename']:
            return jsonify({'error': 'File not available'}), 404
        _fp = _publication_path(row['filename'])
        if not _fp:
            return jsonify({'error': 'File not on disk — may have been moved'}), 404
        _ext = row['filename'].rsplit('.', 1)[-1].lower() if '.' in row['filename'] else ''
        _mime = {
            'pdf':  'application/pdf',
            'epub': 'application/epub+zip',
            'html': 'text/html; charset=utf-8',
        }.get(_ext, 'application/octet-stream')
        return send_file(_fp, mimetype=_mime, as_attachment=True,
                         download_name=row['filename'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/upload', methods=['POST'])
def upload_publication():
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error': 'Forbidden'}), 403
    f = request.files.get('file')
    if not f or not (f.filename or '').lower().endswith('.pdf'):
        return jsonify({'error': 'A PDF file is required'}), 400
    data = f.read()
    if len(data) > 60 * 1024 * 1024:
        return jsonify({'error': 'PDF too large (max 60 MB)'}), 400
    title = (request.form.get('title') or os.path.splitext(secure_filename(f.filename))[0]
             or 'Untitled').strip()[:200]
    desc  = (request.form.get('description') or '').strip()[:1000]
    ts    = datetime.utcnow().strftime('%Y%m%d')
    safe  = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:50] or 'upload'
    filename = f'{safe}_{ts}_{uuid.uuid4().hex[:6]}.pdf'
    try:
        with open(os.path.join(PUBLICATIONS_FOLDER, filename), 'wb') as fh:
            fh.write(data)
    except Exception as e:
        return jsonify({'error': f'Could not store file: {e}'}), 500
    cover = None
    cf = request.files.get('cover')
    if cf and cf.filename and allowed_file(cf.filename):
        cfn = f'pubcover_{uuid.uuid4().hex[:8]}.{cf.filename.rsplit(".", 1)[1].lower()}'
        cf.save(os.path.join(UPLOAD_FOLDER, cfn))
        cover = f'/static/uploads/{cfn}'
    elif (request.form.get('cover_url') or '').strip():
        cover = request.form['cover_url'].strip()
    db = get_db()
    try:
        meta = json.dumps({'uploaded': True, 'description': desc}, ensure_ascii=False)
        db.execute('''INSERT INTO publications
            (title, pub_type, filename, file_size, cover_image, article_count,
             issue_number, price_min, price_max, price_suggested, currency, metadata)
            VALUES (?,?,?,?,?,?,?,0,500,0,'INR',?)''',
            [title, 'pdf', filename, len(data), cover, 0, None, meta])
        db.commit()
        return jsonify({'success': True, 'id': db.execute('SELECT last_insert_rowid()').fetchone()[0]}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/publications/<int:pid>/replace', methods=['POST'])
def replace_publication_file(pid):
    if not _require_staff(): return jsonify({'error': 'Unauthorized'}), 403
    if session.get('role') not in ('admin', 'editor'):
        return jsonify({'error': 'Forbidden'}), 403
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
                                     f'the replacement must be too'}), 400
        data = f.read()
        if len(data) > 60 * 1024 * 1024:
            return jsonify({'error': 'File too large (max 60 MB)'}), 400
        fp = _publication_path(row['filename'])
        if not fp:
            fp = os.path.join(PUBLICATIONS_FOLDER, row['filename'])
        with open(fp, 'wb') as fh:
            fh.write(data)
        db.execute('UPDATE publications SET file_size=? WHERE id=?', [len(data), pid])
        db.commit()
        return jsonify({'success': True, 'file_size': len(data),
                        'filename': row['filename']})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

import io as _io

@app.route('/api/admin/backup/db')
def backup_db():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    return send_file(os.path.realpath(DATABASE), as_attachment=True,
                     download_name='voice_express.db',
                     mimetype='application/octet-stream')

@app.route('/api/admin/backup/all')
def backup_all():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        db_real = os.path.realpath(DATABASE)
        if os.path.exists(db_real):
            zf.write(db_real, 'voice_express.db')

        up_dir = os.path.realpath(UPLOAD_FOLDER)
        if os.path.isdir(up_dir):
            for root, _, files in os.walk(up_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arc  = os.path.join('static', 'uploads',
                                        os.path.relpath(full, up_dir))
                    zf.write(full, arc)

        pub_dir = os.path.realpath(PUBLICATIONS_FOLDER)
        if os.path.isdir(pub_dir):
            for root, _, files in os.walk(pub_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arc  = os.path.join('static', 'publications',
                                        os.path.relpath(full, pub_dir))
                    zf.write(full, arc)

    buf.seek(0)
    from datetime import datetime as _dt
    stamp = _dt.utcnow().strftime('%Y%m%d_%H%M')
    return send_file(buf, as_attachment=True,
                     download_name=f've_backup_{stamp}.zip',
                     mimetype='application/zip')

def _sync_stores():
    return {'uploads': UPLOAD_FOLDER, 'publications': PUBLICATIONS_FOLDER, 'media': MEDIA_FOLDER}

@app.route('/api/admin/manifest')
def admin_manifest():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    out = {'db': None, 'files': []}
    dbp = os.path.realpath(DATABASE)
    if os.path.exists(dbp):
        st = os.stat(dbp); out['db'] = {'size': st.st_size, 'mtime': int(st.st_mtime)}
    for store, base in _sync_stores().items():
        base = os.path.realpath(base)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, base).replace(os.sep, '/')
                if '_cache/' in rel or rel.startswith('_cache'):
                    continue
                st = os.stat(full)
                out['files'].append({'store': store, 'path': rel,
                                     'size': st.st_size, 'mtime': int(st.st_mtime)})
    return jsonify(out)

@app.route('/api/admin/file/<store>/<path:relpath>')
def admin_file(store, relpath):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    base = _sync_stores().get(store)
    if not base:
        return jsonify({'error': 'Unknown store'}), 404
    base = os.path.realpath(base)
    full = os.path.realpath(os.path.join(base, relpath))
    if not (full == base or full.startswith(base + os.sep)) or not os.path.isfile(full):
        return jsonify({'error': 'Not found'}), 404
    return send_file(full, as_attachment=True, download_name=os.path.basename(full))

if __name__ == '__main__':
    if _sys.stdout.encoding and _sys.stdout.encoding.lower() != 'utf-8':
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    print("━" * 50)
    print("  Voice Express — Truth Takes Time")
    print("  http://localhost:5000")
    print("━" * 50)
    _reload_excludes = [
        os.path.join(os.path.dirname(os.__file__), '*'),
        os.path.join(_sys.prefix, 'Lib', 'site-packages', '*'),
    ]
    try:
        import site as _site
        for _sp in (getattr(_site, 'getsitepackages', lambda: [])()
                    + [getattr(_site, 'getusersitepackages', lambda: '')()]):
            if _sp:
                _reload_excludes.append(os.path.join(_sp, '*'))
    except Exception:
        pass
    app.run(debug=True, port=5000, exclude_patterns=_reload_excludes)
