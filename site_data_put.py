#!/usr/bin/env python3
import os, sys, time, json, sqlite3, argparse, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))
STAND_CONFIG = os.path.join(BASE, 'voiceexpressstand', 'config.json')
SHEET_SECRET_FILE = os.path.join(BASE, '.ve_sheet_secret')

CHUNK = 60


def log(msg):
    print(f'[site_data_put] {msg}')


def api_url():
    env = os.environ.get('VE_API_ENDPOINT')
    if env:
        return env
    if not os.path.exists(STAND_CONFIG):
        sys.exit(f'[site_data_put] {STAND_CONFIG} not found -- cannot find the Apps Script URL')
    with open(STAND_CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    api = cfg.get('api')
    if not api:
        sys.exit(f'[site_data_put] {STAND_CONFIG} has no "api" field -- deploy '
                 'tools/stand_apps_script.gs and paste its /exec URL in')
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
    sys.exit('[site_data_put] the Sheet secret is missing -- put it in '
             f'{SHEET_SECRET_FILE} (or set VE_SHEET_SECRET); refusing to call the Sheet without it')


def call(action, dry_run=False, _tries=4, **params):
    params = {'action': action, **params}
    params['secret'] = sheet_secret()
    if dry_run:
        shown = {k: v for k, v in params.items() if k != 'secret'}
        log(f'DRY RUN {action}: {shown}')
        return {'ok': True, 'dry_run': True}
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
    return {'ok': False, 'error': f'failed after {_tries} attempts -- {last}'}


def ok_with(res, field):
    if not isinstance(res, dict) or not res.get('ok'):
        return False
    if res.get('pong'):
        return False
    return field in res


def stale_deployment(res):
    return isinstance(res, dict) and res.get('pong') is True


def chunked(seq, size=CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _has(conn, table, col):
    return col in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}


def push_comment_status(conn, dry_run=False):
    if not _has(conn, 'comments', 'sheet_row'):
        log('comments: no sheet_row column -- run site_data_get.py once first')
        return 0
    live = call('comments_export')
    if not isinstance(live, list):
        log(f'comments_export failed: {live}')
        return 0
    known = {r['sheet_row']: r['status']
             for r in conn.execute(
                 'SELECT sheet_row,status FROM comments WHERE sheet_row IS NOT NULL')}

    high_water = max(known) if known else 0
    if not known:
        log('comments: nothing imported yet -- not inferring any deletions')
        return 0

    pairs = []
    skipped_new = 0
    for row in live:
        r = row.get('row')
        if not r:
            continue
        if r not in known:
            if r > high_water:
                skipped_new += 1
                continue
            status = 'deleted'
        else:
            status = known[r]
        if status == 'approved':
            continue
        pairs.append(f'{r}:{status}')
    if skipped_new:
        log(f'comments: {skipped_new} row(s) on the Sheet are newer than the last '
            'collect -- run site_data_get.py first if you meant to moderate those')
    if not pairs:
        log('comments: nothing to push')
        return 0
    n = 0
    for batch in chunked(pairs):
        res = call('comments_set_status', dry_run=dry_run, pairs=','.join(batch))
        if dry_run:
            n += len(batch); continue
        if not ok_with(res, 'updated'):
            log('comments_set_status: ' + ('the deployed Apps Script does not have this '
                'action -- redeploy tools/stand_apps_script.gs' if stale_deployment(res)
                else f'failed: {res}'))
            break
        n += res.get('updated', len(batch))
    log(f'comments: pushed {n} status change(s)')
    return n


def push_local_comments(conn, dry_run=False):
    if not _has(conn, 'comments', 'sheet_row'):
        log('local comments: no sheet_row column -- run site_data_get.py once first')
        return 0
    rows = conn.execute(
        "SELECT id, article_id, target_kind, target_ref, selected_text, display_name, "
        "content, status, created_at, username "
        "FROM comments WHERE sheet_row IS NULL AND status='approved' "
        "ORDER BY id").fetchall()
    if not rows:
        log('local comments: nothing to push')
        return 0

    roster = {}
    live = call('comments_export') if not dry_run else []
    if isinstance(live, list):
        for row in live:
            key = (str(row.get('target_ref') or row.get('article_id') or ''),
                   row.get('display_name') or '', row.get('content') or '')
            if row.get('row'):
                roster[key] = row['row']
    elif not dry_run:
        log(f'local comments: cannot read the Sheet roster ({live}) -- skipping, '
            'pushing blind would risk duplicates')
        return 0

    adopted = 0
    fresh = []
    for r in rows:
        key = (str(r['target_ref'] or r['article_id'] or ''),
               r['display_name'] or '', r['content'] or '')
        if key in roster:
            conn.execute('UPDATE comments SET sheet_row=? WHERE id=?', [roster[key], r['id']])
            adopted += 1
        else:
            fresh.append(r)
    if adopted:
        conn.commit()
        log(f'local comments: adopted {adopted} existing Sheet row(s) -- already public')
    if not fresh:
        log('local comments: nothing new to push')
        return 0

    n = 0
    for r in fresh:
        res = call('comments_push', dry_run=dry_run,
                   article_id=r['article_id'] or '',
                   target_kind=r['target_kind'] or 'article',
                   target_ref=r['target_ref'] or (r['article_id'] or ''),
                   selected_text=r['selected_text'] or '',
                   display_name=r['display_name'] or '',
                   content=r['content'] or '', status=r['status'] or 'approved',
                   created_at=r['created_at'] or '', username=r['username'] or '')
        if dry_run:
            n += 1
            continue
        if not ok_with(res, 'row'):
            log('comments_push: ' + ('the deployed Apps Script does not have this action '
                '-- redeploy tools/stand_apps_script.gs' if stale_deployment(res)
                else f'failed: {res}'))
            break
        conn.execute('UPDATE comments SET sheet_row=? WHERE id=?', [res['row'], r['id']])
        conn.commit()
        n += 1
    log(f'local comments: pushed {n} to the Sheet')
    return n


def push_letter_replies(conn, dry_run=False):
    rows = [r['sheet_row'] for r in conn.execute(
        "SELECT DISTINCT l.sheet_row FROM letters l "
        "JOIN letter_messages m ON m.letter_id = l.id "
        "WHERE l.source='sheet' AND l.sheet_row IS NOT NULL AND m.sender <> 'guest'")]
    if not rows:
        log('letters: no replied letters to flag')
        return 0
    n = 0
    for batch in chunked(rows):
        res = call('letters_set_replied', dry_run=dry_run,
                   rows=','.join(str(r) for r in batch))
        if dry_run:
            n += len(batch); continue
        if not ok_with(res, 'marked'):
            log('letters_set_replied: ' + ('the deployed Apps Script does not have this '
                'action -- redeploy tools/stand_apps_script.gs' if stale_deployment(res)
                else f'failed: {res}'))
            break
        n += res.get('marked', len(batch))
    log(f'letters: flagged {n} as replied')
    return n


def push_ebook_results(conn, dry_run=False):
    if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name='ebook_requests'").fetchone():
        log('ebooks: no ebook_requests table -- run site_data_get.py once first')
        return 0
    rows = conn.execute(
        "SELECT sheet_row,publication_id,download_url FROM ebook_requests "
        "WHERE sheet_row IS NOT NULL AND publication_id IS NOT NULL").fetchall()
    if not rows:
        log('ebooks: nothing to push')
        return 0
    recs = [f"{r['sheet_row']}:{r['publication_id']}:{(r['download_url'] or '').replace('|', '%7C')}"
            for r in rows]
    n = 0
    for batch in chunked(recs, 25):
        res = call('ebook_requests_set_result', dry_run=dry_run, results='|'.join(batch))
        if dry_run:
            n += len(batch); continue
        if not ok_with(res, 'updated'):
            log('ebook_requests_set_result: ' + ('the deployed Apps Script does not have '
                'this action -- redeploy tools/stand_apps_script.gs' if stale_deployment(res)
                else f'failed: {res}'))
            break
        n += res.get('updated', len(batch))
    log(f'ebooks: pushed {n} result link(s)')
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--comments-only', action='store_true')
    ap.add_argument('--letters-only', action='store_true')
    ap.add_argument('--ebooks-only', action='store_true')
    ap.add_argument('--dry-run', action='store_true',
                    help='print what would be sent without writing to the Sheet')
    args = ap.parse_args()

    only = args.comments_only or args.letters_only or args.ebooks_only
    conn = get_db()
    try:
        if args.comments_only or not only:
            push_local_comments(conn, args.dry_run)
            push_comment_status(conn, args.dry_run)
        if args.letters_only or not only:
            push_letter_replies(conn, args.dry_run)
        if args.ebooks_only or not only:
            push_ebook_results(conn, args.dry_run)
    finally:
        conn.close()
    log('done -- rerun ve-push.py so the emag rebuild picks this up')


if __name__ == '__main__':
    main()
