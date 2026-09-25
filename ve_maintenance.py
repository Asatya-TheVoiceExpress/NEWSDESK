#!/usr/bin/env python3
import os, sys, json, datetime, shutil, subprocess, sqlite3, hashlib, calendar
import app
import ve_library
import ve.db as _ve_db

BASE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.environ.get("MEDIA_PATH", os.path.join(BASE, "static", "media")); os.makedirs(MEDIA, exist_ok=True)
PUBS = app.PUBLICATIONS_FOLDER
STATE = os.environ.get("VE_MAINT_STATE", os.path.join(BASE, ".ve_maint_state.json"))
ARGS = set(sys.argv[1:])
DO_ALL = "--all" in ARGS; DEEP = "--deep" in ARGS; NO_PDF = "--no-pdf" in ARGS
PUSH = ("--push" in ARGS) or os.environ.get("VE_GIT_PUSH", "").lower() in ("1", "true", "yes")

def log(*a): print("[maint]", *a)

def load_state():
    try: return json.load(open(STATE, encoding="utf-8"))
    except Exception: return {"last_run": "2000-01-01T00:00:00"}
def save_state(s): json.dump(s, open(STATE, "w", encoding="utf-8"))


def _build(db, kind, source_ref, fmt, gen_args, data, title=None, sig=None):
    status = {'state': 'stale'}
    if app._ve_library is not None:
        try:
            status = app._ve_library.artifact_status(
                db, kind, source_ref, 'pdf' if fmt == 'pdf' else 'html',
                sig=sig, static_root=app.STATIC_ROOT)
        except Exception as e:
            log('status check failed', kind, source_ref, e)
    if status.get('state') == 'fresh':
        return False
    app._dtp_artifact(db, kind, source_ref, fmt, gen_args=gen_args, data=data,
                      title=title, sig=sig)
    return True


def do_gazettes(db, since):
    rows = db.execute(
        "SELECT a.*,au.name author_name,c.name category_name,s.name section_name "
        "FROM articles a LEFT JOIN authors au ON a.author_id=au.id "
        "LEFT JOIN categories c ON a.category_id=c.id LEFT JOIN sections s ON a.section_id=s.id "
        "WHERE a.status='published'" + ("" if DO_ALL else " AND a.updated_at>?"),
        () if DO_ALL else (since,)).fetchall()
    n = 0
    for r in rows:
        try:
            art = app._article_print_dict(db, r)
            art["byline_auto"] = app.compose_byline(app.article_authors_list(db, r["id"])) or art.get("author_name")
            app._localize_articles(db, [art])
            enh = app.get_pdf_enhancement(db, 'gazette', str(r["id"]))
            gz_sig = f'{r["updated_at"]}|{json.dumps(enh, sort_keys=True)}'
            if not _build(db, 'gazette', str(r["id"]), 'html',
                          ('--article-id', r["id"]), {'art': art, 'enhancement': enh},
                          title=r["title"], sig=gz_sig):
                continue
            n += 1
        except Exception as e:
            log("gazette", r["id"], "FAILED", e)
    log(f"gazettes: {n}")

def do_broadsheets(db):
    months = db.execute(
        "SELECT DISTINCT ym FROM ("
        "  SELECT substr(published_at,1,7) ym FROM articles"
        "   WHERE status='published' AND published_at IS NOT NULL"
        "  UNION"
        "  SELECT substr(entry_date,1,7) ym FROM column_entries"
        "   WHERE status='published' AND entry_date IS NOT NULL"
        ") WHERE ym IS NOT NULL ORDER BY ym").fetchall()
    n = 0; skipped = 0
    for mr in months:
        ym = mr["ym"]
        if not ym: continue
        y, m = int(ym[:4]), int(ym[5:7])
        try:
            enh = app.get_pdf_enhancement(db, 'broadsheet', ym)
            sig = f'{app._month_sig(db, ym)}|{json.dumps(enh, sort_keys=True)}'
            ed = app._generate_newsletter(db, y, m)
            content = ed.get("content", {}) or {}
            if not content.get("articles") and not content.get("columns"): continue
            for a in content.get("articles", []):
                a["byline_auto"] = app.compose_byline(app.article_authors_list(db, a["id"])) or a.get("author_name")
                srow = db.execute("SELECT s.name FROM articles ar LEFT JOIN sections s ON ar.section_id=s.id WHERE ar.id=?", [a["id"]]).fetchone()
                if srow and srow[0]: a["section_name"] = srow[0]
            ed_title = f'The Voice Express - {calendar.month_name[m]} {y}'
            if not _build(db, 'broadsheet', ym, 'html' if NO_PDF else 'pdf',
                          ('--ym', ym), {'articles': content.get('articles'), 'enhancement': enh},
                          title=ed_title, sig=sig):
                skipped += 1; continue
            n += 1
        except Exception as e:
            log("broadsheet", ym, "FAILED", e)
    log(f"broadsheets: {n} built, {skipped} unchanged (skipped)")

def do_magazines(db):
    rows = db.execute("SELECT * FROM publications WHERE pub_type IN ('magazine_html','magazine_pdf')").fetchall()
    n = 0; skipped = 0
    for r in rows:
        try:
            meta = json.loads(r["metadata"] or "{}")
            aids = [a for a in (meta.get("article_ids") or [x.get("id") for x in meta.get("articles", [])]) if a]
            if not aids or not r["filename"]:
                continue
            enh = app.get_pdf_enhancement(db, 'magazine', r["id"])
            ph = ",".join("?" * len(aids))
            arows = db.execute(f"SELECT id,updated_at FROM articles WHERE id IN ({ph})", aids).fetchall()
            creator = meta.get("creator", "") or ""
            description = meta.get("description", "") or ""
            sig = hashlib.md5(('|'.join(f'{a["id"]}:{a["updated_at"]}' for a in arows)
                               + f'#{r["title"]}#{creator}#{description}'
                               + json.dumps(enh, sort_keys=True)).encode()).hexdigest()
            fmt = 'pdf' if r["pub_type"] == "magazine_pdf" else 'html'
            src_ref = ','.join(str(a) for a in aids)
            if app._ve_library is not None:
                st = app._ve_library.artifact_status(db, 'magazine', src_ref, fmt,
                                                     sig=sig, static_root=app.STATIC_ROOT)
                if st.get('state') == 'fresh':
                    skipped += 1; continue
            articles = []
            for aid in aids:
                row = db.execute(
                    "SELECT a.*,au.name as author_name,c.name as category_name,"
                    "s.name as section_name,s.slug as section_slug "
                    "FROM articles a LEFT JOIN authors au ON a.author_id=au.id "
                    "LEFT JOIN categories c ON a.category_id=c.id "
                    "LEFT JOIN sections s ON a.section_id=s.id "
                    "WHERE a.id=? AND a.status='published'", [aid]).fetchone()
                if row: articles.append(app._article_print_dict(db, row))
            if not articles:
                continue
            app._localize_articles(db, articles)
            app._dtp_artifact(db, 'magazine', src_ref, fmt,
                              gen_args=('--article-id', aids[0], '--title', r["title"],
                                        '--creator', creator, '--description', description),
                              data={'articles': articles}, title=r["title"], sig=sig)
            n += 1
        except Exception as e:
            log("magazine", r["id"], "FAILED", e)
    log(f"magazines: {n} built, {skipped} unchanged (skipped)")

def _weeks(dates):
    out = {}
    for d in dates:
        try: iso = datetime.date.fromisoformat(d[:10]).isocalendar()
        except Exception: continue
        out.setdefault(f"{iso[0]}-W{iso[1]:02d}", []).append(d[:10])
    return out

def _months(dates):
    out = {}
    for d in dates:
        if len(d or "") >= 7:
            out.setdefault(d[:7], []).append(d[:10])
    return out

def _years(dates):
    out = {}
    for d in dates:
        if len(d or "") >= 4:
            out.setdefault(d[:4], []).append(d[:10])
    return out

def _compile_one(db, col, arts, period, label, key, enh):
    sig = hashlib.md5(('|'.join(f'{a["id"]}:{a.get("updated_at","")}' for a in arts)
                       + json.dumps(enh or {}, sort_keys=True)).encode()).hexdigest()
    fmt = 'html' if NO_PDF else 'pdf'
    title = f'{col["title"]} — Booklet, {label or period}'
    return _build(db, 'booklet', f'{col["id"]}:{period}:{label}', fmt,
                  ('--column-id', col["id"], '--period', period, '--label', label),
                  {'articles': arts, 'col_row': dict(col), 'enhancement': enh}, title=title, sig=sig)

def do_compilations(db):
    cols = db.execute("SELECT * FROM columns WHERE status='published'").fetchall()
    n = 0; skipped = 0
    for col in cols:
        byline = app.compose_byline(app.column_authors_list(db, col["id"]))
        ents = db.execute("SELECT * FROM column_entries WHERE column_id=? AND status='published' ORDER BY entry_date", [col["id"]]).fetchall()
        if not ents: continue
        enh = app.get_pdf_enhancement(db, 'column_booklet', col["id"])
        dates = [(e["entry_date"] or "")[:10] for e in ents]
        for wk, ds in _weeks(dates).items():
            lo, hi = min(ds), max(ds)
            sub = [e for e in ents if lo <= (e["entry_date"] or "")[:10] <= hi]
            arts = [app._entry_to_article(db, col, e, byline) for e in sub]
            for a, e in zip(arts, sub): a["byline_auto"] = byline; a["updated_at"] = e["updated_at"]
            if _compile_one(db, col, arts, "week", f"{lo} – {hi}", f'compilation_{col["id"]}_{wk}', enh):
                n += 1
            else:
                skipped += 1
        if DEEP:
            def _sub(lo, hi):
                sub = [e for e in ents if lo <= (e["entry_date"] or "")[:10] <= hi]
                arts = [app._entry_to_article(db, col, e, byline) for e in sub]
                for a, e in zip(arts, sub):
                    a["byline_auto"] = byline
                    a["updated_at"] = e["updated_at"] if "updated_at" in e.keys() else e["entry_date"]
                return arts

            runs = []
            for ym, ds in sorted(_months(dates).items()):
                runs.append(("month", ym, min(ds), max(ds)))
            for yr, ds in sorted(_years(dates).items()):
                runs.append(("year", yr, min(ds), max(ds)))
            runs.append(("all", "All time", min(dates), max(dates)))

            for per, label, lo, hi in runs:
                arts = _sub(lo, hi)
                if not arts:
                    continue
                if _compile_one(db, col, arts, per, label,
                                f'compilation_{col["id"]}_{per}_{label}', enh):
                    n += 1
                else:
                    skipped += 1
    tagged = ve_library.sync_booklet_tags(db)
    log(f"compilations: {n} built, {skipped} unchanged (skipped), {tagged} tag sets synced")

def _sync_tree(src, dst):
    src = os.path.realpath(src); dst = os.path.realpath(dst)
    if src == dst or not os.path.isdir(src):
        return
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out, exist_ok=True)
        for fn in files:
            s = os.path.join(root, fn); d = os.path.join(out, fn)
            if (not os.path.exists(d)) or os.path.getsize(d) != os.path.getsize(s):
                shutil.copy2(s, d)

def git_push():
    repo = os.path.realpath(os.environ.get("VE_REPO_DIR", BASE))
    try:
        c = _ve_db.connect(app.DATABASE); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.close()
    except Exception as e:
        log("checkpoint:", e)
    dbdst = os.path.join(repo, "voice_express.db")
    if os.path.realpath(app.DATABASE) != os.path.realpath(dbdst):
        shutil.copy2(app.DATABASE, dbdst)
    _sync_tree(app.UPLOAD_FOLDER,        os.path.join(repo, "static", "uploads"))
    _sync_tree(app.PUBLICATIONS_FOLDER,  os.path.join(repo, "static", "publications"))
    _sync_tree(MEDIA,                    os.path.join(repo, "static", "media"))

    def git(*a): return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        log("git: nothing to push"); return
    msg = "content: maintenance sync " + datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    c = git("-c", "user.name=ve-maintenance", "-c", "user.email=maintenance@thevoiceexpress",
            "commit", "-m", msg)
    if c.returncode != 0:
        log("git commit failed:", c.stderr.strip() or c.stdout.strip()); return
    p = git("push")
    log("git push:", "ok" if p.returncode == 0 else "FAILED " + (p.stderr.strip() or p.stdout.strip()))

def main():
    st = load_state(); since = st.get("last_run", "2000-01-01T00:00:00")
    db = app.get_db()
    try:
        log("start", "(--all)" if DO_ALL else f"(since {since})", "(deep)" if DEEP else "", "(push)" if PUSH else "")
        do_gazettes(db, since)
        do_broadsheets(db)
        do_magazines(db)
        do_compilations(db)
    finally:
        db.close()
    st["last_run"] = datetime.datetime.utcnow().isoformat(); save_state(st)
    log("done. artifacts in", MEDIA)
    if PUSH:
        git_push()

if __name__ == "__main__":
    main()
