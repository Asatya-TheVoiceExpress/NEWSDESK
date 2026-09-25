# Developer TODO

Ordered by priority within each group.

## Security

- Rotate the seeded admin login. It is hardcoded in `ve/db.py` and `clean_db.py`. Read it from the environment and fail startup when unset.
- `app.py` runs `debug=True` on port 5000. Serve it with gunicorn (already in `requirements.txt`) and turn debug off before any network exposure.
- The repo tracks `voice_express.db`, which holds account hashes and reader data. Stop tracking it and ship content as an export zip (`ve_export.py`). Purge old copies from history.
- `deploy.config.json` sets `git_push: true`. That makes weekly maintenance commit the database and media to origin. Turn it off or move to a private repository.
- Keep `.ve_sheet_secret` out of every clone. Add a startup check that names the missing secret.

## Reliability

- No automated tests. Add smoke tests for the six apps (start, load the main page, one write) and for the publish chain against a copy of the database with a stubbed Sheet.
- The publish chain takes about 10 minutes when PDFs rebuild. Add per-step progress to Newsroom and a stale-lock check (`.ve_pipeline.lock` stores a PID; verify it is alive).
- Concurrent use of the desk tools is untested beyond a scripted write test. Ports 8787 and 8788 also collide with another project on some machines; make ports overridable by environment variable in all tools (only Newsroom and dtp are).
- `dtp.py status` reports fresh for an artifact whose article changed after generation. Gate on modification time instead.

## Code

- `app.py` and `desk_editor/serve.py` still carry separate copies of publication, category, section, series, author and column CRUD. Move them into `ve/repo.py` as tags and column entries already are.
- `slugify` exists three times (`app.py`, `desk_editor/helpers.py`, `ve/repo.py`). `ve_semantic.py` exists twice (root and `desk_editor/`). Keep one of each.
- `pypandoc` needs the pandoc program installed. Detect it at startup and disable "Import doc" with a message instead of failing on use.
- Booklet project keys repeat one booklet under several labels (`10:all:`, `10:all:All`, `10:all:All time`, month and year variants). Normalize the label before it becomes a `source_ref`.

## Performance

- The reader site compiles about 400 KB of JSX in the browser on every visit and loads React, Babel, Leaflet and Quill from CDNs. Precompile to one bundle and vendor the libraries. First load is 5 to 20 seconds today.

## Data

- About 280 files in `static/uploads` are unused (old generated icons and covers). Add a cleanup command.
- 12 published articles have no featured image and render as imageless cards.
- The `images` table is not populated, so media is not linked to its article.
- The category "Nightwatch: Let Every City Burn" and the series of the same name are one thing on two axes. Keep one.

## Reader features with no path

- Newsletter subscribers are collected but nothing sends mail.
- Reader messages have no reply path.
- Likes and activity rows cannot be joined to content for analysis.
- Annotations are anonymous, never shown back to the reader, and lost on the office site.
- Newsletters have no desk tool. They need the Editorial Desk panel.
