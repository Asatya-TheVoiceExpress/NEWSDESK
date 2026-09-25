#!/usr/bin/env python3
import argparse
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))

MIRRORS = ['site_messages', 'newsletter_subscribers', 'site_activity',
           'newsstand_accounts', 'sheet_annotations']

BACK_POINTERS = [('comments', 'sheet_row'),
                 ('letters', 'sheet_row'),
                 ('ebook_requests', 'sheet_row')]


def log(msg):
    print(f'[ve_sheet_reset] {msg}')


def has_table(db, name):
    return bool(db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                           "AND name=?", [name]).fetchone())


def has_col(db, table, col):
    return col in {r[1] for r in db.execute(f'PRAGMA table_info({table})')}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true',
                    help='actually write the changes (default is a dry run)')
    ap.add_argument('--drop-mirrors', action='store_true',
                    help='also empty the Sheet-only mirror tables')
    args = ap.parse_args()
    dry = not args.apply

    if not os.path.exists(DATABASE):
        sys.exit(f'[ve_sheet_reset] {DATABASE} not found')
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    try:
        log(f'database: {DATABASE}')
        log('DRY RUN -- nothing will be written. Re-run with --apply to commit.'
            if dry else 'applying changes')

        total = 0
        for table, col in BACK_POINTERS:
            if not has_table(db, table) or not has_col(db, table, col):
                continue
            n = db.execute(f'SELECT COUNT(*) FROM {table} '
                           f'WHERE {col} IS NOT NULL').fetchone()[0]
            total += n
            log(f'  {table}.{col}: {n} back-pointer(s) to clear')
            if n and not dry:
                db.execute(f'UPDATE {table} SET {col}=NULL')

        if has_table(db, 'ebook_requests'):
            n = db.execute("SELECT COUNT(*) FROM ebook_requests "
                           "WHERE status='failed'").fetchone()[0]
            if n:
                log(f'  ebook_requests: {n} failed request(s) from the old Sheet '
                    '-- removing (they cannot be retried against a new one)')
                if not dry:
                    db.execute("DELETE FROM ebook_requests WHERE status='failed'")

        if args.drop_mirrors:
            for t in MIRRORS:
                if not has_table(db, t):
                    continue
                n = db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                log(f'  {t}: {n} mirrored row(s) to delete')
                if n and not dry:
                    db.execute(f'DELETE FROM {t}')
        else:
            log('  (mirror tables kept -- pass --drop-mirrors to empty them)')

        if not dry:
            db.commit()
            log('done. Next: update voiceexpressstand/config.json with the new '
                '/exec URL, then run Collect and Publish.')
        else:
            log(f'{total} back-pointer(s) would be cleared.')
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
