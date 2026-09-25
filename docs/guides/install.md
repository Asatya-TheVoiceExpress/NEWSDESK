# Install the desk on a new machine

For a Windows 10 or 11 office computer. Allow about 30 minutes. You need an internet connection for the first setup.

## 1. Install the programs

Install these once, in this order.

1. **Python 3.11.** Download it from python.org. On the first installer screen, tick "Add python.exe to PATH". Keep the default options, which include Tcl/Tk (the launcher window needs it).
2. **Git for Windows** from git-scm.com. Keep the default options.
3. **Google Chrome.** The layout tool uses it to make PDFs. If Chrome is not installed, step 4 installs a copy of Chromium instead.
4. **Pandoc** from pandoc.org/installing.html. It is needed only for "Import doc" in the Desk Editor (Word and similar files). Skip it if nobody imports documents.

Check the installs. Open the Start menu, type `cmd`, press Enter, then run:

```
python --version
git --version
```

Both should print a version number. If either says "not recognized", close the window and open a new one. If it still fails, run the installer again and tick the PATH option.

## 2. Get the code

Choose a short folder without spaces, for example `C:\VoiceExpress`. In the command window:

```
cd C:\
git clone https://github.com/Asatya-TheVoiceExpress/NEWSDESK.git VoiceExpress
cd VoiceExpress
git clone https://github.com/Asatya-TheVoiceExpress/emag.git emag
git clone https://github.com/Asatya-TheVoiceExpress/newsstand.git voiceexpressstand
```

`emag` (the magazine site) and `voiceexpressstand` (the newsstand site) are separate repositories that live inside the desk folder. The desk rebuilds them when you publish. If Git asks you to sign in, use the Voice Express GitHub account.

## 3. Install the Python packages

Still in the `VoiceExpress` folder:

```
pip install -r requirements.txt
python -m playwright install chromium
```

Do not use a virtual environment. The launcher starts whichever `python` is on the PATH.

## 4. Add the secret file

Collect and Publish talk to the shared Google Sheet. That needs one line of text saved in a file named `.ve_sheet_secret` in the `VoiceExpress` folder. The developer gives you the text. Without the file, Collect and Publish stop with a clear message. Everything else still works.

Do not send this file by email or commit it to Git. It is ignored by Git on purpose.

## 5. Start the desk

Double-click **Voice Express Office.bat** in the `VoiceExpress` folder. A window opens with one row per tool.

1. Click **Start everything**. Wait until every dot is green.
2. Click **Open** beside a tool to use it in the browser.

| Tool | Address | Use |
|---|---|---|
| Reader site | http://localhost:5000 | the public site and its admin area |
| Desk Editor | http://localhost:8787 | articles, authors, tags, pages |
| Social Manager | http://localhost:8788 | users, comments, letters |
| Columnroom | http://localhost:8789 | column entries such as Blotter |
| Newsroom | http://localhost:8790 | collect and publish |
| dtp | http://localhost:8797 | page layout and PDFs |

The Reader site can take up to 20 seconds to appear the first time. That is normal.

Keep the launcher window open while you work. Closing it asks whether to stop the tools.

## 6. First checks

1. Open the Reader site. You should see the front page with stories.
2. Open the Desk Editor and click **Library**. You should see the article list.
3. Open dtp and click **Library...**. You should see the newsstand shelf.
4. In dtp, click **Preview PDF**. A PDF should open. If it fails, Chrome or Chromium is not installed correctly (see below).

## The database

All content lives in one file, `voice_express.db`, in the `VoiceExpress` folder. It comes with the code when you clone it.

- Use one machine for editing at a time. Two computers editing their own copies drift apart and cannot be merged.
- Make a backup before any update or move: run `python ve_export.py`. It writes a dated zip that contains the database and uploaded images. `python ve_import.py <zip>` puts it back.
- To move the desk to another computer, install as above, then restore the latest backup zip.

## Update the code

Stop the tools, then in the `VoiceExpress` folder:

```
python ve_export.py
git pull
pip install -r requirements.txt
```

Start the desk again.

## Problems

| Symptom | Fix |
|---|---|
| "python is not recognized" | Reinstall Python and tick "Add python.exe to PATH". Open a new command window. |
| The launcher window does not open | Run `python voice_express_office.py` in the command window and read the message. |
| A tool stays red | Another program may be using its port. Ports 8787 and 8788 are used by some other projects. Close them, or ask the developer to change the port in that tool's `config.json`. |
| Preview PDF or Publish fails on PDFs | Install Google Chrome, or run `python -m playwright install chromium` again. |
| "pandoc is not installed" in Import doc | Install Pandoc, then restart the Desk Editor. |
| Collect or Publish says the Sheet secret is missing | Add the `.ve_sheet_secret` file (step 4). |
| Publish says a run is already going | Another publish is running. If none is, and the last run crashed, delete the file `.ve_pipeline.lock` in the `VoiceExpress` folder. |
| First page load is slow | Normal for the Reader site. Wait about 20 seconds. |

For day-to-day use, see `docs/INSTRUCTIONS_BOOK.md` and the guides in `docs/guides/`.
