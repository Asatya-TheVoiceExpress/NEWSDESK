#!/usr/bin/env python3
import os, re, sys, json, shutil, argparse, stat, time, sqlite3, urllib.parse
import html as _html_mod

BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(BASE, 'emag')
DATA = os.path.join(OUT, 'data')

JSX_SRC = os.path.join(BASE, 'static', 'js')
JSX_KEEP = ['10-core.jsx', '20-cards.jsx', '30-read.jsx', '40-pages.jsx',
            '55-columns.jsx', '60-admin.jsx', '70-puzzles.jsx', '80-rest.jsx']
SHIM_SRC = os.path.join(BASE, 'emag_shim.jsx')
SHIM_OUT = '15-static-api.jsx'

DAILY_TOPICS = ['history','science','nature','art','music','film','literature',
  'geography','food','sports','technology','philosophy','astronomy','medicine',
  'architecture','mathematics','biology','chemistry','physics','economics',
  'psychology','mythology','language','culture','environment','ocean','space',
  'theatre','poetry','democracy','climate','innovation','tradition','discovery']

UPLOAD_RE = re.compile(r'/static/uploads/[\w.\-]+')


def log(msg):
    print(f'[ve-push] {msg}')


def robust_rmtree(path, retries=12, delay=0.8, max_delay=6.0):
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    last_err = None
    for attempt in range(retries):
        shutil.rmtree(path, onerror=_onerror)
        if not os.path.exists(path):
            return
        last_err = f'{path} still exists after rmtree attempt {attempt + 1}'
        time.sleep(min(delay * (attempt + 1), max_delay))
    raise RuntimeError(
        f'Could not fully remove {path} after {retries} attempts -- a file inside is '
        f'locked (commonly OneDrive sync or antivirus scanning mid-rebuild). '
        f'Close any program that might have it open and re-run. ({last_err})')


MANIFEST_NAME = '.ve_build_manifest.json'
_MANIFEST = set()


def track(path):
    try:
        _MANIFEST.add(os.path.relpath(path, OUT).replace('\\', '/'))
    except ValueError:
        pass
    return path


def unchanged(src, dst):
    try:
        if not os.path.exists(dst):
            return False
        s, d = os.stat(src), os.stat(dst)
        return s.st_size == d.st_size and d.st_mtime >= s.st_mtime - 1
    except OSError:
        return False


def copy_asset(src, dst):
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    track(dst)
    if unchanged(src, dst):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def prune(previous):
    gone = 0
    for rel in sorted(previous - _MANIFEST, key=len, reverse=True):
        p = os.path.join(OUT, rel)
        if (rel.startswith('.git') or rel == MANIFEST_NAME
                or not os.path.abspath(p).startswith(os.path.abspath(OUT))):
            continue
        try:
            if os.path.isfile(p):
                os.remove(p)
                gone += 1
        except OSError as e:
            log(f'  ! could not remove stale {rel}: {e}')
    for root, dirs, files in os.walk(OUT, topdown=False):
        if '.git' in root:
            continue
        if not dirs and not files and os.path.abspath(root) != os.path.abspath(OUT):
            try:
                os.rmdir(root)
            except OSError:
                pass
    return gone


def load_manifest():
    p = os.path.join(OUT, MANIFEST_NAME)
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as f:
                return set(json.load(f))
        except Exception:
            log('  ! manifest unreadable -- falling back to a directory scan')
    if not os.path.isdir(OUT):
        return set()
    found = set()
    for root, dirs, files in os.walk(OUT):
        dirs[:] = [d for d in dirs if d != '.git']
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), OUT).replace('\\', '/')
            if not rel.startswith('.git'):
                found.add(rel)
    return found


PRUNE_SANITY = 0.30


def prune_is_sane(previous, force=False):
    doomed = previous - _MANIFEST
    if not previous or not doomed:
        return True
    share = len(doomed) / max(len(previous), 1)
    if share <= PRUNE_SANITY or force:
        return True
    log(f'  ! refusing to prune {len(doomed)} of {len(previous)} files '
        f'({share:.0%}) -- that is more than {PRUNE_SANITY:.0%} and usually means '
        'the build did not finish, not that the content is gone. '
        'Nothing was deleted; re-run with --force-prune if this really is correct.')
    return False


def save_manifest():
    p = os.path.join(OUT, MANIFEST_NAME)
    _MANIFEST.add(MANIFEST_NAME)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(sorted(_MANIFEST), f)


def write_json(name, obj):
    path = os.path.join(DATA, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    return track(path)


def get_json(client, path):
    r = client.get(path)
    try:
        return r.get_json()
    except Exception:
        return None


def dump_data(client):
    counts = {}

    stubs, offset = [], 0
    while True:
        batch = get_json(client, f'/api/articles?status=published&limit=200&offset={offset}') or []
        stubs.extend(batch)
        if len(batch) < 200:
            break
        offset += 200
    articles = [get_json(client, f'/api/articles/{a["id"]}') for a in stubs]
    articles = [a for a in articles if a]

    media_dir = os.path.join(BASE, 'static', 'media')
    for a in articles:
        gfile = f'gazette_{a["id"]}.html'
        if os.path.exists(os.path.join(media_dir, gfile)):
            a['gazette_file'] = f'/static/media/{gfile}'
    art_dir = os.path.join(DATA, 'articles')
    os.makedirs(art_dir, exist_ok=True)
    search_index = {}
    listing = []
    for a in articles:
        write_json(os.path.join('articles', f'{a["id"]}.json'), a)
        body = a.get('content') or ''
        txt = re.sub(r'<[^>]+>', ' ', body)
        txt = _html_mod.unescape(txt)
        txt = re.sub(r'\s+', ' ', txt).strip().lower()
        if txt:
            search_index[str(a['id'])] = txt
        lite = {k: v for k, v in a.items() if k != 'content'}
        lite['has_content'] = bool(body)
        listing.append(lite)
    write_json('articles.json', listing)
    write_json('search-index.json', search_index)
    counts['article_details'] = len(articles)
    counts['articles'] = len(articles)

    write_json('categories.json', get_json(client, '/api/categories') or [])
    write_json('sections.json', get_json(client, '/api/sections') or [])
    write_json('tags.json', get_json(client, '/api/tags') or [])

    authors = get_json(client, '/api/authors') or []
    for a in authors:
        a['links'] = get_json(client, f'/api/authors/{a["id"]}/links') or []
        a['contributions'] = get_json(client, f'/api/authors/{a["id"]}/contributions') or []
    write_json('authors.json', authors)
    counts['authors'] = len(authors)

    write_json('series.json', get_json(client, '/api/series') or [])

    months = get_json(client, '/api/newsletters/months') or []
    issues = [get_json(client, f'/api/newsletters/{m["year"]}/{m["month"]}') for m in months]
    for m in months:
        bfile = f'broadsheet_{m["year"]}_{m["month"]:02d}'
        for ext in ('pdf', 'html'):
            fp = os.path.join(media_dir, f'{bfile}.{ext}')
            if os.path.exists(fp):
                m['broadsheet_file'] = f'/static/media/{bfile}.{ext}'
                break
        sfile = f'broadsheet_scroll_{m["year"]}_{m["month"]:02d}.html'
        sp = os.path.join(media_dir, sfile)
        if not os.path.exists(sp):
            try:
                r = client.get(f'/api/newsletters/{m["year"]}/{m["month"]}/broadsheet?format=scroll')
                if r.status_code == 200 and r.data:
                    with open(sp, 'wb') as f:
                        f.write(r.data)
            except Exception as e:
                log(f'  ! scroll view for {m["year"]}-{m["month"]:02d} failed: {e}')
        if os.path.exists(sp):
            m['broadsheet_scroll_file'] = f'/static/media/{sfile}'
    newsletter_issues = [i for i in issues if i]
    write_json('newsletters.json', {'months': months, 'issues': newsletter_issues})
    counts['newsletter_months'] = len(months)

    columns = get_json(client, '/api/columns') or []
    columns = [c for c in columns if not c.get('is_private')]
    full_columns = [get_json(client, f'/api/columns/{c["slug"]}') for c in columns]
    write_json('columns.json', [c for c in full_columns if c])
    counts['columns'] = len(full_columns)

    pages = {}
    for slug in ('about', 'submissions'):
        p = get_json(client, f'/api/pages/{slug}')
        if p and not p.get('error'):
            pages[slug] = p
    write_json('pages.json', pages)

    pubs = (get_json(client, '/api/publications') or {}).get('publications', [])
    for p in pubs:
        fn = p.get('filename')
        if not fn:
            continue
        for sub in ('publications', 'media'):
            if os.path.exists(os.path.join(BASE, 'static', sub, fn)):
                p['download_url'] = f"/static/{sub}/{fn}"
                break
    write_json('publications.json', pubs)
    counts['publications'] = len(pubs)

    return articles, authors, [c for c in full_columns if c], pubs, (months, newsletter_issues), counts


def dump_letters():
    db_path = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))
    if not os.path.exists(db_path):
        write_json('letters.json', [])
        return 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_flag = 'is_public' in {r[1] for r in conn.execute('PRAGMA table_info(letters)')}
        where = ('WHERE is_public=1' if has_flag else "WHERE source='sheet'")
        letters = conn.execute(
            "SELECT id,guest_name,subject,status,created_at FROM letters "
            f"{where} ORDER BY created_at DESC").fetchall()
        out = []
        for l in letters:
            msgs = conn.execute(
                "SELECT sender,content,created_at FROM letter_messages "
                "WHERE letter_id=? ORDER BY created_at", [l['id']]).fetchall()
            out.append({
                'id': l['id'], 'subject': l['subject'], 'guest_name': l['guest_name'],
                'status': l['status'], 'created_at': l['created_at'],
                'messages': [dict(m) for m in msgs],
            })
    finally:
        conn.close()
    write_json('letters.json', out)
    return len(out)


def dump_reader_state():
    db_path = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))
    if not os.path.exists(db_path):
        write_json('reader_state.json', {})
        return 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    state = {}

    def bucket(user, key):
        u = (user or '').strip().lower()
        if not u:
            return None
        return state.setdefault(u, {'comments': [], 'letters': [], 'ebooks': []})[key]

    def has_col(table, col):
        return col in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}

    try:
        if has_col('comments', 'username'):
            for r in conn.execute(
                    "SELECT article_id,content,status,created_at,username FROM comments "
                    "WHERE username IS NOT NULL AND TRIM(username) <> ''"):
                b = bucket(r['username'], 'comments')
                if b is not None:
                    b.append({'article_id': r['article_id'], 'status': r['status'],
                              'created_at': r['created_at'],
                              'excerpt': (r['content'] or '')[:140]})

        if has_col('letters', 'username'):
            for r in conn.execute(
                    "SELECT id,subject,status,created_at,username FROM letters "
                    "WHERE username IS NOT NULL AND TRIM(username) <> ''"):
                b = bucket(r['username'], 'letters')
                if b is None:
                    continue
                replies = conn.execute(
                    "SELECT content,created_at FROM letter_messages "
                    "WHERE letter_id=? AND sender <> 'guest' ORDER BY created_at",
                    [r['id']]).fetchall()
                b.append({'id': r['id'], 'subject': r['subject'], 'status': r['status'],
                          'created_at': r['created_at'], 'replied': bool(replies),
                          'replies': [dict(x) for x in replies]})

        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name='ebook_requests'").fetchone():
            for r in conn.execute(
                    "SELECT title,status,download_url,publication_id,built_at,username "
                    "FROM ebook_requests WHERE username IS NOT NULL AND TRIM(username) <> ''"):
                b = bucket(r['username'], 'ebooks')
                if b is None:
                    continue
                url, fn = '', None
                if r['publication_id']:
                    got = conn.execute("SELECT filename FROM publications WHERE id=?",
                                       [r['publication_id']]).fetchone()
                    fn = got['filename'] if got else None
                if fn:
                    for sub in ('publications', 'media'):
                        if os.path.exists(os.path.join(BASE, 'static', sub, fn)):
                            url = f'static/{sub}/{fn}'
                            break
                b.append({'title': r['title'],
                          'status': r['status'] if url else 'pending',
                          'publication_id': r['publication_id'],
                          'built_at': r['built_at'], 'download_url': url})
    finally:
        conn.close()

    write_json('reader_state.json', state)
    return len(state)


def bake_crossword_words(existing, skip=False):
    if skip:
        write_json('puzzles/crossword-words.json', existing)
        return len(existing)

    import urllib.request as ur
    result = {}
    for i, topic in enumerate(DAILY_TOPICS):
        key = str(i)
        if key in existing and existing[key].get('words'):
            result[key] = existing[key]
            continue
        try:
            url = ('https://api.datamuse.com/words?rel_trg=' +
                   urllib.parse.quote(topic) + '&max=70&md=d')
            with ur.urlopen(url, timeout=8) as r:
                raw = json.loads(r.read().decode('utf-8'))
            words = []
            seen = set()
            for w in raw:
                word = w.get('word', '')
                if not re.fullmatch(r'[a-z]+', word) or not (4 <= len(word) <= 9):
                    continue
                if word.upper() in seen:
                    continue
                seen.add(word.upper())
                defs = w.get('defs') or []
                clue = re.sub(r'[;,].*', '', re.sub(r'^[a-z]+\t', '', defs[0] if defs else '')).strip()
                words.append({'word': word.upper(), 'clue': clue or f'A word related to {topic}'})
            words.sort(key=lambda w: -len(w['word']))
            result[key] = {'words': words[:22], 'topic': topic}
        except Exception as e:
            result[key] = existing.get(key) or {'words': [], 'topic': topic, 'error': str(e)}
    write_json('puzzles/crossword-words.json', result)
    return len(result)


def bake_link_previews(client, articles, existing, skip=False):
    urls = set()
    for a in articles:
        for c in (a.get('citations') or []):
            u = c.get('url')
            if u:
                urls.add(u)
    if skip:
        write_json('link-previews.json', existing)
        return len(existing)
    result = dict(existing)
    for u in sorted(urls):
        if u in result and not result[u].get('error'):
            continue
        result[u] = get_json(client, '/api/link-preview?url=' + urllib.parse.quote(u, safe='')) or {'url': u}
    write_json('link-previews.json', result)
    return len(result)


WEB_IMG_MAX_PX = 1800
WEB_IMG_QUALITY = 82
WEB_IMG_MIN_BYTES = 250 * 1024


def copy_web_image(src, dst):
    try:
        if os.path.getsize(src) < WEB_IMG_MIN_BYTES:
            shutil.copy2(src, dst); return
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        ext = os.path.splitext(dst)[1].lower()
        fmt = {'.png': 'PNG', '.webp': 'WEBP'}.get(ext, 'JPEG')
        tmp = dst + '.tmp'
        with Image.open(src) as im:
            im.load()
            if fmt == 'PNG':
                has_alpha = im.mode in ('RGBA', 'LA') or (
                    im.mode == 'P' and 'transparency' in im.info)
                if not has_alpha:
                    fmt = 'JPEG'
                    dst = os.path.splitext(dst)[0] + '.jpg'
                    tmp = dst + '.tmp'
            if max(im.size) > WEB_IMG_MAX_PX:
                im.thumbnail((WEB_IMG_MAX_PX, WEB_IMG_MAX_PX), Image.LANCZOS)
            if fmt == 'JPEG':
                im.convert('RGB').save(tmp, format='JPEG', quality=WEB_IMG_QUALITY,
                                       optimize=True, progressive=True)
            elif fmt == 'WEBP':
                im.save(tmp, format='WEBP', quality=WEB_IMG_QUALITY, method=4)
            else:
                im.save(tmp, format='PNG', optimize=True)
        plain = os.path.join(os.path.dirname(dst), os.path.basename(src))
        if os.path.getsize(tmp) < os.path.getsize(src):
            os.replace(tmp, dst)
            if os.path.basename(dst) != os.path.basename(src):
                return os.path.basename(src), os.path.basename(dst)
        else:
            os.remove(tmp); shutil.copy2(src, plain)
    except Exception as e:
        log(f'  ! image downscale failed for {os.path.basename(src)} ({e}) -- copying as-is')
        try:
            shutil.copy2(src, os.path.join(os.path.dirname(dst), os.path.basename(src)))
        except Exception:
            pass
    return None


def rewrite_image_refs(renames):
    if not renames:
        return 0
    hits = 0
    for fn in os.listdir(DATA):
        if not fn.endswith('.json'):
            continue
        fp = os.path.join(DATA, fn)
        with open(fp, encoding='utf-8') as f:
            txt = f.read()
        new = txt
        for old, repl in renames.items():
            new = new.replace(old, repl)
        if new != txt:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(new)
            hits += 1
    return hits


READER_DESK_CSS = """
.ve-desk{position:fixed;right:1rem;bottom:1rem;z-index:9999;font-family:var(--fb,inherit);}
.ve-desk-pill{background:#111;color:#fff;border:1px solid #111;border-radius:2rem;
  padding:.5rem 1rem;font-size:.85rem;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.25);}
.ve-desk-pill:hover{background:#333;}
.ve-desk-panel{position:absolute;right:0;bottom:3rem;width:min(23rem,calc(100vw - 2rem));
  max-height:min(30rem,70vh);overflow-y:auto;background:#fff;color:#111;
  border:1px solid #111;padding:1rem;box-shadow:0 6px 24px rgba(0,0,0,.28);}
.ve-desk-h{margin:0 0 .5rem;font-size:1rem;}
.ve-desk-h4{margin:.9rem 0 .35rem;font-size:.8rem;text-transform:uppercase;
  letter-spacing:.06em;border-bottom:1px solid #ddd;padding-bottom:.2rem;}
.ve-desk-note{font-size:.75rem;color:#555;margin:.4rem 0;}
.ve-desk-empty{font-size:.78rem;color:#888;margin:.2rem 0;}
.ve-desk-row{display:flex;gap:.4rem;align-items:center;justify-content:space-between;}
.ve-desk-input{width:100%;padding:.45rem;border:1px solid #111;margin:.3rem 0;font-size:.85rem;}
.ve-desk-btn{background:#fff;color:#111;border:1px solid #111;padding:.35rem .7rem;
  font-size:.78rem;cursor:pointer;}
.ve-desk-btn:hover{background:#111;color:#fff;}
.ve-desk-msg{font-size:.75rem;color:#a00;margin:.3rem 0 0;min-height:1em;}
.ve-desk-item{border-bottom:1px solid #eee;padding:.45rem 0;font-size:.82rem;}
.ve-desk-item strong{display:block;margin-bottom:.2rem;}
.ve-desk-badge{display:inline-block;background:#111;color:#fff;font-size:.66rem;
  padding:.1rem .4rem;text-transform:uppercase;letter-spacing:.04em;}
.ve-desk-badge-wait{background:#fff;color:#555;border:1px solid #bbb;}
.ve-desk-badge-no{background:#a00;}
.ve-desk-reply{margin:.35rem 0;padding:.4rem .5rem;background:#f6f6f6;
  border-left:2px solid #111;font-size:.8rem;white-space:pre-wrap;}
.ve-desk-link{display:inline-block;margin-left:.4rem;font-size:.78rem;}
.ve-desk-when{color:#888;font-size:.7rem;margin-top:.2rem;}
@media (prefers-color-scheme:dark){
  .ve-desk-panel{background:#141414;color:#eee;border-color:#eee;}
  .ve-desk-h4{border-bottom-color:#333;}
  .ve-desk-item{border-bottom-color:#262626;}
  .ve-desk-note,.ve-desk-empty,.ve-desk-when{color:#999;}
  .ve-desk-input{background:#000;color:#eee;border-color:#eee;}
  .ve-desk-btn{background:#141414;color:#eee;border-color:#eee;}
  .ve-desk-btn:hover{background:#eee;color:#111;}
  .ve-desk-reply{background:#1e1e1e;border-left-color:#eee;}
  .ve-desk-badge{background:#eee;color:#111;}
  .ve-desk-badge-wait{background:#141414;color:#bbb;border-color:#555;}
}
"""


def copy_static_assets(articles, authors, columns, pubs, newsletter_months=()):
    dst_css = os.path.join(OUT, 'static', 'css')
    os.makedirs(dst_css, exist_ok=True)
    copy_asset(os.path.join(BASE, 'static', 'css', 'app.css'), dst_css)
    with open(os.path.join(dst_css, 'app.css'), 'a', encoding='utf-8') as _cf:
        _cf.write(READER_DESK_CSS)

    logo = os.path.join(BASE, 'static', 'tve_logo.png')
    if os.path.exists(logo):
        copy_asset(logo, os.path.join(OUT, 'static'))

    media_src = os.path.join(BASE, 'static', 'media')
    media_dst = os.path.join(OUT, 'static', 'media')
    os.makedirs(media_dst, exist_ok=True)
    referenced_media = set()
    for a in articles:
        if a.get('gazette_file'):
            referenced_media.add(os.path.basename(a['gazette_file']))
    for fn in os.listdir(media_src) if os.path.isdir(media_src) else []:
        if fn.startswith('broadsheet_'):
            referenced_media.add(fn)
    pub_src = os.path.join(BASE, 'static', 'publications')
    pub_dst = os.path.join(OUT, 'static', 'publications')
    if os.path.isdir(pub_src):
        os.makedirs(pub_dst, exist_ok=True)
        for p in pubs:
            fn = p.get('filename')
            if not fn:
                continue
            if os.path.exists(os.path.join(pub_src, fn)):
                copy_asset(os.path.join(pub_src, fn), pub_dst)
            else:
                referenced_media.add(fn)

    for fn in referenced_media:
        src = os.path.join(media_src, fn)
        if os.path.exists(src):
            copy_asset(src, media_dst)

    upload_src = os.path.join(BASE, 'static', 'uploads')
    upload_dst = os.path.join(OUT, 'static', 'uploads')
    blobs = []
    for a in articles:
        blobs += [a.get('featured_image', ''), a.get('content', '')]
    for au in authors:
        blobs.append(au.get('avatar_url', '') or '')
    for c in columns:
        blobs.append(c.get('cover_image', '') or '')
        for e in c.get('entries', []):
            blobs += [e.get('cover_image', '') or '', e.get('body', '') or '']
            for pn in (e.get('panels') or []):
                blobs.append(pn.get('image', '') or '')
    for p in pubs:
        blobs.append(p.get('cover_image', '') or '')
    months_seq, issues_seq = newsletter_months if isinstance(newsletter_months, tuple)         else (newsletter_months, ())
    for m in months_seq:
        blobs.append(m.get('cover_image', '') or '')
    for iss in issues_seq:
        blobs.append(json.dumps(iss, ensure_ascii=False))
    referenced = set()
    for b in blobs:
        referenced.update(UPLOAD_RE.findall(b or ''))
    if referenced:
        os.makedirs(upload_dst, exist_ok=True)
    n = 0
    renames = {}
    skipped = 0
    for rel in referenced:
        fn = os.path.basename(rel)
        src = os.path.join(upload_src, fn)
        if not os.path.exists(src):
            continue
        dst = os.path.join(upload_dst, fn)
        alt = os.path.splitext(dst)[0] + '.jpg'
        done = None
        for cand in (dst, alt):
            try:
                if os.path.exists(cand) and os.stat(cand).st_mtime >= os.stat(src).st_mtime - 1:
                    done = cand
                    break
            except OSError:
                pass
        if done:
            track(done)
            if os.path.basename(done) != fn:
                renames[fn] = os.path.basename(done)
            skipped += 1
            n += 1
            continue
        r = copy_web_image(src, dst)
        track(alt if (r and r[1].endswith('.jpg')) else dst)
        if r:
            renames[r[0]] = r[1]
        n += 1
    if skipped:
        log(f'  {skipped} upload(s) already current -- not re-encoded')
    if renames:
        log(f'  {len(renames)} opaque PNG(s) re-encoded as JPEG; '
            f'repointed refs in {rewrite_image_refs(renames)} data file(s)')
    return n


def copy_frontend():
    js_dst = os.path.join(OUT, 'static', 'js')
    os.makedirs(js_dst, exist_ok=True)

    for name in JSX_KEEP:
        copy_asset(os.path.join(JSX_SRC, name), os.path.join(js_dst, name))

    copy_asset(SHIM_SRC, os.path.join(js_dst, SHIM_OUT))

    cfg_src = os.path.join(BASE, 'voiceexpressstand', 'config.json')
    if os.path.exists(cfg_src):
        copy_asset(cfg_src, os.path.join(DATA, 'config.json'))
    else:
        write_json('config.json', {'brand': 'The Voice Express', 'api': '', 'pay': {}})

    build = time.strftime('%Y%m%d%H%M%S')
    scripts = ['10-core.jsx', SHIM_OUT, '20-cards.jsx', '30-read.jsx', '40-pages.jsx',
               '55-columns.jsx', '60-admin.jsx', '70-puzzles.jsx', '80-rest.jsx']
    tags = '\n'.join(f'<script type="text/babel" src="static/js/{s}?v={build}"></script>' for s in scripts)
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Voice Express — Independent journalism. Truth Takes Time.">
<title>Voice Express — Truth Takes Time</title>
<link rel="icon" type="image/png" href="static/tve_logo.png">
<link rel="apple-touch-icon" href="static/tve_logo.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,900;1,400;1,700&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Courier+Prime:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone@8.0.4/babel.min.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>window.VE={{product:"full",build:"{build}",caps:{{admin:false,accounts:false,server_render:false}}}};</script>
<link rel="stylesheet" href="static/css/app.css?v={build}">
</head>
<body>
<div id="root"></div>
{tags}
</body>
</html>
'''
    with open(track(os.path.join(OUT, 'index.html')), 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-crossword', action='store_true')
    ap.add_argument('--no-previews', action='store_true')
    ap.add_argument('--force-prune', action='store_true',
                    help='delete stale files even when that is most of the build '
                         '(the safety check assumes a big prune means a broken run)')
    args = ap.parse_args()

    cw_cache_path = os.path.join(DATA, 'puzzles', 'crossword-words.json')
    lp_cache_path = os.path.join(DATA, 'link-previews.json')
    cw_cache = json.load(open(cw_cache_path, encoding='utf-8')) if os.path.exists(cw_cache_path) else {}
    lp_cache = json.load(open(lp_cache_path, encoding='utf-8')) if os.path.exists(lp_cache_path) else {}

    cname_path = os.path.join(OUT, 'CNAME')
    cname = None
    if os.path.exists(cname_path):
        with open(cname_path, encoding='utf-8') as f:
            cname = f.read().strip()

    previous = load_manifest()
    os.makedirs(DATA, exist_ok=True)

    sys.path.insert(0, BASE)
    import app as ve_app
    client = ve_app.app.test_client()

    articles, authors, columns, pubs, newsletters, counts = dump_data(client)
    n_cw = bake_crossword_words(cw_cache, skip=args.no_crossword)
    n_lp = bake_link_previews(client, articles, lp_cache, skip=args.no_previews)
    n_lt = dump_letters()
    n_rs = dump_reader_state()
    n_up = copy_static_assets(articles, authors, columns, pubs, newsletters)
    copy_frontend()

    open(track(os.path.join(OUT, '.nojekyll')), 'w').close()
    if cname:
        with open(track(os.path.join(OUT, 'CNAME')), 'w', encoding='utf-8') as f:
            f.write(cname + chr(10))
        log(f'  CNAME preserved -> {cname}')
    else:
        log('  ! no CNAME in emag/ -- if this site uses a custom domain '
            '(emag.thevoiceexpress.in), add the file or Pages will serve it '
            'from the default URL, where absolute /static/ paths 404')

    if previous and prune_is_sane(previous, args.force_prune):
        removed = prune(previous)
        if removed:
            log(f'  Pruned {removed} file(s) no longer part of the build')
    save_manifest()

    log(f'{OUT}')
    log(f'  Articles       {counts["articles"]}')
    log(f'  Authors        {counts["authors"]}')
    log(f'  Newsletters    {counts["newsletter_months"]} months')
    log(f'  Columns        {counts["columns"]}')
    log(f'  Publications   {counts["publications"]}')
    log(f'  Letters        {n_lt}')
    log(f'  Readers w/ state {n_rs}')
    log(f'  Crossword banks{" " * 0} {n_cw}/{len(DAILY_TOPICS)} topics')
    log(f'  Link previews  {n_lp}')
    log(f'  Uploaded images{" " * 0} {n_up}')


if __name__ == '__main__':
    main()
