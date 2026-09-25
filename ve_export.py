#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, sqlite3, zipfile
from datetime import date

IMG_SRC = re.compile(r'<img\b[^>]*?\bsrc=["\']([^"\']+)["\']', re.I)
INTERNAL_TABLES = {"sqlite_sequence"}


def referenced_media(db: sqlite3.Connection) -> set[str]:
    out: set[str] = set()

    def grab(text):
        if not text:
            return
        for src in IMG_SRC.findall(text):
            if not src.startswith("http"):
                out.add(os.path.basename(src.split("?")[0]))

    for r in db.execute("SELECT content, excerpt, featured_image FROM articles"):
        grab(r["content"]); grab(r["excerpt"])
        fi = r["featured_image"]
        if fi and not fi.startswith("http"):
            out.add(os.path.basename(fi.split("?")[0]))
    for r in db.execute("SELECT content FROM translations"):
        grab(r["content"])
    for r in db.execute("SELECT avatar_url FROM authors"):
        av = r["avatar_url"]
        if av and not av.startswith("http"):
            out.add(os.path.basename(av.split("?")[0]))
    for r in db.execute("SELECT filename FROM images"):
        if r["filename"]:
            out.add(os.path.basename(r["filename"]))

    def _addlocal(v):
        if v and not v.startswith("http"):
            out.add(os.path.basename(v.split("?")[0]))

    for tbl, col in (("columns", "cover_image"), ("column_entries", "cover_image"),
                     ("column_panels", "image")):
        try:
            for r in db.execute(f"SELECT {col} AS v FROM {tbl}"):
                _addlocal(r["v"])
        except Exception:
            pass
    try:
        for r in db.execute("SELECT body FROM column_entries"):
            grab(r["body"])
    except Exception:
        pass
    out.discard("")
    return out


def build_manifest(db: sqlite3.Connection) -> dict:
    tables = sorted(
        r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        if r["name"] not in INTERNAL_TABLES)
    schema, data, counts = {}, {}, {}
    for t in tables:
        schema[t] = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", [t]).fetchone()["sql"]
        cols = [c["name"] for c in db.execute(f"PRAGMA table_info({t})")]
        order = "rowid" if any(c["pk"] for c in db.execute(f"PRAGMA table_info({t})")) else cols[0]
        try:
            rows = db.execute(f"SELECT * FROM {t} ORDER BY {order}").fetchall()
        except sqlite3.OperationalError:
            rows = db.execute(f"SELECT * FROM {t}").fetchall()
        data[t] = [{c: r[c] for c in cols} for r in rows]
        counts[t] = len(data[t])
    return {
        "meta": {"generator": "ve_export.py", "format": 1,
                 "created": date.today().isoformat(), "counts": counts},
        "schema": schema,
        "tables": data,
    }


def export(db_path: str, uploads_dir: str, out_path: str, all_media: bool = False) -> dict:
    db = sqlite3.connect(db_path); db.row_factory = sqlite3.Row
    manifest = build_manifest(db)
    if all_media:
        media = {f for f in os.listdir(uploads_dir)
                 if os.path.isfile(os.path.join(uploads_dir, f))}
    else:
        media = referenced_media(db)
    db.close()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for fn in sorted(media):
            p = os.path.join(uploads_dir, fn)
            if os.path.isfile(p):
                z.write(p, f"media/{fn}")
    return {"tables": len(manifest["tables"]),
            "rows": sum(manifest["meta"]["counts"].values()),
            "media": len(media)}


def main():
    ap = argparse.ArgumentParser(description="Export Voice Express content + media to a portable zip.")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "voice_express.db"))
    ap.add_argument("--uploads", default=os.environ.get("UPLOADS_PATH", "static/uploads"))
    ap.add_argument("-o", "--out", default=f"ve-export-{date.today().isoformat()}.zip")
    ap.add_argument("--all-media", action="store_true",
                    help="bundle every file in uploads, not only referenced ones")
    a = ap.parse_args()
    s = export(a.db, a.uploads, a.out, a.all_media)
    print(f"-> {a.out}")
    print(f"   tables {s['tables']} | rows {s['rows']} | media {s['media']}")


if __name__ == "__main__":
    main()
