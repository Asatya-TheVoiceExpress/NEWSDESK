
window.DesignDashboard = {
  state: {
    activeType: null,
    activeId: null,
    screenshots: [],
    loading: false,
  },

  async openEditor(type, id) {
    const url = `/api/design/editor/${type}/${id}`;
    const win = window.open(url, `design_${type}_${id}`, 'width=1400,height=900,resizable=yes');
    if (win) {
      console.log(`[Design Editor] Opened ${type} #${id}`);
    }
  },

  async loadScreenshots(type, id) {
    try {
      const resp = await fetch(`/api/design/screenshots/${type}/${id}`);
      if (resp.ok) {
        const data = await resp.json();
        this.state.screenshots = data.screenshots || [];
        this.renderScreenshots();
      }
    } catch (e) {
      console.error('[DesignDashboard] screenshot load error:', e);
    }
  },

  renderScreenshots() {
    const container = document.getElementById('design-screenshot-gallery');
    if (!container) return;

    if (!this.state.screenshots.length) {
      container.innerHTML = '<p style="color:#999; font-size:12px;">No screenshots yet. Generate PDF and capture screenshots.</p>';
      return;
    }

    container.innerHTML = this.state.screenshots.map((s, i) => `
      <div style="
        border: 1px solid #ddd; border-radius: 4px; padding: 8px;
        background: white; margin-bottom: 12px;
      ">
        <div style="font-size: 11px; font-weight: bold; margin-bottom: 8px; color: #333;">
          Page ${s.page_number} <span style="color: #999; font-size: 10px;">
            (${new Date(s.created_at).toLocaleDateString()})
          </span>
        </div>
        <div style="max-height: 300px; overflow: auto; border: 1px solid #eee; border-radius: 2px;">
          <img src="data:image/png;base64,${s.screenshot_base64}"
               style="width: 100%; height: auto; display: block;">
        </div>
      </div>
    `).join('');
  },

  showModal(type, id, title) {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.5); z-index: 10000;
      display: flex; align-items: center; justify-content: center;
    `;

    modal.innerHTML = `
      <div style="
        background: white; border-radius: 8px; padding: 24px;
        max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <h2 style="margin: 0; font-size: 18px;">${title}</h2>
          <button onclick="this.closest('div').parentElement.remove()"
                  style="background: none; border: none; font-size: 24px; cursor: pointer; color: #999;">×</button>
        </div>

        <div style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #eee;">
          <button onclick="window.DesignDashboard.openEditor('${type}', ${id})"
                  style="
                    padding: 10px 16px; background: #0066cc; color: white;
                    border: none; border-radius: 4px; cursor: pointer; font-weight: 500;
                  ">
            ✏️ Open Design Editor
          </button>
        </div>

        <div id="design-screenshot-gallery"></div>

        <div style="margin-top: 16px; font-size: 12px; color: #666;">
          <strong>Workflow:</strong><br>
          1. Click "Open Design Editor" to preview & customize CSS<br>
          2. Save CSS, then click "Generate PDF"<br>
          3. Refresh this modal to see screenshots of all pages<br>
          4. Publish when satisfied with visual quality
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    this.loadScreenshots(type, id);
  },
};
