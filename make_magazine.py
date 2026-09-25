import argparse
import base64
import hashlib
import html as _html_mod
import io
import json
import math
import mimetypes
import os
import random
import re
import struct
import sys
import time
import urllib.request as _req
from datetime import datetime, timezone

try:
    from bs4 import BeautifulSoup, Tag as _BSTag
except ImportError:
    BeautifulSoup = None
    _BSTag = type(None)

_DIR = os.path.dirname(os.path.abspath(__file__))
_CFG = os.path.join(_DIR, 'broadsheet_config.json')

_CAT_ACCENT = {
    'photo_essay':   '#b85e3a',
    'interview':     '#4a7a8c',
    'research':      '#3d4a5c',
    'investigation': '#2c3e6e',
    'explainer':     '#3e6e8c',
    'data':          '#3d4a5c',
    'ground_report': '#c8102e',
    'dispatch':      '#c8102e',
    'news':          '#b02020',
    'breaking':      '#c8102e',
    'culture':       '#7a5e8c',
    'arts':          '#7a5e8c',
    'review':        '#5a3e8c',
    'film':          '#5a3e8c',
    'opinion':       '#b8960c',
    'editorial':     '#b8960c',
    'column':        '#8c7a3e',
    'letter':        '#8c7a3e',
    'feature':       '#5a7a4a',
    'profile':       '#8c5a3e',
    'longform':      '#5a7a4a',
    'labour':        '#c84a3e',
    'workers':       '#c84a3e',
    'politics':      '#3e4a8c',
    'gender':        '#8c3e7a',
    'environment':   '#3e8c5a',
    'education':     '#5a8c3e',
    'health':        '#3e8c7a',
    'economy':       '#7a6e3e',
    'essay':         '#c8a84a',
}

_ACCENT_CYCLE = ['#c8a84a','#b85e3a','#4a7a8c','#7a8c5e','#8c6a3e','#6e5a8c','#3e7a5e']

_CAT_PQ = {
    'photo_essay':   5,
    'interview':     4,
    'research':      1,
    'ground_report': 2,
    'culture':       3,
    'opinion':       5,
    'essay':         1,
    'profile':       6,
    'feature':       7,
    'longform':      3,
}

_CAT_LAYOUT = {
    'photo_essay':   'visual',
    'interview':     'dialogue',
    'research':      'academic',
    'ground_report': 'field',
    'culture':       'arts',
    'review':        'arts',
    'opinion':       'essay',
    'essay':         'literary',
    'profile':       'portrait',
    'feature':       'longform',
    'longform':      'longform',
    'data':          'academic',
    'explainer':     'academic',
}

_PAGE_BUDGET = {'cols-1': 520, 'cols-2': 420, 'cols-3': 560}

_SECTION_LABELS = {
    'context':      'Context',
    'background':   'Background',
    'scene':        'Scene',
    'dispatch':     'Dispatch',
    'analysis':     'Analysis',
    'testimony':    'Voices',
    'voices':       'Voices',
    'perspective':  'Perspective',
    'resolution':   'Resolution',
    'epilogue':     'Epilogue',
    'conclusion':   'Conclusion',
    'data':         'By the Numbers',
    'numbers':      'By the Numbers',
    'key-facts':    'Key Facts',
    'timeline':     'Timeline',
    'what-happened':'What Happened',
    'what-next':    'What Next',
    'why-it-matters':'Why It Matters',
    'series-note':  'Series Note',
}

_END_MARKS = {
    'interview':     '<div class="art-end-mark art-end-mark--dash">&#8212;</div>',
    'research':      '<div class="art-end-mark art-end-mark--square">&#9632;</div>',
    'ground_report': '<div class="art-end-mark art-end-mark--square">&#9632;</div>',
    'opinion':       '<div class="art-end-mark art-end-mark--diamond">&#9670;</div>',
    'essay':         '<div class="art-end-mark art-end-mark--diamond">&#9670;</div>',
    'profile':       '<div class="art-end-mark art-end-mark--diamond">&#9670;</div>',
    'culture':       '<div class="art-end-mark art-end-mark--bullet">&#8226;</div>',
    'review':        '<div class="art-end-mark art-end-mark--bullet">&#8226;</div>',
    'feature':       '<div class="art-end-mark art-end-mark--diamond">&#9670;</div>',
    'longform':      '<div class="art-end-mark art-end-mark--diamond">&#9670;</div>',
}

_PE_W   = 174.0
_PE_H   = 248.0
_PE_GAP = 3.0
_PE_TGT = 62.0


def _cfg():
    try:
        with open(_CFG, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _h(t):
    return _html_mod.escape(_html_mod.unescape(str(t or '')), quote=True)


def _words(html, n=None):
    txt = re.sub(r'<!--.*?-->', '', str(html or ''), flags=re.DOTALL)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    parts = txt.split()
    if n is None:
        return len(parts)
    return ' '.join(parts[:n]) + ('…' if len(parts) > n else '')


def _plain(html):
    return _html_mod.unescape(re.sub(r'<[^>]+>', ' ', str(html or ''))).strip()


_PHOTO_CREDIT_RE = re.compile(r'<cite[^>]*\bclass=["\'][^"\']*\bphoto-credit\b[^"\']*["\'][^>]*>(.*?)</cite>',
                               re.DOTALL | re.IGNORECASE)


def _split_caption_credit(figcaption_inner_html):
    raw = str(figcaption_inner_html or '')
    m = _PHOTO_CREDIT_RE.search(raw)
    if not m:
        return _plain(raw)
    credit = _plain(m.group(1))
    desc = _plain(_PHOTO_CREDIT_RE.sub('', raw))
    if not credit:
        return desc
    return f'{desc}\n{credit}' if desc else credit


def _cap_html(cap):
    return _h(cap or '').replace('\n', '<br>')


MAG_IMG_MAX_PX = 2400
MAG_IMG_QUALITY = 86


def _shrink_bytes(data, path=None):
    if len(data) < 200 * 1024:
        return None
    try:
        from PIL import Image
        import io as _io
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(_io.BytesIO(data)); im.load()
        if max(im.size) > MAG_IMG_MAX_PX:
            im.thumbnail((MAG_IMG_MAX_PX, MAG_IMG_MAX_PX), Image.LANCZOS)
        out = _io.BytesIO()
        im.convert('RGB').save(out, format='JPEG', quality=MAG_IMG_QUALITY,
                               optimize=True, progressive=True)
        v = out.getvalue()
        return (v, 'image/jpeg') if len(v) < len(data) else None
    except Exception:
        return None


def _b64(src, static_root, maxb=4 * 1024 * 1024):
    try:
        if src and src.startswith('/static/'):
            p = os.path.join(static_root, src[len('/static/'):].lstrip('/'))
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    d = f.read()
                mt = mimetypes.guess_type(p)[0] or 'image/jpeg'
                sm = _shrink_bytes(d, p)
                if sm:
                    d, mt = sm
                return 'data:' + mt + ';base64,' + base64.b64encode(d).decode()
        elif src and src.startswith(('http://', 'https://')):
            rq = _req.Request(src, headers={'User-Agent': 'TVE-Magazine/1.0'})
            with _req.urlopen(rq, timeout=8) as resp:
                d = resp.read(maxb)
            ct = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
            sm = _shrink_bytes(d)
            if sm:
                d, ct = sm
            return 'data:' + ct + ';base64,' + base64.b64encode(d).decode()
    except Exception:
        pass
    return None


def _qr_b64(url):
    try:
        import qrcode
        q = qrcode.QRCode(version=1, box_size=6, border=3)
        q.add_data(url or 'https://emag.thevoiceexpress.in')
        q.make(fit=True)
        buf = io.BytesIO()
        q.make_image(fill_color='black', back_color='white').save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _clean(html, static_root, img_cache):
    html = re.sub(r'<!--.*?-->', '', str(html or ''), flags=re.DOTALL)
    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '',
                  html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'\s+class="wp-block-[^"]*"', '', html)
    html = re.sub(r"\s+class='wp-block-[^']*'", '', html)

    def _norm_figure(m):
        inner = m.group(1)
        img_m = re.search(r'<img\b[^>]*/>', inner, re.IGNORECASE)
        if not img_m:
            return m.group(0)
        cap = ''
        fc = re.search(r'<figcaption[^>]*>(.*?)</figcaption>',
                       inner, re.DOTALL | re.IGNORECASE)
        if fc:
            cap = re.sub(r'<[^>]+>', '', fc.group(1)).strip()
        if not cap:
            for pm in re.finditer(r'<p\b([^>]*)>(.*?)</p>',
                                  inner, re.DOTALL | re.IGNORECASE):
                pa = pm.group(1)
                if re.search(r'photo-caption|data-text-role=["\'\']'
                             r'(?:caption|subtitle|description)', pa, re.I):
                    cap = re.sub(r'<[^>]+>', '', pm.group(2)).strip()
                    break
        cls = 'art-fig' + (' has-caption' if len(cap) > 3 else '')
        return (f'<figure class="{cls}">{img_m.group(0)}'
                f'<figcaption>{_h(cap)}</figcaption></figure>')

    html = re.sub(r'<figure[^>]*>(.*?)</figure>',
                  _norm_figure, html, flags=re.DOTALL | re.IGNORECASE)

    for tag in ('br', 'hr', 'img', 'input', 'meta', 'link'):
        html = re.sub(
            rf'<({tag})(\s[^>]*)?>(?!</{tag}>)',
            lambda m: f'<{m.group(1)}{m.group(2) or ""}/>',
            html, flags=re.IGNORECASE)

    html = re.sub(r'<br\s*/>', ' ', html, flags=re.IGNORECASE)

    def _embed(m):
        src = m.group(1)
        if not src or src.startswith('data:'):
            return m.group(0)
        if src not in img_cache:
            img_cache[src] = _b64(src, static_root) or src
        return m.group(0).replace(src, img_cache[src], 1)

    html = re.sub(r'src=["\']([^"\']+)["\']', _embed, html, flags=re.IGNORECASE)
    html = re.sub(
        r'(<img\b[^/]*/?>)(?!\s*</figure>)',
        r'<figure class="art-fig">\1<figcaption></figcaption></figure>',
        html, flags=re.IGNORECASE)
    return html


_CAT_MAP = {
    'photo essay': 'photo_essay', 'photo-essay': 'photo_essay',
    'gallery': 'photo_essay', 'in pictures': 'photo_essay',
    'photo story': 'photo_essay',
    'interview': 'interview', 'in conversation': 'interview', 'q&a': 'interview',
    'profile': 'profile',
    'investigation': 'research', 'explainer': 'explainer',
    'research': 'research', 'data': 'research',
    'analysis': 'research', 'fact check': 'research',
    'ground report': 'ground_report', 'dispatch': 'ground_report',
    'news': 'ground_report', 'breaking': 'ground_report', 'update': 'ground_report',
    'opinion': 'opinion', 'editorial': 'opinion', 'column': 'opinion',
    'letter': 'opinion', 'open letter': 'opinion', 'viewpoint': 'opinion',
    'culture': 'culture', 'arts': 'culture', 'review': 'review',
    'film': 'review', 'music': 'review', 'book review': 'review',
    'feature': 'feature', 'longform': 'feature',
    'essay': 'essay',
}


def _detect_type(art):
    cat_name = (art.get('category_name', '') or '').lower().strip()
    for key, val in _CAT_MAP.items():
        if key in cat_name:
            return val

    content = art.get('content', '') or ''
    imgs    = len(re.findall(r'<img\b', content, re.IGNORECASE))
    wc      = _words(content)
    tags    = [t.get('name', '').lower() for t in art.get('tags', [])]
    sect    = (art.get('section_name', '') or '').lower()
    needle  = ' '.join(tags + [sect, cat_name, (art.get('title', '') or '').lower()])

    if 'photo-essay-deck' in content:                               return 'photo_essay'
    if imgs >= 4 and wc < 400:                                      return 'photo_essay'
    if any(k in needle for k in ('photo essay', 'photo-essay',
                                 'gallery', 'in pictures')):        return 'photo_essay'
    if any(k in needle for k in ('interview', 'in conversation',
                                 'speaks to', 'q&a')):              return 'interview'
    if any(k in needle for k in ('investigation', 'research',
                                 'analysis', 'fact check',
                                 'explainer', 'data')):             return 'research'
    if any(k in needle for k in ('ground report', 'dispatch',
                                 'filed from', 'breaking',
                                 'news')):                          return 'ground_report'
    if any(k in needle for k in ('culture', 'arts', 'review',
                                 'film', 'theatre', 'exhibition',
                                 'music')):                         return 'culture'
    if any(k in needle for k in ('opinion', 'editorial', 'column',
                                 'viewpoint', 'commentary')):       return 'opinion'
    if any(k in needle for k in ('profile', 'portrait of')):        return 'profile'
    if any(k in needle for k in ('explainer',
                                 'everything you need to know')):   return 'explainer'
    return 'essay'


def _art_accent(art, idx):
    atype = _detect_type(art)
    return (art.get('accent_color')
            or _CAT_ACCENT.get(atype, _ACCENT_CYCLE[(idx - 1) % len(_ACCENT_CYCLE)]))


def _col_class(wc, art_type='essay', body_html=''):
    if art_type == 'photo_essay':
        return 'cols-1'

    has_lede  = ('data-text-role="lede"'  in body_html or
                 "data-text-role='lede'"  in body_html)
    has_roles = ('data-text-role='        in body_html or
                 'data-section-index='    in body_html)

    if art_type == 'interview':
        return 'cols-2' if wc > 140 else 'cols-1'

    if art_type in ('research', 'ground_report'):
        if wc > 580: return 'cols-3'
        if wc > 170: return 'cols-2'
        return 'cols-1'

    if art_type in ('profile', 'culture', 'review'):
        if wc > 700: return 'cols-3'
        return 'cols-2' if wc > 160 else 'cols-1'

    if wc < 160:
        return 'cols-1'
    if wc > 650:
        return 'cols-3'
    return 'cols-2'


def _extract_citations(html):
    links, seen = [], {}
    for m in re.finditer(
            r'<a\s[^>]*href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
            html, re.DOTALL | re.IGNORECASE):
        url  = m.group(1).strip()
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if url.startswith(('mailto:', 'javascript:', 'tel:')):
            continue
        if url not in seen:
            seen[url] = len(links) + 1
            links.append((seen[url], text or url, url))
    return links


def _inject_cite_refs(html, citations):
    url_map = {url: num for num, _, url in citations}

    def _r(m):
        url   = m.group(1).strip()
        inner = m.group(2)
        n = url_map.get(url)
        if n:
            return f'{inner}<sup class="cite-ref">[{n}]</sup>'
        return m.group(0)

    return re.sub(r'<a\s[^>]*href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
                  _r, html, flags=re.DOTALL | re.IGNORECASE)


def _style_interview(html):
    html = re.sub(
        r'<p>\s*(?:<(?:strong|b)>)?\s*Q\s*[.:]\s*(?:</(?:strong|b)>)?\s*(.*?)</p>',
        lambda m: f'<p class="iq">{m.group(1).strip()}</p>',
        html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(
        r'<p>\s*(?:<(?:strong|b)>)?\s*A\s*[.:]\s*(?:</(?:strong|b)>)?\s*(.*?)</p>',
        lambda m: f'<p class="ia">{m.group(1).strip()}</p>',
        html, flags=re.DOTALL | re.IGNORECASE)
    return html


def _img_dims(data_uri):
    try:
        raw = base64.b64decode(data_uri.split(',', 1)[1])
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            return struct.unpack('>II', raw[16:24])
        if raw[:2] == b'\xff\xd8':
            i = 2
            while i < len(raw) - 4:
                if raw[i] != 0xff:
                    break
                mk = raw[i + 1]
                if mk in (0xc0, 0xc1, 0xc2, 0xc3):
                    h, w = struct.unpack('>HH', raw[i + 5:i + 9])
                    return w, h
                if mk == 0xd9:
                    break
                i += 2 + struct.unpack('>H', raw[i + 2:i + 4])[0]
        if len(raw) > 30 and raw[8:12] == b'WEBP' and raw[12:16] == b'VP8 ':
            w = struct.unpack('<H', raw[26:28])[0] & 0x3fff
            h = struct.unpack('<H', raw[28:30])[0] & 0x3fff
            return w, h
    except Exception:
        pass
    return None, None


def _stable_seed(value):
    raw = str(value or '').encode('utf-8', 'ignore')
    return int(hashlib.sha1(raw).hexdigest()[:12], 16)


def _aspect(img_tag, fallback=1.5):
    src_m = re.search(r'src=["\']([^"\']+)["\']', img_tag, re.IGNORECASE)
    if src_m:
        src = src_m.group(1)
        if src.startswith('data:'):
            w, h = _img_dims(src)
            if w and h:
                return w / h
    wm = re.search(r'\bwidth=["\']?(\d+)',  img_tag, re.IGNORECASE)
    hm = re.search(r'\bheight=["\']?(\d+)', img_tag, re.IGNORECASE)
    if wm and hm:
        w, h = int(wm.group(1)), int(hm.group(1))
        if h:
            return w / h
    return fallback


def _image_shape(img_tag):
    r = _aspect(img_tag, fallback=1.35)
    if r < 0.78:   return 'portrait',   r
    if r > 1.75:   return 'panorama',   r
    if r > 1.18:   return 'landscape',  r
    return 'standard', r


def _detect_figure_size(html_fragment):
    cls = ' '.join(re.findall(r'class=["\']([^"\']*)["\']', html_fragment, re.IGNORECASE))
    if any(s in cls for s in ('size-full', 'size-large', 'alignfull', 'alignwide')):
        return 'full'
    if any(s in cls for s in ('size-medium', 'aligncenter')):
        return 'medium'
    if any(s in cls for s in ('size-thumbnail', 'size-small', 'alignleft', 'alignright')):
        return 'small'
    w = re.search(r'\bwidth=["\'](\d+)["\']', html_fragment, re.IGNORECASE)
    if w:
        n = int(w.group(1))
        return 'full' if n > 600 else ('medium' if n > 300 else 'small')
    return 'full'


def _figure_cost(block):
    img   = block.get('img') or block.get('html', '')
    shape, _ = _image_shape(img)
    size  = block.get('size', 'full')
    if size == 'small':     return 75
    if shape == 'portrait': return 145
    if shape == 'panorama': return 125
    if size == 'medium':    return 115
    return 135


def _build_pe_rows(photo_figs, page_w=_PE_W, target_h=_PE_TGT, max_per_row=4):
    items = []
    for img_tag, cap in photo_figs:
        r = _aspect(img_tag)
        items.append({'img': img_tag, 'cap': (cap or '').strip(), 'aspect': r})

    rows, cur, cur_w = [], [], 0.0
    for it in items:
        w_at_target = target_h * it['aspect']
        if cur and (cur_w + w_at_target > page_w * 1.08 or len(cur) >= max_per_row):
            rows.append(_justify_row(cur, page_w))
            cur, cur_w = [], 0.0
        cur.append(it)
        cur_w += w_at_target
    if cur:
        rows.append(_justify_row(cur, page_w, is_last=True))
    return rows


def _justify_row(items, page_w, is_last=False, gap_px=3):
    n        = len(items)
    gap_mm   = gap_px * 0.264583
    usable   = max(page_w - gap_mm * max(0, n - 1), page_w * 0.5)
    total_r  = sum(it['aspect'] for it in items) or 1.0
    h_mm     = max(30.0, min(usable / total_r, 155.0))
    result   = []
    for it in items:
        w_pct = (it['aspect'] / total_r) * 100.0
        result.append({**it, 'w_pct': w_pct, 'h_mm': h_mm})
    return result


def _rows_to_pages(rows, page_h=_PE_H, gap=_PE_GAP, first_page_h=None):
    pages, cur_page, cur_h = [], [], 0.0
    for row in rows:
        limit   = first_page_h if (first_page_h and not pages) else page_h
        h_row   = row[0]['h_mm']
        h_cap   = 5.0 if any(it['cap'] for it in row) else 0.0
        h_total = h_row + h_cap + gap
        if cur_page and cur_h + h_total > limit:
            pages.append(cur_page)
            cur_page, cur_h = [], 0.0
        cur_page.append(row)
        cur_h += h_total
    if cur_page:
        pages.append(cur_page)
    return pages or [[]]


def _stretch_photo_pages(pages_of_rows, page_h=_PE_H, gap=_PE_GAP, first_page_h=None):
    for page_idx, rows in enumerate(pages_of_rows):
        if not rows:
            continue
        limit      = first_page_h if (first_page_h and page_idx == 0) else page_h
        cap_total  = sum(5.0 if any(it['cap'] for it in row) else 0.0 for row in rows)
        gap_total  = gap * max(0, len(rows) - 1)
        img_total  = sum(row[0]['h_mm'] for row in rows)
        target_img = max(0.0, limit * 0.92 - cap_total - gap_total)
        if img_total <= 0 or img_total >= target_img:
            continue
        scale = min(1.05, target_img / img_total)
        for row in rows:
            new_h = min(155.0, row[0]['h_mm'] * scale)
            for item in row:
                item['h_mm'] = new_h
    return pages_of_rows


def _render_pe_page(rows_on_page):
    html = ''
    for row in rows_on_page:
        h_mm  = row[0]['h_mm']
        cells = ''
        for item in row:
            cap_html = (f'<div class="pe-cap">{_cap_html(item["cap"])}</div>'
                        if item['cap'] else '')
            cells += (f'<div class="pe-cell" style="flex:{item["aspect"]:.4f} 1 0">'
                      f'<div class="pe-img-box" style="height:{h_mm:.1f}mm">'
                      f'{item["img"]}</div>'
                      f'{cap_html}</div>')
        html += f'<div class="pe-row">{cells}</div>\n'
    return html


def _render_editorial_photo_grid(figs, accent, extra_class='editorial-photo-grid'):
    photo_figs = [(fig.get('img', ''), fig.get('caption', '') or '')
                  for fig in (figs or []) if fig.get('img')]
    if not photo_figs:
        return ''
    rows = _build_pe_rows(photo_figs, target_h=52.0, max_per_row=3)
    return (f'<div class="{extra_class}" style="--ac:{_h(accent)}">'
            f'{_render_pe_page(rows)}</div>')


def _render_sequence_panels(figs, accent, panel_start_idx=0):
    ac = _h(accent)
    items = []
    for fig in figs:
        if isinstance(fig, dict):
            img = fig.get('img', '')
            cap = (fig.get('caption') or '').strip()
        else:
            img = fig[0] if fig else ''
            cap = (fig[1] if len(fig) > 1 else '') or ''
            cap = cap.strip()
        if img:
            items.append((img, cap))
    if not items:
        return ''

    IMG_W_MM = 174.0 * 0.62
    MIN_H    = 66.0
    MAX_H    = 108.0

    panels_html = ''
    for i, (img, cap) in enumerate(items):
        asp      = _aspect(img, fallback=1.35)
        panel_h  = max(MIN_H, min(IMG_W_MM / asp, MAX_H))
        global_i = panel_start_idx + i
        alt_cls  = ' alt' if global_i % 2 == 1 else ''
        num_str  = f'#{global_i + 1:02d}'
        cap_html = (f'<p class="seq-panel-caption">{_cap_html(cap)}</p>' if cap
                    else '<p class="seq-panel-caption"></p>')
        panels_html += (
            f'<div class="seq-panel{alt_cls}"'
            f' style="height:{panel_h:.1f}mm;--ac:{ac}">'
            f'<div class="seq-panel-img">'
            + img +
            f'</div>'
            f'<div class="seq-panel-text">'
            f'<span class="seq-panel-num">{num_str}</span>'
            f'{cap_html}'
            f'</div>'
            f'</div>\n')

    return (f'<div class="seq-panels" style="--ac:{ac}">'
            f'{panels_html}</div>')


def _render_crowd_group(figs, accent):
    ac    = _h(accent)
    items = []
    for fig in figs:
        if isinstance(fig, dict):
            img = fig.get('img', '')
            cap = (fig.get('caption') or '').strip()
        else:
            img, cap = (fig[0] or ''), ((fig[1] or '') if len(fig) > 1 else '')
            cap = cap.strip()
        if img:
            items.append((img, cap))
    if not items:
        return ''
    rows     = _build_pe_rows(items, page_w=_PE_W, target_h=85.0, max_per_row=2)
    rows_html = _render_pe_page(rows)
    return (f'<div class="crowd-group" style="--ac:{ac}">{rows_html}</div>')


def _normalise_photo_items(figs, max_items=20):
    items = []
    for fig in (figs or [])[:max_items]:
        if isinstance(fig, dict):
            img = fig.get('img', '')
            cap = (fig.get('caption', '') or '').strip()
        else:
            flist = list(fig) if fig else []
            img = flist[0] if flist else ''
            cap = (flist[1] if len(flist) > 1 else '') or ''
            cap = cap.strip()
        if img:
            items.append({'img': img, 'cap': cap, 'asp': _aspect(img, fallback=1.35)})
    return items


def _frame_layout_cells(items, canvas_w=174.0, canvas_h=262.0):
    items = list(items[:20])
    n = len(items)
    if not n:
        return []

    GAP = 2.5

    seed    = _stable_seed('|'.join(it['img'] for it in items))
    rng     = random.Random(seed)
    ordered = sorted(items, key=lambda it: (_stable_seed(it['img']) % 997, it['asp']))
    rng.shuffle(ordered)

    def _bsp(x, y, w, h, count):
        if count <= 0:
            return []
        if count == 1:
            return [(x, y, w, h)]
        horiz = (h > w * 1.1) or (h > w * 0.9 and rng.random() < 0.45)
        t  = rng.triangular(0.28, 0.72, 0.50)
        n1 = max(1, min(count - 1, round(count * t)))
        n2 = count - n1
        if horiz:
            h1 = h * t
            return (_bsp(x, y,      w, h1,      n1) +
                    _bsp(x, y + h1, w, h - h1,  n2))
        else:
            w1 = w * t
            return (_bsp(x,      y, w1,      h, n1) +
                    _bsp(x + w1, y, w - w1,  h, n2))

    raw = _bsp(0, 0, canvas_w, canvas_h, n)

    EPS = 0.5
    g   = GAP / 2.0
    cells = []
    for x, y, w, h in raw:
        x2 = x          if x < EPS              else x + g
        y2 = y          if y < EPS              else y + g
        x3 = x + w      if (x + w) > canvas_w - EPS else x + w - g
        y3 = y + h      if (y + h) > canvas_h - EPS else y + h - g
        cells.append((x2, y2, max(10.0, x3 - x2), max(10.0, y3 - y2)))

    placed = []
    for it, (cx, cy, cw, ch) in zip(ordered, cells):
        cell_asp = cw / max(ch, 0.01)
        nat_asp  = it['asp']
        rot_asp  = 1.0 / max(nat_asp, 1e-6)
        err_nat  = abs(math.log(max(nat_asp / cell_asp, 1e-6)))
        err_rot  = abs(math.log(max(rot_asp / cell_asp, 1e-6)))
        rotate   = err_rot < err_nat
        placed.append((it, cx, cy, cw, ch, rotate))

    return placed


def _render_organic_frame_grid(figs, accent, canvas_w=174.0, canvas_h=262.0):
    items = _normalise_photo_items(figs, max_items=20)
    if not items:
        return ''

    ac = _h(accent)
    cells = ''
    for it, x, y, w, h, rotate in _frame_layout_cells(items, canvas_w, canvas_h):
        xp = x / canvas_w * 100
        yp = y / canvas_h * 100
        wp = w / canvas_w * 100
        hp = h / canvas_h * 100
        rot_cls = ' msn-cell-rot' if rotate else ''
        rot_vars = f'--rw:{h:.2f};--rh:{w:.2f};' if rotate else ''
        cap_html = f'<div class="msn-cap">{_cap_html(it["cap"])}</div>' if it['cap'] else ''
        cells += (f'<div class="msn-cell{rot_cls}"'
                  f' style="left:{xp:.3f}%;top:{yp:.3f}%;'
                  f'width:{wp:.3f}%;height:{hp:.3f}%;{rot_vars}">'
                  f'{it["img"]}{cap_html}</div>\n')

    return f'<div class="msn-canvas" style="--ac:{ac}">{cells}</div>'


def _photo_group_chunks(figs, max_per_page=12):
    valid = [f for f in (figs or []) if isinstance(f, dict) and f.get('img')]
    chunks = [valid[i:i + max_per_page] for i in range(0, len(valid), max_per_page)]
    if len(chunks) > 1 and len(chunks[-1]) < 3:
        while len(chunks[-1]) < 3 and len(chunks[-2]) > 3:
            chunks[-1].insert(0, chunks[-2].pop())
    return chunks


_PG_COLS  = 3
_PG_GAP   = 3.0
_PG_COL_W = (_PE_W - _PG_GAP * (_PG_COLS - 1)) / _PG_COLS


def _pg_photo_story_pages(photo_figs, accent, art, page_offset, cfg, intro_html=''):
    MIN_ROW_H = 35.0
    MAX_ROW_H = 82.0
    CANVAS_H  = 264.0
    INTRO_H   = 40.0

    pub_name = cfg.get('publication', {}).get('name', 'The Voice Express')
    title    = (art.get('title', '') or '')[:55]
    ac       = _h(accent)

    if not photo_figs:
        return []

    raw_rows = []
    for i in range(0, len(photo_figs), _PG_COLS):
        batch = photo_figs[i:i + _PG_COLS]
        if not batch:
            continue
        row_h = MIN_ROW_H
        for img, _cap in batch:
            asp   = _aspect(img, fallback=1.35)
            row_h = max(row_h, _PG_COL_W / asp)
        row_h = min(row_h, MAX_ROW_H)
        raw_rows.append({'batch': batch, 'h': row_h})

    if not raw_rows:
        return []

    pages_rows: list = []
    cur: list        = []
    cur_h            = 0.0

    for row in raw_rows:
        has_intro_here = (not pages_rows) and bool(intro_html and intro_html.strip())
        avail  = CANVAS_H - (INTRO_H if has_intro_here else 0.0)
        needed = row['h'] + (_PG_GAP if cur else 0.0)

        if cur and cur_h + needed > avail:
            pages_rows.append(cur)
            cur, cur_h = [], 0.0

        cur.append(row)
        cur_h += needed

    if cur:
        pages_rows.append(cur)

    out = []
    for pg_idx, page_rows in enumerate(pages_rows):
        pg_n      = f'img.{page_offset + pg_idx}'
        has_intro = pg_idx == 0 and bool(intro_html and intro_html.strip())
        intro     = f'<div class="ps-intro">{intro_html}</div>' if has_intro else ''

        rows_html = ''
        for row in page_rows:
            cells = ''
            for img, cap in row['batch']:
                cap_html = f'<div class="pg-cap">{_cap_html(cap)}</div>' if cap else ''
                cells += (f'<div class="pg-cell">'
                          f'<div class="pg-img-box"'
                          f' style="height:{row["h"]:.1f}mm">'
                          f'{img}</div>{cap_html}</div>')
            for _ in range(_PG_COLS - len(row['batch'])):
                cells += '<div class="pg-cell pg-cell-empty"></div>'
            rows_html += f'<div class="pg-row">{cells}</div>\n'

        out.append(f'''<div class="page p-body p-photo-story" style="--ac:{ac}">
  <div class="body-run">
    <span class="body-run-pub">{_h(pub_name)}</span>
    <span class="body-run-title">{_h(title)}</span>
    <span class="body-run-pg">{pg_n}</span>
  </div>
  {intro}
  <div class="pg-grid">{rows_html}</div>
</div>''')

    return out


def _geo_callout(text, accent='#c8a84a', compact=False):
    txt = _plain(str(text or '')).strip()
    if not txt:
        return ''
    ac  = _h(accent)
    cls = ' geo-callout-compact' if compact else ''
    return (f'<div class="geo-callout{cls}" style="--ac:{ac}">'
            f'<svg class="geo-callout-lines" viewBox="0 0 100 100" '
            f'preserveAspectRatio="none" aria-hidden="true">'
            f'<path d="M2 10 H68 L98 40 V98 H16 L2 82 Z"/>'
            f'<path d="M72 10 V2 H98 V28"/>'
            f'</svg>'
            f'<p>{_h(txt)}</p></div>')


def _figure_block_from_html(full):
    size  = _detect_figure_size(full)
    img_m = re.search(r'<img\b[^>]*/?>', full, re.IGNORECASE)
    cap_m = re.search(r'<figcaption[^>]*>(.*?)</figcaption>',
                      full, re.DOTALL | re.IGNORECASE)
    cap   = _split_caption_credit(cap_m.group(1)) if cap_m else ''
    return {'type': 'figure', 'html': full, 'size': size,
            'caption': cap, 'img': img_m.group(0) if img_m else None}


def _semantic_blocks(html):
    if BeautifulSoup is None:
        return None
    soup = BeautifulSoup(html or '', 'html.parser')

    def direct_tags(node):
        return [c for c in node.children if isinstance(c, _BSTag)]

    def fig_info(fig):
        full  = str(fig)
        block = _figure_block_from_html(full)
        block['html'] = full
        return block

    def collect_role_html(node, roles=None):
        out = []
        for el in node.find_all(['p', 'figcaption'], recursive=True):
            role = el.get('data-text-role')
            if roles is None or role in roles:
                out.append(str(el))
        return ''.join(out)

    def parse_node(el):
        tag     = el.name.lower()
        classes = set(el.get('class', []))
        full    = str(el)

        if tag == 'div':
            if 'photo-narrative-unit' in classes:
                fig        = el.find('figure')
                img        = fig.find('img') if fig else el.find('img')
                prose      = el.find(class_='photo-prose')
                cap_html   = collect_role_html(
                    el, {'caption', 'subtitle', 'annotation', 'excerpt'})
                prose_html = (''.join(str(c) for c in direct_tags(prose))
                              if prose else collect_role_html(el, {'description'}))
                return {'type': 'photo_narrative', 'html': full,
                        'fig_html':    str(fig) if fig else '',
                        'img':         str(img) if img else '',
                        'caption':     _plain(cap_html),
                        'caption_html': cap_html,
                        'prose_html':  prose_html}

            if 'photo-unit' in classes:
                fig      = el.find('figure')
                img      = fig.find('img') if fig else el.find('img')
                cap_html = collect_role_html(
                    el, {'caption', 'subtitle', 'annotation', 'excerpt', 'description'})
                return {'type': 'photo_unit', 'html': full,
                        'fig_html':    str(fig) if fig else '',
                        'img':         str(img) if img else '',
                        'caption':     _plain(cap_html),
                        'caption_html': cap_html,
                        'unit_type':   el.get('data-type', 'captioned')}

            if 'photo-group' in classes:
                figs = [fig_info(f) for f in el.find_all('figure')]
                return {'type': 'photo_group', 'html': full,
                        'group_type': el.get('data-type', 'dump'),
                        'figures':    figs}

            if 'article-section' in classes:
                inner = []
                for child in direct_tags(el):
                    result = parse_node(child)
                    if isinstance(result, list):
                        inner.extend(result)
                    elif result:
                        inner.append(result)
                return {'type': 'section', 'html': full,
                        'section_index': el.get('data-section-index', ''),
                        'blocks': _merge_continuations(inner)}

            if 'post-header' in classes:
                inner = []
                for child in direct_tags(el):
                    result = parse_node(child)
                    if isinstance(result, list):
                        inner.extend(result)
                    elif result:
                        inner.append(result)
                return inner

            inner = []
            for child in direct_tags(el):
                result = parse_node(child)
                if isinstance(result, list):
                    inner.extend(result)
                elif result:
                    inner.append(result)
            if inner:
                return inner
            return {'type': 'paragraph', 'html': full}

        if tag == 'figure':
            return fig_info(el)

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            return {'type': 'heading', 'level': int(tag[1]),
                    'text': el.get_text(' ', strip=True), 'html': full}

        if tag == 'blockquote':
            txt      = _plain(el)
            cite     = ''
            cite_el  = el.find('cite')
            if cite_el:
                cite = _plain(str(cite_el))
                cite_el.extract()
                txt = _plain(str(el))
            cls = ' '.join(el.get('class', []))
            return {'type': 'quote', 'html': full,
                    'text': txt, 'cite': cite, 'block_class': cls}

        if tag in ('ul', 'ol'):
            return {'type': 'list', 'html': full}
        if tag == 'hr':
            return {'type': 'divider', 'html': full}
        if tag == 'table':
            return {'type': 'table', 'html': full}
        if tag == 'p':
            role = el.get('data-text-role')
            return {'type': 'paragraph', 'html': full,
                    'text_role': role,
                    'class': ' '.join(el.get('class', []))}

        return {'type': 'paragraph', 'html': full}

    blocks = []
    for el in direct_tags(soup):
        result = parse_node(el)
        if isinstance(result, list):
            blocks.extend(result)
        elif result:
            blocks.append(result)
    return blocks


def _fallback_blocks(html):
    BLOCK = re.compile(
        r'(<(?:p|h[2-6]|blockquote|ul|ol|hr|figure|div)\b[^>]*>.*?'
        r'</(?:p|h[2-6]|blockquote|ul|ol|figure|div)>|<hr\s*/?>|'
        r'<figure\b[^>]*/>\s*(?:<figcaption[^>]*>.*?</figcaption>)?)',
        re.DOTALL | re.IGNORECASE)
    blocks = []
    for m in BLOCK.finditer(html):
        full  = m.group(0).strip()
        tag_m = re.match(r'<(\w+)', full)
        if not tag_m:
            continue
        tag = tag_m.group(1).lower()
        if tag == 'figure':
            blocks.append(_figure_block_from_html(full))
        elif tag in ('h2', 'h3', 'h4', 'h5', 'h6'):
            blocks.append({'type': 'heading', 'level': int(tag[1]),
                           'text': _plain(full), 'html': full})
        elif tag == 'blockquote':
            cite_m = re.search(r'<cite[^>]*>(.*?)</cite>',
                               full, re.DOTALL | re.IGNORECASE)
            cite   = _plain(cite_m.group(1)) if cite_m else ''
            txt    = re.sub(r'<cite[^>]*>.*?</cite>', '', full,
                            flags=re.DOTALL | re.IGNORECASE)
            cls_m  = re.search(r'class=["\']([^"\']*)["\']', full, re.IGNORECASE)
            blocks.append({'type': 'quote', 'html': full,
                           'text': _plain(txt), 'cite': cite,
                           'block_class': cls_m.group(1) if cls_m else ''})
        elif tag in ('ul', 'ol'):
            blocks.append({'type': 'list', 'html': full})
        elif tag == 'hr':
            blocks.append({'type': 'divider', 'html': full})
        elif tag == 'table':
            blocks.append({'type': 'table', 'html': full})
        else:
            blocks.append({'type': 'paragraph', 'html': full})
    return blocks


def _merge_continuations(blocks):
    merged = []
    for blk in blocks:
        if (blk['type'] == 'paragraph'
                and not blk.get('text_role')
                and merged
                and merged[-1]['type'] == 'paragraph'):
            plain = _plain(blk['html']).lstrip()
            if plain and plain[0].islower():
                prev = merged[-1]
                prev_html = prev['html'].rstrip()
                if prev_html.lower().endswith('</p>'):
                    prev_html = prev_html[:-4].rstrip()
                cur_inner = re.sub(r'^<p[^>]*>', '', blk['html'].lstrip(),
                                   flags=re.IGNORECASE).lstrip()
                prev['html'] = prev_html + ' ' + cur_inner
                continue
        merged.append(blk)
    return merged


def _parse_blocks(html):
    result = _semantic_blocks(html)
    blocks = result if result is not None else _fallback_blocks(html)
    return _merge_continuations(blocks)


def _runs_from_html(html):
    if BeautifulSoup is None:
        return [{'text': _plain(html or '')}]
    soup = BeautifulSoup(html or '', 'html.parser')
    runs = []

    def walk(node, bold=False, italic=False, underline=False, color=None, href=None):
        for child in node.children:
            if isinstance(child, _BSTag):
                name = child.name.lower()
                nb, ni, nu, nc, nh = bold, italic, underline, color, href
                if name in ('b', 'strong'):
                    nb = True
                elif name in ('i', 'em'):
                    ni = True
                elif name == 'u':
                    nu = True
                elif name == 'a':
                    nh = child.get('href') or href
                elif name == 'sup' and child.get('data-fn'):
                    runs.append({'text': f'[{child.get("data-fn")}]'})
                    continue
                m = re.search(r'color\s*:\s*([^;]+)', child.get('style', '') or '')
                if m:
                    nc = m.group(1).strip()
                walk(child, nb, ni, nu, nc, nh)
            else:
                text = _html_mod.unescape(str(child))
                if text:
                    run = {'text': text}
                    if bold: run['bold'] = True
                    if italic: run['italic'] = True
                    if underline: run['underline'] = True
                    if color: run['color'] = color
                    if href: run['href'] = href
                    runs.append(run)

    walk(soup)
    return runs or [{'text': _plain(html or '')}]


def _paginate_blocks(blocks, budget):
    def _expand(items):
        expanded = []
        for b in items or []:
            t = b.get('type')
            if t == 'section':
                expanded.extend(_expand(b.get('blocks', [])))
                continue
            if t == 'paragraph':
                expanded.append(b)
                continue
            if t == 'photo_group' and b.get('group_type') == 'sequence':
                figs = [f for f in (b.get('figures', []) or []) if f.get('img')]
                total = len(figs)
                for k, fig in enumerate(figs):
                    expanded.append({
                        'type':             'photo_group',
                        'group_type':       'sequence',
                        '_seq_panel_idx':   k,
                        '_seq_panel_total': total,
                        'figures':          [fig],
                    })
                continue
            if t == 'gallery':
                figs = list(b.get('figures', []) or [])
                if len(figs) > 4:
                    for start in range(0, len(figs), 4):
                        nb = dict(b); nb['figures'] = figs[start:start + 4]
                        expanded.append(nb)
                    continue
            expanded.append(b)
        return expanded

    def _cost(b):
        t = b['type']
        if t == 'figure':       return _figure_cost(b)
        if t == 'gallery':      return 90 if len(b.get('figures', [])) <= 2 else 140
        if t == 'photo_group':
            gtype = b.get('group_type', 'dump')
            if gtype == 'sequence':             return 175
            if gtype == 'crowd':                return 190
            nf = len(b.get('figures', []))
            if nf >= 4:  return budget + 1
            return 130 if nf <= 2 else 180
        if t == 'photo_unit':   return 115
        if t == 'photo_narrative': return 145 + min(_words(b.get('prose_html', '')), 80)
        if t == 'section':      return 35 + sum(_cost(x) for x in b.get('blocks', []))
        if t == 'quote':        return len(b.get('text', '').split()) + 55
        if t == 'heading':      return 28
        if t == 'divider':      return 12
        return _words(b.get('html', ''))

    blocks = _expand(blocks)
    n      = len(blocks)
    pages, cur, cur_w = [], [], 0
    for idx, b in enumerate(blocks):
        t = b['type']
        c = _cost(b)
        if t == 'heading' and cur and idx + 1 < n:
            next_c = min(_cost(blocks[idx + 1]), max(80, budget // 4))
            if cur_w + c + next_c > budget:
                pages.append(cur); cur, cur_w = [], 0
        elif cur_w + c > budget and cur:
            pages.append(cur); cur, cur_w = [], 0
        cur.append(b); cur_w += c
    if cur:
        pages.append(cur)
    return pages or [[]]


def _pq_html(text, cite, style, accent='#c8a84a', text_html=None):
    text = text_html if text_html is not None else \
        _h(_html_mod.unescape(re.sub(r'\s+', ' ', str(text or ''))).strip())
    if not text:
        return ''
    cite_html = f'<p class="pq-cite">{_h(cite)}</p>' if cite else ''
    ac        = _h(accent)

    if style == 2:
        return (f'<div class="pq pq-dark" style="--ac:{ac}"><div class="pq-dark-inner">'
                f'<p class="pq-text">{text}</p>{cite_html}</div></div>')
    if style == 3:
        return (f'<div class="pq pq-hang" style="--ac:{ac}">'
                f'<div class="pq-hang-glyph">&ldquo;</div>'
                f'<div class="pq-hang-body"><p class="pq-text">{text}</p>'
                f'{cite_html}</div></div>')
    if style == 4:
        return (f'<div class="pq pq-monument" style="--ac:{ac}">'
                f'<p class="pq-text pq-monument-text">{text}</p>{cite_html}</div>')
    if style == 5:
        return (f'<div class="pq pq-apos" style="--ac:{ac}">'
                f'<p class="pq-text pq-apos-text">{text}</p>{cite_html}</div>')
    if style == 6:
        return (f'<div class="pq pq-band" style="--ac:{ac}">'
                f'<div class="pq-band-bar"></div>'
                f'<div class="pq-band-body">'
                f'<p class="pq-text pq-band-text">{text}</p>'
                f'{cite_html}</div></div>')
    if style == 7:
        return (f'<div class="pq pq-rules" style="--ac:{ac}">'
                f'<div class="pq-rules-top"></div>'
                f'<p class="pq-text pq-rules-text">{text}</p>'
                f'{cite_html}'
                f'<div class="pq-rules-bot"></div></div>')
    return (f'<div class="pq pq-classic" style="--ac:{ac}">'
            f'<div class="pq-mark">&ldquo;</div>'
            f'<p class="pq-text">{text}</p>{cite_html}</div>')


def _para_fit(words):
    if words <= 70:
        return '', 52
    if words <= 110:
        return 'fit-tight', 47
    if words <= 160:
        return 'fit-tighter', 41
    return 'fit-min', 35


def _render_blocks(blk_list, art_type, pq_style, accent, is_first, citations=None):
    parts     = []
    drop_done = [not is_first]
    n         = len(blk_list)
    consumed  = set()

    def _para(ph):
        if citations:
            ph = _inject_cite_refs(ph, citations)
        if not drop_done[0]:
            drop_done[0] = True
            ph = re.sub(r'<p(\s[^>]*)?>',
                        '<p class="drop-cap">', ph, count=1, flags=re.IGNORECASE)
        return ph

    for idx, blk in enumerate(blk_list):
        if idx in consumed:
            continue
        t = blk['type']

        if t == 'paragraph':
            role = blk.get('text_role', '') or ''
            ph   = blk.get('html', '')

            if role == 'testimony' and art_type in ('ground_report', 'field', 'dispatch'):
                txt = _plain(ph)
                if txt:
                    parts.append(_pq_html(txt, '', 2, accent))
                    continue

            _ROLE_CLASS = {
                'dateline':   'role-dateline',
                'testimony':  'role-testimony',
                'scene':      'role-scene',
                'resolution': 'role-resolution',
                'note':       'role-note',
                'context':    'role-context',
            }
            if role in _ROLE_CLASS:
                rc = _ROLE_CLASS[role]
                if re.search(r'<p\s[^>]*class=', ph, re.IGNORECASE):
                    ph = re.sub(r'(<p\s[^>]*class=["\'])([^"\']*)',
                                lambda m: m.group(1) + rc + ' ' + m.group(2),
                                ph, count=1, flags=re.IGNORECASE)
                else:
                    ph = re.sub(r'<p(\s[^>]*)?>', lambda m:
                                f'<p class="{rc}"{m.group(1) or ""}>',
                                ph, count=1, flags=re.IGNORECASE)

            ph = _para(ph)

            if role == 'lede':
                ph = f'<div class="lede-span">{ph}</div>'

            parts.append(ph)

        elif t == 'heading':
            parts.append(blk['html'])

        elif t == 'quote':
            txt  = blk.get('text', '')
            cite = blk.get('cite', '')
            if not txt:
                continue
            style = 4 if art_type == 'interview' else pq_style
            parts.append(_pq_html(txt, cite, style, accent))

        elif t == 'section':
            inner = _render_blocks(blk.get('blocks', []), art_type, pq_style,
                                   accent, is_first=False, citations=citations)
            if inner:
                si_raw = blk.get('section_index', '') or ''
                si     = _h(si_raw)
                label  = _SECTION_LABELS.get(si_raw.lower(), '')
                num_marker = ''
                if si_raw.isdigit():
                    num_marker = (f'<div class="section-chapter-num"'
                                  f' style="--ac:{_h(accent)}">{si_raw}</div>')
                divider_html = ''
                if label:
                    divider_html = (
                        f'<div class="section-divider" style="--ac:{_h(accent)}">'
                        f'<span class="section-divider-rule"></span>'
                        f'<span class="section-divider-label">{_h(label)}</span>'
                        f'<span class="section-divider-rule"></span>'
                        f'</div>')
                parts.append(
                    f'<section class="semantic-article-section" '
                    f'data-section-index="{si}">'
                    f'{num_marker}{divider_html}{inner}</section>')

        elif t == 'photo_narrative':
            fig_html   = blk.get('fig_html') or ''
            img        = blk.get('img') or ''
            cap_html   = blk.get('caption_html') or ''
            prose_html = blk.get('prose_html') or ''
            if citations and prose_html:
                prose_html = _inject_cite_refs(prose_html, citations)
            if not img and not fig_html:
                continue
            media = (fig_html if fig_html
                     else f'<figure class="art-fig">{img}</figure>')
            call  = _geo_callout(blk.get('caption', ''), accent) if blk.get('caption') else ''
            alt   = ' alt' if idx % 2 else ''
            parts.append(
                f'<div class="semantic-photo-narrative immersive-split{alt}">'
                f'<div class="semantic-photo-media">{media}{cap_html}{call}</div>'
                f'<div class="semantic-photo-prose">{prose_html}</div>'
                f'</div>')

        elif t == 'photo_unit':
            fig_html   = blk.get('fig_html') or ''
            img        = blk.get('img') or ''
            cap_html   = blk.get('caption_html') or ''
            if not img and not fig_html:
                continue
            cap_plain  = (blk.get('caption', '') or '').lower()
            creditish  = any(k in cap_plain for k in (
                'image courtesy', 'photo courtesy', 'courtesy:', 'courtesy ',
                'photo:', 'image:', 'credit:', 'source:'))
            compact    = creditish or _words(cap_html) < 18
            media      = f'<figure class="photo-unit-figure">{img}</figure>' if img else fig_html
            call       = _geo_callout(blk.get('caption', ''), accent) if blk.get('caption') else ''
            alt        = ' alt' if idx % 2 else ''
            cc         = ' photo-card-compact' if compact else ''
            parts.append(
                f'<div class="semantic-photo-unit semantic-photo-card{cc} immersive-split{alt}" '
                f'data-type="{_h(blk.get("unit_type","captioned"))}">'
                f'{media}<div class="semantic-photo-caption">{cap_html}</div>{call}</div>')

        elif t == 'photo_group':
            gtype     = blk.get('group_type', 'dump')
            figs_raw  = blk.get('figures', [])
            valid_figs = [f for f in figs_raw if f.get('img')]
            rendered  = ''

            if gtype == 'crowd':
                rendered = _render_crowd_group(valid_figs if valid_figs else figs_raw, accent)
            elif gtype == 'sequence':
                panel_idx = blk.get('_seq_panel_idx', idx)
                rendered  = _render_sequence_panels(
                    valid_figs if valid_figs else figs_raw, accent,
                    panel_start_idx=panel_idx)
            else:
                figs_to_use = valid_figs if valid_figs else figs_raw
                rendered = _render_organic_frame_grid(figs_to_use, accent)

            if rendered:
                parts.append(rendered)

        elif t == 'figure':
            img  = blk.get('img', '')
            cap  = (blk.get('caption', '') or '').strip()
            size = blk.get('size', 'full')
            if not img:
                continue

            cap_html  = (f'<figcaption>{_cap_html(cap)}</figcaption>' if cap
                         else '<figcaption></figcaption>')
            cap_l     = cap.lower()
            creditish = any(k in cap_l for k in (
                'image courtesy', 'photo courtesy', 'courtesy:', 'courtesy ',
                'photo:', 'image:', 'credit:', 'source:'))
            real_cap  = len(cap) > 35 and not creditish
            sz_cls    = ('art-fig-full' if size == 'full'
                         else ('art-fig-md' if size == 'medium' else 'art-fig-sm'))

            next_idx = idx + 1
            while next_idx < n and next_idx in consumed:
                next_idx += 1
            next_blk     = blk_list[next_idx] if next_idx < n else None
            next_is_para = next_blk is not None and next_blk['type'] == 'paragraph'
            next_words   = _words(next_blk.get('html', '')) if next_is_para else 0
            shape, _asp  = _image_shape(img)

            if next_is_para:
                consumed.add(next_idx)
                para_html = _para(next_blk['html'])
                alt = ' alt' if idx % 2 else ''
                fit_cls, img_pct = _para_fit(next_words)
                txt_cls = ('img-para-text ' + fit_cls).rstrip()
                if size == 'small':
                    parts.append(
                        f'<div class="img-float-wrap">'
                        f'<figure class="img-float">{img}{cap_html}</figure>'
                        f'{para_html}'
                        f'<div class="img-float-clear"></div></div>')
                elif size == 'medium' or shape == 'portrait':
                    grd = f'grid-template-columns:{img_pct}% {100 - img_pct}%'
                    parts.append(
                        f'<div class="img-para-side immersive-split{alt}" style="{grd}">'
                        f'<figure class="img-para-fig">{img}{cap_html}</figure>'
                        f'<div class="{txt_cls}">{para_html}</div></div>')
                else:
                    parts.append(
                        f'<div class="img-para-stacked">'
                        f'<figure class="img-para-fig">{img}{cap_html}</figure>'
                        f'<div class="{txt_cls}">{para_html}</div></div>')
            elif real_cap:
                alt = ' alt' if idx % 2 else ''
                parts.append(
                    f'<div class="side-fig side-fig-callout immersive-split{alt}">'
                    f'<div class="side-fig-img">{img}</div>'
                    f'<div class="side-fig-text">{_geo_callout(cap, accent)}</div>'
                    f'</div>')
            else:
                parts.append(f'<figure class="art-fig {sz_cls}">{img}{cap_html}</figure>')

        elif t == 'gallery':
            figs = blk.get('figures', [])
            if not figs:
                continue
            rendered = _render_editorial_photo_grid(
                figs, accent, 'gallery-editorial editorial-photo-grid')
            if rendered:
                parts.append(rendered)

        elif t in ('list', 'table', 'divider'):
            parts.append(blk.get('html', ''))

    return ''.join(parts)


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Montserrat:wght@300;400;600;700;800;900&family=Cormorant+Garamond:ital,wght@0,300;0,600;1,300;1,600&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

@page { size:A4; margin:0 }
@media print {
  html,body { margin:0; padding:0; background:#fff }
  .page     { box-shadow:none!important; margin:0!important }
  .no-print { display:none!important }
  a         { color:inherit; text-decoration:none }
}
@media screen {
  body  { background:#1a1a1a; padding:2em 0 6em }
  .page { box-shadow:0 24px 80px rgba(0,0,0,.80), 0 2px 8px rgba(0,0,0,.35);
          margin:0 auto 3em;
          transform-origin:top center }
}

*,*::before,*::after { box-sizing:border-box; margin:0; padding:0 }
html { font-size:10.5pt }

:root {
  --ink:    #0d0d0d;
  --paper:  #faf9f7;
  --warm:   #f0ece3;
  --mid:    #666;
  --lt:     #d8d4ce;
  --accent: #c8a84a;
  --ac:     var(--accent);
  --cov:    #000;
  --disp:   'Playfair Display', Georgia, serif;
  --serif:  'EB Garamond','Times New Roman',Georgia,serif;
  --corm:   'Cormorant Garamond', Georgia, serif;
  --sans:   'Montserrat',Helvetica,Arial,sans-serif;
  --mono:   'IBM Plex Mono','Courier New',Courier,monospace;
  --pad:    12mm 14mm 10mm 18mm;
  --gap:    2.6em;
  --gap3:   1.9em;
}

body { font-family:var(--serif); color:var(--ink) }
.no-print {
  position:fixed; bottom:1.5em; right:1.5em; z-index:9999; display:flex; gap:.5em;
}
.no-print button {
  background:#111; color:#fff; border:none; cursor:pointer;
  font-family:var(--mono); font-size:.62rem; text-transform:uppercase;
  letter-spacing:.1em; padding:.55em 1.2em; transition:background .2s;
}
.no-print button:hover { background:#333 }
.page {
  width:210mm; height:297mm; background:var(--paper);
  position:relative; overflow:hidden;
  page-break-after:always; break-after:page;
}

.p-cov { background:#000; color:#f5f5f0; position:relative; overflow:hidden }
.cov-hero-bg {
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:contain; object-position:center;
  filter:brightness(.45) saturate(.7); z-index:0;
}
.cov-art {
  position:absolute; inset:0; z-index:2;
  display:flex; flex-wrap:wrap;
  align-content:center; justify-content:flex-start;
  gap:.1em .22em; padding:22mm 14mm 20mm; overflow:hidden;
}
.tw {
  display:inline-block; font-family:var(--disp); text-transform:uppercase;
  letter-spacing:.04em; line-height:1.06; transform-origin:center left;
}
.tw-xl { font-size:4.8em; font-weight:900; color:rgba(255,255,255,.92) }
.tw-lg { font-size:2.8em; font-weight:700; color:rgba(255,255,255,.65) }
.tw-md { font-size:1.55em; font-weight:500; color:rgba(255,255,255,.38) }
.tw-sm { font-size:.9em;   font-weight:400; color:rgba(255,255,255,.20) }
.tw-xs { font-size:.58em;  font-weight:300; color:rgba(255,255,255,.10) }
.cov-top {
  position:absolute; top:0; left:0; right:0; z-index:10;
  display:flex; align-items:center; gap:.7em; padding:7mm 14mm 5mm;
  border-bottom:2px solid rgba(255,255,255,.14);
  background:linear-gradient(180deg,rgba(0,0,0,.60) 0%,transparent 100%);
}
.cov-logo { height:24px; width:auto; flex-shrink:0 }
.cov-pub  {
  font-family:var(--sans); font-weight:800; font-size:.64em;
  text-transform:uppercase; letter-spacing:.24em; color:rgba(255,255,255,.55);
}
.cov-pip  { width:7mm; height:2.5px; background:var(--accent); flex-shrink:0 }
.cov-foot {
  position:absolute; bottom:0; left:0; right:0; z-index:10;
  padding:5mm 14mm 6mm; border-top:1px solid rgba(255,255,255,.14);
  background:linear-gradient(0deg,rgba(0,0,0,.75) 0%,transparent 100%);
  display:flex; justify-content:space-between; align-items:baseline;
}
.cov-foot-title {
  font-family:var(--disp); font-size:1.5em; font-weight:900;
  color:#fff; letter-spacing:-.01em; line-height:1; max-width:65%;
}
.cov-foot-meta {
  font-family:var(--mono); font-size:.46em; text-transform:uppercase;
  letter-spacing:.16em; color:rgba(255,255,255,.38); text-align:right;
}

.p-dark {
  background:var(--ink); color:#f5f5f0; padding:var(--pad);
  display:flex; flex-direction:column;
}
.mast-panel { display:grid; grid-template-columns:1fr 1fr;
  gap:2em; flex:1; min-height:0 }
.mast-l,.mast-r { display:flex; flex-direction:column }
.mast-l > img {
  display:block; width:auto; height:auto;
  max-width:52mm; max-height:28mm;
  object-fit:contain; object-position:left center;
  flex:0 0 auto; opacity:.92;
}
.mast-pub  { font-family:var(--disp); font-size:2.4em; font-weight:900; color:#f5f5f0;
  letter-spacing:-.02em; margin-bottom:.1em }
.mast-tag  { font-family:var(--corm); font-style:italic; font-size:.9em;
  color:rgba(255,255,255,.42); margin-bottom:2em }
.mast-rule { height:1px; background:rgba(255,255,255,.15); margin:.8em 0 }
.mast-lbl  { font-family:var(--mono); font-size:.52em; text-transform:uppercase;
  letter-spacing:.2em; color:rgba(255,255,255,.3); margin-bottom:.35em }
.mast-val  { font-family:var(--sans); font-weight:600; font-size:.8em;
  color:rgba(255,255,255,.72); margin-bottom:.65em }
.mast-note { font-family:var(--serif); font-size:.83em; line-height:1.72;
  color:rgba(255,255,255,.58); flex:1 }
.mast-est  { position:absolute; bottom:10mm; right:10mm;
  font-family:var(--disp); font-size:9em; font-weight:900;
  color:rgba(255,255,255,.025); line-height:1; pointer-events:none }

.founders-wrap  { font-family:var(--serif); flex:1; overflow:hidden }
.founders-kicker {
  font-family:var(--mono); font-size:.58em; text-transform:uppercase;
  letter-spacing:.22em; color:rgba(255,255,255,.35); margin-bottom:.4em;
}
.founders-title {
  font-family:var(--disp); font-size:2.5em; font-style:italic; font-weight:700;
  color:#f5f5f0; line-height:1.1; margin-bottom:.4em; letter-spacing:-.02em;
}
.founders-rule  { border:none; border-top:2px solid rgba(255,255,255,.18); margin:0 0 1.6em }
.founders-body  { font-size:.88em; line-height:1.78; color:rgba(255,255,255,.82) }
.founders-body p{ margin-bottom:.9em; text-align:justify }
.founders-body > p:first-of-type::first-letter {
  float:left; font-family:var(--disp); font-size:4.5em; font-weight:900;
  line-height:.7; margin:.05em .08em 0 0; color:#fff;
}
.founders-body strong { color:#fff }
.founders-body em     { font-style:italic }
.founders-sig { margin-top:auto; padding-top:1.2em; border-top:1px solid rgba(255,255,255,.14) }
.founders-sig-name { font-family:var(--sans); font-weight:700; font-size:.76em;
  text-transform:uppercase; letter-spacing:.1em; color:#f5f5f0 }
.founders-sig-role { font-family:var(--corm); font-style:italic; font-size:.74em;
  color:rgba(255,255,255,.4); margin-top:.2em }

.p-toc {
  overflow:hidden; display:grid; grid-template-rows:auto auto 1fr;
}
.toc-banner {
  background:#0d0d0d; padding:8mm 16mm 7mm 20mm;
  display:flex; justify-content:space-between; align-items:flex-end; flex-shrink:0;
}
.toc-banner-head {
  font-family:var(--disp); font-size:3.2em; font-weight:900;
  color:#fff; letter-spacing:-.03em; line-height:1;
}
.toc-banner-meta {
  font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.14em; color:rgba(255,255,255,.4); text-align:right; line-height:1.6;
}
.toc-subbar { background:var(--ac,var(--accent)); height:3px; flex-shrink:0 }
.toc-body {
  padding:5mm 16mm 8mm 20mm; overflow:hidden;
  display:grid; grid-template-columns:58% 42%; gap:0 6mm; align-content:start;
}
.toc-featured { display:flex; flex-direction:column; gap:4mm; overflow:hidden }
.toc-feat-item {
  display:grid; grid-template-columns:22mm 1fr; gap:3mm; align-items:start;
  padding-bottom:3.5mm; border-bottom:1px solid var(--lt); break-inside:avoid;
}
.toc-feat-item:last-child { border-bottom:none }
.toc-feat-thumb { width:22mm; height:16mm; overflow:hidden; flex-shrink:0 }
.toc-feat-thumb img {
  width:100%; height:100%; object-fit:cover; object-position:center 20%;
  filter:grayscale(8%) contrast(1.08);
}
.toc-feat-thumb-ph {
  width:100%; height:100%; background:var(--warm);
  display:flex; align-items:center; justify-content:center;
  font-family:var(--mono); font-size:.38em; color:var(--mid); text-transform:uppercase;
}
.toc-feat-n {
  font-family:var(--disp); font-size:2.2em; font-weight:900;
  color:var(--ac,var(--accent)); line-height:1; margin-bottom:.12em; display:block;
}
.toc-feat-beat {
  font-family:var(--mono); font-size:.42em; text-transform:uppercase;
  letter-spacing:.11em; color:var(--mid); margin-bottom:.18em;
}
.toc-feat-ttl {
  font-family:var(--disp); font-size:.95em; font-weight:700;
  line-height:1.22; margin-bottom:.14em;
}
.toc-feat-au {
  font-family:var(--corm); font-style:italic; font-size:.74em; color:var(--mid);
}
.toc-feat-ex {
  font-family:var(--serif); font-size:.7em; color:var(--mid);
  line-height:1.45; overflow:hidden;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
}
.toc-compact { display:flex; flex-direction:column; overflow:hidden;
  border-left:1px solid var(--lt); padding-left:4mm }
.toc-compact-head {
  font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.18em; color:var(--mid); margin-bottom:2.5mm; padding-bottom:1.5mm;
  border-bottom:1px solid var(--lt);
}
.toc-compact-item {
  display:grid; grid-template-columns:6mm 1fr; gap:2mm; align-items:baseline;
  padding:1.8mm 0; border-bottom:.5px solid var(--lt); break-inside:avoid;
}
.toc-compact-n {
  font-family:var(--mono); font-size:.46em; font-weight:700;
  color:var(--ac,var(--accent)); text-align:right; line-height:1.5;
}
.toc-compact-ttl {
  font-family:var(--disp); font-size:.78em; font-weight:700; line-height:1.22;
}
.toc-compact-beat {
  font-family:var(--mono); font-size:.42em; text-transform:uppercase;
  letter-spacing:.08em; color:var(--mid); margin-top:.08em;
}

.p-art-title {
  background:var(--ink); color:#f5f5f0; position:relative; overflow:hidden;
  display:flex; flex-direction:column; padding:var(--pad); justify-content:flex-end;
}
.art-title-num {
  position:absolute; right:10mm; top:6mm; font-family:var(--disp);
  font-size:26em; font-weight:900; color:rgba(255,255,255,.04);
  line-height:1; pointer-events:none; letter-spacing:-.05em;
}
.art-title-pip { width:14mm; height:4px; background:var(--ac,var(--accent));
  margin-bottom:.9em; flex-shrink:0 }
.art-title-badge {
  display:flex; align-items:center; gap:.7em; margin-bottom:.6em;
  flex-wrap:wrap; flex-shrink:0;
}
.art-title-sect {
  background:var(--ac,var(--accent)); color:#000;
  font-family:var(--sans); font-size:.44em; font-weight:800;
  text-transform:uppercase; letter-spacing:.2em; padding:.22em .7em;
}
.art-title-cat {
  font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.12em; color:rgba(255,255,255,.45);
}
.art-title-h1 {
  font-family:var(--disp); font-size:3.2em; font-weight:900;
  line-height:1.06; letter-spacing:-.025em; color:#fff;
  margin-bottom:.38em; hyphens:auto; overflow-wrap:break-word; flex-shrink:0;
}
.art-title-deck {
  font-family:var(--corm); font-size:1.05em; font-style:italic;
  color:rgba(255,255,255,.72); line-height:1.55; margin-bottom:.7em;
  border-left:3px solid var(--ac,var(--accent)); padding-left:.85em;
  max-width:38em; flex-shrink:0;
}
.art-title-byline {
  font-family:var(--mono); font-size:.52em; text-transform:uppercase;
  letter-spacing:.1em; color:rgba(255,255,255,.38); flex-shrink:0;
}
.art-title-byline strong {
  color:rgba(255,255,255,.8); font-family:var(--sans); font-weight:700;
  text-transform:none; letter-spacing:.04em;
}

.p-art-bleed { background:#000; position:relative; overflow:hidden }
.art-bleed-bg {
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:contain; object-position:center;
  filter:brightness(.78) saturate(.86) contrast(1.05); z-index:1;
}
.art-bleed-top-scrim {
  position:absolute; top:0; left:0; right:0; height:45%;
  background:linear-gradient(180deg,rgba(0,0,0,.55) 0%,transparent 100%);
  z-index:2; pointer-events:none;
}
.art-bleed-scrim {
  position:absolute; bottom:0; left:0; right:0; height:52%;
  background:linear-gradient(0deg,rgba(0,0,0,.94) 0%,rgba(0,0,0,.78) 38%,
    rgba(0,0,0,.40) 68%,transparent 100%);
  z-index:2; pointer-events:none;
}
.art-bleed-num {
  position:absolute; right:10mm; top:6mm; z-index:3; font-family:var(--disp);
  font-size:18em; font-weight:900; color:rgba(255,255,255,.14);
  line-height:1; letter-spacing:-.06em; pointer-events:none;
}
.art-bleed-badge {
  position:absolute; top:10mm; left:20mm; z-index:3;
  display:flex; align-items:center; gap:.6em;
}
.art-bleed-sect-tag {
  font-family:var(--sans); font-size:.44em; font-weight:800;
  text-transform:uppercase; letter-spacing:.2em;
  background:var(--ac,var(--accent)); color:#000; padding:.22em .7em;
}
.art-bleed-cat-tag {
  font-family:var(--mono); font-size:.44em; text-transform:uppercase;
  letter-spacing:.12em; color:rgba(255,255,255,.55);
}
.art-bleed-content {
  position:absolute; bottom:0; left:0; right:0; z-index:3;
  padding:0 18mm 14mm 20mm;
}
.art-bleed-pip { width:14mm; height:3px; background:var(--ac,var(--accent));
  margin-bottom:1em; display:block; }
.art-bleed-h1 {
  font-family:var(--disp); font-size:3.8em; font-weight:900;
  line-height:1.04; letter-spacing:-.03em; color:#fff;
  margin-bottom:.3em; hyphens:auto; overflow-wrap:break-word;
  text-shadow:0 2px 24px rgba(0,0,0,.30);
}
.art-bleed-deck {
  font-family:var(--corm); font-size:1.08em; font-style:italic;
  color:rgba(255,255,255,.78); line-height:1.52; margin-bottom:.45em;
  max-width:38em; text-shadow:0 1px 8px rgba(0,0,0,.25);
}
.art-bleed-byline {
  font-family:var(--mono); font-size:.48em;
  text-transform:uppercase; letter-spacing:.12em; color:rgba(255,255,255,.42);
  border-top:1px solid rgba(255,255,255,.22); padding-top:.6em;
  display:flex; justify-content:space-between; align-items:center;
  flex-wrap:wrap; gap:.3em;
}
.art-bleed-byline strong {
  color:rgba(255,255,255,.78); font-family:var(--sans); font-weight:600;
  text-transform:none; letter-spacing:.04em;
}

.p-body {
  padding:var(--pad); display:flex; flex-direction:column;
  border-top:3px solid var(--ac,var(--accent));
}
.body-run {
  display:flex; justify-content:space-between; align-items:center;
  border-bottom:1px solid var(--lt); padding-bottom:.3em; margin-bottom:.65em;
  flex-shrink:0;
}
.body-run-pub   { font-family:var(--mono); font-size:.5em; text-transform:uppercase;
  letter-spacing:.14em; color:var(--mid) }
.body-run-title { font-family:var(--mono); font-size:.5em; color:var(--mid);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:60% }
.body-run-pg    { font-family:var(--mono); font-size:.5em;
  color:var(--ac,var(--accent)); font-weight:700 }

.cols-1 { flex:1; overflow:hidden; font-size:1em; line-height:1.75;
  text-align:justify; hyphens:auto; orphans:4; widows:4 }
.cols-2 {
  flex:1; overflow:hidden;
  column-count:2; column-gap:var(--gap); column-rule:.5px solid var(--lt);
  column-fill:auto;
  font-size:1em; line-height:1.72;
  text-align:justify; hyphens:auto; orphans:4; widows:4;
}
.cols-3 {
  flex:1; overflow:hidden;
  column-count:3; column-gap:var(--gap3); column-rule:.5px solid var(--lt);
  column-fill:auto;
  font-size:.9em; line-height:1.68;
  text-align:justify; hyphens:auto; orphans:4; widows:4;
}
.cols-1>*:first-child,.cols-2>*:first-child,.cols-3>*:first-child { margin-top:0 }
.cols-1 p,.cols-2 p,.cols-3 p { margin:0 0 .85em }
.cols-1 p+p,.cols-2 p+p,.cols-3 p+p { text-indent:1.3em; margin-top:-.1em; margin-bottom:0 }
.cols-2 p,.cols-3 p { break-inside:avoid-column; page-break-inside:avoid }
.cols-2 blockquote,.cols-3 blockquote { break-inside:avoid-column }
.drop-cap::first-letter {
  float:left; font-family:var(--disp); font-size:4.8em; font-weight:900;
  line-height:.68; margin:.04em .08em 0 0; color:var(--ac,var(--ink));
}
.cols-1 h2,.cols-2 h2,.cols-3 h2 {
  font-family:var(--disp); font-size:1.35em; font-weight:700;
  margin:1.4em 0 .45em; padding-bottom:.2em;
  border-bottom:2.5px solid var(--ac,var(--ink)); break-after:avoid;
}
.cols-1 h3,.cols-2 h3,.cols-3 h3 {
  font-family:var(--disp); font-size:1.08em; font-weight:700; margin:1.4em 0 .35em;
}
.cols-1 a,.cols-2 a,.cols-3 a { color:var(--ink) }
.cols-1 ul,.cols-2 ul,.cols-3 ul,
.cols-1 ol,.cols-2 ol,.cols-3 ol { margin:.2em 0 .85em 1.6em }
.cols-1 li,.cols-2 li,.cols-3 li { margin-bottom:.32em }
.cols-1 strong,.cols-2 strong,.cols-3 strong { font-weight:600 }
.cols-1 hr,.cols-2 hr,.cols-3 hr { border:none; margin:1.4em 0 }
.cols-1 hr::after,.cols-2 hr::after,.cols-3 hr::after {
  content:"\2014\00a0\00a7\00a0\2014"; display:block; text-align:center;
  font-family:var(--mono); font-size:.76em; color:var(--lt); letter-spacing:.35em;
}
[data-text-role="lede"]    { column-span:all; font-size:1.08em; margin-bottom:.85em;
  border-bottom:1.5px solid var(--ac,var(--accent)); padding-bottom:.6em }
[data-text-role="dateline"]{ font-family:var(--mono); font-size:.68em;
  text-transform:uppercase; letter-spacing:.1em; color:var(--mid);
  text-indent:0!important; margin-bottom:.6em; }
[data-text-role="testimony"]{ font-style:italic;
  border-left:2px solid var(--ac,var(--accent)); padding-left:.7em }
[data-text-role="resolution"]{ font-style:italic; font-weight:500 }
[data-text-role="note"]    { font-family:var(--mono); font-size:.72em; color:var(--mid) }
[data-text-role="scene"]   { font-style:italic }
.iq {
  font-family:var(--sans); font-size:.74em; font-weight:700;
  text-transform:uppercase; letter-spacing:.1em;
  color:var(--ac,var(--accent)); margin:1.4em 0 .26em; text-indent:0!important;
}
.ia {
  font-family:var(--corm); font-size:1em; line-height:1.72;
  margin:0 0 .5em; text-indent:0!important;
}
.fit-tight   { font-size:.94em; line-height:1.66 }
.fit-tighter { font-size:.86em; line-height:1.58 }
.fit-min     { font-size:.78em; line-height:1.50 }
.cite-ref { font-family:var(--mono); font-size:.6em; vertical-align:super;
  color:var(--ac,var(--accent)); letter-spacing:0 }

.art-fig {
  display:block; margin:.8em 0 1em;
  break-inside:avoid; page-break-inside:avoid; text-align:center;
}
.art-fig-full { column-span:all }
.art-fig-sm   { max-width:52%; margin-left:auto; margin-right:auto }
.art-fig-md   { max-width:80%; margin-left:auto; margin-right:auto }
.art-fig img {
  width:auto; max-width:100%; height:auto; max-height:128mm;
  display:inline-block; object-fit:contain;
  filter:grayscale(4%) contrast(1.04); outline:1px solid rgba(0,0,0,.05);
}
.art-fig figcaption,
.cols-1 figcaption,.cols-2 figcaption,.cols-3 figcaption {
  font-family:var(--mono); font-size:.52em; text-transform:uppercase;
  letter-spacing:.08em; color:var(--mid); margin:.35em 0 .45em;
  display:flex; flex-wrap:wrap; justify-content:space-between; align-items:baseline; text-align:left;
}
.art-fig figcaption::before { content:'▸'; font-size:.75em; opacity:.35; margin-right:.4em; flex-shrink:0 }
.photo-credit { flex-basis:100%; order:2; margin-top:.25em; text-transform:none; letter-spacing:0; font-style:normal; opacity:.72 }


.p-photo-story {
}
.ps-intro {
  font-family:var(--serif); font-size:.86em; line-height:1.58;
  color:var(--ink); margin-bottom:5mm; padding-bottom:3mm;
  border-bottom:1px solid var(--lt); flex-shrink:0; overflow:hidden;
}
.ps-intro p { margin:0 0 .45em!important; text-indent:0!important; font-style:italic }

.pg-grid {
  flex:1; display:flex; flex-direction:column;
  gap:3mm; overflow:hidden;
}
.pg-row {
  display:grid; grid-template-columns:repeat(3,1fr);
  gap:3mm; flex-shrink:0;
  break-inside:avoid; page-break-inside:avoid;
}
.pg-cell { overflow:hidden; min-width:0; }
.pg-cell-empty { background:transparent; }
.pg-img-box {
  overflow:hidden; width:100%;
  background:var(--paper);
}
.pg-img-box img {
  width:100%; height:100%; display:block;
  object-fit:contain; object-position:center;
}
.pg-cap {
  font-family:var(--mono); font-size:.44em; text-transform:uppercase;
  letter-spacing:.06em; color:var(--mid); padding:.18em 0;
  line-height:1.3; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}

.pe-row  { display:flex; gap:3px; margin-bottom:3px;
  break-inside:avoid; page-break-inside:avoid; flex-shrink:0 }
.pe-cell { flex-shrink:0; overflow:hidden; display:flex; flex-direction:column }
.pe-img-box { overflow:hidden; width:100%; flex-shrink:0; background:var(--paper) }
.pe-img-box img { width:100%; height:100%; display:block;
  object-fit:contain; object-position:center }
.pe-cap {
  font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.06em; color:var(--mid); padding:.22em 0 0;
  line-height:1.38; flex-shrink:0;
}

.eg-group { column-span:all; margin:1.2em 0 1.6em; break-inside:avoid }
.eg-rows  { display:flex; flex-direction:column; gap:3px }
.eg-row   { display:flex; gap:3px; align-items:stretch }
.eg-cell  { overflow:hidden; display:flex; flex-direction:column; flex-shrink:0 }
.eg-img-box { overflow:hidden; width:100%; flex-shrink:0; background:var(--paper) }
.eg-img-box img { width:100%; height:100%; display:block;
  object-fit:contain; object-position:center }
.eg-cap { font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.06em; color:var(--mid); padding:.2em 0; line-height:1.3 }
.eg-group-captioned { display:grid; grid-template-columns:1fr auto; gap:6mm; align-items:start }
.eg-float-cap {
  width:26mm; padding:.6em; border-left:3px solid var(--ac,var(--accent));
  background:var(--warm); break-inside:avoid;
}
.eg-float-cap p { font-family:var(--corm); font-style:italic; font-size:.78em;
  line-height:1.5; color:var(--ink) }
.eg-float-cap-bar { display:block; width:12mm; height:2px;
  background:var(--ac,var(--accent)); margin-bottom:.5em }

.bsp-collage {
  position:relative; width:100%; column-span:all;
  overflow:hidden; margin:1.2em 0 1.6em; break-inside:avoid;
}
.bsp-cell {
  position:absolute; overflow:hidden;
  outline:2px solid var(--paper);
}
.bsp-cell img { width:100%; height:100%; object-fit:cover; display:block }
.bsp-empty {
  background:var(--paper);
  outline-color:var(--paper);
}
.bsp-cap {
  position:absolute; bottom:0; left:0; right:0; padding:.25em .4em;
  font-family:var(--mono); font-size:.44em; text-transform:uppercase;
  letter-spacing:.05em; color:#fff;
  background:linear-gradient(0deg,rgba(0,0,0,.68) 0%,transparent 100%);
}

.msnry-collage {
  position:relative; overflow:hidden;
  column-span:all;
  break-inside:avoid; page-break-inside:avoid;
  margin:8mm 0 10mm; width:174mm;
}
.msnry-cell {
  position:absolute; overflow:hidden;
  outline:1.5px solid rgba(255,255,255,.9);
  box-shadow:0 1px 4px rgba(0,0,0,.12);
}
.msnry-cell img { width:100%; height:100%; display:block; object-fit:cover; object-position:center }
.msnry-cap {
  position:absolute; bottom:0; left:0; right:0; padding:.22em .36em;
  font-family:var(--mono); font-size:.42em; text-transform:uppercase;
  letter-spacing:.06em; color:rgba(255,255,255,.9); line-height:1.3;
  background:linear-gradient(0deg,rgba(0,0,0,.72) 0%,transparent 100%);
}

.seq-panels { column-span:all; margin:2mm 0 4mm }
.seq-panel {
  display:flex; align-items:stretch; gap:0;
  margin-bottom:0; break-inside:avoid; page-break-inside:avoid;
  border:0.5px solid var(--lt);
}
.seq-panel.alt { flex-direction:row-reverse }
.seq-panel-img {
  flex:0 0 62%; position:relative; overflow:hidden;
  background:#0a0a0a;
}
.seq-panel-img img {
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:contain; display:block; background:#0a0a0a;
}
.seq-panel-text {
  flex:1; display:flex; flex-direction:column;
  justify-content:flex-end; padding:4.5mm 5mm 4.5mm 5.5mm;
  background:var(--paper); position:relative;
  border-left:2px solid var(--ac,var(--accent));
}
.seq-panel.alt .seq-panel-text {
  padding:4.5mm 5.5mm 4.5mm 5mm;
  border-left:none; border-right:2px solid var(--ac,var(--accent));
}
.seq-panel-num {
  position:absolute; top:3.5mm;
  font-family:var(--mono); font-size:.5em; letter-spacing:.14em;
  color:var(--ac,var(--accent)); text-transform:uppercase; opacity:.75;
}
.seq-panel:not(.alt) .seq-panel-num { right:4.5mm }
.seq-panel.alt           .seq-panel-num { left:4.5mm }
.seq-panel-caption {
  font-family:var(--body); font-size:.76em; line-height:1.62;
  color:var(--ink); margin-top:auto; padding-top:2.5mm;
  border-top:0.5px solid var(--lt);
}
.seq-panel-caption:empty { display:none }
.seq-panel-caption p { margin:0; text-indent:0!important }

.crowd-group { column-span:all; margin:1.2em 0 1.6em; break-inside:avoid }
.crowd-group .pe-img-box { background:#111 }
.crowd-group .pe-img-box img { object-position:center center }

.lede-span {
  column-span:all; font-size:1.1em; line-height:1.68;
  margin-bottom:.9em; padding-bottom:.65em;
  border-bottom:1.5px solid var(--ac,var(--accent));
}
.lede-span p { margin:0!important; text-indent:0!important;
  font-family:var(--serif); font-weight:400 }

.role-dateline {
  font-family:var(--mono)!important; font-size:.68em!important;
  text-transform:uppercase; letter-spacing:.1em; color:var(--mid);
  text-indent:0!important; margin-bottom:.6em!important;
}
.role-testimony {
  font-style:italic; border-left:2px solid var(--ac,var(--accent));
  padding-left:.75em; margin:.4em 0 .7em!important;
  text-indent:0!important; color:#1a1a1a;
}
.role-scene {
  font-style:italic; color:#2a2a2a;
  padding:.3em 0 .3em .8em;
  border-left:1.5px solid var(--lt);
  text-indent:0!important; margin:.5em 0 .7em!important;
}
.role-resolution {
  font-style:italic; font-weight:500;
  text-align:right; color:#2a2a2a;
  text-indent:0!important; margin:.6em 0!important;
  padding-top:.5em; border-top:1px solid var(--lt);
}
.role-note {
  font-family:var(--mono)!important; font-size:.68em!important;
  color:var(--mid); text-indent:0!important;
  padding:.2em .5em; border-left:2px solid var(--lt);
  margin:.4em 0!important;
}
.role-context {
  font-weight:500; font-size:1.02em;
  text-indent:0!important; margin-bottom:.65em!important;
}

.section-divider {
  column-span:all; display:flex; align-items:center; gap:3mm;
  margin:1.5em 0 1em; break-after:avoid;
}
.section-divider-rule {
  flex:1; height:1px; background:var(--lt);
}
.section-divider-label {
  font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.2em; color:var(--ac,var(--accent)); white-space:nowrap;
  padding:0 .4em;
}
.section-chapter-num {
  column-span:all; font-family:var(--disp); font-size:4.5em; font-weight:900;
  color:var(--ac,var(--accent)); opacity:.15; line-height:1;
  margin:.3em 0 -.1em; pointer-events:none; user-select:none;
}

.art-end-mark {
  column-span:all; text-align:center; font-size:.72em;
  color:var(--ac,var(--accent)); margin:1.2em 0 .3em;
  letter-spacing:.1em;
}
.art-end-mark--diamond { font-size:.62em; letter-spacing:.3em }
.art-end-mark--dash    { font-size:1.1em; letter-spacing:.5em; opacity:.6 }
.art-end-mark--square  { font-size:.55em; letter-spacing:.4em }
.art-end-mark--bullet  { font-size:.9em;  letter-spacing:.4em }

.img-para-stacked {
  break-inside:avoid; page-break-inside:avoid;
  margin:.8em 0 1.2em;
}
.img-para-stacked > .img-para-fig { margin:0 0 .55em; }
.img-para-stacked > .img-para-text,
.img-para-side > .img-para-text { font-size:.93em; line-height:1.70; }
.img-para-text p { text-indent:0!important; margin:0 0 .55em!important; break-inside:avoid-column }
.img-para-text p + p { text-indent:0!important; margin-top:.25em!important; }
.img-para-text.fit-tight  { font-size:.84em; line-height:1.62 }
.img-para-text.fit-tighter{ font-size:.76em; line-height:1.54 }
.img-para-text.fit-min    { font-size:.68em; line-height:1.46 }
.img-float-wrap {
  overflow:hidden; margin:.6em 0 1em; clear:both;
  break-inside:avoid; page-break-inside:avoid;
}
.img-float {
  float:left; width:40%; margin:0 3.5mm .5em 0;
  break-inside:avoid; page-break-inside:avoid;
}
.img-float-wrap.alt .img-float { float:right; margin:0 0 .5em 3.5mm; }
.img-float-clear { clear:both; display:block; height:0; }
.img-float figcaption { font-size:.82em; }

.editorial-photo-grid { column-span:all; margin:1em 0 1.4em; break-inside:avoid }
.editorial-photo-grid .pe-row { margin-bottom:3px }

.semantic-article-section { break-inside:avoid; page-break-inside:avoid }
.semantic-photo-narrative {
  column-span:all; display:grid; grid-template-columns:minmax(0,52%) minmax(0,48%);
  gap:5mm; margin:.9em 0 1.2em; padding:4mm;
  border:1px solid rgba(0,0,0,.12);
  background:linear-gradient(90deg,var(--ac,var(--accent)) 0 1.8mm,transparent 1.8mm),
             linear-gradient(180deg,rgba(0,0,0,.035),transparent 42%);
  break-inside:avoid; page-break-inside:avoid; align-items:start; position:relative;
}
.semantic-photo-narrative::after {
  content:""; position:absolute; right:3mm; bottom:3mm; width:20mm; height:20mm;
  border-right:1px solid var(--ac,var(--accent));
  border-bottom:1px solid var(--ac,var(--accent)); opacity:.5;
}
.immersive-split { break-inside:avoid; page-break-inside:avoid; }
.immersive-split.semantic-photo-card { column-span:all; }
.immersive-split.semantic-photo-narrative,
.immersive-split.semantic-photo-card,
.immersive-split.img-para-side {
  display:grid; grid-template-columns:minmax(0,1fr) minmax(38mm,.82fr);
  align-items:center; gap:7mm;
}
.immersive-split.alt {
  grid-template-columns:minmax(38mm,.82fr) minmax(0,1fr);
}
.immersive-split.alt .semantic-photo-media,
.immersive-split.alt > figure,
.immersive-split.alt > .img-para-fig,
.immersive-split.alt > .art-fig { grid-column:2 }
.immersive-split.alt .semantic-photo-prose,
.immersive-split.alt > .img-para-text,
.immersive-split.alt > .semantic-photo-caption,
.immersive-split.alt > .geo-callout { grid-column:1; grid-row:1 }
.immersive-split img { width:100%; height:auto; max-height:155mm; object-fit:contain }
.immersive-split .semantic-photo-prose,
.immersive-split > .img-para-text {
  position:relative; align-self:center; padding:5mm 0 5mm 5mm;
  border-left:1px solid var(--ac,var(--accent));
}
.immersive-split.alt .semantic-photo-prose,
.immersive-split.alt > .img-para-text {
  padding:5mm 5mm 5mm 0; border-left:none;
  border-right:1px solid var(--ac,var(--accent));
}
.semantic-photo-prose { font-size:.92em; line-height:1.72; color:#191919 }
.semantic-photo-prose p { text-indent:0!important; margin:0 0 .75em!important }
.semantic-photo-media img,.semantic-photo-unit img {
  width:100%; height:auto; max-height:135mm; object-fit:contain; display:block;
}
.semantic-photo-unit { column-span:all; margin:.8em 0 1em;
  break-inside:avoid; page-break-inside:avoid }
.semantic-photo-card {
  position:relative; display:grid;
  grid-template-columns:minmax(0,62%) minmax(36mm,1fr);
  gap:5mm; padding:3mm; border:1px solid rgba(0,0,0,.1); background:#fbfaf7;
}
.semantic-photo-card.photo-card-compact {
  grid-template-columns:minmax(0,44%) minmax(0,1fr)!important;
  padding:3mm!important; margin:1em 0 1.2em;
}
.semantic-photo-caption {
  font-family:var(--mono); font-size:.5em; line-height:1.45; text-transform:uppercase;
  letter-spacing:.07em; color:var(--mid); margin:.35em 0 0; text-indent:0!important;
}

.geo-callout { position:relative; margin:.55em 0 0; padding:3.3mm 4mm 3mm 5mm;
  min-height:18mm; break-inside:avoid }
.geo-callout::before {
  content:""; position:absolute; left:-5mm; top:50%; width:5mm;
  border-top:1px solid var(--ac,var(--accent));
}
.geo-callout::after {
  content:""; position:absolute; left:-5.7mm; top:calc(50% - 1.2mm);
  width:2.4mm; height:2.4mm; border-radius:50%; background:var(--ac,var(--accent));
}
.geo-callout-lines { position:absolute; inset:0; width:100%; height:100%;
  pointer-events:none }
.geo-callout-lines path { fill:none; stroke:var(--ac,var(--accent));
  stroke-width:1.2; opacity:.25; }
.geo-callout p { font-family:var(--corm); font-style:italic; font-size:.82em;
  line-height:1.55; position:relative; z-index:1; }

.pq { break-inside:avoid; page-break-inside:avoid; margin:1.4em 0 1.8em }
.pq-text { font-family:var(--disp); line-height:1.35 }
.pq-cite { font-family:var(--mono); font-size:.52em; text-transform:uppercase;
  letter-spacing:.1em; color:var(--mid); margin-top:.5em }
.pq-classic { padding-left:1em; border-left:3px solid var(--ac,var(--accent));
  position:relative }
.pq-classic .pq-mark {
  font-family:var(--disp); font-size:5em; font-weight:900; line-height:.5;
  color:var(--ac,var(--accent)); opacity:.10; position:absolute;
  top:.15em; left:-.12em; pointer-events:none; user-select:none;
}
.pq-dark { column-span:all; padding:1em 0 .8em;
  border-top:5px solid var(--ac,var(--accent)); position:relative; overflow:hidden }
.pq-dark::before {
  content:'"'; font-family:var(--disp); font-size:9em; line-height:.6;
  font-weight:900; color:rgba(0,0,0,.08); position:absolute; top:-.1em; left:-.05em;
  pointer-events:none; user-select:none;
}
.pq-dark .pq-text { font-size:1.22em; font-weight:700; position:relative; z-index:1 }
.pq-hang { display:flex; gap:.6em; align-items:flex-start }
.pq-hang-glyph {
  font-family:var(--disp); font-size:5.2em; line-height:.75; font-weight:900;
  color:var(--ac,var(--accent)); opacity:.22; flex-shrink:0; user-select:none;
}
.pq-monument { column-span:all; padding:1em 0;
  border-top:4px solid var(--ink); border-left:4px solid var(--ac,var(--accent)) }
.pq-monument-text { font-size:1.72em; font-weight:700; padding:.3em .5em }
.pq-apos { border-bottom:2px solid var(--ac,var(--accent));
  padding-bottom:.7em; position:relative }
.pq-apos::before {
  content:'"'; font-family:var(--disp); font-size:6.4em; line-height:.5;
  font-weight:400; color:rgba(0,0,0,.10); position:absolute; top:-.05em; left:-.12em;
  pointer-events:none; user-select:none;
}
.pq-apos-text { font-family:var(--corm)!important; font-style:italic;
  font-size:1.3em; position:relative; z-index:1 }
.pq-band { display:flex; gap:.75em; align-items:flex-start }
.pq-band-bar { width:3px; min-height:100%; background:var(--ac,var(--accent));
  flex-shrink:0; align-self:stretch }
.pq-band-text { font-family:var(--corm)!important; font-style:italic }
.pq-rules { position:relative; padding:.8em 0 }
.pq-rules-top {
  height:1px; background:var(--ink); margin-bottom:.7em; position:relative;
}
.pq-rules-top::after {
  content:''; position:absolute; left:0; top:-6px; width:12mm; height:12px;
  background:var(--ink);
}
.pq-rules-bot { height:1px; background:var(--lt); margin-top:.7em }
.pq-rules-text { font-family:var(--disp) }

.side-fig-callout {
  column-span:all; display:grid; grid-template-columns:minmax(0,58%) minmax(38mm,1fr);
  gap:7mm; margin:1.2em 0 1.6em; align-items:start; break-inside:avoid;
}
.side-fig-callout.alt { grid-template-columns:minmax(38mm,1fr) minmax(0,58%) }
.side-fig-img img { width:100%; height:auto; max-height:120mm; object-fit:contain; display:block }

.p-back {
  background:#0d0d0d; color:#f5f5f0; position:relative;
  overflow:hidden; display:flex; flex-direction:column;
}
.back-ghost {
  position:absolute; inset:0; overflow:hidden; z-index:0;
  display:flex; flex-wrap:wrap; align-content:center;
  gap:.08em .18em; padding:18mm 14mm;
  pointer-events:none; user-select:none;
}
.back-content {
  position:relative; z-index:2; padding:22mm 22mm 16mm;
  display:flex; flex-direction:column; flex:1;
}
.back-pub-name {
  font-family:var(--disp); font-size:3.5em; font-weight:900;
  color:#fff; letter-spacing:-.03em; line-height:1; margin-bottom:.2em;
}
.back-tagline {
  font-family:var(--corm); font-style:italic; font-size:1.1em;
  color:rgba(255,255,255,.45); margin-bottom:4mm;
}
.back-rule { height:2px; width:30mm; background:var(--accent); margin:6mm 0 8mm }
.back-support-head,.back-contact-head {
  font-family:var(--mono); font-size:.5em; text-transform:uppercase;
  letter-spacing:.18em; color:rgba(255,255,255,.3); margin-bottom:1.5mm;
}
.back-support-note {
  font-family:var(--serif); font-size:.8em; line-height:1.6;
  color:rgba(255,255,255,.55); max-width:25em; margin-bottom:5mm;
}
.back-qr-row { display:flex; gap:8mm; align-items:flex-start; margin-bottom:6mm }
.back-qr-item { display:flex; flex-direction:column; align-items:center; gap:1.5mm }
.back-qr-item img { width:22mm; height:22mm; image-rendering:pixelated }
.back-qr-label { font-family:var(--mono); font-size:.44em; text-transform:uppercase;
  letter-spacing:.1em; color:rgba(255,255,255,.35); text-align:center }
.back-row { display:flex; gap:12mm; margin-top:4mm }
.back-contact {
  font-family:var(--mono); font-size:.72em; letter-spacing:.03em;
  line-height:1.9; color:rgba(255,255,255,.5);
}
.back-note { font-family:var(--serif); font-size:.78em; line-height:1.6;
  color:rgba(255,255,255,.4); margin-top:.7em }
.back-identity {
  position:relative; z-index:2; padding:4mm 22mm;
  border-top:1px solid rgba(255,255,255,.1);
  display:flex; justify-content:space-between; align-items:center;
  font-family:var(--mono); font-size:.48em; text-transform:uppercase;
  letter-spacing:.1em; color:rgba(255,255,255,.28);
}
.back-identity img { height:13px; width:auto; opacity:.28; margin-right:.5em }

.cite-list { font-family:var(--mono); font-size:.58em; line-height:1.62;
  color:var(--mid); margin-top:1em; column-span:all; columns:2 70mm;
  column-gap:7mm; border-top:1px solid var(--lt); padding-top:.8em;
  break-inside:avoid; page-break-inside:avoid; }
.cite-list li { margin-bottom:.32em; break-inside:avoid; page-break-inside:avoid }
.cite-list a  { color:var(--ac,var(--accent)); text-decoration:none }
.cite-heading {
  column-span:all; font-family:var(--mono); font-size:.66em;
  text-transform:uppercase; letter-spacing:.18em; color:var(--ac,var(--accent));
  margin:0 0 5mm; padding-bottom:2mm; border-bottom:1px solid var(--lt);
}
.cite-list-page { margin-top:0; columns:2 76mm; font-size:.64em; line-height:1.72 }

.semantic-article-section[data-section-index="resolution"],
.semantic-article-section[data-section-index="conclusion"],
.semantic-article-section[data-section-index="series-note"] {
  break-before:column;
}


.p-photo-full { break-inside:avoid; page-break-inside:avoid; overflow:hidden }
.photo-full-wrap {
  flex:1; position:relative; overflow:hidden; min-height:0;
}
.msn-canvas {
  position:absolute; inset:0; width:100%; height:100%;
  overflow:hidden;
}
.msn-cell {
  position:absolute; overflow:hidden;
  outline:2px solid var(--paper);
  box-sizing:border-box;
}
.msn-cell img {
  position:absolute; inset:0;
  width:100%; height:100%; display:block;
  object-fit:cover; object-position:center;
}
.msn-cell-rot img {
  position:absolute;
  inset:50% auto auto 50%;
  width:calc(var(--rw,100)*1mm);
  height:calc(var(--rh,100)*1mm);
  max-width:none; max-height:none;
  transform:translate(-50%,-50%) rotate(90deg);
  transform-origin:center;
  object-fit:cover; object-position:center;
}
.msn-cap {
  position:absolute; bottom:0; left:0; right:0;
  padding:.22em .4em;
  font-family:var(--mono); font-size:.44em; text-transform:uppercase;
  letter-spacing:.05em; color:rgba(255,255,255,.92); line-height:1.35;
  background:linear-gradient(0deg,rgba(0,0,0,.75) 0%,transparent 100%);
  pointer-events:none;
}
"""

def _pg_cover(articles, title, date_str, logo_b64, cfg,
              creator='', description=''):
    pub      = cfg.get('publication', {})
    pub_name = pub.get('name', 'The Voice Express')

    pool = {}
    for w in re.sub(r'[^\w\s]', '', pub_name).upper().split():
        if len(w) >= 2:
            pool[w] = pool.get(w, 0) + 12
    for art in articles:
        for t in art.get('tags', []):
            nm = re.sub(r'[^\w\s]', '', (t.get('name') or '')).strip().upper()
            if len(nm) >= 3:
                pool[nm] = pool.get(nm, 0) + 6
        for field in ('section_name', 'category_name'):
            s = re.sub(r'[^\w\s]', '', (art.get(field) or '')).strip().upper()
            if len(s) >= 3:
                pool[s] = pool.get(s, 0) + 8
        for w in (art.get('title', '') or '').upper().split():
            w = re.sub(r'[^\w]', '', w)
            if len(w) >= 4:
                pool[w] = pool.get(w, 0) + 3
        for w in (art.get('excerpt', '') or '').upper().split():
            w = re.sub(r'[^\w]', '', w)
            if len(w) >= 5:
                pool[w] = pool.get(w, 0) + 2

    sorted_words = sorted(pool.items(), key=lambda x: -x[1])
    words_list   = [w for w, _ in sorted_words] or [pub_name.upper()]
    rng          = random.Random(42)
    rain         = ''

    anchor_zones = [(12, 14), (48, 8), (72, 22), (25, 52), (58, 62)]
    for rank, (word, _) in enumerate(sorted_words[:5]):
        x, y = anchor_zones[rank % len(anchor_zones)]
        x += rng.uniform(-3, 3); y += rng.uniform(-3, 3)
        sz = rng.uniform(4.5, 6.5); op = rng.uniform(0.80, 0.96); rot = rng.uniform(-3, 3)
        rain += (f'<span style="position:absolute;left:{x:.1f}%;top:{y:.1f}%;'
                 f'font-size:{sz:.1f}em;opacity:{op:.2f};'
                 f'transform:rotate({rot:.1f}deg);'
                 f'font-family:var(--disp);font-weight:900;'
                 f'text-transform:uppercase;letter-spacing:.04em;'
                 f'white-space:nowrap;line-height:1;color:#fff">{_h(word)}</span>\n')

    for rank, (word, _) in enumerate(sorted_words[5:25]):
        x = rng.uniform(2, 86); y = rng.uniform(6, 88)
        sz = rng.uniform(1.6, 3.0); op = rng.uniform(0.30, 0.62); rot = rng.uniform(-10, 10)
        rain += (f'<span style="position:absolute;left:{x:.1f}%;top:{y:.1f}%;'
                 f'font-size:{sz:.1f}em;opacity:{op:.2f};'
                 f'transform:rotate({rot:.1f}deg);'
                 f'font-family:var(--disp);font-weight:700;'
                 f'text-transform:uppercase;letter-spacing:.05em;'
                 f'white-space:nowrap;line-height:1;color:#fff">{_h(word)}</span>\n')

    for k in range(130):
        word = words_list[k % len(words_list)]
        x = rng.uniform(0, 90); y = rng.uniform(2, 96)
        sz = rng.uniform(0.45, 1.15); op = rng.uniform(0.05, 0.24); rot = rng.uniform(-15, 15)
        wt = rng.choice(['300', '400', '600'])
        rain += (f'<span style="position:absolute;left:{x:.1f}%;top:{y:.1f}%;'
                 f'font-size:{sz:.1f}em;opacity:{op:.2f};'
                 f'transform:rotate({rot:.1f}deg);'
                 f'font-family:var(--disp);font-weight:{wt};'
                 f'text-transform:uppercase;letter-spacing:.06em;'
                 f'white-space:nowrap;line-height:1;color:#fff">{_h(word)}</span>\n')

    logo_html    = (f'<img class="cov-logo" src="{logo_b64}" alt=""/>' if logo_b64 else '')
    n            = len(articles)
    creator_line = (
        f'<span style="font-family:var(--mono);font-size:.46em;'
        f'text-transform:uppercase;letter-spacing:.14em;'
        f'color:rgba(255,255,255,.32)">Curated by {_h(creator)}</span>'
        if creator else '')
    issue_no  = cfg.get('magazine', {}).get('issue_number', 1)
    vol       = pub.get('volume', 0)
    issue_tag = (f'<span style="font-family:var(--mono);font-size:.52em;'
                 f'text-transform:uppercase;letter-spacing:.18em;'
                 f'color:rgba(255,255,255,.55);display:block;margin-bottom:.5em">'
                 f'Issue&nbsp;{issue_no}&nbsp;&nbsp;·&nbsp;&nbsp;Vol.&nbsp;{_h(vol)}'
                 f'</span>')

    return f'''<div class="page p-cov">
  <div style="position:absolute;inset:0;overflow:hidden;z-index:2">{rain}</div>
  <div class="cov-top" style="z-index:10">
    {logo_html}
    <span class="cov-pub">{_h(pub_name)}</span>
    <div class="cov-pip"></div>
    {creator_line}
  </div>
  <div class="cov-foot" style="z-index:10">
    <div class="cov-foot-title">{_h(title)}</div>
    <div class="cov-foot-meta">
      {issue_tag}
      {n} article{"s" if n != 1 else ""}&nbsp;&nbsp;·&nbsp;&nbsp;{date_str}<br/>
      {_h(pub.get("location","New Delhi"))}
    </div>
  </div>
</div>'''


def _pg_masthead(logo_b64, cfg):
    pub      = cfg.get('publication', {})
    team     = cfg.get('team', {})
    con      = cfg.get('contact', {})
    pub_name = pub.get('name', 'The Voice Express')
    tagline  = pub.get('tagline', 'The Truth Takes Time.')
    founding = pub.get('founding_statement',
                       'An independent publication based in New Delhi, India.')
    est      = pub.get('est', '2022')
    vol      = pub.get('volume', 'I')
    website  = pub.get('website', '')
    loc      = pub.get('location', 'New Delhi')
    yr       = time.strftime('%Y')

    logo_html = ''
    if logo_b64:
        logo_html = (f'<img style="margin-bottom:4mm" src="{logo_b64}" alt=""/>')

    team_html = ''
    for k, v in team.items():
        if k == 'note' or not v:
            continue
        label = k.replace('_', ' ').title()
        team_html += (f'<div class="mast-lbl">{_h(label)}</div>'
                      f'<div class="mast-val">{_h(v)}</div>')

    ig_html = (f'<div class="mast-val">{_h(con.get("instagram_handle",""))}</div>'
               if con.get('instagram_handle') else '')

    return f'''<div class="page p-dark" style="position:relative;overflow:hidden">
  <div style="position:absolute;left:0;top:0;bottom:0;width:4mm;
    background:var(--accent);z-index:2"></div>
  <div class="mast-panel">
    <div class="mast-l">
      {logo_html}
      <div class="mast-pub">{_h(pub_name)}</div>
      <div class="mast-tag">{_h(tagline)}</div>
      <div class="mast-rule"></div>
      {team_html}
      <div class="mast-rule"></div>
      <div class="mast-lbl">Contact</div>
      <div class="mast-val">{_h(con.get("email",""))}</div>
      {ig_html}
    </div>
    <div class="mast-r">
      <div class="mast-lbl">About</div>
      <div class="mast-note">{_h(founding)}</div>
      <div class="mast-rule"></div>
      <div class="mast-lbl">Website</div>
      <div class="mast-val">{_h(website)}</div>
      <div class="mast-rule"></div>
      <div class="mast-lbl">Location</div>
      <div class="mast-val">{_h(loc)}</div>
      <div class="mast-rule"></div>
      <div style="font-family:var(--mono);font-size:.5em;
        text-transform:uppercase;letter-spacing:.16em;
        color:rgba(255,255,255,.28);line-height:1.9">
        Independent &bull; Volunteer-run<br/>
        Vol.&nbsp;{_h(vol)} &bull; Est.&nbsp;{_h(est)}<br/>
        &copy;&nbsp;{yr}
      </div>
    </div>
  </div>
  <div class="mast-est">{_h(est)}</div>
</div>'''



def _pg_toc(articles, thumb_cache, cfg=None):
    if cfg is None:
        cfg = _cfg()
    pub_name = cfg.get('publication', {}).get('name', 'The Voice Express')
    yr       = time.strftime('%Y')
    n        = len(articles)
    feat_cut = min(3, n)

    featured_html = ''
    for i, art in enumerate(articles[:feat_cut], 1):
        accent = _art_accent(art, i)
        thumb  = thumb_cache.get(i)
        th     = (f'<div class="toc-feat-thumb"><img src="{thumb}" alt=""/></div>'
                  if thumb else
                  '<div class="toc-feat-thumb"><div class="toc-feat-thumb-ph">¶</div></div>')
        sect   = art.get('section_name', '') or art.get('category_name', '')
        cat    = art.get('category_name', '')
        beat   = ' · '.join(filter(None, [_h(sect),
                                          _h(cat) if cat != sect else '']))
        au     = art.get('byline_auto') or art.get('author_name') or art.get('byline', '')
        exc    = (art.get('excerpt') or _words(art.get('content', ''), 18))[:120]
        featured_html += f'''<div class="toc-feat-item" style="--ac:{_h(accent)}">
  {th}
  <div>
    <span class="toc-feat-n">{i:02d}</span>
    {"<div class='toc-feat-beat'>"+beat+"</div>" if beat else ""}
    <div class="toc-feat-ttl">{_h(art.get("title",""))}</div>
    {"<div class='toc-feat-au'>By "+_h(au)+"</div>" if au else ""}
    {"<div class='toc-feat-ex'>"+_h(exc)+"</div>" if exc else ""}
  </div>
</div>'''

    compact_html = ''
    if n > feat_cut:
        for i, art in enumerate(articles[feat_cut:], feat_cut + 1):
            accent = _art_accent(art, i)
            sect   = art.get('section_name', '') or art.get('category_name', '')
            compact_html += f'''<div class="toc-compact-item" style="--ac:{_h(accent)}">
  <div class="toc-compact-n">{i:02d}</div>
  <div>
    <div class="toc-compact-ttl">{_h(art.get("title",""))}</div>
    {"<div class='toc-compact-beat'>"+_h(sect)+"</div>" if sect else ""}
  </div>
</div>'''

    compact_section = (
        f'<div class="toc-compact">'
        f'<div class="toc-compact-head">More in this edition</div>'
        f'{compact_html}</div>'
        if compact_html else '')

    return f'''<div class="page p-toc">
  <div class="toc-banner">
    <div class="toc-banner-head">Contents</div>
    <div class="toc-banner-meta">{_h(pub_name)}<br/>{yr} &bull; {n} article{"s" if n!=1 else ""}</div>
  </div>
  <div class="toc-subbar"></div>
  <div class="toc-body">
    <div class="toc-featured">{featured_html}</div>
    {compact_section}
  </div>
</div>'''


def _pg_art_title(art, idx, accent):
    title   = art.get('title', '') or ''
    deck    = ''
    content = art.get('content', '') or ''
    dm      = re.search(r'<h4[^>]*class=["\'][^"\']*article-deck[^"\']*["\'][^>]*>(.*?)</h4>',
                        content, re.DOTALL | re.IGNORECASE)
    if dm:
        deck = re.sub(r'<[^>]+>', '', dm.group(1)).strip()
    if not deck:
        for sel in (r'<h4\b[^>]*>(.*?)</h4>', r'<p\b[^>]*class=["\'][^"\']*deck[^"\']*["\'][^>]*>(.*?)</p>'):
            m = re.search(sel, content, re.DOTALL | re.IGNORECASE)
            if m:
                deck = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                break

    author = art.get('byline_auto') or art.get('author_name') or art.get('byline', '')
    date   = art.get('published_date') or art.get('date', '')
    if date:
        try:
            date = datetime.fromisoformat(str(date)).strftime('%-d %b %Y')
        except Exception:
            date = str(date)[:10]

    sect    = art.get('section_name', '') or ''
    cat     = art.get('category_name', '') or ''
    ac      = _h(accent)
    num_str = f'{idx:02d}'

    sect_html = (f'<span class="art-title-sect">{_h(sect)}</span>' if sect else '')
    cat_html  = (f'<span class="art-title-cat">{_h(cat)}</span>'
                 if cat and cat != sect else '')
    badge     = (f'<div class="art-title-badge">{sect_html}{cat_html}</div>'
                 if sect_html or cat_html else '')
    deck_html = (f'<div class="art-title-deck">{_h(deck)}</div>' if deck else '')
    by_parts  = [f'By <strong>{_h(author)}</strong>' if author else '',
                 _h(date) if date else '']
    by_str    = ' &mdash; '.join(p for p in by_parts if p)
    by_html   = (f'<div class="art-title-byline">{by_str}</div>' if by_str else '')

    return f'''<div class="page p-art-title" style="--ac:{ac}">
  <div class="art-title-num">{num_str}</div>
  <div class="art-title-pip"></div>
  {badge}
  <div class="art-title-h1">{_h(title)}</div>
  {deck_html}
  {by_html}
</div>'''


def _pg_art_bleed(art, idx, accent, img_b64):
    if not img_b64:
        return ''
    title  = art.get('title', '') or ''
    deck   = ''
    content = art.get('content', '') or ''
    dm = re.search(r'<h4[^>]*class=["\'][^"\']*article-deck[^"\']*["\'][^>]*>(.*?)</h4>',
                   content, re.DOTALL | re.IGNORECASE)
    if dm:
        deck = re.sub(r'<[^>]+>', '', dm.group(1)).strip()
    if not deck:
        m = re.search(r'<h4\b[^>]*>(.*?)</h4>', content, re.DOTALL | re.IGNORECASE)
        if m:
            deck = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    if deck and len(deck.split()) > 75:
        deck = ' '.join(deck.split()[:75]) + '…'

    author  = art.get('byline_auto') or art.get('author_name') or art.get('byline', '')
    date    = art.get('published_date') or art.get('date', '')
    if date:
        try:
            date = datetime.fromisoformat(str(date)).strftime('%-d %b %Y')
        except Exception:
            date = str(date)[:10]

    sect    = art.get('section_name', '') or ''
    cat     = art.get('category_name', '') or ''
    ac      = _h(accent)
    num_str = f'{idx:02d}'

    sect_html = (f'<span class="art-bleed-sect-tag">{_h(sect)}</span>' if sect else '')
    cat_html  = (f'<span class="art-bleed-cat-tag">{_h(cat)}</span>'
                 if cat and cat != sect else '')
    deck_html = (f'<div class="art-bleed-deck">{_h(deck)}</div>' if deck else '')
    by_left   = (f'By <strong>{_h(author)}</strong>' if author else '') + \
                (f' &bull; {_h(date)}' if date else '')
    by_right  = f'No.&nbsp;{num_str}'

    return f'''<div class="page p-art-bleed" style="--ac:{ac}">
  <img class="art-bleed-bg" src="{img_b64}" alt=""/>
  <div class="art-bleed-top-scrim"></div>
  <div class="art-bleed-scrim"></div>
  <div class="art-bleed-num">{num_str}</div>
  <div class="art-bleed-badge">{sect_html}{cat_html}</div>
  <div class="art-bleed-content">
    <span class="art-bleed-pip"></span>
    <div class="art-bleed-h1">{_h(title)}</div>
    {deck_html}
    <div class="art-bleed-byline">
      <span>{by_left}</span>
      <span>{by_right}</span>
    </div>
  </div>
</div>'''


def _pg_body(art, art_idx, page_num, is_first, html_chunk, pq_style, cfg,
             accent, art_type, citations, is_last):
    pub_name  = cfg.get('publication', {}).get('name', 'The Voice Express')
    title     = (art.get('title', '') or '')[:55]
    page_wc   = _words(html_chunk)
    col_cls   = _col_class(page_wc, art_type, html_chunk)
    ac        = _h(accent)
    pg_label  = f'{art_idx}.{page_num}'
    cont      = ' — cont.' if page_num > 1 else ''

    if art_type == 'interview':
        html_chunk = _style_interview(html_chunk)

    cite_html = ''
    if is_last and citations:
        items = ''.join(
            f'<li><sup>[{n}]</sup> <a href="{_h(url)}" target="_blank">'
            f'{_h(text)}</a></li>'
            for n, text, url in citations)
        cite_html = f'<ol class="cite-list">{items}</ol>'

    end_html = _END_MARKS.get(art_type, '') if is_last else ''

    return f'''<div class="page p-body" style="--ac:{ac}">
  <div class="body-run">
    <span class="body-run-pub">{_h(pub_name)}</span>
    <span class="body-run-title">{_h(title)}{cont}</span>
    <span class="body-run-pg">{pg_label}</span>
  </div>
  <div class="{col_cls}">{html_chunk}{cite_html}{end_html}</div>
</div>'''


def _citations_fit_body(html_chunk, citations):
    if not citations:
        return True
    cite_words = sum(max(8, len(str(text or '').split()) + 4)
                     for _n, text, _url in citations)
    return _words(html_chunk) + cite_words <= 380 and len(citations) <= 10


def _pg_citations_page(art, art_idx, page_num, citations, accent, cfg, art_type):
    pub_name = cfg.get('publication', {}).get('name', 'The Voice Express')
    title = (art.get('title', '') or '')[:55]
    ac = _h(accent)
    items = ''.join(
        f'<li><sup>[{n}]</sup> <a href="{_h(url)}" target="_blank">{_h(text)}</a></li>'
        for n, text, url in (citations or []))
    end_html = _END_MARKS.get(art_type, '')
    return f'''<div class="page p-body p-citations" style="--ac:{ac}">
  <div class="body-run">
    <span class="body-run-pub">{_h(pub_name)}</span>
    <span class="body-run-title">{_h(title)} &mdash; references</span>
    <span class="body-run-pg">{art_idx}.{page_num}</span>
  </div>
  <div class="cols-1">
    <h2 class="cite-heading">References</h2>
    <ol class="cite-list cite-list-page">{items}</ol>
    {end_html}
  </div>
</div>'''


def _pg_back(cfg, logo_b64):
    pub      = cfg.get('publication', {})
    support  = cfg.get('support', {})
    con      = cfg.get('contact', {})
    pub_name = pub.get('name', 'The Voice Express')
    tagline  = pub.get('tagline', 'The Truth Takes Time.')
    yr       = time.strftime('%Y')
    est      = pub.get('est', '2022')
    sn       = con.get('submissions_note', '') or support.get('submissions_note', '')

    rng   = random.Random(99)
    words = [pub_name.upper(), 'THE', 'VOICE', 'EXPRESS', 'INDEPENDENT',
             'NEW', 'DELHI', 'TRUTH', 'TAKES', 'TIME']
    ghost = ''
    for k in range(88):
        word = words[k % len(words)]
        x    = rng.uniform(0, 88); y = rng.uniform(2, 94)
        sz   = rng.choice([3.4, 1.9, 1.1, 0.72])
        op   = rng.uniform(0.025, 0.06)
        rot  = rng.uniform(-8, 8)
        wt   = rng.choice(['400', '700', '900'])
        ghost += (f'<span style="position:absolute;left:{x:.1f}%;top:{y:.1f}%;'
                  f'font-size:{sz}em;opacity:{op:.3f};font-weight:{wt};'
                  f'transform:rotate({rot:.1f}deg);font-family:var(--disp);'
                  f'text-transform:uppercase;letter-spacing:.04em;'
                  f'white-space:nowrap;line-height:1;color:#fff">{_h(word)}</span>')

    qr_html = ''
    if support:
        def _support_val(section_key, value_key):
            sec = support.get(section_key, '')
            if isinstance(sec, dict):
                return str(sec.get(value_key, '') or '')
            return str(sec or '')

        qrs = []
        for section_key, value_key, label in (
                ('kofi',     'url', 'Support on Ko-fi'),
                ('razorpay', 'url', 'Support via Razorpay'),
                ('paypal',   'url', 'PayPal')):
            val = _support_val(section_key, value_key)
            if not val:
                continue
            q = _qr_b64(val)
            if q:
                qrs.append(f'<div class="back-qr-item">'
                            f'<img src="{q}" alt="{_h(label)}"/>'
                            f'<span class="back-qr-label">{_h(label)}</span>'
                            f'<span class="back-qr-label" style="opacity:.6">'
                            f'{_h(val[:38])}</span></div>')
        if qrs:
            qr_html = (f'<div class="back-support-note">'
                       f'No ads. No political funding. Reader-supported.</div>'
                       f'<div class="back-qr-row">{"".join(qrs)}</div>')

    contact_html = ''
    if con:
        lines = []
        for key, icon in (('email', ''), ('website', ''), ('emag', ''), ('newsstand', '')):
            v = con.get(key, '')
            if v:
                lines.append(_h(v))
        if lines:
            contact_html = (f'<div class="back-contact-head">Get in Touch</div>'
                            f'<div class="back-contact">'
                            f'{"<br/>".join(lines)}</div>')

    logo_html = ''
    if logo_b64:
        logo_html = f'<img src="{logo_b64}" alt=""/>'

    return f'''<div class="page p-back">
  <div class="back-ghost" style="position:absolute;inset:0;overflow:hidden;z-index:0">{ghost}</div>
  <div class="back-content">
    <div class="back-pub-name">{_h(pub_name)}</div>
    <div class="back-tagline">{_h(tagline)}</div>
    <div class="back-rule"></div>
    <div class="back-row">
      <div>
        {"<div class='back-support-head'>Support Independent Journalism</div>" if qr_html else ""}
        {qr_html}
      </div>
      <div>{contact_html}
        {"<p class='back-note'>"+_h(sn)+"</p>" if sn else ""}
      </div>
    </div>
  </div>
  <div class="back-identity">
    <span>{logo_html}{_h(pub_name)} &mdash; {_h(tagline)}</span>
    <span>&copy;&nbsp;{yr} &bull; {_h(pub.get("location","New Delhi"))}</span>
  </div>
</div>'''


def _pg_photo_group_full_page(art, art_idx, page_num, figs, accent, cfg):
    pub_name = cfg.get('publication', {}).get('name', 'The Voice Express')
    title    = (art.get('title', '') or '')[:55]
    ac       = _h(accent)
    pg_label = f'{art_idx}.img.{page_num}'

    collage = _render_organic_frame_grid(figs, accent)
    if not collage:
        return None

    return f'''<div class="page p-body p-photo-full" style="--ac:{ac}">
  <div class="body-run">
    <span class="body-run-pub">{_h(pub_name)}</span>
    <span class="body-run-title">{_h(title)}</span>
    <span class="body-run-pg">{pg_label}</span>
  </div>
  <div class="photo-full-wrap">{collage}</div>
</div>'''


_JS = r"""
(function(){
  function smartCrop(img){
    if(img.closest('.art-fig')||img.closest('.side-fig')||
       img.closest('.pe-img-box')||img.closest('.img-para-fig')||
       img.closest('.eg-img-box')||img.closest('.bsp-cell')||
       img.closest('.cov-hero-bg')||img.closest('.ps-cell')||
       img.closest('.seq-panel-img')||img.closest('.crowd-group')) return;
    var w=img.naturalWidth, h=img.naturalHeight;
    if(!w||!h) return;
    var r=w/h, pos;
    if(img.closest('.toc-feat-thumb')||img.closest('.toc-thumb')){
      pos=r<0.8?'center 14%':'center 20%';
    }else{ return; }
    img.style.objectPosition=pos;
  }
  function fitCols(box){
    if(!box) return;
    box.classList.remove('fit-tight','fit-tighter','fit-min');
    var lim=box.clientHeight+4;
    if(box.scrollHeight<=lim) return;
    box.classList.add('fit-tight');
    if(box.scrollHeight<=lim) return;
    box.classList.add('fit-tighter');
    if(box.scrollHeight<=lim) return;
    box.classList.add('fit-min');
  }
  function scalePagesToFit(){
    if(window.matchMedia('print').matches) return;
    var pages=document.querySelectorAll('.page');
    if(!pages.length) return;
    var vw=Math.max(document.documentElement.clientWidth||0,window.innerWidth||0)-48;
    var pw=pages[0].offsetWidth||793;
    if(pw<=0||vw<=0) return;
    var scale=Math.min(1, vw/pw);
    pages.forEach(function(p){
      p.style.transform=scale<1?'scale('+scale.toFixed(4)+')':'';
      if(scale<1){
        var h=p.offsetHeight||1123;
        p.style.marginBottom=(h*(scale-1))+'px';
        p.style.marginTop='0';
      } else {
        p.style.marginBottom='';
        p.style.marginTop='';
      }
    });
  }
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('img').forEach(function(img){
      if(img.complete&&img.naturalWidth) smartCrop(img);
      else img.addEventListener('load',function(){ smartCrop(img); });
    });
    function runFit(){
      document.querySelectorAll('.p-body>.cols-1,.p-body>.cols-2,.p-body>.cols-3')
        .forEach(fitCols);
    }
    setTimeout(runFit, 60);
    setTimeout(runFit, 900);
    scalePagesToFit();
  });
  window.addEventListener('resize', scalePagesToFit);
})();
"""


def build_magazine_pages(articles, title, creator='', description='',
                         static_root=None, logo_path=None, cover_image_url=None):
    if static_root is None:
        static_root = os.path.join(_DIR, 'static')
    if logo_path is None:
        for fn in ('tve_logo.png', 'logo.png'):
            p = os.path.join(static_root, fn)
            if os.path.exists(p):
                logo_path = p
                break

    cfg      = _cfg()
    date_str = datetime.now(timezone.utc).strftime('%B %Y')
    pub      = cfg.get('publication', {})

    logo_b64 = None
    if logo_path and os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            d = f.read()
        logo_b64 = 'data:image/png;base64,' + base64.b64encode(d).decode()

    img_cache   = {}
    thumb_cache = {}
    feat_cache  = {}

    for i, art in enumerate(articles, 1):
        fi = art.get('featured_image')
        if fi:
            if fi not in img_cache:
                img_cache[fi] = _b64(fi, static_root)
            b = img_cache.get(fi)
            if b:
                thumb_cache[i] = feat_cache[i] = b

    pages = []

    pages.append(_pg_cover(articles, title, date_str, logo_b64, cfg,
                            creator=creator, description=description))

    pages.append(_pg_masthead(logo_b64, cfg))

    pages.append(_pg_toc(articles, thumb_cache, cfg))

    for i, art in enumerate(articles, 1):
        accent   = _art_accent(art, i)
        art_type = _detect_type(art)

        raw_content = art.get('content', '') or ''
        body_wc_est = _words(raw_content)
        has_img     = bool(feat_cache.get(i))

        if body_wc_est < 220 and has_img:
            bleed = _pg_art_bleed(art, i, accent, feat_cache[i])
            if bleed:
                pages.append(bleed)
        elif body_wc_est < 220:
            pages.append(_pg_art_title(art, i, accent))
        else:
            pages.append(_pg_art_title(art, i, accent))
            if has_img:
                bleed = _pg_art_bleed(art, i, accent, feat_cache[i])
                if bleed:
                    pages.append(bleed)

        body_clean = _clean(raw_content, static_root, img_cache)
        citations  = _extract_citations(body_clean)
        base_pq    = _CAT_PQ.get(art_type, 1)

        if art_type == 'photo_essay':
            all_blocks   = _parse_blocks(body_clean)
            visual_types = ('figure', 'gallery', 'photo_group', 'photo_unit')
            text_blocks  = [b for b in all_blocks if b['type'] not in visual_types]
            visual_blocks = [b for b in all_blocks if b['type'] in visual_types]
            text_wc      = sum(_words(b.get('html', '') or b.get('prose_html', ''))
                               for b in text_blocks)
            intro_html   = ''

            if text_blocks and visual_blocks and text_wc <= 170:
                intro_html = _render_blocks(text_blocks, 'photo_essay', base_pq,
                                            accent, is_first=True, citations=citations)
                n_txt = 0
            else:
                txt_budget = _PAGE_BUDGET.get('cols-1', 300)
                txt_pages  = _paginate_blocks(text_blocks, txt_budget)
                n_txt      = len(txt_pages)
                for page_num, blk_list in enumerate(txt_pages, 1):
                    pq    = base_pq if page_num % 2 == 1 else ((base_pq % 7) + 1)
                    chunk = _render_blocks(blk_list, 'photo_essay', pq, accent,
                                           is_first=(page_num == 1), citations=citations)
                    pages.append(_pg_body(
                        art, i, page_num, is_first=(page_num == 1),
                        html_chunk=chunk, pq_style=pq, cfg=cfg,
                        accent=accent, art_type=art_type,
                        citations=None, is_last=(page_num == n_txt)))

            special_chunks   = []
            pe_collage_groups = []
            photo_figs        = []

            for vi, blk in enumerate(visual_blocks):
                bt = blk['type']
                if bt == 'photo_group':
                    gtype = blk.get('group_type', 'dump')
                    vfigs = [f for f in blk.get('figures', []) if f.get('img')]
                    if gtype == 'sequence' and vfigs:
                        panels = _render_sequence_panels(vfigs, accent,
                                                         panel_start_idx=vi * 3)
                        special_chunks.append(panels)
                    elif vfigs:
                        pe_collage_groups.append(vfigs)
                elif bt == 'figure' and blk.get('img'):
                    photo_figs.append((blk['img'], blk.get('caption', '') or ''))
                elif bt == 'photo_unit' and blk.get('img'):
                    photo_figs.append((blk['img'], blk.get('caption', '') or ''))
                elif bt == 'gallery':
                    for fig in blk.get('figures', []):
                        if fig.get('img'):
                            photo_figs.append(
                                (fig['img'], fig.get('caption', '') or ''))

            for chunk_html in special_chunks:
                pages.append(_pg_body(
                    art, i, n_txt + 1, is_first=False,
                    html_chunk=chunk_html, pq_style=base_pq, cfg=cfg,
                    accent=accent, art_type=art_type,
                    citations=None, is_last=False))

            pg_collage_offset = n_txt + 1 + len(special_chunks)
            collage_pg_count  = 0
            for vfigs in pe_collage_groups:
                for ph_chunk in _photo_group_chunks(vfigs, max_per_page=12):
                    full_pg = _pg_photo_group_full_page(
                        art, i, pg_collage_offset + collage_pg_count,
                        ph_chunk, accent, cfg)
                    if full_pg:
                        pages.append(full_pg)
                        collage_pg_count += 1

            if photo_figs:
                pe_pages = _pg_photo_story_pages(
                    photo_figs, accent, art,
                    page_offset=pg_collage_offset + collage_pg_count,
                    cfg=cfg, intro_html=intro_html)
                pages.extend(pe_pages)
            if citations:
                pages.append(_pg_citations_page(
                    art, i,
                    pg_collage_offset + collage_pg_count + (1 if photo_figs else 0),
                    citations, accent, cfg, art_type))

        else:
            col_cls    = _col_class(_words(body_clean), art_type, body_clean)
            all_blocks = _parse_blocks(body_clean)
            budget     = _PAGE_BUDGET.get(col_cls, 220)
            blk_pages  = _paginate_blocks(all_blocks, budget)

            exploded: list = []
            for blk_list in blk_pages:
                pending: list = []
                for blk in blk_list:
                    gtype = blk.get('group_type', 'dump')
                    ph_figs = (
                        [f for f in blk.get('figures', []) if f.get('img')]
                        if blk.get('type') == 'photo_group'
                           and gtype != 'sequence'
                        else [])
                    if ph_figs:
                        if pending:
                            exploded.append({'kind': 'text', 'blocks': pending})
                            pending = []
                        for ph_chunk in _photo_group_chunks(ph_figs, max_per_page=12):
                            exploded.append({'kind': 'photo', 'figs': ph_chunk})
                    else:
                        pending.append(blk)
                if pending:
                    exploded.append({'kind': 'text', 'blocks': pending})

            last_txt_idx = next(
                (j for j in range(len(exploded) - 1, -1, -1)
                 if exploded[j]['kind'] == 'text'), -1)

            first_text_seen = False
            for pg_idx, entry in enumerate(exploded, 1):
                pq = base_pq if pg_idx % 2 == 1 else ((base_pq % 7) + 1)

                if entry['kind'] == 'photo':
                    full_pg = _pg_photo_group_full_page(
                        art, i, pg_idx, entry['figs'], accent, cfg)
                    if full_pg:
                        pages.append(full_pg)
                else:
                    is_first_text = not first_text_seen
                    first_text_seen = True
                    is_last_text = (pg_idx - 1 == last_txt_idx)
                    chunk = _render_blocks(
                        entry['blocks'], art_type, pq, accent,
                        is_first=is_first_text, citations=citations)
                    cite_on_body = citations if (
                        is_last_text and _citations_fit_body(chunk, citations)) else None
                    pages.append(_pg_body(
                        art, i, pg_idx, is_first=is_first_text,
                        html_chunk=chunk, pq_style=pq, cfg=cfg,
                        accent=accent, art_type=art_type,
                        citations=cite_on_body,
                        is_last=is_last_text and cite_on_body is not None))
                    if is_last_text and citations and cite_on_body is None:
                        pages.append(_pg_citations_page(
                            art, i, pg_idx + 1, citations, accent, cfg, art_type))

    pages.append(_pg_back(cfg, logo_b64))

    return pages


def build_magazine_html(articles, title, creator='', description='',
                        static_root=None, logo_path=None, cover_image_url=None):
    pages = build_magazine_pages(articles, title, creator=creator, description=description,
                                  static_root=static_root, logo_path=logo_path,
                                  cover_image_url=cover_image_url)
    cfg = _cfg()
    pub = cfg.get('publication', {})
    pub_name = pub.get('name', 'The Voice Express')
    fonts = ('https://fonts.googleapis.com/css2?family=Playfair+Display:'
             'ital,wght@0,400;0,700;0,900;1,400;1,700&family=EB+Garamond:'
             'ital,wght@0,400;0,500;0,600;1,400&family=Montserrat:'
             'wght@300;400;600;700;800;900&family=Cormorant+Garamond:'
             'ital,wght@0,300;0,600;1,300;1,600&family=IBM+Plex+Mono:'
             'wght@300;400;500&display=swap')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{_h(title)} &mdash; {_h(pub_name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{fonts}" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="no-print">
  <button onclick="window.print()">&#8595; Print / Save PDF</button>
</div>
{"".join(pages)}<script>{_JS}</script>
</body>
</html>'''


def _cli():
    parser = argparse.ArgumentParser(
        description='make_magazine_v1 — The Voice Express editorial magazine builder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Build from a JSON file of articles:
  python make_magazine_v1.py --articles articles.json --title "Summer 2025"

  # Build with custom output path and curator credit:
  python make_magazine_v1.py --articles articles.json \\
      --title "The State of Things" --creator "Mitali Sharma" \\
      --output state_of_things.html

  # Pipe JSON from another script:
  python fetch_articles.py | python make_magazine_v1.py --articles - --title "Quick Edition"

Article JSON format
-------------------
  [
    {
      "title": "Article headline",
      "content": "<p>Body HTML...</p>",
      "author_name": "Author Name",
      "published_date": "2025-05-25",
      "featured_image": "https://example.com/image.jpg",
      "category_name": "Ground Report",
      "section_name": "Politics",
      "tags": [{"name": "labour"}, {"name": "Delhi"}],
      "excerpt": "Short summary..."
    }
  ]
""")
    parser.add_argument(
        '--articles', '-a', required=True, metavar='FILE',
        help='Path to JSON file containing articles array (use - for stdin)')
    parser.add_argument(
        '--title', '-t', default='The Voice Express',
        help='Edition title (default: "The Voice Express")')
    parser.add_argument(
        '--creator', '-c', default='',
        help='Curator / editor name shown on cover')
    parser.add_argument(
        '--description', '-d', default='',
        help='Edition description (metadata)')
    parser.add_argument(
        '--output', '-o', default='magazine.html', metavar='FILE',
        help='Output HTML file (default: magazine.html)')
    parser.add_argument(
        '--static-root', default=None, metavar='DIR',
        help='Path to static assets directory (default: ./static)')
    parser.add_argument(
        '--logo', default=None, metavar='FILE',
        help='Path to publication logo PNG')
    parser.add_argument(
        '--cover-image', default=None, metavar='URL',
        help='URL or /static/ path for cover background image')
    args = parser.parse_args()

    try:
        if args.articles == '-':
            raw = sys.stdin.read()
        else:
            with open(args.articles, encoding='utf-8') as f:
                raw = f.read()
        articles = json.loads(raw)
        if not isinstance(articles, list):
            raise ValueError('Top-level JSON must be an array of articles')
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f'ERROR loading articles: {e}', file=sys.stderr)
        sys.exit(1)

    if not articles:
        print('ERROR: article list is empty', file=sys.stderr)
        sys.exit(1)

    print(f'Building magazine: {len(articles)} article(s) → {args.output}',
          file=sys.stderr)

    try:
        html = build_magazine_html(
            articles        = articles,
            title           = args.title,
            creator         = args.creator,
            description     = args.description,
            static_root     = args.static_root,
            logo_path       = args.logo,
            cover_image_url = args.cover_image,
        )
    except Exception as e:
        import traceback
        print(f'ERROR building magazine: {e}', file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(html)
        size_kb = os.path.getsize(args.output) / 1024
        print(f'Done. {args.output} ({size_kb:.0f} KB)', file=sys.stderr)
    except OSError as e:
        print(f'ERROR writing output: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    _cli()
