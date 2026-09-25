#!/usr/bin/env python3
import os, re, sys, time, json, sqlite3, argparse, urllib.request, urllib.parse
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))
STAND_CONFIG = os.path.join(BASE, 'voiceexpressstand', 'config.json')
EMAG_LETTERS_JSON = os.path.join(BASE, 'emag', 'data', 'letters.json')
SHEET_SECRET_FILE = os.path.join(BASE, '.ve_sheet_secret')

try:
    import ve_library as _ve_library
except Exception:
    _ve_library = None
import ve.db as _ve_db


def log(msg):
    print(f'[site_data_get] {msg}')


def api_url():
    env = os.environ.get('VE_API_ENDPOINT')
    if env:
        return env
    if not os.path.exists(STAND_CONFIG):
        sys.exit(f'[site_data_get] {STAND_CONFIG} not found -- cannot find the Apps Script URL')
    with open(STAND_CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    api = cfg.get('api')
    if not api:
        sys.exit(f'[site_data_get] {STAND_CONFIG} has no "api" field -- deploy tools/stand_apps_script.gs and paste its /exec URL in')
    return api


def sheet_secret():
    env = os.environ.get('VE_SHEET_SECRET')
    if env:
        return env.strip()
    if os.path.exists(SHEET_SECRET_FILE):
        with open(SHEET_SECRET_FILE, encoding='utf-8') as f:
            secret = f.read().strip()
        if secret:
            return secret
    sys.exit('[site_data_get] the Sheet secret is missing -- put it in '
             f'{SHEET_SECRET_FILE} (or set VE_SHEET_SECRET); refusing to call the Sheet without it')


def call(action, _tries=4, **params):
    params = {'action': action, **params}
    params['secret'] = sheet_secret()
    url = api_url() + '?' + urllib.parse.urlencode(params)
    last = None
    for attempt in range(1, _tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            if attempt < _tries:
                time.sleep(2 * attempt)
    raise RuntimeError(f'{action}: failed after {_tries} attempts -- {last}')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def migrate(conn):
    _ve_db.migrate(conn)


def import_letters(conn):
    rows = call('letters_export')
    if not isinstance(rows, list):
        log(f'letters_export failed: {rows}')
        return 0
    if not rows:
        log('letters: nothing new')
        return 0
    already = {r['sheet_row'] for r in conn.execute(
        "SELECT sheet_row FROM letters WHERE sheet_row IS NOT NULL AND source='sheet'")}
    imported_sheet_rows = []
    reflagged = []
    for row in rows:
        if row['row'] in already:
            reflagged.append(row['row'])
            continue
        now = row.get('time') or datetime.utcnow().isoformat()
        cur = conn.execute(
            "INSERT INTO letters (guest_name,subject,status,created_at,last_message_at,source,"
            "sheet_row,username,is_public) VALUES (?,?,?,?,?,?,?,?,1)",
            [row.get('name') or 'Anonymous', row.get('subject') or '(no subject)', 'open', now, now, 'sheet',
             row['row'], (row.get('username') or '').strip() or None])
        lid = cur.lastrowid
        conn.execute(
            "INSERT INTO letter_messages (letter_id,sender,content,created_at) VALUES (?,?,?,?)",
            [lid, 'guest', row.get('content') or '', now])
        imported_sheet_rows.append(row['row'])
        already.add(row['row'])
    conn.commit()
    if imported_sheet_rows or reflagged:
        call('letters_mark_imported',
             rows=','.join(str(r) for r in imported_sheet_rows + reflagged))
    if reflagged:
        log(f'letters: {len(reflagged)} already imported -- re-flagged on the Sheet '
            '(a previous run marked them locally but not there)')
    log(f'letters: imported {len(imported_sheet_rows)}')
    return len(imported_sheet_rows)


def import_comments(conn):
    rows = call('comments_export')
    if not isinstance(rows, list):
        log(f'comments_export failed: {rows}')
        return 0
    seen_rows = {r['sheet_row'] for r in conn.execute(
        'SELECT sheet_row FROM comments WHERE sheet_row IS NOT NULL')}
    legacy = {(str(r['target_ref']), r['display_name'], r['content'])
              for r in conn.execute('SELECT target_ref,display_name,content FROM comments '
                                    'WHERE sheet_row IS NULL')}
    n = 0
    for row in rows:
        sheet_row = row.get('row')
        key = (str(row.get('target_ref') or row.get('article_id') or ''),
               row.get('display_name') or '', row.get('content') or '')
        if not key[0]:
            continue
        if sheet_row:
            if sheet_row in seen_rows:
                continue
            if key in legacy:
                conn.execute('UPDATE comments SET sheet_row=? WHERE sheet_row IS NULL '
                             'AND target_ref=? AND display_name=? AND content=?',
                             [sheet_row, key[0], key[1], key[2]])
                legacy.discard(key)
                seen_rows.add(sheet_row)
                continue
        elif key in legacy:
            continue
        t_kind = 'publication' if (row.get('target_kind') == 'publication') else 'article'
        t_ref = str(row.get('target_ref') or key[0])
        art_id = int(t_ref) if (t_kind == 'article' and t_ref.isdigit()) else None
        conn.execute(
            "INSERT INTO comments (target_kind,target_ref,article_id,display_name,content,"
            "status,created_at,sheet_row,username,selected_text) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [t_kind, t_ref, art_id, key[1], key[2], 'approved',
             row.get('created_at') or datetime.utcnow().isoformat(),
             sheet_row, (row.get('username') or '').strip() or None,
             (row.get('selected_text') or '').strip() or None])
        if sheet_row:
            seen_rows.add(sheet_row)
        else:
            legacy.add(key)
        n += 1
    conn.commit()
    log(f'comments: mirrored {n} new')
    return n


def import_likes(conn):
    rows = call('likes_export')
    if not isinstance(rows, list):
        log(f'likes_export failed: {rows}')
        return 0
    for row in rows:
        ref = str(row.get('target_ref') or row.get('article_id') or '')
        if not ref:
            continue
        kind = 'publication' if (row.get('target_kind') == 'publication') else (
            'article' if ref.isdigit() else 'publication')
        aid = int(ref) if (kind == 'article' and ref.isdigit()) else None
        conn.execute(
            "INSERT INTO article_likes (target_kind,target_ref,article_id,count,updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(target_kind,target_ref) DO UPDATE SET "
            "count=excluded.count, updated_at=excluded.updated_at",
            [kind, ref, aid, row.get('count') or 0, datetime.utcnow().isoformat()])
    conn.commit()
    log(f'likes: mirrored {len(rows)} article(s)')
    return len(rows)


def import_messages(conn):
    rows = call('messages_export')
    if not isinstance(rows, list):
        log(f'messages_export failed: {rows}')
        return 0
    existing = {(r['from_name'], r['body'], r['created_at'])
                for r in conn.execute('SELECT from_name,body,created_at FROM site_messages')}
    n = 0
    for row in rows:
        key = (row.get('from') or '', row.get('message') or '', row.get('time') or '')
        if key in existing or not key[1]:
            continue
        conn.execute(
            "INSERT INTO site_messages (from_name,body,about,ip_address,created_at) VALUES (?,?,?,?,?)",
            [key[0], key[1], row.get('about') or '', row.get('ip') or '', key[2] or datetime.utcnow().isoformat()])
        existing.add(key)
        n += 1
    conn.commit()
    log(f'messages: mirrored {n} new')
    return n


def import_subscribers(conn):
    rows = call('subscribers_export')
    if not isinstance(rows, list):
        log(f'subscribers_export failed: {rows}')
        return 0
    n = 0
    for row in rows:
        email = (row.get('email') or '').strip().lower()
        if not email:
            continue
        cur = conn.execute(
            "INSERT INTO newsletter_subscribers (email,ip_address,subscribed_at) VALUES (?,?,?) "
            "ON CONFLICT(email) DO NOTHING",
            [email, row.get('ip') or '', row.get('time') or datetime.utcnow().isoformat()])
        n += cur.rowcount
    conn.commit()
    log(f'subscribers: mirrored {n} new')
    return n


def import_activity(conn):
    rows = call('activity_export')
    if not isinstance(rows, list):
        log(f'activity_export failed: {rows}')
        return 0
    existing = {(r['kind'], r['title'], r['file'], r['ref'], r['username'], r['occurred_at'])
                for r in conn.execute('SELECT kind,title,file,ref,username,occurred_at '
                                      'FROM site_activity')}
    n = 0
    for row in rows:
        key = (row.get('kind') or '', row.get('title') or '', row.get('file') or '',
               row.get('ref') or '', row.get('user') or '', row.get('time') or '')
        if key in existing:
            continue
        conn.execute(
            "INSERT INTO site_activity (kind,title,file,type,amount,currency,via,username,ip_address,ref,occurred_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [key[0], key[1], key[2], row.get('type') or '',
             row.get('amount') or 0, row.get('currency') or '', row.get('via') or '',
             key[4], row.get('ip') or '', key[3], key[5] or datetime.utcnow().isoformat()])
        existing.add(key)
        n += 1
    conn.commit()
    log(f'activity: mirrored {n} new')
    return n


def import_accounts(conn):
    rows = call('users_export')
    if not isinstance(rows, list):
        log(f'users_export failed: {rows}')
        return 0
    for row in rows:
        u = (row.get('username') or '').strip()
        if not u:
            continue
        conn.execute(
            "INSERT INTO newsstand_accounts (username,library,hearts,created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(username) DO UPDATE SET library=excluded.library, hearts=excluded.hearts",
            [u, row.get('library') or '[]', row.get('hearts') or 0, row.get('created') or datetime.utcnow().isoformat()])
    conn.commit()
    log(f'newsstand accounts: synced {len(rows)}')
    return len(rows)


def import_sheet_annotations(conn):
    rows = call('annotations_export')
    if not isinstance(rows, list):
        log(f'annotations_export failed: {rows}')
        return 0
    existing = {(str(r['target_ref'] or r['article_id'] or ''), r['selected_text'],
                 r['note'], r['created_at'])
                for r in conn.execute('SELECT article_id,target_ref,selected_text,note,'
                                      'created_at FROM sheet_annotations')}
    n = 0
    for row in rows:
        t_kind = 'publication' if (row.get('target_kind') == 'publication') else 'article'
        t_ref = str(row.get('target_ref') or row.get('article_id') or '')
        key = (t_ref, row.get('selected_text') or '', row.get('note') or '', row.get('time') or '')
        if key in existing or not key[2]:
            continue
        art_id = int(t_ref) if (t_kind == 'article' and t_ref.isdigit()) else None
        conn.execute(
            "INSERT INTO sheet_annotations (article_id,target_kind,target_ref,selected_text,"
            "note,created_at,username) VALUES (?,?,?,?,?,?,?)",
            [art_id, t_kind, t_ref, key[1], key[2], key[3] or datetime.utcnow().isoformat(),
             (row.get('username') or '').strip() or None])
        existing.add(key)
        n += 1
    conn.commit()
    log(f'annotations: mirrored {n} new')
    return n


def build_ebook_requests(conn):
    rows = call('ebook_requests_export')
    if not isinstance(rows, list):
        log(f'ebook_requests_export failed: {rows}')
        return 0

    sys.path.insert(0, BASE)
    import app as ve_app

    built_rows = []
    failed_rows = []
    n = 0

    def _fail(row, reason):
        log(f"ebook request row {row.get('row')}: {reason}")
        if not row.get('row'):
            return
        failed_rows.append((row['row'], reason))
        conn.execute(
            "INSERT OR REPLACE INTO ebook_requests "
            "(sheet_row,username,requester_name,title,article_ids,status,error,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [row['row'], (row.get('username') or '').strip() or None,
             row.get('name') or 'Anonymous', (row.get('title') or '')[:200],
             str(row.get('article_ids') or ''), 'failed', reason[:500],
             row.get('time') or datetime.utcnow().isoformat()])
        conn.commit()

    for row in rows:
        try:
            title = (row.get('title') or 'Voice Express Collection').strip()[:200]
            creator = (row.get('creator') or '').strip()[:200]
            description = (row.get('description') or '').strip()[:1000]
            article_ids = [int(x) for x in re.split(r'[,\s]+', str(row.get('article_ids') or ''))
                           if x.strip().isdigit()][:50]
            if not article_ids:
                _fail(row, 'no usable article ids -- the list was stored as a '
                           f'single value ({row.get("article_ids")!r}), so the '
                           'individual ids cannot be recovered')
                continue
            articles = []
            for aid in article_ids:
                r = conn.execute(
                    "SELECT a.*,au.name as author_name,c.name as category_name,"
                    "s.name as section_name,s.slug as section_slug "
                    "FROM articles a LEFT JOIN authors au ON a.author_id=au.id "
                    "LEFT JOIN categories c ON a.category_id=c.id "
                    "LEFT JOIN sections s ON a.section_id=s.id "
                    "WHERE a.id=? AND a.status='published'", [aid]).fetchone()
                if r:
                    articles.append(ve_app._article_print_dict(conn, r))
            if not articles:
                _fail(row, f'none of the requested articles ({article_ids}) are published')
                continue
            ve_app._localize_articles(conn, articles)
            epub_bytes = ve_app.build_epub(articles, title, creator, description)
            safe_name = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:60] or 'ebook'
            pre_max = conn.execute(
                "SELECT COALESCE(MAX(id),0) FROM publications").fetchone()[0]
            ve_app._save_to_library(conn, title, 'epub', epub_bytes, articles, safe_name, 'epub',
                                     creator=creator, description=description,
                                     extra_meta={'reader_generated': True,
                                                 'requested_by': (row.get('username') or '').strip()
                                                                 or None})
            made = conn.execute(
                "SELECT id,filename FROM publications WHERE id>? ORDER BY id DESC LIMIT 1",
                [pre_max]).fetchone()
            if not made:
                _fail(row, 'the ebook built but no publication row appeared')
                continue
            pub_id, pub_file = made['id'], made['filename']
            download_url = f'/api/publications/{pub_id}/download'
            conn.execute(
                "INSERT OR REPLACE INTO ebook_requests "
                "(sheet_row,username,requester_name,email,title,article_ids,publication_id,"
                " download_url,status,created_at,built_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [row['row'], (row.get('username') or '').strip() or None,
                 row.get('name') or 'Anonymous',
                 (row.get('email') or '').strip().lower() or None, title,
                 ','.join(str(i) for i in article_ids), pub_id, download_url, 'built',
                 row.get('time') or datetime.utcnow().isoformat(),
                 datetime.utcnow().isoformat()])
            conn.commit()
            built_rows.append((row['row'], pub_id, download_url))
            n += 1
            log(f"ebook request row {row['row']}: built \"{title}\" ({len(articles)} articles)")
        except Exception as e:
            _fail(row, f'{type(e).__name__}: {e}')
    if failed_rows:
        res = call('ebook_requests_set_failed',
                   rows=','.join(str(r) for r, _ in failed_rows),
                   message='; '.join(dict.fromkeys(r for _, r in failed_rows))[:400])
        if isinstance(res, dict) and 'failed' in res and not res.get('pong'):
            log(f'ebook requests: {len(failed_rows)} marked failed on the Sheet '
                '(will not retry)')
        else:
            log(f'ebook requests: {len(failed_rows)} recorded failed locally, but the '
                'Sheet did not accept it -- redeploy tools/stand_apps_script.gs or '
                'they will be retried every run')
    if built_rows:
        call('ebook_requests_set_result',
             results='|'.join(f'{r}:{pid}:{url}' for r, pid, url in built_rows))
    log(f'ebook requests: built {n}')
    return n


def write_emag_letters_json(conn):
    has_flag = 'is_public' in {r[1] for r in conn.execute('PRAGMA table_info(letters)')}
    where = 'WHERE is_public=1' if has_flag else "WHERE source='sheet'"
    letters = conn.execute(
        f"SELECT id,guest_name,subject,status,created_at FROM letters {where} "
        "ORDER BY created_at DESC").fetchall()
    out = []
    for l in letters:
        msgs = conn.execute(
            "SELECT sender,content,created_at FROM letter_messages WHERE letter_id=? ORDER BY created_at", [l['id']]).fetchall()
        out.append({
            'id': l['id'], 'subject': l['subject'], 'guest_name': l['guest_name'],
            'status': l['status'], 'created_at': l['created_at'],
            'messages': [dict(m) for m in msgs],
        })
    os.makedirs(os.path.dirname(EMAG_LETTERS_JSON), exist_ok=True)
    with open(EMAG_LETTERS_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f'emag/data/letters.json: wrote {len(out)} letter(s)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--letters-only', action='store_true',
                     help='skip comments/likes/messages/subscribers/activity/accounts/annotations mirroring')
    ap.add_argument('--no-letters-json', action='store_true', help='skip refreshing emag/data/letters.json')
    args = ap.parse_args()

    conn = get_db()
    steps = [('letters', import_letters)]
    if not args.letters_only:
        steps += [('comments', import_comments), ('likes', import_likes),
                  ('messages', import_messages), ('subscribers', import_subscribers),
                  ('activity', import_activity), ('accounts', import_accounts),
                  ('annotations', import_sheet_annotations),
                  ('ebook requests', build_ebook_requests)]
    if not args.no_letters_json:
        steps.append(('letters.json', write_emag_letters_json))

    failed = []
    try:
        for name, fn in steps:
            try:
                fn(conn)
            except Exception as e:
                failed.append(name)
                log(f'{name}: FAILED -- {e}')
    finally:
        conn.close()
    if failed:
        log(f'completed with {len(failed)} failed step(s): {", ".join(failed)}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
