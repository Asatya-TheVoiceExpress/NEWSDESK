
PRAGMA foreign_keys = ON;


CREATE TABLE IF NOT EXISTS authors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE,
    bio             TEXT,
    role            TEXT DEFAULT 'journalist',
    author_type     TEXT DEFAULT 'reporter',
    avatar_url      TEXT,
    social_twitter  TEXT,
    social_instagram TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS author_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id   INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    link_type   TEXT DEFAULT 'other',
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    description TEXT,
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS article_series (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    description TEXT,
    cover_image TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    author_id     INTEGER REFERENCES authors(id),
    role          TEXT DEFAULT 'author',
    email         TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP
);


CREATE TABLE IF NOT EXISTS articles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    slug           TEXT UNIQUE,
    subtitle       TEXT,
    content        TEXT,
    excerpt        TEXT,
    seo_description TEXT,
    seo_keywords   TEXT,
    author_id      INTEGER REFERENCES authors(id),
    byline         TEXT,
    category_id    INTEGER REFERENCES categories(id),
    section_id     INTEGER REFERENCES sections(id),
    status         TEXT DEFAULT 'draft',
    language       TEXT DEFAULT 'en',
    featured_image TEXT,
    latitude       REAL,
    longitude      REAL,
    location_name  TEXT,
    series_id      INTEGER REFERENCES article_series(id),
    series_order   INTEGER DEFAULT 0,
    reading_time   INTEGER DEFAULT 1,
    is_featured    INTEGER DEFAULT 0,
    published_at   TIMESTAMP,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS article_authors (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    author_id  INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    role       TEXT DEFAULT 'author',
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (article_id, author_id)
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    tag_id     INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

CREATE TABLE IF NOT EXISTS translations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    language        TEXT NOT NULL,
    title           TEXT,
    content         TEXT,
    excerpt         TEXT,
    translator_id   INTEGER REFERENCES users(id),
    translator_name TEXT,
    UNIQUE(article_id, language)
);

CREATE TABLE IF NOT EXISTS citations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    reference_text  TEXT,
    url             TEXT,
    author          TEXT,
    published_date  TEXT,
    citation_number INTEGER
);

CREATE TABLE IF NOT EXISTS annotations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id    INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    start_offset  INTEGER,
    end_offset    INTEGER,
    selected_text TEXT,
    note          TEXT,
    color         TEXT DEFAULT '#ffeb3b',
    user_id       INTEGER REFERENCES users(id),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS images (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    original_name TEXT,
    article_id    INTEGER REFERENCES articles(id),
    uploaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS article_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id   INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id),
    display_name TEXT,
    action       TEXT NOT NULL,
    language     TEXT,
    edited_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS columns (
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
    is_private  INTEGER DEFAULT 0,
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS column_authors (
    column_id  INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
    author_id  INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    role       TEXT DEFAULT 'author',
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (column_id, author_id)
);

CREATE TABLE IF NOT EXISTS column_entries (
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
);

CREATE TABLE IF NOT EXISTS column_panels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id   INTEGER NOT NULL REFERENCES column_entries(id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    image      TEXT,
    caption    TEXT,
    text       TEXT,
    span       TEXT DEFAULT 'half'
);

CREATE INDEX IF NOT EXISTS idx_entries_column_date ON column_entries(column_id, entry_date);


CREATE TABLE IF NOT EXISTS comments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind  TEXT NOT NULL DEFAULT 'article',
    target_ref   TEXT NOT NULL,
    article_id   INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    content      TEXT NOT NULL,
    ip_address   TEXT,
    user_id      INTEGER REFERENCES users(id),
    status       TEXT DEFAULT 'pending',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),
    guest_name      TEXT,
    subject         TEXT NOT NULL,
    status          TEXT DEFAULT 'open',
    ip_address      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letter_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id  INTEGER NOT NULL REFERENCES letters(id) ON DELETE CASCADE,
    sender     TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reading_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    read_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_count INTEGER DEFAULT 1,
    UNIQUE(user_id, article_id)
);


CREATE TABLE IF NOT EXISTS site_pages (
    slug       TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS newsletters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    month        INTEGER,
    year         INTEGER,
    content      TEXT,
    status       TEXT DEFAULT 'draft',
    published_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publications (
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
    metadata        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pdf_enhancements (
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
);


CREATE TABLE IF NOT EXISTS puzzle_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    puzzle_type TEXT NOT NULL,
    puzzle_date TEXT NOT NULL,
    difficulty  TEXT NOT NULL DEFAULT '',
    state       TEXT,
    elapsed     INTEGER DEFAULT 0,
    completed   INTEGER DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(puzzle_type, puzzle_date, difficulty)
);

CREATE TABLE IF NOT EXISTS user_puzzle_completions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    puzzle_type  TEXT NOT NULL,
    puzzle_date  TEXT NOT NULL,
    difficulty   TEXT DEFAULT '',
    elapsed      INTEGER DEFAULT 0,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, puzzle_type, puzzle_date, difficulty)
);

CREATE TABLE IF NOT EXISTS puzzle_word_cache (
    puzzle_date TEXT PRIMARY KEY,
    word_data   TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ip_geo_cache (
    ip           TEXT PRIMARY KEY,
    country      TEXT,
    country_code TEXT,
    city         TEXT,
    lat          REAL,
    lon          REAL,
    cached_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
