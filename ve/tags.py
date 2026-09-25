def entry_tag_ids(db, entry_id):
    return [r[0] for r in db.execute(
        'SELECT tag_id FROM column_entry_tags WHERE entry_id=? ORDER BY tag_id', [entry_id]).fetchall()]


def entry_tag_names(db, entry_id):
    return [r[0] for r in db.execute(
        'SELECT t.name FROM column_entry_tags ct JOIN tags t ON t.id=ct.tag_id '
        'WHERE ct.entry_id=? ORDER BY t.name', [entry_id]).fetchall()]


def names_for_entries(db, entry_ids):
    ids = list(dict.fromkeys(int(i) for i in entry_ids))
    if not ids:
        return []
    marks = ','.join('?' * len(ids))
    rows = db.execute(
        'SELECT DISTINCT t.name FROM column_entry_tags ct JOIN tags t ON t.id=ct.tag_id '
        f'WHERE ct.entry_id IN ({marks}) ORDER BY t.name', ids).fetchall()
    return [r[0] for r in rows]


def set_entry_tags(db, entry_id, tag_ids):
    db.execute('DELETE FROM column_entry_tags WHERE entry_id=?', [entry_id])
    add_entry_tags(db, [entry_id], tag_ids)


def add_entry_tags(db, entry_ids, tag_ids):
    for tid in dict.fromkeys(int(t) for t in (tag_ids or [])):
        for eid in entry_ids:
            db.execute('INSERT OR IGNORE INTO column_entry_tags (entry_id,tag_id) '
                       'SELECT ?, id FROM tags WHERE id=?', [eid, tid])


def remap_tag(db, source_id, target_id):
    db.execute('UPDATE OR IGNORE column_entry_tags SET tag_id=? WHERE tag_id=?', [target_id, source_id])
    db.execute('DELETE FROM column_entry_tags WHERE tag_id=?', [source_id])


def usage_count(db, tag_id):
    articles = db.execute('SELECT COUNT(*) FROM article_tags WHERE tag_id=?', [tag_id]).fetchone()[0]
    entries = db.execute('SELECT COUNT(*) FROM column_entry_tags WHERE tag_id=?', [tag_id]).fetchone()[0]
    return articles + entries
