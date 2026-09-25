# Reader site and Editorial Desk

This guide covers the public Voice Express site (http://localhost:5000) and its staff area, the Editorial Desk.

## What the site does

Readers can:

- Read articles. Each article page has a **Read Mode** button for distraction-free reading.
- Browse by section (the section names sit in the top bar), and open **Columns**, **Newsstand**, **Puzzles**, **Timeline**, **Map**, **Newsletter**, **Letters**, **Authors** and **About**.
- Search. Click the magnifier in the top bar, or press / on the keyboard. Type a phrase and press Enter. The search page can also narrow results by author, section, tag, or place on a map.
- Read columns. A column page shows its entries as **Cards** or on a **Calendar**, and offers a **Booklet** download.
- Get issues from the Newsstand: published PDFs, monthly newsletter editions and broadsheets.
- Play Sudoku and crosswords under **Puzzles**, including a 30-day archive.
- Write to the editor under **Letters**. Without an account a reader can use **Write a Letter**. With a reader account the page is **My Letters** and readers can continue a conversation.
- Post a comment on an article with **Post Comment**. Comments are moderated, so they do not show at once.
- Send a story idea. **Submit a story** in the top bar opens the Submissions page. Its wording is an editable page (see Pages below).
- Create an account with **Join** in the sign-in window. Reader accounts are for reading history and puzzle scores, not for staff work.
- Change the look with the theme button (light, sepia, dark).

Some features appear only on the static copy of the site, not on localhost: the **Like** button under articles and the newsletter **Subscribe** box.

### Tags

Every article shows its tags as small chips at the bottom of the article page. Article cards in lists show up to three tag chips. Column entries show their tags as chips on the entry card and at the bottom of the entry page. Chips are labels. Clicking one does nothing. To find articles by tag, use the search page tag filter.

### What happens to reader input

1. Comments, letters, likes, newsletter subscribers, activity and ebook requests are stored in the Sheet.
2. In Newsroom, press **Collect reader input** to pull them in.
3. Moderate in Social Manager (tabs **Users**, **Comments**, **Mailbox**). A reply only reaches the reader after the next Publish.
4. In Newsroom, press **Publish to both sites**. This sends your moderation decisions back and rebuilds the emag and the Newsstand.

On localhost, comments and letters also appear directly in the Editorial Desk (see below).

## Signing in as staff

1. Open http://localhost:5000.
2. Click the circled plus icon at the top right (hover text: Sign in).
3. In the window, stay on the **Sign In** tab. Enter **Username** and **Password** and press **Sign In**. Use the admin account set up by the developer.
4. Your name appears at the top right. Click it, or use **Admin** in the menu, or **Editorial Desk** in the page footer, to open the desk.
5. To leave, click the arrow icon next to your name (hover text: Sign out).

A reader account (from **Join**) only sees "Staff access required". The **Users** section is shown to admins only.

If you forget a password, an admin resets it under Users.

## The Editorial Desk

The desk has a left menu grouped like this:

- Newsroom: **Writing Desk**, **Series**, **Pages**
- Periodicals: **Column Studio**
- Distribution: **Newsletter**
- Audience: **Comments**, **Mailbox**, **Sheet Data**
- Insights: **Analytics**
- Taxonomy & People: **Authors**, **Categories**, **Tags**, **Users** (admin only)

At the top are counts (Published, Drafts, Authors, and so on). A **Needs attention** strip lists articles with no abstract, no SEO text, no tags, no cover image, no beat, or still in draft. Click an item to see those articles.

## Tasks

### Manage a column (Column Studio)

1. Open **Column Studio**.
2. To start a column, press **+ New column**. Fill in **Title** (required), **Subtitle**, **Description**, **Cadence**, **Period (days)**, **Accent** (a colour code such as #aa0000), **Cover image** and **Status**.
3. Tick **Feature on homepage** to show it on the home page.
4. Tick **Private** to keep it staff-only. It is then never public.
5. Press **Save column**. A column set to draft is not shown to readers. Set **Status** to published to release it.
6. To edit or remove a column, use **Edit** or **Delete** on its row. Delete also removes all its entries.

To work on entries:

1. Press **Entries** on a column row.
2. Press **+ New entry**. Set **Date**, **Layout** (prose, comic, slideshow or grid), **Status**, **Title**, **Subtitle** and **Cover**.
3. Write in **Body (typeset)**. For comics or picture pages, add **Panels** with **+ panel** (image plus caption). Use the arrows to reorder.
4. Press **Save entry**. Entries have their own draft and published status.
5. **Compile booklet** makes a booklet PDF for this week, month, year or all time.

### Manage newsletters

1. Open **Newsletter**.
2. The monthly newsletter builds itself from the latest published articles the first time it is opened each month.
3. After adding stories, press **Regenerate This Month** to rebuild it.
4. **View Newsletter** opens the public page.
5. **All Editions** lists past editions. **Delete** removes one and cannot be undone.

### Manage publications (Newsstand)

Publications are handled on the public **Newsstand** page while signed in as an editor or admin. Each item shows extra buttons.

1. Open **Newsstand** from the top bar.
2. **+ Upload PDF** adds a file. Choose the PDF, and optionally a title, cover image and description. Press **Add to Newsstand**.
3. **Hide** or **Show** controls whether readers see an item. Hidden items are dimmed for you.
4. **Feature** keeps an item. Ebooks built by readers are temporary and are deleted 30 days after they are made unless featured.
5. **Delete** removes an item and cannot be undone.

### Handle the comments queue

1. Open **Comments**. The list opens on **Pending**.
2. Read each comment. It shows the name, date and the article it is on.
3. Press **Approve**, **Reject** or **Spam**. Approved comments appear under the article. **Delete** removes one for good.
4. Use the **Approved**, **Rejected** and **Spam** buttons to review earlier decisions, and **Refresh** to reload.

### Answer letters (Mailbox)

1. Open **Mailbox**. Each row is a letter with a status: open, replied or closed.
2. Click a letter to read the thread.
3. Type in the reply box and press **Send Reply**. Replies are signed Voice Express Editorial.
4. **Close Thread** ends the conversation. Use **Mailbox** with the back arrow to return to the list.

### Look at Sheet data

**Sheet Data** shows what was pulled from the Sheet. It is read only. Tabs: **Subscribers**, **Messages**, **Activity**, **Newsstand Accounts**, **Annotations**. Use **Refresh** to reload the page view. New data appears here after the developer's Sheet pull has run.

### Manage user accounts (admin only)

1. Open **Users**.
2. To add someone, enter **Username** and **Password** (at least 6 characters), choose a **Role** (Author, Translator, Typesetter, Editor or Admin), and optionally a **Linked Author**. Press **Create User**.
3. **Reset PW** sets a new password for a person.
4. The delete button removes a user. The main admin account cannot be deleted.
5. **Last Login** shows when each person last signed in.

Do not write passwords in shared notes or messages.

### Other desk sections

- **Writing Desk**: search, publish, unpublish, edit and delete articles. Tick boxes to change several at once (publish, set beat, set category, add tag, delete). **+ New Article** starts a story.
- **Series**: group related articles.
- **Pages**: edit About, Submissions and other fixed pages. Press **Edit**, change the text, press **Save Page**.
- **Authors**: add people, edit details, and add links. **Categories** and **Tags**: add, rename, merge or delete. Deleting a tag removes it from all articles.
- **Analytics**: visitor and reading figures.

## When something looks wrong

- The first load can take up to 20 seconds while the page prepares. Wait for the LOADING VOICE EXPRESS screen to go away. This is normal.
- A blank page: wait the full 20 seconds, then reload. Try a different browser tab. If it stays blank, tell the developer.
- Content looks old, or a change is missing on the reader-facing sites: run **Publish to both sites** in Newsroom. Publish rebuilds the emag and the Newsstand, and a reply or moderation decision only reaches readers after it.
- New comments or letters from readers are not showing: run **Collect reader input** in Newsroom first, then check Social Manager.
- A comment you approved does not show for readers: it needs the next Publish.
- The desk says "Staff access required": you are signed in with a reader account, or not signed in. Sign out and sign in with a staff account.
- No Users section: only admins see it.
- To report a fault, use **Report an error** in the banner at the top of the site.
