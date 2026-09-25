#!/usr/bin/env python3
import os, sys, json, socket, argparse, getpass, urllib.request, http.cookiejar

LOCAL = {
    'uploads':      os.environ.get('UPLOADS_PATH', 'static/uploads'),
    'publications': os.environ.get('PUBLICATIONS_PATH', 'static/publications'),
    'media':        os.environ.get('MEDIA_PATH', 'static/media'),
}
DB_LOCAL = os.environ.get('DB_PATH', 'voice_express.db')

GUARD_PORTS = (5000, 8787, 8788, 8789, 8790, 8797)


def refuse_if_busy(db_path, force, tag):
    if force:
        return
    busy = []
    for port in GUARD_PORTS:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                busy.append(f'port {port} is answering')
    if os.path.exists(db_path + '-wal'):
        busy.append(f'{db_path}-wal exists')
    if busy:
        print(f'[{tag}] refusing to replace the database: ' + '; '.join(busy)
              + '. Stop the apps first, or pass --force.', file=sys.stderr)
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description='Pull live DB + media to a local dev copy.')
    ap.add_argument('cmd', choices=['pull'])
    ap.add_argument('--remote', default=os.environ.get('VE_REMOTE'))
    ap.add_argument('--user', default=os.environ.get('VE_ADMIN_USER', 'tve'))
    ap.add_argument('--full', action='store_true', help='re-download every file')
    ap.add_argument('--force', action='store_true', help='skip the servers-running check')
    a = ap.parse_args()
    refuse_if_busy(DB_LOCAL, a.force, 've_sync')

    remote = (a.remote or '').rstrip('/')
    if not remote:
        sys.exit('error: set --remote or VE_REMOTE (e.g. https://your-app.up.railway.app)')
    pw = os.environ.get('VE_ADMIN_PASS') or getpass.getpass(f'{a.user} password: ')

    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def get(path, data=None):
        req = urllib.request.Request(
            remote + path,
            data=(json.dumps(data).encode() if data is not None else None),
            headers={'Content-Type': 'application/json'} if data is not None else {})
        return op.open(req, timeout=600)

    get('/api/auth/login', {'username': a.user, 'password': pw}); print('logged in ->', remote)
    man = json.load(get('/api/admin/manifest'))

    os.makedirs(os.path.dirname(os.path.abspath(DB_LOCAL)), exist_ok=True)
    with get('/api/admin/backup/db') as r, open(DB_LOCAL, 'wb') as f:
        f.write(r.read())
    print('db   ->', DB_LOCAL, f"({(man.get('db') or {}).get('size', 0)//1024} KB)")

    got = skip = 0
    for fi in man.get('files', []):
        base = LOCAL.get(fi['store'])
        if not base:
            continue
        dest = os.path.join(base, fi['path'].replace('/', os.sep))
        if (not a.full) and os.path.exists(dest) and os.path.getsize(dest) == fi['size']:
            skip += 1; continue
        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
        with get(f"/api/admin/file/{fi['store']}/{fi['path']}") as r, open(dest, 'wb') as f:
            f.write(r.read())
        got += 1
    print(f'media -> {got} fetched, {skip} already current')
    print('done. run a local dev server with:  python app.py')

if __name__ == '__main__':
    main()
