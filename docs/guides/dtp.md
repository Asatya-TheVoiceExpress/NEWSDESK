# dtp: page layout and publication design

dtp is where you lay out magazines, broadsheets, gazettes and other publications, and shelve them on the Newsstand. Open http://localhost:8797, or start it from the Voice Express Office launcher (row dtp, then Open).

## The screen

- Top bar: the project selector, then the groups File, Generate, Edit and View.
- Insert row under the top bar: buttons that add a block to the current page.
- Left panel: Pages, Masters, Layers, Article Components and Images.
- Middle: the page, with rulers.
- Right panel: the inspector. It shows Select a block until you click a block.

### Project selector

The list at the top left shows every project as [kind] name. Pick one to open it. Save before switching.

### File

- **New**: asks for a project name and creates a blank project. Click Create.
- **Library...**: opens The Newsstand shelf window (see below). Click a title to open that publication for editing.
- **Save**: saves the open project. The status line shows Saved.
- **Preview PDF**: opens the PDF of the project in a new browser tab.
- **Publish**: asks for a Title and Tags, then puts the PDF on the Newsstand shelf.
- **Export to Scribus...**: downloads a Scribus file for hand polish in Scribus. It is one way. Changes made in Scribus do not come back.
- **Import from Scribus...**: choose a Scribus .sla file. It becomes a new project.
- **Import PDF...**: shelves a finished PDF on the Newsstand without a layout.

### Generate

Each button builds a new project and opens it.

- **Magazine...**: tick the articles for the issue, then click Generate magazine. Search by title at the top.
- **Broadsheet...**: pick a month from the list. Each month shows how many articles it has.
- **Special...**: opens New special broadsheet. Fill in Edition label (printed on the masthead) and Key (short name of letters, digits and dashes, used to regenerate the same issue). Choose Build from content or Free issue (empty frames). For content, set the Published between dates, or use Pick articles... to choose exact articles (the dates are then ignored). Clear removes the picks. For a free issue, set the number of pages of empty text frames. Click Create.
- **Gazette...**: pick one article. The gazette is built from that article.

### Edit and View

- **Undo** (Ctrl+Z) and **Redo** (Ctrl+Y) step through your changes.
- **Grid(mm)**: a number for snapping. 0 means off.
- **-** and **+**: zoom out and in. The percentage is shown between them. The range is 20% to 200%.
- **Spread: Off / On**: shows facing pages side by side.

## Insert row

Click a button to add that block to the current page: **Text**, **Image**, **Headline**, **Pull quote**, **Logo**, **QR code**, **Generative art**, **Copyright**, **Author bio**, **Shape**. **Draw shape...** lets you click points on the page to draw your own shape. Click for a straight point, click and drag for a curve. Double-click or Enter finishes. Esc cancels.

## Panels

### Pages

Each page shows as a thumbnail. Click one to work on it. **+ Page** adds a page at the end.

### Masters

A master is a set of blocks shared by pages, such as a header or page number. **+ Master** creates one and opens it for editing. The banner then says Editing master and has a **Back to pages** button. The menu This page's master picks the master for the current page, or (none). Add override lets one page change a master block. The x button deletes a master.

### Layers

Every project starts with a Default layer. **+ Layer** adds one. For each layer you can tick Visible, rename it, lock it (blocks on a locked layer cannot be edited) or delete it. Blocks of a deleted layer move to the first layer.

### Article Components

Click **Browse article...**, pick an article, and its parts appear as chips: its details and its paragraphs, quotes and pictures. Drag a chip onto the page.

### Images

Search the uploaded pictures and drag one onto the page.

### Inspector

Click a block to see its settings: text, image and caption, position and size in mm, font, text colour, alignment, spacing, columns, overflow behavior, layer and text flow. Buttons include **Duplicate block** and **Delete block**. With several blocks selected you also get Align, Distribute, **Group** and **Ungroup**. Link to Next Box makes overflow text continue in another frame. Remove from chain undoes that.

## The Newsstand shelf

Open it with **Library...**. It lists everything on the Newsstand with type, file name, a note and tags. Search at the top.

- Click a title to open it in dtp. Titles marked imported PDF cannot be opened. Change them with Replace.
- The star button marks a publication as featured. Featured items are promoted on the shelf and never pruned. Reader-built ebooks are deleted 30 days after they are made unless they are featured. A filled star means featured.
- **Tags** opens Tags for that title. Type tags separated by commas and click **Save tags**.
- **Replace** asks for a new file of the same type and swaps it in, keeping the shelf entry.

## Tasks

### Make a gazette

1. Click **Gazette...** in the Generate group.
2. Search for the article and click it.
3. Wait for Generating... to clear. The project opens.
4. Adjust blocks if you need to. Click **Save**.
5. Click **Preview PDF** to check it.

### Make a broadsheet

1. Click **Broadsheet...**.
2. Click the month.
3. Check the pages, then **Save** and **Preview PDF**.

For a one-off issue use **Special...** instead.

### Publish to the Newsstand

1. Open the project. Click **Save**.
2. Click **Publish**.
3. In Publish to the Newsstand fill Title (starts as the project name) and Tags (optional, separated by commas). Click **Publish**.
4. The status line reads Published to Newsstand with a publication number.
5. In Newsroom click Publish to both sites so the Newsstand is rebuilt. It does not appear on the shelf before that.

### Tag a Newsstand item

1. Click **Library...**.
2. Find the item. Click **Tags**.
3. Type the tags, separated by commas. Click **Save tags**.
4. Click the star if the item should be featured.
5. Close the window. Publish in Newsroom to show the change on the site.

### Import a PDF

1. Click **Import PDF...** and choose the file.
2. In Import PDF to the Newsstand set Title on the Newsstand (starts as the file name), Tags (optional) and the Featured box (promoted on the shelf, never pruned).
3. Click **Import**.
4. The status line reads Shelved as publication with a number.
5. Run Publish to both sites in Newsroom so it appears on the shelf.
6. To change the file later, use **Library...** then **Replace**.

## When something looks wrong

- The status line says Failed: the text after it names the problem. Send it to the developer.
- The status stays on Generating... or Publishing...: wait. Large issues take time. If it never clears, reload the page. Unsaved changes are lost.
- A block will not move: the block or its layer is locked. Unlock it.
- Text is cut off: use Link to Next Box in the inspector to continue it in another frame, or change Overflow behavior.
- A shelf title will not open: it is an imported PDF or has no editable source. Use Replace to change the file.
- A published or imported item is not on the site: run Publish to both sites in Newsroom, then ask the developer to push the site folders.
- Nothing opens at http://localhost:8797: start dtp from the launcher.
