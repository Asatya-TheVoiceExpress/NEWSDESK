#!/usr/bin/env python3
import os, re, json, calendar, datetime, hashlib, sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))

import ve.paths as _ve_paths
import ve.tags as _ve_tags

try:
    import pub_icons
except Exception:
    pub_icons = None

MEDIA_REL = 'media'
PUBS_REL  = 'publications'


def _static_root():
    return _ve_paths.static_root()


PUBLICATION_COLUMNS = (
    ('is_featured', 'INTEGER DEFAULT 0'),
)


def ensure_publication_columns(db, commit=True):
    try:
        have = {r[1] for r in db.execute('PRAGMA table_info(publications)').fetchall()}
    except sqlite3.Error:
        return
    if not have:
        return
    for col, decl in PUBLICATION_COLUMNS:
        if col not in have:
            db.execute(f'ALTER TABLE publications ADD COLUMN {col} {decl}')
    if commit:
        db.commit()


def canonical_target(kind, source_ref, ext):
    src = '' if source_ref is None else str(source_ref)
    if kind == 'gazette' and src.isdigit():
        return MEDIA_REL, f'gazette_{int(src)}.{ext}'
    if kind == 'broadsheet':
        m = re.match(r'^(\d{4})-(\d{2})$', src)
        if m:
            return MEDIA_REL, f'broadsheet_{m.group(1)}_{m.group(2)}.{ext}'
        if src:
            slug = re.sub(r'[^a-z0-9]+', '_', src.lower()).strip('_')
            return MEDIA_REL, f'broadsheet_special_{slug}.{ext}'
    if kind == 'booklet':
        parts = src.split(':')
        if parts and parts[0].isdigit():
            suffix = (parts[2] or parts[1] or 'all') if len(parts) > 2 else 'all'
            suffix = re.sub(r'[^A-Za-z0-9]+', '-', suffix).strip('-') or 'all'
            return MEDIA_REL, f'compilation_{int(parts[0])}_{suffix}.{ext}'
    return None


FORMAT_RANK = {'pdf': 3, 'html': 2, 'epub': 1}

READ_RANK = {'html': 3, 'pdf': 2, 'epub': 1}


def preferred_rendering(exts):
    return max(exts, key=lambda e: FORMAT_RANK.get(e, 0)) if exts else None


def preferred_reading(exts):
    return max(exts, key=lambda e: READ_RANK.get(e, 0)) if exts else None


def reading_view_for(fn):
    stem = os.path.splitext(fn)[0]
    ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''

    m = re.match(r'broadsheet_(\d{4})_(\d{2})$', stem)
    if m:
        scroll = f'broadsheet_scroll_{m.group(1)}_{m.group(2)}.html'
        p = locate(scroll)
        if p:
            return scroll, 'html', p

    sibs = siblings_for(stem)
    if len(sibs) > 1:
        r = preferred_reading(list(sibs))
        if r and r != ext:
            return f'{stem}.{r}', r, sibs[r]
    return None


def siblings_for(stem):
    found = {}
    for dirpath, _web in scan_dirs():
        if not os.path.isdir(dirpath):
            continue
        for ext in FORMAT_RANK:
            p = os.path.join(dirpath, f'{stem}.{ext}')
            if os.path.isfile(p) and ext not in found:
                found[ext] = p
    return found


def clean_title(fn):
    stem = os.path.splitext(fn)[0]
    stem = re.sub(r'_\d{6,8}(_[0-9a-f]{4,8})?$', '', stem)
    return stem.replace('_', ' ').strip() or stem


def _article_meta(db, aid):
    r = db.execute(
        'SELECT a.title, a.featured_image, a.published_at, au.name author, s.name section, '
        '(SELECT group_concat(t.name) FROM article_tags at JOIN tags t ON t.id=at.tag_id '
        '  WHERE at.article_id=a.id) tags '
        'FROM articles a LEFT JOIN authors au ON au.id=a.author_id '
        'LEFT JOIN sections s ON s.id=a.section_id WHERE a.id=?', [aid]).fetchone()
    return dict(r) if r else None


def _icon(*a, **kw):
    if not pub_icons:
        return None
    try:
        return pub_icons.generate_icon(*a, **kw)
    except Exception:
        return None


_BOOKLET_REF = re.compile(r'^(\d+):([a-z]+):(.*)$', re.I)
_ISO_DATE = re.compile(r'(\d{4}-\d{2}-\d{2})')


def booklet_entries(db, source_ref):
    m = _BOOKLET_REF.match(str(source_ref or '').strip())
    if not m:
        return None
    col_id, period, label = int(m.group(1)), m.group(2).lower(), m.group(3)
    out = {'column_id': col_id, 'period': period, 'range': None, 'entry_ids': []}

    sql = ("SELECT id, entry_date FROM column_entries "
           "WHERE column_id=? AND status='published'")
    args = [col_id]
    dates = _ISO_DATE.findall(label)
    if period.startswith('week') and len(dates) >= 2:
        lo, hi = dates[0], dates[1]
        out['range'] = [lo, hi]
        sql += " AND substr(entry_date,1,10) BETWEEN ? AND ?"
        args += [lo, hi]
    try:
        rows = db.execute(sql + " ORDER BY entry_date, id", args).fetchall()
    except Exception:
        return out
    out['entry_ids'] = [r['id'] if hasattr(r, 'keys') else r[0] for r in rows]
    if out['range'] is None and rows:
        ds = [str((r['entry_date'] if hasattr(r, 'keys') else r[1]) or '')[:10] for r in rows]
        ds = [d for d in ds if d]
        if ds:
            out['range'] = [min(ds), max(ds)]
    return out


def merge_tag_names(*groups):
    out, seen = [], set()
    for group in groups:
        for tag in group or []:
            tag = str(tag).strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                out.append(tag)
    return out


def booklet_tag_names(db, entry_ids):
    try:
        return _ve_tags.names_for_entries(db, entry_ids or [])
    except sqlite3.Error:
        return []


def sync_booklet_tags(db, pub_id=None, commit=True):
    sql = 'SELECT id, pub_type, metadata FROM publications'
    args = []
    if pub_id is not None:
        sql += ' WHERE id=?'
        args.append(pub_id)
    changed = 0
    for row in db.execute(sql, args).fetchall():
        try:
            meta = json.loads(row['metadata'] or '{}') or {}
        except (json.JSONDecodeError, TypeError):
            continue
        if (row['pub_type'] not in ('booklet', 'compilation')
                and meta.get('kind') not in ('booklet', 'compilation')):
            continue
        ids = meta.get('entry_ids') or (booklet_entries(db, meta.get('source_ref')) or {}).get('entry_ids')
        if not ids:
            continue
        current = meta.get('tags') or []
        derived = booklet_tag_names(db, ids)
        previous = {str(t).lower() for t in (meta.get('entry_tags') or [])}
        typed = [t for t in current if str(t).lower() not in previous]
        merged = merge_tag_names(typed, derived)
        if merged != list(current) or derived != list(meta.get('entry_tags') or []):
            meta['tags'] = merged
            meta['entry_tags'] = derived
            db.execute('UPDATE publications SET metadata=? WHERE id=?',
                       [json.dumps(meta, ensure_ascii=False), row['id']])
            changed += 1
    if commit and changed:
        db.commit()
    return changed


def booklet_contents(db, source_ref, entry_ids=None):
    ids = list(entry_ids or [])
    rng = None
    if not ids:
        info = booklet_entries(db, source_ref)
        if not info:
            return []
        ids, rng = info['entry_ids'], info['range']
    if not ids:
        return []
    qs = ','.join('?' * len(ids))
    try:
        rows = db.execute(
            f"SELECT id, title, subtitle, entry_date FROM column_entries "
            f"WHERE id IN ({qs}) ORDER BY entry_date, id", list(ids)).fetchall()
    except Exception:
        return []
    return [{'id': r['id'],
             'title': (r['title'] or '').strip() or f'Entry #{r["id"]}',
             'subtitle': (r['subtitle'] or '').strip() or None,
             'date': str(r['entry_date'] or '')[:10]} for r in rows]


_ROLE_BYLINE = {'photographer': 'Photos by', 'illustrator': 'Art by',
                'translator': 'Translation by', 'editor': 'Edited by',
                'as-told-to': 'As told to', 'reporting': 'Additional reporting by',
                'typesetter': 'Typeset by', 'post-editor': 'Post-edited by'}


def article_authors_list(db, aid):
    rows = db.execute('''SELECT aa.author_id AS id, au.name, aa.role, aa.sort_order,
        au.role AS position, au.bio, au.avatar_url, au.social_twitter, au.social_instagram
        FROM article_authors aa JOIN authors au ON au.id=aa.author_id
        WHERE aa.article_id=? ORDER BY aa.sort_order, aa.author_id''', [aid]).fetchall()
    return [dict(r) for r in rows]


def compose_byline(authors):
    if not authors:
        return ''
    def _join(names):
        names = [n for n in names if n]
        if not names:
            return ''
        if len(names) == 1:
            return names[0]
        return ', '.join(names[:-1]) + ' & ' + names[-1]
    groups, order = {}, []
    for a in authors:
        r = a.get('role') or 'author'
        if r not in groups:
            groups[r] = []
            order.append(r)
        groups[r].append(a.get('name'))
    parts = []
    writers = (groups.pop('author', []) if 'author' in groups else []) + \
              (groups.pop('co-author', []) if 'co-author' in groups else [])
    if writers:
        parts.append(_join(writers))
    for r in order:
        if r in ('author', 'co-author') or r not in groups:
            continue
        parts.append(f"{_ROLE_BYLINE.get(r, r.title() + ' by')} {_join(groups[r])}")
    return ' - '.join(p for p in parts if p)


def derive_entry(db, fn, abs_path):
    if fn.endswith('.dtp.json'):
        return None
    if fn.startswith('broadsheet_scroll_'):
        return None
    if fn.startswith(('.', '_')):
        return None

    ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
    stem = os.path.splitext(fn)[0]
    sibs = siblings_for(stem)
    if len(sibs) > 1 and preferred_rendering(list(sibs)) != ext:
        return None
    mtime = datetime.date.fromtimestamp(os.path.getmtime(abs_path)).isoformat()
    e = {'filename': fn, 'ext': ext, 'size': os.path.getsize(abs_path),
         'date': mtime, 'tags': [], 'cover': None, 'subtitle': None,
         'section_name': None, 'source_ref': None, 'article_ids': [],
         'entry_ids': [], 'column_id': None, 'period': None, 'range': None}

    m_gaz = re.match(r'gazette_(\d+)\.', fn)
    m_brd = re.match(r'broadsheet_(\d{4})_(\d{2})\.', fn)
    m_comp = re.match(r'compilation_(\d+)_(.+)\.html$', fn)

    if m_gaz:
        aid = int(m_gaz.group(1))
        meta = _article_meta(db, aid) or {}
        e['pub_type'] = 'gazette'
        e['kind'] = 'gazette'
        e['source_ref'] = str(aid)
        e['article_ids'] = [aid]
        e['title'] = meta.get('title') or f'Gazette #{aid}'
        e['subtitle'] = meta.get('author')
        e['date'] = (meta.get('published_at') or mtime)[:10]
        e['tags'] = [t for t in (meta.get('tags') or '').split(',') if t]
        e['section_name'] = meta.get('section')
        e['cover'] = _icon('gazette', e['tags'], e['title'], seed=aid,
                           article_images=[meta.get('featured_image')])

    elif m_brd:
        y, mo = int(m_brd.group(1)), int(m_brd.group(2))
        e['pub_type'] = 'broadsheet'
        e['kind'] = 'broadsheet'
        e['source_ref'] = f'{y:04d}-{mo:02d}'
        e['title'] = f'The Voice Express - {calendar.month_name[mo]} {y}'
        e['subtitle'] = 'Monthly edition'
        e['date'] = f'{y}-{mo:02d}-01'
        e['cover'] = _icon('broadsheet', [], e['title'], seed=y * 100 + mo)

    elif m_comp:
        cid, suffix = int(m_comp.group(1)), m_comp.group(2)
        crow = db.execute('SELECT title FROM columns WHERE id=?', [cid]).fetchone()
        col_title = crow['title'] if crow else f'Column #{cid}'
        if re.search(r'W\d', suffix):
            period, word = 'Weekly', 'weekly'
        elif suffix == 'month':
            period, word = 'Monthly', 'monthly'
        elif suffix == 'year':
            period, word = 'Yearly', 'yearly'
        else:
            period, word = 'All-time', 'all-time'
        imgs = [r['cover_image'] for r in db.execute(
            "SELECT cover_image FROM column_entries WHERE column_id=? AND cover_image<>''",
            [cid]).fetchall()]
        e['pub_type'] = 'compilation'
        e['kind'] = 'booklet'
        e['source_ref'] = f'{cid}:{suffix}:'
        _bk = booklet_entries(db, e['source_ref']) or {}
        e['entry_ids'] = _bk.get('entry_ids') or []
        e['column_id'] = cid
        e['period'] = suffix
        e['range'] = _bk.get('range')
        e['tags'] = booklet_tag_names(db, e['entry_ids'])
        e['title'] = f'{col_title} - {period} Compilation'
        e['subtitle'] = suffix if period == 'Weekly' else period
        e['cover'] = _icon('compilation', [], f'{word} compilation {col_title}',
                           seed=cid * 1000 + hash(suffix) % 997, article_images=imgs)

    else:
        e['pub_type'] = {'epub': 'epub', 'pdf': 'pdf'}.get(ext, 'booklet')
        e['kind'] = 'custom'
        e['title'] = clean_title(fn)
        e['cover'] = _icon({'pdf': 'magazine_pdf'}.get(e['pub_type'], e['pub_type']),
                           [], e['title'], seed=e['size'] % 100000)
    return e


def _cover_exists(cover):
    if not cover or cover.startswith(('http://', 'https://')):
        return bool(cover)
    rel = cover[len('/static/'):] if cover.startswith('/static/') else \
          cover[len('static/'):] if cover.startswith('static/') else None
    return bool(rel) and os.path.exists(os.path.join(_static_root(), rel))


def register_artifact(db, fn, abs_path, commit=True):
    e = derive_entry(db, fn, abs_path)
    if not e:
        return None
    row = db.execute('SELECT id, cover_image FROM publications WHERE filename=?', [fn]).fetchone()
    if row:
        if not _cover_exists(row['cover_image']) and e['cover']:
            db.execute('UPDATE publications SET cover_image=? WHERE id=?', [e['cover'], row['id']])
        sync_booklet_tags(db, row['id'], commit=False)
        if commit:
            db.commit()
        return row['id']
    meta_d = {'source': 'artifact', 'kind': e['kind'],
              'source_ref': e['source_ref'], 'article_ids': e['article_ids'],
              'subtitle': e['subtitle'], 'tags': e['tags'],
              'section_name': e['section_name'], 'date': e['date']}
    if e.get('entry_ids'):
        meta_d.update({'entry_ids': e['entry_ids'], 'column_id': e['column_id'],
                       'period': e['period'], 'range': e['range']})
    meta = json.dumps(meta_d, ensure_ascii=False)
    cur = db.execute(
        '''INSERT INTO publications
           (title, pub_type, filename, file_size, cover_image, article_count,
            issue_number, price_min, price_max, price_suggested, currency, metadata)
           VALUES (?,?,?,?,?,?,?,0,500,0,'INR',?)''',
        [e['title'], e['pub_type'], fn, e['size'], e['cover'],
         len(e['article_ids']), None, meta])
    if commit:
        db.commit()
    return cur.lastrowid


def scan_dirs():
    return [(_ve_paths.publications_path(), f'static/{PUBS_REL}'),
            (_ve_paths.media_path(), f'static/{MEDIA_REL}')]


def register_all(db, verbose=False):
    added, seen = 0, set()
    for dirpath, _web in scan_dirs():
        if not os.path.isdir(dirpath):
            continue
        for fn in sorted(os.listdir(dirpath)):
            full = os.path.join(dirpath, fn)
            if not os.path.isfile(full) or fn in seen:
                continue
            seen.add(fn)
            existed = db.execute('SELECT 1 FROM publications WHERE filename=?', [fn]).fetchone()
            if register_artifact(db, fn, full, commit=False) and not existed:
                added += 1
                if verbose:
                    print('[ve_library] registered', fn)
    db.commit()
    return added


_CONFIG_PATH = os.path.join(BASE, 'broadsheet_config.json')
_CONFIG_FP = {'mtime': None, 'hash': ''}


def config_fingerprint():
    try:
        mtime = os.path.getmtime(_CONFIG_PATH)
    except OSError:
        return ''
    if _CONFIG_FP['mtime'] != mtime:
        try:
            with open(_CONFIG_PATH, 'rb') as f:
                _CONFIG_FP['hash'] = hashlib.md5(f.read()).hexdigest()[:12]
        except OSError:
            _CONFIG_FP['hash'] = ''
        _CONFIG_FP['mtime'] = mtime
    return _CONFIG_FP['hash']


_RENDERER_PATHS = [os.path.join(BASE, n) for n in (
    'make_article_print.py',
    'make_magazine.py',
    'make_newsletter_broadsheet.py',
    'make_column_booklet.py',
)]
_RENDERER_FP = {'mtimes': None, 'hash': ''}


def renderer_fingerprint():
    mtimes = []
    for p in _RENDERER_PATHS:
        try:
            mtimes.append(os.path.getmtime(p))
        except OSError:
            mtimes.append(None)
    if _RENDERER_FP['mtimes'] != mtimes:
        h = hashlib.md5()
        for p, mt in zip(_RENDERER_PATHS, mtimes):
            if mt is None:
                continue
            try:
                with open(p, 'rb') as f:
                    h.update(f.read())
            except OSError:
                continue
        _RENDERER_FP['hash'] = h.hexdigest()[:12]
        _RENDERER_FP['mtimes'] = mtimes
    return _RENDERER_FP['hash']


def build_sig(sig):
    if sig is None:
        return None
    return f'{sig}#cfg:{config_fingerprint()}#gen:{renderer_fingerprint()}'


def artifact_status(db, kind, source_ref, ext, sig=None, static_root=None):
    root = static_root or _static_root()
    target = canonical_target(kind, source_ref, ext)
    if not target:
        return {'state': 'stale', 'filename': None, 'path': None,
                'publication_id': None, 'project_id': None}
    subdir, filename = target
    path = os.path.join(root, subdir, filename)
    out = {'state': 'stale', 'filename': filename, 'path': path,
           'publication_id': None, 'project_id': None}
    if not os.path.exists(path):
        return out
    row = db.execute('SELECT id, metadata FROM publications WHERE filename=?',
                     [filename]).fetchone()
    if not row:
        return out
    out['publication_id'] = row['id']
    try:
        meta = json.loads(row['metadata'] or '{}') or {}
    except (json.JSONDecodeError, TypeError):
        meta = {}
    out['project_id'] = meta.get('dtp_project_id')
    if sig is not None and meta.get('build_sig') != build_sig(sig):
        return out
    built_at = meta.get('built_at')
    if out['project_id'] and built_at:
        try:
            prow = db.execute('SELECT updated_at FROM dtp_projects WHERE id=?',
                              [out['project_id']]).fetchone()
        except sqlite3.OperationalError:
            prow = None
        if prow and (prow['updated_at'] or '') > built_at:
            out['state'] = 'restale'
            return out
    out['state'] = 'fresh'
    return out


def reconcile(db, verbose=True):
    merged = moved = 0
    rows = db.execute('SELECT id, title, filename, metadata, cover_image FROM publications').fetchall()
    projects = {}
    try:
        for r in db.execute('SELECT id, kind, source_ref FROM dtp_projects').fetchall():
            projects[r['id']] = (r['kind'], r['source_ref'])
    except sqlite3.OperationalError:
        return (0, 0)

    for row in rows:
        fn = row['filename'] or ''
        try:
            meta = json.loads(row['metadata'] or '{}') or {}
        except (json.JSONDecodeError, TypeError):
            continue
        pid = meta.get('dtp_project_id')
        if not pid or pid not in projects:
            continue
        kind, source_ref = projects[pid]
        ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
        target = canonical_target(kind, source_ref, ext)
        if not target or target[1] == fn:
            continue
        subdir, canon_fn = target
        src = locate(fn)
        dst = os.path.join(_static_root(), subdir, canon_fn)
        if not src:
            continue

        if os.path.exists(dst):
            if os.path.getmtime(src) > os.path.getmtime(dst):
                _replace_file(src, dst)
            else:
                _remove(src)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            _replace_file(src, dst)
        _remove(os.path.join(os.path.dirname(src), os.path.splitext(fn)[0] + '.dtp.json'))

        keeper = db.execute('SELECT id, metadata, cover_image FROM publications '
                            'WHERE filename=? AND id<>?', [canon_fn, row['id']]).fetchone()
        if keeper:
            try:
                km = json.loads(keeper['metadata'] or '{}') or {}
            except (json.JSONDecodeError, TypeError):
                km = {}
            km['dtp_project_id'] = pid
            km.setdefault('source', 'dtp')
            km.setdefault('kind', kind)
            km.setdefault('source_ref', source_ref)
            db.execute('UPDATE publications SET metadata=?, cover_image=COALESCE(?, cover_image), '
                       'file_size=? WHERE id=?',
                       [json.dumps(km, ensure_ascii=False),
                        keeper['cover_image'] or row['cover_image'],
                        os.path.getsize(dst) if os.path.exists(dst) else 0, keeper['id']])
            db.execute('DELETE FROM publications WHERE id=?', [row['id']])
            merged += 1
            if verbose:
                print(f'[ve_library] merged {fn} -> {canon_fn}')
        else:
            db.execute('UPDATE publications SET filename=?, file_size=? WHERE id=?',
                       [canon_fn, os.path.getsize(dst) if os.path.exists(dst) else 0, row['id']])
            moved += 1
            if verbose:
                print(f'[ve_library] moved {fn} -> {canon_fn}')
    db.commit()
    return (merged, moved)


def _replace_file(src, dst):
    import shutil
    if os.path.abspath(src) == os.path.abspath(dst):
        return
    shutil.copy2(src, dst)
    _remove(src)


def _remove(path):
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError as e:
            print(f'[ve_library] could not remove {path}: {e}')


def locate(fn):
    for dirpath, _web in scan_dirs():
        p = os.path.join(dirpath, fn)
        if os.path.isfile(p):
            return p
    return None


def web_base_for(fn):
    for dirpath, web in scan_dirs():
        if os.path.isfile(os.path.join(dirpath, fn)):
            return web
    return f'static/{PUBS_REL}'
