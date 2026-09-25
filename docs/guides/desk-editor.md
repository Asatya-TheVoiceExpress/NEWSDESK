# Desk Editor guide

The Desk Editor is where articles are written, tagged, previewed and published. Open it at http://localhost:8787.

## The screen

- Top bar: tabs for open articles, then the buttons **Library**, **Authors**, **Taxonomy**, **Specials**, **Pages**, **Config**, **Import doc**, **preview**, **Publish**, **Push live**, **Save**. The **+** button opens the "Open project" list. The status text next to the buttons shows "unsaved", "saving...", "saved" or "save failed".
- Toolbar under it: **B**, **I**, **link**, **fn** (footnote), **cite**, then the Insert buttons, then the **role** menu, then **-** and **+** to make the writing column narrower or wider.
- Left panel: **Media** and **Sources** tabs.
- Middle: the article itself.
- Right panel: **Document**, **Block**, **Citations**, **Translations**, **History** tabs.
- Bottom bar: word count, reading time, slug, section, save state.
- Each panel has a collapse arrow. Use the small arrow at the screen edge to bring it back.
- The **?** button (or F1, or the ? key outside a text field) lists shortcuts. The full-screen button starts focus mode. Press Esc to leave it.

## Keyboard shortcuts

- Ctrl+S: save.
- Ctrl+O: open the "Open project" list.
- Ctrl+B, Ctrl+I: bold, italic.
- Ctrl+K: add a link.
- Ctrl+Z, Ctrl+Y: undo, redo.
- / : menu of blocks to insert. Move with the arrow keys, press Enter.
- F1 or ?: help.
- Esc: leave focus mode.

Typing these at the start of a line converts it:

- `## ` makes a section heading.
- `> ` makes a spoken quote.
- `"" ` makes a pull quote.
- `- ` or `*` makes a bulleted list.
- `1. ` makes a numbered list.
- `---` makes a divider.

## Write and save a draft

1. Click **+**, then **+ New article** (or press Ctrl+O). A blank tab opens.
2. Type the text in the middle. Use the Insert buttons for headings, quotes, photos and so on (see "Blocks").
3. Open the **Document** tab on the right and fill in **Title** (see next section).
4. Click **Save** or press Ctrl+S. The first save creates the article.
5. After the first save, the article also saves by itself about two seconds after you stop typing. An article that has never been saved is not autosaved.

To reopen an article later, use **Library**, or **+** and click its card. Closing a tab with unsaved changes asks for confirmation.

## Title, slug, strapline, excerpt

All in the **Document** tab.

- **Title**: the headline.
- **Slug (URL)**: the web address part. It is made from the title when the article is first saved. Edit it to override. If the slug is already used, a number is added.
- **Strapline / subtitle**: the line under the headline.
- **Excerpt / deck**: the short summary text.
- **SEO description** and **SEO keywords**: for search engines.

## Category and section

These are two different fields.

- **Category (format)** is the kind of piece.
- **Section (beat)** is the topic area the piece belongs to. Sections are fixed; you can rename and reorder them under **Taxonomy**.

Set both in the **Document** tab. The section name shows in the bottom bar.

## Tags

1. In **Document**, click the **Tags** box.
2. Type part of a tag name. Matching tags appear. Click one, or press Enter to take the first.
3. If no tag has exactly that name, the list offers a "Create" line. Click it to make a new tag and add it.
4. Click the x on a tag to remove it from this article.

Tags are saved with the article. Use **Push live** to update the public sites. Clean up duplicates under **Taxonomy**, **Tags**.

## Series

1. In **Document**, pick a **Series** from the menu.
2. New series are made under **Taxonomy**, **Series**.

## Byline and authors

- **Authors**: click **+ author**, pick the person, pick their role in the second menu, and click x to remove. Add as many as needed.
- **Byline (free text)**: leave blank and the byline is composed from the authors list. Type here only to override it.
- If a person is not in the list, add them under **Authors** in the top bar first.

## Featured image and media

Featured image:

1. In **Document**, find **Featured image**.
2. Drag an image onto it, or click it to choose a file. You can also paste a path starting `/static/uploads/`.
3. Click the x on the image to remove it.

Media panel (left, **Media** tab):

1. Click **Add files**, or drop images on "Drop images here to stage them". They are staged, not yet in the article. The count shows "N staged".
2. **Mount folder...** asks for a full folder path on this computer. Its images appear in the panel and are referenced, not copied.
3. Double-click a thumbnail to insert it as a photo. Or drag it into the article, or into an empty cell of a photo block.
4. Right-click a thumbnail for **Insert as photo**, **Set as featured image**, **Remove from palette**.

The article is saved first when an image is added, so it has an ID to attach files to.

## Sources and citations

Sources (left, **Sources** tab) hold reporting material next to the article.

1. Click **+ Text source** to paste notes, or **+ URL source** to add a web address.
2. Rename the source in its title box. Edit the text in its body. Click the x to delete it.
3. Select text inside a source. A "Push to article" menu appears with **As body prose**, **As spoken quote**, **As field quote**, **As Q&A line**. The text is inserted at the cursor in the article.
4. Quotes pushed from a URL source also add that URL to the article's citations.

Citations (right, **Citations** tab) are the numbered reference list.

1. Click **+ citation**, or click **cite** in the toolbar.
2. Fill in **Reference text**, **URL**, **Author**, **Date**.
3. Click **Insert ref** to place its number in the text at the cursor.
4. Click **Delete** to remove a citation.

You can also select text, click **cite** and pick an existing citation.

## Footnotes

1. Put the cursor where the note number belongs.
2. Click **fn** in the toolbar (or in the small bar that appears over selected text). A number is placed in the text and a line "Note..." is added at the end of the article.
3. Replace "Note..." with the footnote text.

Right-click selected text and choose **Annotation...** to type a note in a box instead.

## Blocks

Insert buttons: **Section**, **Pull quote**, **Field quote**, **Spoken quote**, **Q&A line**, **Photo**, **Photo grid**, **Sequence**, **Comic**, **Comparison**, **Table**, **Editor's note**, **Divider**.

- **Section**: a heading with its own text. Use for each part of a long piece.
- **Pull quote**: a line from the piece shown large. Not attributed.
- **Field quote**: a quote gathered in reporting, with the source name.
- **Spoken quote**: verbatim speech, with the speaker's name.
- **Q&A line**: one line of an interview, "Name: answer".
- **Photo**: one image with a caption.
- **Photo grid**: several images together, three empty cells to start.
- **Sequence**: images that show events in order.
- **Comic**: comic panels, four to start.
- **Comparison**: side by side columns, for example Now and Then.
- **Table**: rows and columns of data.
- **Editor's note**: a note from the editor.
- **Divider**: a line that separates parts.

To turn text you already wrote into a quote, select it and use the quote button in the small bar, or right-click and choose **Pull quote**, **Field quote**, **Spoken quote** or **Section heading**. Field and spoken quotes ask for the source or speaker.

Working with blocks:

- Drag the handle at the left of a block to move it. Right-click a block for **Duplicate block**, **Move up**, **Move down**, **Delete block**.
- Right-click a photo for **Add photo credit** or **Edit photo credit**.
- The **Block** tab shows the selected block. For a photo it has **Figure type (print layout)**. For a grid it also has **+ cell**. For a grid cell it has **Cell span** (full, wide, half, third). For a comparison it has **+ column**.
- Photo blocks with no image are dropped when the article is saved. Empty captions are dropped too.

The **role** menu sets the job of a paragraph: lede, analysis, context, scene, testimony, resolution, note, dateline. "body" means plain text. It applies to normal paragraphs only.

## Geotag

In **Document**, fill **Latitude**, **Longitude** and **Location name**. To set a place on many articles at once, use the Library map (see "Library").

## Language and translations

- **Language** in **Document** is the language the article is written in. It defaults to "en".
- **Translations** tab: save the article once first.
- Target languages: Hindi, French, Spanish, Arabic, Chinese, German. The article's own language is left out.

1. Pick a language under **Add / Replace** and click **+ Open editor**.
2. Fill **Translated title**, **Translated excerpt**, **Translated content (HTML)**.
3. Optional: click **Auto-translate** to fill the boxes by machine. It says "Machine-translated - review before saving." Read it before saving. It can fail.
4. Click **Save translation**.

Existing translations are listed under "Existing" with **Edit** and x (delete, asks first).

## History

Every save is recorded.

1. Open the **History** tab.
2. Each entry shows a message, time and name.
3. Click **Restore** on the version you want and confirm. The article reloads with that version.

Restoring is itself recorded as a new version. If the tab says "Save once to start history", save the article first.

## Preview

Click **preview**. The article is saved, then opens in a new browser tab. A popup blocker may need to allow it.

## Publish and unpublish

1. Click **Publish** and confirm. The status becomes "published" and the article is saved. If **Publish date** is empty it is set to now.
2. To change the date, edit **Publish date** in **Document**.
3. To unpublish, set **Status** to "draft" in **Document** and click **Save**. Or use **Unpublish** in the Library.
4. Publishing marks the article live in the database. The public emag and Stand sites are snapshots. To update them, use **Push live**.

## Push live

1. Click **Push live**. A box opens.
2. Leave both boxes ticked: rebuild emag (articles, authors, pages, newsletters) and rebuild the Stand catalogue.
3. Click **Push live now**. It can take a minute. The log appears below.
4. The button says "Finished with errors" if something failed. Read the log.

The **Newsroom** link in the top bar opens the Newsroom app, described on screen as the place to publish to both sites.

## Library

Click **Library** (or the logo).

- Search box: finds text in title, category, section, place and tag names.
- Menu next to it: all, draft, published.
- Columns: Title, Status, Beat (section, or category if there is no section), Place.
- Click a title to open it.
- Right-click a row: **Open in editor**, **Publish** or **Unpublish**, **Delete**.

Batch actions:

1. Tick the boxes of the articles. The top box ticks all shown.
2. A bar appears with the count.
3. To change category, section or tag, pick values in "set beat/format...", "set section...", "add tag..." and click **Apply**. Adding a tag keeps existing tags.
4. **Publish** and **Unpublish** change the status of all ticked articles.
5. **Map location...** opens a map. Click a point, optionally type a place name, and click **Apply to N**.
6. **Delete** asks first and cannot be undone.

## Authors

Click **Authors**. Pick a person on the left, or click **+ New author** and type a name.

Fields: **Name**, **Role**, **Author type**, **Bio**, **Avatar URL**, **Twitter**, **Instagram**, and a **Link tree** (**+ link**, each with title, address and type). Click **Save author**.

## Taxonomy

Click **Taxonomy**. Four tabs.

- **Categories**: type a name and click **+ Add**. Click a name to rename it. **merge into** moves all articles to another category and deletes this one. **delete** removes the category; articles keep everything else.
- **Sections**: rename, and set the number that decides the order. You cannot add or delete sections here.
- **Tags**: rename, **merge into** (moves everything to another tag and deletes this one), **delete**. Use merge for duplicates. New tags are created in the article.
- **Series**: type a title and click **+ Add**. Rename by clicking the title. **delete** removes the series; its articles stay published.

Each row shows how many articles use it.

## Specials

Click **Specials**. Three tabs.

**Columns**

1. Click **+ New column** and enter a title, or pick one from the list.
2. Edit **Title**, **Subtitle**, **Description**, **Cover image**, **Cadence** (daily, weekly, monthly, custom), **Period (days, if custom)**, **Accent color**, **Status**, **Sort order**, **Authors**, and **Feature on homepage**.
3. Click **Save column**. **Delete column** removes it and all its entries.
4. Entries (dated posts) are written in Columnroom, a separate app, not here.

**Publications**: finished PDFs or ebooks for the Newsstand.

1. Click **+ Upload PDF**, choose the file, fill **Title**, **Description**, cover, **Min price**, **Max price**, **Suggested price**, **Currency**, and click **Upload**.
2. Select one to edit. Fields: the above plus **Tags (comma separated)**, **Visible on the Newsstand**, **Featured**.
3. Buttons: **Save**, **Generate icon**, **Download**, **Replace file**, **Delete** (also removes the file).
4. Reader-built ebooks are removed after 30 days unless Featured.

**Broadsheets**

1. Pick a month from the list.
2. Set the PDF enhancements and click **Save enhancements**.

PDF enhancements (also on columns and magazine publications): **Table of contents / issue index**, **Page numbers**, **Cover note**, **Accent color**, and for columns and broadsheets **Extra CSS (advanced)**. They apply at the next maintenance rebuild. They never change a PDF that is already built.

## Pages

Click **Pages**. The list has About and Submissions, plus any others.

1. Pick a page. Edit **Page title** and **Page content**. The bar has B, I, H2, paragraph, bullet list and link.
2. Click **Save page**.
3. **+ New page** asks for a slug (letters, numbers, dashes; it becomes the address) and a title.
4. Use **Push live** to update the public site.

## Config

Click **Config**. Groups: Publication, Team, Contact, Support, Print. Edit the fields and click **Save config**. The next PDF, newsletter or magazine build uses the new values. Closing with unsaved changes asks for confirmation.

Print holds broadsheet and magazine settings such as paper size, columns, current issue number and checkboxes (include sudoku, support page, grayscale images and others).

## Import doc

Click **Import doc** and choose a file: .docx, .doc, .rtf, .odt, .html, .htm, .md or .txt.

- If the article is empty, the file becomes the article. If not, it is added at the cursor.
- The first heading becomes the title if the title is blank.
- Images in the file are stored with the article.
- The article is saved first so images have somewhere to go. Check headings and quotes after import.
- It fails with a message if the converter (pandoc) is missing on the server.

## When something looks wrong

- "save failed": click **Save** again. If it keeps failing, the Desk Editor server may have stopped. Copy your text somewhere safe before reloading.
- Changes not on the public site: use **Push live**. Publishing alone does not update it.
- Image missing after save: photo blocks without an image are removed on save. Add the image first.
- A dot on a tab means unsaved changes.
- Tag not in the list: type its name and choose the Create line.
- Translations or History say "Save once": save the article first.
- Wrong text after a change: open **History** and **Restore** an earlier version.
- Auto-translate fails: write the translation by hand.
- Import fails: check the file type against the list above.
- The Library map does not load: it needs an internet connection.
