# File structure

One SQLite database (`voice_express.db`) is the source of truth. The websites, PDFs and ePubs are all built from it.

```
VoiceExpress/
  Voice Express Office.bat     double-click to open the launcher
  voice_express_office.py      launcher window: start/stop tools, Collect, Publish
  voice_express.db             the database (all content, users, publications)
  schema.sql                   base table definitions, loaded by app.py on first run
  requirements.txt             Python packages for the whole desk
  deploy.sh, deploy.config.json    server install (systemd, optional tunnel)
  broadsheet_config.json       masthead, contact and team text used in print layouts
  logo-ve.png, fonts/          logo and web fonts
  emag_shim.jsx                front-end shim used when building the emag mirror

  app.py                       reader site, public API and Editorial Desk admin (port 5000)
  templates/index.html         page shell for the reader site
  static/
    css/, js/                  reader site styles and React (JSX) front end
    media/                     built gazettes, broadsheets, booklets (PDF and HTML)
    publications/              imported PDFs and layout sidecars for the Newsstand
    uploads/                   article and column images
    logo.png, tve_logo.png     site logos

  desk_editor/                 Desk Editor (port 8787)
    serve.py, helpers.py       server
    web/                       browser app (index.html, src/*.js, styles/)
    config.json                port and paths
  columnroom/                  Columnroom (port 8789): serve.py, config.json
  social_manager/              Social Manager (port 8788): serve.py, config.json
  newsroom/                    Newsroom (port 8790): serve.py, config.json

  dtp.py                       layout tool server and command line (port 8797)
  dtp_engine.py                layout and PDF/HTML rendering engine
  make_magazine.py             magazine layout
  make_article_print.py        single-article gazette layout
  make_column_booklet.py       column booklet layout
  make_newsletter_broadsheet.py    broadsheet entry points (delegates to dtp_engine)
  pub_icons.py                 generated cover art for Newsstand items
  pdf_design_editor.py         saved layout enhancements for PDFs

  ve_pipeline.py               collect and publish chains (with --dry-run preview)
  ve_maintenance.py            builds out-of-date gazettes, broadsheets, booklets
  ve-push.py                   rebuilds the emag mirror
  librarize.py                 rebuilds the Newsstand catalog and static copy
  ve_library.py                maps artifacts to publication rows and tags
  ve_prune.py                  removes old reader-made ebooks
  ve_ebook_mail.py             emails finished ebooks to readers
  site_data_get.py             Google Sheet to database (Collect)
  site_data_put.py             database to Google Sheet (moderation, replies)
  ve_sheet_reset.py            clears Sheet row links when the Sheet is replaced
  ve_semantic.py               normalizes article HTML to the site vocabulary
  ve_export.py, ve_import.py   backup to and restore from a zip
  ve_sync.py                   pull the database from a live server
  clean_db.py                  reset a database to a clean starting state

  ve/
    db.py                      connections, schema migrations
    paths.py                   where the database and media folders are
    tags.py                    tag helpers shared by all tools
    repo.py                    tag and column-entry writes shared by the tools
  tools/
    stand_apps_script.gs       Google Apps Script for the shared Sheet

  emag/                        magazine site (its own git repository, generated)
  voiceexpressstand/           newsstand site (its own git repository, generated)
  tve/                         static landing page and logo

  docs/
    INSTRUCTIONS_BOOK.md       daily and weekly routines for the office
    guides/                    install guide and one guide per tool
  TODO.md                      open work for developers
```

Generated or local only, never committed: `__pycache__/`, `.ve_secret`, `.ve_sheet_secret`, `.ve_maint_state.json`, `.ve_pipeline.lock`, `dtp.log`, `static/_dtp_cache/`, `static/design_screenshots/`, `desk_editor/previews/`, `desk_editor/thumbs/`.

## Rules for the mirrors

`emag/` and `voiceexpressstand/` are rebuilt by every Publish. Do not edit them by hand. Change the generator instead. They are separate git repositories inside this folder and are pushed on their own.
