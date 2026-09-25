#!/usr/bin/env python3
from __future__ import annotations
import os, json, calendar
from html import escape as _esc, unescape as _un



def _date_str(s: str) -> str:
    s = (s or '')[:10]
    try:
        y, m, d = s.split('-')
        return f'{int(d)} {calendar.month_name[int(m)]} {y}'
    except Exception:
        return s


def _month_year_str(s: str) -> str:
    s = (s or '')[:10]
    try:
        y, m, _d = s.split('-')
        return f'{calendar.month_name[int(m)].upper()} {y}'
    except Exception:
        return ''


def build_article_parts(article: dict, static_root: str = None, config: dict = None,
                        enhancement: dict = None) -> dict:
    from make_newsletter_broadsheet import _embed, _qr, _blocks, _byline
    enhancement = enhancement or {}
    here = os.path.dirname(os.path.abspath(__file__))
    static_root = static_root or os.path.join(here, 'static')
    if config is None:
        try:
            with open(os.path.join(here, 'broadsheet_config.json'), encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            config = {}
    pub     = config.get('publication', {})
    support = config.get('support', {})
    contact = config.get('contact', {})

    title  = _un((article.get('title') or 'Untitled').strip())
    deck   = _un((article.get('excerpt') or '').strip())
    byline = _un(_byline(article))
    kicker = _un((article.get('section_name') or article.get('category_name') or '')).upper()
    date_s = _date_str(article.get('published_at'))
    month_year = _month_year_str(article.get('published_at'))
    rt     = article.get('reading_time')
    meta_bits = ' · '.join([b for b in [date_s, (f'{rt} min read' if rt else '')] if b])

    logo = _embed('/static/logo.png', static_root) or _embed('/logo-ve.png', static_root)
    logo_img = f'<img class="ap-logo" src="{logo}" alt="">' if logo else ''
    fi = article.get('featured_image')
    fi_b64 = _embed(fi, static_root) if fi else ''
    hero = ''

    blocks = _blocks(article.get('content') or '', static_root)
    body = ''.join(b['html'] for b in blocks)

    def panel(data, label, note):
        qr = _qr(data)
        qrx = f'<img class="ap-qr" src="{qr}">' if qr else '<div class="ap-qr ap-qr-x">—</div>'
        return (f'<div class="ap-supp">{qrx}<div><div class="ap-supp-l">{_esc(label)}</div>'
                f'<div class="ap-supp-n">{_esc(note)}</div></div></div>')
    kofi = support.get('kofi') or {}
    rzp  = support.get('razorpay') or {}
    site = contact.get('website', '') or pub.get('website', '')
    emag = contact.get('emag', '')
    stand = contact.get('newsstand', '')
    colophon = (
        (panel(kofi.get('url', ''), kofi.get('label', 'Support on Ko-fi'), kofi.get('note', '')) if kofi.get('url') else '') +
        (panel(rzp.get('url', ''), rzp.get('label', 'Support via Razorpay'), rzp.get('note', ''))
         if rzp.get('url') else '') +
        (panel(emag, 'Read the magazine', emag) if emag else panel(site, 'Read more online', site)) +
        (panel(stand, 'The Newsstand', stand) if stand else '')
    )

    kickx = f'<div class="ap-kicker">{_esc(kicker)}</div>' if kicker else ''
    deckx = f'<p class="ap-deck">{_esc(deck)}</p>' if deck else ''
    byx   = f'<div class="ap-byline">By {_esc(byline)}</div>' if byline else ''
    notex = (f'<div class="ap-covernote">{_esc(enhancement["cover_note"])}</div>'
             if enhancement.get('cover_note') else '')

    accent_c = '#3a3427'
    if fi_b64:
        cover_bg = f'background-image:url({fi_b64});background-size:cover;background-position:center'
        scrim_cls = 'ap-cover-scrim'
    else:
        cover_bg = f'background:{_esc(accent_c)}'
        scrim_cls = 'ap-cover-scrim ap-cover-scrim-flat'
    issue_x = f'<div class="ap-cover-issue">{_esc(month_year)}</div>' if month_year else ''
    header_html = (
        f'<div class="ap-cover-bleed" style="{cover_bg}">'
        f'<div class="{scrim_cls}"></div>'
        f'{issue_x}'
        f'<div class="ap-cover-mast">{logo_img}'
        f'<div class="ap-pub">{_esc(pub.get("name", "The Voice Express"))}</div>'
        f'<div class="ap-pub-tag">{_esc(pub.get("tagline", ""))}</div>'
        f'<div class="ap-standalone">The Voice Express Gazette</div></div>'
        f'<div class="ap-cover-foot">{kickx}'
        f'<h1 class="ap-cover-headline">{_esc(title)}</h1>{deckx}{byx}'
        f'<div class="ap-meta">{_esc(meta_bits)}</div>{notex}</div>'
        f'</div>')
    body_html = f'<div class="ap-body">{body}</div>'
    colophon_html = f'<div class="ap-colophon">{colophon}</div>'

    pagenum_css = ('@page{@bottom-center{content:counter(page) " / " counter(pages);'
                   'font-family:Georgia,serif;font-size:8pt;color:#5b5547}}'
                   if enhancement.get('page_numbers') else '')
    extra_css = enhancement.get('extra_css') or ''
    enh_css = '\n'.join(x for x in (pagenum_css, extra_css) if x)

    return {
        'title': title, 'pub_name': pub.get('name', 'The Voice Express'), 'tag': pub.get('tagline', ''),
        'header_html': header_html, 'body_html': body_html, 'colophon_html': colophon_html,
        'footname': pub.get('name', 'The Voice Express'), 'footnote': support.get('general_note', ''),
        'logo_img': logo_img, 'kickx': kickx, 'deckx': deckx, 'byx': byx, 'notex': notex,
        'meta_bits': meta_bits, 'hero': hero, 'body': body, 'colophon': colophon,
        'enh_css': enh_css,
    }


def build_article_print(article: dict, static_root: str = None, config: dict = None,
                        enhancement: dict = None) -> str:
    parts = build_article_parts(article, static_root=static_root, config=config, enhancement=enhancement)
    doc = _DOC
    doc = (doc.replace('__TITLE__', _esc(parts['title']))
               .replace('__HEADER__', parts['header_html'])
               .replace('__HERO__', parts['hero'])
               .replace('__BODY__', parts['body'])
               .replace('__COLOPHON__', parts['colophon'])
               .replace('__FOOTNAME__', _esc(parts['footname']))
               .replace('__FOOTNOTE__', _esc(parts['footnote'])))
    if parts.get('enh_css'):
        doc = doc.replace('</style>', parts['enh_css'] + '\n</style>')
    return doc


_DOC = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>__TITLE__ — The Voice Express Gazette</title>
<style>
:root{--ink:#16140f;--paper:#f4efe2;--g:#5b5547;--rule:2px solid #16140f;--thin:1px solid #b3ab98;--accent:#3a3427}
*{box-sizing:border-box}
@page{size:210mm 297mm;margin:14mm 16mm}
html,body{margin:0;background:transparent;font-family:"Georgia","Times New Roman",serif;color:var(--ink)}
.ap-doc{width:100%;max-width:178mm;margin:0 auto;padding:0;background:var(--paper)}
.ap-logo{height:48px;width:auto;margin:0 auto .6rem;display:block}
.ap-pub{font-variant:small-caps;letter-spacing:.16em;font-weight:700;font-size:.95rem}
.ap-pub-tag{font-style:italic;color:var(--g);font-size:.75rem;margin:0.25rem 0}
.ap-standalone{font-size:.50rem;letter-spacing:.26em;text-transform:uppercase;color:var(--g);margin:1rem 0 0.5rem;font-weight:500}
.ap-kicker{font-size:.60rem;letter-spacing:.20em;text-transform:uppercase;font-weight:700;color:var(--accent);margin:0.8rem 0 0}
.ap-deck{font-style:italic;font-size:1.05rem;line-height:1.45;color:#352f24;max-width:85%;margin:0.8rem auto 0.8rem;text-align:center}
.ap-byline{font-size:.65rem;letter-spacing:.13em;text-transform:uppercase;color:var(--g);text-align:center;margin:0.4rem 0}
.ap-meta{font-family:"Georgia",serif;font-size:.63rem;letter-spacing:.09em;text-transform:uppercase;color:var(--g);margin-top:.5rem;text-align:center}
.ap-covernote{font-style:italic;font-size:.78rem;color:var(--accent);text-align:center;margin:0.7rem auto 0;max-width:85%}
.ap-cover-bleed-wrap{margin:-14mm -16mm 0;width:calc(100% + 32mm);height:297mm;overflow:hidden;position:relative;page-break-after:always}
.ap-cover-bleed{position:relative;width:100%;height:100%;box-sizing:border-box;background-color:var(--ink);background-repeat:no-repeat;color:#fff;display:flex;flex-direction:column;justify-content:space-between;
  font-size:16px;--accent:#d6d1c2}
.ap-cover-issue{position:absolute;top:10mm;right:14mm;z-index:1;font-family:"Georgia",serif;font-size:.62em;
  letter-spacing:.2em;text-transform:uppercase;color:rgba(255,255,255,.75);font-weight:700}
.ap-cover-scrim{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(10,8,4,.74) 0%,rgba(10,8,4,.05) 32%,rgba(10,8,4,.08) 55%,rgba(10,8,4,.94) 100%)}
.ap-cover-scrim-flat{background:linear-gradient(160deg,rgba(0,0,0,.12),rgba(0,0,0,.42))}
.ap-cover-mast{position:relative;z-index:1;text-align:center;padding:16mm 14mm 0}
.ap-cover-mast .ap-pub{color:#fff;font-size:.95em}
.ap-cover-mast .ap-pub-tag{color:rgba(255,255,255,.78);font-size:.75em}
.ap-cover-mast .ap-standalone{color:rgba(255,255,255,.55);font-size:.50em}
.ap-cover-foot{position:relative;z-index:1;padding:0 14mm 18mm;text-align:center;color:#fff}
.ap-cover-foot .ap-kicker{font-size:.60em}
.ap-cover-foot .ap-covernote{font-size:.78em}
.ap-cover-headline{font-family:"Playfair Display","Georgia",serif;font-weight:900;font-size:3.1em;line-height:1.04;
  letter-spacing:-.5px;margin:.5em 0 .6em;text-align:center;text-shadow:0 2px 20px rgba(0,0,0,.55)}
.ap-cover-foot .ap-deck{color:rgba(255,255,255,.92);margin-left:auto;margin-right:auto;font-size:1.05em}
.ap-cover-foot .ap-byline{color:rgba(255,255,255,.82);font-size:.65em}
.ap-cover-foot .ap-meta{color:rgba(255,255,255,.68);font-size:.63em}
.ap-body{column-count:2;column-gap:10mm;column-rule:1px solid #d4cfc0;text-align:justify;hyphens:auto;
  font-size:.90rem;line-height:1.58;color:#2a2520}
.ap-body p{margin:0;text-indent:1em;orphans:2;widows:2}
.ap-body p[data-role="lede"]{text-indent:0;font-size:.95rem;line-height:1.52;font-weight:500}
.ap-body > p:first-of-type{text-indent:0}
.ap-body > p:first-of-type::first-letter{font-family:"Playfair Display","Georgia",serif;float:left;font-size:3.8rem;
  line-height:.75;font-weight:900;padding:.08em .15em 0 0;color:var(--ink)}
.ap-body .bs-sub{font-family:"Playfair Display","Georgia",serif;font-weight:700;font-size:1.15rem;margin:1.2rem 0 0.4rem;text-indent:0;line-height:1.1;column-span:1}
.ap-body .bs-quote{margin:1rem 0;padding:0.4rem 0 0.4rem 0.8mm;border-left:3.5px solid var(--accent);font-style:italic;
  font-size:.95rem;line-height:1.45;text-indent:0;column-span:1;page-break-inside:avoid}
.ap-body .bs-q-who{display:block;font-style:normal;font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--g);margin-top:.4rem}
.ap-body .bs-fig{margin:1.2rem 0;break-inside:avoid;column-span:1}
.ap-body .bs-fig img{width:100%;max-height:90mm;object-fit:contain;background:var(--paper);display:block;border:1px solid var(--g);margin-bottom:.4rem}
.ap-body .bs-fig figcaption{font-size:.64rem;color:#5a5247;line-height:1.35;text-indent:0;border-bottom:1px solid #d4cfc0;padding-bottom:.3rem;margin-bottom:0}
.ap-body .photo-credit{display:block;font-style:normal;opacity:.75;margin-top:.2em}
.ap-body .bs-list{margin:0.8rem 0 0.8rem 1.2rem;font-size:.88rem;line-height:1.5}
.ap-body .bs-list li{margin-bottom:.3rem}
.ap-colophon{margin-top:2.2rem;border-top:2px solid var(--ink);padding-top:1.2rem;break-inside:avoid}
.ap-colophon-head{font-family:"Playfair Display",serif;font-weight:700;font-size:1.0rem;margin-bottom:1rem;color:var(--ink)}
.ap-supps{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem}
.ap-supp{display:grid;grid-template-columns:56px 1fr;gap:.6rem;align-items:flex-start}
.ap-qr{width:56px;height:56px;flex-shrink:0}
.ap-qr-x{display:flex;align-items:center;justify-content:center;border:1px solid var(--g);color:var(--g);width:56px;height:56px;font-size:.7rem}
.ap-supp-l{font-weight:700;font-size:.82rem;line-height:1.2}
.ap-supp-n{font-size:.65rem;color:#5a5247;line-height:1.3}
.ap-foot{margin-top:1.2rem;border-top:1px solid #d4cfc0;padding-top:.6rem;display:flex;justify-content:space-between;
  font-size:.58rem;letter-spacing:.11em;text-transform:uppercase;color:var(--g)}
@media print{.ap-body{column-count:2}body{margin:0;padding:0}}
@media screen{
  .ap-cover-bleed-wrap{height:auto;min-height:297mm}
  .ap-cover-headline{font-size:clamp(1.6em,7vw,3.1em);overflow-wrap:break-word;word-break:break-word;
    hyphens:auto;-webkit-hyphens:auto;text-wrap:balance}
  .ap-cover-foot .ap-deck{font-size:clamp(.82em,3vw,1.05em);overflow-wrap:break-word;word-break:break-word;
    hyphens:auto;-webkit-hyphens:auto}
  .ap-cover-issue{font-size:clamp(.5em,1.6vw,.62em)}
}
</style></head><body>
<article class="ap-doc">
  <div class="ap-cover-bleed-wrap">__HEADER__</div>
  __HERO__
  <div class="ap-body">__BODY__</div>
  <section class="ap-colophon">
    <div class="ap-colophon-head">Reader-supported journalism</div>
    <div class="ap-supps">__COLOPHON__</div>
    <div class="ap-foot"><span>__FOOTNAME__</span><span>__FOOTNOTE__</span></div>
  </section>
</article>
</body></html>'''
