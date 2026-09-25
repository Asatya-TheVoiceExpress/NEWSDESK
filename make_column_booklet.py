#!/usr/bin/env python3
import os, re, json, calendar
from html import escape as _esc, unescape as _un

try:
    from make_newsletter_broadsheet import _embed, _qr
except Exception:
    def _embed(src, root): return src or ''
    def _qr(d): return ''

def _embed_imgs(html_str, static_root):
    if not html_str:
        return ''
    return re.sub(r'(<img[^>]+src=")([^"]+)(")',
                  lambda m: m.group(1) + _embed(m.group(2), static_root) + m.group(3),
                  html_str)

_FIG_RE = re.compile(r'<figure\b[^>]*>.*?</figure>', re.S | re.I)
_GROUP_RE = re.compile(r'<div class="photo-group"[^>]*>(.*?)</div>', re.S | re.I)
_CAP_RE = re.compile(r'<figcaption\b[^>]*>(.*?)</figcaption>', re.S | re.I)
_IMG_RE = re.compile(r'<img\b[^>]*>', re.I)


def _has_text(html_str):
    return bool(re.sub(r'<[^>]+>|&nbsp;|\s', '', html_str or ''))


def _split_images(body):
    figures = []

    def _take(fig_html):
        img = _IMG_RE.search(fig_html)
        if not img:
            return
        cap = _CAP_RE.search(fig_html)
        figures.append((img.group(0), (cap.group(1).strip() if cap else '')))

    for grp in _GROUP_RE.findall(body):
        for fig in _FIG_RE.findall(grp):
            _take(fig)
    prose = _GROUP_RE.sub('', body)
    for fig in _FIG_RE.findall(prose):
        _take(fig)
    prose = _FIG_RE.sub('', prose)
    for img in _IMG_RE.findall(prose):
        figures.append((img, ''))
    prose = _IMG_RE.sub('', prose)
    return figures, prose.strip()


def _image_page(img_html, caption, kicker=''):
    band = ''
    if caption or kicker:
        band = (f'<div class="cb-img-band">'
                f'{f"<span class=cb-img-k>{_esc(kicker)}</span>" if kicker else ""}'
                f'{f"<span class=cb-img-c>{caption}</span>" if caption else ""}'
                f'</div>')
    return f'<section class="cb-page cb-imgpage"><div class="cb-img-wrap">{img_html}</div>{band}</section>'


def _date(s):
    s = (s or '')[:10]
    try:
        y, m, d = s.split('-'); return f'{int(d)} {calendar.month_name[int(m)]} {y}'
    except Exception:
        return s

try:
    from pub_icons import flow_field_png, voronoi_png
except Exception:
    flow_field_png = voronoi_png = lambda *a, **k: None

import datetime as _dt, hashlib as _hl

def _grouping(period, d):
    s = (d or '')[:10]
    try:
        dt = _dt.date.fromisoformat(s)
    except Exception:
        return ('', 'flow', '')
    if period == 'month':
        iso = dt.isocalendar(); return (f'{iso[0]}-W{iso[1]:02d}', 'flow', f'Week {iso[1]}')
    if period == 'year':
        return (f'{dt.year}-{dt.month:02d}', 'voro', dt.strftime('%B %Y'))
    if period == 'all':
        return (f'{dt.year}', 'voro', str(dt.year))
    return (None, None, None)

def _art_cover(art, kicker, big, sub=''):
    art_img = f'<div class="cb-art"><img src="{art}" alt=""></div>' if art else ''
    return (f'<section class="cb-page cb-artcover">{art_img}'
            f'<div class="cb-cover-band"><div class="cb-kicker">{_esc(kicker)}</div>'
            f'<h1 class="cb-cover-ttl">{_esc(big)}</h1>'
            f'{f"<div class=cb-cover-sub>{_esc(sub)}</div>" if sub else ""}</div></section>')

def _date_page(n, date_str, title, sub='', cover=''):
    art = f'<div class="cb-date-art"><img src="{cover}" alt=""></div>' if cover else ''
    return (f'<section class="cb-page cb-datepage{" has-art" if cover else ""}">{art}'
            f'<div class="cb-date-band">'
            f'<div class="cb-date-no">{n:02d}</div>'
            f'<div class="cb-date-big">{_esc(date_str)}</div>'
            f'<h2 class="cb-date-ttl">{_esc(title)}</h2>'
            f'{f"<div class=cb-date-sub>{_esc(sub)}</div>" if sub else ""}'
            f'</div></section>')


def build_column_booklet(col, entries, static_root=None, config=None, period='all', label='',
                         enhancement=None):
    enhancement = enhancement or {}
    static_root = static_root or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    if config is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'broadsheet_config.json'), encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            config = {}
    support = config.get('support', {}); contact = config.get('contact', {}); pub = config.get('publication', {})
    title = _un((col.get('title') or 'Column').strip())
    subtitle = _un((col.get('subtitle') or '').strip())
    desc = _un((col.get('description') or '').strip())
    byline = _un((entries[0].get('byline_auto') or entries[0].get('byline') or '').strip()) if entries else ''
    cadence = (col.get('cadence') or '').strip()

    dates = [(e.get('published_at') or '')[:10] for e in entries if e.get('published_at')]
    run = ''
    if dates:
        lo, hi = min(dates), max(dates)
        run = _date(lo) if lo == hi else f'{_date(lo)} – {_date(hi)}'

    n = len(entries)
    seed = int(_hl.md5(f'{title}|{period}|{label}|{run}'.encode()).hexdigest()[:8], 16)
    main_kind = 'flow' if period == 'week' else 'voro'
    main_art = (flow_field_png(seed) if main_kind == 'flow' else voronoi_png(seed))
    period_lbl = {'week': 'Weekly compilation', 'month': 'Monthly compilation',
                  'year': 'Yearly compilation', 'all': 'Collected edition'}.get(period, 'Compilation')
    cover_sub = label or run or subtitle
    cover = _art_cover(_embed(main_art, static_root) if main_art else '',
                       f'A Voice Express Column · {period_lbl}', title, cover_sub)

    plural = 'entry' if n == 1 else 'entries'
    cover_note = (enhancement.get('cover_note') or '').strip()
    intro = (f'<section class="cb-page cb-intro">'
             f'<div class="cb-intro-mark">¶</div>'
             f'<h2 class="cb-intro-ttl">{_esc(title)}</h2>'
             f'{f"<p class=cb-intro-sub>{_esc(subtitle)}</p>" if subtitle else ""}'
             f'{f"<p class=cb-intro-desc>{_esc(desc)}</p>" if desc else ""}'
             f'{f"<p class=cb-intro-note>{_esc(cover_note)}</p>" if cover_note else ""}'
             f'<dl class="cb-meta">'
             f'{f"<dt>Contributors</dt><dd>{_esc(byline)}</dd>" if byline else ""}'
             f'{f"<dt>Cadence</dt><dd>{_esc(cadence)}</dd>" if cadence else ""}'
             f'<dt>In this collection</dt><dd>{n} {plural}</dd>'
             f'{f"<dt>Run</dt><dd>{_esc(run)}</dd>" if run else ""}'
             f'</dl></section>')

    want_toc = bool(enhancement.get('toc')) and n > 1
    base_offset = 2 + (1 if want_toc else 0)
    ents = sorted(entries, key=lambda e: (e.get('published_at') or ''))
    chapters = []; cur_key = None; toc_rows_meta = []
    for i, e in enumerate(ents, 1):
        gk, kind, sect = _grouping(period, e.get('published_at'))
        if gk is not None and gk != cur_key:
            cur_key = gk
            sseed = int(_hl.md5(f'{title}|{gk}'.encode()).hexdigest()[:8], 16)
            sart = flow_field_png(sseed) if kind == 'flow' else voronoi_png(sseed)
            chapters.append(_art_cover(_embed(sart, static_root) if sart else '', title, sect))
        body = _embed_imgs(e.get('content') or '', static_root)
        et = _un((e.get('title') or '').strip())
        es = _un((e.get('excerpt') or '').strip())
        edate = _date(e.get('published_at'))
        chapters.append(_date_page(i, edate, et, es))
        toc_rows_meta.append((et, edate, base_offset + len(chapters)))

        figures, prose = _split_images(body)
        cover_img = (e.get('featured_image') or '').strip()
        if not figures and cover_img:
            figures = [(f'<img src="{_embed(cover_img, static_root)}" alt="">', '')]
        for fig_img, fig_cap in figures:
            chapters.append(_image_page(fig_img, fig_cap, f'{i:02d} · {edate}'))

        if _has_text(prose):
            chapters.append(
                f'<section class="cb-page cb-entry">'
                f'<div class="cb-entry-head"><span class="cb-no">{i:02d}</span>'
                f'<span class="cb-entry-date">{_esc(edate)}</span></div>'
                f'<h2 class="cb-entry-ttl">{_esc(et)}</h2>'
                f'{f"<p class=cb-entry-sub>{_esc(es)}</p>" if es else ""}'
                f'<div class="cb-body">{prose}</div></section>')

    toc = ''
    if want_toc:
        rows = ''.join(
            f'<div class="cb-toc-row"><span class="cb-toc-no">{i:02d}</span>'
            f'<span class="cb-toc-t">{_esc(et[:60])}</span><span class="cb-toc-d">{_esc(d)}</span>'
            f'<span class="cb-toc-p">{p}</span></div>'
            for i, (et, d, p) in enumerate(toc_rows_meta, 1))
        toc = f'<section class="cb-page cb-toc"><div class="cb-toc-head">Contents</div>{rows}</section>'

    qr_kofi = _qr((support.get('kofi') or {}).get('url', ''))
    rzp_url = (support.get('razorpay') or {}).get('url', '')
    qr_rzp = _qr(rzp_url)
    site_url = contact.get('website', '') or pub.get('website', '')
    emag_url = contact.get('emag', '')
    stand_url = contact.get('newsstand', '')
    qr_site = _qr(emag_url or site_url)
    qr_stand = _qr(stand_url)
    def panel(qr, label, note=''):
        img = f'<img src="{qr}">' if qr else ''
        notex = f'<div class="cb-supp-n">{_esc(note)}</div>' if note else ''
        return f'<div class="cb-supp">{img}<div class="cb-supp-l">{_esc(label)}</div>{notex}</div>'
    kofi_html = panel(qr_kofi, "Ko-fi") if (support.get('kofi') or {}).get('url') else ''
    rzp_html = panel(qr_rzp, "Support", "Razorpay") if rzp_url else ''
    stand_html = panel(qr_stand, "Newsstand", stand_url) if stand_url else ''
    colo_contact = ' · '.join(b for b in (contact.get('email', ''), emag_url or site_url) if b)
    back = (f'<section class="cb-page cb-back">'
            f'<div class="cb-back-head">Reader-supported journalism</div>'
            f'<div class="cb-supp-row">{kofi_html}{rzp_html}'
            f'{panel(qr_site, "Read online", emag_url or site_url)}{stand_html}</div>'
            f'<div class="cb-colophon"><strong>{_esc(pub.get("name","The Voice Express"))}</strong>'
            f'{" — " + _esc(colo_contact) if colo_contact else ""}</div></section>')

    pages = [cover, intro] + ([toc] if toc else []) + chapters + [back]
    if enhancement.get('page_numbers', True):
        pub_name = pub.get('name', 'The Voice Express')
        total = len(pages)
        def _foot(i):
            return (f'<div class="cb-foot"><span>{_esc(pub_name)}</span>'
                    f'<span>{i} / {total}</span></div>')
        pages = [p[:-len('</section>')] + _foot(i) + '</section>' if p.endswith('</section>') else p
                 for i, p in enumerate(pages, 1)]

    body_html = ''.join(pages)
    accent_css = f':root{{--accent:{enhancement["accent"]}}}' if enhancement.get('accent') else ''
    extra_css = enhancement.get('extra_css') or ''
    doc = _DOC.replace('__TITLE__', _esc(f'{title} — Booklet')).replace('__BODY__', body_html)
    if accent_css or extra_css:
        doc = doc.replace('</style>', accent_css + '\n' + extra_css + '\n</style>')
    return doc

_DOC = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
:root{--ink:#16140f;--paper:#f4efe2;--g:#5b5547;--rule:1.5px solid #16140f;--thin:1px solid #b3ab98;--accent:#7a2018}
*{box-sizing:border-box}
@page{size:148mm 210mm;margin:0}
html,body{margin:0;background:#9a948a;font-family:"EB Garamond","Georgia",serif;color:var(--ink)}
.cb-page{position:relative;width:148mm;min-height:210mm;margin:10px auto;background:var(--paper);
  padding:14mm 13mm;box-shadow:0 4px 18px rgba(0,0,0,.32);page-break-after:always;overflow:hidden}
.cb-page:last-child{page-break-after:auto}
img{filter:grayscale(1) contrast(1.04)}
.cb-cover,.cb-artcover{padding:0;display:flex;flex-direction:column;height:210mm}
.cb-art{flex:1;min-height:0;overflow:hidden}
.cb-art img{width:100%;height:100%;object-fit:cover;display:block}
.cb-grid{flex:1;display:grid;gap:2px;background:#16140f}
.cb-tile{overflow:hidden}
.cb-tile img{width:100%;height:100%;object-fit:cover;display:block}
.cb-tile-empty{background:#cdc3ad}
.cb-cover-band{background:#16140f;color:var(--paper);padding:8mm 10mm 10mm}
.cb-kicker{font-family:"Courier Prime",monospace;font-size:.56rem;letter-spacing:.28em;text-transform:uppercase;opacity:.7;margin-bottom:.4rem}
.cb-cover-ttl{font-family:"Playfair Display","Georgia",serif;font-weight:900;font-size:2.6rem;line-height:1;margin:0}
.cb-cover-sub{font-style:italic;font-size:1.02rem;margin-top:.5rem;opacity:.92}
.cb-cover-by{font-family:"Courier Prime",monospace;font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;margin-top:.7rem;opacity:.75}
.cb-intro{display:flex;flex-direction:column;justify-content:center}
.cb-intro-mark{font-size:3rem;color:var(--g);line-height:1}
.cb-intro-ttl{font-family:"Playfair Display",serif;font-weight:900;font-size:2rem;margin:.4rem 0 .2rem}
.cb-intro-sub{font-style:italic;font-size:1.1rem;color:#352f24;margin:.2rem 0 1rem}
.cb-intro-desc{font-size:.96rem;line-height:1.6;color:#2a261d}
.cb-meta{margin-top:1.4rem;border-top:var(--thin);padding-top:1rem}
.cb-meta dt{font-family:"Courier Prime",monospace;font-size:.54rem;letter-spacing:.16em;text-transform:uppercase;color:var(--g);margin-top:.6rem}
.cb-meta dd{margin:0;font-size:.95rem}
.cb-imgpage{padding:0;display:flex;flex-direction:column;height:210mm;background:var(--paper)}
.cb-img-wrap{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.cb-img-wrap img{width:100%;height:100%;object-fit:contain;display:block}
.cb-img-band{flex:0 0 auto;display:flex;justify-content:space-between;align-items:baseline;gap:1rem;
  padding:4mm 13mm 14mm;font-family:"Courier Prime",monospace;font-size:.54rem;
  letter-spacing:.1em;color:var(--g);border-top:var(--thin)}
.cb-img-k{text-transform:uppercase;white-space:nowrap;color:var(--accent)}
.cb-img-c{text-align:right}
.cb-datepage{padding:0;display:flex;flex-direction:column;justify-content:flex-end;height:210mm}
.cb-date-art{flex:1;overflow:hidden;min-height:0}
.cb-date-art img{width:100%;height:100%;object-fit:cover;display:block}
.cb-datepage:not(.has-art){justify-content:center;padding:14mm 13mm}
.cb-date-band{background:#16140f;color:var(--paper);padding:9mm 13mm 11mm}
.cb-datepage:not(.has-art) .cb-date-band{background:none;color:var(--ink);padding:0;
  border-top:var(--rule);border-bottom:var(--rule)}
.cb-date-no{font-family:"Playfair Display",serif;font-weight:900;font-size:1.1rem;
  color:var(--accent);line-height:1}
.cb-datepage:not(.has-art) .cb-date-no{margin-top:.8rem}
.cb-date-big{font-family:"Playfair Display",serif;font-weight:900;font-size:2.4rem;
  line-height:1.05;margin:.2rem 0 .4rem}
.cb-date-ttl{font-family:"Playfair Display",serif;font-weight:700;font-size:1.15rem;
  line-height:1.2;margin:0;opacity:.92}
.cb-date-sub{font-style:italic;font-size:.92rem;margin-top:.35rem;opacity:.8}
.cb-datepage:not(.has-art) .cb-date-sub{margin-bottom:.9rem}
.cb-entry-head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:var(--rule);padding-bottom:.3rem}
.cb-no{font-family:"Playfair Display",serif;font-weight:900;font-size:1.4rem;color:var(--accent)}
.cb-intro-note{font-size:.86rem;font-style:italic;color:var(--accent);margin:.3rem 0 0}
.cb-foot{position:absolute;left:13mm;right:13mm;bottom:6mm;display:flex;justify-content:space-between;
  font-family:"Courier Prime",monospace;font-size:.52rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--g);border-top:var(--thin);padding-top:.25rem}
.cb-toc{display:flex;flex-direction:column}
.cb-toc-head{font-family:"Playfair Display",serif;font-weight:900;font-size:1.6rem;border-bottom:var(--rule);
  padding-bottom:.4rem;margin-bottom:.8rem}
.cb-toc-row{display:grid;grid-template-columns:1.6rem 1fr auto auto;gap:.5rem;align-items:baseline;
  border-bottom:1px dotted #b3ab98;padding:.3rem 0;font-size:.86rem}
.cb-toc-no{color:var(--accent);font-weight:700}
.cb-toc-t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cb-toc-d{font-family:"Courier Prime",monospace;font-size:.62rem;color:var(--g)}
.cb-toc-p{font-weight:700;color:var(--accent)}
.cb-entry-date{font-family:"Courier Prime",monospace;font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:var(--g)}
.cb-entry-ttl{font-family:"Playfair Display",serif;font-weight:800;font-size:1.7rem;line-height:1.05;margin:.6rem 0 .2rem}
.cb-entry-sub{font-style:italic;font-size:1.02rem;color:#352f24;margin:.1rem 0 .8rem}
.cb-body{font-size:.98rem;line-height:1.62;text-align:justify;hyphens:auto}
.cb-body p{margin:0 0 .7rem;break-inside:avoid}
.cb-body p[data-text-role=lede]:first-letter{font-family:"Playfair Display",serif;font-size:2.6rem;float:left;line-height:.8;padding:.1rem .3rem .1rem 0}
.cb-body h2,.cb-body h3,.cb-body .section-heading{font-family:"Playfair Display",serif;font-size:1.1rem;margin:1rem 0 .3rem;break-after:avoid}
.cb-body figure{margin:.9rem -13mm;break-inside:avoid}
.cb-body img{width:100%;height:auto;max-height:163mm;object-fit:contain;display:block}
.cb-body figcaption{font-family:"Courier Prime",monospace;font-size:.56rem;color:var(--g);
  margin-top:.25rem;padding:0 13mm;text-align:left}
.cb-body .photo-credit,.cb-img-c .photo-credit{display:block;opacity:.7;margin-top:.2em}
.cb-body .photo-group{display:block;margin:.9rem -13mm}
.cb-body .photo-group figure{margin:0 0 .5rem}
.cb-body .photo-group img{width:100%;height:auto}
.cb-body .photo-group figcaption{padding:0 13mm}
.cb-body blockquote{font-family:"Playfair Display",serif;font-size:1.15rem;font-style:italic;line-height:1.4;
  border-left:3px solid var(--ink);margin:.8rem 0;padding:.2rem 0 .2rem 1rem;text-align:left}
.cb-body blockquote cite{display:block;font-family:"Courier Prime",monospace;font-size:.58rem;font-style:normal;
  letter-spacing:.08em;text-transform:uppercase;color:var(--g);margin-top:.4rem}
.cb-body .qa-line{margin:0 0 .5rem}.cb-body .qa-speaker{font-weight:700}
.cb-body .gen-art{max-width:100%;border:1px solid var(--ink)}
.cb-body .gen-poem{text-align:center;font-style:italic;border-bottom:var(--thin);padding:.6rem 0;margin:.6rem 0}
.cb-body .gen-poem-ttl{font-family:"Courier Prime",monospace;font-size:.52rem;letter-spacing:.16em;text-transform:uppercase;font-style:normal;color:var(--g);margin-bottom:.4rem}
.cb-back{display:flex;flex-direction:column;justify-content:center}
.cb-back-head{font-family:"Playfair Display",serif;font-weight:700;font-size:1.2rem;border-bottom:var(--rule);padding-bottom:.4rem;margin-bottom:1rem}
.cb-supp-row{display:flex;gap:1rem;justify-content:space-around}
.cb-supp{text-align:center}
.cb-supp img{width:30mm;height:30mm}
.cb-supp-l{font-family:"Courier Prime",monospace;font-size:.56rem;letter-spacing:.1em;text-transform:uppercase;margin-top:.3rem}
.cb-colophon{margin-top:auto;border-top:var(--thin);padding-top:.8rem;font-size:.78rem;color:#2a261d;line-height:1.5}
@media print{
  html,body{background:var(--paper)}
  .cb-page{margin:0;box-shadow:none}
}
</style></head><body>__BODY__</body></html>'''
