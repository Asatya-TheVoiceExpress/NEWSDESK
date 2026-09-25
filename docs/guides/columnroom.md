# Columnroom guide

Columnroom is where recurring columns (a Blotter, a weekly comic, a photo series) are set up and their entries written. Open it at http://localhost:8789.

## The screen

- Top bar: the column selector, the **+ New column** button and, at the far right, the current period status.
- Left side: four tabs named entries, timeline, template and settings. The entry list shows only on the entries tab.
- Right side: the editor for whatever the tab shows.

The column selector lists every column with its entry count in brackets. A column marked [private] is private. A column marked (ended) has an ended run.

The link **Newsroom** in the top bar opens the Newsroom (localhost:8790).

## Where the work goes next

Saving an entry does not put it on the site. Entries appear on the site after the Newsroom Publish. See docs/guides/newsroom.md.

## Add an entry (a Blotter-style entry)

1. Pick the column in the selector.
2. Open the entries tab.
3. Click **+ New entry**.
4. A question asks whether to start from this column's saved template. Click OK to use the template's layout and panel slots. Click Cancel to start blank.
5. The new entry appears in the list as "Untitled" with today's date, and can be clicked to open it.
6. Fill in the fields (see the next section).
7. Click **Save entry**. The button shows Saved. If it shows Failed, the reason follows the word.

The new entry exists as soon as it is created, but your typing is stored only when you click **Save entry**.

## Entry fields

- **Date**: the day the entry belongs to. The timeline and the period status use this date.
- **Layout**: prose, comic, slideshow or grid.
- **Status**: draft or published.
- **Title** and **Subtitle**.
- **Image** (the cover image): type or paste a path such as /static/uploads/..., or use the file chooser below it to upload. Accepted types: png, jpg, jpeg, gif, webp, avif. A small preview appears once an image is set.
- **Body**: the text editor. Select text, then click **Bold**, **Italic**, **Link** or **Quote**. Link asks for a web address. Quote turns the paragraph into a quotation.
- **Tags**: see below.
- **Panels (comic / grid / slideshow)**: see below.

## Tag one entry

1. Open the entry.
2. Under **Tags**, open the "add tag" list and pick a tag. It appears as a chip.
3. To remove a tag, click its chip (it ends with ×).
4. Click **Save entry**.

Only tags that already exist can be chosen. This screen cannot create new tags.

## Tag all entries in a column

1. On the entries tab, click **Tag all entries**.
2. Pick one or more tags from the list. Each shows as a chip. Click a chip to take it back out.
3. Click **Apply**. The message reads "Tagged N entries".
4. Click **Close** to hide the panel.

Apply works at once and does not need **Save entry**. It adds the tags to every entry in the column, drafts included. If you click Apply with no tag chosen, it asks you to pick at least one.

## Add panels (comic, grid, slideshow)

1. In the entry, go to **Panels** and click **+ Panel**.
2. For each panel, set an image (path or upload), a caption and a text.
3. Set the width with the list: full, wide, half or third.
4. To drop a panel, click **Remove panel**.
5. Click **Save entry**.

## Publish an entry

1. Open the entry.
2. Set **Status** to published.
3. Click **Save entry**.
4. Run the Newsroom Publish so it reaches the site.

Set Status back to draft and save to hold an entry back.

## Delete an entry

Open the entry and click **Delete entry**. A question asks you to confirm.

## Read the timeline

1. Open the timeline tab.
2. The line at the top gives the cadence, for example "Cadence: weekly". For a custom cadence it also gives the number of days.
3. Each square is one period, from the first entry (or the column's creation date if it has no entries) up to today.
4. Green means at least one entry exists for that period. Red means none.
5. Hover a square to see the period name.

Drafts count as entries. A period with only a draft shows green.

## The current period status

Top right, next to the column selector:

- current period: done (green). An entry exists for the present day, week, month or window.
- current period: missing (red). No entry exists yet for the present period. Add one.
- RUN ENDED with a date. The run was ended (see below).

The period follows the column's cadence.

## Set up a new column

1. Click **+ New column**.
2. Type the title in the box that appears and confirm. The column is created and selected.
3. Open the settings tab.
4. Choose the **Cadence**: daily, weekly, monthly or custom. For custom, type the number of days in **Period days (custom)**.
5. Choose **Status**: draft or published.
6. Tick the private box if the column must not be public.
7. Click **Save**.
8. Optionally build a template (next section).
9. Go to the entries tab and add the first entry.

A new column starts as draft and weekly.

## Settings tab

Fields: **Title**, **Cadence**, **Period days (custom)**, **Status**, and the private box. Click **Save** to keep changes.

Private columns are for admin and editor accounts only. They are never public and never in the static copies of the site.

## Template and start from template

A template is a default layout and a set of empty panel slots for new entries.

1. Open the template tab.
2. Choose the **Default layout**.
3. Under **Panel skeleton**, click **+ Panel slot** to add a slot. Type a caption hint and choose a width. Click **Remove** to drop a slot.
4. Click **Save template**. The button shows Saved.

To use it, click **+ New entry** and answer OK to "Start from this column's saved template?". Changing a template does not change entries already made.

## End a run and reopen it

Use this when a column stops running.

1. Open the settings tab.
2. Click **End this column's run** and confirm.
3. The selector shows (ended) and the top right shows RUN ENDED with the date.

Ending only marks the column as no longer active. The column stays on the site. To resume, open settings and click **Reopen run**.

## When something looks wrong

- No columns in the selector: click **+ New column**.
- The entry list is missing: you are not on the entries tab.
- A change is gone after switching entries: **Save entry** was not clicked.
- Save shows Failed: read the reason after the word. Try again, and tell whoever runs the system if it repeats.
- The image will not upload: use png, jpg, jpeg, gif, webp or avif.
- The timeline shows red for a period you did write: check the entry's **Date**. Entries count by their date, not the day they were written.
- The entry is saved but not on the site: set Status to published and run the Newsroom Publish.
- The page does not load: the program is not running. Ask whoever runs the system to start Columnroom.
