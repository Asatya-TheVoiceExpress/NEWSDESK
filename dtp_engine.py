#!/usr/bin/env python3
from __future__ import annotations
import base64
import calendar
import hashlib
import json
import math
import os
import random
import string
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from html import escape as _esc, unescape as _un

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import make_magazine as mm
from bs4 import BeautifulSoup
import ve.db as _ve_db
import ve.paths as _ve_paths
import ve.tags as _ve_tags

DB_PATH = _ve_paths.db_path(env=('DTP_DB_PATH', 'DB_PATH'))
STATIC_ROOT = _ve_paths.static_root()
PUBLICATIONS_FOLDER = _ve_paths.publications_path()
os.makedirs(PUBLICATIONS_FOLDER, exist_ok=True)
_DTP_PUB_TYPE = {'magazine': 'magazine_pdf', 'broadsheet': 'broadsheet', 'gazette': 'gazette',
                  'booklet': 'booklet', 'custom': 'pdf'}
try:
    from pub_icons import generate_icon as _gen_icon
except Exception:
    _gen_icon = None
try:
    from pub_icons import flow_field_png as _flow_png, voronoi_png as _voronoi_png, \
        spiral_text_icon as _spiral_icon
except Exception:
    _flow_png = _voronoi_png = _spiral_icon = None

PAGE_PRESETS = {
    'a4': {'w': 210.0, 'h': 297.0},
    'letter': {'w': 215.9, 'h': 279.4},
    'tabloid': {'w': 279.4, 'h': 431.8},
    'broadsheet': {'w': 420.0, 'h': 297.0},
    'booklet': {'w': 148.0, 'h': 210.0},
}


def get_db():
    return _ve_db.connect(DB_PATH)


def ensure_schema():
    db = get_db()
    _ve_db.migrate(db)
    db.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def blank_layout(preset='a4'):
    dims = PAGE_PRESETS.get(preset, PAGE_PRESETS['a4'])
    return {'preset': preset, 'page': dims, 'pages': [{'blocks': []}]}


PAGE_MARGINS = {
    'magazine': (12.0, 14.0, 10.0, 18.0),
    'broadsheet': (11.0, 12.0, 11.0, 12.0),
    'gazette': (14.0, 16.0, 14.0, 16.0),
    'booklet': (10.0, 10.0, 10.0, 10.0),
    'custom': (15.0, 15.0, 15.0, 15.0),
}


def _project_dict(row):
    d = dict(row)
    try:
        layout = json.loads(d['layout'] or '{}')
    except (json.JSONDecodeError, TypeError):
        layout = {}
    if not layout.get('pages'):
        layout = blank_layout()
    layout.setdefault('page', PAGE_PRESETS.get(layout.get('preset'), PAGE_PRESETS['a4']))
    layout['page'] = dict(layout['page'])
    layout['page'].setdefault('margin', list(PAGE_MARGINS.get(d.get('kind'), PAGE_MARGINS['custom'])))
    layout.setdefault('doc_layers', [{'name': 'Default', 'visible': True, 'locked': False}])
    d['layout'] = layout
    return d


def get_project(pid):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM dtp_projects WHERE id=?', [pid]).fetchone()
        return _project_dict(row) if row else None
    finally:
        db.close()


def _find_existing(kind, source_ref):
    db = get_db()
    try:
        row = db.execute('SELECT id FROM dtp_projects WHERE kind=? AND source_ref=? '
                         'ORDER BY updated_at DESC, id DESC LIMIT 1',
                         [kind, str(source_ref)]).fetchone()
        return row['id'] if row else None
    finally:
        db.close()


_DTP_IMG_CACHE_DIR = os.path.join(STATIC_ROOT, '_dtp_cache')
_DATA_URI_RE = re.compile(r'data:image/(png|jpe?g|gif|webp);base64,([A-Za-z0-9+/=]+)', re.I)


def _deflate_images_in_layout(layout):
    s = json.dumps(layout)
    if 'data:image' not in s:
        return layout
    os.makedirs(_DTP_IMG_CACHE_DIR, exist_ok=True)

    def repl(m):
        ext = m.group(1).lower()
        ext = 'jpg' if ext == 'jpeg' else ext
        try:
            raw = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)
        fn = f'{hashlib.sha1(raw).hexdigest()}.{ext}'
        fp = os.path.join(_DTP_IMG_CACHE_DIR, fn)
        if not os.path.exists(fp):
            with open(fp, 'wb') as f:
                f.write(raw)
        return f'/static/_dtp_cache/{fn}'

    return json.loads(_DATA_URI_RE.sub(repl, s))


def _dedupe_extra_css_in_layout(layout):
    seen = set()
    for page in (layout.get('pages') or []):
        for b in page.get('blocks', []):
            css = b.get('extra_css')
            if css:
                if css in seen:
                    b['extra_css'] = None
                else:
                    seen.add(css)
    return layout


def _normalize_layout_for_storage(layout):
    return _dedupe_extra_css_in_layout(_deflate_images_in_layout(layout))


_render_embed_cache = {}
_STATIC_IMG_SRC_RE = re.compile(r'(/static/_dtp_cache/[^\s"\'<>)]+|/static/[^\s"\'<>)]+\.(?:png|jpe?g|gif|webp))', re.I)


_PRINT_EMBED_MAX_EDGE = 2400
_PRINT_EMBED_MIN_BYTES = 600_000


def _downscale_for_print(raw, ext):
    if len(raw) < _PRINT_EMBED_MIN_BYTES:
        return raw, ext
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return raw, ext
    w, h = im.size
    if max(w, h) > _PRINT_EMBED_MAX_EDGE:
        k = _PRINT_EMBED_MAX_EDGE / float(max(w, h))
        im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    buf = io.BytesIO()
    if im.mode in ('RGBA', 'LA', 'P'):
        im.convert('RGBA').save(buf, 'PNG', optimize=True)
        new_ext = 'png'
    else:
        im.convert('RGB').save(buf, 'JPEG', quality=82, optimize=True, progressive=True)
        new_ext = 'jpeg'
    out = buf.getvalue()
    return (out, new_ext) if len(out) < len(raw) else (raw, ext)


def _embed_static_images(html):
    if '/static/' not in html:
        return html

    def repl(m):
        rel = m.group(1)
        cached = _render_embed_cache.get(rel)
        if cached is not None:
            return cached
        fp = os.path.join(STATIC_ROOT, rel[len('/static/'):].replace('/', os.sep))
        out = rel
        if os.path.exists(fp):
            ext = os.path.splitext(fp)[1].lstrip('.').lower()
            ext = 'jpeg' if ext == 'jpg' else ext
            try:
                with open(fp, 'rb') as f:
                    raw = f.read()
                raw, ext = _downscale_for_print(raw, ext)
                out = f'data:image/{ext};base64,' + base64.b64encode(raw).decode()
            except Exception:
                out = rel
        _render_embed_cache[rel] = out
        return out

    return _STATIC_IMG_SRC_RE.sub(repl, html)


def _create(name, kind, source_ref, layout):
    layout = _normalize_layout_for_storage(layout)
    db = get_db()
    try:
        cur = db.execute('INSERT INTO dtp_projects (name, kind, source_ref, layout, created_at, updated_at) '
                         'VALUES (?,?,?,?,?,?)', [name, kind, source_ref, json.dumps(layout), now(), now()])
        db.commit()
        return cur.lastrowid
    finally:
        db.close()


def _update_layout(pid, layout):
    layout = _normalize_layout_for_storage(layout)
    db = get_db()
    try:
        db.execute('UPDATE dtp_projects SET layout=?, updated_at=? WHERE id=?',
                  [json.dumps(layout), now(), pid])
        db.commit()
    finally:
        db.close()


_FRAME_FIELDS = ('x', 'y', 'w', 'h', 'rotation', 'layer', 'locked',
                 'fit_box', 'fit_text', 'link_next')


def _reflow_page(old_blocks, new_blocks):
    pools = {}
    for b in old_blocks:
        pools.setdefault(b.get('type'), []).append(b)
    cursors = {}
    out = []
    for nb in new_blocks:
        t = nb.get('type')
        i = cursors.get(t, 0)
        pool = pools.get(t) or []
        if i < len(pool):
            ob = pool[i]
            cursors[t] = i + 1
            merged = dict(nb)
            merged['id'] = ob.get('id', nb.get('id'))
            for f in _FRAME_FIELDS:
                if f in ob:
                    merged[f] = ob[f]
                elif f in merged and f in ('rotation', 'layer', 'locked',
                                           'fit_box', 'fit_text', 'link_next'):
                    pass
            out.append(merged)
        else:
            out.append(nb)
    return out


def reflow_into_frames(old_layout, new_layout):
    if not isinstance(old_layout, dict) or not old_layout.get('pages'):
        return new_layout
    merged = dict(new_layout)
    old_pages = old_layout.get('pages') or []
    pages = []
    for i, np_ in enumerate(new_layout.get('pages') or []):
        op = old_pages[i] if i < len(old_pages) else None
        if not op:
            pages.append(np_)
            continue
        page = dict(np_)
        page['blocks'] = _reflow_page(op.get('blocks') or [], np_.get('blocks') or [])
        for carry in ('master', 'preset'):
            if carry in op:
                page[carry] = op[carry]
        pages.append(page)
    merged['pages'] = pages
    for carry in ('page', 'preset', 'doc_layers', 'masters', 'guides'):
        if carry in old_layout:
            merged[carry] = old_layout[carry]
    return merged


def _regenerate_layout(pid, layout):
    proj = get_project(pid)
    if proj:
        layout = reflow_into_frames(proj.get('layout') or {}, layout)
    _update_layout(pid, layout)
    return pid


_ART_SQL = '''SELECT a.id, a.title, a.subtitle, a.content, a.excerpt, a.featured_image,
                     a.byline, a.published_at, a.author_id,
                     au.name AS author_name, s.name AS section_name, c.name AS category_name
              FROM articles a LEFT JOIN authors au ON a.author_id=au.id
              LEFT JOIN sections s ON a.section_id=s.id LEFT JOIN categories c ON a.category_id=c.id'''


def _art_row_to_dict(row):
    d = dict(row)
    d['byline_auto'] = d.get('author_name') or d.get('byline') or ''
    d['published_date'] = (d.get('published_at') or '')[:10]
    d['tags'] = []
    eid = d.get('column_entry_id') or d.get('entry_id')
    if eid:
        db = get_db()
        try:
            d['tags'] = [{'name': n} for n in _ve_tags.entry_tag_names(db, eid)]
        except sqlite3.Error:
            pass
        finally:
            db.close()
    return d


def get_article(article_id):
    db = get_db()
    try:
        row = db.execute(_ART_SQL + ' WHERE a.id=?', [article_id]).fetchone()
        return _art_row_to_dict(row) if row else None
    finally:
        db.close()


def get_articles_for_month(ym):
    db = get_db()
    try:
        rows = db.execute(_ART_SQL + " WHERE a.status='published' AND strftime('%Y-%m', a.published_at)=? "
                                      "ORDER BY a.published_at", [ym]).fetchall()
        return [_art_row_to_dict(r) for r in rows]
    finally:
        db.close()


def get_articles_for_range(date_from, date_to):
    db = get_db()
    try:
        rows = db.execute(_ART_SQL + " WHERE a.status='published' "
                                      "AND date(a.published_at) BETWEEN date(?) AND date(?) "
                                      "ORDER BY a.published_at", [date_from, date_to]).fetchall()
        return [_art_row_to_dict(r) for r in rows]
    finally:
        db.close()


def get_articles_by_ids(ids):
    ids = [int(i) for i in (ids or [])]
    if not ids:
        return []
    db = get_db()
    try:
        qs = ','.join('?' * len(ids))
        rows = db.execute(_ART_SQL + f' WHERE a.id IN ({qs})', ids).fetchall()
        by_id = {r['id']: _art_row_to_dict(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]
    finally:
        db.close()


_META_FIELDS = [
    ('title', 'Title', 'text'), ('subtitle', 'Subtitle', 'text'),
    ('byline_auto', 'Byline', 'text'), ('published_date', 'Date', 'text'),
    ('excerpt', 'Excerpt', 'text'), ('category_name', 'Category', 'text'),
    ('section_name', 'Section', 'text'), ('featured_image', 'Featured image', 'image'),
]


def _block_preview(block):
    t = block.get('type')
    if t == 'photo_unit' or t == 'photo_narrative':
        return block.get('caption') or '(photo)'
    if t == 'photo_group':
        return f"({len(block.get('figures') or [])} photos)"
    if t == 'quote':
        return block.get('text', '')[:80]
    if t == 'heading':
        return block.get('text', '')[:80]
    if t == 'section':
        return f"Section: {block.get('section_index') or ''}".strip()
    return mm._plain(block.get('html', ''))[:80]


def get_article_components(article_id):
    art = get_article(article_id)
    if not art:
        return None
    meta = []
    for field, label, ftype in _META_FIELDS:
        val = art.get(field)
        if val:
            meta.append({'field': field, 'label': label, 'type': ftype, 'value': val})
    semantic = mm._semantic_blocks(art.get('content') or '') or []
    blocks = [{'index': i, 'type': b.get('type'), 'role': b.get('text_role') or '',
              'preview': _block_preview(b)} for i, b in enumerate(semantic)]
    return {'article_id': article_id, 'title': art.get('title', ''), 'meta': meta, 'blocks': blocks}


def get_article_semantic_block(article_id, index):
    art = get_article(article_id)
    if not art:
        return None
    semantic = mm._semantic_blocks(art.get('content') or '') or []
    if index < 0 or index >= len(semantic):
        return None
    return semantic[index]


_LOGO_B64 = None


def _logo_b64():
    global _LOGO_B64
    if _LOGO_B64 is None:
        _LOGO_B64 = ''
        for fn in ('tve_logo.png', 'logo.png', 'logo-ve.png'):
            p = os.path.join(STATIC_ROOT, fn)
            if not os.path.exists(p):
                p2 = os.path.join(BASE, fn)
                if os.path.exists(p2):
                    p = p2
                else:
                    continue
            if os.path.exists(p):
                import base64
                with open(p, 'rb') as f:
                    _LOGO_B64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                break
    return _LOGO_B64 or None


_STYLE_FONTS = {
    'playfair': '"Playfair Display",Georgia,serif', 'garamond': '"EB Garamond",Georgia,serif',
    'montserrat': 'Montserrat,sans-serif', 'cormorant': '"Cormorant Garamond",Georgia,serif',
    'mono': '"IBM Plex Mono",monospace', 'georgia': 'Georgia,"Times New Roman",serif',
}


_DROPCAP_SCALE = {'small': 0.7, 'medium': 1.0, 'large': 1.4}


def _apply_style_overrides(html, block):
    font = _STYLE_FONTS.get(block.get('style_font') or '')
    color = block.get('style_color') or ''
    align = block.get('style_align') or ''
    letter_spacing = block.get('style_letter_spacing')
    line_height = block.get('style_line_height')
    hyphens = block.get('style_hyphens') or ''
    columns = block.get('columns')
    dropcap = block.get('style_dropcap')
    font_size = block.get('style_font_size')

    css = ''
    if font: css += f'font-family:{font};'
    if color: css += f'color:{mm._h(color)};'
    if align: css += f'text-align:{align};'
    if letter_spacing is not None: css += f'letter-spacing:{float(letter_spacing)}px;'
    if line_height is not None: css += f'line-height:{float(line_height)};'
    if hyphens in ('auto', 'none'): css += f'hyphens:{hyphens};'
    if columns in (2, 3, '2', '3'): css += f'column-count:{int(columns)};column-gap:6mm;'
    if font_size is not None: css += f'font-size:{float(font_size)}px;'

    scale = _DROPCAP_SCALE.get(dropcap)
    if scale is not None and scale != 1.0:
        size_em = 4.8 * scale
        cls = f'dc{abs(hash((block.get("id"), dropcap))) % 100000}'
        style_tag = f'<style>.{cls} .drop-cap::first-letter{{font-size:{size_em}em}}</style>'
        inner = f'<div class="{cls}" style="{css}">{html}</div>' if css else f'<div class="{cls}">{html}</div>'
        return style_tag + inner

    if not css:
        return html
    return f'<div style="{css}">{html}</div>'

    if not css:
        return html
    return f'<div style="{css}">{html}</div>'


def _runs_to_html(runs):
    parts = []
    for r in (runs or []):
        txt = mm._h(r.get('text', ''))
        if r.get('href'):
            txt = f'<a href="{mm._h(r["href"])}" style="color:inherit">{txt}</a>'
        if r.get('underline'):
            txt = f'<u>{txt}</u>'
        if r.get('italic'):
            txt = f'<i>{txt}</i>'
        if r.get('bold'):
            txt = f'<b>{txt}</b>'
        if r.get('color'):
            txt = f'<span style="color:{mm._h(r["color"])}">{txt}</span>'
        parts.append(txt)
    return ''.join(parts)


_SVG_PATH_ARGC = {'M': 2, 'L': 2, 'C': 6, 'Q': 4}


def _parse_svg_path_commands(d):
    tokens = re.findall(r'[MLCQZmlcqz]|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', d or '')
    cmds = []
    i = 0
    cur = None
    while i < len(tokens):
        tok = tokens[i]
        if tok.upper() in _SVG_PATH_ARGC or tok.upper() == 'Z':
            cur = tok.upper()
            i += 1
            if cur == 'Z':
                cmds.append(('Z', []))
                cur = None
                continue
        if cur is None:
            i += 1
            continue
        nargs = _SVG_PATH_ARGC[cur]
        nums = []
        for x in tokens[i:i + nargs]:
            try:
                nums.append(float(x))
            except ValueError:
                nums = []
                break
        if len(nums) < nargs:
            break
        cmds.append((cur, nums))
        i += nargs
    return cmds


def _svg_path_anchor_points(svg_path):
    pts = []
    for cmd, nums in _parse_svg_path_commands(svg_path):
        if cmd in ('M', 'L'):
            pts.append([nums[0], nums[1]])
        elif cmd == 'C':
            pts.append([nums[4], nums[5]])
        elif cmd == 'Q':
            pts.append([nums[2], nums[3]])
    return pts


def _render_vector_shape(block):
    w = max(1.0, float(block.get('w', 50)))
    h = max(1.0, float(block.get('h', 30)))
    shape = block.get('shape', 'rect')
    fill = block.get('fill') or 'none'
    stroke = block.get('stroke') or '#111'
    sw = block.get('stroke_width', 1)
    pts = block.get('points') or []
    svg_path = block.get('svg_path')
    if svg_path:
        body = f'<path d="{mm._h(svg_path)}"/>'
    elif shape == 'ellipse':
        body = f'<ellipse cx="{w/2:.3f}" cy="{h/2:.3f}" rx="{w/2:.3f}" ry="{h/2:.3f}"/>'
    elif shape in ('polygon', 'polyline') and pts:
        pts_str = ' '.join(f'{float(x):.3f},{float(y):.3f}' for x, y in pts)
        tag = 'polygon' if shape == 'polygon' else 'polyline'
        body = f'<{tag} points="{mm._h(pts_str)}"/>'
    else:
        body = f'<rect x="0" y="0" width="{w:.3f}" height="{h:.3f}"/>'
    return (f'<svg viewBox="0 0 {w:.3f} {h:.3f}" width="100%" height="100%" preserveAspectRatio="none" '
            f'style="display:block;fill:{mm._h(fill)};stroke:{mm._h(stroke)};stroke-width:{sw}" '
            f'vector-effect="non-scaling-stroke">{body}</svg>')


def render_block_html(block):
    return _apply_style_overrides(_render_block_html_inner(block), block)


def _render_block_html_inner(block):
    cfg = mm._cfg()
    t = block.get('type')
    try:
        if t == 'masthead_page':
            return mm._pg_masthead(_logo_b64(), cfg)
        if t == 'cover':
            article_ids = block.get('article_ids') or []
            articles = [get_article(i) for i in article_ids]
            articles = [a for a in articles if a]
            return mm._pg_cover(articles, block.get('title', ''), block.get('date_str', ''),
                                 _logo_b64(), cfg, creator=block.get('creator', ''),
                                 description=block.get('description', ''))
        if t == 'founders':
            return ''
        if t == 'toc':
            article_ids = block.get('article_ids') or []
            articles = [get_article(i) for i in article_ids]
            articles = [a for a in articles if a]
            thumb_cache = {}
            for i, a in enumerate(articles, 1):
                fi = a.get('featured_image')
                if fi:
                    b = mm._b64(fi, STATIC_ROOT)
                    if b:
                        thumb_cache[i] = b
            return mm._pg_toc(articles, thumb_cache, cfg)
        if t == 'back_cover':
            return mm._pg_back(cfg, _logo_b64())
        if t in ('art_title', 'art_bleed'):
            art = get_article(block.get('article_id'))
            if not art:
                return '<div class="hint">Article not found</div>'
            idx = int(block.get('idx', 1))
            accent = block.get('accent') or mm._art_accent(art, idx)
            if t == 'art_title':
                return mm._pg_art_title(art, idx, accent)
            img_b64 = mm._b64(art.get('featured_image'), STATIC_ROOT) if art.get('featured_image') else None
            if not img_b64:
                return mm._pg_art_title(art, idx, accent)
            return mm._pg_art_bleed(art, idx, accent, img_b64)
        if t == 'citations':
            art = get_article(block.get('article_id'))
            if not art:
                return '<div class="hint">Article not found</div>'
            idx = int(block.get('idx', 1))
            accent = block.get('accent') or mm._art_accent(art, idx)
            citations = [(c.get('num'), c.get('text'), c.get('url', '')) for c in (block.get('citations') or [])]
            return mm._pg_citations_page(art, idx, int(block.get('page_num', 1)), citations, accent, cfg,
                                          mm._detect_type(art))
        if t == 'body':
            art = get_article(block.get('article_id'))
            if not art:
                return '<div class="hint">Article not found</div>'
            idx = int(block.get('idx', 1))
            accent = block.get('accent') or mm._art_accent(art, idx)
            art_type = block.get('art_type') or mm._detect_type(art)
            page_blocks = block.get('blocks')
            semantic_blocks = page_blocks if page_blocks is not None else mm._semantic_blocks(art.get('content') or '')
            if not semantic_blocks:
                return f'<div class="cols-2">{art.get("content") or ""}</div>'
            citations = [(c.get('num'), c.get('text'), c.get('url', '')) for c in (block.get('citations') or [])] or None
            chunk = mm._render_blocks(semantic_blocks, art_type, int(block.get('pq_style', 1)), accent,
                                       bool(block.get('is_first', True)), citations)
            return mm._pg_body(art, idx, int(block.get('page_num', 1)), bool(block.get('is_first', True)),
                                chunk, int(block.get('pq_style', 1)), cfg, accent, art_type,
                                citations, bool(block.get('is_last', False)))
        if t == 'body_chrome':
            art = get_article(block.get('article_id'))
            if not art:
                return '<div class="hint">Article not found</div>'
            idx = int(block.get('idx', 1))
            accent = block.get('accent') or mm._art_accent(art, idx)
            art_type = block.get('art_type') or mm._detect_type(art)
            is_last = bool(block.get('is_last', False))
            citations = [(c.get('num'), c.get('text'), c.get('url', '')) for c in (block.get('citations') or [])] or None
            return mm._pg_body(art, idx, int(block.get('page_num', 1)), bool(block.get('is_first', True)),
                                '', int(block.get('pq_style', 1)), cfg, accent, art_type,
                                citations if is_last else None, is_last)
        if t == 'sem_para':
            art = get_article(block.get('article_id'))
            if not art:
                return '<div class="hint">Article not found</div>'
            idx = int(block.get('idx', 1))
            accent = block.get('accent') or mm._art_accent(art, idx)
            art_type = block.get('art_type') or mm._detect_type(art)
            sem = block.get('sem') or {}
            if sem.get('type') == 'paragraph' and sem.get('runs'):
                sem = dict(sem)
                cls = f' class="{mm._h(sem["class"])}"' if sem.get('class') else ''
                role = f' data-text-role="{mm._h(sem["text_role"])}"' if sem.get('text_role') else ''
                sem['html'] = f'<p{cls}{role}>{_runs_to_html(sem["runs"])}</p>'
            cx = block.get('crop_x'); cy = block.get('crop_y')
            if cx is not None and cy is not None and sem.get('img') and sem.get('type') in ('photo_unit', 'photo_narrative'):
                sem = dict(sem)
                pos = f'object-position:{float(cx)}% {float(cy)}%'
                sem['img'] = re.sub(r'<img\b', f'<img style="{pos}"', sem['img'], count=1)
            citations = [(c.get('num'), c.get('text'), c.get('url', '')) for c in (block.get('citations') or [])] or None
            return mm._render_blocks([sem], art_type, int(block.get('pq_style', 1)), accent,
                                      bool(block.get('is_first', False)), citations)
        if t == 'pullquote':
            text_html = _runs_to_html(block['runs']) if block.get('runs') else None
            return mm._pq_html(block.get('text', ''), block.get('cite', ''),
                                int(block.get('style', 1)), block.get('accent') or '#c8a84a',
                                text_html=text_html)
        if t == 'headline':
            inner = _runs_to_html(block['runs']) if block.get('runs') else mm._h(block.get('text', ''))
            return f'<h1 class="art-title-h1" style="color:{block.get("color","#111")}">{inner}</h1>'
        if t == 'vector_shape':
            return _render_vector_shape(block)
        if t == 'image':
            src = block.get('src', '')
            cap = block.get('caption', '')
            credit = block.get('credit', '')
            credit_html = f'<cite class="photo-credit">{mm._h(credit)}</cite>' if credit else ''
            cap_html = f'<figcaption>{mm._h(cap)}{credit_html}</figcaption>' if (cap or credit_html) else ''
            cx = block.get('crop_x'); cy = block.get('crop_y')
            pos = f'object-position:{float(cx)}% {float(cy)}%;' if cx is not None and cy is not None else ''
            return (f'<figure class="art-fig" style="margin:0;height:100%">'
                    f'<img src="{mm._h(src)}" style="width:100%;height:100%;object-fit:cover;{pos}">{cap_html}</figure>')
        if t == 'text':
            inner = _runs_to_html(block['runs']) if block.get('runs') else mm._h(block.get('text', ''))
            return f'<div class="cols-1"><p>{inner}</p></div>'
        if t == 'meta_field':
            inner = _runs_to_html(block['runs']) if block.get('runs') else mm._h(block.get('text', ''))
            return f'<div class="cols-1"><p>{inner}</p></div>'
        if t == 'raw_page':
            return block.get('html', '')
        if t == 'bs_chrome':
            front = bool(block.get('front'))
            edition = block.get('edition', '')
            if front:
                inner = _bs_cols_grid([])
            else:
                inner = (f'<div class="bs-runhead"><span>{mm._h(block.get("pub_name",""))}</span>'
                         f'<span>{mm._h(edition)}</span></div>' + _bs_cols_grid([]))
                sec = (block.get('section') or '').strip()
                if sec:
                    inner += f'<div class="bs-side-label"><span>{mm._h(sec)}</span></div>'
            cg = block.get('col_grid')
            if cg:
                inner += ''.join(
                    f'<div class="bs-col-rule" style="left:{cg["side_margin"] + c * (cg["col_unit"] + cg["gutter"]) + cg["col_unit"] + cg["gutter"] / 2:.2f}mm;'
                    f'top:{cg["chrome_y"]:.2f}mm;height:{cg["content_h"]:.2f}mm"></div>'
                    for c in range(cg['cols'] - 1)
                )
            return _bs_sheet(inner, int(block.get('folio', 1)), int(block.get('total', 1)),
                              block.get('pub_name', ''), edition, front=front)
        if t == 'bs_masthead':
            pub = {'name': block.get('pub_name', ''), 'volume': block.get('volume', ''),
                   'issue_note': block.get('issue_note', ''), 'tagline': block.get('tagline', ''),
                   'website': block.get('website', ''), 'location': block.get('location', '')}
            edition = block.get('edition', '')
            mast = _bs_masthead(pub, edition, block.get('volume', ''), block.get('issue_note', ''),
                               block.get('egg_words'))
            note = f'<div class="bs-covernote">{_esc(block["cover_note"])}</div>' if block.get('cover_note') else ''
            index = block.get('toc_html') or ''
            return mast + note + index
        if t == 'bs_column':
            items = block.get('items') or []
            tmpl = block.get('template') or ''
            cls = f'bs-col {tmpl}'.strip()
            inner = f'<div class="{cls}">{"".join(it.get("html", "") for it in items)}</div>'
            scale = block.get('scale')
            if scale:
                ow, oh = block.get('orig_w', 0), block.get('orig_h', 0)
                return (f'<div style="width:{ow}mm;height:{oh}mm;'
                        f'transform:scale({scale});transform-origin:0 0">{inner}</div>')
            return inner
        if t == 'bs_divider':
            quote_html = block.get('quote_html') or ''
            inner = f'<div class="bs-divider-quote">{quote_html}</div>' if quote_html else ''
            cls = 'bs-divider' if quote_html else 'bs-divider bs-divider-plain'
            rule_html = ''
            if not quote_html:
                h = int(hashlib.md5(block.get('id', '').encode()).hexdigest()[:6], 16)
                thickness = 2 + (h % 4)
                height_pct = 40 + (h // 4 % 40)
                rule_html = (f'<div style="position:absolute;left:50%;top:{(100 - height_pct) // 2}%;'
                             f'height:{height_pct}%;width:{thickness}px;background:var(--accent);'
                             f'transform:translateX(-50%)"></div>')
            return f'<div class="{cls}">{inner}{rule_html}</div>'
        if t == 'bs_egg':
            return block.get('html', '')
        if t in ('photo_group', 'photo_page'):
            art = get_article(block.get('article_id'))
            if not art:
                return '<div class="hint">Article not found</div>'
            idx = int(block.get('idx', 1))
            accent = block.get('accent') or mm._art_accent(art, idx)
            semantic = mm._semantic_blocks(art.get('content') or '')
            photo_groups = [b for b in (semantic or [])
                             if b.get('type') == 'photo_group' and b.get('group_type', 'dump') != 'sequence']
            group_index = int(block.get('group_index', 0))
            if group_index >= len(photo_groups):
                return '<div class="hint">Photo-group not found at this index</div>'
            figs = [f for f in photo_groups[group_index].get('figures', []) if f.get('img')]
            chunks = mm._photo_group_chunks(figs, max_per_page=12)
            chunk_index = int(block.get('chunk_index', 0))
            if not chunks or chunk_index >= len(chunks):
                return '<div class="hint">No photo-group figures at this chunk</div>'
            page_num = int(block.get('page_num', chunk_index + 1))
            html = mm._pg_photo_group_full_page(art, idx, page_num, chunks[chunk_index], accent, cfg)
            return html or '<div class="hint">Empty photo-group page</div>'
        if t == 'logo':
            b64 = _logo_b64()
            if not b64:
                return '<div class="hint">Logo not found</div>'
            filt = 'filter:invert(1) brightness(1.9) contrast(0.9);' if block.get('invert') else ''
            return f'<img src="{b64}" style="width:100%;height:100%;object-fit:contain;{filt}">'
        if t == 'qr':
            pub = cfg.get('publication') or {}
            con = cfg.get('contact') or {}
            url = (block.get('url') or pub.get('website') or con.get('website') or '').strip()
            q = mm._qr_b64(url) if url else None
            if not q:
                return '<div class="hint">QR unavailable (no URL / qrcode not installed)</div>'
            label = block.get('label', '')
            label_html = (f'<div style="text-align:center;font-family:Georgia,serif;'
                           f'font-size:.75em;margin-top:4px">{mm._h(label)}</div>') if label else ''
            return f'<div style="text-align:center">' \
                   f'<img src="{q}" style="width:100%;height:auto;max-width:100%">{label_html}</div>'
        if t == 'generative_art':
            style = block.get('art_style', 'flow')
            try:
                seed = int(block.get('seed'))
            except (TypeError, ValueError):
                seed = abs(hash(block.get('id', 'seed'))) % 100000
            label = block.get('label', '')
            url = None
            if style == 'voronoi' and _voronoi_png:
                url = _voronoi_png(seed, label)
            elif style == 'spiral' and _spiral_icon:
                url = _spiral_icon(seed, [label] if label else [])
            elif _flow_png:
                url = _flow_png(seed, label)
            if not url:
                return '<div class="hint">Generative art unavailable</div>'
            b64 = mm._b64(url, STATIC_ROOT) or url
            return f'<img src="{b64}" style="width:100%;height:100%;object-fit:cover">'
        if t == 'copyright':
            pub = cfg.get('publication') or {}
            year = datetime.now(timezone.utc).year
            default_text = f"© {year} {pub.get('name', '')}".strip()
            if pub.get('tagline'):
                default_text += f". {pub['tagline']}"
            text = block.get('text_override') or default_text
            return (f'<div style="font-family:Georgia,serif;font-size:.72em;color:#555;'
                    f'text-align:{block.get("align","center")}">{mm._h(text)}</div>')
        if t == 'author_bio':
            aid = block.get('author_id')
            row = None
            if aid:
                db = get_db()
                try:
                    row = db.execute(
                        'SELECT name, bio, role, avatar_url, social_twitter, social_instagram '
                        'FROM authors WHERE id=?', (aid,)).fetchone()
                finally:
                    db.close()
            if not row:
                return '<div class="hint">No author selected</div>'
            avatar = row['avatar_url'] or ''
            av_b64 = mm._b64(avatar, STATIC_ROOT) if avatar else None
            avatar_html = (f'<img src="{av_b64}" style="width:56px;height:56px;border-radius:50%;'
                            f'object-fit:cover;float:left;margin-right:10px">') if av_b64 else ''
            socials = []
            if row['social_twitter']:
                socials.append(f"@{mm._h(row['social_twitter'])}")
            if row['social_instagram']:
                socials.append(f"@{mm._h(row['social_instagram'])}")
            social_html = (f'<div style="font-size:.8em;color:#888;margin-top:4px">'
                            f'{" · ".join(socials)}</div>') if socials else ''
            return (f'<div style="font-family:Georgia,serif;overflow:hidden">{avatar_html}'
                    f'<div style="font-weight:700;font-size:1.05em">{mm._h(row["name"] or "")}</div>'
                    f'<div style="font-size:.8em;color:#666;text-transform:uppercase;'
                    f'letter-spacing:.05em">{mm._h(row["role"] or "")}</div>'
                    f'<div style="font-size:.85em;margin-top:4px">{mm._h(row["bio"] or "")}</div>'
                    f'{social_html}</div>')
    except Exception as e:
        return f'<div style="border:1px solid #c00;color:#900;padding:4px;font:11px monospace">Render error ({t}): {mm._h(str(e))}</div>'
    return f'<div class="hint">Unknown block type: {mm._h(t)}</div>'


def _extra_css_for_layout(layout):
    seen, out = set(), []
    for page in (layout.get('pages') or []):
        for b in page.get('blocks', []):
            css = b.get('extra_css')
            if css and css not in seen:
                seen.add(css)
                out.append(css)
    return '\n'.join(out)


def layout_to_html(layout, editable=False):
    layout = _resolve_master_inheritance(layout)
    dims = layout.get('page') or PAGE_PRESETS['a4']
    hidden = {l['name'] for l in (layout.get('doc_layers') or []) if l.get('visible') is False}
    parts = [f'<style>{mm.CSS}</style>',
             f'<style>{_extra_css_for_layout(layout)}</style>',
             '<style>body{margin:0;background:#ddd}.dtp-block{position:absolute;overflow:hidden}'
             + ('.dtp-block{outline:1px dashed rgba(0,0,255,.35)}' if editable else '') + '</style>']
    for pi, page in enumerate(layout.get('pages') or []):
        page_h = page.get('h', dims['h'])
        style = f'width:{dims["w"]}mm;height:{page_h}mm;position:relative;margin:0 auto 12px;box-shadow:0 2px 10px rgba(0,0,0,.3);'
        parts.append(f'<div class="page" data-page="{pi}" style="page:p{pi};{style}">')
        for b in page.get('blocks', []):
            if b.get('layer', 'Default') in hidden:
                continue
            bstyle = f'left:{b.get("x",0)}mm;top:{b.get("y",0)}mm;width:{b.get("w",50)}mm;height:{b.get("h",30)}mm;'
            rot = b.get('rotation') or 0
            if rot:
                bstyle += f'transform:rotate({rot}deg);transform-origin:center center;'
            parts.append(f'<div class="dtp-block" data-block-id="{b["id"]}" data-page="{pi}" style="{bstyle}">'
                         f'{render_block_html(b)}</div>')
        parts.append('</div>')
    return _embed_static_images(''.join(parts))


def master_to_html(layout, master_name, editable=False):
    dims = layout.get('page') or PAGE_PRESETS['a4']
    hidden = {l['name'] for l in (layout.get('doc_layers') or []) if l.get('visible') is False}
    blocks = (layout.get('masters') or {}).get(master_name, {}).get('blocks', [])
    parts = [f'<style>{mm.CSS}</style>',
             f'<style>{_extra_css_for_layout(layout)}</style>',
             '<style>body{margin:0;background:#ddd}.dtp-block{position:absolute;overflow:hidden}'
             + ('.dtp-block{outline:1px dashed rgba(0,0,255,.35)}' if editable else '') + '</style>']
    style = f'width:{dims["w"]}mm;height:{dims["h"]}mm;position:relative;margin:0 auto 12px;box-shadow:0 2px 10px rgba(0,0,0,.3);'
    parts.append(f'<div class="page" data-page="0" style="page:p0;{style}">')
    for b in blocks:
        if b.get('layer', 'Default') in hidden:
            continue
        bstyle = f'left:{b.get("x",0)}mm;top:{b.get("y",0)}mm;width:{b.get("w",50)}mm;height:{b.get("h",30)}mm;'
        rot = b.get('rotation') or 0
        if rot:
            bstyle += f'transform:rotate({rot}deg);transform-origin:center center;'
        parts.append(f'<div class="dtp-block" data-block-id="{b["id"]}" data-page="0" style="{bstyle}">'
                     f'{render_block_html(b)}</div>')
    parts.append('</div>')
    return _embed_static_images(''.join(parts))


def _resolve_master_inheritance(layout):
    masters = layout.get('masters') or {}
    if not masters or not any(p.get('master') for p in (layout.get('pages') or [])):
        return layout
    layout = json.loads(json.dumps(layout))
    masters = layout.get('masters') or {}
    for page in (layout.get('pages') or []):
        master_name = page.get('master')
        if not master_name:
            continue
        master_blocks = masters.get(master_name, {}).get('blocks', [])
        if not master_blocks:
            continue
        master_by_id = {mb['id']: mb for mb in master_blocks}
        own_blocks = page.get('blocks', [])
        overridden_ids = {b['master_ref'] for b in own_blocks if b.get('master_ref')}
        resolved = []
        for mb in master_blocks:
            if mb['id'] in overridden_ids:
                continue
            bg = dict(mb)
            bg['_from_master'] = True
            resolved.append(bg)
        for b in own_blocks:
            if b.get('_from_master'):
                continue
            ref = b.get('master_ref')
            if ref and ref in master_by_id:
                merged = dict(master_by_id[ref])
                merged.update(b.get('overrides') or {})
                merged['id'] = b.get('id') or merged['id']
                merged['master_ref'] = ref
                merged['overrides'] = b.get('overrides') or {}
                resolved.append(merged)
            else:
                resolved.append(b)
        page['blocks'] = resolved
    return layout


_MAGAZINE_FONTS_URL = (
    'https://fonts.googleapis.com/css2?family=Playfair+Display:'
    'ital,wght@0,400;0,700;0,900;1,400;1,700&family=EB+Garamond:'
    'ital,wght@0,400;0,500;0,600;1,400&family=Montserrat:'
    'wght@300;400;600;700;800;900&family=Cormorant+Garamond:'
    'ital,wght@0,300;0,600;1,300;1,600&family=IBM+Plex+Mono:'
    'wght@300;400;500&display=swap')


def _measure_box_height_mm(pw_page, block, width_mm):
    html = render_block_html(block)
    extra_css = block.get('extra_css', '')
    doc = (f'<!doctype html><html><head><style>{mm.CSS}</style><style>{extra_css}</style>'
           f'<style>body{{margin:0}}#box{{width:{width_mm}mm}}</style></head>'
           f'<body><div id="box">{html}</div></body></html>')
    try:
        pw_page.set_content(doc, wait_until='domcontentloaded', timeout=8000)
    except Exception:
        pw_page.set_content(doc, wait_until='commit', timeout=8000)
    h_px = pw_page.eval_on_selector('#box', 'el => el.scrollHeight')
    return h_px / 3.7795275591


def _resolve_fit_blocks(layout):
    has_fit = any(b.get('fit_box') or b.get('fit_text')
                  for p in (layout.get('pages') or []) for b in p.get('blocks', []))
    if not has_fit:
        return layout
    layout = json.loads(json.dumps(layout))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return layout
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            pg = browser.new_page()
            for layout_page in (layout.get('pages') or []):
                for block in layout_page.get('blocks', []):
                    if block.get('fit_box'):
                        h = _measure_box_height_mm(pg, block, block.get('w', 50))
                        block['h'] = max(5.0, h)
                    elif block.get('fit_text'):
                        lo, hi = 6.0, 48.0
                        target_h, width = block.get('h', 30), block.get('w', 50)
                        best = lo
                        for _ in range(6):
                            mid = (lo + hi) / 2
                            trial = dict(block); trial['style_font_size'] = mid
                            h = _measure_box_height_mm(pg, trial, width)
                            if h <= target_h:
                                best = mid; lo = mid
                            else:
                                hi = mid
                        block['style_font_size'] = round(best, 1)
            browser.close()
    except Exception as e:
        print(f'[dtp_engine] fit-text/fit-box resolve failed: {e}')
    return layout


def _plain_text_from_html(html):
    return re.sub(r'<[^>]+>', '', html or '')


def _split_text_to_fit(pw_page, block, text):
    words = text.split(' ')
    if not words:
        return text, ''
    lo, hi, best = 0, len(words), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = dict(block)
        trial['sem'] = dict(block.get('sem') or {})
        trial['sem']['html'] = f'<p>{mm._h(" ".join(words[:mid]))}</p>' if mid else '<p></p>'
        h = _measure_box_height_mm(pw_page, trial, block.get('w', 50))
        if h <= block.get('h', 30):
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return ' '.join(words[:best]), ' '.join(words[best:])


def _build_frame_chains(layout, block_index):
    chains = []
    covered = set()
    for ch in (layout.get('frame_chains') or []):
        ids = [i for i in (ch.get('frame_ids') or []) if i in block_index]
        if len(ids) >= 2:
            chains.append(ids)
            covered.update(ids)
    targets = {b['link_next'] for b in block_index.values() if b.get('link_next')}
    heads = [b for b in block_index.values()
             if b.get('link_next') and b['id'] not in targets and b['id'] not in covered]
    for head in heads:
        chain, seen, cur = [head['id']], {head['id']}, head
        while cur and cur.get('link_next') and cur['link_next'] not in seen and cur['link_next'] not in covered:
            nxt_id = cur['link_next']
            chain.append(nxt_id)
            seen.add(nxt_id)
            cur = block_index.get(nxt_id)
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def _resolve_linked_frames(layout):
    block_index = {b['id']: b for p in (layout.get('pages') or []) for b in p.get('blocks', [])}
    if not any(b.get('link_next') for b in block_index.values()) and not layout.get('frame_chains'):
        return layout
    layout = json.loads(json.dumps(layout))
    block_index = {b['id']: b for p in (layout.get('pages') or []) for b in p.get('blocks', [])}
    chains = _build_frame_chains(layout, block_index)
    if not chains:
        return layout
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return layout
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            pg = browser.new_page()
            for chain in chains:
                for cur_id, nxt_id in zip(chain, chain[1:]):
                    cur = block_index.get(cur_id); nxt = block_index.get(nxt_id)
                    if not cur or not nxt:
                        continue
                    if (cur.get('sem') or {}).get('type') != 'paragraph':
                        continue
                    if (nxt.get('sem') or {}).get('type') != 'paragraph':
                        break
                    full_text = _plain_text_from_html(cur['sem'].get('html', ''))
                    h = _measure_box_height_mm(pg, cur, cur.get('w', 50))
                    if h <= cur.get('h', 30):
                        continue
                    fitting, remainder = _split_text_to_fit(pg, cur, full_text)
                    cur['sem']['html'] = f'<p>{mm._h(fitting)}</p>'
                    nxt['sem']['html'] = f'<p>{mm._h(remainder)}</p>'
            browser.close()
    except Exception as e:
        print(f'[dtp_engine] linked-frame resolve failed: {e}')
    return layout


def _resolve_bs_column_overflow(layout):
    block_index = {b['id']: b for p in (layout.get('pages') or []) for b in p.get('blocks', [])}
    bs_columns = {bid: b for bid, b in block_index.items() if b.get('type') == 'bs_column'}
    if not bs_columns:
        return layout
    layout = json.loads(json.dumps(layout))
    block_index = {b['id']: b for p in (layout.get('pages') or []) for b in p.get('blocks', [])}
    bs_columns = {bid: b for bid, b in block_index.items() if b.get('type') == 'bs_column'}
    targets = {b['link_next'] for b in bs_columns.values() if b.get('link_next')}
    heads = [b for b in bs_columns.values() if b['id'] not in targets]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return layout
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            pg = browser.new_page()
            for head in heads:
                cur = head
                seen = set()
                while cur and cur['id'] not in seen:
                    seen.add(cur['id'])
                    nxt = bs_columns.get(cur.get('link_next'))
                    items = cur.get('items') or []
                    if items:
                        h = _measure_box_height_mm(pg, cur, cur.get('w', 50))
                        if h > cur.get('h', 30):
                            if nxt:
                                moved = []
                                while h > cur.get('h', 30):
                                    idx = next((i for i in range(len(items) - 1, -1, -1)
                                                if not items[i].get('jump')), None)
                                    if idx is None:
                                        break
                                    moved.insert(0, items.pop(idx))
                                    cur['items'] = items
                                    h = _measure_box_height_mm(pg, cur, cur.get('w', 50)) if items else 0
                                if moved:
                                    nxt['items'] = moved + (nxt.get('items') or [])
                    cur = nxt
            browser.close()
    except Exception as e:
        print(f'[dtp_engine] broadsheet column-overflow resolve failed: {e}')
    return layout


def resolve_layout(layout):
    layout = _resolve_master_inheritance(layout)
    return _resolve_fit_blocks(_resolve_bs_column_overflow(_resolve_linked_frames(layout)))


def render_html(layout, title=None, kind=None):
    layout = resolve_layout(layout)
    head = [f'<meta charset="utf-8">']
    if title:
        head.append(f'<title>{mm._h(title)}</title>')
    if kind == 'magazine':
        head.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
        head.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
        head.append(f'<link href="{_MAGAZINE_FONTS_URL}" rel="stylesheet">')
    return f'<!doctype html><html><head>{"".join(head)}</head><body>{layout_to_html(layout, editable=False)}</body></html>'


def render_pdf(layout):
    layout = resolve_layout(layout)
    dims = layout.get('page') or PAGE_PRESETS['a4']
    per_page_rules = ''.join(
        f'@page p{pi}{{size:{dims["w"]}mm {p.get("h", dims["h"])}mm;margin:0}}\n'
        for pi, p in enumerate(layout.get('pages') or []))
    per_page_fit = ''.join(
        f'.page[data-page="{pi}"]{{height:{p.get("h", dims["h"]) - 0.4}mm!important;'
        f'box-sizing:border-box!important;overflow:hidden!important;'
        f'page-break-after:auto!important;break-after:auto!important}}\n'
        for pi, p in enumerate(layout.get('pages') or []))
    html = (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>@page{{size:{dims["w"]}mm {dims["h"]}mm;margin:0}}\n{per_page_rules}'
            f'.page{{box-shadow:none!important;margin:0!important}}\n'
            f'.bs-sheet{{page-break-after:auto!important;break-after:auto!important}}\n'
            f'html,body{{margin:0!important;padding:0!important}}\n'
            f'{per_page_fit}</style></head>'
            f'<body>{layout_to_html(layout, editable=False)}'
            f'<style>@page{{margin:0}}\n{per_page_rules}</style>'
            f'</body></html>')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, 'Playwright not installed'
    try:
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                b = p.chromium.launch(headless=True)
            pg = b.new_page()
            try:
                pg.set_content(html, wait_until='load', timeout=30000)
            except Exception:
                pass
            pg.set_default_timeout(300000)
            pdf = pg.pdf(prefer_css_page_size=True, print_background=True,
                         margin={'top': '0mm', 'right': '0mm', 'bottom': '0mm', 'left': '0mm'})
            b.close()
        return pdf, None
    except Exception as e:
        return None, str(e)


_MM_TO_PT = 72.0 / 25.4


def _sla_esc(s):
    return _esc(str(s if s is not None else ''), quote=True)


def _sla_plain_text(b):
    t = b.get('type')
    if t == 'sem_para':
        sem = b.get('sem') or {}
        if sem.get('type') == 'quote':
            txt = sem.get('text', '')
            return f'{txt}\n— {sem["cite"]}' if sem.get('cite') else txt
        return BeautifulSoup(sem.get('html', '') or '', 'html.parser').get_text()
    if t == 'bs_masthead':
        head = b.get('head') or {}
        parts = [head.get('kicker', ''), head.get('title', ''), head.get('deck', ''), head.get('byline', '')]
        return '\n'.join(p for p in parts if p)
    if t == 'bs_column':
        return BeautifulSoup(''.join(it.get('html', '') for it in (b.get('items') or [])), 'html.parser').get_text()
    if t == 'raw_page':
        return BeautifulSoup(b.get('html', '') or '', 'html.parser').get_text()
    if t in ('copyright',):
        return b.get('text_override') or '(publication copyright line)'
    if t == 'author_bio':
        return '(author bio)'
    if t in ('logo', 'qr', 'generative_art'):
        return f'[{t}]'
    for k in ('text', 'caption', 'label'):
        if b.get(k):
            return b[k]
    return ''


def _sla_block_runs(b):
    if b.get('runs'):
        return b['runs']
    if b.get('type') == 'sem_para':
        sem = b.get('sem') or {}
        if sem.get('type') == 'paragraph' and sem.get('runs'):
            return sem['runs']
    return None


def _sla_run_font(r):
    bold, italic = bool(r.get('bold')), bool(r.get('italic'))
    if bold and italic:
        return 'Arial Bold Italic'
    if bold:
        return 'Arial Bold'
    if italic:
        return 'Arial Italic'
    return 'Arial Regular'


def _sla_runs_to_story(runs, fontsize):
    story = []
    for r in (runs or []):
        text = r.get('text', '')
        if not text:
            continue
        font = _sla_esc(_sla_run_font(r))
        feat = ' FEATURES="underline"' if r.get('underline') else ''
        for i, line in enumerate(text.split('\n')):
            if i:
                story.append('<para/>\n')
            if line:
                story.append(f'<ITEXT FONT="{font}" FONTSIZE="{fontsize}"{feat} CH="{_sla_esc(line)}"/>\n')
    return ''.join(story)


_BEZIER_KAPPA = 0.5522847498307936


def _sla_ellipse_bezier_path(w_pt, h_pt):
    cx, cy, rx, ry = w_pt / 2, h_pt / 2, w_pt / 2, h_pt / 2
    kx, ky = rx * _BEZIER_KAPPA, ry * _BEZIER_KAPPA
    e, s, w_, n = (cx + rx, cy), (cx, cy + ry), (cx - rx, cy), (cx, cy - ry)
    return (
        f'M{e[0]:.3f} {e[1]:.3f} '
        f'C{e[0]:.3f} {e[1]+ky:.3f} {s[0]+kx:.3f} {s[1]:.3f} {s[0]:.3f} {s[1]:.3f} '
        f'C{s[0]-kx:.3f} {s[1]:.3f} {w_[0]:.3f} {w_[1]+ky:.3f} {w_[0]:.3f} {w_[1]:.3f} '
        f'C{w_[0]:.3f} {w_[1]-ky:.3f} {n[0]-kx:.3f} {n[1]:.3f} {n[0]:.3f} {n[1]:.3f} '
        f'C{n[0]+kx:.3f} {n[1]:.3f} {e[0]:.3f} {e[1]-ky:.3f} {e[0]:.3f} {e[1]:.3f} Z'
    )


def _svg_path_scale_to_pt(svg_path, w_mm, h_mm, w_pt, h_pt):
    cmds = _parse_svg_path_commands(svg_path)
    out = []
    closed = False
    for cmd, nums in cmds:
        if cmd == 'Z':
            out.append('Z')
            closed = True
            continue
        pairs = [(nums[i] / w_mm * w_pt, nums[i + 1] / h_mm * h_pt) for i in range(0, len(nums), 2)]
        coord_str = ' '.join(f'{x:.3f} {y:.3f}' for x, y in pairs)
        out.append(f'{cmd}{coord_str}')
    return ' '.join(out), closed


def _sla_shape_path_pt(b, w_pt, h_pt):
    shape = b.get('shape', 'rect')
    w_mm = max(0.001, b.get('w', 50)); h_mm = max(0.001, b.get('h', 30))

    def scale(pt):
        x, y = pt
        return (float(x) / w_mm) * w_pt, (float(y) / h_mm) * h_pt

    if b.get('svg_path'):
        return _svg_path_scale_to_pt(b['svg_path'], w_mm, h_mm, w_pt, h_pt)
    if shape in ('polygon', 'polyline') and b.get('points'):
        pts = [scale(p) for p in b['points']]
        d = f'M{pts[0][0]:.3f} {pts[0][1]:.3f} ' + ' '.join(f'L{x:.3f} {y:.3f}' for x, y in pts[1:])
        closed = (shape == 'polygon')
        return (d + (' Z' if closed else '')), closed
    if shape == 'ellipse':
        return _sla_ellipse_bezier_path(w_pt, h_pt), True
    return f'M0 0 L{w_pt:.3f} 0 L{w_pt:.3f} {h_pt:.3f} L0 {h_pt:.3f} Z', True


def _sla_link_annotation_object(x_pt, y_pt, w_pt, h_pt, page_num, item_id, href):
    common = (f'XPOS="{x_pt:.3f}" YPOS="{y_pt:.3f}" OwnPage="{page_num}" ItemID="{item_id}" '
              f'WIDTH="{w_pt:.3f}" HEIGHT="{h_pt:.3f}" ROT="0" FRTYPE="0" CLIPEDIT="0" PWIDTH="1" PLINEART="1" '
              f'LOCALSCX="1" LOCALSCY="1" LOCALX="0" LOCALY="0" LOCALROT="0" PICART="1" SCALETYPE="1" RATIO="1" '
              f'COLUMNS="1" COLGAP="0" AUTOTEXT="0" EXTRA="0" TEXTRA="0" BEXTRA="0" REXTRA="0" VAlign="0" FLOP="0" '
              f'PLTSHOW="0" BASEOF="0" textPathType="0" textPathFlipped="0" '
              f'path="M0 0 L{w_pt:.3f} 0 L{w_pt:.3f} {h_pt:.3f} L0 {h_pt:.3f} Z" '
              f'copath="M0 0 L{w_pt:.3f} 0 L{w_pt:.3f} {h_pt:.3f} L0 {h_pt:.3f} Z" '
              f'gXpos="0" gYpos="0" gWidth="{w_pt:.3f}" gHeight="{h_pt:.3f}" LAYER="0" NEXTITEM="-1" BACKITEM="-1"')
    ann = (f'Annotation="1" AnnotationType="11" AnnotationAction="" AnnotationActionE="" AnnotationActionX="" '
           f'AnnotationActionD="" AnnotationActionFo="" AnnotationActionBl="" AnnotationActionK="" '
           f'AnnotationActionF="" AnnotationActionV="" AnnotationActionC="" AnnotationActionType="8" '
           f'AnnotationExtern="{_sla_esc(href)}" AnnotationCount="0" AnnotationToolTip="" '
           f'AnnotationBorderWidth="0" AnnotationBorderStyle="0" AnnotationFeed="1" AnnotationFlag="0" '
           f'AnnotationFont="4" AnnotationFormat="0" AnnotationRollOver="" AnnotationDown="" '
           f'AnnotationVisible="0" AnnotationMaxChar="-1" AnnotationIsCheck="0" '
           f'AnnotationAdditionalAction="0" AnnotationCheckStyle="0" AnnotationBorderColor="" '
           f'AnnotationHTML="0" AnnotationUseIcons="0" AnnotationTextPosition="1" AnnotationScaleWidth="0" '
           f'AnnotationIcon="0" AnnotationTextOpen="0"')
    return f'<PAGEOBJECT PTYPE="4" PCOLOR="None" PCOLOR2="None" {common} {ann}>\n<StoryText>\n</StoryText>\n</PAGEOBJECT>\n'


def _sla_link_annotations(b, x_pt, y_pt, w_pt, h_pt, page_num, next_id):
    runs = _sla_block_runs(b)
    if not runs:
        return ''
    total = sum(len(r.get('text', '')) for r in runs) or 1
    out = []
    pos = 0
    for r in runs:
        text = r.get('text', '')
        n = len(text)
        href = r.get('href')
        if href and n:
            frac0, frac1 = pos / total, (pos + n) / total
            ly = y_pt + frac0 * h_pt
            lh = max(2.0, (frac1 - frac0) * h_pt)
            out.append(_sla_link_annotation_object(x_pt, ly, w_pt, lh, page_num, next_id(), href))
        pos += n
    return ''.join(out)


def _sla_pageobject(b, ox_pt, oy_pt, item_id, page_num, next_item=-1, back_item=-1, link_id_gen=None):
    x = ox_pt + b.get('x', 0) * _MM_TO_PT
    y = oy_pt + b.get('y', 0) * _MM_TO_PT
    w = max(1.0, b.get('w', 50) * _MM_TO_PT)
    h = max(1.0, b.get('h', 30) * _MM_TO_PT)
    rot = b.get('rotation') or 0

    if b.get('type') == 'vector_shape':
        path, closed = _sla_shape_path_pt(b, w, h)
        ptype = '6' if closed else '7'
        fill = _sla_esc(b.get('fill')) if b.get('fill') and b.get('fill') != 'none' else 'None'
        stroke = _sla_esc(b.get('stroke')) if b.get('stroke') else 'Black'
        common = (f'XPOS="{x:.3f}" YPOS="{y:.3f}" OwnPage="{page_num}" ItemID="{item_id}" WIDTH="{w:.3f}" HEIGHT="{h:.3f}" '
                  f'ROT="{rot}" FRTYPE="0" CLIPEDIT="0" PWIDTH="{float(b.get("stroke_width", 1)):.3f}" PLINEART="1" '
                  f'LOCALSCX="1" LOCALSCY="1" LOCALX="0" LOCALY="0" LOCALROT="0" PICART="1" SCALETYPE="1" RATIO="1" '
                  f'COLUMNS="1" COLGAP="0" AUTOTEXT="0" EXTRA="0" TEXTRA="0" BEXTRA="0" REXTRA="0" VAlign="0" FLOP="0" '
                  f'PLTSHOW="0" BASEOF="0" textPathType="0" textPathFlipped="0" path="{path}" copath="{path}" '
                  f'gXpos="0" gYpos="0" gWidth="{w:.3f}" gHeight="{h:.3f}" LAYER="0" NEXTITEM="{next_item}" BACKITEM="{back_item}"')
        return f'<PAGEOBJECT PTYPE="{ptype}" PCOLOR="{fill}" PCOLOR2="{stroke}" {common}>\n</PAGEOBJECT>\n'

    path = f'M0 0 L{w:.3f} 0 L{w:.3f} {h:.3f} L0 {h:.3f} L0 0 Z'
    common = (f'XPOS="{x:.3f}" YPOS="{y:.3f}" OwnPage="{page_num}" ItemID="{item_id}" WIDTH="{w:.3f}" HEIGHT="{h:.3f}" '
              f'ROT="{rot}" FRTYPE="0" CLIPEDIT="0" PWIDTH="1" PLINEART="1" LOCALSCX="1" LOCALSCY="1" '
              f'LOCALX="0" LOCALY="0" LOCALROT="0" PICART="1" SCALETYPE="1" RATIO="1" COLUMNS="1" COLGAP="0" '
              f'AUTOTEXT="0" EXTRA="0" TEXTRA="0" BEXTRA="0" REXTRA="0" VAlign="0" FLOP="0" PLTSHOW="0" '
              f'BASEOF="0" textPathType="0" textPathFlipped="0" path="{path}" copath="{path}" '
              f'gXpos="0" gYpos="0" gWidth="{w:.3f}" gHeight="{h:.3f}" LAYER="0" NEXTITEM="{next_item}" BACKITEM="{back_item}"')
    if b.get('type') == 'image':
        pfile = _sla_esc(b.get('src') or '')
        return (f'<PAGEOBJECT PTYPE="2" PCOLOR="None" {common} PFILE="{pfile}">\n'
                f'</PAGEOBJECT>\n')
    fontsize = 24 if b.get('type') in ('headline', 'bs_masthead') else 12
    runs = _sla_block_runs(b)
    if runs:
        story_xml = _sla_runs_to_story(runs, fontsize)
        if story_xml.strip():
            links_xml = _sla_link_annotations(b, x, y, w, h, page_num, link_id_gen) if link_id_gen else ''
            return (f'<PAGEOBJECT PTYPE="4" PCOLOR="None" {common}>\n'
                    f'<StoryText>\n{story_xml}</StoryText>\n'
                    f'</PAGEOBJECT>\n') + links_xml
    text = _sla_plain_text(b)
    if not text.strip():
        return f'<PAGEOBJECT PTYPE="6" PCOLOR="None" PCOLOR2="Black" {common}>\n</PAGEOBJECT>\n'
    story = []
    for i, line in enumerate(text.split('\n')):
        if i:
            story.append('<para/>\n')
        if line:
            story.append(f'<ITEXT FONTSIZE="{fontsize}" CH="{_sla_esc(line)}"/>\n')
    return (f'<PAGEOBJECT PTYPE="4" PCOLOR="None" {common}>\n'
            f'<StoryText>\n{"".join(story)}</StoryText>\n'
            f'</PAGEOBJECT>\n')


def layout_to_sla(layout, doc_name='Untitled'):
    dims = layout.get('page') or PAGE_PRESETS['a4']
    pages = layout.get('pages') or [{'blocks': []}]
    page_w_pt = dims['w'] * _MM_TO_PT
    margin = dims.get('margin') or [15, 15, 15, 15]
    bt, br, bb, bl = (m * _MM_TO_PT for m in margin)
    scratch = 14.173
    preset_name = next((k for k, v in PAGE_PRESETS.items() if v == dims), None)
    page_size_name = {'a4': 'A4', 'letter': 'Letter', 'tabloid': 'Tabloid'}.get(preset_name, 'Custom')

    block_index = {b['id']: b for p in pages for b in (p.get('blocks') or [])}
    item_ids, _next_id = {}, 1000000
    for p in pages:
        for b in (p.get('blocks') or []):
            _next_id += 1
            item_ids[b['id']] = _next_id
    next_item_of, back_item_of = {}, {}
    for chain in _build_frame_chains(layout, block_index):
        for cur_id, nxt_id in zip(chain, chain[1:]):
            next_item_of[cur_id] = item_ids.get(nxt_id, -1)
            back_item_of[nxt_id] = item_ids.get(cur_id, -1)

    _link_id_cell = [_next_id]

    def _next_link_id():
        _link_id_cell[0] += 1
        return _link_id_cell[0]

    page_xml, obj_xml, master_xml = [], [], []
    oy = scratch
    for pi, page in enumerate(pages):
        page_h_pt = page.get('h', dims['h']) * _MM_TO_PT
        ox = scratch
        page_xml.append(
            f'<PAGE PAGEXPOS="{ox:.3f}" PAGEYPOS="{oy:.3f}" PAGEWIDTH="{page_w_pt:.3f}" PAGEHEIGHT="{page_h_pt:.3f}" '
            f'BORDERLEFT="{bl:.3f}" BORDERRIGHT="{br:.3f}" BORDERTOP="{bt:.3f}" BORDERBOTTOM="{bb:.3f}" NUM="{pi}" '
            f'NAM="" MNAM="Normal" Size="{page_size_name}" Orientation="0" LEFT="0" PRESET="0" VerticalGuides="" '
            f'HorizontalGuides="" AGhorizontalAutoGap="0" AGverticalAutoGap="0" AGhorizontalAutoCount="0" '
            f'AGverticalAutoCount="0" AGhorizontalAutoRefer="0" AGverticalAutoRefer="0" AGSelection="0 0 0 0" '
            f'pageEffectDuration="1" pageViewDuration="1" effectType="0" Dm="0" M="0" Di="0"/>\n')
        for b in page.get('blocks') or []:
            obj_xml.append(_sla_pageobject(b, ox, oy, item_ids[b['id']], pi,
                                            next_item=next_item_of.get(b['id'], -1),
                                            back_item=back_item_of.get(b['id'], -1),
                                            link_id_gen=_next_link_id))
        oy += page_h_pt + scratch

    master_h_pt = dims['h'] * _MM_TO_PT
    master_xml.append(
        f'<MASTERPAGE PAGEXPOS="{scratch:.3f}" PAGEYPOS="{scratch:.3f}" PAGEWIDTH="{page_w_pt:.3f}" '
        f'PAGEHEIGHT="{master_h_pt:.3f}" BORDERLEFT="{bl:.3f}" BORDERRIGHT="{br:.3f}" BORDERTOP="{bt:.3f}" '
        f'BORDERBOTTOM="{bb:.3f}" NUM="0" NAM="Normal" MNAM="" Size="{page_size_name}" Orientation="0" LEFT="0" '
        f'PRESET="0" VerticalGuides="" HorizontalGuides="" AGhorizontalAutoGap="0" AGverticalAutoGap="0" '
        f'AGhorizontalAutoCount="0" AGverticalAutoCount="0" AGhorizontalAutoRefer="0" AGverticalAutoRefer="0" '
        f'AGSelection="0 0 0 0" pageEffectDuration="1" pageViewDuration="1" effectType="0" Dm="0" M="0" Di="0"/>\n')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<SCRIBUSUTF8NEW Version="1.5.2.svn">
    <DOCUMENT ANZPAGES="{len(pages)}" PAGEWIDTH="{page_w_pt:.3f}" PAGEHEIGHT="{master_h_pt:.3f}" BORDERLEFT="{bl:.3f}" BORDERRIGHT="{br:.3f}" BORDERTOP="{bt:.3f}" BORDERBOTTOM="{bb:.3f}" PRESET="0" BleedTop="0" BleedLeft="0" BleedRight="0" BleedBottom="0" ORIENTATION="0" PAGESIZE="{page_size_name}" FIRSTNUM="1" BOOK="0" AUTOSPALTEN="1" ABSTSPALTEN="11" UNITS="0" DFONT="Arial Regular" DSIZE="12" DCOL="1" DGAP="0" TabFill="" TabWidth="36" AUTHOR="" COMMENTS="Exported from Voice Express DTP" KEYWORDS="" PUBLISHER="" DOCDATE="" DOCTYPE="" DOCFORMAT="" DOCIDENT="" DOCSOURCE="" DOCLANGINFO="" DOCRELATION="" DOCCOVER="" DOCRIGHTS="" DOCCONTRIB="" TITLE="{_sla_esc(doc_name)}" SUBJECT="" VHOCH="33" VHOCHSC="66" VTIEF="33" VTIEFSC="66" VKAPIT="75" BASEGRID="14.4" BASEO="0" AUTOL="100" UnderlinePos="-1" UnderlineWidth="-1" StrikeThruPos="-1" StrikeThruWidth="-1" GROUPC="1" HCMS="0" DPSo="0" DPSFo="0" DPuse="0" DPgam="0" DPbla="1" DISc="1" DIIm="0" ALAYER="0" LANGUAGE="en_GB" MINWORDLEN="3" HYCOUNT="2" AUTOMATIC="1" AUTOCHECK="0" GUIDELOCK="0" SnapToGuides="1" SnapToGrid="0" SnapToElement="0" MINGRID="20.001" MAJGRID="100.001" SHOWGRID="0" SHOWGUIDES="1" showcolborders="1" previewMode="0" SHOWFRAME="1" SHOWControl="0" SHOWLAYERM="0" SHOWMARGIN="1" SHOWBASE="0" SHOWPICT="1" SHOWLINK="0" rulerMode="1" showrulers="1" showBleed="1" rulerXoffset="0" rulerYoffset="0" GuideRad="10" GRAB="4" AutoSave="1" AutoSaveTime="600000" AutoSaveCount="5" AutoSaveKeep="0" AUtoSaveInDocDir="1" AutoSaveDir="" ScratchBottom="14.173" ScratchLeft="14.173" ScratchRight="14.173" ScratchTop="14.173" GapHorizontal="14.173" GapVertical="14.173" StartArrow="0" EndArrow="0" PEN="Black" BRUSH="None" PENLINE="Black" PENTEXT="Black" StrokeText="Black" TextBackGround="None" TextLineColor="None" TextBackGroundShade="100" TextLineShade="100" TextPenShade="100" TextStrokeShade="100" STIL="1" STILLINE="1" WIDTH="1" WIDTHLINE="1" PENSHADE="100" LINESHADE="100" BRUSHSHADE="100" CPICT="None" PICTSHADE="100" CSPICT="None" PICTSSHADE="100" PICTSCX="1" PICTSCY="1" PSCALE="1" PASPECT="1" EmbeddedPath="0" HalfRes="1" dispX="10.001" dispY="10.001" constrain="15" MINORC="#00ff00" MAJORC="#00ff00" GuideC="#000080" BaseC="#c0c0c0" renderStack="0 1 2 3 4" GridType="0" PAGEC="#ffffff" MARGC="#0000ff" RANDF="0">
        <STYLE NAME="Default Paragraph Style" DefaultStyle="1" ALIGN="0" LINESPMode="0" LINESP="15" INDENT="0" RMARGIN="0" FIRST="0" VOR="0" NACH="0" ParagraphEffectOffset="0" DROP="0" DROPLIN="2" Bullet="0" Numeration="0" BCOLOR="None" BSHADE="100"/>
        <LAYERS NUMMER="0" LEVEL="0" NAME="Background" SICHTBAR="1" DRUCKEN="1" EDIT="1" SELECT="0" FLOW="1" TRANS="1" BLEND="0" OUTL="0" LAYERC="#000000"/>
        <Printer firstUse="1" toFile="0" useAltPrintCommand="0" outputSeparations="0" useSpotColors="0" useColor="0" mirrorH="0" mirrorV="0" useICC="0" doGCR="0" doClip="0" setDevParam="0" useDocBleeds="0" cropMarks="0" bleedMarks="0" registrationMarks="0" colorMarks="0" includePDFMarks="0" PSLevel="0" PDLanguage="0" markLength="0" markOffset="0" BleedTop="0" BleedLeft="0" BleedRight="0" BleedBottom="0" printer="" filename="" separationName="" printerCommand=""/>
        <DocItemAttributes/>
        <TablesOfContents/>
        <NotesFrames/>
        <PageSets>
            <Set Name="Single Page" FirstPage="0" Rows="1" Columns="1"/>
        </PageSets>
        <Sections>
            <Section Number="0" Name="0" From="0" To="{len(pages)}" Type="Type_1_2_3" Start="1" Reversed="0" Active="1" FillChar="0" FieldWidth="0"/>
        </Sections>
{''.join(master_xml)}{''.join(page_xml)}{''.join(obj_xml)}    </DOCUMENT>
</SCRIBUSUTF8NEW>
'''


def _sla_float(el, name, default=0.0):
    v = el.get(name)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _sla_story_text(obj):
    story = obj.find('StoryText')
    if story is None:
        return ''
    parts = []
    for child in story:
        if child.tag == 'ITEXT':
            parts.append(child.get('CH') or '')
        elif child.tag in ('para', 'trail'):
            parts.append('\n')
    return ''.join(parts).strip('\n')


def _sla_font_style(font_name):
    f = (font_name or '').lower()
    return ('bold' in f, 'italic' in f)


def _sla_runs_from_story(obj):
    story = obj.find('StoryText')
    if story is None:
        return None
    runs = []
    for child in story:
        if child.tag == 'ITEXT':
            ch = child.get('CH') or ''
            if not ch:
                continue
            bold, italic = _sla_font_style(child.get('FONT'))
            run = {'text': ch}
            if bold:
                run['bold'] = True
            if italic:
                run['italic'] = True
            if 'underline' in (child.get('FEATURES') or ''):
                run['underline'] = True
            runs.append(run)
        elif child.tag in ('para', 'trail'):
            runs.append({'text': '\n'})
    return runs or None


def _sla_apply_href_range(runs, start_char, end_char, href):
    if start_char >= end_char:
        return runs
    out = []
    pos = 0
    for r in runs:
        text = r.get('text', '')
        n = len(text)
        r_start, r_end = pos, pos + n
        pos = r_end
        lo, hi = max(r_start, start_char), min(r_end, end_char)
        if lo >= hi:
            out.append(r)
            continue
        if lo > r_start:
            out.append({**r, 'text': text[:lo - r_start]})
        mid = dict(r)
        mid['text'] = text[lo - r_start:hi - r_start]
        mid['href'] = href
        out.append(mid)
        if hi < r_end:
            out.append({**r, 'text': text[hi - r_start:]})
    return out


_SLA_PATH_CMD_RE = re.compile(r'([ML])\s*([-\d.]+)\s+([-\d.]+)')


def _sla_parse_path_points(path):
    pts = [(float(m.group(2)), float(m.group(3))) for m in _SLA_PATH_CMD_RE.finditer(path or '')]
    closed = (path or '').strip().upper().endswith('Z')
    return pts, closed


def _sla_path_to_local_svg(path, w_pt, h_pt, w_mm, h_mm):
    cmds = _parse_svg_path_commands(path)
    if not cmds:
        return None, False, False
    has_curve = any(c in ('C', 'Q') for c, _ in cmds)
    closed = any(c == 'Z' for c, _ in cmds)
    out = []
    for cmd, nums in cmds:
        if cmd == 'Z':
            out.append('Z')
            continue
        pairs = [(nums[i] / w_pt * w_mm, nums[i + 1] / h_pt * h_mm) for i in range(0, len(nums), 2)]
        coord_str = ' '.join(f'{x:.3f} {y:.3f}' for x, y in pairs)
        out.append(f'{cmd}{coord_str}')
    return ' '.join(out), has_curve, closed


def sla_to_layout(sla_bytes):
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(sla_bytes)
    except ET.ParseError as e:
        raise ValueError(f'Not a well-formed .sla/XML file: {e}')
    doc = root.find('DOCUMENT')
    if doc is None:
        raise ValueError('Not a Scribus document (no <DOCUMENT> element found)')

    page_w_mm = _sla_float(doc, 'PAGEWIDTH', 210 * _MM_TO_PT) / _MM_TO_PT
    page_h_mm = _sla_float(doc, 'PAGEHEIGHT', 297 * _MM_TO_PT) / _MM_TO_PT
    margin = [_sla_float(doc, 'BORDERTOP') / _MM_TO_PT, _sla_float(doc, 'BORDERRIGHT') / _MM_TO_PT,
              _sla_float(doc, 'BORDERBOTTOM') / _MM_TO_PT, _sla_float(doc, 'BORDERLEFT') / _MM_TO_PT]

    page_els = sorted(doc.findall('PAGE'), key=lambda p: _sla_float(p, 'NUM', 0))
    if not page_els:
        raise ValueError('No <PAGE> elements found')
    pages_meta = [{'num': int(_sla_float(p, 'NUM', i)), 'ox': _sla_float(p, 'PAGEXPOS'), 'oy': _sla_float(p, 'PAGEYPOS')}
                  for i, p in enumerate(page_els)]
    num_to_idx = {pm['num']: i for i, pm in enumerate(pages_meta)}
    pages = [{'blocks': []} for _ in pages_meta]

    item_id_to_block_id = {}
    next_item_of_iid = {}
    pending_links = []

    for obj in doc.findall('PAGEOBJECT'):
        pidx = num_to_idx.get(int(_sla_float(obj, 'OwnPage', 0)), 0)
        pm = pages_meta[pidx]
        x_mm = (_sla_float(obj, 'XPOS') - pm['ox']) / _MM_TO_PT
        y_mm = (_sla_float(obj, 'YPOS') - pm['oy']) / _MM_TO_PT
        w_pt = _sla_float(obj, 'WIDTH', 50 * _MM_TO_PT)
        h_pt = _sla_float(obj, 'HEIGHT', 30 * _MM_TO_PT)
        w_mm = max(1.0, w_pt / _MM_TO_PT)
        h_mm = max(1.0, h_pt / _MM_TO_PT)
        if (obj.get('Annotation') == '1' and obj.get('AnnotationType') == '11'
                and obj.get('AnnotationActionType') == '8' and (obj.get('AnnotationExtern') or '').strip()):
            pending_links.append((pidx, x_mm, y_mm, w_mm, h_mm, obj.get('AnnotationExtern').strip()))
            continue
        rot = _sla_float(obj, 'ROT', 0)
        block = {'id': uuid.uuid4().hex[:8], 'x': round(x_mm, 3), 'y': round(y_mm, 3),
                 'w': round(w_mm, 3), 'h': round(h_mm, 3)}
        if rot:
            block['rotation'] = round(rot, 2)
        ptype = obj.get('PTYPE')
        if ptype == '2':
            block['type'] = 'image'
            block['src'] = obj.get('PFILE') or ''
            block['caption'] = ''
        elif ptype == '4':
            text = _sla_story_text(obj)
            block['type'] = 'text'
            block['text'] = text if text.strip() else '[imported text frame, empty]'
            runs = _sla_runs_from_story(obj)
            if runs:
                block['runs'] = runs
        elif ptype in ('6', '7'):
            svg_local, has_curve, closed = _sla_path_to_local_svg(obj.get('path'), w_pt, h_pt, w_mm, h_mm)
            pts_pt, pts_closed = _sla_parse_path_points(obj.get('path'))
            if has_curve and svg_local:
                block['type'] = 'vector_shape'
                block['shape'] = 'polygon' if closed else 'polyline'
                block['svg_path'] = svg_local
                block['points'] = [[round(x, 3), round(y, 3)] for x, y in _svg_path_anchor_points(svg_local)]
                pcolor = obj.get('PCOLOR')
                if pcolor and pcolor != 'None':
                    block['fill'] = pcolor
                pcolor2 = obj.get('PCOLOR2')
                block['stroke'] = pcolor2 if pcolor2 and pcolor2 != 'None' else '#111111'
            elif len(pts_pt) >= 2:
                block['type'] = 'vector_shape'
                block['shape'] = 'polygon' if pts_closed else 'polyline'
                block['points'] = [[round((x / w_pt) * w_mm, 3), round((y / h_pt) * h_mm, 3)] for x, y in pts_pt]
                pcolor = obj.get('PCOLOR')
                if pcolor and pcolor != 'None':
                    block['fill'] = pcolor
                pcolor2 = obj.get('PCOLOR2')
                block['stroke'] = pcolor2 if pcolor2 and pcolor2 != 'None' else '#111111'
            else:
                block['type'] = 'text'
                block['text'] = '[imported shape, empty]'
        else:
            text = _sla_story_text(obj)
            block['type'] = 'text'
            block['text'] = text if text.strip() else '[imported frame, empty]'
        iid = obj.get('ItemID')
        if iid:
            item_id_to_block_id[iid] = block['id']
            nx = obj.get('NEXTITEM')
            if nx and nx != '-1':
                next_item_of_iid[iid] = nx
        pages[pidx]['blocks'].append(block)

    for pidx, lx, ly, lw, lh, href in pending_links:
        cy = ly + lh / 2
        host = None
        for b in pages[pidx]['blocks']:
            if b.get('type') != 'text':
                continue
            bx, by, bw, bh = b.get('x', 0), b.get('y', 0), b.get('w', 0), b.get('h', 0)
            if by <= cy <= by + bh and (bx < lx + lw) and (bx + bw > lx):
                if host is None or bh < host.get('h', 1e9):
                    host = b
        if host is None:
            continue
        runs = host.get('runs')
        if not runs:
            base_text = host.get('text', '')
            if not base_text:
                continue
            runs = [{'text': base_text}]
        total = sum(len(r.get('text', '')) for r in runs) or 1
        bh = max(0.001, host.get('h', 1))
        frac0 = max(0.0, min(1.0, (ly - host.get('y', 0)) / bh))
        frac1 = max(0.0, min(1.0, (ly + lh - host.get('y', 0)) / bh))
        start_char = int(round(frac0 * total))
        end_char = max(start_char + 1, int(round(frac1 * total)))
        host['runs'] = _sla_apply_href_range(runs, start_char, end_char, href)

    frame_chains = []
    targets = set(next_item_of_iid.values())
    heads = [iid for iid in item_id_to_block_id if iid in next_item_of_iid and iid not in targets]
    for start_iid in heads:
        chain_ids, seen, cur_iid = [], set(), start_iid
        while cur_iid and cur_iid not in seen:
            bid = item_id_to_block_id.get(cur_iid)
            if not bid:
                break
            chain_ids.append(bid)
            seen.add(cur_iid)
            cur_iid = next_item_of_iid.get(cur_iid)
        if len(chain_ids) >= 2:
            frame_chains.append({'id': uuid.uuid4().hex[:8], 'frame_ids': chain_ids})

    result = {'preset': 'custom', 'page': {'w': round(page_w_mm, 3), 'h': round(page_h_mm, 3),
              'margin': [round(m, 3) for m in margin]}, 'pages': pages}
    if frame_chains:
        result['frame_chains'] = frame_chains
    return result


def _raw_page_block(dims, html, css, x=0, y=0, w=None, h=None):
    return {'id': uuid.uuid4().hex[:8], 'type': 'raw_page', 'x': x, 'y': y,
            'w': w if w is not None else dims['w'], 'h': h if h is not None else dims['h'],
            'html': html, 'extra_css': css}


def _pages_layout(dims, preset, page_htmls, css):
    pages = [{'blocks': [_raw_page_block(dims, html, css)]} for html in page_htmls]
    return {'preset': preset, 'page': dims, 'pages': pages or [{'blocks': []}]}


def _native_page(dims, type_, **fields):
    return {'blocks': [{'id': uuid.uuid4().hex[:8], 'type': type_, 'x': 0, 'y': 0,
                         'w': dims['w'], 'h': dims['h'], **fields}]}


_BODY_CONTENT_MARGIN = {'x': 18.0, 'y': 26.0, 'right': 14.0, 'bottom': 10.0}

_SEM_DEFAULT_H_MM = {
    'heading': 14.0, 'quote': 42.0, 'photo_unit': 95.0, 'photo_narrative': 100.0,
    'gallery': 70.0, 'list': 40.0, 'table': 60.0, 'divider': 6.0,
}


def _sem_block_height_mm(sem):
    t = sem.get('type')
    if t == 'paragraph':
        words = mm._words(sem.get('html', '') or '')
        return max(14.0, min(160.0, words * 0.85))
    if t == 'section':
        inner = sem.get('blocks') or []
        total = sum(_sem_block_height_mm(b) for b in inner) if inner else 40.0
        return max(30.0, total + 10.0)
    return _SEM_DEFAULT_H_MM.get(t, 40.0)


def create_magazine_project(article_ids, articles=None, title=None, creator='', description='',
                            regenerate=False):
    if isinstance(article_ids, int):
        article_ids = [article_ids]
    article_ids = [int(x) for x in article_ids]
    key = ','.join(str(x) for x in article_ids)
    existing = _find_existing('magazine', key)
    if existing and not regenerate:
        return existing
    if articles is None:
        articles = [get_article(i) for i in article_ids]
    articles = [a for a in articles if a]
    if not articles:
        return None

    dims = PAGE_PRESETS['a4']
    date_str = datetime.now(timezone.utc).strftime('%B %Y')
    mag_title = title or (articles[0]['title'] if len(articles) == 1 else 'Voice Express Collection')

    pages = [_native_page(dims, 'cover', article_ids=article_ids, title=mag_title,
                           date_str=date_str, creator=creator, description=description),
             _native_page(dims, 'masthead_page')]
    pages.append(_native_page(dims, 'toc', article_ids=article_ids))

    for i, art in enumerate(articles, 1):
        article_id = art['id']
        accent = mm._art_accent(art, i)
        art_type = mm._detect_type(art)

        if art_type == 'photo_essay':
            full_pages = mm.build_magazine_pages([art], title=art['title'], static_root=STATIC_ROOT)
            soup = BeautifulSoup(''.join(full_pages), 'html.parser')
            article_pages_html = [str(el) for el in soup.find_all('div', class_='page', recursive=False)][3:-1]
            for html in article_pages_html:
                pages.append({'blocks': [_raw_page_block(dims, html, '')]})
            continue

        raw_content = art.get('content', '') or ''
        has_img = bool(art.get('featured_image'))
        body_wc_est = mm._words(raw_content)
        if body_wc_est < 220 and has_img:
            pages.append(_native_page(dims, 'art_bleed', article_id=article_id, idx=i, accent=accent))
        elif body_wc_est < 220:
            pages.append(_native_page(dims, 'art_title', article_id=article_id, idx=i, accent=accent))
        else:
            pages.append(_native_page(dims, 'art_title', article_id=article_id, idx=i, accent=accent))
            if has_img:
                pages.append(_native_page(dims, 'art_bleed', article_id=article_id, idx=i, accent=accent))

        body_clean = mm._clean(raw_content, STATIC_ROOT, {})
        citations = mm._extract_citations(body_clean)
        base_pq = mm._CAT_PQ.get(art_type, 1)
        col_cls = mm._col_class(mm._words(body_clean), art_type, body_clean)
        all_blocks = mm._parse_blocks(body_clean)
        budget = mm._PAGE_BUDGET.get(col_cls, 220)
        blk_pages = mm._paginate_blocks(all_blocks, budget)

        photo_groups_seen = 0
        exploded = []
        for blk_list in blk_pages:
            pending = []
            for blk in blk_list:
                gtype = blk.get('group_type', 'dump')
                is_photo_group = blk.get('type') == 'photo_group' and gtype != 'sequence'
                if is_photo_group and blk.get('figures'):
                    if pending:
                        exploded.append({'kind': 'text', 'blocks': pending}); pending = []
                    n_chunks = len(mm._photo_group_chunks(
                        [f for f in blk['figures'] if f.get('img')], max_per_page=12))
                    for ci in range(n_chunks):
                        exploded.append({'kind': 'photo', 'group_index': photo_groups_seen, 'chunk_index': ci})
                    photo_groups_seen += 1
                else:
                    pending.append(blk)
            if pending:
                exploded.append({'kind': 'text', 'blocks': pending})

        last_txt_idx = next((j for j in range(len(exploded) - 1, -1, -1) if exploded[j]['kind'] == 'text'), -1)
        first_text_seen = False
        first_para_seen = False
        cite_dicts = [{'num': n, 'text': t, 'url': u} for n, t, u in citations] if citations else []
        for pg_idx, entry in enumerate(exploded, 1):
            pq = base_pq if pg_idx % 2 == 1 else ((base_pq % 7) + 1)
            if entry['kind'] == 'photo':
                pages.append(_native_page(dims, 'photo_group', article_id=article_id, idx=i, accent=accent,
                                           group_index=entry['group_index'], chunk_index=entry['chunk_index'],
                                           page_num=pg_idx))
            else:
                is_first_text = not first_text_seen
                first_text_seen = True
                is_last_text = (pg_idx - 1 == last_txt_idx)
                page_blocks = [{
                    'id': uuid.uuid4().hex[:8], 'type': 'body_chrome', 'x': 0, 'y': 0,
                    'w': dims['w'], 'h': dims['h'], 'article_id': article_id, 'idx': i,
                    'accent': accent, 'art_type': art_type, 'pq_style': pq, 'page_num': pg_idx,
                    'is_first': is_first_text, 'is_last': is_last_text,
                    'citations': cite_dicts if is_last_text else [],
                }]
                cx = _BODY_CONTENT_MARGIN['x']
                cy = _BODY_CONTENT_MARGIN['y']
                cw = dims['w'] - _BODY_CONTENT_MARGIN['x'] - _BODY_CONTENT_MARGIN['right']
                for sem in entry['blocks']:
                    h = _sem_block_height_mm(sem)
                    is_drop = (sem.get('type') == 'paragraph' and not first_para_seen)
                    if is_drop:
                        first_para_seen = True
                    if sem.get('type') == 'paragraph' and sem.get('html'):
                        sem = dict(sem)
                        sem['runs'] = mm._runs_from_html(sem['html'])
                    page_blocks.append({
                        'id': uuid.uuid4().hex[:8], 'type': 'sem_para',
                        'x': cx, 'y': cy, 'w': cw, 'h': h,
                        'article_id': article_id, 'idx': i, 'accent': accent,
                        'art_type': art_type, 'pq_style': pq, 'is_first': is_drop,
                        'sem': sem, 'citations': cite_dicts,
                    })
                    cy += h + 3.0
                pages.append({'blocks': page_blocks})
        if citations:
            pages.append(_native_page(dims, 'citations', article_id=article_id, idx=i, accent=accent,
                                       page_num=len(exploded) + 1,
                                       citations=[{'num': n, 'text': t, 'url': u} for n, t, u in citations]))

    pages.append(_native_page(dims, 'back_cover'))
    layout = {'preset': 'a4', 'page': dims, 'pages': pages}
    name = f'Magazine: {mag_title}'
    if existing:
        return _regenerate_layout(existing, layout)
    return _create(name, 'magazine', key, layout)



BS_COLS        = 3
BS_CPL         = 54
BS_LINES_COL   = 64
BS_LINES_FRONT = 46
BS_FIG_LINES   = 24
BS_MM_PER_LINE = 3.43
BS_MAXW_IMG    = 900

_bs_embed_cache: dict = {}
_bs_aspect_cache: dict = {}

def _bs_file_for(src: str, static_root: str):
    if not src or src.startswith('data:'):
        return None
    s = src.split('?')[0]
    if s.startswith('http://') or s.startswith('https://'):
        return None
    for pre in ('/static/', 'static/'):
        if s.startswith(pre):
            return os.path.join(static_root, s[len(pre):].replace('/', os.sep))
    p = os.path.join(static_root, s.lstrip('/').replace('/', os.sep))
    if not os.path.exists(p):
        p2 = os.path.join(BASE, os.path.basename(s))
        if os.path.exists(p2):
            return p2
    return p

def _bs_embed(src: str, static_root: str) -> str:
    if not src or src.startswith('data:'):
        return src or ''
    if src in _bs_embed_cache:
        return _bs_embed_cache[src]
    out = src
    fp = _bs_file_for(src, static_root) if static_root else None
    if fp and os.path.exists(fp):
        try:
            from PIL import Image
            import io as _io
            im = Image.open(fp).convert('RGB')
            _bs_aspect_cache[src] = im.height / im.width if im.width else None
            if im.width > BS_MAXW_IMG:
                im = im.resize((BS_MAXW_IMG, int(im.height * BS_MAXW_IMG / im.width)))
            buf = _io.BytesIO(); im.save(buf, 'JPEG', quality=82)
            out = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            out = src
    _bs_embed_cache[src] = out
    return out

def _bs_img_aspect(src: str):
    return _bs_aspect_cache.get(src)

def _bs_qr(data: str) -> str:
    if not data:
        return ''
    try:
        import qrcode, io as _io
        q = qrcode.QRCode(border=1, box_size=8,
                          error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(data); q.make(fit=True)
        img = q.make_image(fill_color='black', back_color='white')
        buf = _io.BytesIO(); img.save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ''

_BS_BIO_RE = re.compile(
    r"(work (has )?appeared in|is (a|an|currently|the founder|law student|presently|a scholar|"
    r"a postgraduate|a final year|a student of)|scholar of religion|associate professor|"
    r"Head of Design|Cover (photo|design)|Based on a report by|Photographs? by [A-Z]|"
    r"Proposed by|Interviewed by|graphic designer|muckrack)", re.I)

def _bs_t(el) -> str:
    return re.sub(r'\s+', ' ', el.get_text(' ', strip=True)) if el else ''

def _bs_credit(figc) -> str:
    if not figc:
        return ''
    cite = figc.find(class_='photo-credit')
    if not cite:
        return ''
    txt = _bs_t(cite)
    cite.extract()
    return txt

def _bs_pcost(chars: int, cpl: int = BS_CPL) -> int:
    return max(1, math.ceil(chars / cpl)) + 1

_BS_MAX_ITEM_COST = 40

def _bs_chunk_text(text: str, cpl: int, max_cost: int = _BS_MAX_ITEM_COST) -> list:
    if _bs_pcost(len(text), cpl) <= max_cost:
        return [text]
    sentences = [s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])', text) if s] or [text]
    chunks, cur = [], ''
    for s in sentences:
        trial = f'{cur} {s}'.strip() if cur else s
        if cur and _bs_pcost(len(trial), cpl) > max_cost:
            chunks.append(cur)
            cur = s
        else:
            cur = trial
    if cur:
        chunks.append(cur)
    return chunks or [text]

def _blocks(html_str: str, static_root: str, credit: str = '') -> list:
    if not html_str:
        return []
    if BeautifulSoup is None:
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html_str)).strip()
        return [{'html': f'<p>{_esc(c)}</p>', 'cost': _bs_pcost(len(c))}
                for c in re.split(r'(?<=[.!?])\s+(?=[A-Z])', text) if c][:60]
    soup = BeautifulSoup(html_str, 'html.parser')
    root = soup.body or soup
    out: list = []

    def _img_shape(aspect):
        if aspect is None:
            return 'square'
        if aspect <= 0.8:
            return 'wide'
        if aspect >= 1.25:
            return 'tall'
        return 'square'

    def emit_img(figel):
        img = figel if getattr(figel, 'name', '') == 'img' else figel.find('img')
        if not img:
            return
        orig_src = img.get('src', '')
        src = _bs_embed(orig_src, static_root)
        if not src:
            return
        figc = None if getattr(figel, 'name', '') == 'img' else figel.find('figcaption')
        photo_credit = _bs_credit(figc)
        cap = _bs_t(figc) if figc else ''
        alt = img.get('alt', '') or cap
        credit_html = ''
        if photo_credit:
            credit_html = f'<span class="bs-credit">{_esc(photo_credit)}</span>'
        elif credit and 'photo' not in cap.lower() and 'credit' not in cap.lower():
            credit_html = f'<span class="bs-credit">Photo: {_esc(credit)}</span>'
        capx = f'<figcaption>{_esc(cap)}{credit_html}</figcaption>' if (cap or credit_html) else ''
        aspect = _bs_img_aspect(orig_src)
        if aspect:
            bs_col_w_mm = 91.0
            fig_cost = max(6, round((bs_col_w_mm * aspect) / BS_MM_PER_LINE))
        else:
            fig_cost = BS_FIG_LINES
        out.append({'html': f'<figure class="bs-fig"><img src="{src}" alt="{_esc(alt)}">{capx}</figure>',
                    'cost': fig_cost + (_bs_pcost(len(cap)) if cap else 0),
                    'kind': 'photo', 'aspect': aspect, 'shape': _img_shape(aspect)})

    def emit_group(el, group_type):
        figs = []
        cost = 2
        for im in el.find_all('img'):
            orig_src = im.get('src', '')
            src = _bs_embed(orig_src, static_root)
            if not src:
                continue
            parent_fig = im.parent if im.parent and im.parent.name == 'figure' else None
            figc = parent_fig.find('figcaption') if parent_fig else None
            photo_credit = _bs_credit(figc)
            cap = _bs_t(figc) if figc else ''
            alt = im.get('alt', '') or cap
            credit_html = f'<span class="bs-credit">{_esc(photo_credit)}</span>' if photo_credit else ''
            capx = f'<figcaption>{_esc(cap)}{credit_html}</figcaption>' if (cap or credit_html) else ''
            figs.append(f'<figure><img src="{src}" alt="{_esc(alt)}">{capx}</figure>')
            aspect = _bs_img_aspect(orig_src)
            bs_col_w_mm = 91.0
            cost += max(4, round((bs_col_w_mm * (aspect or 1.0)) / BS_MM_PER_LINE) // 2)
        if not figs:
            return
        shape = 'wide' if group_type in ('sequence', 'comic') else 'square'
        style_attr = ''
        if group_type in ('dump', 'grid', 'collage', 'crowd') and len(figs) > 4:
            cols = max(3, min(5, round(len(figs) ** 0.5)))
            style_attr = f' style="grid-template-columns:repeat({cols},1fr)"'
        out.append({'html': f'<div class="bs-strip" data-type="{_esc(group_type)}"{style_attr}>{"".join(figs)}</div>',
                    'cost': cost, 'kind': 'photo-group', 'group_type': group_type,
                    'n': len(figs), 'shape': shape})

    for el in root.children:
        name = getattr(el, 'name', None)
        if name is None:
            t = re.sub(r'\s+', ' ', str(el)).strip()
            if t:
                out.append({'html': f'<p>{_esc(t)}</p>', 'cost': _bs_pcost(len(t))})
            continue
        cls = ' '.join(el.get('class', []))
        if name in ('h2', 'h3', 'h4') or 'section-heading' in cls:
            t = _bs_t(el)
            if t:
                out.append({'html': f'<h3 class="bs-sub">{_esc(t)}</h3>', 'cost': 2, 'kind': 'heading'})
        elif name == 'figure' or (name == 'div' and ('photo-unit' in cls or 'photo-group' in cls)):
            imgs = el.find_all('img')
            if len(imgs) <= 1:
                emit_img(el)
            elif 'photo-group' in cls:
                emit_group(el, el.get('data-type') or 'dump')
            else:
                for im in imgs:
                    emit_img(im.parent if im.parent and im.parent.name == 'figure' else im)
        elif name == 'img':
            emit_img(el)
        elif name == 'blockquote' or 'pull' in cls or 'spoken-quote' in cls:
            t = _bs_t(el)
            cite = el.find('cite') or el.find(class_='qa-speaker')
            who = f'<span class="bs-q-who">— {_esc(_bs_t(cite))}</span>' if cite and _bs_t(cite) else ''
            chunks = _bs_chunk_text(t, BS_CPL - 6)
            for ci, chunk in enumerate(chunks):
                who_html = who if ci == len(chunks) - 1 else ''
                out.append({'html': f'<blockquote class="bs-quote">{_esc(chunk)}{who_html}</blockquote>',
                            'cost': _bs_pcost(len(chunk), BS_CPL - 6) + 2, 'kind': 'quote'})
        elif name in ('ul', 'ol'):
            items = [_bs_t(li) for li in el.find_all('li')]
            tag = 'ol' if name == 'ol' else 'ul'
            groups, cur, cur_cost = [], [], 0
            for i in items:
                c = _bs_pcost(len(i))
                if cur and cur_cost + c > _BS_MAX_ITEM_COST:
                    groups.append(cur)
                    cur, cur_cost = [], 0
                cur.append(i); cur_cost += c
            if cur:
                groups.append(cur)
            n_seen = 0
            for grp in groups:
                lis = ''.join(f'<li>{_esc(i)}</li>' for i in grp)
                start_attr = f' start="{n_seen + 1}"' if tag == 'ol' and n_seen else ''
                out.append({'html': f'<{tag} class="bs-list"{start_attr}>{lis}</{tag}>',
                            'cost': sum(_bs_pcost(len(i)) for i in grp) + 1, 'kind': 'list',
                            'n_items': len(grp)})
                n_seen += len(grp)
        elif name in ('p', 'div'):
            t = _bs_t(el)
            if t and not _BS_BIO_RE.search(t):
                role = el.get('data-text-role', '')
                rc = f' data-role="{_esc(role)}"' if role else ''
                for chunk in _bs_chunk_text(t, BS_CPL):
                    out.append({'html': f'<p{rc}>{_esc(chunk)}</p>', 'cost': _bs_pcost(len(chunk)),
                                'kind': 'text', 'role': role, 'chars': len(chunk)})
    return out

def _bs_byline(a: dict) -> str:
    return (a.get('byline_auto') or a.get('author_name') or a.get('byline') or '').strip()

def _story(a: dict, static_root: str, lead: bool = False) -> dict:
    title = _un((a.get('title') or 'Untitled').strip())
    deck  = _un((a.get('excerpt') or '').strip())
    byline = _un(_bs_byline(a))
    raw_content = a.get('content') or ''
    blocks = _blocks(raw_content, static_root, credit=byline)
    fi = a.get('featured_image')
    fi_in_body = bool(fi) and (f'src="{fi}"' in raw_content or f"src='{fi}'" in raw_content)
    fi_embed = _bs_embed(fi, static_root) if (fi and not fi_in_body) else ''
    hcost = (7 if lead else 4) + len(title) // 28 + (2 if deck else 0) + 2
    section = _un((a.get('section_name') or a.get('category_name') or '')).upper()
    head = {'lead': lead, 'cost': hcost, 'kicker': section,
            'title': title, 'deck': deck, 'byline': byline,
            'featured': fi_embed if (lead and fi) else ''}
    if fi_embed and not lead:
        credit_html = f'<span class="bs-credit">Photo: {_esc(byline)}</span>' if byline else ''
        capx = f'<figcaption>{credit_html}</figcaption>' if credit_html else ''
        aspect = _bs_img_aspect(fi)
        fi_cost = max(6, round((91.0 * aspect) / BS_MM_PER_LINE)) if aspect else BS_FIG_LINES
        blocks = [{'html': f'<figure class="bs-fig bs-fig-feat"><img src="{fi_embed}" alt="{_esc(title)}">{capx}</figure>',
                   'cost': fi_cost + 1}] + blocks
    return {'head': head, 'body': blocks, 'title': title, 'section': section}

def _lead_banner(h: dict) -> str:
    kick = f'<div class="bs-kicker">{_esc(h["kicker"])}</div>' if h['kicker'] else ''
    deck = f'<p class="bs-banner-deck">{_esc(h["deck"])}</p>' if h['deck'] else ''
    by   = f'<div class="bs-byline">By {_esc(h["byline"])}</div>' if h['byline'] else ''
    hero = f'<figure class="bs-banner-hero"><img src="{h["featured"]}" alt=""></figure>' if h['featured'] else ''
    return (f'<div class="bs-banner">{kick}<h2 class="bs-banner-hl">{_esc(h["title"])}</h2>'
            f'{deck}{by}{hero}</div>')

def _bs_render_head(h: dict) -> str:
    cls  = 'bs-head bs-head-lead' if h['lead'] else 'bs-head'
    kick = f'<div class="bs-kicker">{_esc(h["kicker"])}</div>' if h['kicker'] else ''
    deck = f'<p class="bs-deck">{_esc(h["deck"])}</p>' if h['deck'] else ''
    by   = f'<div class="bs-byline">By {_esc(h["byline"])}</div>' if h['byline'] else ''
    return f'<div class="{cls}">{kick}<h2 class="bs-hl">{_esc(h["title"])}</h2>{deck}{by}</div>'

class _Packer:
    def __init__(self, front_cap: int = BS_LINES_FRONT, cols: int = BS_COLS):
        self.cols = max(1, cols)
        self.pages = [[[] for _ in range(self.cols)]]
        self.p = 0; self.c = 0; self.u = 0
        self.front_cap = front_cap

    def _cap(self):
        return self.front_cap if self.p == 0 else BS_LINES_COL

    def _advance(self):
        self.c += 1; self.u = 0
        if self.c >= self.cols:
            self.c = 0; self.p += 1
            self.pages.append([[] for _ in range(self.cols)])
            return True
        return False

    def _emit(self, html, cost, section=None, jump=False):
        item = {'html': html, 'cost': cost}
        if section:
            item['section'] = section
        if jump:
            item['jump'] = True
        self.pages[self.p][self.c].append(item)

    def force_new_page(self):
        if self.u > 0 or self.c > 0 or any(self.pages[self.p]):
            self.c = self.cols - 1
            self._advance()

    def _place_body(self, body: list, title: str, section: str = None):
        for blk in body:
            cost = min(blk['cost'], self._cap())
            if self.u > 0 and self.u + cost > self._cap():
                if self._advance():
                    self.pages[self.p - 1][self.cols - 1].append({
                        'html': f'<div class="bs-jump bs-jump-to">Continued on page {self.p + 1} →</div>',
                        'cost': 3, 'jump': True})
                    self._emit(
                        f'<div class="bs-jump bs-jump-from"><em>{_esc(title[:54])}</em>'
                        f' · continued from page {self.p} </div>', 3, jump=True)
            self._emit(blk['html'], cost, section=section)
            self.u += cost
        self.u = min(self._cap(), self.u + 2)

    def place_story(self, st: dict):
        need = st['head']['cost'] + 6
        if self.u > 0 and self.u + need > self._cap():
            self._advance()
        st['start_page'] = self.p + 1
        section = st.get('section') or st['head'].get('kicker')
        self._emit(_bs_render_head(st['head']), st['head']['cost'], section=section)
        self.u += st['head']['cost']
        self._place_body(st['body'], st['title'], section=section)

    def place_lead_body(self, st: dict):
        section = st.get('section') or st['head'].get('kicker')
        self._place_body(st['body'], st['title'], section=section)

def _bs_sudoku(seed: int, blanks: int = 46):
    rng = random.Random(seed)
    base = 3; side = 9
    def pat(r, c): return (base * (r % base) + r // base + c) % side
    rows = [g * base + r for g in rng.sample(range(base), base) for r in rng.sample(range(base), base)]
    cols = [g * base + c for g in rng.sample(range(base), base) for c in rng.sample(range(base), base)]
    nums = rng.sample(range(1, side + 1), side)
    grid = [[nums[pat(r, c)] for c in cols] for r in rows]
    cells = [(r, c) for r in range(side) for c in range(side)]
    rng.shuffle(cells)
    for r, c in cells[:blanks]:
        grid[r][c] = 0
    return grid

def _bs_sudoku_html(grid) -> str:
    cells = ''
    for r in range(9):
        for c in range(9):
            v = grid[r][c]
            br = ' bsk-rb' if c in (2, 5) else ''
            bb = ' bsk-bb' if r in (2, 5) else ''
            cells += f'<div class="bsk-cell{br}{bb}">{v if v else ""}</div>'
    return f'<div class="bsk-grid">{cells}</div>'

_WS_DIRS = [(0, 1), (1, 0), (1, 1), (-1, 1)]


def _bs_wordsearch(seed: int, words: list, size: int = 12):
    rng = random.Random(seed)
    words = [w.upper() for w in words if 2 < len(w) <= size][:8]
    grid = [[None] * size for _ in range(size)]
    placed = []
    for w in words:
        for _ in range(60):
            dr, dc = rng.choice(_WS_DIRS)
            r0 = rng.randrange(size)
            c0 = rng.randrange(size)
            r1 = r0 + dr * (len(w) - 1)
            c1 = c0 + dc * (len(w) - 1)
            if not (0 <= r1 < size and 0 <= c1 < size):
                continue
            ok = True
            for i, ch in enumerate(w):
                cell = grid[r0 + dr * i][c0 + dc * i]
                if cell is not None and cell != ch:
                    ok = False
                    break
            if not ok:
                continue
            for i, ch in enumerate(w):
                grid[r0 + dr * i][c0 + dc * i] = ch
            placed.append(w)
            break
    letters = string.ascii_uppercase
    for r in range(size):
        for c in range(size):
            if grid[r][c] is None:
                grid[r][c] = rng.choice(letters)
    return grid, placed


def _bs_wordsearch_html(grid, placed) -> str:
    size = len(grid)
    cells = ''.join(f'<div class="bsw-cell">{grid[r][c]}</div>' for r in range(size) for c in range(size))
    words_html = ''.join(f'<span>{_esc(w)}</span>' for w in placed)
    return (f'<div class="bsw-grid" style="grid-template-columns:repeat({size},1fr)">{cells}</div>'
            f'<div class="bsw-words">{words_html}</div>')

def _bs_cryptogram(seed: int, text: str):
    rng = random.Random(seed)
    letters = list(string.ascii_uppercase)
    shuffled = letters[:]
    while True:
        rng.shuffle(shuffled)
        if all(a != b for a, b in zip(letters, shuffled)):
            break
    key = dict(zip(letters, shuffled))
    text = text.upper()
    cipher = ''.join(key.get(ch, ch) for ch in text)
    return cipher


def _bs_cryptogram_html(cipher: str) -> str:
    rows = []
    for i in range(0, len(cipher), 24):
        chunk = cipher[i:i + 24]
        cells = ''.join(
            f'<div class="bsc-cell">{ch if ch.strip() else ""}</div>' if ch != ' ' else '<div class="bsc-gap"></div>'
            for ch in chunk)
        rows.append(f'<div class="bsc-row">{cells}</div>')
    return '<div class="bsc-grid">' + ''.join(rows) + '</div>'

_EGG_LETTERS = 'TRUTH'
_EGG_ROT = (-7, 5, -3, 6, -5)

_HAIKU_1SYLL = ['dawn', 'ink', 'news', 'dusk', 'rain', 'light', 'dust', 'word',
               'cold', 'print', 'truth', 'wind', 'dark', 'warm', 'doubt', 'hand',
               'sound', 'page', 'time', 'fact']
_HAIKU_2SYLL = ['morning', 'evening', 'silence', 'paper', 'whisper', 'shadow',
               'story', 'ribbon', 'hollow', 'header', 'distant', 'printer',
               'humble', 'honest', 'city', 'sunrise']
_HAIKU_3SYLL = ['newspaper', 'uncertain', 'tomorrow', 'memory', 'headline',
               'forgotten', 'remember', 'together']

_HAIKU_STOPWORDS = {'the', 'and', 'that', 'with', 'this', 'from', 'were', 'have', 'your', 'you'}


def _bs_local_haiku(seed: int) -> list:
    rng = random.Random(seed)
    buckets = {1: _HAIKU_1SYLL, 2: _HAIKU_2SYLL, 3: _HAIKU_3SYLL}

    def line(target_syll):
        words, total, last = [], 0, None
        while total < target_syll:
            remaining = target_syll - total
            choices = [n for n in (1, 2, 3) if n <= remaining]
            if not choices:
                break
            n = rng.choice(choices)
            pool = [w for w in buckets[n] if w != last] or buckets[n]
            w = rng.choice(pool)
            words.append(w)
            total += n
            last = w
        return ' '.join(words)

    return [line(5), line(7), line(5)]


def _bs_edition_words(ym: str):
    seed = int(hashlib.md5(ym.encode()).hexdigest()[:8], 16)
    sentence = None
    try:
        import requests
        r = requests.get('https://zenquotes.io/api/random', timeout=3)
        if r.ok:
            data = r.json()
            if isinstance(data, list) and data and data[0].get('q'):
                sentence = data[0]['q']
    except Exception as e:
        print(f'[dtp_engine] edition-words API fetch failed, using local fallback: {e}')
    if not sentence:
        local_pool = [
            'The truth takes time to travel far.',
            'A quiet page outlives the loudest noise.',
            'Ink remembers what the moment forgets.',
            'Every headline was once just a whisper.',
            'The news is only half of what happened.',
        ]
        sentence = local_pool[seed % len(local_pool)]
    haiku = _bs_local_haiku(seed)
    words = set()
    for text in (sentence, *haiku):
        for w in re.findall(r"[A-Za-z']+", text):
            wl = w.strip("'").lower()
            if len(wl) >= 3 and wl not in _HAIKU_STOPWORDS:
                words.add(wl)
    words = sorted(words)
    random.Random(seed).shuffle(words)
    return words or list(_EGG_LETTERS), haiku


def _bs_egg(i: int, words=None) -> str:
    rot = _EGG_ROT[i % len(_EGG_ROT)]
    if words:
        text = words[i % len(words)]
        size = '.58em'
    else:
        text = _EGG_LETTERS[i % len(_EGG_LETTERS)]
        size = '.72em'
    return (f'<span class="bs-egg" aria-hidden="true" style="font-family:\'Segoe Script\','
            f'\'Brush Script MT\',cursive;font-size:{size};opacity:.34;color:var(--accent);'
            f'transform:rotate({rot}deg);display:inline-block;vertical-align:middle;'
            f'white-space:nowrap">{_esc(text)}</span>')

def _bs_masthead(pub: dict, edition: str, vol, issue_note: str, egg_words=None) -> str:
    name = pub.get('name', 'The Voice Express')
    tag  = pub.get('tagline', '')
    website = pub.get('website', '')
    location = pub.get('location', '')
    return f'''<header class="bs-mast">
      <div class="bs-mast-rule bs-mast-rule-top">{_bs_egg(0, egg_words)}</div>
      <h1 class="bs-mast-name">{_esc(name)}</h1>
      <div class="bs-mast-tag">{_esc(tag)} {_bs_egg(2, egg_words)}</div>
      <div class="bs-mast-rule bs-mast-rule-mid"></div>
      <div class="bs-mast-byline">
        <span class="bs-mast-seg bs-mast-seg-l">{_bs_egg(1, egg_words)} Vol. {_esc(str(vol))}{" &middot; " + _esc(location) if location else ""}</span>
        <span class="bs-mast-seg bs-mast-seg-c">{_esc(edition)}</span>
        <span class="bs-mast-seg bs-mast-seg-r">{_esc(website)} {_bs_egg(3, egg_words)}</span>
      </div>
      <div class="bs-mast-note">{_esc(issue_note)}</div>
      <div class="bs-mast-rule bs-mast-rule2">{_bs_egg(4, egg_words)}</div>
    </header>'''

def _bs_sheet(inner: str, folio: int, total: int, pubname: str, edition_tag: str, front=False) -> str:
    foot = (f'<footer class="bs-foot"><span>{_esc(pubname)}</span>'
            f'<span>{folio} / {total}</span><span>{_esc(edition_tag)}</span></footer>')
    return f'<section class="bs-sheet{" bs-front" if front else ""}">{inner}{foot}</section>'

def _bs_cols_grid(page_cols: list) -> str:
    n = max(1, len(page_cols))
    cols = ''.join(f'<div class="bs-col">{"".join(item["html"] for item in col)}</div>' for col in page_cols)
    return f'<div class="bs-grid" style="grid-template-columns:repeat({n},1fr)">{cols}</div>'

def _bs_load_config(config):
    if config is not None:
        return config
    try:
        with open(os.path.join(BASE, 'broadsheet_config.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def build_broadsheet_sheets(content: dict, year: int, month: int,
                            static_root: str = None, config: dict = None,
                            enhancement: dict = None) -> list:
    enhancement = enhancement or {}
    static_root = static_root or os.path.join(BASE, 'static')
    config = _bs_load_config(config)
    pub     = config.get('publication', {})
    support = config.get('support', {})
    contact = config.get('contact', {})
    month_name = calendar.month_name[month]
    edition = f'{month_name} {year}'
    articles = content.get('articles', []) or []
    columns  = content.get('columns', []) or []

    stories = [_story(a, static_root, lead=(i == 0)) for i, a in enumerate(articles)]
    editorial = (content.get('editorial') or '').strip()
    total_lines = sum(s['head']['cost'] + sum(b['cost'] for b in s['body']) for s in stories)
    eff_cols = max(2, min(BS_COLS, math.ceil(total_lines / (BS_LINES_COL * 0.9)))) if stories else BS_COLS
    lead_banner = ''
    if stories:
        lead = stories[0]
        lead_banner = _lead_banner(lead['head'])
        banner_lines = 12 + (24 if lead['head']['featured'] else 0)
        front_cap = max(16, BS_LINES_FRONT - banner_lines)
        pk = _Packer(front_cap=front_cap, cols=eff_cols)
        pk.place_lead_body(lead)
        for st in stories[1:]:
            pk.place_story(st)
    else:
        pk = _Packer(cols=eff_cols)
    article_pages = pk.pages

    n_article_sheets = len(article_pages)
    has_cols   = bool(columns)
    has_puzzle = config.get('broadsheet', {}).get('include_sudoku', True)
    total = n_article_sheets + (1 if has_cols else 0) + (1 if has_puzzle else 0)

    sheets = []
    for pi, pcols in enumerate(article_pages):
        if pi == 0:
            mast = _bs_masthead(pub, edition, pub.get('volume', ''), pub.get('issue_note', ''))
            stand = (f'<div class="bs-standfirst"><span class="bs-sf-lbl">From the Editors</span>'
                     f'<p>{_esc(editorial)}</p></div>') if editorial else ''
            note = (f'<div class="bs-covernote">{_esc(enhancement["cover_note"])}</div>'
                    if enhancement.get('cover_note') else '')
            index = ''
            if enhancement.get('toc') and len(stories) > 1:
                rows = ''.join(
                    f'<div class="bs-idx-row"><span class="bs-idx-t">{_esc(s["title"][:60])}</span>'
                    f'<span class="bs-idx-p">{s.get("start_page", 1)}</span></div>'
                    for s in stories[1:])
                index = f'<div class="bs-index"><span class="bs-sf-lbl">Inside This Issue</span>{rows}</div>'
            inner = mast + stand + note + index + lead_banner + _bs_cols_grid(pcols)
        else:
            inner = (f'<div class="bs-runhead"><span>{_esc(pub.get("name",""))}</span>'
                     f'<span>{_esc(edition)}</span></div>' + _bs_cols_grid(pcols))
        sheets.append(_bs_sheet(inner, pi + 1, total, pub.get('name', ''), edition, front=(pi == 0)))

    folio = n_article_sheets
    if has_cols:
        folio += 1
        sheets.append(_bs_sheet(_bs_columns_inner(columns, static_root), folio, total, pub.get('name', ''), edition))

    if has_puzzle:
        folio += 1
        sheets.append(_bs_sheet(_bs_back_inner(config, year, month, edition), folio, total, pub.get('name', ''), edition))

    return sheets


def _bs_columns_inner(columns, static_root) -> str:
    cards = ''
    for e in columns:
        cov = _bs_embed(e.get('cover_image', ''), static_root) if e.get('cover_image') else ''
        covx = f'<div class="bs-colcard-img"><img src="{cov}" alt=""></div>' if cov else ''
        cards += (f'<div class="bs-colcard">{covx}'
                  f'<div class="bs-colcard-kick">{_esc((e.get("column_title") or "").upper())}</div>'
                  f'<div class="bs-colcard-title">{_esc(e.get("title",""))}</div>'
                  f'<div class="bs-colcard-sub">{_esc(e.get("subtitle",""))}</div>'
                  f'<div class="bs-colcard-date">{_esc((e.get("entry_date") or "")[:10])}</div></div>')
    return (f'<div class="bs-section-head"><h2>From the Columns</h2>'
            f'<div class="bs-section-sub">This month in our recurring periodicals</div></div>'
            f'<div class="bs-colcards">{cards}</div>')


def _bs_back_inner(config, year, month, edition) -> str:
    pub, support, contact = config.get('publication', {}), config.get('support', {}), config.get('contact', {})
    grid = _bs_sudoku(year * 100 + month)
    qr_kofi = _bs_qr((support.get('kofi') or {}).get('url', ''))
    rzp = support.get('razorpay') or {}
    qr_rzp  = _bs_qr(rzp.get('url', ''))
    emag_url = contact.get('emag', '')
    stand_url = contact.get('newsstand', '')
    qr_site = _bs_qr(emag_url or contact.get('website', '') or pub.get('website', ''))
    qr_stand = _bs_qr(stand_url)
    def panel(qr, label, note):
        qrx = f'<img class="bs-qr" src="{qr}">' if qr else '<div class="bs-qr bs-qr-x">—</div>'
        return (f'<div class="bs-supp">{qrx}<div class="bs-supp-l">{_esc(label)}</div>'
                f'<div class="bs-supp-n">{_esc(note)}</div></div>')
    supp = ((panel(qr_kofi, (support.get('kofi') or {}).get('label', 'Support on Ko-fi'),
                   (support.get('kofi') or {}).get('note', '')) if (support.get('kofi') or {}).get('url') else '')
            + (panel(qr_rzp, rzp.get('label', 'Support via Razorpay'), rzp.get('note', ''))
               if rzp.get('url') else '')
            + panel(qr_site, 'Read the magazine', emag_url or contact.get('website', '') or pub.get('website', ''))
            + (panel(qr_stand, 'The Newsstand', stand_url) if stand_url else ''))
    colo_bits = [b for b in [pub.get('description', ''), f'Est. {pub.get("est","")}' if pub.get('est') else '',
                              support.get('general_note', ''), contact.get('email', ''),
                              emag_url or contact.get('website', '') or pub.get('website', '')] if b]
    colophon = (f'<div class="bs-colophon"><strong>{_esc(pub.get("name",""))}</strong>'
                f'{" — " if colo_bits else ""}{_esc(" · ".join(colo_bits))}</div>')
    return (f'<div class="bs-section-head"><h2>The Back Page</h2>'
            f'<div class="bs-section-sub">Sudoku · {edition}</div></div>'
            f'<div class="bs-backgrid"><div class="bs-puzzle">{_bs_sudoku_html(grid)}'
            f'<div class="bs-puzzle-cap">Fill every row, column and 3×3 box with 1–9.</div></div>'
            f'<div class="bs-supp-wrap"><div class="bs-supp-head">Reader-supported journalism</div>'
            f'{supp}</div></div>{colophon}')


def _bs_backcover_inner(config, year, month, edition, ym: str, static_root: str) -> str:
    pub, support, contact = config.get('publication', {}), config.get('support', {}), config.get('contact', {})
    seed = int(hashlib.md5(ym.encode()).hexdigest()[:8], 16) % 100000
    label = pub.get('tagline', '') or pub.get('name', '')
    art_url = None
    if seed % 2 == 0 and _flow_png:
        art_url = _flow_png(seed, label)
    elif _voronoi_png:
        art_url = _voronoi_png(seed, label)
    elif _flow_png:
        art_url = _flow_png(seed, label)
    art_b64 = mm._b64(art_url, static_root) if art_url else None
    art_html = (f'<img class="bs-backcover-art" src="{art_b64}" alt="">' if art_b64
                else '<div class="bs-backcover-art" style="background:var(--paper)"></div>')

    logo = _logo_b64()
    mono_html = (f'<div class="bs-backcover-mono"><img src="{logo}" alt="V&amp;E"></div>' if logo else
                 f'<div class="bs-backcover-mono"><span class="bs-backcover-mono-fallback">V&amp;E</span></div>')

    read_url = (contact.get('website', '') or pub.get('website', '')).strip()
    qr = _bs_qr(read_url) if read_url else ''
    qr_html = (f'<div class="bs-backcover-qr-wrap"><img src="{qr}" alt="Read online QR"> '
               f'<div class="bs-backcover-qr-label">Read {_esc(edition)} online</div></div>'
               if qr else '')

    return (f'<div class="bs-backcover">{art_html}<div class="bs-backcover-plate"></div>'
            f'{mono_html}{qr_html}'
            f'<div class="bs-backcover-foot">{_esc(pub.get("name",""))} · {_esc(edition)}</div></div>')


def build_newsletter_broadsheet(content: dict, year: int, month: int,
                                static_root: str = None, config: dict = None,
                                enhancement: dict = None) -> str:
    enhancement = enhancement or {}
    month_name = calendar.month_name[month]
    edition = f'{month_name} {year}'
    sheets = build_broadsheet_sheets(content, year, month, static_root=static_root,
                                      config=config, enhancement=enhancement)
    body = '\n'.join(sheets)
    accent_css = f':root{{--accent:{enhancement["accent"]}}}' if enhancement.get('accent') else ''
    extra_css = enhancement.get('extra_css') or ''
    doc = _BS_DOC.replace('__TITLE__', _esc(f'The Voice Express — {edition} — Broadsheet')) \
              .replace('__BODY__', body)
    if accent_css or extra_css:
        doc = doc.replace('</style>', accent_css + '\n' + extra_css + '\n</style>')
    return doc

_BS_DOC = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
:root{--ink:#16140f;--paper:#f4efe2;--g:#5b5547;--rule:2px solid #16140f;--thin:1px solid #8a8273;--accent:#7a2018}
*{box-sizing:border-box}
.photo-credit{display:block;font-style:normal;opacity:.72;margin-top:.2em}
@page{size:420mm 297mm;margin:11mm 12mm}
html,body{margin:0;background:transparent;font-family:"Georgia","Times New Roman",serif;color:var(--ink)}
.bs-sheet{position:relative;width:100%;max-width:396mm;margin:0 auto;padding:0 0 28mm 0;
  background-color:var(--paper);
  background-image:
    radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(22,20,15,.05) 100%),
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='matrix' values='0 0 0 0 0.086  0 0 0 0 0.078  0 0 0 0 0.059  0 0 0 0.045 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
  background-repeat:no-repeat,repeat;
  background-size:100% 100%,120px 120px;
  page-break-after:always;min-height:297mm}
.bs-sheet:last-child{page-break-after:auto}
.bs-module{border-top:3px solid var(--ink);padding:1.6mm 0 0;box-sizing:border-box}
.bs-mod-head{border-bottom:1px solid var(--ink);padding-bottom:1.2mm;margin-bottom:1.6mm}
.bs-mod-head .bs-hl{font-size:1.5rem;line-height:1.06}
.bs-mod-head .bs-deck{font-size:.8rem;margin:.2rem 0 .1rem}
.bs-mod-body{column-gap:6mm;column-rule:1px solid #d4cfc0;column-fill:balance}
.bs-mod-body > *{break-inside:avoid-column}
.bs-mod-body p{margin:0 0 .18rem;text-indent:1.05em;text-align:justify;hyphens:auto;
  font-size:.7rem;line-height:1.32;
  -webkit-hyphenate-limit-before:3;-webkit-hyphenate-limit-after:3;
  hyphenate-limit-chars:6 3 3;hyphenate-limit-lines:2}
.bs-mod-body p:first-of-type{text-indent:0}
.bs-mod-body .bs-quote{border-left:3px solid var(--accent);padding:.1rem 0 .1rem 2mm;margin:.3rem 0;
  font-family:"Playfair Display","Georgia",serif;font-style:italic;font-size:.86rem;line-height:1.26;
  text-indent:0;font-weight:600}
.bs-mod-body .bs-sub{font-size:.86rem;margin:.45rem 0 .2rem;text-indent:0}
.bs-mod-body .bs-fig,.bs-mod-body .bs-strip{column-span:all;margin:.5rem 0 .6rem}
.bs-mod-body .bs-fig img{max-height:56mm;object-fit:contain;object-position:center}
.bs-mod-body .bs-fig figcaption{font-size:.62rem}
.bs-mod-body .bs-strip img{max-height:44mm;object-fit:cover}
.bs-mod-body .bs-fig:nth-of-type(n+3) img{max-height:38mm}
.bs-mod-body .bs-strip[data-type="dump"],.bs-mod-body .bs-strip[data-type="grid"],
.bs-mod-body .bs-strip[data-type="collage"]{column-count:3;column-gap:2mm}
.bs-mod-body .bs-strip[data-type="crowd"]{column-count:4;column-gap:1.6mm}
.bs-col-rule{position:absolute;width:1px;background:#d4cfc0;pointer-events:none;z-index:0}
.bs-side-label{position:absolute;left:0;top:0;height:100%;width:8mm;display:flex;
  align-items:center;justify-content:center;pointer-events:none;z-index:1;
  overflow:hidden}
.bs-side-label span{display:inline-block;font-family:var(--fm,Georgia,serif);font-size:.6rem;
  font-weight:700;letter-spacing:.28em;text-transform:uppercase;color:var(--accent);
  border-top:1px solid var(--accent);border-bottom:1px solid var(--accent);padding:.25em .1em;
  white-space:nowrap;transform:rotate(-90deg);transform-origin:center center}
.bs-fig-feat img{width:100%;max-height:48mm;object-fit:contain;background:var(--paper)}
@import url('https://fonts.googleapis.com/css2?family=Pirata+One&display=swap');
.bs-mast{text-align:center;margin-bottom:0.7rem;padding:0 0 0.5rem}
.bs-mast-rule{height:0;margin:0;border-top:3px double var(--ink)}
.bs-mast-rule-top{margin-bottom:.5rem}
.bs-mast-rule-mid{border-top:1px solid var(--ink);margin:.4rem 0}
.bs-mast-rule2{margin-top:.45rem}
.bs-mast-name{font-family:"Pirata One","Playfair Display","Old English Text MT","Georgia",serif;
  font-weight:400;font-size:5.6rem;letter-spacing:.5px;line-height:.9;margin:0;text-align:center;
  text-rendering:optimizeLegibility;text-shadow:0.35px 0 0 var(--ink)}
.bs-mast-tag{text-align:center;font-style:italic;font-size:1.0rem;color:var(--g);letter-spacing:.03em;margin-top:.15rem}
.bs-mast-note{text-align:center;font-size:.68rem;font-style:italic;color:var(--accent);margin-top:.25rem}
.bs-mast-byline{display:flex;justify-content:space-between;align-items:baseline;margin-top:.5rem;
  font-size:.64rem;letter-spacing:.09em;text-transform:uppercase;color:var(--g)}
.bs-mast-seg-c{font-weight:700;color:var(--ink)}
.bs-mast-seg-r{text-align:right}
.bs-standfirst{border-top:1px solid #d4cfc0;border-bottom:1px solid #d4cfc0;padding:0.6rem 0;margin:0.8rem 0 1rem;
  display:flex;gap:1rem;align-items:baseline}
.bs-sf-lbl{font-size:.58rem;letter-spacing:.16em;text-transform:uppercase;font-weight:700;white-space:nowrap;color:var(--accent)}
.bs-standfirst p{margin:0;font-style:italic;font-size:.90rem;line-height:1.45;color:#322d22}
.bs-runhead{display:flex;justify-content:space-between;font-size:.60rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--g);border-bottom:1px solid #d4cfc0;padding-bottom:.4rem;margin-bottom:0.8rem}
.bs-covernote{font-style:italic;font-size:.76rem;color:var(--accent);text-align:center;margin:0.4rem 0 0.6rem}
.bs-index{border-top:1px solid #d4cfc0;border-bottom:1px solid #d4cfc0;padding:0.5rem 0;margin:0.8rem 0 1rem;
  display:grid;grid-template-columns:repeat(3,1fr);gap:0 1.2rem;font-size:.66rem;min-width:0;overflow:hidden}
.bs-index .bs-sf-lbl{grid-column:1/-1;display:block;margin-bottom:.4rem;color:var(--accent)}
.bs-idx-row{display:flex;justify-content:space-between;gap:.5rem;border-bottom:1px dotted #b3ab98;padding:.15rem 0;
  page-break-inside:avoid;min-width:0}
.bs-idx-t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.bs-idx-p{color:var(--accent);font-weight:700;flex:0 0 auto}
.bs-banner{border-bottom:2px solid #d4cfc0;padding-bottom:0.8rem;margin-bottom:1rem;page-break-inside:avoid}
.bs-banner-hl{font-family:"Playfair Display","Georgia",serif;font-weight:900;font-size:4.0rem;
  line-height:0.98;letter-spacing:-.8px;margin:0 0 0.4rem;text-align:center;
  text-rendering:optimizeLegibility;text-shadow:0.3px 0 0 var(--ink)}
.bs-banner-deck{font-style:italic;font-size:1.2rem;line-height:1.35;text-align:center;color:#352f24;
  max-width:80%;margin:0.4rem auto 0.6rem}
.bs-banner .bs-kicker{text-align:center;font-size:.68rem}
.bs-banner .bs-byline{text-align:center}
.bs-banner-hero{margin:0.8rem 0 0}
.bs-banner-hero img{width:100%;max-height:180mm;object-fit:contain;background:var(--paper);display:block;border:1px solid var(--g)}
.bs-grid{column-count:unset;display:grid;grid-template-columns:repeat(3,1fr);gap:0 8mm;text-align:justify;hyphens:auto}
.bs-col{padding:0;border-right:1px solid #d4cfc0;break-inside:avoid}
.bs-col:last-child{border-right:none}
.bs-col > *{padding:0 2mm}
.bs-framed{border-top:3px solid var(--ink);border-bottom:1px solid var(--ink);
  border-left:1px solid var(--ink);border-right:2px solid var(--ink);padding:3mm 4mm;
  box-sizing:border-box;position:relative;
  box-shadow:1.1mm 1.1mm 1.8mm rgba(22,20,15,.12)}
.bs-framed > *{padding:0}
.bs-framed::before,.bs-framed::after{content:"";position:absolute;width:7mm;height:7mm;pointer-events:none}
.bs-framed::before{top:-2px;left:-2px;border-top:3px solid var(--accent);border-left:1px solid var(--accent)}
.bs-framed::after{bottom:-2px;right:-2px;border-bottom:3px solid var(--accent);border-right:1px solid var(--accent)}
.bs-plain{border-top:1px solid #d4cfc0;border-right:3px double #c9c2ac;padding:2.5mm 4mm 1mm 1.5mm;
  box-sizing:border-box}
.bs-plain > *{padding:0}
.bs-boxed{border:1px solid var(--ink);padding:2mm 3mm;box-sizing:border-box;
  box-shadow:0.8mm 0.8mm 1.2mm rgba(22,20,15,.08)}
.bs-boxed > *{padding:0}
.bs-pullquote{border-left:4px solid var(--accent);padding:1mm 0 1mm 4mm;box-sizing:border-box;
  background:rgba(122,32,24,.035)}
.bs-pullquote > *{padding:0}
.bs-pullquote .bs-quote{border-left:none;padding-left:0;font-size:1.15rem;line-height:1.32;
  font-family:"Playfair Display","Georgia",serif;font-weight:600}
.bs-pullquote .bs-q-who{font-size:.62rem}
.bs-front-puzzle,.bs-front-logo,.bs-front-qr,.bs-front-links,.bs-front-monthyear{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:100%;height:100%;text-align:center}
.bs-front-puzzle .bsk-grid{width:88%}
.bs-front-puzzle-cap{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--g);margin-top:.4rem}
.bs-front-logo img{max-width:80%;max-height:80%;object-fit:contain}
.bs-front-monthyear{font-family:"Playfair Display","Georgia",serif;font-weight:900;
  font-size:1.6rem;letter-spacing:.04em;line-height:1.05}
.bs-front-qr img{width:60%;height:auto}
.bs-front-qr-label{font-size:.6rem;letter-spacing:.08em;text-transform:uppercase;color:var(--g);margin-top:.3rem}
.bs-front-links{font-size:.68rem;line-height:1.9;color:var(--g)}
.bs-front-quote{font-family:"Playfair Display","Georgia",serif;font-style:italic;font-weight:700;
  font-size:.86rem;line-height:1.3;color:var(--accent);opacity:.55;text-align:center}
.bs-front-wordmark{font-family:"Pirata One","Playfair Display",serif;font-size:1.1rem;
  color:var(--ink);opacity:.16;text-align:center;letter-spacing:.03em;white-space:nowrap}
.bs-front-haiku{display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:100%;height:100%;text-align:center;font-family:"Playfair Display","Georgia",serif;
  font-style:italic;font-size:.82rem;line-height:1.5;color:var(--ink)}
.bs-front-haiku-cap{font-family:"Georgia",serif;font-style:normal;font-size:.58rem;
  letter-spacing:.1em;text-transform:uppercase;color:var(--g);margin-top:.4rem}
.bs-lead-box{padding:0 4mm}
.bs-lead-box .bs-head-lead{border-bottom:none;padding-bottom:0}
.bs-lead-box .bs-head-lead .bs-hl{font-size:2.9rem}
.bs-lead-hero{margin:0 0 .6rem}
.bs-lead-hero img{width:100%;max-height:150mm;object-fit:cover;display:block;border:1px solid var(--g)}
.bs-lead-hero figcaption{font-size:.62rem;color:#5a5247;padding:.25rem 0;border-bottom:1px solid #d4cfc0}
.bs-lead-body{column-count:2;column-gap:8mm;column-rule:1px solid #d4cfc0;text-align:justify;hyphens:auto}
.bs-lead-body p{margin:0;font-size:.83rem;line-height:1.44;text-indent:1.05em;orphans:2;widows:2}
.bs-lead-body p[data-role="lede"]{text-indent:0}
.bs-side-box{padding:0 3mm;border-left:1px solid #d4cfc0;border-right:1px solid #d4cfc0}
.bs-side-box .bs-hl{font-size:1.3rem}
.bs-side-box .bs-deck{font-style:italic}
.bs-side-box p{font-size:.79rem}
.bs-head{margin:0.2rem 0 0.4rem;break-inside:avoid;orphans:2;widows:2}
.bs-kicker{font-size:.54rem;letter-spacing:.18em;text-transform:uppercase;font-weight:700;color:var(--accent);
  margin-bottom:.2rem;display:flex;align-items:center;gap:.4em}
.bs-kicker::before{content:"";display:inline-block;width:3px;height:.85em;background:var(--accent);flex:0 0 auto}
.bs-hl{font-family:"Playfair Display","Georgia",serif;font-weight:800;line-height:1.04;margin:0 0 .25rem;
  font-size:1.15rem;text-rendering:optimizeLegibility;
  text-shadow:0.25px 0 0 var(--ink)}
.bs-head-lead .bs-hl{font-size:2.4rem;line-height:1.0;letter-spacing:-.6px}
.bs-head-lead{border-bottom:2px solid #d4cfc0;padding-bottom:0.4rem;margin-bottom:0.6rem}
.bs-deck{font-style:italic;font-size:.84rem;line-height:1.4;color:#352f24;margin:.15rem 0 .25rem}
.bs-head-lead .bs-deck{font-size:1.0rem;line-height:1.42}
.bs-byline{font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:var(--g);margin-bottom:.35rem}
.bs-col p{margin:0;font-size:.72rem;line-height:1.28;text-indent:1.05em;orphans:2;widows:2;
  text-align:justify;hyphens:auto}
.bs-col p[data-role="lede"]{text-indent:0;font-size:.77rem;line-height:1.26}
.bs-col.bs-span-1 p{font-size:.68rem;line-height:1.24}
.bs-col.bs-span-1 .bs-hl{font-size:.92rem}
.bs-col.bs-span-3 p,.bs-col.bs-span-4 p{font-size:.78rem;line-height:1.34}
.bs-col.bs-span-3 .bs-hl,.bs-col.bs-span-4 .bs-hl{font-size:1.2rem}
.bs-sub{font-family:"Playfair Display","Georgia",serif;font-weight:700;font-size:.98rem;margin:.55rem 0 .25rem;text-indent:0}
.bs-quote{margin:.5rem 0;padding:.25rem 0 .25rem 0.6mm;border-left:3px solid var(--accent);
  font-style:italic;font-size:.88rem;line-height:1.38;text-indent:0;page-break-inside:avoid}
.bs-q-who{display:block;font-style:normal;font-size:.60rem;letter-spacing:.09em;text-transform:uppercase;color:var(--g);margin-top:.3rem}
.bs-list{margin:.4rem 0 .4rem 1.1rem;font-size:.79rem;line-height:1.38}
.bs-fig{margin:.5rem 0;break-inside:avoid;page-break-inside:avoid}
.bs-fig img{width:100%;display:block;border:1px solid var(--g);margin-bottom:.3rem}
.bs-fig figcaption{font-size:.60rem;line-height:1.3;color:#5a5247;padding:.2rem 0;text-indent:0;border-bottom:1px solid #d4cfc0}
.bs-strip{margin:.5rem 0;break-inside:avoid;page-break-inside:avoid}
.bs-strip img{display:block;width:100%;height:auto;border:1px solid var(--g)}
.bs-strip figure{margin:0}
.bs-strip figcaption{font-size:.58rem;line-height:1.28;color:#5a5247;padding:.2rem 0;text-indent:0}
.bs-strip[data-type="dump"],.bs-strip[data-type="grid"],.bs-strip[data-type="collage"]{
  display:grid;grid-template-columns:repeat(2,1fr);gap:.4rem}
.bs-strip[data-type="crowd"]{display:grid;grid-template-columns:repeat(3,1fr);gap:.35rem}
.bs-strip[data-type="sequence"]{display:block;counter-reset:bs-seq}
.bs-strip[data-type="sequence"] figure{counter-increment:bs-seq;display:flex;align-items:center;
  gap:.9rem;margin:0 0 .55rem}
.bs-strip[data-type="sequence"] figure:last-child{margin-bottom:0}
.bs-strip[data-type="sequence"] figure:nth-child(even){flex-direction:row-reverse}
.bs-strip[data-type="sequence"] img{flex:0 0 54%;width:54%}
.bs-strip[data-type="sequence"] figcaption{flex:1;border:none}
.bs-strip[data-type="sequence"] figcaption::before{content:counter(bs-seq,decimal-leading-zero) " / ";
  font-weight:700;color:var(--accent)}
.bs-strip[data-type="comic"]{display:block;background:var(--ink);border:2px solid var(--ink);
  padding:3px;counter-reset:bs-pan}
.bs-strip[data-type="comic"] figure{background:var(--paper);margin:0 0 3px;counter-increment:bs-pan}
.bs-strip[data-type="comic"] figure:last-child{margin-bottom:0}
.bs-strip[data-type="comic"] figcaption{padding:.25rem .4rem;font-style:italic}
.bs-strip[data-type="comic"] figcaption::before{content:counter(bs-pan) ". "; font-weight:700;
  font-style:normal;color:var(--accent)}
.bs-colcal{display:grid;gap:.3rem}
.bs-colcal figcaption{text-align:center}
.bs-colcal-empty{border:1px dashed #b3ab98;min-height:12mm;
  background:repeating-linear-gradient(45deg,var(--paper),var(--paper) 4px,#e5ddc9 4px,#e5ddc9 5px)}
.bs-colcal-text{border:1px solid var(--g);padding:.3rem;font-size:.58rem;line-height:1.25;
  display:flex;flex-direction:column;gap:.2rem;min-height:12mm}
.bs-colcal-text span{font-weight:700;color:var(--accent);font-size:.54rem;letter-spacing:.06em;text-transform:uppercase}
.bs-divider{display:flex;align-items:center;justify-content:center;border-left:1px solid var(--accent);
  border-right:1px solid var(--accent)}
.bs-divider-quote{display:flex;align-items:center;justify-content:center;width:100%;height:100%}
.bs-divider-quote span{display:inline-block;white-space:nowrap;transform:rotate(-90deg);
  font-family:"Playfair Display","Georgia",serif;font-style:italic;font-size:.82rem;
  color:var(--accent);letter-spacing:.02em}
.bs-divider-plain{position:relative}
.bs-tmpl-brief .bs-col p,.bs-col.bs-tmpl-brief p{font-size:.70rem;line-height:1.3}
.bs-tmpl-brief .bs-hl,.bs-col.bs-tmpl-brief .bs-hl{font-size:.92rem}
.bs-tmpl-brief .bs-kicker,.bs-col.bs-tmpl-brief .bs-kicker{font-size:.5rem}
.bs-tmpl-brief .bs-quote,.bs-col.bs-tmpl-brief .bs-quote{font-size:.74rem;padding-left:.4rem}
.bs-hero{margin:0 0 .5rem}
.bs-hero img{width:100%;display:block;border:1px solid var(--g)}
.bs-jump{font-size:.60rem;letter-spacing:.05em;text-transform:uppercase;font-weight:700;
  padding:.3rem 0;border-top:1px solid var(--g);margin-top:.4rem;text-indent:0;color:var(--accent)}
.bs-jump-from{border-top:none;border-bottom:1px solid var(--g);margin:0 0 .4rem;color:var(--ink)}
.bs-jump-from em{font-style:italic;text-transform:none;letter-spacing:0}
.bs-foot{position:absolute;left:12mm;right:12mm;bottom:6mm;display:flex;justify-content:space-between;
  font-size:.58rem;letter-spacing:.10em;text-transform:uppercase;color:var(--g);border-top:2px solid #d4cfc0;padding-top:.5rem}
.bs-foot::before{content:"";position:absolute;top:-5px;left:50%;transform:translateX(-50%);
  width:3px;height:10px;background:var(--accent)}
.bs-section-head{border-bottom:3px double var(--ink);margin-bottom:1rem;padding-bottom:0.5rem;page-break-inside:avoid}
.bs-section-head h2{font-family:"Playfair Display","Georgia",serif;font-weight:900;font-size:2.3rem;margin:0;font-variant:small-caps}
.bs-section-sub{font-style:italic;color:var(--g);font-size:.85rem}
.bs-colcards{display:grid;grid-template-columns:repeat(3,1fr);gap:6mm}
.bs-colcard{border:1px solid #d4cfc0;padding:0.8rem;page-break-inside:avoid}
.bs-colcard-img{height:125px;overflow:hidden;border:1px solid var(--g);margin-bottom:.5rem;background:var(--paper);
  display:flex;align-items:center;justify-content:center}
.bs-colcard-img img{width:100%;height:100%;object-fit:contain}
.bs-colcard-kick{font-size:.54rem;letter-spacing:.16em;text-transform:uppercase;color:#7a2018;font-weight:700;margin-bottom:.15rem}
.bs-colcard-title{font-family:"Playfair Display",serif;font-weight:700;font-size:1.05rem;line-height:1.15;margin:0.1rem 0}
.bs-colcard-sub{font-style:italic;font-size:.80rem;color:#352f24;margin:.3rem 0}
.bs-colcard-date{font-size:.58rem;letter-spacing:.11em;text-transform:uppercase;color:var(--g);margin-top:.4rem}
.bs-backgrid{display:grid;grid-template-columns:1fr 1fr;gap:10mm;align-items:start}
.bs-puzzle{text-align:center;page-break-inside:avoid}
.bsk-grid{display:grid;grid-template-columns:repeat(9,1fr);width:75%;margin:0 auto;border:2.5px solid var(--ink)}
.bsk-cell{aspect-ratio:1;display:flex;align-items:center;justify-content:center;border:1px solid #b3ab98;
  font-size:1.05rem;font-weight:600}
.bsk-rb{border-right:2px solid var(--ink)}
.bsk-bb{border-bottom:2px solid var(--ink)}
.bsw-grid{display:grid;width:88%;margin:0 auto;border:2px solid var(--ink)}
.bsw-cell{aspect-ratio:1;display:flex;align-items:center;justify-content:center;border:.5px solid #b3ab98;
  font-size:.62rem;font-weight:600;letter-spacing:.02em}
.bsw-words{margin-top:.4rem;font-size:.56rem;letter-spacing:.06em;text-transform:uppercase;color:var(--g);
  display:flex;flex-wrap:wrap;gap:.5em;justify-content:center}
.bsc-grid{display:flex;flex-direction:column;gap:5px;align-items:center}
.bsc-row{display:flex;gap:2px}
.bsc-cell{width:1.05em;height:1.4em;border-bottom:1px solid var(--ink);display:flex;align-items:flex-end;
  justify-content:center;font-size:.6rem;font-weight:600;padding-bottom:1px}
.bsc-gap{width:.6em}
.bs-puzzle-cap{font-style:italic;color:var(--g);margin-top:.8rem;font-size:.80rem;line-height:1.35}
.bs-supp-head{font-family:"Playfair Display",serif;font-weight:700;font-size:1.25rem;margin-bottom:0.8rem;border-bottom:1px solid #d4cfc0;padding-bottom:0.4rem}
.bs-supp{display:grid;grid-template-columns:68px 1fr;gap:.7rem;align-items:flex-start;margin-bottom:0.9rem;page-break-inside:avoid}
.bs-qr{width:68px;height:68px;flex-shrink:0}
.bs-qr-x{display:flex;align-items:center;justify-content:center;border:1px solid var(--g);color:var(--g);width:68px;height:68px;font-size:.65rem}
.bs-supp-l{font-weight:700;font-size:.88rem;line-height:1.2}
.bs-supp-n{grid-column:2;font-size:.70rem;color:#5a5247;line-height:1.35}
.bs-supp-wrap{}
.bs-colophon{grid-column:1/-1;margin-top:1.2rem;border-top:2px solid #d4cfc0;padding-top:0.8rem;font-size:.70rem;line-height:1.42;color:#352f24}
.bs-egg{user-select:none}
.bs-credit{display:block;font-style:italic;opacity:.75;margin-top:.1rem}
.bs-tmpl-feature .bs-grid{grid-template-columns:repeat(2,1fr)}
.bs-tmpl-feature .bs-col p,.bs-col.bs-tmpl-feature p{font-size:.92rem;line-height:1.56}
.bs-tmpl-feature .bs-col p[data-role="lede"]::first-letter,
.bs-tmpl-feature .bs-col > p:first-of-type::first-letter,
.bs-col.bs-tmpl-feature > p:first-of-type::first-letter{
  float:left;font-family:"Playfair Display",serif;font-weight:900;font-size:3.1em;
  line-height:.78;padding:.03em .06em 0 0;color:var(--accent)}
.bs-tmpl-feature .bs-quote,.bs-col.bs-tmpl-feature .bs-quote{font-size:1.05rem;padding-left:1rem;border-left-width:4px}
.bs-tmpl-feature .bs-hl,.bs-col.bs-tmpl-feature .bs-hl{font-size:1.4rem}
.bs-col.bs-tmpl-feature .bs-fig-feat img{max-height:none}
.bs-tmpl-label{font-size:.56rem;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
  font-weight:700;margin-bottom:.5rem;grid-column:1/-1}
.bs-backcover{position:absolute;inset:0;overflow:hidden}
.bs-backcover-art{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.bs-backcover-plate{position:absolute;inset:0;background:radial-gradient(ellipse at center,rgba(244,239,226,.0) 0%,rgba(244,239,226,.0) 45%,rgba(244,239,226,.55) 100%)}
.bs-backcover-mono{position:absolute;top:50%;left:50%;transform:translate(-50%,-165mm);
  width:34mm;height:34mm;border-radius:50%;background:var(--paper);border:2px solid var(--ink);
  display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 6px rgba(244,239,226,.55)}
.bs-backcover-mono img{width:70%;height:70%;object-fit:contain}
.bs-backcover-mono-fallback{font-family:"Playfair Display",serif;font-weight:900;font-size:1.35rem;
  letter-spacing:.02em;color:var(--ink)}
.bs-backcover-qr-wrap{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  display:flex;flex-direction:column;align-items:center;background:var(--paper);
  border:2px solid var(--ink);padding:8mm 10mm 6mm;box-shadow:0 0 0 6px rgba(244,239,226,.55)}
.bs-backcover-qr-wrap img{width:38mm;height:38mm}
.bs-backcover-qr-label{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--g);margin-top:.5rem}
.bs-backcover-foot{position:absolute;left:0;right:0;bottom:34mm;text-align:center;
  font-family:"Playfair Display",serif;font-size:.78rem;letter-spacing:.08em;color:var(--ink);
  background:rgba(244,239,226,.72);padding:.3rem 0}
@media print{body{margin:0;padding:0}}
</style></head><body>
__BODY__
</body></html>'''


def _bs_stylesheet():
    m = re.search(r'<style>(.*?)</style>', _BS_DOC, re.S)
    return m.group(1) if m else ''


def _bs_scatter_eggs(free: list, rng, start_idx: int, words=None):
    pieces = []
    idx = start_idx
    for r in free:
        if not (14.0 <= r['w'] <= 70.0 and 14.0 <= r['h'] <= 70.0):
            continue
        if rng.random() > 0.4:
            continue
        box_w = min(r['w'] * 0.9, 42.0)
        box_h = min(r['h'] * 0.6, 12.0)
        cx = r['x'] + r['w'] / 2 - box_w / 2
        cy = r['y'] + r['h'] / 2 - box_h / 2
        html = (f'<div style="width:{box_w}mm;height:{box_h}mm;display:flex;'
                f'align-items:center;justify-content:center;font-size:{box_h * 0.75}mm;overflow:hidden">'
                f'{_bs_egg(idx, words)}</div>')
        pieces.append({'x': cx, 'y': cy, 'w': box_w, 'h': box_h, 'html': html})
        idx += 1
    return pieces, idx


def _bs_scatter_ornaments(free: list, rng):
    pieces = []
    keep = []
    for r in free:
        short_side = min(r['w'], r['h'])
        if not (10.0 <= short_side and r['w'] <= 140.0 and r['h'] <= 140.0) or rng.random() > 0.5:
            keep.append(r)
            continue
        seed = int(hashlib.md5(f"{r['x']:.1f}:{r['y']:.1f}:{r['w']:.1f}:{r['h']:.1f}".encode()).hexdigest()[:6], 16)
        thickness = 2 + (seed % 5)
        length_pct = 35 + (seed // 5 % 45)
        vertical = r['h'] >= r['w']
        if vertical:
            bar_h = r['h'] * length_pct / 100.0
            bar_html = (f'<div style="position:absolute;left:50%;top:{(r["h"] - bar_h) / 2}mm;'
                        f'height:{bar_h}mm;width:{thickness}px;background:var(--accent);'
                        f'transform:translateX(-50%)"></div>')
        else:
            bar_w = r['w'] * length_pct / 100.0
            bar_html = (f'<div style="position:absolute;top:50%;left:{(r["w"] - bar_w) / 2}mm;'
                        f'width:{bar_w}mm;height:{thickness}px;background:var(--accent);'
                        f'transform:translateY(-50%)"></div>')
        html = f'<div style="position:relative;width:{r["w"]}mm;height:{r["h"]}mm">{bar_html}</div>'
        pieces.append({'x': r['x'], 'y': r['y'], 'w': r['w'], 'h': r['h'], 'html': html})
    free[:] = keep
    return pieces


def _bs_front_extras(config: dict, ym: str, edition: str, quote_frags: list, avail_w: float,
                      haiku_lines=None, egg_words=None):
    pub = config.get('publication', {})
    contact = config.get('contact', {})
    pieces = []

    seed = int(hashlib.md5(ym.encode()).hexdigest()[:8], 16)
    grid = _bs_sudoku(seed)
    side = min(avail_w * 0.50, 108.0)
    pieces.append({'w': side, 'h': side + 10.0,
                    'html': f'<div class="bs-front-puzzle">{_bs_sudoku_html(grid)}'
                            f'<div class="bs-front-puzzle-cap">This Month\'s Sudoku</div></div>'})

    if egg_words and len(egg_words) >= 3:
        ws_grid, ws_placed = _bs_wordsearch(seed + 1, egg_words, size=12)
        if ws_placed:
            side = min(avail_w * 0.46, 96.0)
            pieces.append({'w': side, 'h': side + 18.0,
                            'html': f'<div class="bs-front-puzzle">{_bs_wordsearch_html(ws_grid, ws_placed)}'
                                    f'<div class="bs-front-puzzle-cap">Word Search</div></div>'})

    crypto_source = None
    if quote_frags:
        crypto_source = BeautifulSoup(quote_frags[0]['html'], 'html.parser').get_text()
    elif haiku_lines:
        crypto_source = ' '.join(haiku_lines)
    if crypto_source:
        crypto_source = crypto_source[:90]
        cipher = _bs_cryptogram(seed + 2, crypto_source)
        w = min(avail_w * 0.44, 100.0)
        n_rows = -(-len(cipher) // 24)
        pieces.append({'w': w, 'h': 22.0 + n_rows * 13.0,
                        'html': f'<div class="bs-front-puzzle">{_bs_cryptogram_html(cipher)}'
                                f'<div class="bs-front-puzzle-cap">Cryptogram &mdash; decode this issue\'s quote</div></div>'})

    if haiku_lines:
        pieces.append({'w': min(avail_w * 0.30, 86.0), 'h': 46.0,
                        'html': '<div class="bs-front-haiku">' +
                                ''.join(f'<div>{_esc(l)}</div>' for l in haiku_lines) +
                                '<div class="bs-front-haiku-cap">This Issue\'s Haiku</div></div>'})

    logo = _logo_b64()
    if logo:
        side = min(avail_w * 0.20, 40.0)
        pieces.append({'w': side, 'h': side,
                        'html': f'<div class="bs-front-logo"><img src="{logo}" alt="{_esc(pub.get("name", ""))}"></div>'})

    pieces.append({'w': min(avail_w * 0.34, 110.0), 'h': 34.0,
                    'html': f'<div class="bs-front-monthyear">{_esc(edition.upper())}</div>'})

    website = (contact.get('website') or pub.get('website') or '').strip()
    if website:
        qr = _bs_qr(website)
        if qr:
            pieces.append({'w': 38.0, 'h': 44.0,
                            'html': f'<div class="bs-front-qr"><img src="{qr}" alt="QR">'
                                    f'<div class="bs-front-qr-label">Read online</div></div>'})

    def _bare(u):
        return u.replace('https://', '').replace('http://', '').rstrip('/') if u else ''
    links = [l for l in (
        _bare(website),
        contact.get('email', ''),
        _bare(contact.get('emag', '')),
    ) if l]
    if links:
        pieces.append({'w': min(avail_w * 0.26, 74.0), 'h': 16.0 + 12.0 * len(links),
                        'html': '<div class="bs-front-links">' + ''.join(f'<div>{_esc(l)}</div>' for l in links) + '</div>'})

    short_quotes = [f for f in quote_frags
                    if len(BeautifulSoup(f['html'], 'html.parser').get_text()) < 130][:2]
    for i, f in enumerate(short_quotes):
        text = BeautifulSoup(f['html'], 'html.parser').get_text()
        w, h = min(avail_w * 0.30, 90.0), 58.0
        if i % 2 == 0:
            html = (f'<div style="width:{w}mm;height:{h}mm;display:flex;align-items:center;'
                    f'justify-content:center;transform:rotate(180deg)">'
                    f'<span class="bs-front-quote">{_esc(text)}</span></div>')
        else:
            html = (f'<div style="width:{w}mm;height:{h}mm;display:flex;align-items:center;'
                    f'justify-content:center;overflow:hidden">'
                    f'<span class="bs-front-quote" style="display:inline-block;max-width:{h * 0.85}mm;'
                    f'transform:rotate(90deg)">{_esc(text)}</span></div>')
        pieces.append({'w': w, 'h': h, 'html': html})

    for _ in range(5):
        pieces.append({'w': 64.0, 'h': 15.0, 'html': '<div class="bs-front-wordmark">The Voice Express</div>'})

    return pieces


_BS_SQUARE_MIN_CHARS = 220


def _bs_col_count(content_w: float) -> int:
    return max(6, round(content_w / 48.0))


def _bs_col_unit(content_w: float) -> float:
    cols = _bs_col_count(content_w)
    return (content_w - (cols - 1) * _BS_GUTTER) / cols


def _bs_span_width(span: int, content_w: float) -> float:
    unit = _bs_col_unit(content_w)
    return min(content_w, span * unit + (span - 1) * _BS_GUTTER)


def _bs_role_span(role: str, content_w: float, signal=None) -> int:
    cols = _bs_col_count(content_w)
    if role == 'headline':
        n = len(signal or '')
        span = 2 if n < 40 else (3 if n < 80 else 4)
    elif role == 'lede':
        span = 2
    elif role == 'body':
        n = signal or 0
        span = 2 if n < 420 else 1
    elif role in ('brief', 'quote'):
        span = 1
    elif role == 'list':
        span = 2 if (signal or 0) > 4 else 1
    elif role == 'photo':
        span = 3 if (signal or 1.0) >= 0.85 else 2
    elif role == 'photo-group':
        span = {'wide': 4, 'square': 3, 'tall': 2}.get(signal or 'square', 3)
    else:
        span = 2
    return max(1, min(cols, span))


_BS_MERGE_TARGET_CHARS = 260


def _bs_merge_text_frags(body: list) -> list:
    merged = []
    buf_html, buf_chars = [], 0

    def flush():
        nonlocal buf_html, buf_chars
        if buf_chars > 0:
            merged.append({'html': ''.join(buf_html), 'kind': 'text', 'chars': buf_chars})
            buf_html, buf_chars = [], 0

    for frag in body:
        if frag.get('kind') == 'text':
            buf_html.append(frag['html'])
            buf_chars += frag.get('chars', 0)
            if buf_chars >= _BS_MERGE_TARGET_CHARS:
                flush()
        elif frag.get('kind') == 'heading':
            flush()
            buf_html.append(frag['html'])
        else:
            flush()
            if buf_html:
                frag = {**frag, 'label_html': ''.join(buf_html)}
                buf_html = []
            merged.append(frag)
    if buf_html:
        merged.append({'html': ''.join(buf_html), 'kind': 'text', 'chars': 0})
    else:
        flush()
    return merged


def _bs_blast_articles(articles, static_root):
    out = []
    for a in articles:
        st = _story(a, static_root)
        aid = a['id']
        out.append({'article_id': aid, 'order': 0, 'kind': 'heading', 'role': 'headline',
                     'html': _bs_render_head(st['head']), 'title': st['title'],
                     'section': st.get('section')})
        first_body_seen = False
        for i, frag in enumerate(_bs_merge_text_frags(st['body'])):
            if frag.get('kind') == 'text':
                if not first_body_seen:
                    role = 'lede'
                    first_body_seen = True
                elif frag.get('chars', 0) < _BS_SQUARE_MIN_CHARS:
                    role = 'brief'
                else:
                    role = 'body'
                frag = {**frag, 'role': role}
            out.append({**frag, 'article_id': aid, 'order': i + 1,
                        'title': st['title'], 'section': st.get('section')})
    return out


def _bs_blast_columns(ym: str, static_root: str, date_from: str = None, date_to: str = None,
                      entry_ids=None):
    out = []
    custom_window = bool(entry_ids) or bool(date_from and date_to)
    try:
        db = get_db()
        try:
            base_sel = ("SELECT ce.id, ce.column_id, ce.entry_date, ce.title, ce.cover_image, "
                        "       c.title AS column_title, c.cadence, c.period_days "
                        "FROM column_entries ce JOIN columns c ON ce.column_id = c.id "
                        "WHERE ce.status='published' AND c.is_private=0 ")
            base_pan = ("SELECT cp.entry_id, cp.image FROM column_panels cp "
                        "JOIN column_entries ce ON cp.entry_id = ce.id "
                        "JOIN columns c ON ce.column_id = c.id "
                        "WHERE ce.status='published' AND c.is_private=0 ")
            if entry_ids:
                ids = [int(i) for i in entry_ids]
                qs = ','.join('?' * len(ids))
                where, params = f'AND ce.id IN ({qs}) ', ids
            elif date_from and date_to:
                where = 'AND date(ce.entry_date) BETWEEN date(?) AND date(?) '
                params = [date_from, date_to]
            else:
                where, params = "AND strftime('%Y-%m', ce.entry_date)=? ", [ym]
            rows = db.execute(base_sel + where + 'ORDER BY c.id, ce.entry_date', params).fetchall()
            if not rows:
                return out
            panel_rows = db.execute(base_pan + where + 'ORDER BY cp.entry_id, cp.sort_order',
                                    params).fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f'[dtp_engine] column blast lookup failed: {e}')
        return out

    first_panel_img = {}
    for r in panel_rows:
        first_panel_img.setdefault(r['entry_id'], r['image'])

    by_col: dict = {}
    for r in rows:
        info = by_col.setdefault(r['column_id'], {'title': r['column_title'], 'cadence': r['cadence'],
                                                   'period_days': r['period_days'], 'entries': []})
        info['entries'].append(r)

    if custom_window:
        _dates = sorted(r['entry_date'] for r in rows if r['entry_date'])
        _start = date_from or (_dates[0] if _dates else None)
        _end   = date_to   or (_dates[-1] if _dates else None)
        first_of_month = datetime.strptime(_start[:10], '%Y-%m-%d') if _start else datetime(1970, 1, 1)
        _last          = datetime.strptime(_end[:10], '%Y-%m-%d') if _end else first_of_month
        days_in_month  = max(1, (_last - first_of_month).days + 1)
        year, month    = first_of_month.year, first_of_month.month
    else:
        year, month = (int(x) for x in ym.split('-'))
        days_in_month = calendar.monthrange(year, month)[1]
        first_of_month = datetime(year, month, 1)

    def _square_grid(n_expected):
        n_expected = max(1, int(n_expected))
        c = max(1, round(n_expected ** 0.5))
        return c, math.ceil(n_expected / c)

    for cid, info in by_col.items():
        cadence = (info['cadence'] or 'weekly').lower()
        entries = info['entries']

        if custom_window and cadence in ('daily', 'weekly', 'monthly'):
            _per = {'daily': 1, 'weekly': 7, 'monthly': 30}[cadence]
            cols_n, rows_n = _square_grid(math.ceil(days_in_month / _per))
            def cell_of(r, _fom=first_of_month, _p=_per, _cap=cols_n * rows_n):
                return min(max(0, (datetime.strptime(r['entry_date'][:10], '%Y-%m-%d') - _fom).days // _p),
                           _cap - 1)
        elif cadence == 'daily':
            cols_n, rows_n = 8, 4
            def cell_of(r):
                return int(r['entry_date'][-2:]) - 1
        elif cadence == 'monthly':
            cols_n = rows_n = 1
            def cell_of(r):
                return 0
        elif cadence == 'weekly':
            cols_n, rows_n = 3, 2
            def cell_of(r, _fom=first_of_month):
                return (datetime.strptime(r['entry_date'], '%Y-%m-%d') - _fom).days // 7
        else:
            period = max(1, int(info['period_days'] or 7))
            n_expected = max(1, math.ceil(days_in_month / period))
            cols_n = max(1, round(n_expected ** 0.5))
            rows_n = math.ceil(n_expected / cols_n)
            def cell_of(r, _fom=first_of_month, _p=period, _cap=cols_n * rows_n):
                return min((datetime.strptime(r['entry_date'], '%Y-%m-%d') - _fom).days // _p, _cap - 1)

        cells = [''] * (cols_n * rows_n)
        for r in entries:
            idx = cell_of(r)
            if not (0 <= idx < len(cells)):
                continue
            img_src = r['cover_image'] or first_panel_img.get(r['id'])
            label = (r['entry_date'][-2:] if cadence == 'daily' else
                    f'Wk {cell_of(r) + 1}' if cadence == 'weekly' else r['entry_date'])
            if img_src:
                embedded = _bs_embed(img_src, static_root)
                cell_html = (f'<figure><img src="{embedded}" alt="{_esc(r["title"])}">'
                             f'<figcaption>{_esc(label)}</figcaption></figure>')
            else:
                cell_html = f'<div class="bs-colcal-text"><span>{_esc(label)}</span>{_esc(r["title"][:40])}</div>'
            cells[idx] = cell_html

        grid_html = (f'<div class="bs-strip bs-colcal" data-type="{_esc(cadence)}" '
                     f'style="grid-template-columns:repeat({cols_n},1fr)">' +
                     ''.join(c or '<div class="bs-colcal-empty"></div>' for c in cells) + '</div>')
        n_real = sum(1 for c in cells if c)
        aid = f'col-{cid}'
        out.append({'article_id': aid, 'order': 0, 'kind': 'heading', 'role': 'headline',
                     'html': f'<div class="bs-head"><div class="bs-kicker">COLUMNS</div>'
                             f'<h2 class="bs-hl">{_esc(info["title"])}</h2>'
                             f'<div class="bs-deck">This month\'s {_esc(cadence)} entries</div></div>',
                     'title': info['title'], 'section': 'COLUMNS'})
        out.append({'article_id': aid, 'order': 1, 'kind': 'photo-group',
                     'group_type': cadence, 'shape': 'square', 'n': n_real,
                     'html': grid_html, 'title': info['title'], 'section': 'COLUMNS'})
    return out


_BS_GUTTER = 5.0


def _bs_try_place(free: list, w: float, h: float, gutter: float = 0.0):
    gw, gh = w + gutter, h + gutter
    best_i, best_waste = None, None
    for i, r in enumerate(free):
        if r['w'] >= gw and r['h'] >= gh:
            waste = r['w'] * r['h'] - gw * gh
            if best_waste is None or waste < best_waste:
                best_waste, best_i = waste, i
    if best_i is None:
        return None
    r = free.pop(best_i)
    right_w = r['w'] - gw
    bottom_h = r['h'] - gh
    if right_w > 12.0:
        free.append({'x': r['x'] + gw, 'y': r['y'], 'w': right_w, 'h': gh})
    if bottom_h > 12.0:
        free.append({'x': r['x'], 'y': r['y'] + gh, 'w': r['w'], 'h': bottom_h})
    return {'x': r['x'] + gutter / 2, 'y': r['y'] + gutter / 2}


_BS_ROW_GAP = 2.0


_BS_MIN_MODULE_H = 20.0


def _bs_skyline_window(skyline: list, span: int):
    n = len(skyline)
    span = max(1, min(n, span))
    best_c, best_top = None, None
    for c in range(n - span + 1):
        top = max(skyline[c:c + span])
        if best_top is None or top < best_top - 1e-6:
            best_top, best_c = top, c
    return best_c, best_top


def _bs_module_html(head_html: str, body_frags: list, span: int) -> str:
    head = f'<div class="bs-mod-head">{head_html}</div>' if head_html else ''
    body = ''.join((f.get('label_html') or '') + f['html'] for f in body_frags)
    col_css = f'column-count:{span};' if span > 1 else ''
    return (f'<div class="bs-module">{head}'
            f'<div class="bs-mod-body" style="{col_css}">{body}</div></div>')


def _bs_module_pack_pages(all_frags: list, dims: dict, css: str, side_margin: float,
                          top_margin: float, start_folio: int, pub: dict, edition: str,
                          egg_words=None, front_geom: dict = None, front_extras: list = None):
    if not all_frags:
        return [], {}

    content_w = dims['w'] - 2 * side_margin
    chrome_y = top_margin + 14.0
    content_h = dims['h'] - chrome_y - 30.0
    cols = _bs_col_count(content_w)
    col_unit = _bs_col_unit(content_w)

    pw_ctx = browser = pw_page = None
    try:
        from playwright.sync_api import sync_playwright
        pw_ctx = sync_playwright().start()
        try:
            browser = pw_ctx.chromium.launch(channel='chrome', headless=True)
        except Exception:
            browser = pw_ctx.chromium.launch(headless=True)
        pw_page = browser.new_page()
    except Exception as e:
        print(f'[dtp_engine] module-pack fitting unavailable ({e}) -- dumping all content onto one page')

    stories: dict = {}
    for f in all_frags:
        s = stories.setdefault(f['article_id'], {'head': None, 'body': [], 'title': f.get('title', ''),
                                                  'section': f.get('section')})
        if f.get('order', 0) == 0:
            s['head'] = f
        else:
            s['body'].append(f)
    for s in stories.values():
        s['body'].sort(key=lambda f: f['order'])
        s['chars'] = sum(f.get('chars', 0) or 0 for f in s['body'])

    queue = sorted(stories.items(), key=lambda kv: -kv[1]['chars'])
    pending = [{'aid': aid, **s, 'mod': 0} for aid, s in queue]

    def measure(head_html, frags, span):
        w = _bs_span_width(span, content_w)
        if pw_page is None:
            return w, 40.0
        h = _measure_html_height_mm(pw_page, _bs_module_html(head_html, frags, span), css, w)
        return w, max(5.0, h)

    page_modules = []
    module_page: dict = {}
    egg_idx = 0

    pi = 0
    try:
        while pending and pi < 500:
            rng = random.Random(int(hashlib.md5(f'{edition}:{pi}'.encode()).hexdigest()[:8], 16))
            is_front = bool(front_geom) and pi == 0
            page_y = front_geom['y'] if is_front else chrome_y
            page_h = front_geom['h'] if is_front else content_h
            skyline = [0.0] * cols
            placed_this_page = []
            progressed = True
            while progressed and pending:
                progressed = False
                for si, st in enumerate(list(pending)):
                    if not st['body'] and st['mod'] > 0:
                        pending.remove(st)
                        continue
                    if st['mod'] == 0:
                        span = min(cols, 4 if st['chars'] > 2600 else (3 if st['chars'] > 1200 else 2))
                    else:
                        span = min(cols, 2)
                    c, top = _bs_skyline_window(skyline, span)
                    avail = page_h - top
                    while avail < _BS_MIN_MODULE_H and span > 1:
                        span -= 1
                        c, top = _bs_skyline_window(skyline, span)
                        avail = page_h - top
                    if c is None or avail < _BS_MIN_MODULE_H:
                        continue
                    head_html = st['head']['html'] if (st['mod'] == 0 and st.get('head')) else ''
                    frags = st['body']
                    w, h_all = measure(head_html, frags, span)
                    if h_all <= avail:
                        k, h_fit = len(frags), h_all
                    else:
                        lo, hi, k, h_fit = 0, len(frags), 0, 0.0
                        while lo <= hi:
                            mid = (lo + hi) // 2
                            _, hm = measure(head_html, frags[:mid], span)
                            if hm <= avail:
                                k, h_fit = mid, hm
                                lo = mid + 1
                            else:
                                hi = mid - 1
                    if k == 0:
                        if head_html and not placed_this_page:
                            _, h_fit = measure(head_html, [], span)
                            if h_fit <= avail:
                                k = 0
                            else:
                                continue
                        else:
                            continue
                    x = c * (col_unit + _BS_GUTTER)
                    placed_this_page.append({
                        'x': x, 'y': top, 'w': w, 'h': h_fit, 'span': span,
                        'aid': st['aid'], 'mod': st['mod'], 'head_html': head_html,
                        'frags': frags[:k], 'title': st['title'], 'section': st['section'],
                    })
                    module_page[(st['aid'], st['mod'])] = pi
                    new_top = top + h_fit + _BS_ROW_GAP
                    for i in range(c, c + span):
                        skyline[i] = new_top
                    st['body'] = frags[k:]
                    st['mod'] += 1
                    if not st['body']:
                        pending.remove(st)
                    progressed = True
            if not placed_this_page:
                break
            free = []
            c = 0
            while c < cols:
                h_left = page_h - skyline[c]
                if h_left > 1.0:
                    span = 1
                    while c + span < cols and abs((page_h - skyline[c + span]) - h_left) < 0.5:
                        span += 1
                    free.append({'x': c * (col_unit + _BS_GUTTER), 'y': skyline[c],
                                 'w': span * col_unit + (span - 1) * _BS_GUTTER, 'h': h_left})
                    c += span
                else:
                    c += 1
            extras_placed = []
            if is_front and front_extras:
                for piece in sorted(front_extras, key=lambda p: -(p['w'] * p['h'])):
                    spot = _bs_try_place(free, piece['w'], piece['h'], gutter=_BS_GUTTER)
                    if spot is None:
                        continue
                    extras_placed.append({'x': spot['x'], 'y': spot['y'],
                                          'w': piece['w'], 'h': piece['h'], 'html': piece['html']})
            ornaments = _bs_scatter_ornaments(free, rng)
            eggs, egg_idx = _bs_scatter_eggs(free, rng, egg_idx, egg_words)
            page_modules.append((placed_this_page, eggs, ornaments, page_y, is_front, extras_placed))
            pi += 1
    finally:
        if browser is not None:
            try: browser.close()
            except Exception: pass
        if pw_ctx is not None:
            try: pw_ctx.stop()
            except Exception: pass

    mods_by_article: dict = {}
    for (aid, m), p in module_page.items():
        mods_by_article.setdefault(aid, []).append((m, p))
    jump_to: dict = {}
    jump_from: dict = {}
    for aid, lst in mods_by_article.items():
        lst.sort()
        for (ma, pa), (mb, pb) in zip(lst, lst[1:]):
            if pa != pb:
                jump_to[(aid, ma)] = pb
                jump_from[(aid, mb)] = pa

    pages = []
    for pidx, (mods, eggs, ornaments, page_y, is_front, extras_placed) in enumerate(page_modules):
        folio = start_folio + pidx
        blocks = [] if is_front else [{
            'id': uuid.uuid4().hex[:8], 'type': 'bs_chrome', 'x': 0, 'y': 0,
            'w': dims['w'], 'h': dims['h'], 'front': False, 'pub_name': pub.get('name', ''),
            'edition': edition, 'folio': folio, 'total': 0, 'extra_css': css,
            'section': (mods[0].get('section') or '') if mods else '',
            'col_grid': {'side_margin': side_margin, 'chrome_y': chrome_y, 'content_h': content_h,
                         'cols': cols, 'col_unit': col_unit, 'gutter': _BS_GUTTER},
        }]
        for ex in extras_placed:
            blocks.append({
                'id': uuid.uuid4().hex[:8], 'type': 'bs_column',
                'x': side_margin + ex['x'], 'y': page_y + ex['y'],
                'w': ex['w'], 'h': ex['h'], 'items': [{'html': ex['html']}], 'extra_css': css,
                'template': '' if ('bs-front-quote' in ex['html'] or 'bs-front-wordmark' in ex['html'])
                            else 'bs-framed',
            })
        for m in mods:
            key = (m['aid'], m['mod'])
            head_html = m['head_html']
            if key in jump_from and not head_html:
                head_html = (f'<div class="bs-jump bs-jump-from"><em>{_esc((m.get("title") or "")[:54])}</em>'
                             f' · continued from page {start_folio + jump_from[key]} </div>')
            inner = _bs_module_html(head_html, m['frags'], m['span'])
            if key in jump_to:
                inner += (f'<div class="bs-jump bs-jump-to">Continued on page '
                          f'{start_folio + jump_to[key]} →</div>')
            blocks.append({
                'id': uuid.uuid4().hex[:8], 'type': 'bs_column',
                'x': side_margin + m['x'], 'y': page_y + m['y'],
                'w': m['w'], 'h': m['h'], 'items': [{'html': inner}], 'extra_css': css,
                'template': '',
            })
        for egg in eggs:
            blocks.append({'id': uuid.uuid4().hex[:8], 'type': 'bs_egg',
                           'x': side_margin + egg['x'], 'y': page_y + egg['y'],
                           'w': egg['w'], 'h': egg['h'], 'html': egg['html']})
        for orn in ornaments:
            blocks.append({'id': uuid.uuid4().hex[:8], 'type': 'bs_egg',
                           'x': side_margin + orn['x'], 'y': page_y + orn['y'],
                           'w': orn['w'], 'h': orn['h'], 'html': orn['html']})
        pages.append({'blocks': blocks})

    article_first_page = {aid: min(p for _, p in lst) for aid, lst in mods_by_article.items()}
    return pages, article_first_page


def _bs_blank_layout(n_pages, dims, css, pub, edition, side_margin, top_margin,
                     front_chrome_extra, content_w, egg_words):
    cols = _bs_col_count(content_w)
    col_unit = _bs_col_unit(content_w)
    pages, frame_ids = [], []
    for i in range(n_pages):
        front = (i == 0)
        chrome_y = top_margin + (front_chrome_extra + 6.0 if front else 0.0)
        content_h = max(40.0, dims['h'] - chrome_y - 30.0)
        chrome = {
            'id': uuid.uuid4().hex[:8], 'type': 'bs_chrome', 'x': 0, 'y': 0,
            'w': dims['w'], 'h': dims['h'], 'front': front, 'pub_name': pub.get('name', ''),
            'edition': edition, 'folio': i + 1, 'total': n_pages, 'extra_css': css,
            'col_grid': {'side_margin': side_margin, 'chrome_y': chrome_y,
                         'content_h': content_h, 'cols': cols, 'col_unit': col_unit,
                         'gutter': _BS_GUTTER},
        }
        blocks = [chrome]
        if front:
            blocks.append({
                'id': uuid.uuid4().hex[:8], 'type': 'bs_masthead', 'x': 0, 'y': top_margin,
                'w': dims['w'], 'h': front_chrome_extra, 'fit_box': True,
                'pub_name': pub.get('name', ''), 'edition': edition,
                'volume': pub.get('volume', ''), 'issue_note': pub.get('issue_note', ''),
                'tagline': pub.get('tagline', ''), 'website': pub.get('website', ''),
                'location': pub.get('location', ''), 'extra_css': css,
                'cover_note': '', 'toc_html': '', 'egg_words': egg_words,
            })
        for c in range(cols):
            bid = uuid.uuid4().hex[:8]
            frame_ids.append(bid)
            blocks.append({
                'id': bid, 'type': 'bs_column',
                'x': side_margin + c * (col_unit + _BS_GUTTER), 'y': chrome_y,
                'w': col_unit, 'h': content_h,
                'items': [], 'extra_css': css, 'template': '',
            })
        pages.append({'blocks': blocks})

    by_id = {b['id']: b for p in pages for b in p['blocks']}
    for a, nxt in zip(frame_ids, frame_ids[1:]):
        by_id[a]['link_next'] = nxt
    return {'preset': 'broadsheet', 'page': dims, 'pages': pages or [{'blocks': []}]}


def _month_has_column_entries(ym, date_from=None, date_to=None):
    db = get_db()
    try:
        if date_from and date_to:
            row = db.execute(
                "SELECT COUNT(*) n FROM column_entries WHERE status='published' "
                "AND substr(entry_date,1,10)>=? AND substr(entry_date,1,10)<=?",
                [date_from, date_to]).fetchone()
        else:
            row = db.execute(
                "SELECT COUNT(*) n FROM column_entries WHERE status='published' "
                "AND substr(entry_date,1,7)=?", [ym]).fetchone()
        return bool(row and row['n'])
    except sqlite3.OperationalError:
        return False
    finally:
        db.close()


def create_broadsheet_project(ym, articles=None, regenerate=False, enhancement: dict = None,
                              *, key=None, edition_label=None, kind='broadsheet', name=None,
                              date_from=None, date_to=None, entry_ids=None, blank_pages=0):
    if not re.match(r'^\d{4}-\d{2}$', ym or ''):
        return None
    key = str(key or ym)
    blank_pages = max(0, int(blank_pages or 0))
    existing = _find_existing(kind, key)
    if existing and not regenerate:
        return existing
    if articles is None and not blank_pages:
        articles = (get_articles_for_range(date_from, date_to) if (date_from and date_to)
                    else get_articles_for_month(ym))
    articles = articles or []
    if not articles and not blank_pages and not entry_ids:
        if not _month_has_column_entries(ym, date_from, date_to):
            return None
    enhancement = enhancement or {}
    year, month = (int(x) for x in ym.split('-'))
    config = _bs_load_config(None)
    pub = config.get('publication', {})
    month_name = calendar.month_name[month]
    edition = edition_label or f'{month_name} {year}'
    css = _bs_stylesheet()
    accent_css = f':root{{--accent:{enhancement["accent"]}}}' if enhancement.get('accent') else ''
    extra_css_user = enhancement.get('extra_css') or ''
    if accent_css or extra_css_user:
        css = css + '\n' + accent_css + '\n' + extra_css_user

    bs_cfg = config.get('broadsheet', {}) or {}
    dims = PAGE_PRESETS['broadsheet']
    top_margin = 11.0
    side_margin = 20.0
    content_w = dims['w'] - 2 * side_margin

    egg_words, haiku_lines = _bs_edition_words(ym)

    front_chrome_extra = 34.0
    if articles:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as _pw:
                try:
                    _pw_browser = _pw.chromium.launch(channel='chrome', headless=True)
                except Exception:
                    _pw_browser = _pw.chromium.launch(headless=True)
                _pw_page = _pw_browser.new_page()
                mast_html = _bs_masthead(pub, edition, pub.get('volume', ''), pub.get('issue_note', ''), egg_words)
                doc = (f'<!doctype html><html><head><style>{css}</style>'
                       f'<style>body{{margin:0}}#box{{width:{dims["w"]}mm}}</style></head>'
                       f'<body><div id="box">{mast_html}</div></body></html>')
                _pw_page.set_content(doc, wait_until='domcontentloaded', timeout=8000)
                h_px = _pw_page.eval_on_selector('#box', 'el => el.scrollHeight')
                front_chrome_extra = max(24.0, h_px / 3.7795275591 + 4.0)
                _pw_browser.close()
        except Exception as e:
            print(f'[dtp_engine] broadsheet masthead measurement failed, using default: {e}')

    if blank_pages:
        layout = _bs_blank_layout(blank_pages, dims, css, pub, edition, side_margin,
                                  top_margin, front_chrome_extra, content_w, egg_words)
        if existing:
            return _regenerate_layout(existing, layout)
        return _create(name or f'Broadsheet {key}', kind, key, layout)

    all_frags = (_bs_blast_articles(articles, STATIC_ROOT)
                 + _bs_blast_columns(ym, STATIC_ROOT, date_from=date_from,
                                     date_to=date_to, entry_ids=entry_ids))

    front_extra_y = top_margin + front_chrome_extra + 6.0
    front_extra_h = max(40.0, dims['h'] - front_extra_y - 30.0)
    quote_frags = [f for f in all_frags if f.get('kind') == 'quote']
    extras = _bs_front_extras(config, ym, edition, quote_frags, content_w, haiku_lines, egg_words)
    all_pages, article_first_page = _bs_module_pack_pages(
        all_frags, dims, css, side_margin, top_margin, 1, pub, edition, egg_words,
        front_geom={'y': front_extra_y, 'h': front_extra_h}, front_extras=extras)
    front_content_blocks = all_pages[0]['blocks'] if all_pages else []
    inner_pages = all_pages[1:]

    columns = []
    has_cols = bool(columns)
    has_puzzle = bs_cfg.get('include_sudoku', True)
    n_content_pages = 1 + len(inner_pages)
    total = n_content_pages + (1 if has_cols else 0) + (1 if has_puzzle else 0)
    for p in inner_pages:
        for b in p['blocks']:
            if b.get('type') == 'bs_chrome':
                b['total'] = total

    front_blocks = [{
        'id': uuid.uuid4().hex[:8], 'type': 'bs_chrome', 'x': 0, 'y': 0,
        'w': dims['w'], 'h': dims['h'], 'front': True, 'pub_name': pub.get('name', ''),
        'edition': edition, 'folio': 1, 'total': total, 'extra_css': css,
    }, {
        'id': uuid.uuid4().hex[:8], 'type': 'bs_masthead', 'x': 0, 'y': top_margin,
        'w': dims['w'], 'h': front_chrome_extra, 'fit_box': True,
        'pub_name': pub.get('name', ''), 'edition': edition, 'volume': pub.get('volume', ''),
        'issue_note': pub.get('issue_note', ''), 'tagline': pub.get('tagline', ''),
        'website': pub.get('website', ''), 'location': pub.get('location', ''),
        'extra_css': css, 'cover_note': '', 'toc_html': '', 'egg_words': egg_words,
    }]

    front_blocks.extend(front_content_blocks)
    front_blocks[0]['col_grid'] = {
        'side_margin': side_margin, 'chrome_y': front_extra_y, 'content_h': front_extra_h,
        'cols': _bs_col_count(content_w), 'col_unit': _bs_col_unit(content_w), 'gutter': _BS_GUTTER,
    }

    pages = [{'blocks': front_blocks}]
    pages.extend(inner_pages)

    folio = n_content_pages
    if has_cols:
        folio += 1
        inner = _bs_sheet(_bs_columns_inner(columns, STATIC_ROOT), folio, total, pub.get('name', ''), edition)
        pages.append({'blocks': [_raw_page_block(dims, inner, css)]})
    if has_puzzle:
        folio += 1
        inner = _bs_sheet(_bs_backcover_inner(config, year, month, edition, ym, STATIC_ROOT),
                          folio, total, pub.get('name', ''), edition)
        pages.append({'blocks': [_raw_page_block(dims, inner, css)]})

    layout = {'preset': 'broadsheet', 'page': dims, 'pages': pages or [{'blocks': []}]}
    if existing:
        return _regenerate_layout(existing, layout)
    return _create(name or f'Broadsheet {key}', kind, key, layout)



def _bs_scroll_slug(i: int, title: str) -> str:
    base = re.sub(r'[^a-z0-9]+', '-', (title or '').lower()).strip('-')[:40]
    return f'story-{i}-{base}' if base else f'story-{i}'


_BS_SCROLL_CSS = '''
html{scroll-behavior:smooth}
.bs-scroll-page{max-width:920px;margin:0 auto;padding:14mm 5mm 0;background:var(--paper)}
.bs-scroll-page .bs-mast-name{font-size:3.4rem}
.bs-scroll-page .bs-mast-meta-l,.bs-scroll-page .bs-mast-meta-r{white-space:nowrap}
.bs-scroll-page .bs-col{border-right:none;text-align:justify;hyphens:auto}
.bs-scroll-page .bs-col > *{padding:0}
.bs-scroll-lead{margin-top:1.1rem}
.bs-scroll-secondary{margin:0}
.bs-scroll-story{border-top:1px solid #d4cfc0;padding-top:1.1rem;margin-top:1.5rem}
.bs-scroll-section{margin-bottom:0.5rem}
.bs-scroll-index{grid-template-columns:1fr!important}
.bs-scroll-index .bs-idx-row{flex-direction:row;align-items:baseline;gap:.8rem;white-space:normal}
.bs-scroll-index .bs-idx-t{overflow:visible;text-overflow:clip;white-space:normal;color:var(--ink);
  text-decoration:none;font-weight:600;flex:1 1 auto;min-width:0}
.bs-scroll-index .bs-idx-t:hover{text-decoration:underline;color:var(--accent)}
.bs-scroll-index .bs-idx-p{font-style:italic;font-weight:400;font-size:.6rem;letter-spacing:.08em;
  text-transform:uppercase;flex:0 0 auto}
.bs-scroll-back{margin:2.5rem auto 0;border-top:3px double var(--ink)}
.bs-scroll-foot{text-align:center;font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--g);padding:1.2rem 0 2rem}
'''


def build_broadsheet_scroll(ym, articles=None, static_root: str = None,
                            config: dict = None, enhancement: dict = None) -> str:
    if not re.match(r'^\d{4}-\d{2}$', ym or ''):
        return None
    if articles is None:
        articles = get_articles_for_month(ym)
    if not articles:
        return None
    enhancement = enhancement or {}
    year, month = (int(x) for x in ym.split('-'))
    static_root = static_root or STATIC_ROOT
    config = _bs_load_config(config)
    pub = config.get('publication', {})
    month_name = calendar.month_name[month]
    edition = f'{month_name} {year}'

    stories = [_story(a, static_root, lead=(i == 0)) for i, a in enumerate(articles)]
    for i, st in enumerate(stories):
        st['anchor'] = _bs_scroll_slug(i, st['title'])

    bs_cfg = config.get('broadsheet', {}) or {}
    articles_on_front = max(1, int(bs_cfg.get('articles_on_front', 3) or 3))
    lead = stories[0]
    secondary = stories[1:articles_on_front]
    rest = stories[articles_on_front:]

    def render_story(st):
        body_html = ''.join(item['html'] for item in st['body'])
        return (f'<article id="{st["anchor"]}" class="bs-scroll-story">'
                f'{_bs_render_head(st["head"])}<div class="bs-col">{body_html}</div></article>')

    lead_body_html = ''.join(item['html'] for item in lead['body'])
    lead_html = (f'<div id="{lead["anchor"]}" class="bs-scroll-lead">{_lead_banner(lead["head"])}'
                f'<div class="bs-col bs-tmpl-feature">{lead_body_html}</div></div>')
    secondary_html = ''.join(render_story(st) for st in secondary)

    groups: dict = {}
    order: list = []
    for st in rest:
        key = st.get('section') or 'MORE FROM THIS ISSUE'
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(st)
    sections_html = ''
    for key in order:
        cards = ''.join(render_story(st) for st in groups[key])
        sections_html += (f'<div class="bs-section-head"><h2>{_esc(key)}</h2></div>'
                          f'<div class="bs-scroll-section">{cards}</div>')

    toc_targets = secondary + rest
    index_html = ''
    if toc_targets:
        rows = ''.join(
            f'<div class="bs-idx-row"><a class="bs-idx-t" href="#{s["anchor"]}">{_esc(s["title"])}</a>'
            f'<span class="bs-idx-p">{_esc(s.get("section") or "")}</span></div>'
            for s in toc_targets)
        index_html = (f'<div class="bs-index bs-scroll-index"><span class="bs-sf-lbl">Inside This Issue</span>'
                     f'{rows}</div>')

    mast = _bs_masthead(pub, edition, pub.get('volume', ''), pub.get('issue_note', ''))
    back_inner = _bs_backcover_inner(config, year, month, edition, ym, static_root)
    back_html = (f'<section class="bs-sheet bs-scroll-back">{back_inner}</section>'
                f'<div class="bs-scroll-foot">{_esc(pub.get("name",""))} &middot; {_esc(edition)} '
                f'&middot; End of issue</div>')

    body = (f'<div class="bs-scroll-page">{mast}{index_html}{lead_html}'
            f'<div class="bs-scroll-secondary">{secondary_html}</div>'
            f'{sections_html}</div>{back_html}')

    accent_css = f':root{{--accent:{enhancement["accent"]}}}' if enhancement.get('accent') else ''
    extra_css = enhancement.get('extra_css') or ''
    doc = _BS_DOC.replace('__TITLE__', _esc(f'The Voice Express — {edition} — Broadsheet (Scroll)')) \
              .replace('__BODY__', body)
    doc = doc.replace('</style>', _BS_SCROLL_CSS + '\n' + accent_css + '\n' + extra_css + '\n</style>')
    return doc


import make_article_print as ap_mod


def _ap_stylesheet():
    m = re.search(r'<style>(.*?)</style>', ap_mod._DOC, re.S)
    return m.group(1) if m else ''


_ART_CONTENT_CSS = r'''
.art-content{
  --ac-ink:#0a0a0a;--ac-paper:#fafaf8;
  --ac-g100:#f2f2f0;--ac-g200:#e5e5e3;--ac-g300:#d0d0ce;
  --ac-g400:#a8a8a6;--ac-g500:#7a7a78;--ac-g600:#555553;--ac-g700:#3a3a38;
  --ac-fh:"Playfair Display",Georgia,serif;
  --ac-fb:"EB Garamond",Georgia,serif;
  --ac-fm:"Courier New",monospace;
  --ac-rule:1px solid var(--ac-ink);
  --ac-rt:1px solid var(--ac-g300);
  --ac-rk:3px solid var(--ac-ink);
  counter-reset:ve-sec;
  font-family:var(--ac-fb);font-size:1.0rem;line-height:1.66;color:var(--ac-ink);
  text-align:justify;hyphens:auto;-webkit-hyphens:auto;
  font-feature-settings:"kern" 1,"liga" 1,"onum" 1,"calt" 1;font-variant-numeric:oldstyle-nums;
}
.art-content p{margin:0}
.art-content p+p{text-indent:1.3em}
.art-content figure+p,.art-content h2+p,.art-content h3+p,.art-content blockquote+p,.art-content hr+p,
  .art-content .section-heading+p,.art-content .section-subheading+p,.art-content .ve-dropcap{text-indent:0}
.art-content .ve-dropcap{margin-top:.2em}
.art-content .ve-dropcap::first-letter{float:left;font-family:var(--ac-fh);font-size:3.6rem;line-height:.78;
  padding:.02em .12em 0 0;font-weight:900}
.art-content h2{font-family:var(--ac-fh);font-size:1.35rem;font-weight:700;margin:1.7em 0 .55em;line-height:1.2}
.art-content h3{font-family:var(--ac-fh);font-size:1.1rem;font-weight:600;margin:1.5em 0 .45em}
.art-content blockquote{font-family:var(--ac-fb);font-size:1.15rem;line-height:1.48;font-style:italic;
  color:var(--ac-g700);margin:1.6em 0 1.6em 1em;padding-left:1.1em;border-left:2px solid var(--ac-ink);
  text-align:left;break-inside:avoid;page-break-inside:avoid}
.art-content blockquote cite{display:block;font-family:var(--ac-fm);font-style:normal;font-size:.6rem;
  letter-spacing:.07em;text-transform:uppercase;color:var(--ac-g500);margin-top:.5em}
.art-content blockquote p,.art-content figcaption,.art-content .photo-caption,.art-content .photo-prose,
  .art-content .qa-line,.art-content .compare-item p,.art-content .intro-note,.art-content li,
  .art-content .pull-quote,.art-content .field-quote,.art-content .spoken-quote{text-indent:0;text-align:left}
.art-content a{text-decoration:underline;color:inherit}
.art-content ul,.art-content ol{padding-left:1.8rem;margin-bottom:1.3em}
.art-content li{margin-bottom:.3em}
.art-content img{margin:1.5em auto;border:var(--ac-rt);max-width:100%}
.art-divider{text-align:center;font-family:var(--ac-fh);font-size:1.1rem;color:var(--ac-g300);margin:2rem 0;letter-spacing:.4em}
.art-content p[data-text-role="dateline"]{font-family:var(--ac-fm);font-size:.66rem;letter-spacing:.07em;
  text-transform:uppercase;color:var(--ac-g600)}
.art-content p[data-text-role="note"],.art-content .intro-note,.art-content .italic-note{font-style:italic;
  color:var(--ac-g700);border-left:var(--ac-rt);padding-left:.9rem;margin:1.4em 0}
.art-content .article-deck{font-family:var(--ac-fb);font-size:1.15rem;font-style:italic;color:var(--ac-g700);
  line-height:1.46;margin:.2em 0 1.1em}
.art-content .article-section{counter-increment:ve-sec;border-top:var(--ac-rule);margin-top:2.2em;
  padding-top:1em;break-inside:avoid;page-break-inside:avoid}
.art-content .article-section>.section-heading::before{content:counter(ve-sec,decimal-leading-zero) " / ";
  font-family:var(--ac-fm);font-size:.6em;letter-spacing:.09em;color:var(--ac-g500);vertical-align:.3em}
.art-content .section-heading{font-family:var(--ac-fh);font-size:1.35rem;font-weight:700;line-height:1.18;margin:0 0 .55em}
.art-content .section-subheading{font-family:var(--ac-fm);font-size:.66rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ac-g500);margin:-.28em 0 .9em}
.art-content .section-divider,.art-content hr{border:none;border-top:var(--ac-rule);width:42%;margin:2em auto}
.art-content .pull-quote{font-family:var(--ac-fh);font-size:1.6rem;line-height:1.24;font-weight:700;
  font-style:normal;text-align:center;border:none;background:none;color:var(--ac-ink);padding:.2em 3%;
  margin:1.5em 0;break-inside:avoid;page-break-inside:avoid}
.art-content .pull-quote cite{display:block;font-family:var(--ac-fm);font-size:.62rem;font-style:normal;
  letter-spacing:.07em;text-transform:uppercase;color:var(--ac-g500);margin-top:.65em}
.art-content .field-quote{border:var(--ac-rule);border-left:var(--ac-rk);background:var(--ac-g100);
  padding:.95rem 1.1rem;font-style:italic;font-size:1.02rem;color:var(--ac-g700);margin:1.5em 0;
  break-inside:avoid;page-break-inside:avoid}
.art-content .field-quote cite{display:block;font-family:var(--ac-fm);font-size:.6rem;font-style:normal;
  text-transform:uppercase;letter-spacing:.06em;color:var(--ac-g500);margin-top:.5em}
.art-content .spoken-quote{padding-left:1.1rem;border-left:var(--ac-rt);font-style:italic;color:var(--ac-g700)}
.art-content .quote-attribution,.art-content .quote-block cite{font-family:var(--ac-fm);font-size:.6rem;
  text-transform:uppercase;letter-spacing:.06em;color:var(--ac-g500)}
.art-content .field-quote .quote-credit,.art-content blockquote .quote-credit{float:right;width:80px;height:80px;
  object-fit:cover;border:var(--ac-rule);margin:0 0 .5rem 1rem}
.art-content .qa-line{margin:.45em 0;text-indent:0}
.art-content .qa-speaker{font-family:var(--ac-fm);font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;
  font-weight:700;color:var(--ac-ink);margin-right:.35em}
.art-content sup[data-fn],.art-content sup[data-cite]{font-family:var(--ac-fm);font-size:.6em;font-weight:700}
.art-content sup.cite-ref{font-family:var(--ac-fm);font-size:.62em;font-weight:700;color:var(--ac-ink)}
.art-content .fn{font-family:var(--ac-fb);font-size:.8rem;color:var(--ac-g600);border-top:var(--ac-rt);
  padding-top:.28em;margin:.28em 0}
.art-content figure,.art-content .photo-unit{margin:1.6em 0;break-inside:avoid;page-break-inside:avoid}
.art-content .photo-unit figure{margin:0}
.art-content .photo-unit img,.art-content figure img{display:block;width:100%;height:auto;border:var(--ac-rt);margin:0 auto}
.art-content figcaption,.art-content .photo-caption{font-family:var(--ac-fm);font-size:.62rem;line-height:1.45;
  letter-spacing:.02em;color:var(--ac-g600);text-transform:uppercase;padding-top:.45em;border-top:var(--ac-rt);margin-top:.45em}
.art-content .photo-prose{font-size:.94rem;color:var(--ac-g700);margin-top:.55em}
.art-content .photo-unit[data-type="portrait"]{max-width:46%;float:right;margin:.4em 0 1.1em 1.4em}
.art-content .photo-unit[data-type="scene"]{margin-left:0;margin-right:0}
.art-content .photo-unit[data-type="document"] img,.art-content .photo-unit[data-type="reference"] img{
  border:var(--ac-rule);background:var(--ac-g100);padding:.45rem}
.art-content .photo-unit[data-type="reference"] .reference-label,.art-content .reference-label{
  display:inline-block;font-family:var(--ac-fm);font-size:.58rem;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;background:var(--ac-ink);color:var(--ac-paper);padding:.1em .45em;margin-right:.45em}
.art-content .photo-narrative-unit{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;align-items:start;
  margin:1.6em 0;break-inside:avoid;page-break-inside:avoid}
.art-content .photo-narrative-unit figure{margin:0}
.art-content .photo-group{margin:1.6em 0;column-count:2;column-gap:.5rem;break-inside:avoid;page-break-inside:avoid}
.art-content .photo-group figure{margin:0 0 .5rem;break-inside:avoid;page-break-inside:avoid}
.art-content .photo-group img{display:block;width:100%;height:auto;border:var(--ac-rt)}
.art-content .photo-group figcaption{margin-top:.28em}
.art-content .photo-group[data-type="dump"],.art-content .photo-group[data-type="grid"],
  .art-content .photo-group[data-type="collage"]{column-count:3;column-gap:.5rem}
.art-content .photo-group[data-type="crowd"]{column-count:4;column-gap:.45rem}
.art-content .photo-group[data-type="sequence"]{display:block;column-count:1;counter-reset:ve-seq}
.art-content .photo-group[data-type="sequence"] figure{counter-increment:ve-seq;display:flex;align-items:center;
  gap:1.3rem;margin:0 0 1.6em;break-inside:avoid;page-break-inside:avoid}
.art-content .photo-group[data-type="sequence"] figure:last-child{margin-bottom:0}
.art-content .photo-group[data-type="sequence"] figure:nth-child(even){flex-direction:row-reverse}
.art-content .photo-group[data-type="sequence"] img{flex:0 0 54%;width:54%;height:auto;border:var(--ac-rt)}
.art-content .photo-group[data-type="sequence"] figcaption{flex:1;border:none;padding:0;margin:0;
  text-transform:none;font-family:var(--ac-fb);font-size:.92rem;line-height:1.45;color:var(--ac-g700);text-align:left}
.art-content .photo-group[data-type="sequence"] figure:nth-child(even) figcaption{text-align:right}
.art-content .photo-group[data-type="sequence"] figcaption::before{content:counter(ve-seq,decimal-leading-zero);
  display:block;font-family:var(--ac-fh);font-weight:900;font-size:2.2rem;line-height:.9;color:var(--ac-ink);margin-bottom:.16em}
.art-content .photo-group[data-type="comic"]{display:block;column-count:1;background:var(--ac-ink);
  border:var(--ac-rk);padding:4px;counter-reset:ve-pan}
.art-content .photo-group[data-type="comic"] figure{background:var(--ac-paper);margin:0 0 4px;
  counter-increment:ve-pan;display:block}
.art-content .photo-group[data-type="comic"] figure:last-child{margin-bottom:0}
.art-content .photo-group[data-type="comic"] figure::before{content:counter(ve-pan);display:block;
  font-family:var(--ac-fh);font-weight:900;font-size:1.5rem;line-height:1;color:var(--ac-ink);padding:.16em .4em 0}
.art-content .photo-group[data-type="comic"] img{width:100%;height:auto;display:block}
.art-content .photo-group[data-type="comic"] .panel-caption{font-family:var(--ac-fb);font-size:.8rem;
  font-style:italic;color:var(--ac-g700);padding:.35rem .45rem;border:none;text-transform:none}
.art-content .comparison{display:grid;grid-template-columns:repeat(2,1fr);gap:0;border:var(--ac-rule);
  margin:1.6em 0;break-inside:avoid;page-break-inside:avoid}
.art-content .comparison[data-count="3"]{grid-template-columns:repeat(3,1fr)}
.art-content .comparison .compare-item{padding:1rem 1.1rem;border-left:var(--ac-rt)}
.art-content .comparison .compare-item:first-child{border-left:none}
.art-content .comparison .compare-label{font-family:var(--ac-fm);font-size:.6rem;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ac-g500);border-bottom:var(--ac-rt);padding-bottom:.35em;margin-bottom:.6em}
.art-content a.ext-link{text-decoration:underline;text-underline-offset:2px}
'''


_FONT_FILES = {
    'Playfair Display': [('normal', '700', 'PlayfairDisplay-Bold.woff2'), ('italic', 'normal', 'PlayfairDisplay-Italic.woff2')],
    'EB Garamond': [('normal', 'normal', 'EBGaramond-Regular.woff2'), ('italic', 'normal', 'EBGaramond-Italic.woff2')],
}
_ART_FONT_CSS = None


def _art_content_font_css():
    global _ART_FONT_CSS
    if _ART_FONT_CSS is not None:
        return _ART_FONT_CSS
    import base64
    rules = []
    for fam, variants in _FONT_FILES.items():
        for style, weight, fname in variants:
            p = os.path.join(BASE, 'fonts', fname)
            try:
                with open(p, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode()
            except Exception:
                continue
            wdesc = f'font-weight:{weight};' if weight != 'normal' else ''
            rules.append(f'@font-face{{font-family:"{fam}";src:url(data:font/woff2;base64,{b64}) '
                         f'format("woff2");font-style:{style};{wdesc}}}')
    _ART_FONT_CSS = '\n'.join(rules)
    return _ART_FONT_CSS


def _measure_html_height_mm(pw_page, inner_html, css, width_mm):
    doc = (f'<!doctype html><html><head><style>{css}</style>'
           f'<style>body{{margin:0}}#box{{width:{width_mm}mm}}</style></head>'
           f'<body><div id="box">{inner_html}</div></body></html>')
    try:
        pw_page.set_content(doc, wait_until='domcontentloaded', timeout=8000)
    except Exception:
        pw_page.set_content(doc, wait_until='commit', timeout=8000)
    h_px = pw_page.eval_on_selector('#box', 'el => el.scrollHeight')
    return h_px / 3.7795275591


def _gazette_body_pages(content_html, dims, body_w, max_h_mm, css):
    citations = mm._extract_citations(content_html) if content_html else []
    html_for_body = mm._inject_cite_refs(content_html, citations) if citations else (content_html or '')
    if not html_for_body.strip():
        return [], citations
    soup = BeautifulSoup(html_for_body, 'html.parser')
    root = soup.body or soup
    from bs4 import NavigableString
    elems = [c for c in list(root.children) if not (isinstance(c, NavigableString) and not str(c).strip())]
    if not elems:
        return [], citations
    first_p = soup.find('p')
    if first_p is not None:
        first_p['class'] = (first_p.get('class') or []) + ['ve-dropcap']
    elem_strs = [str(c) for c in elems]
    section_flags = ['article-section' in (c.get('class') or []) if hasattr(c, 'get') else False for c in elems]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [(''.join(elem_strs), 0)], citations

    splittable_text = {}
    for i, c in enumerate(elems):
        if getattr(c, 'name', None) == 'p' and c.find(True) is None:
            splittable_text[i] = c.get_text()

    pages_html, pages_sections = [], []
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            pg = browser.new_page()

            def h_of(html_str):
                return _measure_html_height_mm(pg, f'<div class="art-content dropcap">{html_str}</div>', css, body_w)

            def close_page():
                nonlocal cur_parts, cur_sections
                pages_html.append(''.join(cur_parts))
                pages_sections.append(cur_sections)
                cur_parts, cur_sections = [], 0

            cur_parts, cur_sections = [], 0
            queue = list(enumerate(elem_strs))
            while queue:
                i, frag = queue.pop(0)
                fits = h_of(''.join(cur_parts) + frag) <= max_h_mm
                if fits:
                    cur_parts.append(frag)
                    if section_flags[i]:
                        cur_sections += 1
                    continue
                if cur_parts:
                    close_page()
                    queue.insert(0, (i, frag))
                    continue
                if i in splittable_text:
                    words = splittable_text[i].split(' ')
                    lo, hi, best = 0, len(words), 0
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        trial_p = f'<p>{mm._h(" ".join(words[:mid]))}</p>' if mid else ''
                        if h_of(trial_p) <= max_h_mm:
                            best = mid; lo = mid + 1
                        else:
                            hi = mid - 1
                    if best == 0:
                        best = 1
                    cur_parts.append(f'<p>{mm._h(" ".join(words[:best]))}</p>')
                    if best < len(words):
                        remainder = ' '.join(words[best:])
                        splittable_text[i] = remainder
                        queue.insert(0, (i, f'<p>{mm._h(remainder)}</p>'))
                    else:
                        if section_flags[i]:
                            cur_sections += 1
                    close_page()
                else:
                    cur_parts.append(frag)
                    if section_flags[i]:
                        cur_sections += 1
                    close_page()
            if cur_parts:
                close_page()
            browser.close()
    except Exception as e:
        print(f'[dtp_engine] gazette body pagination measurement failed, falling back to one page: {e}')
        return [(''.join(elem_strs), 0)], citations

    pages, running = [], 0
    for html_str, n_sections in zip(pages_html, pages_sections):
        pages.append((html_str, running))
        running += n_sections
    return pages, citations


_AP_SOURCES_CSS = '''
.ap-sources{padding:20mm 18mm}
.ap-sources-head{font-family:"Playfair Display",Georgia,serif;font-weight:700;font-size:1.7rem;
  margin:0 0 1.2rem;border-bottom:2px solid var(--ink);padding-bottom:.6rem;color:var(--ink)}
.ap-sources-sub{font-family:Georgia,serif;font-style:italic;font-size:.85rem;color:var(--g);margin:-0.8rem 0 1.4rem}
.ap-cite-list{font-family:Georgia,serif;font-size:.74rem;line-height:1.62;color:var(--g);
  columns:2 76mm;column-gap:9mm;list-style:none;padding:0;margin:0}
.ap-cite-list li{margin-bottom:.55rem;break-inside:avoid;page-break-inside:avoid}
.ap-cite-list sup{color:var(--accent);font-weight:700;margin-right:.35em}
.ap-cite-list a{color:var(--ink);text-decoration:underline;word-break:break-word}
'''


def _ap_sources_page_html(citations):
    items = ''.join(
        f'<li><sup>[{n}]</sup> <a href="{_esc(url)}" target="_blank">{_esc(_un(text) or url)}</a></li>'
        for n, text, url in citations)
    return (f'<div class="ap-sources"><div class="ap-sources-head">Sources &amp; References</div>'
            f'<div class="ap-sources-sub">Every external link cited in this article, numbered in the order it appears.</div>'
            f'<ol class="ap-cite-list">{items}</ol></div>')


_AP_TOC_CSS = '''
.ap-toc-page{padding:22mm 20mm}
.ap-toc-head{font-family:"Playfair Display",Georgia,serif;font-weight:700;font-size:1.7rem;color:var(--ink);
  margin:0 0 .3rem}
.ap-toc-subhead{font-family:Georgia,serif;font-style:italic;font-size:.85rem;color:var(--g);
  margin:0 0 1.6rem;padding-bottom:1.2rem;border-bottom:2px solid var(--ink)}
.ap-toc-item{display:flex;gap:.9rem;padding:.8rem 0;border-bottom:1px solid #d4cfc0;align-items:baseline}
.ap-toc-n{font-family:"Playfair Display",Georgia,serif;font-weight:900;font-size:1.4rem;color:var(--accent);
  flex:0 0 auto;width:12mm}
.ap-toc-ttl{font-family:"Playfair Display",Georgia,serif;font-weight:700;font-size:1.05rem;color:var(--ink);
  line-height:1.28}
.ap-toc-sub{font-family:Georgia,serif;font-size:.78rem;color:var(--g);margin-top:.25rem;line-height:1.4}
'''


def _gazette_toc_page_html(content_html):
    if not content_html:
        return None
    soup = BeautifulSoup(content_html, 'html.parser')
    sections = soup.find_all(class_='article-section')
    if not sections:
        return None
    items = []
    for i, sec in enumerate(sections, 1):
        heading = sec.find(class_='section-heading')
        sub = sec.find(class_='section-subheading')
        title = heading.get_text().strip() if heading else f'Section {i}'
        sub_txt = sub.get_text().strip() if sub else ''
        sub_html = f'<div class="ap-toc-sub">{_esc(sub_txt)}</div>' if sub_txt else ''
        items.append(f'<div class="ap-toc-item"><div class="ap-toc-n">{i:02d}</div>'
                     f'<div><div class="ap-toc-ttl">{_esc(title)}</div>{sub_html}</div></div>')
    n = len(sections)
    return (f'<div class="ap-toc-page"><div class="ap-toc-head">In This Issue</div>'
           f'<div class="ap-toc-subhead">{n} section{"s" if n != 1 else ""} in this article</div>'
           f'{"".join(items)}</div>')


_AP_TEASER_CSS = '''
.ap-teaser-page{padding:22mm 20mm;height:100%;box-sizing:border-box;display:flex;flex-direction:column;
  justify-content:center;gap:14mm}
.ap-teaser-quote{text-align:center;max-width:130mm;margin:0 auto}
.ap-teaser-mark{font-family:"Playfair Display",Georgia,serif;font-size:3.4rem;line-height:1;color:var(--accent);
  opacity:.55;margin-bottom:-.3rem}
.ap-teaser-txt{font-family:"Playfair Display",Georgia,serif;font-weight:700;font-style:italic;font-size:1.7rem;
  line-height:1.28;color:var(--ink)}
.ap-teaser-cite{font-family:Georgia,serif;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--g);margin-top:1rem}
'''


def _gazette_teaser_page_html(content_html):
    if not content_html:
        return None
    soup = BeautifulSoup(content_html, 'html.parser')
    quotes = []
    for cls in ('pull-quote', 'field-quote'):
        for el in soup.find_all(class_=cls):
            el = BeautifulSoup(str(el), 'html.parser')
            cite_el = el.find('cite')
            cite_txt = cite_el.get_text().strip() if cite_el else ''
            if cite_el:
                cite_el.extract()
            txt = el.get_text().strip()
            if txt:
                quotes.append((txt, cite_txt))
            if len(quotes) >= 2:
                break
        if len(quotes) >= 2:
            break
    if not quotes:
        return None
    def _one(txt, cite):
        cite_html = f'<div class="ap-teaser-cite">{_esc(cite)}</div>' if cite else ''
        return (f'<div class="ap-teaser-quote"><div class="ap-teaser-mark">&#8220;</div>'
               f'<div class="ap-teaser-txt">{_esc(txt)}</div>{cite_html}</div>')
    blocks = ''.join(_one(txt, cite) for txt, cite in quotes)
    return f'<div class="ap-teaser-page">{blocks}</div>'


def _gazette_author_ids(article_id, fallback_author_id):
    db = get_db()
    try:
        rows = db.execute(
            'SELECT author_id FROM article_authors WHERE article_id=? ORDER BY sort_order, author_id',
            (article_id,)).fetchall()
    finally:
        db.close()
    ids = [r['author_id'] for r in rows]
    if not ids and fallback_author_id:
        ids = [fallback_author_id]
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


_AP_BACK_CSS = '''
.ap-back-page{position:relative;overflow:hidden;background:#0d0d0d;color:#f5f5f0;width:100%;height:100%;
  box-sizing:border-box;padding:20mm 18mm 14mm;display:flex;flex-direction:column;
  --accent:#d6d1c2}
.ap-back-pub{font-family:"Playfair Display",Georgia,serif;font-size:2.2rem;font-weight:900;color:#fff;
  letter-spacing:-.02em;margin-bottom:.15em}
.ap-back-tag{font-family:Georgia,serif;font-style:italic;font-size:.9rem;color:rgba(255,255,255,.5);margin-bottom:6mm}
.ap-back-rule{height:2px;width:30mm;background:var(--accent);margin:0 0 7mm}
.ap-back-grid{display:grid;grid-template-columns:1fr 1.2fr;gap:12mm;flex:1;min-height:0;overflow:hidden}
.ap-back-qr-head{font-family:Georgia,serif;font-size:.64rem;letter-spacing:.14em;text-transform:uppercase;
  color:rgba(255,255,255,.55);margin-bottom:3mm}
.ap-back-qr-row{display:flex;flex-wrap:wrap;gap:5mm}
.ap-back-qr-item{width:24mm}
.ap-back-qr-item img{width:100%;height:auto;background:#fff;padding:1.5mm;display:block}
.ap-back-qr-label{display:block;font-family:Georgia,serif;font-size:.56rem;color:rgba(255,255,255,.72);
  margin-top:.35em;line-height:1.3}
.ap-back-sources-head{font-family:Georgia,serif;font-size:.64rem;letter-spacing:.14em;text-transform:uppercase;
  color:rgba(255,255,255,.55);margin-bottom:2.5mm;border-bottom:1px solid rgba(255,255,255,.18);padding-bottom:2mm}
.ap-back-cite-list{list-style:none;margin:0;padding:0;font-family:Georgia,serif;font-size:.56rem;line-height:1.5;
  color:rgba(255,255,255,.6);columns:2 36mm;column-gap:5mm;overflow:hidden;max-height:100%}
.ap-back-cite-list li{margin-bottom:.35em;break-inside:avoid}
.ap-back-cite-list sup{color:var(--accent);font-weight:700;margin-right:.3em}
.ap-back-cite-list a{color:rgba(255,255,255,.75);text-decoration:none;word-break:break-word}
.ap-back-foot{margin-top:5mm;padding-top:3.5mm;border-top:1px solid rgba(255,255,255,.18);display:flex;
  justify-content:space-between;font-family:"Courier New",monospace;font-size:.54rem;letter-spacing:.1em;
  text-transform:uppercase;color:rgba(255,255,255,.4)}
'''


def _gazette_back_page_html(citations, article_url, cfg):
    pub = cfg.get('publication', {}) or {}
    support = cfg.get('support', {}) or {}
    con = cfg.get('contact', {}) or {}
    pub_name = pub.get('name', 'The Voice Express')
    tagline = pub.get('tagline', '')

    def _support_val(section_key, value_key):
        sec = support.get(section_key, '')
        if isinstance(sec, dict):
            return str(sec.get(value_key, '') or '')
        return str(sec or '')

    qr_items = []
    if article_url:
        aq = mm._qr_b64(article_url)
        if aq:
            qr_items.append(f'<div class="ap-back-qr-item"><img src="{aq}" alt="">'
                            f'<span class="ap-back-qr-label">Read this article online</span></div>')
    for section_key, value_key, label in (('kofi', 'url', 'Support on Ko-fi'),
                                           ('razorpay', 'url', 'Support via Razorpay'),
                                           ('paypal', 'url', 'PayPal')):
        val = _support_val(section_key, value_key)
        if not val:
            continue
        q = mm._qr_b64(val)
        if q:
            qr_items.append(f'<div class="ap-back-qr-item"><img src="{q}" alt="">'
                            f'<span class="ap-back-qr-label">{_esc(label)}</span></div>')
    for url, label in ((con.get('emag', ''), 'Read the magazine'),
                       (con.get('newsstand', ''), 'The Newsstand')):
        if not url:
            continue
        q = mm._qr_b64(url)
        if q:
            qr_items.append(f'<div class="ap-back-qr-item"><img src="{q}" alt="">'
                            f'<span class="ap-back-qr-label">{_esc(label)}</span></div>')

    cite_html = ''
    if citations:
        items = ''.join(
            f'<li><sup>[{n}]</sup> <a href="{_esc(url)}" target="_blank">{_esc(_un(text) or url)}</a></li>'
            for n, text, url in citations)
        cite_html = (f'<div class="ap-back-sources-head">Sources &amp; References</div>'
                    f'<ol class="ap-back-cite-list">{items}</ol>')

    site = con.get('emag', '') or con.get('website', '') or pub.get('website', '')
    foot_right = ' · '.join(b for b in (con.get('email', ''),
                                        site.replace('https://', '').rstrip('/')) if b)
    return (f'<div class="ap-back-page">'
           f'<div class="ap-back-pub">{_esc(pub_name)}</div>'
           f'<div class="ap-back-tag">{_esc(tagline)}</div>'
           f'<div class="ap-back-rule"></div>'
           f'<div class="ap-back-grid">'
           f'<div><div class="ap-back-qr-head">Reader-Supported Journalism</div>'
           f'<div class="ap-back-qr-row">{"".join(qr_items)}</div></div>'
           f'<div style="height:100%;overflow:hidden">{cite_html}</div>'
           f'</div>'
           f'<div class="ap-back-foot"><span>{_esc(pub_name)}</span><span>{_esc(foot_right)}</span></div>'
           f'</div>')


_AP_AUTHOR_CSS = '''
.ap-author-page{padding:22mm 18mm;text-align:center}
.ap-author-kicker{font-family:"Georgia",serif;font-size:.62rem;letter-spacing:.24em;text-transform:uppercase;
  color:var(--g);margin-bottom:1.4rem}
.ap-author-avatar{width:88px;height:88px;border-radius:50%;object-fit:cover;border:1px solid var(--g);
  margin:0 auto 1rem;display:block}
.ap-author-avatar-x{background:var(--g);opacity:.25}
.ap-author-name{font-family:"Playfair Display",Georgia,serif;font-weight:700;font-size:1.9rem;color:var(--ink)}
.ap-author-role{font-family:Georgia,serif;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--accent);margin:.35rem 0 1.2rem}
.ap-author-bio{font-family:Georgia,serif;font-size:.98rem;line-height:1.6;color:#2a2520;max-width:120mm;
  margin:0 auto;text-align:left}
.ap-author-links{font-family:Georgia,serif;font-size:.72rem;color:var(--g);margin-top:1rem;display:flex;
  gap:.8rem;justify-content:center;flex-wrap:wrap}
.ap-author-links a{color:var(--accent);text-decoration:none}
.ap-author-grid-head{font-family:"Georgia",serif;font-size:.62rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--g);border-top:1px solid #d4cfc0;margin-top:2rem;padding-top:1.2rem;text-align:left}
.ap-author-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:1rem;text-align:left}
.ap-author-grid-item img{width:100%;height:26mm;object-fit:cover;border:1px solid var(--g);display:block}
.ap-author-grid-x{width:100%;height:26mm;background:var(--g);opacity:.15}
.ap-author-grid-title{font-family:Georgia,serif;font-size:.72rem;line-height:1.32;margin-top:.4rem;color:#2a2520}
'''


def _ap_page_frame(inner_html, pad=(15.0, 18.0, 15.0, 18.0)):
    t, r, b, l = pad
    return (f'<div style="width:100%;height:100%;box-sizing:border-box;background:var(--paper);'
           f'padding:{t}mm {r}mm {b}mm {l}mm;overflow:hidden">{inner_html}</div>')


def _gazette_author_page_html(author_id, exclude_article_id):
    if not author_id:
        return None
    db = get_db()
    try:
        row = db.execute(
            'SELECT name, bio, role, avatar_url, social_twitter, social_instagram '
            'FROM authors WHERE id=?', (author_id,)).fetchone()
        if not row:
            return None
        links = db.execute(
            'SELECT title, url FROM author_links WHERE author_id=? ORDER BY sort_order, id',
            (author_id,)).fetchall()
        recent = db.execute(
            "SELECT id, title, featured_image FROM articles WHERE author_id=? AND status='published' "
            "AND id != ? ORDER BY published_at DESC LIMIT 6", (author_id, exclude_article_id)).fetchall()
    finally:
        db.close()

    avatar_b64 = _bs_embed(row['avatar_url'], STATIC_ROOT) if row['avatar_url'] else None
    avatar_html = (f'<img class="ap-author-avatar" src="{avatar_b64}" alt="">' if avatar_b64
                   else '<div class="ap-author-avatar ap-author-avatar-x"></div>')
    socials = []
    if row['social_twitter']:
        socials.append(f'<span>@{_esc(row["social_twitter"])}</span>')
    if row['social_instagram']:
        socials.append(f'<span>@{_esc(row["social_instagram"])}</span>')
    for l in links:
        socials.append(f'<a href="{_esc(l["url"])}" target="_blank">{_esc(l["title"])}</a>')
    social_html = f'<div class="ap-author-links">{" &middot; ".join(socials)}</div>' if socials else ''

    grid_items = ''
    for a in recent:
        thumb = _bs_embed(a['featured_image'], STATIC_ROOT) if a['featured_image'] else None
        thumb_html = f'<img src="{thumb}">' if thumb else '<div class="ap-author-grid-x"></div>'
        grid_items += (f'<div class="ap-author-grid-item">{thumb_html}'
                       f'<div class="ap-author-grid-title">{_esc(a["title"])}</div></div>')
    grid_html = (f'<div class="ap-author-grid-head">More from {_esc(row["name"] or "this author")}</div>'
                f'<div class="ap-author-grid">{grid_items}</div>') if recent else ''

    return (f'<div class="ap-author-page">'
           f'<div class="ap-author-kicker">About the Author</div>'
           f'{avatar_html}'
           f'<div class="ap-author-name">{_esc(row["name"] or "")}</div>'
           f'<div class="ap-author-role">{_esc(row["role"] or "")}</div>'
           f'<div class="ap-author-bio">{_esc(row["bio"] or "")}</div>'
           f'{social_html}{grid_html}</div>')


SPECIAL_BROADSHEET_KIND = 'broadsheet_special'


def create_special_broadsheet_project(key, label=None, *, article_ids=None, entry_ids=None,
                                      date_from=None, date_to=None, blank_pages=0,
                                      seed_month=None, regenerate=False, enhancement: dict = None):
    if not key:
        return None
    key = re.sub(r'[^a-z0-9._-]+', '-', str(key).strip().lower()).strip('-') or None
    if not key:
        return None
    blank_pages = max(0, int(blank_pages or 0))

    if seed_month and re.match(r'^\d{4}-\d{2}$', seed_month):
        ym = seed_month
    elif date_from and re.match(r'^\d{4}-\d{2}', str(date_from)):
        ym = str(date_from)[:7]
    else:
        ym = datetime.now().strftime('%Y-%m')

    articles = None
    if blank_pages:
        articles = []
    elif article_ids:
        articles = get_articles_by_ids(article_ids)
    elif date_from and date_to:
        articles = get_articles_for_range(date_from, date_to)
    elif entry_ids:
        articles = []

    return create_broadsheet_project(
        ym, articles=articles, regenerate=regenerate, enhancement=enhancement,
        key=key, edition_label=(label or key), kind=SPECIAL_BROADSHEET_KIND,
        name=f'Special · {label or key}', date_from=date_from, date_to=date_to,
        entry_ids=entry_ids, blank_pages=blank_pages)


def create_gazette_project(article_id, art=None, regenerate=False, enhancement: dict = None):
    existing = _find_existing('gazette', article_id)
    if existing and not regenerate:
        return existing
    if art is None:
        art = get_article(article_id)
    if not art:
        return None
    enhancement = enhancement or {}
    parts = ap_mod.build_article_parts(art, static_root=STATIC_ROOT, enhancement=enhancement)
    dims = PAGE_PRESETS['a4']
    _gazette_mono_css = '.p-dark{--accent:#d6d1c2}'
    css = _ap_stylesheet() + '\n' + _ART_CONTENT_CSS + '\n' + _art_content_font_css() + \
        '\n' + _AP_TOC_CSS + '\n' + _AP_TEASER_CSS + '\n' + _AP_AUTHOR_CSS + '\n' + _AP_BACK_CSS + \
        '\n' + _gazette_mono_css
    if parts.get('enh_css'):
        css = css + '\n' + parts['enh_css']

    content_html = art.get('content') or ''

    pages = [{'blocks': [_raw_page_block(dims, parts['header_html'], css)]}]

    toc_html = _gazette_toc_page_html(content_html)
    if toc_html:
        pages.append({'blocks': [_raw_page_block(dims, _ap_page_frame(toc_html, pad=(0, 0, 0, 0)), css)]})

    cfg = mm._cfg()
    mast_html = mm._pg_masthead(_logo_b64(), cfg)
    pages.append({'blocks': [_raw_page_block(dims, mast_html, css)]})

    teaser_html = _gazette_teaser_page_html(content_html)
    if teaser_html:
        pages.append({'blocks': [_raw_page_block(dims, _ap_page_frame(teaser_html, pad=(0, 0, 0, 0)), css)]})

    body_top, body_right, body_bottom, body_left = 15.0, 18.0, 15.0, 18.0
    body_w = dims['w'] - body_left - body_right
    max_h_mm = dims['h'] - body_top - body_bottom
    body_pages, citations = _gazette_body_pages(content_html, dims, body_w, max_h_mm, css)
    if not body_pages:
        body_pages = [(parts['body_html'], 0)]
    for inner_html, sec_offset in body_pages:
        wrapped = f'<div class="art-content dropcap" style="counter-reset:ve-sec {sec_offset}">{inner_html}</div>'
        pages.append({'blocks': [_raw_page_block(dims, _ap_page_frame(wrapped), css)]})

    for aid in _gazette_author_ids(article_id, art.get('author_id')):
        author_html = _gazette_author_page_html(aid, article_id)
        if author_html:
            pages.append({'blocks': [_raw_page_block(dims, _ap_page_frame(author_html, pad=(0, 0, 0, 0)), css)]})

    pub = cfg.get('publication', {}) or {}
    website = (pub.get('website') or (cfg.get('contact') or {}).get('website') or '').rstrip('/')
    article_url = f'{website}/?article={article_id}' if website else ''
    back_html = _gazette_back_page_html(citations, article_url, cfg)
    pages.append({'blocks': [_raw_page_block(dims, back_html, css)]})

    layout = {'preset': 'a4', 'page': dims, 'pages': pages}
    if existing:
        return _regenerate_layout(existing, layout)
    return _create(f'Gazette: {art["title"]}', 'gazette', str(article_id), layout)


def create_booklet_project(column_id, articles, col_row, period='all', label='', regenerate=False,
                            enhancement: dict = None):
    import make_column_booklet as cb_mod
    source_ref = f'{column_id}:{period}:{label}'
    existing = _find_existing('booklet', source_ref)
    if existing and not regenerate:
        return existing
    if not articles:
        return None
    html_str = cb_mod.build_column_booklet(col_row, articles, static_root=STATIC_ROOT, period=period,
                                            label=label, enhancement=enhancement)
    soup = BeautifulSoup(html_str, 'html.parser')
    page_els = soup.find_all(class_='cb-page')
    page_htmls = [str(el) for el in page_els] or [html_str]
    css_m = re.search(r'<style>(.*?)</style>', html_str, re.S)
    css = css_m.group(1) if css_m else ''
    layout = _pages_layout(PAGE_PRESETS['booklet'], 'booklet', page_htmls, css)
    if existing:
        return _regenerate_layout(existing, layout)
    title = (col_row['title'] if isinstance(col_row, dict) else col_row['title']) or 'Column'
    return _create(f'Booklet: {title}', 'booklet', source_ref, layout)


def project_for_publication(pub_id, regenerate=False):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM publications WHERE id=?', [pub_id]).fetchone()
        if not row:
            return {'error': 'Publication not found'}
        try:
            meta = json.loads(row['metadata'] or '{}') or {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
    finally:
        db.close()

    pid = meta.get('dtp_project_id')
    if pid and get_project(pid) and not regenerate:
        return {'project_id': pid, 'via': 'existing'}

    fn = row['filename'] or ''
    kind = meta.get('kind') or _PUB_TYPE_KIND.get(row['pub_type'] or '', 'custom')
    source_ref = meta.get('source_ref')

    if not pid:
        sidecar = os.path.join(PUBLICATIONS_FOLDER, os.path.splitext(fn)[0] + '.dtp.json')
        if os.path.isfile(sidecar):
            try:
                with open(sidecar, encoding='utf-8') as f:
                    saved = json.load(f)
                pid = _create(saved.get('name') or row['title'] or fn,
                              saved.get('kind') or kind,
                              saved.get('source_ref') or source_ref,
                              saved.get('layout') or blank_layout())
                _link_publication(pub_id, pid)
                return {'project_id': pid, 'via': 'sidecar'}
            except Exception as e:
                print(f'[dtp_engine] sidecar import failed for {fn}: {e}')

    if source_ref is None and meta.get('article_ids'):
        ids = [int(x) for x in meta['article_ids'] if str(x).isdigit() or isinstance(x, int)]
        if ids:
            kind, source_ref = 'magazine', ','.join(str(i) for i in ids)

    if source_ref is None:
        return {'error': f'No dtp source for "{row["title"]}" -- it has no '
                         f'recorded origin to rebuild a layout from.'}
    try:
        if kind == 'gazette':
            pid = create_gazette_project(int(source_ref), regenerate=regenerate)
        elif kind == 'broadsheet':
            pid = create_broadsheet_project(str(source_ref), regenerate=regenerate)
        elif kind == 'booklet':
            return {'error': 'Column booklets are rebuilt from the column itself '
                             '-- regenerate it from the Columns board.'}
        elif kind == 'magazine':
            ids = [int(x) for x in str(source_ref).split(',') if str(x).strip().isdigit()]
            pid = create_magazine_project(ids, regenerate=regenerate)
        else:
            return {'error': f'Publications of kind "{kind}" have no generator to rebuild from.'}
    except Exception as e:
        return {'error': f'Rebuild failed: {e}'}
    if not pid:
        return {'error': 'Rebuild produced no project (source content missing?)'}
    _link_publication(pub_id, pid)
    return {'project_id': pid, 'via': 'rebuilt'}


_PUB_TYPE_KIND = {'gazette': 'gazette', 'broadsheet': 'broadsheet', 'newsletter': 'broadsheet',
                  'booklet': 'booklet', 'compilation': 'booklet',
                  'magazine_pdf': 'magazine', 'magazine_html': 'magazine'}


def _link_publication(pub_id, pid):
    db = get_db()
    try:
        row = db.execute('SELECT metadata FROM publications WHERE id=?', [pub_id]).fetchone()
        try:
            meta = json.loads(row['metadata'] or '{}') if row else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        meta['dtp_project_id'] = pid
        db.execute('UPDATE publications SET metadata=? WHERE id=?',
                   [json.dumps(meta or {}, ensure_ascii=False), pub_id])
        db.commit()
    finally:
        db.close()


def list_publications():
    db = get_db()
    try:
        if _lib:
            _lib.ensure_publication_columns(db)
        out = []
        for r in db.execute('SELECT id, title, pub_type, filename, cover_image, metadata, '
                            'COALESCE(is_featured,0) AS is_featured '
                            'FROM publications ORDER BY id DESC').fetchall():
            try:
                meta = json.loads(r['metadata'] or '{}') or {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            out.append({'id': r['id'], 'title': r['title'], 'pub_type': r['pub_type'],
                        'filename': r['filename'], 'cover': r['cover_image'],
                        'dtp_project_id': meta.get('dtp_project_id'),
                        'tags': meta.get('tags') or [],
                        'featured': bool(r['is_featured']),
                        'frozen': bool(meta.get('frozen')),
                        'editable': bool(not meta.get('frozen')
                                         and (meta.get('dtp_project_id') or meta.get('source_ref')))})
        return out
    finally:
        db.close()


def set_publication_flags(pub_id, featured=None, tags=None, title=None):
    db = get_db()
    try:
        if _lib:
            _lib.ensure_publication_columns(db, commit=False)
        row = db.execute('SELECT metadata FROM publications WHERE id=?', [pub_id]).fetchone()
        if not row:
            return {'error': 'Publication not found'}
        fields, params = [], []
        if featured is not None:
            fields.append('is_featured=?'); params.append(1 if featured else 0)
        if title:
            fields.append('title=?'); params.append(str(title)[:200])
        if tags is not None:
            try:
                meta = json.loads(row['metadata'] or '{}') or {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            meta['tags'] = [str(t).strip() for t in tags if str(t).strip()][:20]
            fields.append('metadata=?'); params.append(json.dumps(meta, ensure_ascii=False))
        if fields:
            params.append(pub_id)
            db.execute(f'UPDATE publications SET {", ".join(fields)} WHERE id=?', params)
            db.commit()
        return {'success': True, 'publication_id': pub_id}
    except Exception as e:
        db.rollback()
        return {'error': str(e)}
    finally:
        db.close()


def replace_publication_file(pub_id, content, filename):
    if not content:
        return {'error': 'No file content'}
    db = get_db()
    try:
        row = db.execute('SELECT filename, title FROM publications WHERE id=?',
                         [pub_id]).fetchone()
        if not row or not row['filename']:
            return {'error': 'Publication not found'}
        old_ext = row['filename'].rsplit('.', 1)[-1].lower()
        new_ext = filename.rsplit('.', 1)[-1].lower() if '.' in (filename or '') else ''
        if new_ext != old_ext:
            return {'error': f'This publication is a .{old_ext} — the replacement must be too'}
        fp = _lib.locate(row['filename']) if _lib else None
        if not fp:
            fp = os.path.join(PUBLICATIONS_FOLDER, row['filename'])
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'wb') as f:
            f.write(content)
        db.execute('UPDATE publications SET file_size=? WHERE id=?', [len(content), pub_id])
        db.commit()
        return {'success': True, 'publication_id': pub_id,
                'filename': row['filename'], 'file_size': len(content)}
    except Exception as e:
        db.rollback()
        return {'error': str(e)}
    finally:
        db.close()


def import_pdf(content, filename, title=None, tags=None, description='', featured=False):
    if not content:
        return {'error': 'No file content'}
    if not (filename or '').lower().endswith('.pdf'):
        return {'error': 'A PDF file is required'}
    title = (title or os.path.splitext(os.path.basename(filename))[0] or 'Untitled').strip()[:200]
    tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:20]

    ts = datetime.utcnow().strftime('%Y%m%d')
    safe = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:50] or 'import'
    stored = f'{safe}_{ts}_{uuid.uuid4().hex[:6]}.pdf'
    os.makedirs(PUBLICATIONS_FOLDER, exist_ok=True)
    with open(os.path.join(PUBLICATIONS_FOLDER, stored), 'wb') as f:
        f.write(content)

    cover = None
    if _gen_icon:
        try:
            seed_words = tags or [w for w in re.sub(r'<[^>]+>', '', title).upper().split()
                                  if len(w) > 4 and w.isalpha()]
            cover = _gen_icon('pdf', list(dict.fromkeys(seed_words))[:20], title)
        except Exception as e:
            print(f'[dtp_engine] icon generation failed: {e}')

    meta = json.dumps({'source': 'import', 'frozen': True, 'tags': tags,
                       'description': description or '', 'article_ids': [],
                       'imported_at': now()}, ensure_ascii=False)
    db = get_db()
    try:
        if _lib:
            _lib.ensure_publication_columns(db, commit=False)
        cur = db.execute(
            '''INSERT INTO publications
               (title, pub_type, filename, file_size, cover_image, description,
                article_count, issue_number, price_min, price_max, price_suggested,
                currency, is_featured, metadata)
               VALUES (?,?,?,?,?,?,0,NULL,0,500,0,'INR',?,?)''',
            [title, 'pdf', stored, len(content), cover, description or '',
             1 if featured else 0, meta])
        db.commit()
        return {'success': True, 'publication_id': cur.lastrowid,
                'filename': stored, 'title': title, 'tags': tags}
    except Exception as e:
        db.rollback()
        try:
            os.remove(os.path.join(PUBLICATIONS_FOLDER, stored))
        except OSError:
            pass
        return {'error': str(e)}
    finally:
        db.close()


def artifact_status(kind, source_ref, ext, sig=None):
    db = get_db()
    try:
        return _lib_artifact_status(db, kind, source_ref, ext, sig=sig,
                                    static_root=STATIC_ROOT)
    finally:
        db.close()


def _publication_id_for_project(db, pid):
    for r in db.execute("SELECT id, metadata FROM publications "
                        "WHERE metadata LIKE '%dtp_project_id%' ORDER BY id DESC").fetchall():
        try:
            if int((json.loads(r['metadata'] or '{}') or {}).get('dtp_project_id') or 0) == int(pid):
                return r['id']
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return None


def _published_filename_for(pid):
    db = get_db()
    try:
        rid = _publication_id_for_project(db, pid)
        if not rid:
            return None
        row = db.execute('SELECT filename FROM publications WHERE id=?', [rid]).fetchone()
        return row['filename'] if row else None
    finally:
        db.close()


def _cover_on_disk(cover):
    if not cover:
        return False
    if cover.startswith(('http://', 'https://')):
        return True
    rel = cover[len('/static/'):] if cover.startswith('/static/') else \
          cover[len('static/'):] if cover.startswith('static/') else None
    return bool(rel) and os.path.exists(os.path.join(STATIC_ROOT, rel))


def _is_sibling_rendering(a, b):
    if not a or not b:
        return False
    sa, ea = os.path.splitext(a)
    sb, eb = os.path.splitext(b)
    if sa != sb or not sa:
        return False
    return (ea.lstrip('.').lower() in _lib.FORMAT_RANK
            and eb.lstrip('.').lower() in _lib.FORMAT_RANK) if _lib else True


def _retire_artifact_files(filename):
    stem = os.path.splitext(filename)[0]
    for d in (PUBLICATIONS_FOLDER, os.path.join(STATIC_ROOT, 'media')):
        for fn in (filename, f'{stem}.dtp.json'):
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError as e:
                    print(f'[dtp_engine] could not retire {p}: {e}')


try:
    import ve_library as _lib
    from ve_library import canonical_target as _canonical_target,         artifact_status as _lib_artifact_status
except Exception as _e:
    _lib = None
    _canonical_target = None
    _lib_artifact_status = None
    print(f'[dtp_engine] ve_library unavailable, publishing to minted names: {_e}')


def publish_project(pid, title=None, output='pdf', pub_type_override=None, sig=None,
                    tags=None):
    proj = get_project(pid)
    if not proj:
        return {'error': 'Project not found'}

    if output == 'html':
        content = render_html(proj['layout'], title=title or proj['name'], kind=proj['kind']).encode('utf-8')
        ext = 'html'
        mimetype = 'text/html; charset=utf-8'
    else:
        content, err = render_pdf(proj['layout'])
        if err:
            return {'error': err}
        ext = 'pdf'
        mimetype = 'application/pdf'

    title = (title or proj['name'] or 'Untitled').strip()[:200]
    pub_type = pub_type_override or _DTP_PUB_TYPE.get(proj['kind'], 'pdf')
    if proj['kind'] == 'magazine':
        pub_type = 'magazine_pdf' if ext == 'pdf' else 'magazine_html'

    prev_filename = _published_filename_for(pid)
    target = _canonical_target(proj['kind'], proj.get('source_ref'), ext) if _canonical_target else None
    subdir = None
    if target:
        subdir, filename = target
        out_dir = os.path.join(STATIC_ROOT, subdir)
    else:
        out_dir = PUBLICATIONS_FOLDER
        if prev_filename and prev_filename.rsplit('.', 1)[-1].lower() == ext:
            filename = prev_filename
        else:
            ts = datetime.utcnow().strftime('%Y%m%d')
            safe = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:50] or 'dtp'
            filename = f'{safe}_{ts}_{uuid.uuid4().hex[:6]}.{ext}'
    stem = os.path.splitext(filename)[0]
    layout_filename = f'{stem}.dtp.json'

    article_ids = []
    if proj['kind'] in ('magazine', 'gazette') and proj.get('source_ref'):
        for part in str(proj['source_ref']).split(','):
            try:
                article_ids.append(int(part))
            except ValueError:
                pass

    typed_tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:20]
    derived_tags = [w for w in re.sub(r'<[^>]+>', '', title).upper().split()
                    if len(w) > 4 and w.isalpha()]
    derived_tags = list(dict.fromkeys(derived_tags))[:20]

    db = get_db()
    try:
        row = None
        for cand in ([f'{stem}.{e}' for e in ('pdf', 'html', 'epub')] if target else [filename]):
            row = db.execute(
                'SELECT id, cover_image, title, metadata, filename FROM publications WHERE filename=?',
                [cand]).fetchone()
            if row:
                break
        if not row:
            pubid = _publication_id_for_project(db, pid)
            row = db.execute('SELECT id, cover_image, title, metadata, filename FROM publications WHERE id=?',
                             [pubid]).fetchone() if pubid else None
        if not row and article_ids:
            want = sorted(article_ids)
            fam = (('magazine_html', 'magazine_pdf') if pub_type.startswith('magazine')
                   else (pub_type,))
            ph = ','.join('?' * len(fam))
            for cand in db.execute(
                    "SELECT id, cover_image, title, metadata, filename FROM publications "
                    f"WHERE pub_type IN ({ph})", list(fam)).fetchall():
                try:
                    cm = json.loads(cand['metadata'] or '{}') or {}
                except (json.JSONDecodeError, TypeError):
                    continue
                if sorted(int(x) for x in (cm.get('article_ids') or []) if str(x).isdigit()) == want:
                    row = cand
                    break
        _row_meta = {}
        if row:
            try:
                _prev_row_fn = row['filename']
            except (IndexError, KeyError):
                _prev_row_fn = None
            if _prev_row_fn and _prev_row_fn != filename and not prev_filename:
                prev_filename = _prev_row_fn
            try:
                _row_meta = json.loads(row['metadata'] or '{}') or {}
            except (json.JSONDecodeError, TypeError):
                _row_meta = {}
            if _row_meta.get('frozen'):
                return {'error': f'"{row["title"]}" is a frozen publication — '
                                 'upload a replacement file instead of publishing over it'}

        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, filename), 'wb') as f:
            f.write(content)
        with open(os.path.join(PUBLICATIONS_FOLDER, layout_filename), 'w', encoding='utf-8') as f:
            json.dump({'name': proj['name'], 'kind': proj['kind'], 'source_ref': proj.get('source_ref'),
                       'layout': proj['layout']}, f, ensure_ascii=False)

        booklet_meta = {}
        booklet_tags = []
        if proj['kind'] == 'booklet' and proj.get('source_ref') and _lib \
                and hasattr(_lib, 'booklet_entries'):
            try:
                info = _lib.booklet_entries(db, proj['source_ref'])
                if info and info.get('entry_ids'):
                    booklet_meta = {'entry_ids': info['entry_ids'],
                                    'column_id': info['column_id'],
                                    'period': info['period'],
                                    'range': info['range']}
                    booklet_tags = _ve_tags.names_for_entries(db, info['entry_ids'])
            except Exception as e:
                print(f'[dtp_engine] booklet contents lookup failed: {e}')

        cover = None
        if _gen_icon:
            try:
                cover = _gen_icon(pub_type, derived_tags, title, seed=pid)
            except Exception as e:
                print(f'[dtp_engine] icon generation failed: {e}')

        meta_d = {'source': 'dtp', 'dtp_project_id': pid, 'article_ids': article_ids,
                  'layout_file': layout_filename, 'built_at': now()}
        meta_d.update(booklet_meta)
        prior_entry_tags = {str(t).lower() for t in (_row_meta.get('entry_tags') or [])}
        if typed_tags:
            final_tags = typed_tags
        elif _row_meta.get('tags'):
            final_tags = [t for t in _row_meta['tags'] if str(t).lower() not in prior_entry_tags]
        else:
            final_tags = derived_tags
        if booklet_tags:
            final_tags = _lib.merge_tag_names(final_tags, booklet_tags)
            meta_d['entry_tags'] = list(booklet_tags)
        if final_tags:
            meta_d['tags'] = final_tags
        if sig is not None:
            meta_d['build_sig'] = _lib.build_sig(sig) if _lib and hasattr(_lib, 'build_sig') else sig
        if proj.get('source_ref') is not None:
            meta_d['kind'] = proj['kind']
            meta_d['source_ref'] = proj['source_ref']

        if row:
            keep_cover = row['cover_image'] if _cover_on_disk(row['cover_image']) else cover
            shelf_fn, renderings = filename, [ext]
            if target and _lib:
                sibs = _lib.siblings_for(stem)
                sibs[ext] = os.path.join(out_dir, filename)
                renderings = sorted(sibs)
                shelf_fn = f'{stem}.{_lib.preferred_rendering(renderings)}'
            meta_d['renderings'] = renderings
            shelf_path = os.path.join(STATIC_ROOT, subdir, shelf_fn) if target else os.path.join(out_dir, shelf_fn)
            db.execute(
                '''UPDATE publications SET title=?, pub_type=?, filename=?, file_size=?,
                   cover_image=?, article_count=?, metadata=? WHERE id=?''',
                [title, pub_type, shelf_fn,
                 os.path.getsize(shelf_path) if os.path.exists(shelf_path) else len(content),
                 keep_cover, len(article_ids),
                 json.dumps(meta_d, ensure_ascii=False), row['id']])
            pub_id = row['id']
        else:
            cur = db.execute(
                '''INSERT INTO publications
                   (title, pub_type, filename, file_size, cover_image, article_count,
                    issue_number, price_min, price_max, price_suggested, currency, metadata)
                   VALUES (?,?,?,?,?,?,?,0,500,0,'INR',?)''',
                [title, pub_type, filename, len(content), cover, len(article_ids), None,
                 json.dumps(meta_d, ensure_ascii=False)])
            pub_id = cur.lastrowid
        if prev_filename and prev_filename != filename and \
                not _is_sibling_rendering(prev_filename, filename):
            db.execute('DELETE FROM publications WHERE filename=? AND id<>?',
                       [prev_filename, pub_id])
            _retire_artifact_files(prev_filename)
        db.commit()
        return {'success': True, 'publication_id': pub_id, 'filename': filename,
                'layout_file': layout_filename, 'content': content, 'mimetype': mimetype}
    except Exception as e:
        db.rollback()
        try:
            os.remove(os.path.join(PUBLICATIONS_FOLDER, layout_filename))
        except Exception:
            pass
        return {'error': str(e)}
    finally:
        db.close()
