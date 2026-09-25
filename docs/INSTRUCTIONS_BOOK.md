# Instruction book

How the Voice Express desk runs day to day. Each tool has its own guide in `docs/guides/`. To install on a new computer, start with `docs/guides/install.md`.

## The tools

| Tool | Address | Who uses it | Guide |
|---|---|---|---|
| Launcher | desktop window | everyone, first thing | `guides/newsroom.md` |
| Desk Editor | http://localhost:8787 | writers and editors | `guides/desk-editor.md` |
| Columnroom | http://localhost:8789 | column writers (Blotter and others) | `guides/columnroom.md` |
| Social Manager | http://localhost:8788 | moderator | `guides/social-manager.md` |
| Newsroom | http://localhost:8790 | publisher | `guides/newsroom.md` |
| dtp | http://localhost:8797 | layout and print | `guides/dtp.md` |
| Reader site | http://localhost:5000 | the public site, and editors through its Editorial Desk | `guides/reader-site-admin.md` |

All tools read and write one database, `voice_express.db`. Whatever you save in one tool shows in the others straight away. The public sites do not change until you publish.

## Words used here

- **Category** is the format of a piece (report, interview, editorial). **Section** is its topic (politics, education). They are different fields. Set both.
- **Gazette** is the print PDF of one article. **Broadsheet** is the monthly print sheet. **Booklet** is a PDF of column entries for a week, month, year or all time. **Magazine** is a PDF of several articles.
- **Newsstand** is the shelf of PDFs and ePubs readers can download. **emag** is the magazine website. Both sites are files that Publish rebuilds on this computer.
- **Publish** in Newsroom rebuilds the PDFs and both sites. It does not put them on the internet. A developer does that step (see "Handing over to the developer").

## Start of day

1. Double-click **Voice Express Office.bat**.
2. Click **Start everything** and wait for green dots.
3. Open Newsroom, then **Waiting on you**. It lists comments to review, letters without a reply, ebook requests and failures.
4. Click **Collect reader input** to pull new comments, letters, likes and subscribers from the shared Sheet.

## Writing and publishing an article

1. Open the Desk Editor. Write the piece or use **Import doc** for a Word file.
2. In the inspector, set title, strapline, category, section, tags, series, byline, geotag and a featured image. An article with no featured image shows as a card without a picture.
3. Save often. Use **preview** to check it.
4. Set the status to published and save (the **Publish** button does this). Use **Library** to review or unpublish several articles at once.
5. Open Newsroom and click **Publish to both sites**. Read the preview, then click **Confirm**. Newsroom rebuilds the article's gazette, the month's broadsheet and both sites.

A full publish can take about ten minutes when many PDFs rebuild. Do not close the launcher while it runs.

## Column entries (Blotter and others)

1. Open Columnroom and pick the column.
2. Click **+ New entry**. Fill in date, layout, status, title, subtitle, cover image, body and panels.
3. Add tags. To give the same tags to every entry in the column, click **Tag all entries**, pick the tags, then **Apply**.
4. Set the status to published and click **Save entry**.
5. Check the **timeline** tab. Green means the period has an entry. Red means it is missing.
6. Publish from Newsroom. Booklets rebuild from the entries and take their tags from them. Removing a tag from entries removes it from the booklets the next time you publish.

## Tags

- Articles: Desk Editor, inspector, Document tab. Type to find a tag or create one.
- Column entries: Columnroom, Tags field.
- Newsstand items (PDFs, booklets, imported files): dtp, **Library...**, **Tags** button.
- Manage the tag list (rename, merge, delete): Desk Editor, **Taxonomy**, Tags. Merging moves every article and column entry to the tag you keep.

## Reader comments and letters

1. After **Collect reader input**, open Social Manager.
2. **Comments**: review pending comments. Approve or reject each one.
3. **Mailbox**: read letters and reply.
4. Publish from Newsroom. Approvals, rejections and replies reach the reader only after a publish.

## PDFs and print layouts

dtp builds and edits print layouts. Use it for a special issue, a hand-tuned gazette, a magazine, or to shelve an existing PDF with **Import PDF...**. Ordinary gazettes and broadsheets need no manual work. Publish builds them.

## Weekly

1. Back up: open a command window in the desk folder and run `python ve_export.py`. Copy the zip it creates to another drive.
2. Clear **Waiting on you** in Newsroom.
3. Tell the developer to push the two site repositories (below).

## Handing over to the developer

Publish rebuilds two folders on this computer, `emag` and `voiceexpressstand`. They are separate git repositories. A developer commits and pushes each one, after which the public sites update within a few minutes. The desk itself is a third repository and is pushed separately.

Give the developer the date and time of the last publish and what changed.

## If something goes wrong

| Problem | What to do |
|---|---|
| A tool will not open | Check its dot in the launcher. Click **Start** on that row. |
| Publish says a run is already going | Wait. If none is running, delete `.ve_pipeline.lock` in the desk folder and try again. |
| Publish or Collect says the Sheet secret is missing | The `.ve_sheet_secret` file is missing. Ask the developer. |
| A PDF will not build | Check that Chrome is installed. See `guides/install.md`. |
| The site shows old content | Run Publish in Newsroom, then ask the developer to push. |
| The Reader site is blank at first | It needs up to 20 seconds to load. Wait. |
| Something you saved is gone | Desk Editor keeps version history: inspector, History tab. For anything else restore the last backup zip with `python ve_import.py <zip>` (stop the tools first). |

Do not edit files inside `emag` or `voiceexpressstand` by hand. The next publish overwrites them.
