import sqlite3

from werkzeug.security import generate_password_hash

import ve_library


def connect(path, timeout=30):
    conn = sqlite3.connect(path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute(f'PRAGMA busy_timeout = {int(timeout * 1000)}')
    return conn


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS article_series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        cover_image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    for col, defn in [
        ('series_id',    'INTEGER REFERENCES article_series(id)'),
        ('series_order', 'INTEGER DEFAULT 0'),
    ]:
        try:
            db.execute(f'ALTER TABLE articles ADD COLUMN {col} {defn}')
        except Exception:
            pass
    db.execute('''CREATE TABLE IF NOT EXISTS puzzle_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        puzzle_type TEXT NOT NULL,
        puzzle_date TEXT NOT NULL,
        difficulty TEXT NOT NULL DEFAULT '',
        state TEXT,
        elapsed INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(puzzle_type, puzzle_date, difficulty)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS puzzle_word_cache (
        puzzle_date TEXT PRIMARY KEY,
        word_data TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        author_id INTEGER REFERENCES authors(id),
        role TEXT DEFAULT 'author',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS author_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        link_type TEXT DEFAULT 'other',
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    try:
        db.execute("ALTER TABLE authors ADD COLUMN author_type TEXT DEFAULT 'reporter'")
    except Exception:
        pass
    db.execute('''CREATE TABLE IF NOT EXISTS article_authors (
        article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        author_id   INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
        role        TEXT DEFAULT 'author',
        sort_order  INTEGER DEFAULT 0,
        PRIMARY KEY (article_id, author_id, role)
    )''')
    pk = [r[1] for r in sorted(db.execute('PRAGMA table_info(article_authors)').fetchall(),
                               key=lambda r: r[5]) if r[5]]
    if 'role' not in pk:
        # one person can hold several credits on a story (e.g. writer and photographer)
        db.execute('''CREATE TABLE article_authors_new (
            article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            author_id   INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
            role        TEXT NOT NULL DEFAULT 'author',
            sort_order  INTEGER DEFAULT 0,
            PRIMARY KEY (article_id, author_id, role)
        )''')
        db.execute('''INSERT OR IGNORE INTO article_authors_new (article_id, author_id, role, sort_order)
                      SELECT aa.article_id, aa.author_id, COALESCE(aa.role, 'author'), aa.sort_order
                      FROM article_authors aa
                      JOIN articles ar ON ar.id = aa.article_id
                      JOIN authors au ON au.id = aa.author_id''')
        db.execute('DROP TABLE article_authors')
        db.execute('ALTER TABLE article_authors_new RENAME TO article_authors')
    db.execute('''INSERT OR IGNORE INTO article_authors (article_id, author_id, role, sort_order)
                  SELECT id, author_id, 'author', 0 FROM articles
                  WHERE author_id IS NOT NULL AND id NOT IN (SELECT article_id FROM article_authors)''')
    db.commit()
    db.execute('''CREATE TABLE IF NOT EXISTS columns (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        slug        TEXT UNIQUE NOT NULL,
        subtitle    TEXT,
        description TEXT,
        cover_image TEXT,
        cadence     TEXT DEFAULT 'weekly',
        period_days INTEGER DEFAULT 7,
        accent      TEXT,
        status      TEXT DEFAULT 'draft',
        is_featured INTEGER DEFAULT 0,
        sort_order  INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS column_authors (
        column_id   INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
        author_id   INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
        role        TEXT DEFAULT 'author',
        sort_order  INTEGER DEFAULT 0,
        PRIMARY KEY (column_id, author_id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS column_entries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        column_id   INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
        entry_date  TEXT NOT NULL,
        title       TEXT NOT NULL,
        subtitle    TEXT,
        cover_image TEXT,
        body        TEXT,
        layout      TEXT DEFAULT 'prose',
        status      TEXT DEFAULT 'draft',
        sort_order  INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS column_panels (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id    INTEGER NOT NULL REFERENCES column_entries(id) ON DELETE CASCADE,
        sort_order  INTEGER DEFAULT 0,
        image       TEXT,
        caption     TEXT,
        text        TEXT,
        span        TEXT DEFAULT 'half'
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS column_entry_tags (
        entry_id    INTEGER NOT NULL REFERENCES column_entries(id) ON DELETE CASCADE,
        tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        PRIMARY KEY (entry_id, tag_id)
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_entries_column_date ON column_entries(column_id, entry_date)')
    try:
        db.execute('ALTER TABLE columns ADD COLUMN is_private INTEGER DEFAULT 0')
    except Exception:
        pass
    db.commit()
    try:
        db.execute('ALTER TABLE users ADD COLUMN email TEXT')
    except Exception:
        pass
    db.execute('''CREATE TABLE IF NOT EXISTS reading_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        read_count INTEGER DEFAULT 1,
        UNIQUE(user_id, article_id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS user_puzzle_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        puzzle_type TEXT NOT NULL,
        puzzle_date TEXT NOT NULL,
        difficulty TEXT DEFAULT '',
        elapsed INTEGER DEFAULT 0,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, puzzle_type, puzzle_date, difficulty)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS article_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id),
        display_name TEXT,
        action TEXT NOT NULL,
        language TEXT,
        edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS article_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id),
        display_name TEXT,
        message TEXT,
        snapshot TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    for _col, _def in [('translator_id','INTEGER REFERENCES users(id)'),('translator_name','TEXT')]:
        try: db.execute(f'ALTER TABLE translations ADD COLUMN {_col} {_def}')
        except Exception: pass
    db.execute('''CREATE TABLE IF NOT EXISTS corrections (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id    INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        title         TEXT NOT NULL,
        body          TEXT NOT NULL,
        severity      TEXT DEFAULT 'minor',
        published_by  INTEGER REFERENCES users(id),
        published_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS ip_geo_cache (
        ip TEXT PRIMARY KEY,
        country TEXT,
        country_code TEXT,
        city TEXT,
        lat REAL,
        lon REAL,
        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    try: db.execute('ALTER TABLE letters ADD COLUMN ip_address TEXT')
    except Exception: pass
    db.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_kind TEXT NOT NULL DEFAULT 'article',
        target_ref TEXT NOT NULL,
        article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
        display_name TEXT NOT NULL,
        content TEXT NOT NULL,
        ip_address TEXT,
        user_id INTEGER REFERENCES users(id),
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    _ccols = {r[1] for r in db.execute('PRAGMA table_info(comments)')}
    if 'target_ref' not in _ccols:
        db.execute('''CREATE TABLE comments__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_kind TEXT NOT NULL DEFAULT 'article',
            target_ref TEXT NOT NULL,
            article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
            display_name TEXT NOT NULL,
            content TEXT NOT NULL,
            ip_address TEXT,
            user_id INTEGER REFERENCES users(id),
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sheet_row INTEGER,
            username TEXT
        )''')
        _carry = [c for c in ('ip_address', 'user_id', 'status', 'created_at',
                              'sheet_row', 'username') if c in _ccols]
        db.execute(
            "INSERT INTO comments__new "
            "(id,target_kind,target_ref,article_id,display_name,content" +
            (',' + ','.join(_carry) if _carry else '') + ") "
            "SELECT id,'article',CAST(article_id AS TEXT),article_id,display_name,content" +
            (',' + ','.join(_carry) if _carry else '') + " FROM comments")
        db.execute('DROP TABLE comments')
        db.execute('ALTER TABLE comments__new RENAME TO comments')
        _ccols = {r[1] for r in db.execute('PRAGMA table_info(comments)')}
    try: db.execute('ALTER TABLE comments ADD COLUMN selected_text TEXT')
    except Exception: pass
    db.execute('CREATE INDEX IF NOT EXISTS idx_comments_target '
               'ON comments(target_kind, target_ref, status)')
    db.execute('''CREATE TABLE IF NOT EXISTS letters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        guest_name TEXT,
        subject TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    try: db.execute("ALTER TABLE letters ADD COLUMN source TEXT DEFAULT 'site'")
    except Exception: pass
    try: db.execute('ALTER TABLE letters ADD COLUMN sheet_row INTEGER')
    except Exception: pass
    db.execute('''CREATE TABLE IF NOT EXISTS article_likes (
        article_id INTEGER PRIMARY KEY,
        count INTEGER DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    _lcols = {r[1] for r in db.execute('PRAGMA table_info(article_likes)')}
    if 'target_ref' not in _lcols:
        db.execute('''CREATE TABLE article_likes__new (
            target_kind TEXT NOT NULL DEFAULT 'article',
            target_ref TEXT NOT NULL,
            article_id INTEGER,
            count INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (target_kind, target_ref)
        )''')
        db.execute("INSERT INTO article_likes__new "
                   "(target_kind,target_ref,article_id,count,updated_at) "
                   "SELECT 'article',CAST(article_id AS TEXT),article_id,count,updated_at "
                   "FROM article_likes")
        db.execute('DROP TABLE article_likes')
        db.execute('ALTER TABLE article_likes__new RENAME TO article_likes')
    db.execute('''CREATE TABLE IF NOT EXISTS letter_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        letter_id INTEGER NOT NULL REFERENCES letters(id) ON DELETE CASCADE,
        sender TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS newsletter_subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        ip_address TEXT,
        subscribed_at TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS site_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_name TEXT,
        body TEXT NOT NULL,
        about TEXT,
        ip_address TEXT,
        created_at TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS site_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,
        title TEXT,
        file TEXT,
        type TEXT,
        amount REAL,
        currency TEXT,
        via TEXT,
        username TEXT,
        ip_address TEXT,
        ref TEXT,
        occurred_at TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS newsstand_accounts (
        username TEXT PRIMARY KEY,
        library TEXT DEFAULT '[]',
        hearts INTEGER DEFAULT 0,
        created_at TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS sheet_annotations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER REFERENCES articles(id),
        selected_text TEXT,
        note TEXT,
        created_at TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    for _c, _d in (('target_kind', "TEXT DEFAULT 'article'"), ('target_ref', 'TEXT'),
                   ('username', 'TEXT')):
        try: db.execute(f'ALTER TABLE sheet_annotations ADD COLUMN {_c} {_d}')
        except Exception: pass
    db.execute('''CREATE TABLE IF NOT EXISTS pdf_enhancements (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type   TEXT NOT NULL,
        target_key    TEXT NOT NULL,
        toc           INTEGER DEFAULT 0,
        page_numbers  INTEGER DEFAULT 1,
        cover_note    TEXT DEFAULT '',
        accent        TEXT DEFAULT '',
        extra_css     TEXT DEFAULT '',
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(target_type, target_key)
    )''')
    if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        db.execute('INSERT INTO users (username,password_hash,role) VALUES (?,?,?)',
            ['tve', generate_password_hash('h3ll0w0rld@th3v0ic33xpr3ss'), 'admin'])

    old_admin = db.execute("SELECT id FROM users WHERE username='thevoiceexpress' AND role='admin'").fetchone()
    if old_admin:
        db.execute("UPDATE users SET username='tve', password_hash=? WHERE id=?",
                   [generate_password_hash('h3ll0w0rld@th3v0ic33xpr3ss'), old_admin[0]])

    mouli_author = db.execute("SELECT id FROM authors WHERE name='Mouli Sharma' LIMIT 1").fetchone()
    if mouli_author:
        exists = db.execute("SELECT 1 FROM users WHERE username='mouli'").fetchone()
        if not exists:
            db.execute('INSERT INTO users (username,password_hash,role,author_id) VALUES (?,?,?,?)',
                ['mouli', generate_password_hash('tve_mouli2024'), 'editor', mouli_author[0]])
    db.commit()

    db.execute('''CREATE TABLE IF NOT EXISTS site_pages (
        slug        TEXT PRIMARY KEY,
        title       TEXT NOT NULL,
        content     TEXT NOT NULL DEFAULT '',
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    _ABOUT_DEFAULT = """<p>Independent news publication based in New Delhi, India. Formerly student-run.</p>
<p><em>The Voice Express</em> was founded in 2022 as an Intro to New Media project that refused to stay one. We started because none of the seven journalism departments in the University of Delhi had their own publication. We stayed because the absence we were trying to fill turned out to be larger than we thought.</p>
<p>We cover the stories that fall through institutional cracks — labour, state violence, student life, protest, culture, and whatever else needs to be said. We do not take advertising. We do not answer to institutions.</p>
<p>After all, the truth takes time.</p>
<h2>Our Team</h2>
<p><strong>Mouli</strong> — Chief Editor, Journalist &amp; Creator of the Magazine<br/><strong>Mitali (Aayat Mahnoor)</strong> — Web Developer &amp; Website Maintainer (<a href="mailto:aayatmahnoor@proton.me">aayatmahnoor@proton.me</a>)</p>
<h2>Contact</h2>
<p>Email: <a href="mailto:thevoiceexpress@proton.me">thevoiceexpress@proton.me</a><br/>Read the magazine: <a href="https://emag.thevoiceexpress.in">emag.thevoiceexpress.in</a><br/>The Newsstand: <a href="https://newsstand.thevoiceexpress.in">newsstand.thevoiceexpress.in</a></p>"""
    _SUBMISSIONS_DEFAULT = """<p>We accept submissions all year round. Carefully read the classification criteria &amp; additional guidelines of all categories to ensure that your submission is relevant, &amp; please limit submissions to one at a time <em>per category</em>. All submissions are to be made via e-mail as a .docx (Word file) attachment to <a href="mailto:thevoiceexpress@proton.me">thevoiceexpress@proton.me</a> with ‘[INSERT CATEGORY] SUBMISSION’ as the subject. Please include a brief third-person bio (authors/whistleblowers concerned about identity may request anonymity).</p>
<h2>Guidelines</h2>
<h3>Formatting</h3>
<p>Standard margins, Times New Roman 12pt, double-spaced. The document should contain in order: 1) A title page (title, author(s), completion date, brief description). 2) The article, centred bold title. 3) References with working URLs. 4) Appendix of documentary or photographic material.</p>
<h2>Categories</h2>
<ol>
<li><strong>Whistleblower</strong>: Verified submissions go directly into our News Feed. If it should be out there, we’ll publish it.</li>
<li><strong>Opinion</strong>: Logical substantiation required. 1,000–2,000 words.</li>
<li><strong>Editorials</strong>: Essays 1,500–5,000 words. Experimental writing encouraged. No fiction or poetry.</li>
<li><strong>Pictured</strong>: Photo stories. Minimum 3 photographs, at least 1080px on shortest side. Accompanying text optional, max 500 words.</li>
</ol>"""
    for slug, title, content in [
        ('about',       'About',               _ABOUT_DEFAULT),
        ('submissions', 'Submission Guidelines', _SUBMISSIONS_DEFAULT),
    ]:
        if not db.execute('SELECT 1 FROM site_pages WHERE slug=?', [slug]).fetchone():
            db.execute('INSERT INTO site_pages (slug,title,content) VALUES (?,?,?)',
                       [slug, title, content])
    db.execute('''CREATE TABLE IF NOT EXISTS sections (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE NOT NULL,
        slug        TEXT UNIQUE NOT NULL,
        description TEXT,
        sort_order  INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    try:
        db.execute('ALTER TABLE articles ADD COLUMN section_id INTEGER REFERENCES sections(id)')
    except Exception:
        pass
    _SECTIONS_SEED = [
        ('Labour',        'labour',        'Worker rights, unions, and labour movements',    1),
        ('Politics',      'politics',      'Governance, elections, and political movements', 2),
        ('Gender',        'gender',        'Gender rights, feminism, and equality',          3),
        ('Education',     'education',     'Universities, students, and academic freedom',   4),
        ('International', 'international', 'Global affairs and international solidarity',    5),
        ('Culture',       'culture',       'Arts, film, literature, and social life',        6),
        ('Media',         'media',         'Press freedom and journalism',                   7),
        ('Features',      'features',      'Long reads, investigations, and analysis',       8),
    ]
    for _nm, _sl, _ds, _so in _SECTIONS_SEED:
        try:
            db.execute('INSERT OR IGNORE INTO sections (name,slug,description,sort_order) VALUES (?,?,?,?)',
                       [_nm, _sl, _ds, _so])
        except Exception:
            pass
    db.commit()

    _sid = {r[0]: r[1] for r in db.execute('SELECT slug,id FROM sections').fetchall()}
    _SECTION_RULES = [
        ('labour',        ['maruti', 'equal pay', 'manesar', 'labour union', 'labor union',
                           'workers establish', 'aane do dilli', 'suzuki', 'factory']),
        ('international', ['palestine', 'gaza', 'west bank', 'rcep', 'bilateral invest',
                           'occupied territ']),
        ('gender',        ['women\'s day', 'aurat ke haq', 'aurat', 'औरत',
                           'head of my household', 'sanitary pad']),
        ('media',         ['deepankar', "editor's desk", 'press freedom', 'censorship']),
        ('education',     ['icme', 'sub fest', 'viksit bharat', 'infirmary', 'professor',
                           'university', 'college']),
        ('culture',       ['namaaz', 'tamasha', 'sustainable fashion', 'tokyo thrift',
                           'merchandise', 'absent in the spring', 'अंध',
                           'जीवन', 'बोया',
                           'ek waqt']),
        ('gender',        ['women', 'feminist', 'gender', 'हक']),
        ('politics',      ['dictator', 'autocra', 'parliament', 'judicial', 'bjp',
                           'leftist', 'jai bhim', 'ambedkar', ' pil ', 'collective',
                           'amendment', 'solidarity', 'political', 'modi', 'government',
                           'protest', 'statement']),
        ('labour',        ['worker', 'union', 'wage', 'farmworker', 'migrant']),
        ('international', ['occupied', 'tokyo', 'global politics']),
        ('culture',       ['review', 'film', 'fashion', 'art', 'thrift']),
    ]

    def _classify(title, cat_name):
        low = (title or '').lower()
        for slug, kws in _SECTION_RULES:
            if any(kw in low for kw in kws):
                return _sid.get(slug) or _sid.get('features')
        cat = (cat_name or '').lower()
        if 'photo' in cat or 'review' in cat:
            return _sid.get('culture') or _sid.get('features')
        if 'press release' in cat:
            return _sid.get('politics') or _sid.get('features')
        if 'editorial' in cat:
            return _sid.get('features')
        return _sid.get('features')

    unclassified = db.execute(
        '''SELECT a.id, a.title, c.name as cat_name FROM articles a
           LEFT JOIN categories c ON a.category_id=c.id
           WHERE a.section_id IS NULL''').fetchall()
    for row in unclassified:
        sec_id = _classify(row[1], row[2])
        if sec_id:
            db.execute('UPDATE articles SET section_id=? WHERE id=?', [sec_id, row[0]])
    db.commit()
    db.execute('''CREATE TABLE IF NOT EXISTS publications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        title           TEXT NOT NULL,
        pub_type        TEXT NOT NULL,
        filename        TEXT,
        file_size       INTEGER DEFAULT 0,
        cover_image     TEXT,
        description     TEXT,
        issue_number    INTEGER,
        article_count   INTEGER DEFAULT 0,
        price_min       REAL DEFAULT 0,
        price_max       REAL DEFAULT 500,
        price_suggested REAL DEFAULT 0,
        currency        TEXT DEFAULT 'INR',
        is_visible      INTEGER DEFAULT 1,
        is_featured     INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        metadata        TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS editor_projects (
        article_id   INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
        folder_mounts TEXT DEFAULT '[]',
        layout       TEXT DEFAULT '{}',
        preview_path TEXT,
        updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP )''')
    db.execute('''CREATE TABLE IF NOT EXISTS editor_resources (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL DEFAULT 'text',
        title       TEXT,
        url         TEXT,
        path        TEXT,
        body        TEXT,
        thumb       TEXT,
        sort_order  INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP )''')
    db.execute('''CREATE TABLE IF NOT EXISTS column_room_meta (
        column_id  INTEGER PRIMARY KEY REFERENCES columns(id) ON DELETE CASCADE,
        template   TEXT DEFAULT '{}',
        ended_at   TEXT )''')
    db.execute('''CREATE TABLE IF NOT EXISTS dtp_projects (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        kind         TEXT NOT NULL DEFAULT 'custom',
        source_ref   TEXT,
        layout       TEXT DEFAULT '{}',
        created_at   TIMESTAMP,
        updated_at   TIMESTAMP )''')
    cols = lambda t: {r[1] for r in db.execute(f'PRAGMA table_info({t})')}
    for table, col, decl in (
        ('comments', 'sheet_row', 'INTEGER'),
        ('comments', 'username', 'TEXT'),
        ('letters', 'username', 'TEXT'),
        ('letters', 'is_public', 'INTEGER DEFAULT 0'),
    ):
        if col not in cols(table):
            db.execute(f'ALTER TABLE {table} ADD COLUMN {col} {decl}')
            if (table, col) == ('letters', 'is_public'):
                db.execute("UPDATE letters SET is_public=1 WHERE source='sheet'")
    db.execute("""
        CREATE TABLE IF NOT EXISTS ebook_requests (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_row      INTEGER UNIQUE,
            username       TEXT,
            requester_name TEXT,
            title          TEXT,
            article_ids    TEXT,
            publication_id INTEGER,
            download_url   TEXT,
            status         TEXT DEFAULT 'pending',
            error          TEXT,
            created_at     TEXT,
            built_at       TEXT
        )""")
    if 'error' not in cols('ebook_requests'):
        db.execute('ALTER TABLE ebook_requests ADD COLUMN error TEXT')
    for _col, _decl in (('email', 'TEXT'), ('emailed_at', 'TEXT')):
        if _col not in cols('ebook_requests'):
            db.execute(f'ALTER TABLE ebook_requests ADD COLUMN {_col} {_decl}')
    db.execute('''
        CREATE TABLE IF NOT EXISTS design_custom_css (
            id INTEGER PRIMARY KEY,
            design_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            custom_css TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(design_type, target_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS design_screenshots (
            id INTEGER PRIMARY KEY,
            design_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            screenshot_base64 TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(design_type, target_id, page_number)
        )
    ''')
    ve_library.ensure_publication_columns(db, commit=False)
    db.commit()
