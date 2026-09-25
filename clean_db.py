#!/usr/bin/env python3
import os, sys, shutil, datetime

DB    = os.environ.setdefault('DB_PATH',           'voice_express.db')
UP    = os.environ.setdefault('UPLOADS_PATH',      'static/uploads')
PUBS  = os.environ.setdefault('PUBLICATIONS_PATH', 'static/publications')
MEDIA = os.environ.setdefault('MEDIA_PATH',        'static/media')
KEEP_MEDIA = '--keep-media' in sys.argv

def main():
    if '--yes' not in sys.argv:
        what = 'the DATABASE' if KEEP_MEDIA else 'the DATABASE *and* all media (uploads/publications/media)'
        if input(f'This will wipe {what}.\nType "yes" to continue: ').strip().lower() != 'yes':
            print('aborted.'); return

    if os.path.exists(DB):
        bdir = '_clean_backup'; os.makedirs(bdir, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(bdir, f'voice_express.{ts}.db')
        shutil.copy2(DB, dest); print('backed up ->', dest)

    for ext in ('', '-wal', '-shm'):
        try: os.remove(DB + ext)
        except FileNotFoundError: pass

    if not KEEP_MEDIA:
        for d in (UP, PUBS, MEDIA):
            if os.path.isdir(d):
                for name in os.listdir(d):
                    p = os.path.join(d, name)
                    try:
                        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                    except Exception as e:
                        print('  skip', p, e)
            os.makedirs(d, exist_ok=True)
        print('cleared media ->', UP, PUBS, MEDIA)

    open(DB, 'w').close()
    import app
    print('fresh database ->', DB)
    print('done. admin: tve / h3ll0w0rld@th3v0ic33xpr3ss  ->  start with: python app.py')

if __name__ == '__main__':
    main()
