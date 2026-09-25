# Social Manager guide

Social Manager handles reader accounts, comments and letters. Open it at http://localhost:8788.

## The screen

- Top bar: the tabs Users, Comments and Mailbox, and the counters at the top right.
- Left side: a list. Right side: the details of the item you click.

The link **Newsroom** opens the Newsroom (localhost:8790).

## The counters at top right

The box shows two counts, for example "3 pending comments | 1 open letter".

- Pending comments: comments waiting for a decision.
- Open letters: letters with status open.

A count above zero can be clicked. It jumps to the Comments or Mailbox tab. A grey zero does nothing. The counts refresh every 30 seconds and after each action. If the box reads "notifications unavailable", the page cannot read its data.

## Where the work goes next

Replies to letters reach readers only after the Newsroom Publish. See docs/guides/newsroom.md.

## Users

The Users tab lists each account with its role, its linked author and its last login.

### Create a user account

1. Open the Users tab.
2. Click **+ New user**.
3. Type a **Username** and a **Password**. The password needs at least 6 characters.
4. Choose a **Role**: admin, editor, author or reader. The default is reader.
5. Type an **Email** if you have one.
6. Under **Linked author**, choose the author's name, or leave (none).
7. Click **Create user**.

If it fails, the button shows Failed and the reason. A username already in use will fail.

### What each role can do

Checked against the main site's code:

- admin: everything an editor can do, and the only role that can create accounts in the main site.
- editor: moderates comments, answers letters, closes letters, sees private columns, and can see and restore earlier versions of articles.
- author: writes articles. If the account has a linked author, that author is credited as co-author on articles the account edits.
- reader: the public account for commenting and writing letters. It has no staff tools.

The linked author is what ties an account to a byline. Leave it empty for accounts that are not writers.

### Change an account

1. Click the user in the list.
2. Change **Role**, **Email** or **Linked author**.
3. Click **Save**.

The username cannot be changed here.

To set a new password, click **Set new password**, type at least 6 characters and confirm. The button shows Password set.

**Delete user** removes the account after a confirmation.

## Comments

The list shows the commenter's name, the status, the article and the start of the comment. The filter buttons are pending, approved, rejected and all. The list opens on pending and shows at most the newest 400.

### Moderate a comment

1. Open the Comments tab. Pending shows first.
2. Click a comment. The right side shows the full text, the article, the time and the sender's address.
3. Click **Approve** to accept it, or **Reject** to refuse it.
4. The comment leaves the pending list and the counter goes down.

A comment already approved shows only Reject. A rejected one shows only Approve. This lets you change a decision later using the approved or rejected filter.

**Delete** removes the comment for good, after a confirmation. Use Reject instead if you may want the record.

## Mailbox

Letters are messages from readers. Each letter is a thread with a subject, the sender (username or guest name) and a status.

- open: the letter is waiting.
- replied: a reply was sent.
- closed: the thread is finished.

The filter buttons are all, open, replied and closed. The list opens on all.

### Answer a letter

1. Open the Mailbox tab. Click open to see only waiting letters.
2. Click a letter. The whole thread shows. Replies from the newsroom have a blue background.
3. Type in the **Reply** box. **Bold**, **Italic** and **Link** are above it. Link asks for a web address.
4. Click **Send reply**. The thread updates and its status becomes replied.
5. Run the Newsroom Publish. The page itself says a reply reaches the reader only after a publish.

An empty reply is not sent.

### Close and reopen a thread

Click **Close thread** when it is finished. A closed thread shows **Reopen** instead, which sets it back to open.

### Show a letter on the letters page

The button **Publish on the letters page** marks the letter as public. When it is public the button reads "Public ✓ — unpublish". Click it to take the letter off again.

If it fails with a message about letters.is_public, the database needs a one-time update. Ask whoever runs the system to run site_data_get.py.

## When something looks wrong

- The counters read "notifications unavailable": reload the page. If it stays, ask whoever runs the system.
- A reply is not on the site: run the Newsroom Publish.
- A comment is missing from the pending list: it was already decided. Check the approved or rejected filter, or all.
- A new user cannot be created: check the password length (6 or more) and that the username is not taken.
- A change to a user did not stick: click **Save**.
- A reply is not in the thread: it was not sent. Click **Send reply**.
- The page does not load: the program is not running. Ask whoever runs the system to start Social Manager.
