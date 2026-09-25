import re

from ve import tags as _tags


class Invalid(ValueError):
    pass


class Missing(LookupError):
    pass


def slugify(text):
    text = str(text).lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:80] or 'untitled'


def list_tags(db):
    out = []
    for r in db.execute('SELECT * FROM tags ORDER BY name').fetchall():
        t = dict(r)
        t['article_count'] = _tags.usage_count(db, t['id'])
        out.append(t)
    return out


def create_tag(db, name, match='slug'):
    name = (name or '').strip()
    if not name:
        raise Invalid('Name required')
    base = slugify(name)
    if match == 'name':
        ex = db.execute('SELECT id,name,slug FROM tags WHERE name=? COLLATE NOCASE', [name]).fetchone()
        if ex:
            return dict(ex), False
        slug, i = base, 1
    else:
        ex = db.execute('SELECT id FROM tags WHERE slug=?', [base]).fetchone()
        if ex:
            return {'id': ex['id'], 'slug': base, 'name': name}, False
        slug, i = base, 1
    while db.execute('SELECT 1 FROM tags WHERE slug=?', [slug]).fetchone():
        slug = f'{base}-{i}'; i += 1
    db.execute('INSERT INTO tags (name,slug) VALUES (?,?)', [name, slug])
    tid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.commit()
    return {'id': tid, 'name': name, 'slug': slug}, True


def rename_tag(db, tid, name):
    name = (name or '').strip()
    if not name:
        raise Invalid('Name required')
    slug = slugify(name); n = 2
    while db.execute('SELECT 1 FROM tags WHERE slug=? AND id!=?', [slug, tid]).fetchone():
        slug = f'{slugify(name)}-{n}'; n += 1
    db.execute('UPDATE tags SET name=?,slug=? WHERE id=?', [name, slug, tid])
    db.commit()
    return {'id': tid, 'name': name, 'slug': slug}


def delete_tag(db, tid):
    db.execute('DELETE FROM article_tags WHERE tag_id=?', [tid])
    db.execute('DELETE FROM column_entry_tags WHERE tag_id=?', [tid])
    db.execute('DELETE FROM tags WHERE id=?', [tid])
    db.commit()


def merge_tag(db, tid, into):
    if not into or int(into) == tid:
        raise Invalid('Pick a different target tag')
    db.execute('UPDATE OR IGNORE article_tags SET tag_id=? WHERE tag_id=?', [into, tid])
    db.execute('DELETE FROM article_tags WHERE tag_id=?', [tid])
    _tags.remap_tag(db, tid, into)
    db.execute('DELETE FROM tags WHERE id=?', [tid])
    db.commit()
    return {'success': True, 'into': into}


def entry_dict(db, row, with_panels=True, with_names=False):
    d = dict(row)
    d['tag_ids'] = _tags.entry_tag_ids(db, d['id'])
    if with_names:
        d['tags'] = _tags.entry_tag_names(db, d['id'])
    if with_panels:
        d['panels'] = [dict(p) for p in db.execute(
            'SELECT * FROM column_panels WHERE entry_id=? ORDER BY sort_order, id', [d['id']]).fetchall()]
    return d


def list_entries(db, cid, only_published=False, with_panels=True, with_names=False):
    q = 'SELECT * FROM column_entries WHERE column_id=?'
    if only_published:
        q += " AND status='published'"
    q += ' ORDER BY entry_date DESC, sort_order'
    return [entry_dict(db, r, with_panels, with_names) for r in db.execute(q, [cid]).fetchall()]


def get_entry(db, eid, with_private=False, with_names=False, joined=True):
    if joined:
        cols = 'e.*, c.title AS column_title, c.slug AS column_slug, c.accent'
        if with_private:
            cols += ', c.is_private'
        row = db.execute(f'SELECT {cols} FROM column_entries e JOIN columns c ON c.id=e.column_id WHERE e.id=?',
                         [eid]).fetchone()
    else:
        row = db.execute('SELECT * FROM column_entries WHERE id=?', [eid]).fetchone()
    if not row:
        raise Missing('Not found')
    return entry_dict(db, row, True, with_names)


def save_panels(db, eid, panels):
    db.execute('DELETE FROM column_panels WHERE entry_id=?', [eid])
    for i, pn in enumerate(panels or []):
        db.execute('INSERT INTO column_panels (entry_id,sort_order,image,caption,text,span) VALUES (?,?,?,?,?,?)',
                   [eid, int(pn.get('sort_order', i) or i), pn.get('image', ''),
                    pn.get('caption', ''), pn.get('text', ''), pn.get('span', 'half')])


def create_entry(db, cid, data, now, normalize=None):
    if not db.execute('SELECT 1 FROM columns WHERE id=?', [cid]).fetchone():
        raise Missing('Column not found')
    body = data.get('body', '')
    if normalize:
        body = normalize(body)
    db.execute('''INSERT INTO column_entries (column_id,entry_date,title,subtitle,cover_image,
        body,layout,status,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''', [
        cid, (data.get('entry_date') or now[:10]), (data.get('title') or 'Untitled').strip(),
        data.get('subtitle', ''), data.get('cover_image', ''), body,
        data.get('layout', 'prose'), data.get('status', 'draft'),
        int(data.get('sort_order') or 0), now, now])
    eid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    save_panels(db, eid, data.get('panels'))
    if 'tag_ids' in data:
        _tags.set_entry_tags(db, eid, data.get('tag_ids'))
    db.commit()
    return eid


def update_entry(db, eid, data, now, normalize=None):
    ex = db.execute('SELECT * FROM column_entries WHERE id=?', [eid]).fetchone()
    if not ex:
        raise Missing('Not found')
    body = data.get('body', ex['body'] or '')
    if normalize:
        body = normalize(body)
    db.execute('''UPDATE column_entries SET entry_date=?,title=?,subtitle=?,cover_image=?,
        body=?,layout=?,status=?,sort_order=?,updated_at=? WHERE id=?''', [
        data.get('entry_date', ex['entry_date']), (data.get('title') or ex['title']).strip(),
        data.get('subtitle', ex['subtitle'] or ''), data.get('cover_image', ex['cover_image'] or ''),
        body, data.get('layout', ex['layout']), data.get('status', ex['status']),
        int(data.get('sort_order', ex['sort_order']) or 0), now, eid])
    if 'panels' in data:
        save_panels(db, eid, data.get('panels'))
    if 'tag_ids' in data:
        _tags.set_entry_tags(db, eid, data.get('tag_ids'))
    db.commit()


def delete_entry(db, eid, purge_children=False):
    if purge_children:
        db.execute('DELETE FROM column_panels WHERE entry_id=?', [eid])
        db.execute('DELETE FROM column_entry_tags WHERE entry_id=?', [eid])
    db.execute('DELETE FROM column_entries WHERE id=?', [eid])
    db.commit()
