#!/usr/bin/env python3
from __future__ import annotations
import re

PROSE_ROLES = {
    "lede", "analysis", "context", "scene", "testimony",
    "resolution", "note", "dateline", "caption", "subtitle", "description",
}
QUOTE_VARIANTS = {"pull-quote", "field-quote", "spoken-quote", "quote-block"}
PHOTO_TYPES = {"captioned", "dump", "scene", "crowd", "narrative",
               "document", "portrait", "sequence", "grid", "collage",
               "comic", "reference"}
STRUCTURE = {
    "article-section", "section-heading", "section-subheading", "section-divider",
    "post-header", "article-deck", "dateline", "intro-note", "italic-note",
    "photo-unit", "photo-group", "photo-narrative-unit", "photo-frame",
    "photo-caption", "photo-prose", "photo-essay-deck",
    "qa-line", "qa-speaker", "quote-text", "quote-attribution",
    "fn", "ve-gallery", "embedded",
    "comparison", "compare-item", "compare-label",
    "panel", "panel-caption", "reference-label", "quote-credit", "photo-credit",
} | QUOTE_VARIANTS

DROP_CLASSES = {"columns-default", "columns-2", "columns-3"}

CLASS_FOLDS = {
    "interview-question": "qa-line",
    "interview-quote": "qa-line",
    "interview-speaker": "qa-speaker",
    "photo-item": "photo-frame",
    "photo-unit-caption": "photo-caption",
    "photo-subtitle": "photo-caption",
    "photo-description": "photo-prose",
    "photo-intro-note": "intro-note",
}
WP_TOKEN = re.compile(r"^(wp-|has-|is-|size-|align|ql-|mce-)")

_IMG = re.compile(r"<img\b[^>]*>", re.I)


def _clean_class_value(value: str) -> str:
    out = []
    for tok in value.split():
        if WP_TOKEN.match(tok) or tok in DROP_CLASSES:
            continue
        out.append(CLASS_FOLDS.get(tok, tok))
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return " ".join(uniq)


def _fix_classes(html: str) -> str:
    def repl(m):
        q = m.group(1)
        cleaned = _clean_class_value(m.group(2))
        return f"class={q}{cleaned}{q}" if cleaned else ""
    return re.sub(r'class=(["\'])(.*?)\1', repl, html)


def _fix_img(tag: str, alt_lookup=None) -> str:
    alts = re.findall(r'alt=(["\'])(.*?)\1', tag)
    chosen = next((v.strip() for _, v in alts if v.strip()), "")
    if not chosen and alt_lookup:
        src = (re.search(r'src=(["\'])(.*?)\1', tag) or [None, "", ""])[2]
        chosen = alt_lookup(src) or ""
    tag = re.sub(r'\s*alt=(["\']).*?\1', "", tag)
    return re.sub(r"(<img\b)", r'\1' + f' alt="{chosen}"', tag, count=1)


def normalize(html: str, alt_lookup=None) -> str:
    if not html:
        return html
    out = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    out = _fix_classes(out) if "class=" in out else out
    out = re.sub(r"\sclass=(['\"])\s*\1", "", out)
    out = re.sub(r'class="([^"]*\b)ve-gallery(\b[^"]*)"',
                 lambda m: f'class="{(m.group(1)+ "photo-group" + m.group(2)).strip()}" data-type="dump"',
                 out)
    out = re.sub(r'\sdata-text-role=(["\'])(.*?)\1',
                 lambda m: (f' data-text-role={m.group(1)}{m.group(2)}{m.group(1)}'
                            if m.group(2) in PROSE_ROLES else ""),
                 out)
    out = _IMG.sub(lambda m: _fix_img(m.group(0), alt_lookup), out)
    return out


def regroup_figures(html: str) -> str:
    if not html or "<figure" not in html:
        return html
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html
    soup = BeautifulSoup(html, "html.parser")
    in_group = lambda el: el.find_parent(
        class_=lambda c: c and any(k in c for k in ("photo-group", "photo-unit", "photo-narrative-unit")))
    seen, runs = set(), []
    for fig in soup.find_all("figure"):
        if id(fig) in seen:
            continue
        seen.add(id(fig))
        if in_group(fig):
            continue
        run, sib = [fig], fig.next_sibling
        while sib is not None:
            if isinstance(sib, str):
                if sib.strip() == "":
                    sib = sib.next_sibling; continue
                break
            if getattr(sib, "name", None) == "figure" and not in_group(sib):
                run.append(sib); seen.add(id(sib)); sib = sib.next_sibling
            else:
                break
        if len(run) >= 2:
            runs.append(run)
    for run in runs:
        wrap = soup.new_tag("div")
        wrap["class"] = ["photo-group"]; wrap["data-type"] = "grid"
        run[0].insert_before(wrap)
        for f in run:
            wrap.append(f.extract())
    return str(soup)


def audit(html: str) -> dict:
    classes = set()
    for cl in re.findall(r'class=["\']([^"\']*)["\']', html or ""):
        classes.update(cl.split())
    non_canon = sorted(
        c for c in classes
        if c not in STRUCTURE and c not in QUOTE_VARIANTS
        and not c.startswith(("photo-", "section-", "qa-", "quote-", "article-")))
    bad_roles = sorted(set(
        v for v in re.findall(r'data-text-role=["\']([^"\']*)["\']', html or "")
        if v not in PROSE_ROLES))
    noalt = sum(1 for t in _IMG.findall(html or "")
                if not (re.search(r'alt=["\'][^"\']+["\']', t)))
    return {"non_canonical_classes": non_canon, "bad_roles": bad_roles,
            "imgs_without_alt": noalt}


def _main():
    import argparse, os, sqlite3
    ap = argparse.ArgumentParser(description="Audit content for non-canonical semantic markup.")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", "voice_express.db"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    db = sqlite3.connect(a.db); db.row_factory = sqlite3.Row
    bad = {}
    for r in db.execute("SELECT id, content FROM articles"):
        rep = audit(r["content"] or "")
        if rep["non_canonical_classes"] or rep["bad_roles"] or rep["imgs_without_alt"]:
            bad[f"article#{r['id']}"] = rep
    for k, v in bad.items():
        print(k, v)
    print(f"\n{len(bad)} bodies with non-canonical markup")
    db.close()


if __name__ == "__main__":
    _main()
