#!/usr/bin/env python3
import os
import sqlite3
import base64
from datetime import datetime

import ve.db as _ve_db

DATABASE = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'voice_express.db'))
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), 'static', 'design_screenshots')


def init_design_tables(db_path=DATABASE):
    conn = _ve_db.connect(db_path)
    _ve_db.migrate(conn)
    conn.close()


def get_custom_css(design_type, target_id, db_path=DATABASE):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT custom_css FROM design_custom_css WHERE design_type=? AND target_id=?',
        [design_type, target_id]
    ).fetchone()
    conn.close()
    return row['custom_css'] if row else ''


def save_custom_css(design_type, target_id, custom_css, db_path=DATABASE):
    conn = sqlite3.connect(db_path)
    now = datetime.utcnow().isoformat()
    conn.execute('''
        INSERT INTO design_custom_css (design_type, target_id, custom_css, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(design_type, target_id) DO UPDATE SET
            custom_css=excluded.custom_css,
            updated_at=excluded.updated_at
    ''', [design_type, target_id, custom_css, now])
    conn.commit()
    conn.close()
    return {'success': True, 'message': 'CSS saved'}


def save_screenshots(design_type, target_id, screenshots_base64_list, db_path=DATABASE):
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    conn = sqlite3.connect(db_path)
    for page_num, b64_data in enumerate(screenshots_base64_list, 1):
        fn = f'{design_type}_{target_id}_{page_num}.png'
        with open(os.path.join(SCREENSHOT_DIR, fn), 'wb') as f:
            f.write(base64.b64decode(b64_data))
        path = f'/static/design_screenshots/{fn}'
        conn.execute('''
            INSERT INTO design_screenshots (design_type, target_id, page_number, screenshot_base64)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(design_type, target_id, page_number) DO UPDATE SET
                screenshot_base64=excluded.screenshot_base64,
                created_at=CURRENT_TIMESTAMP
        ''', [design_type, target_id, page_num, path])
    conn.commit()
    conn.close()


def get_screenshots(design_type, target_id, db_path=DATABASE):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT page_number, screenshot_base64 AS url, created_at FROM design_screenshots '
        'WHERE design_type=? AND target_id=? ORDER BY page_number',
        [design_type, target_id]
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render_html_with_custom_css(html_str, custom_css):
    if not custom_css:
        return html_str

    injection = f'<style>\n{custom_css}\n</style>'

    if '</head>' in html_str:
        return html_str.replace('</head>', f'{injection}\n</head>')
    elif '<body' in html_str:
        return html_str.replace('<body', f'{injection}\n<body')
    else:
        return html_str + injection


def capture_pdf_screenshots(pdf_bytes, max_pages=None):
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        screenshots = []
        for page_num in range(len(doc)):
            if max_pages and page_num >= max_pages:
                break
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img_bytes = pix.tobytes('png')
            b64 = base64.b64encode(img_bytes).decode('utf-8')
            screenshots.append(b64)
        doc.close()
        return screenshots
    except ImportError:
        print('[design_editor] PyMuPDF not available, skipping PDF screenshots')
        return []
    except Exception as e:
        print(f'[design_editor] screenshot capture error: {e}')
        return []


EDITOR_TEMPLATE = r'''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Design Editor — __TYPE__ #__ID__</title>
<style>
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; display: flex; height: 100vh; }
.editor-sidebar {
  width: 320px; background: #f5f5f5; border-right: 1px solid #ccc;
  overflow-y: auto; padding: 16px; flex-shrink: 0;
}
.editor-main {
  flex: 1; overflow-y: auto; display: flex; flex-direction: column;
  background: #e9e9e9; padding: 20px;
}
.editor-preview {
  flex: 1; background: white; overflow: auto; position: relative;
  box-shadow: 0 0 20px rgba(0,0,0,0.1);
}
.editor-preview iframe {
  width: 100%; height: 100%; border: none;
}
.editor-heading { font-size: 14px; font-weight: bold; margin: 0 0 12px; color: #333; }
.editor-group { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #ddd; }
.editor-group:last-child { border-bottom: none; }
textarea {
  width: 100%; min-height: 200px; font-family: 'Monaco', monospace; font-size: 11px;
  padding: 8px; border: 1px solid #bbb; border-radius: 4px;
  box-sizing: border-box;
}
.editor-buttons { display: flex; gap: 8px; }
button {
  flex: 1; padding: 8px 12px; border: none; border-radius: 4px;
  font-size: 12px; font-weight: 500; cursor: pointer;
}
.btn-save { background: #0066cc; color: white; }
.btn-save:hover { background: #0052a3; }
.btn-export { background: #28a745; color: white; }
.btn-export:hover { background: #218838; }
.btn-preview { background: #6c757d; color: white; }
.btn-preview:hover { background: #5a6268; }
.editor-status {
  padding: 8px 12px; background: #e8f5e9; border-radius: 4px; font-size: 11px;
  color: #2e7d32; margin-top: 8px; display: none;
}
.editor-status.visible { display: block; }
.editor-tips {
  background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px;
  border-radius: 4px; font-size: 11px; color: #664d03; margin-top: 12px;
}
.editor-tips strong { display: block; margin-bottom: 6px; }
</style>
</head>
<body>

<div class="editor-sidebar">
  <div class="editor-heading">Design Editor</div>
  <div class="editor-group">
    <p style="font-size: 12px; color: #666; margin: 0;">
      <strong>__TYPE__</strong> #__ID__<br>
      Live CSS editor — changes appear instantly in preview.
    </p>
  </div>

  <div class="editor-group">
    <div class="editor-heading">Custom CSS</div>
    <textarea id="custom-css-input" placeholder="/* Add custom CSS here. Will override all styles. */&#10;.ap-headline { font-size: 2.5rem; }&#10;.ap-body { column-gap: 12mm; }"></textarea>
    <div class="editor-buttons">
      <button class="btn-save" onclick="saveCSS()">Save CSS</button>
      <button class="btn-preview" onclick="updatePreview()">Preview</button>
    </div>
    <div class="editor-status" id="save-status"></div>
  </div>

  <div class="editor-group">
    <div class="editor-heading">Export</div>
    <button class="btn-export" onclick="generatePDF()">Generate PDF</button>
    <p style="font-size: 11px; color: #666; margin: 8px 0 0;">
      Creates final PDF with your custom CSS applied. Screenshot verification coming next.
    </p>
  </div>

  <div class="editor-tips">
    <strong>💡 Quick Tips</strong>
    • Use developer tools (F12) to inspect elements<br>
    • Test responsiveness: Font sizes, margins, line-height<br>
    • Images: Adjust filters, max-width, borders<br>
    • Columns: Tweak column-gap, column-count, column-rule<br>
    • Typography: font-size, font-weight, letter-spacing
  </div>
</div>

<div class="editor-main">
  <div class="editor-preview">
    <iframe id="preview-frame" src="about:blank"></iframe>
  </div>
</div>

<script>
const TYPE = '__TYPE__';
const ID = __ID__;

async function loadCSS() {
  const resp = await fetch(`/api/design/custom-css/${TYPE}/${ID}`);
  if (resp.ok) {
    const data = await resp.json();
    document.getElementById('custom-css-input').value = data.custom_css || '';
  }
}

async function saveCSS() {
  const css = document.getElementById('custom-css-input').value;
  const resp = await fetch(`/api/design/custom-css/${TYPE}/${ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ custom_css: css })
  });

  const status = document.getElementById('save-status');
  if (resp.ok) {
    status.textContent = '✓ CSS saved. Preview will update when you click "Preview" or reload.';
    status.classList.add('visible');
  } else {
    status.textContent = '✗ Save failed. Check console.';
    status.classList.add('visible');
  }
  setTimeout(() => status.classList.remove('visible'), 3000);
  updatePreview();
}

async function updatePreview() {
  const resp = await fetch(`/api/design/preview/${TYPE}/${ID}`);
  if (resp.ok) {
    const html = await resp.text();
    const frame = document.getElementById('preview-frame');
    frame.srcdoc = html;
  }
}

async function generatePDF() {
  if (!confirm('Generate PDF with current custom CSS?\nYou can review screenshots after generation.')) return;

  const css = document.getElementById('custom-css-input').value;
  const resp = await fetch(`/api/design/generate-pdf/${TYPE}/${ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ custom_css: css })
  });

  if (resp.ok) {
    const data = await resp.json();
    alert('PDF generated! Capturing screenshots...');
    captureScreenshots();
  } else {
    alert('PDF generation failed. Check server logs.');
  }
}

async function captureScreenshots() {
  const resp = await fetch(`/api/design/screenshots/${TYPE}/${ID}`, { method: 'POST' });
  if (resp.ok) {
    alert('Screenshots captured! View them in the dashboard.');
  }
}

window.addEventListener('load', () => {
  loadCSS();
  updatePreview();
});
</script>

</body>
</html>
'''


if __name__ == '__main__':
    init_design_tables()
    print('[design_editor] Tables initialized')
