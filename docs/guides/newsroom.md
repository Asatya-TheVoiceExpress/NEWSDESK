# Newsroom and the Office launcher

Newsroom is the page where you bring in reader input and publish the day's edition. The Office launcher is a small desktop window that starts all the office tools.

## Open the launcher

1. Double-click `Voice Express Office.bat`. The Voice Express Office window opens.
2. Click **Start everything** to start every tool, or **Start** on one row.
3. Click **Open** on a row to open that tool in your browser.

Each row shows a coloured dot and a status word:

- stopped: the tool is not running.
- starting...: you started it and it is not ready yet.
- running: the tool is up and was started from this window.
- running*: the tool is up but was started somewhere else. Open works. Stop is off, because this window did not start it.

Stop turns a tool off only if it shows running. **Stop everything** stops every tool started from this window. Closing the window asks whether to stop them too.

The rows and their ports: Newsroom 8790, Desk Editor 8787, Social Manager 8788, Columnroom 8789, dtp 8797, Reader site 5000.

The log box at the bottom shows what each tool and each pipeline run prints.

## The Newsroom page

Open http://localhost:8790 (or Open on the Newsroom row). Three tabs: **Run**, **Analytics**, **Waiting on you**. Links to the other tools and the Reader site are at the top right.

### Run

Three buttons:

- **Collect reader input**: reads comments, letters, likes, subscribers, activity and ebook requests from the shared Sheet into the database. In the Sheet it only marks imported letters and ebook results. Nothing goes live.
- **Publish to both sites**: rebuilds the emag and the Newsstand and does the mail and clean-up around it.
- **Full cycle**: Collect, then Publish.

While a run is going the buttons are grey and a log fills in below. The status beside the buttons reads running..., done, or finished with errors.

### Publish the day's edition

1. Finish the work in Desk Editor, Social Manager and Columnroom first.
2. Open Newsroom and click **Collect reader input**. Wait for done.
3. Check the Waiting on you tab (see below). Moderate comments and answer letters in Social Manager.
4. On the Run tab click **Publish to both sites**. Use **Full cycle** instead if you want Collect and Publish in one go.
5. A short preview runs first. Nothing is changed by it. A box then lists:
   - how many ebook emails will be sent to readers,
   - how many old reader ebooks and their files will be deleted,
   - how many updates will be written to the Sheet,
   - that the emag and the Newsstand will be rebuilt (files written in both site folders).
   It also shows the current queues: ebook requests, comments and newsletter subscribers.
6. Read the counts. Click **Confirm** to publish, or **Cancel** to stop. Cancel changes nothing.
7. Wait for the log to say done.

If the preview fails, the box says so and nothing is changed. Read the log.

The launcher Publish button works the same way. It runs the preview and shows a Publish box with the counts and the question Continue?. Choose OK to go ahead or Cancel to stop.

### What Publish does, in order

1. Build artifacts: makes or refreshes the PDFs and pages that are out of date. Items already up to date are skipped.
2. Push decisions out: writes your moderation decisions and letter replies to the Sheet so readers see them.
3. Prune reader ebooks: deletes reader-built ebooks older than 30 days, with their files. Featured items are kept.
4. Rebuild emag: rebuilds the emag site files in the `emag` folder.
5. Rebuild newsstand: rebuilds the Newsstand shelf files in the `voiceexpressstand` folder.
6. Email ready ebooks: sends each finished ebook to the reader who asked for it.

If step 4 or 5 fails, the run stops. If any other step fails, the run continues and ends with finished with errors.

### How long it takes

When many PDFs need rebuilding it takes about 10 minutes. Leave the page open. Do not start a second run.

### Publishing does not put the sites online

Publish only writes files into two folders inside the project: `emag` and `voiceexpressstand`. Each is a separate git repository. The developer pushes them to make the changes live. After you publish, tell the developer.

### Analytics

Shows totals (articles, publications, readers, comments, letters, subscribers, likes, messages) and Newsstand activity for the last 90 days: events, most opened, support taps, most discussed and most liked articles. A box on the page lists what the numbers cannot tell you. For example, the emag records no reads, so traffic covers the Newsstand only.

### Waiting on you

Check what is waiting:

1. Open the **Waiting on you** tab.
2. Read the three cards: Comments to review, Letters unanswered, Ebooks failed. A red card has something waiting. **open** takes you to Social Manager.
3. Below are the lists: comments awaiting review, letters with no reply yet, ebook requests with status and note, and a Download CSV link for newsletter subscribers.
4. Deal with comments and letters in Social Manager. A reply reaches the reader only after the next publish.

The list shows the newest 50 of each. Newsroom sends no newsletter email. Download CSV if you want to send from elsewhere.

## When something looks wrong

- The message says another pipeline run holds `.ve_pipeline.lock`: a run is in progress, so wait for it. If nobody is running anything (a crash or a closed window left the file), check that no Newsroom or launcher run is going, then delete the file `.ve_pipeline.lock` in the voice_express folder and try again. The message shows who holds it (pid and start time).
- The message says a job is already running: one run is already going in Newsroom. Wait for it to finish.
- The tab was closed during a run: the run keeps going. Wait, then reopen the page and check the log before starting another.
- A row shows running* but you did not start it: it was started elsewhere, for example by a colleague. Use Open. To stop it, close it where it was started.
- A row will not start: click Start and read the log for a line naming the problem. Send that line to the developer.
- Newsroom will not open: start it from the launcher and wait for running.
- Finished with errors: find the lines starting with !! or ** in the log. Send them to the developer.
- Ebooks failed card is not zero: the Ebook requests table on the same tab shows the note for each failed request.
- Changes are not on the live sites after a publish: the developer has not pushed the emag and voiceexpressstand folders yet.
