#!/usr/bin/env python3
import os, sys, json, argparse, sqlite3, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH') or os.path.join(BASE, 'voice_express.db')

DEFAULT_DAYS = 30

try:
    import ve_library
except Exception:
    ve_library = None


def log(msg):
    print(f'[prune] {msg}')


def _static_root():
    return os.environ.get('DTP_STATIC_ROOT') or os.path.join(BASE, 'static')


def _locate(filename):
    if not filename:
        return None
    if ve_library and hasattr(ve_library, 'locate'):
        try:
            found = ve_library.locate(filename)
            if found:
                return found
        except Exception:
            pass
    root = _static_root()
    for rel in ('publications', 'media'):
        fp = os.path.join(root, rel, filename)
        if os.path.exists(fp):
            return fp
    return None


def _is_reader_ebook(row, request_pub_ids):
    if row['id'] in request_pub_ids:
        return True
    try:
        meta = json.loads(row['metadata'] or '{}') or {}
    except (json.JSONDecodeError, TypeError):
        return False
    return bool(meta.get('reader_generated'))


def _age_days(created_at, now):
    if not created_at:
        return 0
    stamp = str(created_at).strip().replace('T', ' ')[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return (now - datetime.datetime.strptime(stamp, fmt)).days
        except ValueError:
            continue
    return 0


def prune_reader_ebooks(conn, days=DEFAULT_DAYS, apply=False):
    if ve_library:
        try:
            ve_library.ensure_publication_columns(conn)
        except Exception as e:
            log(f'could not ensure publications columns: {e}')

    request_pub_ids = set()
    try:
        request_pub_ids = {r[0] for r in conn.execute(
            'SELECT publication_id FROM ebook_requests WHERE publication_id IS NOT NULL')}
    except sqlite3.Error:
        pass

    now = datetime.datetime.utcnow()
    pruned, kept = 0, 0
    for row in conn.execute(
            "SELECT id, title, filename, metadata, created_at, "
            "COALESCE(is_featured,0) AS is_featured "
            "FROM publications WHERE pub_type='epub'").fetchall():
        if not _is_reader_ebook(row, request_pub_ids):
            continue
        if row['is_featured']:
            kept += 1
            continue
        age = _age_days(row['created_at'], now)
        if age < days:
            continue
        log(f'{"pruning" if apply else "would prune"} #{row["id"]} '
            f'"{(row["title"] or "")[:60]}" ({age}d old)')
        if not apply:
            pruned += 1
            continue
        fp = _locate(row['filename'])
        if fp:
            try:
                os.remove(fp)
            except OSError as e:
                log(f'  could not delete {row["filename"]}: {e} -- row kept, will retry')
                continue
        if row['filename'] and '.' in row['filename']:
            side = _locate(f'{row["filename"].rsplit(".", 1)[0]}.dtp.json')
            if side:
                try:
                    os.remove(side)
                except OSError:
                    pass
        conn.execute('DELETE FROM publications WHERE id=?', [row['id']])
        try:
            conn.execute("UPDATE ebook_requests SET publication_id=NULL, download_url=NULL, "
                         "status='pruned' WHERE publication_id=?", [row['id']])
        except sqlite3.Error:
            pass
        pruned += 1
    if apply:
        conn.commit()

    log(f'{"pruned" if apply else "would prune"} {pruned} reader ebook(s); '
        f'{kept} featured kept'
        + ('' if apply else '  (dry run -- pass --apply)'))
    return pruned, kept


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--days', type=int, default=DEFAULT_DAYS,
                    help=f'age in days before a reader ebook is pruned (default {DEFAULT_DAYS})')
    ap.add_argument('--apply', action='store_true',
                    help='actually delete (default: dry run)')
    args = ap.parse_args(argv)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        prune_reader_ebooks(conn, days=args.days, apply=args.apply)
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
