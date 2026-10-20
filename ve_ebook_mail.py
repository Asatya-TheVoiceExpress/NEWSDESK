#!/usr/bin/env python3
import os, sys, json, sqlite3, argparse
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DB_PATH', os.path.join(BASE, 'voice_express.db'))
STAND_DIR = os.path.join(BASE, 'voiceexpressstand')
STAND_CNAME = os.path.join(STAND_DIR, 'CNAME')
STAND_CATALOG = os.path.join(STAND_DIR, 'catalog.json')

from site_data_get import call, migrate
import html as _html
import ve.mailer as mailer


def log(msg):
    print(f'[ebook-mail] {msg}')


def stand_base_url():
    try:
        with open(STAND_CNAME, encoding='utf-8') as f:
            host = f.read().strip().strip('/')
        if host:
            return f'https://{host}'
    except OSError:
        pass
    return 'https://newsstand.thevoiceexpress.in'


def catalog_urls():
    try:
        with open(STAND_CATALOG, encoding='utf-8') as f:
            cat = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log(f'could not read the Stand catalog ({e}) -- nothing will be mailed')
        return {}
    out = {}
    for item in cat.get('catalog') or []:
        pid, url = item.get('publication_id'), item.get('url')
        if pid and url:
            out[int(pid)] = url
    return out


def ebook_message(name, title, url):
    e = _html.escape
    text = (f'Hello {name},\n\n'
            f'The ebook you asked us to put together — "{title}" — is ready, '
            f'and it is on the Newsstand now:\n\n{url}\n\n'
            'It is an ePub: open it in Apple Books, Calibre, KOReader, or any e-reader.\n\n'
            'Thank you for reading.\n\nThe Voice Express\nhttps://emag.thevoiceexpress.in\n')
    html = (f'<p>Hello {e(name)},</p>'
            f'<p>The ebook you asked us to put together — <b>{e(title)}</b> — is ready, '
            'and it is on the Newsstand now.</p>'
            f'<p><a href="{e(url)}">Download your ebook</a></p>'
            '<p>It is an ePub: open it in Apple Books, Calibre, KOReader, or any e-reader.</p>'
            '<p>Thank you for reading.<br><b>The Voice Express</b><br>'
            '<a href="https://emag.thevoiceexpress.in">emag.thevoiceexpress.in</a></p>')
    return text, html


def pending(conn):
    try:
        return conn.execute(
            "SELECT r.id, r.sheet_row, r.email, r.requester_name, r.title, "
            "       r.publication_id, p.filename "
            "FROM ebook_requests r "
            "JOIN publications p ON p.id = r.publication_id "
            "WHERE r.status='built' AND r.emailed_at IS NULL "
            "  AND r.email IS NOT NULL AND r.email <> '' "
            "ORDER BY r.id").fetchall()
    except sqlite3.Error as e:
        log(f'no requests to read ({e})')
        return []


def send_all(conn, apply=False):
    rows = pending(conn)
    if not rows:
        log('nothing to mail')
        return 0
    urls = catalog_urls()
    base = stand_base_url()
    sent = 0
    for r in rows:
        rel = urls.get(r['publication_id'])
        if not rel:
            log(f'request {r["id"]} ("{(r["title"] or "")[:40]}"): '
                'not on the Stand yet -- will mail after the next publish')
            continue
        link = f'{base}/{rel.lstrip("/")}'
        if not apply:
            log(f'would mail {r["email"]} -> {link}')
            sent += 1
            continue
        name = (r['requester_name'] or 'reader').strip()[:100] or 'reader'
        title = (r['title'] or 'Your Voice Express ebook').strip()[:200]
        try:
            if mailer.configured():
                text, html = ebook_message(name, title, link)
                mailer.send(r['email'], f'Your ebook is ready — {title}', text, html)
                res = {'ok': True, 'sent': 1}
            else:
                res = call('ebook_email', to=r['email'], name=name, title=title, url=link)
        except Exception as e:
            log(f'request {r["id"]}: send failed ({e}) -- will retry next publish')
            continue
        if not (isinstance(res, dict) and res.get('ok') and res.get('sent')):
            log(f'request {r["id"]}: the Sheet did not send it ({res}) -- '
                'redeploy tools/stand_apps_script.gs')
            continue
        conn.execute('UPDATE ebook_requests SET emailed_at=? WHERE id=?',
                     [datetime.utcnow().isoformat(), r['id']])
        conn.commit()
        sent += 1
        log(f'mailed {r["email"]} about "{(r["title"] or "")[:50]}"')
    log(f'{"sent" if apply else "would send"} {sent}'
        + ('' if apply else '  (dry run -- pass --apply)'))
    return sent


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='actually send (default: dry run)')
    args = ap.parse_args(argv)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    try:
        try:
            migrate(conn)
        except Exception as e:
            log(f'schema check failed ({e}) -- continuing')
        send_all(conn, apply=args.apply)
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
