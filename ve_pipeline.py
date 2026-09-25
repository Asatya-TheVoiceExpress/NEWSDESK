#!/usr/bin/env python3
import os, sys, json, time, sqlite3, argparse, subprocess
from datetime import datetime, timedelta

from ve.db import connect

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))

COLLECT_STEPS = [
    ('Collect reader input', 'site_data_get.py', [], False),
]
PUBLISH_STEPS = [
    ('Build artifacts',      've_maintenance.py', [],           False),
    ('Push decisions out',   'site_data_put.py',  [],           False),
    ('Prune reader ebooks',  've_prune.py',       ['--apply'],  False),
    ('Rebuild emag',         've-push.py',        [],           True),
    ('Rebuild newsstand',    'librarize.py',      [],           True),
    ('Email ready ebooks',   've_ebook_mail.py',  ['--apply'],  False),
]
DRY_STEPS = [
    ('Preview prune',        've_prune.py',       [],            False),
    ('Preview ebook mail',   've_ebook_mail.py',  [],            False),
    ('Preview Sheet writes', 'site_data_put.py',  ['--dry-run'], False),
]

LOCK_PATH = os.path.join(BASE, '.ve_pipeline.lock')


def acquire_lock():
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            with open(LOCK_PATH, encoding='utf-8') as fh:
                holder = fh.read().strip()
        except OSError:
            holder = ''
        return False, holder
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(f'pid {os.getpid()} since {datetime.now().isoformat()}')
    return True, ''


def release_lock():
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass


def _run(name, script, argv, on_log):
    path = os.path.join(BASE, script)
    if not os.path.exists(path):
        on_log(f'!! {script} not found -- skipping {name}')
        return False, -1
    on_log(f'$ python {script}' + (' ' + ' '.join(argv) if argv else ''))
    try:
        proc = subprocess.Popen(
            [sys.executable, '-u', script, *argv], cwd=BASE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding='utf-8', errors='replace')
    except Exception as e:
        on_log(f'!! could not start {script}: {e}')
        return False, -1
    for line in proc.stdout:
        on_log(line.rstrip())
    code = proc.wait()
    if code != 0:
        on_log(f'!! {script} exited {code}')
    return code == 0, code


def _chain(steps, on_log):
    started = time.time()
    out = {'ok': True, 'steps': [], 'started_at': datetime.now().isoformat()}
    for name, script, argv, hard in steps:
        t0 = time.time()
        on_log(f'--- {name} ---')
        ok, code = _run(name, script, argv, on_log)
        out['steps'].append({'name': name, 'script': script, 'ok': ok,
                             'exit_code': code, 'seconds': round(time.time() - t0, 1)})
        if not ok:
            out['ok'] = False
            if hard:
                on_log(f'** stopping: "{name}" failed and the rest depends on it')
                break
            on_log(f'** "{name}" failed -- continuing, the sites can still be '
                   'rebuilt from the database as it stands')
    out['seconds'] = round(time.time() - started, 1)
    on_log(f'== {"done" if out["ok"] else "finished with errors"} '
           f'in {out["seconds"]}s ==')
    return out


def collect(on_log=print):
    return _chain(COLLECT_STEPS, on_log)


def queue_counts():
    out = {'ebook_requests': {}, 'comments': {}, 'newsletter_subscribers': 0}
    db = connect(DATABASE)
    try:
        if _table_exists(db, 'ebook_requests'):
            out['ebook_requests'] = {r[0] or '': r[1] for r in db.execute(
                'SELECT status, COUNT(*) FROM ebook_requests GROUP BY status')}
        if _table_exists(db, 'comments'):
            out['comments'] = {r[0] or '': r[1] for r in db.execute(
                'SELECT status, COUNT(*) FROM comments GROUP BY status')}
        if _table_exists(db, 'newsletter_subscribers'):
            out['newsletter_subscribers'] = db.execute(
                'SELECT COUNT(*) FROM newsletter_subscribers').fetchone()[0]
    finally:
        db.close()
    return out


def publish_dry(on_log=print):
    tally = {'would_prune': 0, 'would_mail': 0, 'sheet_writes': 0}

    def counting(line):
        if 'would prune #' in line:
            tally['would_prune'] += 1
        elif 'would mail ' in line:
            tally['would_mail'] += 1
        elif 'DRY RUN ' in line:
            tally['sheet_writes'] += 1
        on_log(line)

    out = _chain(DRY_STEPS, counting)
    out['dry_run'] = True
    out['counts'] = {**queue_counts(), **tally}
    return out


def publish(on_log=print, dry_run=False):
    if dry_run:
        return publish_dry(on_log)
    return _chain(PUBLISH_STEPS, on_log)


def full(on_log=print, dry_run=False):
    if dry_run:
        return publish_dry(on_log)
    a = collect(on_log)
    b = publish(on_log)
    return {'ok': a['ok'] and b['ok'], 'steps': a['steps'] + b['steps'],
            'seconds': round(a['seconds'] + b['seconds'], 1)}



def _table_exists(db, name):
    return bool(db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                           "AND name=?", [name]).fetchone())


def analytics(days=30):
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    out = {'days': days, 'generated_at': datetime.utcnow().isoformat(),
           'limits': [
               'The emag logs no reads or downloads -- traffic covers the Newsstand only.',
               'Likes are a running total with no timestamps, so they cannot be plotted.',
               'Activity rows carry a title but no article id; content joins are by title.',
               'Hearts are never written to accounts; they appear as via=hearts activity.',
           ]}

    def q1(sql, args=()):
        r = db.execute(sql, args).fetchone()
        return (r[0] if r and r[0] is not None else 0)

    try:
        out['totals'] = {
            'articles':     q1("SELECT COUNT(*) FROM articles WHERE status='published'"),
            'comments':     q1("SELECT COUNT(*) FROM comments"),
            'letters':      q1("SELECT COUNT(*) FROM letters"),
            'subscribers':  q1("SELECT COUNT(*) FROM newsletter_subscribers")
                            if _table_exists(db, 'newsletter_subscribers') else 0,
            'messages':     q1("SELECT COUNT(*) FROM site_messages")
                            if _table_exists(db, 'site_messages') else 0,
            'readers':      q1("SELECT COUNT(*) FROM newsstand_accounts")
                            if _table_exists(db, 'newsstand_accounts') else 0,
            'annotations':  q1("SELECT COUNT(*) FROM sheet_annotations")
                            if _table_exists(db, 'sheet_annotations') else 0,
            'publications': q1("SELECT COUNT(*) FROM publications"),
            'likes_total':  q1("SELECT SUM(count) FROM article_likes"),
        }

        out['queues'] = {
            'pending_comments': q1("SELECT COUNT(*) FROM comments WHERE status='pending'"),
            'open_letters':     q1("SELECT COUNT(*) FROM letters WHERE status='open'"),
            'unanswered_letters': q1(
                "SELECT COUNT(*) FROM letters l WHERE l.status='open' AND NOT EXISTS "
                "(SELECT 1 FROM letter_messages m WHERE m.letter_id=l.id AND m.sender<>'guest')"),
        }
        if _table_exists(db, 'ebook_requests'):
            out['queues']['ebooks_built'] = q1(
                "SELECT COUNT(*) FROM ebook_requests WHERE status='built'")
            out['queues']['ebooks_failed'] = q1(
                "SELECT COUNT(*) FROM ebook_requests WHERE status='failed'")

        out['activity'] = {'by_kind': [], 'by_day': [], 'top_titles': [],
                           'revenue': [], 'readers': 0}
        if _table_exists(db, 'site_activity'):
            out['activity']['by_kind'] = [dict(r) for r in db.execute(
                "SELECT kind, COUNT(*) AS n FROM site_activity WHERE occurred_at >= ? "
                "GROUP BY kind ORDER BY n DESC", [since])]
            out['activity']['by_day'] = [dict(r) for r in db.execute(
                "SELECT substr(occurred_at,1,10) AS day, COUNT(*) AS n FROM site_activity "
                "WHERE occurred_at >= ? GROUP BY day ORDER BY day", [since])]
            out['activity']['top_titles'] = [dict(r) for r in db.execute(
                "SELECT COALESCE(NULLIF(title,''),'(untitled)') AS title, kind, COUNT(*) AS n "
                "FROM site_activity WHERE occurred_at >= ? AND kind IN ('read','download') "
                "GROUP BY title, kind ORDER BY n DESC LIMIT 12", [since])]
            out['activity']['revenue'] = [dict(r) for r in db.execute(
                "SELECT COALESCE(NULLIF(via,''),'(unknown)') AS via, currency, "
                "COUNT(*) AS taps, SUM(amount) AS total FROM site_activity "
                "WHERE kind='pay' AND occurred_at >= ? GROUP BY via, currency "
                "ORDER BY total DESC", [since])]
            out['activity']['readers'] = q1(
                "SELECT COUNT(DISTINCT username) FROM site_activity "
                "WHERE occurred_at >= ? AND username IS NOT NULL AND TRIM(username) <> ''",
                [since])

        out['top_commented'] = [dict(r) for r in db.execute(
            "SELECT a.id, a.title, COUNT(c.id) AS n FROM comments c "
            "JOIN articles a ON a.id = c.article_id "
            "WHERE c.status='approved' GROUP BY a.id ORDER BY n DESC LIMIT 10")]
        out['top_liked'] = [dict(r) for r in db.execute(
            "SELECT a.id, a.title, l.count AS n FROM article_likes l "
            "JOIN articles a ON a.id = l.article_id ORDER BY l.count DESC LIMIT 10")]
    finally:
        db.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action', choices=['collect', 'publish', 'all', 'analytics'])
    ap.add_argument('--days', type=int, default=30, help='analytics window')
    ap.add_argument('--dry-run', action='store_true',
                    help='publish/all: preview only, no writes, no mail, no deletes')
    args = ap.parse_args()

    if args.dry_run and args.action not in ('publish', 'all'):
        ap.error('--dry-run applies to publish and all')
    if args.action == 'analytics':
        print(json.dumps(analytics(args.days), indent=2, default=str))
        return 0
    if args.dry_run:
        res = publish_dry()
        print(json.dumps(res, indent=2, default=str))
        return 0 if res['ok'] else 1
    got, holder = acquire_lock()
    if not got:
        print(f'another pipeline run holds {LOCK_PATH} ({holder}); '
              'delete the file if that run is gone', file=sys.stderr)
        return 3
    try:
        res = {'collect': collect, 'publish': publish, 'all': full}[args.action]()
    finally:
        release_lock()
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
