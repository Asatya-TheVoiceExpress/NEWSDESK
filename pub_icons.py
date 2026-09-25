#!/usr/bin/env python3
import base64, hashlib, math, os, random, re
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    _PIL = True
except ImportError:
    _PIL = False

_BASE     = Path(__file__).parent
import ve.paths as _ve_paths

_UPLOADS  = Path(_ve_paths.uploads_path())
_LOGO_PNG = _BASE / "logo-ve.png"

IW, IH = 300, 420


def _atomic_save_img(img, path):
    tmp = path.with_name(path.name + ".tmp")
    img.save(tmp, "PNG", optimize=True)
    os.replace(tmp, path)


def _atomic_write_text(text, path, encoding="utf-8"):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def _valid_cache(path):
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False

_INK   = (10,  10,  10)
_PAPER = (244, 244, 244)
_BODY  = (20,  20,  20)
_DIM   = (102, 102, 102)
_RULE  = (170, 170, 170)


def _font(size, bold=False):
    if not _PIL:
        return None
    names = (["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
               "LiberationSans-Bold.ttf", "Verdana Bold.ttf"]
             if bold else
             ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
              "LiberationSans-Regular.ttf", "Verdana.ttf"])
    dirs = [
        Path("C:/Windows/Fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/Library/Fonts"),
        Path("/usr/share/fonts"),
    ]
    for name in names:
        for d in dirs:
            p = d / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _serif(size, bold=False, italic=False):
    if not _PIL:
        return None
    if bold and italic:
        names = ["georgiaz.ttf", "timesbi.ttf", "BOOKOSBI.TTF", "cambriaz.ttf"]
    elif bold:
        names = ["georgiab.ttf", "timesbd.ttf", "BOOKOSB.TTF", "cambriab.ttf"]
    elif italic:
        names = ["georgiai.ttf", "timesi.ttf", "BOOKOSI.TTF", "cambriai.ttf"]
    else:
        names = ["georgia.ttf", "times.ttf", "BOOKOS.TTF", "cambria.ttf"]
    dirs = [Path("C:/Windows/Fonts"), Path("/Library/Fonts"),
            Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts")]
    for name in names:
        for d in dirs:
            p = d / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    pass
    return _font(size, bold)


def _times(size, bold=False, italic=False):
    if not _PIL:
        return None
    fn = ("timesbi.ttf" if bold and italic else "timesbd.ttf" if bold
          else "timesi.ttf" if italic else "times.ttf")
    for d in (Path("C:/Windows/Fonts"), Path("/Library/Fonts"),
              Path("/usr/share/fonts")):
        p = d / fn
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return _serif(size, bold, italic)


def _text_size(draw, text, font):
    try:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        return len(text) * max(6, font.size // 2), font.size if hasattr(font, 'size') else 10


def _spaced_w(draw, text, font, tracking):
    if not text:
        return 0
    w = sum(_text_size(draw, ch, font)[0] for ch in text)
    return w + tracking * (len(text) - 1)


def _spaced(draw, cx, y, text, font, fill, tracking, stroke=0, stroke_fill=None):
    total = _spaced_w(draw, text, font, tracking)
    x = cx - total / 2
    h = 0
    for ch in text:
        cw, ch_h = _text_size(draw, ch, font)
        draw.text((x, y), ch, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=stroke_fill)
        x += cw + tracking
        h = max(h, ch_h)
    return h


def _fit_spaced(draw, text, target_w, tracking, serif=True, bold=True,
                max_size=200, min_size=8):
    load = (lambda s: _serif(s, bold)) if serif else (lambda s: _font(s, bold))
    lo, hi, best = min_size, max_size, load(min_size)
    while lo <= hi:
        mid = (lo + hi) // 2
        f = load(mid)
        if _spaced_w(draw, text, f, tracking) <= target_w:
            best, lo = f, mid + 1
        else:
            hi = mid - 1
    return best


def _save(img, key):
    _UPLOADS.mkdir(parents=True, exist_ok=True)
    p = _UPLOADS / f"_icon_{key}.png"
    _atomic_save_img(img, p)
    return f"/static/uploads/_icon_{key}.png"


def _key(pub_type, tags, title, seed=42, article_images=None):
    clean_imgs = [i for i in (article_images or []) if i][:8]
    clean_tags = [t for t in (tags or []) if t][:8]
    img_part = "|".join(sorted(clean_imgs))
    raw = f"{pub_type}|{seed}|{'|'.join(sorted(clean_tags))}|{(title or '')[:40]}|{img_part}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _logo_bitmap(px_w, px_h, threshold=140):
    if not _PIL or not _LOGO_PNG.exists():
        return None
    try:
        logo = Image.open(_LOGO_PNG).convert("L")
        logo = logo.resize((px_w, px_h), Image.LANCZOS)
        return [[logo.getpixel((c, r)) > threshold
                 for c in range(px_w)]
                for r in range(px_h)]
    except Exception:
        return None


def _resolve_img_path(url):
    if not url:
        return None
    url = str(url).strip()
    if url.startswith(('http://', 'https://')):
        return None
    url = url.lstrip('/')
    if url.startswith('static/uploads/'):
        return _UPLOADS / url[len('static/uploads/'):]
    return _UPLOADS / Path(url).name


def _make_pdf_icon(tags, title, seed):
    rng  = random.Random(seed)
    img  = Image.new("RGBA", (IW, IH), (*_INK, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    words = [t.upper() for t in tags if t.strip()] or ["VOICE", "EXPRESS", "TRUTH"]
    pool  = (words * 30)[:300]
    rng.shuffle(pool)
    wi    = 0

    fn_sm = _font(8)
    fn_md = _font(9, bold=True)

    COLS  = 14
    col_w = IW / COLS

    for col in range(COLS):
        x      = int(col * col_w + rng.uniform(1, col_w * 0.4))
        head_y = rng.randint(IH // 5, IH - 18)
        trail  = rng.randint(6, 20)

        for row in range(trail + 2):
            y = head_y - row * 13
            if y < -12 or y > IH:
                continue
            frac = row / max(trail, 1)

            if row == 0:
                op  = rng.randint(220, 255)
                rgb = (230, 235, 230)
                fn  = fn_md
            elif row == 1:
                op  = rng.randint(160, 210)
                rgb = (190, 200, 190)
                fn  = fn_sm
            else:
                op  = max(15, int(170 * max(0.0, 1 - frac) ** 2.2))
                g   = rng.randint(100, 155)
                rgb = (g, g + 5, g)
                fn  = fn_sm

            word = pool[wi % len(pool)][:6]; wi += 1
            draw.text((x, y), word, font=fn, fill=(*rgb, op))

        for _ in range(rng.randint(0, 2)):
            gy = head_y + rng.randint(14, max(15, IH - head_y - 4))
            if gy >= IH:
                continue
            op = rng.randint(8, 28)
            draw.text((x, gy), pool[wi % len(pool)][:4], font=fn_sm,
                      fill=(110, 110, 110, op)); wi += 1

    fn_lbl = _font(10, bold=True)
    short  = title[:26].upper() if title else "PDF"
    tw, th = _text_size(draw, short, fn_lbl)
    draw.rectangle([0, IH - 28, IW, IH], fill=(8, 8, 8, 210))
    draw.text(((IW - tw) / 2, IH - 22), short, font=fn_lbl,
              fill=(210, 215, 210, 225))

    return img.convert("RGB")


def _make_emag_icon(tags, title, seed):
    rng   = random.Random(seed)
    img   = Image.new("RGB", (IW, IH), _PAPER)
    draw  = ImageDraw.Draw(img)

    words = [t.upper() for t in tags if t.strip()] or ["VOICE", "EXPRESS"]
    pool  = (words * 15)[:120]
    rng.shuffle(pool)

    sizes_layers = [(26, 4), (20, 5), (15, 7), (11, 10), (8, 14), (7, 18)]

    placed = []
    wi     = 0

    def _overlaps(x, y, w, h, pad=5):
        for px, py, pw, ph in placed:
            if (x - pad < px + pw and x + w + pad > px and
                    y - pad < py + ph and y + h + pad > py):
                return True
        return False

    for sz, count in sizes_layers:
        fn = _font(sz, bold=(sz >= 18))
        for _ in range(count * 4):
            word = pool[wi % len(pool)]; wi += 1
            tw, th = _text_size(draw, word, fn)
            if tw <= 0: continue
            x = rng.randint(3, max(4, IW - tw - 3))
            y = rng.randint(3, max(4, IH - th - 3))
            if not _overlaps(x, y, tw, th):
                darkness = rng.randint(8, 130)
                draw.text((x, y), word, font=fn, fill=(darkness, darkness, darkness))
                placed.append((x, y, tw, th))

    if title:
        fn_t  = _font(13, bold=True)
        short = title[:24].upper()
        tw, th = _text_size(draw, short, fn_t)
        cx    = (IW - tw) // 2
        cy    = (IH - th) // 2
        pad   = 8
        draw.rectangle([cx - pad, cy - pad, cx + tw + pad, cy + th + pad],
                       fill=(248, 248, 248))
        draw.line([cx - pad, cy - pad, cx + tw + pad, cy - pad],
                  fill=_BODY, width=1)
        draw.line([cx - pad, cy + th + pad, cx + tw + pad, cy + th + pad],
                  fill=_BODY, width=1)
        draw.text((cx, cy), short, font=fn_t, fill=_BODY)

    return img


def _make_epub_icon(title, tags, seed):
    fn = None
    for name in ["cour.ttf", "DejaVuSansMono.ttf",
                 "LiberationMono-Regular.ttf", "consola.ttf"]:
        for d in [Path("C:/Windows/Fonts"),
                  Path("/usr/share/fonts/truetype/dejavu"),
                  Path("/usr/share/fonts/truetype/liberation"),
                  Path("/Library/Fonts")]:
            p = d / name
            if p.exists():
                try:
                    fn = ImageFont.truetype(str(p), 7)
                    break
                except Exception:
                    pass
        if fn:
            break
    if fn is None:
        fn = _font(7)

    tmp_img  = Image.new("RGB", (80, 20))
    tmp_draw = ImageDraw.Draw(tmp_img)
    try:
        bb  = tmp_draw.textbbox((0, 0), "M" * 10, font=fn)
        CW  = max(3, (bb[2] - bb[0]) // 10)
        bb1 = tmp_draw.textbbox((0, 0), "M", font=fn)
        CH  = max(6, bb1[3] - bb1[1] + 1)
    except Exception:
        CW, CH = 4, 8

    COLS = IW // CW
    ROWS = IH // CH

    C_BG    = (13, 15, 13)
    C_BGPAT = (19, 22, 19)
    C_BORD  = (42, 58, 42)
    C_LOGO  = (212, 232, 212)
    C_LOGOD = (50, 70, 50)
    C_EDGE  = (148, 172, 148)
    C_PFILL = (36, 50, 36)
    C_PDIM  = (22, 32, 22)
    C_UNDER = (16, 19, 16)
    C_SPINE = (108, 138, 108)
    C_TITLE = (188, 212, 188)
    C_LABEL = (90, 120, 90)
    C_TAGS  = (38, 52, 38)

    chars  = [[' '] * COLS for _ in range(ROWS)]
    colors = [[C_BG]  * COLS for _ in range(ROWS)]

    def put(r, c, ch, col):
        if 0 <= r < ROWS and 0 <= c < COLS:
            chars[r][c]  = ch
            colors[r][c] = col

    def hline(r, c1, c2, ch, col):
        for c in range(max(0, c1), min(COLS, c2 + 1)):
            put(r, c, ch, col)

    def vline(ci, r1, r2, ch, col):
        for r in range(max(0, r1), min(ROWS, r2 + 1)):
            put(r, ci, ch, col)

    def textrow(r, c, s, col):
        for i, ch in enumerate(s):
            put(r, c + i, ch, col)

    bg = ".ve.xe."
    for r in range(ROWS):
        for c in range(COLS):
            put(r, c, bg[(r * 7 + c * 3) % len(bg)], C_BGPAT)

    hline(0,      0, COLS - 1, '#', C_BORD)
    hline(ROWS-1, 0, COLS - 1, '#', C_BORD)

    LOGO_PX = 14
    PW      = 2
    LOGO_W  = LOGO_PX * PW
    LOGO_R  = 2
    LOGO_C  = (COLS - LOGO_W) // 2
    GH      = LOGO_PX

    bitmap = _logo_bitmap(LOGO_PX, LOGO_PX)
    if bitmap:
        for ri, row in enumerate(bitmap):
            for ci, lit in enumerate(row):
                ch  = 'X' if lit else 'x'
                col = C_LOGO if lit else C_LOGOD
                for pw in range(PW):
                    put(LOGO_R + ri, LOGO_C + ci * PW + pw, ch, col)
    else:
        fallback = ["XX....XX", "XX....XX", ".XX..XX.", ".XX..XX.",
                    "..XXXX..", "...XX...", "...XX..."]
        GH = len(fallback)
        for ri, row in enumerate(fallback):
            for ci, b in enumerate(row):
                ch  = 'X' if b == 'X' else 'x'
                col = C_LOGO if b == 'X' else C_LOGOD
                for pw in range(PW):
                    put(LOGO_R + ri, LOGO_C + ci * PW + pw, ch, col)

    sub_r = LOGO_R + GH + 1
    sub   = "THE VOICE EXPRESS"
    textrow(sub_r, (COLS - len(sub)) // 2, sub, C_LABEL)

    sep_r = sub_r + 1
    hline(sep_r, 1, COLS - 2, '-', C_BORD)

    BK_TOP = sep_r + 1
    BK_BOT = ROWS - 5
    BK_H   = BK_BOT - BK_TOP
    SPINE  = COLS // 2
    BK_L   = 1
    BK_R   = COLS - 2

    hline(BK_TOP, BK_L, BK_R, '=', C_EDGE)
    hline(BK_BOT, BK_L, BK_R, '=', C_EDGE)
    put(BK_TOP, BK_L, '+', C_EDGE); put(BK_TOP, BK_R, '+', C_EDGE)
    put(BK_BOT, BK_L, '+', C_EDGE); put(BK_BOT, BK_R, '+', C_EDGE)
    vline(BK_L, BK_TOP + 1, BK_BOT - 1, '|', C_EDGE)
    vline(BK_R, BK_TOP + 1, BK_BOT - 1, '|', C_EDGE)

    vline(SPINE, BK_TOP, BK_BOT, '|', C_SPINE)

    for r in range(BK_TOP + 1, BK_BOT):
        lc  = '~' if (r - BK_TOP) % 2 == 0 else '-'
        lco = C_PFILL if (r - BK_TOP) % 2 == 0 else C_PDIM
        for c in range(SPINE + 1, BK_R):
            put(r, c, lc, lco)

    mid_r = (BK_TOP + BK_BOT) // 2
    ttl   = (title[:12] if title else "VOICE").upper()
    t_col = SPINE + 1 + max(0, (BK_R - SPINE - 2 - len(ttl)) // 2)
    for c in range(SPINE + 1, BK_R):
        put(mid_r - 1, c, ' ', C_BG)
        put(mid_r,     c, ' ', C_BG)
        put(mid_r + 1, c, ' ', C_BG)
    textrow(mid_r, t_col, ttl, C_TITLE)

    left_mid = (BK_L + SPINE) // 2
    for r in range(BK_TOP + 1, BK_BOT):
        frac   = (r - BK_TOP) / max(1, BK_H)
        fold_c = int(left_mid + (BK_L + 1 - left_mid) * frac)
        fold_c = max(BK_L + 1, min(SPINE - 2, fold_c))

        for c in range(BK_L + 1, fold_c):
            lc  = '~' if (r - BK_TOP) % 2 == 0 else '-'
            lco = C_PFILL if (r - BK_TOP) % 2 == 0 else C_PDIM
            put(r, c, lc, lco)

        put(r, fold_c, '/', C_EDGE)

        for c in range(fold_c + 1, SPINE):
            put(r, c, '.', C_UNDER)

    hline(ROWS - 4, 1, COLS - 2, '-', C_BORD)
    epub_lbl = "-[ ePUB ]-"
    textrow(ROWS - 3, (COLS - len(epub_lbl)) // 2, epub_lbl, C_LABEL)

    if tags:
        tag_str = "  ".join(t.upper()[:5] for t in tags[:5])[:COLS - 2]
        textrow(ROWS - 2, max(0, (COLS - len(tag_str)) // 2), tag_str, C_TAGS)

    img  = Image.new("RGB", (IW, IH), _INK)
    draw = ImageDraw.Draw(img)
    for r in range(ROWS):
        y = r * CH
        for c in range(COLS):
            ch = chars[r][c]
            if ch != ' ':
                draw.text((c * CW, y), ch, font=fn, fill=colors[r][c])

    return img


_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _fit_font(draw, text, target_w, target_h=10 ** 6, bold=True,
              max_size=240, min_size=8):
    lo, hi, best = min_size, max_size, _font(min_size, bold)
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _font(mid, bold)
        w, h = _text_size(draw, text, f)
        if w <= target_w and h <= target_h:
            best, lo = f, mid + 1
        else:
            hi = mid - 1
    return best


def _roman(n):
    if not n or n < 1:
        return ""
    vals = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I"))
    out = ""
    for v, s in vals:
        while n >= v:
            out += s; n -= v
    return out


_SCRIPT_FILES = ["Gabriola.ttf", "VIVALDII.TTF", "FRSCRIPT.TTF",
                 "LCALLIG.TTF", "SCRIPTBL.TTF", "BRUSHSCI.TTF"]
_RANSOM_FILES = ["impact.ttf", "STENCIL.TTF", "BOOKOSB.TTF", "timesbd.ttf",
                 "georgiab.ttf", "courbd.ttf", "comicbd.ttf", "PLAYBILL.TTF",
                 "FORTE.TTF", "COLONNA.TTF", "ONYX.TTF", "arialbd.ttf",
                 "verdanab.ttf", "consolab.ttf", "trebucbd.ttf"]
_FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/Library/Fonts"),
              Path("/usr/share/fonts")]


def _named(files, size):
    for name in files:
        for dd in _FONT_DIRS:
            p = dd / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    pass
    return None


def _pool(files):
    out = []
    for name in files:
        for dd in _FONT_DIRS:
            if (dd / name).exists():
                out.append(str(dd / name)); break
    return out


def _script(size):
    return _named(_SCRIPT_FILES, size) or _serif(size, italic=True)


def _script_reflection(d, img, word, cx, cy, width, max_h, fill):
    lo, hi, best = 18, 200, 18
    while lo <= hi:
        mid = (lo + hi) // 2
        l, t, r, b = d.textbbox((0, 0), word, font=_script(mid))
        if (r - l) <= width and (b - t) <= max_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    f = _script(best)
    l, t, r, b = d.textbbox((0, 0), word, font=f)
    w, h = max(1, r - l), max(1, b - t)
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((-l, -t), word, font=f, fill=fill)
    tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
    img.paste(tile, (int(cx - w / 2), int(cy - h / 2)), tile)


def _ransom_tile(ch, font, mode):
    tmp = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    l, t, r, b = tmp.textbbox((0, 0), ch, font=font)
    gw, gh = max(1, r - l), max(1, b - t)
    px, py = max(3, gh // 7), max(2, gh // 10)
    W, H = gw + 2 * px, gh + 2 * py
    tile = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(tile)
    if mode == 1:
        dd.rectangle([0, 0, W - 1, H - 1], fill=_INK)
        dd.text((px - l, py - t), ch, font=font, fill=_PAPER)
    elif mode == 2:
        dd.rectangle([0, 0, W - 1, H - 1], fill=_PAPER, outline=_INK, width=2)
        dd.text((px - l, py - t), ch, font=font, fill=_INK)
    else:
        dd.text((px - l, py - t), ch, font=font, fill=_INK)
    return tile


def _has_glyph(font, ch):
    if ch.isspace():
        return True
    try:
        mask = font.getmask(ch)
        return mask.getbbox() is not None
    except Exception:
        return False


def _ransom_word(d, img, word, cx, midline, width, max_h, seed, pool):
    n = len(word)

    def build(base):
        rng, tiles = random.Random(seed), []
        for ch in word:
            sz = max(10, int(base * rng.uniform(0.80, 1.22)))
            cc = ch.upper() if rng.random() < 0.6 else ch.lower()
            font = None
            if pool:
                order = list(range(len(pool)))
                rng.shuffle(order)
                for i in order:
                    try:
                        cand = ImageFont.truetype(pool[i], sz)
                    except Exception:
                        continue
                    if _has_glyph(cand, cc):
                        font = cand
                        break
                if font is None:
                    cc = ch.upper()
                    for i in order:
                        try:
                            cand = ImageFont.truetype(pool[i], sz)
                        except Exception:
                            continue
                        if _has_glyph(cand, cc):
                            font = cand
                            break
            else:
                font = _serif(sz, bold=True) if rng.random() < .5 else _font(sz, True)
            if font is None:
                font = _serif(sz, bold=True)
                if not _has_glyph(font, cc):
                    cc = ch.upper()
            mode = rng.choices([0, 1, 2], weights=[5, 3, 2])[0]
            ang  = rng.uniform(-7, 7)
            dy   = rng.uniform(-0.09, 0.09) * base
            tiles.append((_ransom_tile(cc, font, mode).rotate(
                ang, expand=True, resample=Image.BICUBIC), dy))
        track = max(2, int(base * 0.06))
        total = sum(t.width for t, _ in tiles) + track * (n - 1)
        tall  = max(t.height for t, _ in tiles)
        return tiles, total, tall, track

    lo, hi, best = 16, 150, 16
    while lo <= hi:
        mid = (lo + hi) // 2
        _, total, tall, _ = build(mid)
        if total <= width and tall <= max_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    tiles, total, _, track = build(best)
    penx = cx - total / 2
    for tile, dy in tiles:
        img.paste(tile, (int(penx), int(midline - tile.height / 2 + dy)), tile)
        penx += tile.width + track


def _year_staircase(d, year, cx, top, width, height, fill):
    a, b = year[:2], year[2:]
    lo, hi, best = 20, 240, 20
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _times(mid)
        wa, wb = d.textlength(a, font=f), d.textlength(b, font=f)
        l, t, r, bb = d.textbbox((0, 0), "00", font=f)
        if max(wa, wb) <= width * 0.62 and (bb - t) <= height * 0.60:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    f = _times(best)
    wa, wb = d.textlength(a, font=f), d.textlength(b, font=f)
    l, t, r, bb = d.textbbox((0, 0), "00", font=f); hh = bb - t
    dx, dy = best * 0.50, best * 0.55
    total_w = max(wa, dx + wb)
    total_h = hh + dy
    x0 = cx - total_w / 2
    y0 = top + (height - total_h) / 2
    d.text((x0, y0), a, font=f, fill=fill, anchor="lt")
    d.text((x0 + dx, y0 + dy), b, font=f, fill=fill, anchor="lt")
    d.line([x0 + wa - best * 0.10, y0 + hh * 0.5,
            x0 + dx + best * 0.10, y0 + dy + hh * 0.5], fill=fill, width=1)


def _make_broadsheet_cover(tags, title, seed):
    img = Image.new("RGB", (IW, IH), _PAPER)
    d   = ImageDraw.Draw(img)
    cx  = IW // 2

    month = next((m.upper() for m in _MONTHS
                  if re.search(r'\b' + m[:3], title or '', re.I)), None)
    mo_n  = next((i + 1 for i, m in enumerate(_MONTHS)
                  if re.search(r'\b' + m[:3], title or '', re.I)), 0)
    ym    = re.search(r'(?:19|20)\d{2}', title or '')
    year  = ym.group(0) if ym else None
    yr_n  = int(year) if year else 0

    M = 13
    d.rectangle([M, M, IW - M - 1, IH - M - 1], outline=_INK, width=3)
    d.rectangle([M + 5, M + 5, IW - M - 6, IH - M - 6], outline=_INK, width=1)
    il, ir = M + 14, IW - M - 14
    iw = ir - il
    y  = M + 16

    est = "ESTABLISHED " + (_roman(2023) or "MMXXIII")
    kf  = _serif(7, italic=True)
    _spaced(d, cx, y, est, kf, _DIM, 2); y += 12

    name = "The Voice Express"
    nf   = _fit_spaced(d, name, iw, 1, serif=True, bold=True, max_size=30)
    nh   = _spaced(d, cx, y, name, nf, _INK, 1); y += nh + 7

    d.line([il, y, ir, y], fill=_INK, width=2); y += 3
    d.line([il, y, ir, y], fill=_INK, width=1)
    vol  = "VOL. %s" % (_roman(max(1, yr_n - 2022)) or "I")
    no   = "NO. %d" % (mo_n or 1)
    sf   = _serif(8)
    d.text((il, y + 4), vol, font=sf, fill=_DIM)
    nw, _ = _text_size(d, no, sf)
    d.text((ir - nw, y + 4), no, font=sf, fill=_DIM)
    mid  = "MONTHLY BROADSHEET"
    _spaced(d, cx, y + 4, mid, _serif(7), _BODY, 2)
    y += 18
    d.line([il, y, ir, y], fill=_INK, width=1); y += 6

    foot = IH - M - 30

    if year and month:
        body = foot - y
        yz_h, mz_h, gap = int(body * 0.40), int(body * 0.34), int(body * 0.04)
        top = y + (body - (yz_h + gap + mz_h)) // 2

        _year_staircase(d, year, cx, top, iw, yz_h, (206, 206, 206))

        ry = top + yz_h + gap // 2
        d.line([cx - 26, ry, cx + 26, ry], fill=_INK, width=1)

        mz_top = top + yz_h + gap
        ransom_mid = mz_top + int(mz_h * 0.30)
        _ransom_word(d, img, month.upper(), cx, ransom_mid, iw - 6,
                     int(mz_h * 0.46), seed, _pool(_RANSOM_FILES))
        _script_reflection(d, img, month.title(), cx - 12,
                           ransom_mid + int(mz_h * 0.44), iw - 2,
                           int(mz_h * 0.40), (205, 205, 205))
    else:
        big = (re.sub(r'(?i)^the voice express\W*', '', title or '').strip()
               or "BROADSHEET").upper()[:11]
        region = foot - y
        bf = _fit_spaced(d, big, iw, 2, serif=True, bold=True, max_size=120)
        _, bh = _text_size(d, big, bf)
        _spaced(d, cx, y + (region - bh) // 2, big, bf, _INK, 2)

    by = IH - M - 24
    d.line([il, by, ir, by], fill=_INK, width=1)
    lbl = "* GATHERED EDITION *"
    _spaced(d, cx, by + 6, lbl, _serif(8), _DIM, 2)
    return img


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if not cur or _text_size(draw, t, font)[0] <= width:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_wrap(draw, text, width, max_lines, bold=True, max_size=64, min_size=9,
              serif=False):
    load = (lambda s: _serif(s, bold)) if serif else (lambda s: _font(s, bold))
    lo, hi = min_size, max_size
    f0 = load(min_size)
    best = (f0, _wrap(draw, text, f0, width))
    while lo <= hi:
        mid = (lo + hi) // 2
        f = load(mid)
        ls = _wrap(draw, text, f, width)
        if len(ls) <= max_lines and all(_text_size(draw, l, f)[0] <= width for l in ls):
            best, lo = (f, ls), mid + 1
        else:
            hi = mid - 1
    return best


def _frame(d, M=13):
    d.rectangle([M, M, IW - M - 1, IH - M - 1], outline=_INK, width=3)
    d.rectangle([M + 5, M + 5, IW - M - 6, IH - M - 6], outline=_INK, width=1)


def _masthead(d, y, kicker, il, ir, iw):
    head = "THE VOICE EXPRESS"
    hf = _fit_font(d, head, iw, bold=True, max_size=16)
    hw, hh = _text_size(d, head, hf)
    d.text(((IW - hw) // 2, y), head, font=hf, fill=_INK); y += hh + 5
    d.line([il, y, ir, y], fill=_INK, width=2); y += 3
    kf = _font(9, bold=True); kw, kh = _text_size(d, kicker, kf)
    d.text(((IW - kw) // 2, y), kicker, font=kf, fill=_DIM); y += kh + 4
    d.line([il, y, ir, y], fill=_INK, width=1)
    return y + 14


def _serif_masthead(d, y, kicker, il, ir, iw):
    cx = (il + ir) // 2
    name = "The Voice Express"
    nf = _fit_spaced(d, name, iw, 1, serif=True, bold=True, max_size=22)
    nh = _spaced(d, cx, y, name, nf, _INK, 1); y += nh + 5
    d.line([il, y, ir, y], fill=_INK, width=2); y += 2
    d.line([il, y, ir, y], fill=_INK, width=1); y += 4
    _spaced(d, cx, y, kicker, _serif(8), _DIM, 3); y += 11
    d.line([il, y, ir, y], fill=_INK, width=1)
    return y + 10


def _make_gazette_cover(tags, title, seed, article_images=None):
    rng = random.Random(seed)
    img = Image.new("RGB", (IW, IH), _PAPER)
    d = ImageDraw.Draw(img)
    M = 13; _frame(d, M)
    il, ir = M + 14, IW - M - 14; iw = ir - il
    y = _serif_masthead(d, M + 16, "GAZETTE · SINGLE SHEET", il, ir, iw)

    plate = None
    for u in (article_images or []):
        p = _resolve_img_path(u)
        if p and p.exists():
            try:
                plate = Image.open(p).convert("RGB"); break
            except Exception:
                plate = None
    if plate is not None:
        PH = 150
        fit = ImageOps.fit(plate, (iw, PH), method=Image.LANCZOS)
        img.paste(fit, (il, y))
        d.rectangle([il - 1, y - 1, ir, y + PH], outline=_INK, width=2)
        y += PH + 9

    title = (title or "Untitled").strip()
    tf, lines = _fit_wrap(d, title.upper(), iw, (2 if plate is not None else 3),
                          bold=True, serif=True,
                          max_size=(22 if plate is not None else 27))
    cxp = (il + ir) // 2
    lh = _text_size(d, "Ag", tf)[1] + 4
    for ln in lines:
        w, _ = _text_size(d, ln, tf)
        d.text((cxp - w // 2, y), ln, font=tf, fill=_INK); y += lh
    y += 5; d.line([il, y, ir, y], fill=_DIM, width=1); y += 11

    cap = (re.sub(r'[^A-Za-z]', '', title)[:1] or "V").upper()
    cf = _serif(54, bold=True); cw, _ = _text_size(d, cap, cf)
    d.text((il, y - 6), cap, font=cf, fill=_INK)

    ly, row = y + 2, 0
    if plate is None:
        band_top = y + 2
        band_h = (IH - M - 30) - band_top
        if band_h > 40:
            try:
                import math as _m
                art = Image.new("RGB", (iw, band_h), _PAPER)
                ad = ImageDraw.Draw(art)
                f = rng.uniform(0.010, 0.024); ph = rng.uniform(0, 6.28)
                for _ in range(max(400, iw * band_h // 90)):
                    x = rng.uniform(0, iw); yy = rng.uniform(0, band_h)
                    ang = (_m.sin(x * f + ph) + _m.cos(yy * f - ph)) * _m.pi
                    ln = rng.uniform(4, 11)
                    ad.line([(x, yy), (x + ln * _m.cos(ang), yy + ln * _m.sin(ang))],
                            fill=_INK, width=1)
                img.paste(art, (il, band_top))
                d.rectangle([il - 1, band_top - 1, ir, band_top + band_h], outline=_INK, width=1)
                d.rectangle([il, band_top, il + cw + 6, band_top + 46], fill=_PAPER)
                d.text((il, band_top - 4), cap, font=cf, fill=_INK)
                ly = IH
            except Exception:
                ly = y + 2
    while ly < IH - M - 30:
        x0 = il + cw + 8 if row < 3 else il
        short = (row % 6 == 5)
        x1 = ir - (rng.randint(60, 120) if short else rng.randint(0, 30))
        if x1 > x0:
            d.line([x0, ly, x1, ly], fill=_RULE, width=2)
        ly += 9; row += 1

    by = IH - M - 21
    d.line([il, by, ir, by], fill=_INK, width=1)
    _spaced(d, cxp, by + 5, "SINGLE EDITION", _serif(8), _DIM, 2)
    return img


def _make_booklet_cover(tags, title, seed):
    img = Image.new("RGB", (IW, IH), _PAPER)
    d = ImageDraw.Draw(img)
    M = 13; _frame(d, M)
    il, ir = M + 14, IW - M - 14; iw = ir - il
    y = _masthead(d, M + 16, "COLUMN BOOKLET", il, ir, iw)

    BW, BH = 150, 150
    bx, by0 = (IW - BW) // 2 - 10, y + 6
    for i in range(3, -1, -1):
        ox, oy = bx + i * 8, by0 + i * 8
        d.rectangle([ox, oy, ox + BW, oy + BH], fill=_PAPER, outline=_INK, width=2)
        d.line([ox + 14, oy, ox + 14, oy + BH], fill=_INK, width=1)
        for k in range(1, 4):
            sy = oy + BH * k // 4
            d.line([ox + 11, sy - 4, ox + 11, sy + 4], fill=_INK, width=2)
        if i == 0:
            tf, lines = _fit_wrap(d, (title or "Column").upper(), BW - 34, 3,
                                  bold=True, max_size=20)
            ty = oy + 22
            for ln in lines:
                _, hh = _text_size(d, ln, tf)
                d.text((ox + 24, ty), ln, font=tf, fill=_INK); ty += hh + 4
            for r in range(3):
                ry = oy + BH - 40 + r * 9
                d.line([ox + 24, ry, ox + BW - 14, ry], fill=_RULE, width=2)

    by = IH - M - 21
    d.line([il, by, ir, by], fill=_INK, width=1)
    lbl = "SADDLE-STITCHED"
    lf = _font(8, bold=True); lw, _ = _text_size(d, lbl, lf)
    d.text(((IW - lw) // 2, by + 5), lbl, font=lf, fill=_DIM)
    return img


def _make_compilation_cover(article_images, tags, title, seed):
    rng = random.Random(seed)
    img = Image.new("RGB", (IW, IH), _PAPER)

    paths = [p for p in (_resolve_img_path(u) for u in (article_images or []))
             if p and p.exists()]

    circles, RMIN, RMAX = [], 15, 58
    for _ in range(1600):
        cx, cy = rng.randint(2, IW - 2), rng.randint(2, IH - 2)
        r = min(RMAX, cx, cy, IW - cx, IH - cy)
        for ox, oy, orr in circles:
            r = min(r, math.hypot(cx - ox, cy - oy) - orr)
        if r >= RMIN:
            circles.append((cx, cy, int(r)))

    for i, (cx, cy, r) in enumerate(circles):
        dia = r * 2
        disc = None
        if paths:
            try:
                disc = ImageOps.fit(Image.open(paths[i % len(paths)]).convert("RGB"),
                                    (dia, dia), method=Image.LANCZOS)
            except Exception:
                disc = None
        if disc is None:
            g = rng.randint(45, 215)
            disc = Image.new("RGB", (dia, dia), (g, g, g))
        mask = Image.new("L", (dia, dia), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, dia - 1, dia - 1], fill=255)
        img.paste(disc, (cx - r, cy - r), mask)

    d = ImageDraw.Draw(img)
    for cx, cy, r in circles:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_INK, width=2)

    LR, mx, my = 36, IW // 2, IH // 2
    d.ellipse([mx - LR, my - LR, mx + LR, my + LR], fill=_PAPER, outline=_INK, width=3)
    placed = False
    try:
        if _LOGO_PNG.exists():
            logo = Image.open(_LOGO_PNG).convert("RGBA")
            logo.thumbnail((int(LR * 1.4), int(LR * 1.4)))
            img.paste(logo, (mx - logo.width // 2, my - logo.height // 2), logo)
            placed = True
    except Exception:
        pass
    if not placed:
        f = _font(26, bold=True); tw, th = _text_size(d, "VE", f)
        d.text((mx - tw // 2, my - th // 2), "VE", font=f, fill=_INK)

    t = (title or "").lower()
    period = ("WEEKLY" if "week" in t else "MONTHLY" if "month" in t else
              "YEARLY" if "year" in t else "ALL-TIME" if "all" in t else "")
    _frame(d, 8)
    if period:
        bw, bh = 158, 26
        bx2, by2 = (IW - bw) // 2, IH - 12 - bh
        d.rectangle([bx2, by2, bx2 + bw, by2 + bh], fill=_PAPER, outline=_INK, width=2)
        lbl = f"{period} COMPILATION"
        lf = _fit_font(d, lbl, bw - 14, bold=True, max_size=12)
        lw, lh = _text_size(d, lbl, lf)
        d.text(((IW - lw) // 2, by2 + (bh - lh) // 2 - 1), lbl, font=lf, fill=_INK)
    return img


def _spiral_pts(x0, y0, x1, y1, sp, flip=False):
    pts = [(x0, y0)]
    while (x1 - x0) > sp and (y1 - y0) > sp:
        if not flip:
            pts += [(x1, y0), (x1, y1), (x0, y1)]; y0 += sp; pts.append((x0, y0))
        else:
            pts += [(x0, y1), (x1, y1), (x1, y0)]; y0 += sp; pts.append((x1, y0))
        x0 += sp; x1 -= sp; y1 -= sp
    return pts

def _make_spiral_icon(tags, title, seed):
    img = Image.new("RGB", (IW, IH), _PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, IW - 7, IH - 7], outline=_INK, width=3)
    cols, rows = 3, 4
    cw = (IW - 28) / cols; ch = (IH - 28) / rows
    sp = max(6, int(min(cw, ch) / 6))
    for r in range(rows):
        for c in range(cols):
            x0 = 14 + c * cw + 5; y0 = 14 + r * ch + 5
            x1 = 14 + (c + 1) * cw - 5; y1 = 14 + (r + 1) * ch - 5
            d.line(_spiral_pts(x0, y0, x1, y1, sp),
                   fill=_INK, width=2, joint="curve")
    cx, cy, R = IW // 2, IH // 2, 66
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=_PAPER, outline=_INK, width=3)
    placed = False
    try:
        if _LOGO_PNG.exists():
            logo = Image.open(_LOGO_PNG).convert("RGBA")
            lw = int(R * 1.55); logo.thumbnail((lw, lw))
            img.paste(logo, (cx - logo.width // 2, cy - logo.height // 2), logo)
            placed = True
    except Exception:
        pass
    if not placed:
        f = _font(40, bold=True); tw, th = _text_size(d, "VE", f)
        d.text((cx - tw / 2, cy - th / 2 - 4), "VE", fill=_INK, font=f)
    return img

def _period_save(img, key):
    _UPLOADS.mkdir(parents=True, exist_ok=True)
    p = _UPLOADS / f"_cover_{key}.png"
    _atomic_save_img(img, p)
    return f"/static/uploads/_cover_{key}.png"

def flow_field_png(seed, label="", W=900, H=1200):
    if not _PIL: return None
    import math as _m
    key = hashlib.md5(f"flow|{seed}|{label}|{W}x{H}".encode()).hexdigest()[:12]
    cached = _UPLOADS / f"_cover_{key}.png"
    if _valid_cache(cached): return f"/static/uploads/_cover_{key}.png"
    rng = random.Random(seed)
    img = Image.new("RGB", (W, H), _PAPER); d = ImageDraw.Draw(img)
    f = rng.uniform(0.004, 0.009); ph = rng.uniform(0, 6.28)
    for _ in range(2600):
        x = rng.uniform(0, W); y = rng.uniform(0, H)
        a = (_m.sin(x * f + ph) + _m.cos(y * f - ph)) * _m.pi
        ln = rng.uniform(10, 22)
        d.line([(x, y), (x + ln * _m.cos(a), y + ln * _m.sin(a))], fill=_INK, width=1)
    d.rectangle([8, 8, W - 9, H - 9], outline=_INK, width=3)
    return _period_save(img, key)

def voronoi_png(seed, label="", W=900, H=1200, sites=26):
    if not _PIL: return None
    key = hashlib.md5(f"voro|{seed}|{label}|{W}x{H}".encode()).hexdigest()[:12]
    cached = _UPLOADS / f"_cover_{key}.png"
    if _valid_cache(cached): return f"/static/uploads/_cover_{key}.png"
    rng = random.Random(seed)
    pts = [(rng.randint(0, W), rng.randint(0, H)) for _ in range(sites)]
    img = Image.new("L", (W, H), 244)
    step = 3
    def nearest(x, y):
        best = 0; bd = 1e18
        for i, (sx, sy) in enumerate(pts):
            dd = (x - sx) ** 2 + (y - sy) ** 2
            if dd < bd: bd = dd; best = i
        return best
    grid = {}
    for gy in range(0, H, step):
        for gx in range(0, W, step):
            grid[(gx, gy)] = nearest(gx, gy)
    d = ImageDraw.Draw(img)
    for gy in range(0, H, step):
        for gx in range(0, W, step):
            me = grid[(gx, gy)]
            for nx, ny in ((gx + step, gy), (gx, gy + step)):
                if (nx, ny) in grid and grid[(nx, ny)] != me:
                    d.line([(gx, gy), (nx, ny)], fill=20, width=2)
    for sx, sy in pts:
        d.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=20)
    img = img.convert("RGB"); d = ImageDraw.Draw(img)
    d.rectangle([8, 8, W - 9, H - 9], outline=_INK, width=3)
    return _period_save(img, key)

def spiral_text_icon(seed, phrases):
    phrases = [re.sub(r'\s+', ' ', (p or '')).strip() for p in (phrases or []) if (p or '').strip()]
    key = hashlib.md5(('spiral2|%d|%s' % (seed, '|'.join(phrases))[:300]).encode()).hexdigest()[:12]
    _UPLOADS.mkdir(parents=True, exist_ok=True)
    out = _UPLOADS / f'_icon_{key}.svg'
    if _valid_cache(out):
        return f'/static/uploads/_icon_{key}.svg'
    W = H = 620; M = 22; SP = 21
    x0, y0, x1, y1 = M, M, W - M, H - M
    pts = [(x0, y0)]
    while (x1 - x0) > SP and (y1 - y0) > SP:
        pts += [(x1, y0), (x1, y1), (x0, y1)]; y0 += SP; pts.append((x0, y0))
        x0 += SP; x1 -= SP; y1 -= SP
    d = 'M' + ' L'.join(f'{a:.0f},{b:.0f}' for a, b in pts)
    def esc(s): return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    glyph = '  ✦  '
    seq = glyph.join(esc(p) for p in phrases) if phrases else 'THE VOICE EXPRESS'
    text = ((seq + glyph) * 3)[:1500]
    logo = ''
    if _LOGO_PNG.exists():
        try:
            b64 = base64.b64encode(_LOGO_PNG.read_bytes()).decode()
            logo = (f'<circle cx="{W//2}" cy="{H//2}" r="78" fill="#f4efe2" stroke="#15110c" stroke-width="3"/>'
                    f'<image x="{W//2-58}" y="{H//2-58}" width="116" height="116" preserveAspectRatio="xMidYMid meet" '
                    f'href="data:image/png;base64,{b64}"/>')
        except Exception:
            logo = ''
    if not logo:
        logo = (f'<circle cx="{W//2}" cy="{H//2}" r="70" fill="#15110c"/>'
                f'<text x="{W//2}" y="{H//2+14}" text-anchor="middle" font-size="44" font-weight="900" fill="#f4efe2">VE</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="Georgia,serif"><rect width="{W}" height="{H}" fill="#f4efe2"/>'
           f'<path id="sp{key}" d="{d}" fill="none" stroke="#d2c9b4" stroke-width="0.5"/>'
           f'<text font-size="11.5" letter-spacing="0.5" fill="#15110c">'
           f'<textPath href="#sp{key}">{text}</textPath></text>{logo}</svg>')
    _atomic_write_text(svg, out)
    return f'/static/uploads/_icon_{key}.svg'

def generate_icon(pub_type, tags, title="", seed=42, article_images=None):
    if not _PIL:
        return None

    tags  = [re.sub(r'[^\w\s]', '', t).strip() for t in (tags or []) if t and t.strip()]
    key   = _key(pub_type, tags, title, seed, article_images)
    cached = _UPLOADS / f"_icon_{key}.png"
    if _valid_cache(cached):
        return f"/static/uploads/_icon_{key}.png"

    try:
        if pub_type == "magazine_pdf":
            img = _make_pdf_icon(tags, title, seed)
        elif pub_type == "magazine_html":
            img = _make_emag_icon(tags, title, seed)
        elif pub_type in ("broadsheet", "newsletter"):
            img = _make_broadsheet_cover(tags, title, seed)
        elif pub_type == "gazette":
            img = _make_gazette_cover(tags, title, seed, article_images)
        elif pub_type == "booklet":
            img = _make_booklet_cover(tags, title, seed)
        elif pub_type == "compilation":
            img = _make_compilation_cover(article_images, tags, title, seed)
        elif pub_type == "spiral":
            img = _make_spiral_icon(tags, title, seed)
        elif pub_type == "epub":
            img = _make_epub_icon(title, tags, seed)
        else:
            img = _make_emag_icon(tags, title, seed)
        return _save(img, key) if img else None
    except Exception as e:
        print(f"[pub_icons] {pub_type}: {e}")
        return None
