#!/usr/bin/env python3
import os, re, sys, json, sqlite3, datetime, shutil

import pub_icons
import ve_library
import ve.db as _ve_db
import ve.paths as _ve_paths
import ve.tags as _ve_tags

BASE     = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = _ve_paths.db_path()
OUT_DIR  = os.path.join(BASE, "voiceexpressstand")
CAT_PATH = os.path.join(OUT_DIR, "catalog.json")
CFG_PATH = os.path.join(OUT_DIR, "config.json")
NOJEKYLL_PATH = os.path.join(OUT_DIR, ".nojekyll")
SW_PATH  = os.path.join(OUT_DIR, "sw.js")
WEB_UP   = "static"
_COPY_QUEUE = []

DEFAULT_CONFIG = {
    "brand": "The Voice Express",
    "tagline": "Truth Takes Time",
    "logo": "logo.png",
    "currency": "INR",
    "api": os.environ.get("VE_API_ENDPOINT", os.environ.get("VE_LOG_ENDPOINT", "")),
    "pay": {
        "hearts": True,
        "message": True,
        "kofi":   [],
        "paypal": "",
        "razorpay": ""
    }
}

REFRESH  = "--refresh-covers" in sys.argv[1:]

SECTIONS = [
    ("gazettes",     "Gazettes",                 ("gazette",)),
    ("booklets",     "Booklets & Compilations",  ("booklet", "compilation")),
    ("broadsheets",  "Broadsheets",              ("broadsheet", "newsletter")),
    ("magazines",    "Magazines",                ("magazine_pdf", "magazine_html", "epub", "pdf")),
]
_SECTION_OF = {pt: key for key, _, pts in SECTIONS for pt in pts}

MIME = {"pdf": "application/pdf", "epub": "application/epub+zip",
        "html": "text/html"}


def log(*a): print("[librarize]", *a)


def _connect():
    return _ve_db.connect(DB_PATH)


def _clean_title(fn):
    stem = os.path.splitext(fn)[0]
    stem = re.sub(r"_\d{6,8}(_[0-9a-f]{4,8})?$", "", stem)
    return stem.replace("_", " ").strip() or stem


def _web_cover(path):
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    rel = path[len("/static/"):] if path.startswith("/static/") else \
          path[len("static/"):] if path.startswith("static/") else None
    if rel is None:
        log("WARNING: unrecognised cover path, not copied ->", path)
        return path
    _COPY_QUEUE.append((os.path.join(_ve_paths.static_root(), rel), os.path.join(WEB_UP, rel)))
    return f"{WEB_UP}/{rel}"


def _gazette_extras(db, aid):
    row = db.execute(
        "SELECT a.subtitle, a.excerpt, a.seo_description, a.reading_time, "
        "       c.name AS category, s.name AS section "
        "FROM articles a "
        "LEFT JOIN categories c ON c.id = a.category_id "
        "LEFT JOIN sections   s ON s.id = a.section_id "
        "WHERE a.id = ?", [aid]).fetchone()
    if not row:
        return {}
    authors = ve_library.article_authors_list(db, aid)
    tags = [r["name"] for r in db.execute(
        "SELECT t.name FROM article_tags at JOIN tags t ON t.id = at.tag_id "
        "WHERE at.article_id = ? ORDER BY t.name", [aid]).fetchall()]
    out = {
        "byline": ve_library.compose_byline(authors),
        "authors": [{"name": a.get("name"), "role": a.get("role") or "author"}
                    for a in authors if a.get("name")],
        "description": ((row["excerpt"] or "") or (row["subtitle"] or "")
                        or (row["seo_description"] or "")).strip(),
        "reading_time": int(row["reading_time"] or 0),
        "category": row["category"],
        "section_name": row["section"],
        "tags": tags,
    }
    return {k: v for k, v in out.items() if v}


def _column_title(db, cid, _cache={}):
    if cid not in _cache:
        r = db.execute("SELECT title FROM columns WHERE id=?", [cid]).fetchone()
        _cache[cid] = (r["title"] if r else None) or f"Column #{cid}"
    return _cache[cid]


_PERIOD_LABEL = {"week": "Weekly", "month": "Monthly", "year": "Yearly", "all": "All-time"}
_TITLE_DATES = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _booklet_ref_from_title(db, title):
    t = (title or "").strip()
    if not t:
        return None
    row = None
    for r in db.execute("SELECT id, title FROM columns").fetchall():
        ct = (r["title"] or "").strip()
        if ct and t.lower().startswith(ct.lower()):
            row = r
            break
    if not row:
        return None
    dates = _TITLE_DATES.findall(t)
    if len(dates) >= 2:
        return f'{row["id"]}:week:{dates[0]} - {dates[1]}'
    low = t.lower()
    for period in ("month", "year"):
        if period in low:
            return f'{row["id"]}:{period}:{period.title()}'
    return f'{row["id"]}:all:All'


def _series_of(db, e, meta):
    if e["type"] in ("broadsheet", "newsletter"):
        return {"key": "tve-monthly", "label": "The Voice Express",
                "kind": "issues", "role": "issue", "issue": (e.get("date") or "")[:7]}
    if e["type"] in ("booklet", "compilation"):
        cid = meta.get("column_id")
        period = meta.get("period")
        if cid is None or period is None:
            info = ve_library.booklet_entries(db, meta.get("source_ref") or "") or {}
            cid = info.get("column_id", cid)
            period = info.get("period", period)
        if cid is None:
            return None
        return {"key": f"column-{cid}", "label": _column_title(db, cid),
                "kind": "compilations", "role": "compilation",
                "period": period, "period_label": _PERIOD_LABEL.get(period, period),
                "range": meta.get("range")}
    return None


def _entry_for_row(db, row):
    fn = row["filename"]
    path = ve_library.locate(fn)
    if not path:
        return None
    webbase = ve_library.web_base_for(fn)
    ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
    try:
        meta = json.loads(row["metadata"] or "{}") or {}
    except (json.JSONDecodeError, TypeError):
        meta = {}

    mtime = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    created = (row["created_at"] or "") if "created_at" in row.keys() else ""
    derived = ""
    extras, contents = {}, []
    kind, sref = meta.get("kind"), str(meta.get("source_ref") or "")
    if kind == "gazette" and sref.isdigit():
        arow = db.execute(
            "SELECT published_at FROM articles WHERE id=?", [int(sref)]).fetchone()
        if arow and arow["published_at"]:
            derived = str(arow["published_at"])
        extras = _gazette_extras(db, int(sref))
    elif kind == "broadsheet" and re.fullmatch(r"\d{4}-\d{2}", sref):
        derived = f"{sref}-01"
    elif (kind in ("booklet", "compilation")
          or (row["pub_type"] or "") in ("booklet", "compilation")):
        stored = meta.get("entry_ids") or None
        if not stored and not sref:
            sref = _booklet_ref_from_title(db, row["title"]) or ""
        contents = ve_library.booklet_contents(db, sref, stored)
        if sref and not meta.get("source_ref"):
            meta["source_ref"] = sref
        rng = meta.get("range")
        if not rng and contents:
            rng = [contents[0]["date"], contents[-1]["date"]]
        if rng and rng[1]:
            derived = str(rng[1])
            meta.setdefault("range", rng)
    entry_date = meta.get("date") or derived or created or mtime
    if contents and derived:
        entry_date = derived
    e = {"file": fn, "url": f"{webbase}/{fn}", "ext": ext,
         "size": os.path.getsize(path),
         "date": str(entry_date)[:10],
         "tags": meta.get("tags") or [],
         "subtitle": meta.get("subtitle"),
         "type": row["pub_type"] or "booklet",
         "title": row["title"] or _clean_title(fn),
         "cover": row["cover_image"]}
    _COPY_QUEUE.append((path, os.path.join(webbase, fn)))

    try:
        rv = ve_library.reading_view_for(fn)
    except Exception:
        rv = None
    if rv:
        r_fn, r_ext, r_path = rv
        e["read_file"] = r_fn
        e["read_url"] = f"{webbase}/{r_fn}"
        e["read_ext"] = r_ext
        _COPY_QUEUE.append((r_path, os.path.join(webbase, r_fn)))

    if meta.get("section_name"):
        e["section_name"] = meta["section_name"]

    cov = e["cover"]
    local = os.path.join(BASE, cov.lstrip("/")) if cov and cov.startswith(("static", "/static")) else None
    if not cov or (local and not os.path.exists(local)):
        ctype = {"pdf": "magazine_pdf"}.get(e["type"], e["type"])
        e["cover"] = pub_icons.generate_icon(ctype, e["tags"], e["title"],
                                             seed=e["size"] % 100000)

    e["currency"] = row["currency"] or "INR"
    e["price_min"] = float(row["price_min"] or 0)
    e["price_sugg"] = float(row["price_suggested"] or 0)
    e["section"] = _SECTION_OF.get(e["type"], "magazines")
    e["cover"] = _web_cover(e["cover"])
    e["id"] = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(fn)[0].lower()).strip("-")
    e["year"] = (e.get("date") or "")[:4]
    e["publication_id"] = row["id"]
    e["dtp_project_id"] = meta.get("dtp_project_id")

    e.update(extras)
    e["author"] = extras.get("byline") or (e["subtitle"] if e["type"] == "gazette" else None)

    if row["description"] and not e.get("description"):
        e["description"] = str(row["description"]).strip()
    if row["issue_number"]:
        e["issue_number"] = row["issue_number"]

    if contents:
        e["contents"] = contents
        e["article_count"] = len(contents)
    elif row["article_count"]:
        e["article_count"] = row["article_count"]

    ser = _series_of(db, e, meta)
    if ser:
        e["series"] = ser

    if e["type"] == "gazette" and not extras.get("tags"):
        e["tags"] = []
    if contents:
        e["tags"] = ve_library.merge_tag_names(
            e["tags"], _ve_tags.names_for_entries(db, [c["id"] for c in contents]))
    return e


def build_catalog(db):
    if REFRESH:
        for f in os.listdir(pub_icons._UPLOADS):
            if f.startswith("_icon_"):
                try: os.remove(os.path.join(pub_icons._UPLOADS, f))
                except OSError: pass

    added = ve_library.register_all(db)
    if added:
        log(f"registered {added} previously unshelved artifact(s) into publications")

    items = []
    for row in db.execute("SELECT * FROM publications ORDER BY id").fetchall():
        if not row["filename"]:
            continue
        try:
            e = _entry_for_row(db, row)
        except Exception as ex:
            log("skip", row["filename"], "->", ex)
            continue
        if e:
            items.append(e)
        else:
            log("missing file, not catalogued ->", row["filename"])
    return items


def flush_copies():
    for sub in ("media", "publications", "uploads"):
        d = os.path.join(OUT_DIR, WEB_UP, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
    n = 0
    for src, rel_dest in _COPY_QUEUE:
        if not os.path.exists(src):
            log("WARNING: source missing, not copied ->", src)
            continue
        if os.path.getsize(src) == 0:
            log("WARNING: source is 0 bytes, skipped ->", src)
            continue
        dest = os.path.join(OUT_DIR, rel_dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        n += 1
    return n


def remove_stale_snapshot():
    stale = os.path.join(OUT_DIR, "voice_express.snapshot.db")
    if os.path.exists(stale):
        os.remove(stale)
        return True
    return False


def ensure_config():
    if os.path.exists(CFG_PATH):
        return False
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    return True


def ensure_nojekyll():
    if os.path.exists(NOJEKYLL_PATH):
        return False
    open(NOJEKYLL_PATH, "w").close()
    return True


def write_catalog(items):
    os.makedirs(OUT_DIR, exist_ok=True)
    counts = {key: 0 for key, _, _ in SECTIONS}
    for it in items:
        counts[it["section"]] = counts.get(it["section"], 0) + 1
    series = {}
    for it in items:
        s = it.get("series")
        if not s:
            continue
        cur = series.setdefault(s["key"], {
            "key": s["key"], "label": s["label"], "kind": s["kind"],
            "count": 0, "cover": None, "latest": "", "earliest": "",
        })
        cur["count"] += 1
        d = it.get("date") or ""
        if d > cur["latest"]:
            cur["latest"] = d
            cur["cover"] = it.get("cover") or cur["cover"]
        if d and (not cur["earliest"] or d < cur["earliest"]):
            cur["earliest"] = d

    data = {
        "generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sections": [{"key": k, "label": l, "count": counts.get(k, 0)} for k, l, _ in SECTIONS],
        "series": sorted(series.values(), key=lambda s: -s["count"]),
        "catalog": items,
    }
    with open(CAT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    legacy = os.path.join(OUT_DIR, "catalog.js")
    if os.path.exists(legacy):
        try: os.remove(legacy)
        except OSError: pass
    return counts


def stamp_service_worker():
    if not os.path.exists(SW_PATH):
        return None
    with open(SW_PATH, encoding="utf-8") as f:
        src = f.read()
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    new, n = re.subn(r'var CACHE = "ve-shell-[^"]*";',
                     'var CACHE = "ve-shell-%s";' % stamp, src, count=1)
    if not n or new == src:
        return None
    with open(SW_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return stamp


def main():
    db = _connect()
    try:
        items = build_catalog(db)
    finally:
        db.close()
    counts = write_catalog(items)
    n_copied = flush_copies()
    dropped_snapshot = remove_stale_snapshot()
    if ensure_config():
        log("wrote starter config ->", CFG_PATH, "(paste your Ko-fi / PayPal / API links here)")
    stamp = stamp_service_worker()
    if stamp:
        log("service worker shell cache ->", "ve-shell-" + stamp)
    if ensure_nojekyll():
        log("wrote .nojekyll ->", NOJEKYLL_PATH, "(GitHub Pages must not run Jekyll on this folder)")
    log(f"{len(items)} publications ->", CAT_PATH)
    for key, label, _ in SECTIONS:
        log(f"  {label:28} {counts.get(key, 0)}")
    log(f"  {'Files copied into static/':28} {n_copied}")
    if dropped_snapshot:
        log(f"  {'DB snapshot':28} removed (never used; not for a published dir)")


if __name__ == "__main__":
    main()
