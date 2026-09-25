#!/usr/bin/env python3
from __future__ import annotations
import re

_ROLE_BYLINE = {'photographer': 'Photos by', 'illustrator': 'Art by',
                'translator': 'Translation by', 'editor': 'Edited by',
                'as-told-to': 'As told to', 'reporting': 'Additional reporting by'}


def slugify(text: str) -> str:
    text = str(text).lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:80] or 'untitled'


def reading_time(content) -> int:
    words = len(re.sub(r'<[^>]+>', '', str(content or '')).split())
    return max(1, round(words / 200))


def unique_slug(db, base: str, exclude_id=None) -> str:
    slug, i = base, 1
    while True:
        q = ('SELECT id FROM articles WHERE slug=? AND id!=?' if exclude_id
             else 'SELECT id FROM articles WHERE slug=?')
        p = [slug, exclude_id] if exclude_id else [slug]
        if not db.execute(q, p).fetchone():
            return slug
        slug = f'{base}-{i}'; i += 1


def compose_byline(authors) -> str:
    if not authors:
        return ''
    def _join(names):
        names = [n for n in names if n]
        if not names: return ''
        if len(names) == 1: return names[0]
        return ', '.join(names[:-1]) + ' & ' + names[-1]
    groups, order = {}, []
    for a in authors:
        r = a.get('role') or 'author'
        if r not in groups: groups[r] = []; order.append(r)
        groups[r].append(a.get('name'))
    parts = []
    writers = (groups.pop('author', []) if 'author' in groups else []) + \
              (groups.pop('co-author', []) if 'co-author' in groups else [])
    if writers: parts.append(_join(writers))
    for r in order:
        if r in ('author', 'co-author') or r not in groups: continue
        parts.append(f"{_ROLE_BYLINE.get(r, r.title() + ' by')} {_join(groups[r])}")
    return ' - '.join(p for p in parts if p)
