#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, socket, sqlite3, sys, zipfile

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


def _load(zip_path: str) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        return json.loads(z.read("manifest.json").decode("utf-8"))


def plan(zip_path: str, db_path: str, uploads_dir: str) -> dict:
    man = _load(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        media = [n[len("media/"):] for n in z.namelist()
                 if n.startswith("media/") and not n.endswith("/")]
    new_media = sum(1 for m in media if not os.path.exists(os.path.join(uploads_dir, m)))
    return {"tables": len(man["tables"]),
            "rows": sum(len(v) for v in man["tables"].values()),
            "new_media": new_media,
            "existing_media": len(media) - new_media}


def restore(zip_path: str, db_path: str, uploads_dir: str, force_media: bool = False) -> dict:
    man = _load(zip_path)
    os.makedirs(uploads_dir, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys = OFF")
    n_rows = 0
    for table, create_sql in man["schema"].items():
        idempotent = create_sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
        db.execute(idempotent)
        rows = man["tables"].get(table, [])
        for row in rows:
            cols = list(row.keys())
            ph = ",".join("?" * len(cols))
            db.execute(f'INSERT OR REPLACE INTO {table} ({",".join(cols)}) VALUES ({ph})',
                       [row[c] for c in cols])
            n_rows += 1
    db.commit()
    db.execute("PRAGMA foreign_keys = ON")
    db.close()

    n_media = 0
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.startswith("media/") or name.endswith("/"):
                continue
            dest = os.path.join(uploads_dir, name[len("media/"):])
            if force_media or not os.path.exists(dest):
                with z.open(name) as src, open(dest, "wb") as out:
                    out.write(src.read())
                n_media += 1
    return {"tables": len(man["tables"]), "rows": n_rows, "media": n_media}


def main():
    ap = argparse.ArgumentParser(description="Import a Voice Express export zip into a DB + uploads dir.")
    ap.add_argument("zip", help="ve-export-*.zip to restore")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "voice_express.db"))
    ap.add_argument("--uploads", default=os.environ.get("UPLOADS_PATH", "static/uploads"))
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    ap.add_argument("--force", action="store_true", help="skip the servers-running check")
    ap.add_argument("--force-media", action="store_true", help="overwrite media files that already exist")
    a = ap.parse_args()
    if a.dry_run:
        p = plan(a.zip, a.db, a.uploads)
        print(f"DRY-RUN {a.zip} -> {a.db}")
        print(f"   tables {p['tables']} | rows {p['rows']} | "
              f"media new {p['new_media']} / existing {p['existing_media']}")
        return
    refuse_if_busy(a.db, a.force, "ve_import")
    s = restore(a.zip, a.db, a.uploads, a.force_media)
    print(f"imported {a.zip} -> {a.db}")
    print(f"   tables {s['tables']} | rows {s['rows']} | media copied {s['media']}")


if __name__ == "__main__":
    main()
